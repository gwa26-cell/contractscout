"""ЮKassa: создание платежа и подтверждение по API (не доверяем сырому webhook)."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Dict, Optional

from contract_scout.billing import BillingLedger
from contract_scout.config import Settings

logger = logging.getLogger("contract_scout.payments")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(normalize_email(email)))


def _payment_as_dict(payment: Any) -> Dict[str, Any]:
    if isinstance(payment, dict):
        return payment
    if hasattr(payment, "json") and callable(payment.json):
        try:
            return payment.json()
        except Exception:
            pass
    data: Dict[str, Any] = {}
    for key in ("id", "status", "amount", "metadata", "confirmation"):
        if hasattr(payment, key):
            data[key] = getattr(payment, key)
    meta = data.get("metadata")
    if meta is not None and not isinstance(meta, dict):
        try:
            data["metadata"] = dict(meta)
        except Exception:
            data["metadata"] = {}
    amount = data.get("amount")
    if amount is not None and not isinstance(amount, dict):
        data["amount"] = {"value": getattr(amount, "value", None), "currency": getattr(amount, "currency", "RUB")}
    confirmation = data.get("confirmation")
    if confirmation is not None and not isinstance(confirmation, dict):
        data["confirmation"] = {
            "type": getattr(confirmation, "type", None),
            "confirmation_url": getattr(confirmation, "confirmation_url", None),
        }
    return data


class YooKassaGateway:
    def __init__(self, settings: Settings, ledger: BillingLedger) -> None:
        self.settings = settings
        self.ledger = ledger
        self.enabled = settings.yookassa_enabled
        if self.enabled:
            try:
                from yookassa import Configuration

                Configuration.account_id = settings.yookassa_shop_id
                Configuration.secret_key = settings.yookassa_secret_key
            except Exception:
                logger.exception("Не удалось инициализировать SDK ЮKassa")
                self.enabled = False

    def create_checkout(
        self,
        *,
        visitor_id: str,
        email: str = "",
        consent: bool = False,
    ) -> Dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("ЮKassa не настроена: задайте YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY.")
        if not self.settings.public_base_url:
            raise RuntimeError("Для оплаты на сервере задайте PUBLIC_BASE_URL (https://ваш-домен).")
        email_n = normalize_email(email)
        need_receipt = self.settings.yookassa_require_receipt
        if need_receipt or email_n:
            if not consent:
                raise RuntimeError("Нужно согласие на обработку email для чека (152‑ФЗ).")
            if not valid_email(email_n):
                raise RuntimeError("Укажите корректный email для чека ЮKassa.")
        from yookassa import Payment

        credits = self.settings.yookassa_credits
        amount = self.settings.yookassa_amount
        return_url = f"{self.settings.public_base_url}/pay/return"
        payload: Dict[str, Any] = {
            "amount": {"value": amount, "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": return_url},
            "capture": True,
            "description": f"ContractScout: {credits} проверок ИИ / черновиков",
            "metadata": {"visitor_id": visitor_id, "credits": str(credits)},
        }
        if email_n:
            payload["receipt"] = {
                "customer": {"email": email_n},
                "items": [
                    {
                        "description": "Пакет проверок ИИ ContractScout",
                        "quantity": "1.00",
                        "amount": {"value": amount, "currency": "RUB"},
                        "vat_code": self.settings.yookassa_vat_code,
                        "payment_mode": "full_payment",
                        "payment_subject": "service",
                    }
                ],
            }
        payment = Payment.create(payload, str(uuid.uuid4()))
        data = _payment_as_dict(payment)
        pid = str(data.get("id") or "")
        confirm = data.get("confirmation") or {}
        url = confirm.get("confirmation_url") or ""
        if not pid or not url:
            raise RuntimeError("ЮKassa не вернула ссылку на оплату.")
        self.ledger.remember_pending(
            payment_id=pid, visitor_id=visitor_id, credits=credits, amount=amount
        )
        return {"payment_id": pid, "confirmation_url": url, "credits": credits, "amount": amount}

    def fetch_payment(self, payment_id: str) -> Optional[Dict[str, Any]]:
        if not self.enabled or not payment_id:
            return None
        try:
            from yookassa import Payment

            return _payment_as_dict(Payment.find_one(payment_id))
        except Exception:
            logger.exception("ЮKassa find_one failed id=%s", payment_id)
            return None

    def apply_payment(self, payment: Dict[str, Any]) -> bool:
        meta = payment.get("metadata") or {}
        if not isinstance(meta, dict):
            meta = {}
        amount_obj = payment.get("amount") if isinstance(payment.get("amount"), dict) else {}
        try:
            credits = int(meta.get("credits") or self.settings.yookassa_credits)
        except (TypeError, ValueError):
            credits = self.settings.yookassa_credits
        return self.ledger.apply_succeeded_payment(
            payment_id=str(payment.get("id") or ""),
            visitor_id=str(meta.get("visitor_id") or ""),
            credits=credits,
            amount=str((amount_obj or {}).get("value") or self.settings.yookassa_amount),
            raw_status=str(payment.get("status") or ""),
        )

    def handle_notification(self, body: Dict[str, Any]) -> Dict[str, Any]:
        obj = body.get("object") if isinstance(body, dict) else None
        if not isinstance(obj, dict):
            return {"ok": False, "reason": "empty"}
        pid = str(obj.get("id") or "")
        fetched = self.fetch_payment(pid) if pid else None
        if not fetched:
            return {"ok": True, "applied": False, "reason": "pending_verify", "payment_id": pid}
        applied = self.apply_payment(fetched)
        return {"ok": True, "applied": applied, "payment_id": pid, "status": fetched.get("status")}

    def sync_payment(self, payment_id: str) -> Dict[str, Any]:
        payment = self.fetch_payment(payment_id)
        if not payment:
            return {"ok": False, "applied": False}
        applied = self.apply_payment(payment)
        return {"ok": True, "applied": applied, "status": payment.get("status")}
