"""Каталог узких мест: общие гражданские + IT и другие профили."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from contract_scout.types import normalize_kind

ROOT = Path(__file__).resolve().parent.parent
RISKS_PATH = ROOT / "knowledge" / "risks.json"
GENERAL_PATH = ROOT / "knowledge" / "general.json"

IT_ONLY = {
    "ip_background",
    "unlimited_revisions",
    "sla_247",
    "source_escrow_all",
    "warranty_any_purpose",
    "subcontract_ban",
    "change_free",
    "data_processor",
    "noncompete",
}

CORE_CLAUSES = [
    {"id": "subject", "title": "Предмет и существенные условия"},
    {"id": "price", "title": "Цена и порядок оплаты"},
    {"id": "term", "title": "Срок, расторжение и расчёты при отказе"},
    {"id": "liability", "title": "Ответственность и лимит / неустойка"},
    {"id": "law", "title": "Применимое право и подсудность"},
]

EXTRA_CLAUSES: Dict[str, List[Dict[str, str]]] = {
    "it": [
        {"id": "acceptance", "title": "Приёмка и автоприёмка по сроку молчания"},
        {"id": "ip", "title": "Интеллектуальные права: результат vs фоновый код"},
        {"id": "confidential", "title": "Конфиденциальность с разумным сроком"},
        {"id": "personal_data", "title": "Персональные данные (если есть доступ к ПДн)"},
        {"id": "change", "title": "Порядок изменения ТЗ (change request)"},
    ],
    "services": [
        {"id": "acceptance", "title": "Акт и срок проверки услуг"},
        {"id": "confidential", "title": "Конфиденциальность"},
    ],
    "work": [
        {"id": "acceptance", "title": "Сдача-приёмка результата работ"},
        {"id": "change", "title": "Изменение сметы / объёма"},
    ],
    "sale": [
        {"id": "acceptance", "title": "Передача товара, недостатки, переход риска"},
    ],
    "supply": [
        {"id": "acceptance", "title": "Отгрузка, недостача, скрытые недостатки"},
    ],
    "lease": [
        {"id": "acceptance", "title": "Акт приёма-передачи помещения / вещи"},
    ],
    "nda": [
        {"id": "confidential", "title": "Состав тайны, срок, исключения, возврат носителей"},
    ],
    "license": [
        {"id": "ip", "title": "Объём лицензии: способы, территория, срок"},
    ],
    "gph": [
        {"id": "acceptance", "title": "Акт за результат, а не за часы присутствия"},
    ],
}

CLAUSE_KEYS = {
    "subject": ["предмет", "товар", "услуг", "работ", "лиценз", "аренд"],
    "price": ["цен", "стоим", "оплат", "аванс", "арендн", "вознагражд", "процент"],
    "acceptance": ["акт", "приёмк", "приемк", "передач", "отгруз"],
    "ip": ["исключительн", "интеллектуальн", "авторск", "лиценз"],
    "liability": ["ответственн", "убытк", "неустойк", "штраф"],
    "confidential": ["конфиденциал", "nda", "тайн"],
    "personal_data": ["персональн", "152-фз", "пдн"],
    "change": ["изменен", "дополнительн", "тз", "смет"],
    "term": ["расторж", "срок действия", "отказ от"],
    "law": ["подсудност", "применим", "арбитраж", "спор"],
}


def _kinds_for_it_risk(risk_id: str) -> List[str]:
    if risk_id in IT_ONLY:
        return ["it", "license"] if risk_id in {"ip_background"} else ["it"]
    return ["general", "it", "any", "services", "work"]


def load_risks() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in (RISKS_PATH, GENERAL_PATH):
        if not path.is_file():
            continue
        for item in json.loads(path.read_text(encoding="utf-8")):
            rec = dict(item)
            if not rec.get("kinds"):
                rec["kinds"] = _kinds_for_it_risk(str(rec.get("id") or ""))
            rows.append(rec)
    return rows


def clauses_for(kind: str) -> List[Dict[str, str]]:
    extra = list(EXTRA_CLAUSES.get(kind) or [])
    seen = {c["id"] for c in CORE_CLAUSES}
    out = list(CORE_CLAUSES)
    for item in extra:
        if item["id"] not in seen:
            out.append(item)
            seen.add(item["id"])
    if kind in {"any", "auto"}:
        for item in EXTRA_CLAUSES.get("it") or []:
            if item["id"] not in seen:
                out.append(item)
                seen.add(item["id"])
    return out


def risk_matches_kind(risk: Dict[str, Any], kind: str) -> bool:
    kinds = [str(x).lower() for x in (risk.get("kinds") or ["general"])]
    if kind in {"auto", "any"}:
        return True
    if "general" in kinds:
        return True
    return kind in kinds


def scan_rules(text: str, kind: str = "any") -> List[Dict[str, Any]]:
    low = (text or "").lower()
    resolved = normalize_kind(kind, text)
    hits: List[Dict[str, Any]] = []
    for risk in load_risks():
        if not risk_matches_kind(risk, resolved):
            continue
        matched = [kw for kw in (risk.get("keywords") or []) if kw.lower() in low]
        if not matched:
            continue
        hits.append(
            {
                "id": risk["id"],
                "title": risk["title"],
                "severity": risk["severity"],
                "matched_keywords": matched,
                "why": risk["why"],
                "fix": risk["fix"],
            }
        )
    return hits


def missing_clause_hints(text: str, kind: str = "any") -> List[Dict[str, str]]:
    low = (text or "").lower()
    resolved = normalize_kind(kind, text)
    missing: List[Dict[str, str]] = []
    for item in clauses_for(resolved):
        keys = CLAUSE_KEYS.get(item["id"]) or [item["id"]]
        if not any(k in low for k in keys):
            missing.append(item)
    return missing


def knowledge_rows() -> List[Dict[str, Any]]:
    rows = []
    for risk in load_risks():
        content = (
            f"{risk['title']}. Типы: {', '.join(risk.get('kinds') or [])}. "
            f"Серьёзность: {risk['severity']}. "
            f"Почему это узкое место: {risk['why']} "
            f"Как чинить: {risk['fix']} "
            f"Маркеры: {', '.join(risk.get('keywords') or [])}"
        )
        rows.append(
            {
                "content": content,
                "metadata": {
                    "kind": "risk",
                    "risk_id": risk["id"],
                    "severity": risk["severity"],
                    "title": risk["title"],
                    "kinds": ",".join(risk.get("kinds") or []),
                },
            }
        )
    return rows
