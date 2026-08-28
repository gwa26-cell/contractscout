from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ServiceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = ""
    price_from: int = Field(ge=0)
    price_to: int = Field(ge=0)


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = None
    price_from: int | None = Field(default=None, ge=0)
    price_to: int | None = Field(default=None, ge=0)


class ServiceOut(BaseModel):
    id: int
    name: str
    description: str
    price_from: int
    price_to: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class OrderCreate(BaseModel):
    service_id: int
    client_name: str = Field(min_length=2, max_length=120)
    client_email: EmailStr
    client_phone: str = ""
    comment: str = ""
    priority: int = Field(default=2, ge=1, le=3)


class OrderOut(BaseModel):
    id: int
    service_id: int
    client_name: str
    client_email: str
    client_phone: str
    comment: str
    priority: int
    lead_temperature: str
    created_at: datetime | None = None
    message: str = "Заявка отправлена!"
    service_name: str | None = None

    model_config = {"from_attributes": True}


class BehaviorMetricCreate(BaseModel):
    application_id: int = 0
    time_on_page: int = Field(ge=0)
    buttons_clicked: str = "{}"
    cursor_positions: str = "[]"
    return_frequency: int = 0


class BehaviorMetricOut(BaseModel):
    id: int
    application_id: int
    time_on_page: int
    buttons_clicked: str
    cursor_positions: str
    return_frequency: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class BehaviorStatsOut(BaseModel):
    avg_time_day_sec: float
    avg_time_week_sec: float
    avg_time_month_sec: float
    heatmap: list[dict[str, int | float]]
