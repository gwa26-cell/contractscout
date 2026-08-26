"""Типы договоров: проверка любого контракта, IT — один из профилей."""

from __future__ import annotations

from typing import Dict, List, Tuple

# id -> (человекочитаемое имя, глава/рамка для черновика)
CONTRACT_KINDS: Dict[str, Tuple[str, str]] = {
    "auto": ("Определить по тексту", "по тексту документа"),
    "any": ("Любой / смешанный", "гражданско-правовой договор РФ"),
    "it": ("IT: разработка и услуги", "возмездное оказание услуг в сфере IT, гл. 39 ГК РФ"),
    "services": ("Оказание услуг", "возмездное оказание услуг, гл. 39 ГК РФ"),
    "work": ("Подряд", "подряд, гл. 37 ГК РФ"),
    "sale": ("Купля-продажа", "купля-продажа, гл. 30 ГК РФ"),
    "supply": ("Поставка", "поставка, § 3 гл. 30 ГК РФ"),
    "lease": ("Аренда", "аренда, гл. 34 ГК РФ"),
    "nda": ("Конфиденциальность (NDA)", "соглашение о конфиденциальности"),
    "license": ("Лицензия на ПО / РИД", "лицензионный договор, ст. 1235 ГК РФ"),
    "loan": ("Заём", "заём, гл. 42 ГК РФ"),
    "agency": ("Агентский / поручение", "агентский договор, гл. 52 ГК РФ"),
    "gph": ("ГПХ (работы/услуги с физлицом)", "гражданско-правовой договор с физлицом"),
}

DETECT_HINTS: List[Tuple[str, Tuple[str, ...]]] = [
    ("it", ("программн", "разработк", "исходн", "репозитор", "api", "saas", "хостинг", "devops")),
    ("license", ("лицензион", "неисключительн", "исключительн прав", "рид")),
    ("nda", ("конфиденциал", "nda", "коммерческ тайн")),
    ("lease", ("аренд", "наём жилого", "лизинг", "помещен")),
    ("supply", ("поставк", "товарная накладн", "партия товара")),
    ("sale", ("купл", "продав", "покупател", "товар")),
    ("loan", ("заём", "заем", "процентн ставк", "займодав")),
    ("agency", ("агентск", "поручен", "комиссион")),
    ("work", ("подряд", "результат работ", "смета")),
    ("gph", ("физическ лиц", "самозанят", "гпх")),
    ("services", ("оказан услуг", "исполнитель", "заказчик")),
]


def kind_label(kind: str) -> str:
    return CONTRACT_KINDS.get(kind, CONTRACT_KINDS["any"])[0]


def kind_frame(kind: str) -> str:
    return CONTRACT_KINDS.get(kind, CONTRACT_KINDS["any"])[1]


def detect_kind(text: str) -> str:
    low = (text or "").lower()
    scores: Dict[str, int] = {}
    for kind, hints in DETECT_HINTS:
        scores[kind] = sum(1 for h in hints if h in low)
    best = max(scores, key=lambda k: scores[k])
    if scores[best] <= 0:
        return "any"
    return best


def normalize_kind(kind: str | None, text: str = "") -> str:
    raw = (kind or "auto").strip().lower()
    if raw in {"", "auto"}:
        return detect_kind(text)
    if raw in CONTRACT_KINDS:
        return raw
    return "any"


def kinds_for_select() -> List[Dict[str, str]]:
    return [{"id": k, "label": v[0]} for k, v in CONTRACT_KINDS.items()]
