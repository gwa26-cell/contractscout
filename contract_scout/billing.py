"""Локальный журнал оплат и кредитов (без ПДн договора)."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BillingLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> Dict[str, Any]:
        if not self.path.is_file():
            return {"visitors": {}, "payments": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"visitors": {}, "payments": {}}
        if not isinstance(data, dict):
            return {"visitors": {}, "payments": {}}
        data.setdefault("visitors", {})
        data.setdefault("payments", {})
        return data

    def _write(self, data: Dict[str, Any]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def credits(self, visitor_id: str) -> int:
        with _lock:
            row = (self._read().get("visitors") or {}).get(visitor_id) or {}
            return int(row.get("credits") or 0)

    def snapshot(self, visitor_id: str) -> Dict[str, Any]:
        return {"visitor_id": visitor_id, "credits": self.credits(visitor_id)}

    def try_consume(self, visitor_id: str, amount: int = 1) -> bool:
        if amount <= 0:
            return True
        with _lock:
            data = self._read()
            visitors = data.setdefault("visitors", {})
            row = visitors.setdefault(visitor_id, {"credits": 0})
            have = int(row.get("credits") or 0)
            if have < amount:
                return False
            row["credits"] = have - amount
            row["updated_at"] = _now()
            self._write(data)
            return True

    def grant(self, visitor_id: str, amount: int, *, reason: str = "") -> int:
        with _lock:
            data = self._read()
            visitors = data.setdefault("visitors", {})
            row = visitors.setdefault(visitor_id, {"credits": 0})
            row["credits"] = int(row.get("credits") or 0) + int(amount)
            row["updated_at"] = _now()
            if reason:
                row["last_reason"] = reason
            self._write(data)
            return int(row["credits"])

    def payment_applied(self, payment_id: str) -> bool:
        with _lock:
            pay = (self._read().get("payments") or {}).get(payment_id) or {}
            return pay.get("status") == "applied"

    def apply_succeeded_payment(
        self,
        *,
        payment_id: str,
        visitor_id: str,
        credits: int,
        amount: str,
        raw_status: str,
    ) -> bool:
        """Идемпотентно начислить кредиты по успешному платежу ЮKassa."""
        if raw_status != "succeeded" or not payment_id or not visitor_id:
            return False
        credits = max(0, int(credits))
        with _lock:
            data = self._read()
            payments = data.setdefault("payments", {})
            existing = payments.get(payment_id) or {}
            if existing.get("status") == "applied":
                return False
            visitors = data.setdefault("visitors", {})
            row = visitors.setdefault(visitor_id, {"credits": 0})
            row["credits"] = int(row.get("credits") or 0) + credits
            row["updated_at"] = _now()
            payments[payment_id] = {
                "id": payment_id,
                "visitor_id": visitor_id,
                "credits": credits,
                "amount": amount,
                "status": "applied",
                "applied_at": _now(),
            }
            self._write(data)
            return True

    def latest_pending(self, visitor_id: str) -> str:
        with _lock:
            payments = (self._read().get("payments") or {}).values()
            pending = [
                row
                for row in payments
                if isinstance(row, dict)
                and row.get("visitor_id") == visitor_id
                and row.get("status") == "pending"
            ]
        pending.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
        return str((pending[0].get("id") if pending else "") or "")

    def remember_pending(
        self, *, payment_id: str, visitor_id: str, credits: int, amount: str
    ) -> None:
        with _lock:
            data = self._read()
            payments = data.setdefault("payments", {})
            if (payments.get(payment_id) or {}).get("status") == "applied":
                return
            payments[payment_id] = {
                "id": payment_id,
                "visitor_id": visitor_id,
                "credits": credits,
                "amount": amount,
                "status": "pending",
                "created_at": _now(),
            }
            self._write(data)
