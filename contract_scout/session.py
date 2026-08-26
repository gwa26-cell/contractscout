"""Подпись cookie посетителя — привязка кредитов ЮKassa без логина."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from typing import Optional

COOKIE = "scout_vid"


def _sign(secret: str, visitor_id: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), visitor_id.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    return f"{visitor_id}.{digest}"


def new_visitor_id() -> str:
    return uuid.uuid4().hex


def parse_cookie(secret: str, raw: Optional[str]) -> Optional[str]:
    if not raw or "." not in raw:
        return None
    visitor_id, got = raw.rsplit(".", 1)
    if not visitor_id or not got:
        return None
    expect = hmac.new(secret.encode("utf-8"), visitor_id.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(got, expect):
        return None
    return visitor_id


def issue_cookie(secret: str, visitor_id: str) -> str:
    return _sign(secret, visitor_id)
