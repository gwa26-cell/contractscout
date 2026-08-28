from __future__ import annotations

import os

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, hash_password, lead_temperature, verify_password
from app.database import Base, engine, get_db
from app.models import BehaviorMetric, Consultation, Order, Service, User
from app.schemas import (
    BehaviorMetricCreate,
    BehaviorMetricOut,
    BehaviorStatsOut,
    ConsultationCreate,
    ConsultationOut,
    OrderCreate,
    OrderOut,
    ServiceCreate,
    ServiceOut,
    ServiceUpdate,
    TokenOut,
    UserLogin,
    UserOut,
    UserRegister,
)
from app.seed import behavior_stats, seed_admin, seed_services

app = FastAPI(
    title="ContractScout Services API",
    version="2.0.0",
    description="Услуги, заявки, метрики поведения и админ-панель.",
)

origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    try:
        seed_services(db)
        seed_admin(
            db,
            email=os.getenv("ADMIN_EMAIL", "gwa26@bk.ru"),
            password=os.getenv("ADMIN_PASSWORD", "admin123"),
        )
    finally:
        db.close()


@app.get("/health")
def health(db: Session = Depends(get_db)):
    return {
        "ok": True,
        "services": db.query(Service).count(),
        "orders": db.query(Order).count(),
        "metrics": db.query(BehaviorMetric).count(),
        "consultations": db.query(Consultation).count(),
    }


# --- Auth ---


@app.post("/api/auth/register", response_model=UserOut, status_code=201)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="Email уже зарегистрирован")
    user = User(email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/api/auth/login", response_model=TokenOut)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    token = create_access_token(user.id, user.email)
    return TokenOut(access_token=token)


@app.get("/api/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


# --- Services CRUD ---


@app.get("/api/services", response_model=list[ServiceOut])
def list_services(db: Session = Depends(get_db)):
    return db.query(Service).order_by(Service.id).all()


@app.post("/api/services", response_model=ServiceOut, status_code=201)
def create_service(
    payload: ServiceCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if db.query(Service).filter(Service.name == payload.name).first():
        raise HTTPException(status_code=409, detail="Услуга с таким названием уже есть")
    row = Service(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.put("/api/services/{service_id}", response_model=ServiceOut)
def update_service(
    service_id: int,
    payload: ServiceUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    row = db.get(Service, service_id)
    if not row:
        raise HTTPException(status_code=404, detail="Услуга не найдена")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


@app.delete("/api/services/{service_id}", status_code=204)
def delete_service(
    service_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    row = db.get(Service, service_id)
    if not row:
        raise HTTPException(status_code=404, detail="Услуга не найдена")
    db.delete(row)
    db.commit()


# --- Orders ---


@app.post("/api/orders", response_model=OrderOut, status_code=201)
def create_order(payload: OrderCreate, db: Session = Depends(get_db)):
    service = db.get(Service, payload.service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Услуга не найдена")
    row = Order(
        **payload.model_dump(),
        lead_temperature=lead_temperature(payload.priority, payload.comment),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    out = OrderOut.model_validate(row)
    out.service_name = service.name
    out.message = "Заявка отправлена!"
    return out


@app.get("/api/orders", response_model=list[OrderOut])
def list_orders(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = db.query(Order).order_by(Order.priority.asc(), Order.created_at.desc()).limit(200).all()
    out: list[OrderOut] = []
    for row in rows:
        item = OrderOut.model_validate(row)
        item.service_name = row.service.name if row.service else None
        out.append(item)
    return out


@app.get("/api/orders/{order_id}", response_model=OrderOut)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    row = db.get(Order, order_id)
    if not row:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    out = OrderOut.model_validate(row)
    out.service_name = row.service.name if row.service else None
    return out


# --- Consultation (stub) ---


@app.post("/api/consultation", response_model=ConsultationOut, status_code=201)
@app.post("/api/consultation/", response_model=ConsultationOut, status_code=201)
def create_consultation(payload: ConsultationCreate, db: Session = Depends(get_db)):
    row = Consultation(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return ConsultationOut(id=row.id)


# --- Behavior metrics (anonymous, append-only) ---


@app.post("/api/behavior-metrics/", response_model=BehaviorMetricOut, status_code=201)
@app.post("/api/behavior-metrics", response_model=BehaviorMetricOut, status_code=201)
def create_behavior_metric(payload: BehaviorMetricCreate, db: Session = Depends(get_db)):
    row = BehaviorMetric(
        application_id=payload.application_id,
        time_on_page=payload.time_on_page,
        buttons_clicked=payload.buttons_clicked or "{}",
        cursor_positions=payload.cursor_positions or "[]",
        return_frequency=payload.return_frequency,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.get("/api/behavior-metrics/", response_model=list[BehaviorMetricOut])
@app.get("/api/behavior-metrics", response_model=list[BehaviorMetricOut])
def list_behavior_metrics(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return (
        db.query(BehaviorMetric)
        .order_by(BehaviorMetric.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@app.get("/api/behavior-metrics/stats", response_model=BehaviorStatsOut)
def behavior_metrics_stats(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return behavior_stats(db)
