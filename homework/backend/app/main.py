from __future__ import annotations

import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import Order, Service
from app.schemas import OrderCreate, OrderOut, ServiceCreate, ServiceOut
from app.seed import seed_services

app = FastAPI(
    title="ContractScout Homework API",
    version="1.0.0",
    description="Отдельный backend для сдачи ДЗ: услуги и заявки. Основной продукт — ContractScout.",
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
    finally:
        db.close()


@app.get("/health")
def health(db: Session = Depends(get_db)):
    count = db.query(Service).count()
    return {"ok": True, "services": count}


@app.get("/api/services", response_model=list[ServiceOut])
def list_services(db: Session = Depends(get_db)):
    return db.query(Service).order_by(Service.id).all()


@app.post("/api/services", response_model=ServiceOut, status_code=201)
def create_service(payload: ServiceCreate, db: Session = Depends(get_db)):
    exists = db.query(Service).filter(Service.name == payload.name).first()
    if exists:
        raise HTTPException(status_code=409, detail="Услуга с таким названием уже есть")
    row = Service(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.post("/api/orders", response_model=OrderOut, status_code=201)
def create_order(payload: OrderCreate, db: Session = Depends(get_db)):
    service = db.get(Service, payload.service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Услуга не найдена")
    row = Order(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    out = OrderOut.model_validate(row)
    out.message = "Заявка отправлена!"
    return out


@app.get("/api/orders", response_model=list[OrderOut])
def list_orders(db: Session = Depends(get_db)):
    return db.query(Order).order_by(Order.id.desc()).limit(50).all()
