from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.models import BehaviorMetric, Service, User

DEFAULT_SERVICES = [
    {
        "name": "Проверить договор",
        "description": "Локальный сканер рисков и опционально разбор в ИИ.",
        "price_from": 0,
        "price_to": 490,
    },
    {
        "name": "Собрать договор",
        "description": "Бриф, реквизиты, черновик и DOCX.",
        "price_from": 490,
        "price_to": 2900,
    },
    {
        "name": "Занести в базу договор",
        "description": "Архив проектов и поиск по названию.",
        "price_from": 0,
        "price_to": 0,
    },
    {
        "name": "Исправить по рискам",
        "description": "Правка текста с учётом найденных узких мест.",
        "price_from": 490,
        "price_to": 1500,
    },
    {
        "name": "Консультация по переговорам",
        "description": "Скрипт для контрагента по результатам проверки.",
        "price_from": 1500,
        "price_to": 5000,
    },
]


def seed_services(db: Session) -> None:
    if db.query(Service).count():
        return
    for row in DEFAULT_SERVICES:
        db.add(Service(**row))
    db.commit()


def seed_admin(db: Session, *, email: str, password: str) -> None:
    if db.query(User).filter(User.email == email).first():
        return
    db.add(User(email=email, password_hash=hash_password(password)))
    db.commit()


def parse_cursor_positions(raw: str) -> list[tuple[int, int]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = raw
    points: list[tuple[int, int]] = []
    if isinstance(data, str):
        for part in re.findall(r"(\d+)\s*,\s*(\d+)", data):
            points.append((int(part[0]), int(part[1])))
        return points
    if isinstance(data, dict) and "x" in data and "y" in data:
        return [(int(data["x"]), int(data["y"]))]
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "x" in item and "y" in item:
                points.append((int(item["x"]), int(item["y"])))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                points.append((int(item[0]), int(item[1])))
            elif isinstance(item, str) and "," in item:
                x, y = item.split(",", 1)
                points.append((int(x.strip()), int(y.strip())))
    return points


def behavior_stats(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    def avg_since(since: datetime) -> float:
        val = (
            db.query(func.avg(BehaviorMetric.time_on_page))
            .filter(BehaviorMetric.created_at >= since)
            .scalar()
        )
        return float(val or 0)

    rows = (
        db.query(BehaviorMetric.cursor_positions)
        .filter(BehaviorMetric.created_at >= month_ago)
        .limit(5000)
        .all()
    )
    counter: Counter[tuple[int, int]] = Counter()
    for (raw,) in rows:
        for x, y in parse_cursor_positions(raw or ""):
            bucket = (x // 20 * 20, y // 20 * 20)
            counter[bucket] += 1
    heatmap = [
        {"x": x, "y": y, "count": count}
        for (x, y), count in counter.most_common(400)
    ]

    return {
        "avg_time_day_sec": avg_since(day_ago),
        "avg_time_week_sec": avg_since(week_ago),
        "avg_time_month_sec": avg_since(month_ago),
        "heatmap": heatmap,
    }
