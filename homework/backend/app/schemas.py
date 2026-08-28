from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class ServiceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = ""
    price_from: int = Field(ge=0)
    price_to: int = Field(ge=0)


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


class OrderOut(BaseModel):
    id: int
    service_id: int
    client_name: str
    client_email: str
    client_phone: str
    comment: str
    created_at: datetime | None = None
    message: str = "Заявка отправлена!"

    model_config = {"from_attributes": True}
