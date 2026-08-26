"""Вырезание реквизитов сторон перед любой отправкой во внешний ИИ."""

from __future__ import annotations

import re
from typing import Any, Dict, Tuple

# Не трогаем короткие числа вроде «7 дней» / «10%».
_INN = re.compile(r"\bИНН\s*[:№]?\s*\d{10,12}\b", re.I)
_OGRN = re.compile(r"\b(?:ОГРНИП|ОГРН)\s*[:№]?\s*\d{13,15}\b", re.I)
_KPP = re.compile(r"\bКПП\s*[:№]?\s*\d{9}\b", re.I)
_BIK = re.compile(r"\bБИК\s*[:№]?\s*\d{9}\b", re.I)
_RS = re.compile(r"\b(?:р/?сч?ё?т|расчётн\w*\s+счёт|кор(?:р)?\.?\s*счёт|к/?с)\s*[:№]?\s*\d{20}\b", re.I)
_ACCOUNT = re.compile(r"\b\d{20}\b")
_SNILS = re.compile(r"\b\d{3}-\d{3}-\d{3}\s*\d{2}\b")
_PASSPORT = re.compile(r"\b(?:паспорт|серия)\s*[:№]?\s*\d{2}\s*\d{2}\s*\d{6}\b", re.I)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", re.I)
_PHONE = re.compile(r"(?:\+7|8)[\s\-(]?\d{3}[\s\-)]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}")
_CARD = re.compile(r"\b(?:\d{4}[\s-]?){3}\d{4}\b")
_ORG = re.compile(
    r"\b(?:ООО|АО|ПАО|НАО|ЗАО|НКО|ИП)\s*(?:«[^»]{1,80}»|\"[^\"]{1,80}\"|“[^”]{1,80}”)?",
    re.I,
)
_IP_FIO = re.compile(
    r"\bИП\s+[А-ЯЁ][а-яё-]+(?:\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.|\s+[А-ЯЁ][а-яё-]+\s+[А-ЯЁ][а-яё-]+)?",
)
_ADDRESS = re.compile(
    r"(?:адрес(?:\s+места\s+нахождения)?|юридический\s+адрес|место\s+нахождения)\s*[:–-]?\s*[^\n.]{8,180}",
    re.I,
)
_FIO = re.compile(
    r"\b[А-ЯЁ][а-яё]{1,20}\s+[А-ЯЁ][а-яё]{1,20}(?:\s+[А-ЯЁ][а-яё]{1,20})?\b"
)


def redact_requisites(text: str) -> Tuple[str, int]:
    """Возвращает обезличенный текст и число замен. Условия договора не трогаем специально."""
    if not text:
        return "", 0
    count = 0
    out = text

    def sub(pattern: re.Pattern[str], repl: str) -> None:
        nonlocal out, count

        def _repl(_m: re.Match[str]) -> str:
            nonlocal count
            count += 1
            return repl

        out = pattern.sub(_repl, out)

    sub(_OGRN, "[ОГРН]")
    sub(_KPP, "[КПП]")
    sub(_BIK, "[БИК]")
    sub(_RS, "[СЧЁТ]")
    sub(_SNILS, "[СНИЛС]")
    sub(_PASSPORT, "[ПАСПОРТ]")
    sub(_EMAIL, "[EMAIL]")
    sub(_PHONE, "[ТЕЛЕФОН]")
    sub(_CARD, "[КАРТА]")
    sub(_INN, "[ИНН]")
    sub(_ACCOUNT, "[СЧЁТ]")
    sub(_ADDRESS, "адрес: [АДРЕС]")
    sub(_IP_FIO, "[ИП]")
    sub(_ORG, "[ОРГАНИЗАЦИЯ]")
    # ФИО только рядом с типовыми ролями, не каждое слово с заглавной.
    role_fio = re.compile(
        r"(директор|представитель|гражданин|физлицо|физическое лицо|паспорт на имя)\s+"
        + _FIO.pattern,
        re.I,
    )
    sub(role_fio, r"\1 [ФИО]")
    return out, count


def redact_any(value: Any) -> Any:
    if isinstance(value, str):
        return redact_requisites(value)[0]
    if isinstance(value, list):
        return [redact_any(item) for item in value]
    if isinstance(value, dict):
        return {k: redact_any(v) for k, v in value.items()}
    return value


def public_brief(data: Dict[str, Any]) -> Dict[str, Any]:
    """Бриф для ИИ без имён и реквизитов сторон."""
    allowed = {
        "contract_kind",
        "subject",
        "scope",
        "price",
        "currency",
        "prepay_percent",
        "term_days",
        "city",
        "extra",
        "contract_number",
        "contract_date",
    }
    out = {k: redact_requisites(str(v))[0] for k, v in data.items() if k in allowed and v}
    out["parties"] = "Сторона A и Сторона B (реквизиты подставятся локально, не генерируй их)"
    return out
