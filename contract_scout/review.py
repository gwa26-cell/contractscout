"""Гибридная проверка договора: правила + RAG по каталогу рисков + LLM."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from contract_scout.knowledge import missing_clause_hints, scan_rules
from contract_scout.llm import ChatLLM
from contract_scout.redact import redact_any, redact_requisites
from contract_scout.store import VectorStore
from contract_scout.types import kind_label, normalize_kind

logger = logging.getLogger("contract_scout.review")

DISCLAIMER = (
    "Это не юридическая консультация и не замена адвокату. "
    "Отчёт помогает найти типичные узкие места любого гражданско-правового договора "
    "(включая IT) и подготовить вопросы к юристу."
)

SEVERITY_WEIGHT = {"critical": 28, "high": 16, "medium": 8, "low": 3}

REVIEW_PROMPT = """Ты юрист по гражданским договорам РФ. Пишешь для предпринимателя, не для суда.
Тип договора (ориентир): {kind_label}.
Задача: найти УЗКИЕ МЕСТА. Не пересказывай весь документ. IT-специфику учитывай, только если она есть в тексте.

Правила:
- опирайся только на текст договора и каталог рисков;
- в тексте реквизиты сторон уже заменены на [ОРГАНИЗАЦИЯ], [ИНН], [СЧЁТ] и т.п. — не восстанавливай их;
- каждая находка должна содержать короткую цитату из договора;
- не выдумывай статьи, которых нет в тексте;
- если пункт выглядит нормальным — не завышай риск;
- язык: русский.

Каталог типичных рисков (RAG):
{knowledge}

Фрагменты договора:
{chunks}

Сработавшие правиловые маркеры:
{rules}

Верни ТОЛЬКО JSON:
{{
  "overall_score": 0-100,
  "verdict": "низкий риск | средний риск | высокий риск | критический риск",
  "summary": "3-6 предложений",
  "bottlenecks": [
    {{
      "title": "",
      "severity": "critical|high|medium|low",
      "quote": "",
      "why": "",
      "fix": "",
      "related_risk_id": ""
    }}
  ],
  "missing_clauses": [{{"title": "", "why": ""}}],
  "negotiate_script": ["короткая фраза контрагенту"],
  "detected_kind": ""
}}
"""


def _join(docs: List[Dict[str, Any]], limit: int = 9000) -> str:
    parts = []
    used = 0
    for doc in docs:
        block = (doc.get("content") or "").strip()
        if not block:
            continue
        if used + len(block) > limit:
            break
        parts.append(block)
        used += len(block)
    return "\n\n---\n\n".join(parts)


def parse_json_object(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise ValueError("Модель не вернула JSON")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("JSON не объект")
    return data


def score_from_hits(hits: List[Dict[str, Any]]) -> int:
    total = 0
    for hit in hits:
        total += SEVERITY_WEIGHT.get(str(hit.get("severity") or "low"), 3)
    return max(0, min(100, total))


def _verdict(score: int) -> str:
    if score >= 70:
        return "критический риск"
    if score >= 45:
        return "высокий риск"
    if score >= 20:
        return "средний риск"
    return "низкий риск"


def rule_only_report(full_text: str, filename: str, kind: str = "auto") -> Dict[str, Any]:
    resolved = normalize_kind(kind, full_text)
    hits = scan_rules(full_text, resolved)
    missing = missing_clause_hints(full_text, resolved)
    score = score_from_hits(hits)
    bottlenecks = [
        {
            "title": h["title"],
            "severity": h["severity"],
            "quote": ", ".join(h.get("matched_keywords") or []),
            "why": h["why"],
            "fix": h["fix"],
            "related_risk_id": h["id"],
        }
        for h in hits
    ]
    return {
        "disclaimer": DISCLAIMER,
        "filename": filename,
        "contract_kind": resolved,
        "contract_kind_label": kind_label(resolved),
        "mode": "rules",
        "overall_score": score,
        "verdict": _verdict(score),
        "summary": (
            f"Локальный сканер нашёл {len(hits)} потенциальных узких мест "
            f"и {len(missing)} возможных пробелов в структуре. "
            "Текст остался на этом компьютере: в облачный ИИ ничего не отправлялось."
        ),
        "bottlenecks": bottlenecks,
        "missing_clauses": missing,
        "negotiate_script": [
            "Просим ограничить ответственность сторон ценой договора и исключить упущенную выгоду.",
            "Неустойка — зеркальная, с потолком. Одностороннее изменение условий — только доп. соглашением.",
            "Оплата: аванс / этапы; понятный срок приёмки, молчание = приёмка.",
        ],
    }


class ReviewPipeline:
    def __init__(self, store: VectorStore, llm: ChatLLM) -> None:
        self.store = store
        self.llm = llm

    def review(
        self,
        *,
        user_ns: str,
        filename: str,
        full_text: str,
        kind: str = "auto",
        use_llm: bool = True,
    ) -> Dict[str, Any]:
        resolved = normalize_kind(kind, full_text)
        hits = scan_rules(full_text, resolved)
        query = (
            f"узкие места договора {kind_label(resolved)} ответственность оплата "
            f"неустойка расторжение предмет " + " ".join(h["title"] for h in hits[:6])
        )
        knowledge = self.store.search(query, namespace="knowledge", top_k=10)
        chunks = self.store.search(query, namespace=user_ns, top_k=self.store.settings.match_count)
        if not chunks:
            chunks = [{"content": full_text[:8000], "metadata": {"filename": filename}}]
        safe_chunks = []
        redacted_n = 0
        for ch in chunks:
            safe, n = redact_requisites(ch.get("content") or "")
            redacted_n += n
            safe_chunks.append({**ch, "content": safe})
        safe_rules = redact_any(hits)

        if not use_llm or not self.llm.settings.llm_enabled:
            report = rule_only_report(full_text, filename, resolved)
            report["rag_hits"] = len(knowledge)
            report["requisites_redacted"] = redact_requisites(full_text)[1]
            return report

        prompt = REVIEW_PROMPT.format(
            kind_label=kind_label(resolved),
            knowledge=_join(knowledge),
            chunks=_join(safe_chunks),
            rules=json.dumps(safe_rules, ensure_ascii=False, indent=2),
        )
        raw = self.llm.complete(prompt)
        try:
            data = parse_json_object(raw)
        except Exception:
            logger.exception("LLM JSON parse failed, falling back to rules")
            data = rule_only_report(full_text, filename, resolved)

        data["disclaimer"] = DISCLAIMER
        data["filename"] = filename
        data["contract_kind"] = resolved
        data["contract_kind_label"] = kind_label(resolved)
        data["mode"] = "hybrid"
        data = redact_any(data)
        data["requisites_redacted"] = redacted_n
        data.setdefault("bottlenecks", [])
        data.setdefault("missing_clauses", missing_clause_hints(full_text, resolved))
        data.setdefault("negotiate_script", [])
        if "overall_score" not in data:
            data["overall_score"] = score_from_hits(hits)
        data.setdefault("verdict", _verdict(int(data.get("overall_score") or 0)))
        data.setdefault("summary", "")
        return data


def contract_text_from_rows(rows: List[Dict[str, Any]]) -> str:
    return "\n\n".join(r.get("content") or "" for r in rows)
