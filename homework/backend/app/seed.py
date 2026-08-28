from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Service

DEFAULT_SERVICES = [
    {
        "name": "Проверить договор",
        "description": "Загрузка PDF/DOCX/TXT, локальный сканер рисков, опционально разбор в ИИ.",
        "price_from": 0,
        "price_to": 490,
    },
    {
        "name": "Собрать договор",
        "description": "Бриф, реквизиты сторон, черновик и выгрузка DOCX.",
        "price_from": 490,
        "price_to": 2900,
    },
    {
        "name": "Занести в базу договор",
        "description": "Сохранение в архив проектов, поиск по названию и повторная работа с файлом.",
        "price_from": 0,
        "price_to": 0,
    },
]


def seed_services(db: Session) -> None:
    if db.query(Service).count():
        return
    for row in DEFAULT_SERVICES:
        db.add(Service(**row))
    db.commit()
