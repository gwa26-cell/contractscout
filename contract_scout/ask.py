"""Вопросы по договору: поиск подходящих пунктов и простой комментарий ИИ."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from contract_scout.clause_ref import clause_ref_at_line
from contract_scout.llm import ChatLLM
from contract_scout.review import parse_json_object

logger = logging.getLogger("contract_scout.ask")

FIND_CLAUSES_PROMPT = """Ты помогаешь предпринимателю найти в договоре пункты, которые относятся к вопросу.

Вопрос пользователя:
{question}

Текст договора (реквизиты могут быть обезличены):
{contract}

Задача:
- найди 1–8 пунктов (или абзацев), которые лучше всего отвечают на вопрос;
- опирайся только на текст договора, ничего не выдумывай;
- для каждого пункта укажи номер (clause_ref), например «п. 5» или «п. 5.2», и короткую цитату;
- relevance: насколько пункт подходит (0–100);
- why: одно короткое предложение — почему этот пункт относится к вопросу;
- язык: русский.

Верни ТОЛЬКО JSON:
{{
  "answer_hint": "1–2 предложения: где в договоре искать ответ",
  "clauses": [
    {{
      "clause_ref": "п. 5",
      "quote": "цитата из пункта",
      "relevance": 80,
      "why": "почему подходит"
    }}
  ]
}}
"""

EXPLAIN_CLAUSE_PROMPT = """Ты объясняешь пункт договора простым понятным языком для человека без юридического образования.

Вопрос пользователя (если есть): {question}

Пункт: {clause_ref}

Текст пункта:
{clause_text}

Правила:
- пиши по-русски, коротко и ясно (3–8 предложений);
- без канцелярита и без выдуманных статей закона;
- скажи: о чём пункт, что это значит на практике, на что обратить внимание;
- это не юридическая консультация — мягко отметь это в конце одной фразой.

Верни ТОЛЬКО JSON:
{{
  "plain": "простое объяснение",
  "risks": ["короткий риск или нюанс", "..."],
  "questions_to_ask": ["что уточнить у контрагента или юриста"]
}}
"""

_CLAUSE_SPLIT = re.compile(
    r"(?=^\s*(?:(?:статья|раздел|пункт|п\.|пп\.|подпункт)\s*)?\d+(?:\.\d+)*\.?\s+)",
    re.I | re.M,
)


def split_clauses(text: str) -> List[Dict[str, str]]:
    """Грубо режет договор на пронумерованные блоки."""
    raw = (text or "").strip()
    if not raw:
        return []
    parts = [p.strip() for p in _CLAUSE_SPLIT.split(raw) if p and p.strip()]
    if len(parts) <= 1:
        # fallback: по строкам с номером в начале
        blocks: List[Dict[str, str]] = []
        current_ref = ""
        buf: List[str] = []
        for line in raw.splitlines():
            ref = clause_ref_at_line(line)
            if ref:
                if buf:
                    blocks.append({"clause_ref": current_ref or "фрагмент", "text": "\n".join(buf).strip()})
                current_ref = ref
                buf = [line]
            elif buf:
                buf.append(line)
        if buf:
            blocks.append({"clause_ref": current_ref or "фрагмент", "text": "\n".join(buf).strip()})
        return [b for b in blocks if len(b["text"]) >= 20]
    out: List[Dict[str, str]] = []
    for part in parts:
        first = part.splitlines()[0] if part else ""
        ref = clause_ref_at_line(first) or "фрагмент"
        if len(part) < 20:
            continue
        out.append({"clause_ref": ref, "text": part[:4000]})
    return out


def _local_keyword_hits(text: str, question: str, *, limit: int = 6) -> List[Dict[str, Any]]:
    words = [w for w in re.findall(r"[a-zа-яё0-9]{4,}", (question or "").lower()) if w]
    clauses = split_clauses(text)
    scored: List[Dict[str, Any]] = []
    for c in clauses:
        low = c["text"].lower()
        hits = [w for w in words if w in low]
        if not hits:
            continue
        quote = c["text"].strip().split("\n")[0][:220]
        scored.append(
            {
                "clause_ref": c["clause_ref"],
                "quote": quote,
                "relevance": min(95, 40 + 10 * len(hits)),
                "why": f"В тексте встречаются слова из вопроса: {', '.join(hits[:4])}",
                "text": c["text"][:2500],
            }
        )
    scored.sort(key=lambda x: int(x.get("relevance") or 0), reverse=True)
    return scored[:limit]


class AskPipeline:
    def __init__(self, llm: ChatLLM) -> None:
        self.llm = llm

    def find_clauses(self, *, contract_text: str, question: str) -> Dict[str, Any]:
        text = (contract_text or "").strip()
        q = (question or "").strip()
        if len(text) < 40:
            raise ValueError("Сначала загрузите или вставьте текст договора.")
        if len(q) < 3:
            raise ValueError("Сформулируйте вопрос по договору.")

        local = _local_keyword_hits(text, q)
        if not self.llm.settings.llm_enabled:
            return {
                "mode": "local",
                "answer_hint": "Показаны пункты по совпадению слов (без ИИ).",
                "clauses": [{k: v for k, v in c.items() if k != "text"} for c in local],
                "clauses_full": local,
            }

        prompt = FIND_CLAUSES_PROMPT.format(question=q, contract=text[:24000])
        raw = self.llm.complete(prompt, temperature=0.1, max_tokens=2500)
        try:
            data = parse_json_object(raw)
        except Exception:
            logger.exception("ask find_clauses JSON failed, fallback to local")
            return {
                "mode": "local",
                "answer_hint": "ИИ не вернул JSON — показаны локальные совпадения.",
                "clauses": [{k: v for k, v in c.items() if k != "text"} for c in local],
                "clauses_full": local,
            }

        clauses = data.get("clauses") if isinstance(data.get("clauses"), list) else []
        enriched: List[Dict[str, Any]] = []
        by_ref = {c["clause_ref"]: c for c in split_clauses(text)}
        for item in clauses[:8]:
            if not isinstance(item, dict):
                continue
            ref = str(item.get("clause_ref") or "").strip() or "пункт"
            quote = str(item.get("quote") or "").strip()
            full = ""
            if ref in by_ref:
                full = by_ref[ref]["text"]
            elif quote:
                pos = text.find(quote[:40]) if len(quote) >= 40 else text.find(quote)
                if pos >= 0:
                    start = text.rfind("\n", 0, pos) + 1
                    end = text.find("\n\n", pos)
                    if end < 0:
                        end = min(len(text), pos + 800)
                    full = text[start:end].strip()
            try:
                relevance = int(item.get("relevance") or 50)
            except (TypeError, ValueError):
                relevance = 50
            enriched.append(
                {
                    "clause_ref": ref,
                    "quote": quote or (full[:220] if full else ""),
                    "relevance": max(0, min(100, relevance)),
                    "why": str(item.get("why") or "").strip(),
                    "text": full[:2500] if full else quote,
                }
            )
        if not enriched:
            enriched = local
        public = [{k: v for k, v in c.items() if k != "text"} for c in enriched]
        return {
            "mode": "hybrid",
            "answer_hint": str(data.get("answer_hint") or "").strip(),
            "clauses": public,
            "clauses_full": enriched,
            "disclaimer": "Не является юридической консультацией.",
        }

    def explain_clause(
        self,
        *,
        clause_text: str,
        clause_ref: str = "",
        question: str = "",
    ) -> Dict[str, Any]:
        body = (clause_text or "").strip()
        if len(body) < 10:
            raise ValueError("Выберите пункт договора для комментария.")
        if not self.llm.settings.llm_enabled:
            return {
                "mode": "local",
                "plain": (
                    f"Пункт {clause_ref or 'договора'} говорит о следующем (кратко по тексту): "
                    f"{body[:400]}…"
                    if len(body) > 400
                    else body
                ),
                "risks": [],
                "questions_to_ask": ["Уточните формулировку у юриста при спорной ситуации."],
                "disclaimer": "Не является юридической консультацией.",
            }

        prompt = EXPLAIN_CLAUSE_PROMPT.format(
            question=question.strip() or "—",
            clause_ref=clause_ref.strip() or "без номера",
            clause_text=body[:6000],
        )
        raw = self.llm.complete(prompt, temperature=0.2, max_tokens=1200)
        try:
            data = parse_json_object(raw)
        except Exception:
            logger.exception("ask explain JSON failed")
            return {
                "mode": "raw",
                "plain": raw[:2000],
                "risks": [],
                "questions_to_ask": [],
                "disclaimer": "Не является юридической консультацией.",
            }
        risks = data.get("risks") if isinstance(data.get("risks"), list) else []
        qs = data.get("questions_to_ask") if isinstance(data.get("questions_to_ask"), list) else []
        return {
            "mode": "llm",
            "plain": str(data.get("plain") or "").strip(),
            "risks": [str(x).strip() for x in risks if str(x).strip()][:6],
            "questions_to_ask": [str(x).strip() for x in qs if str(x).strip()][:6],
            "disclaimer": "Не является юридической консультацией.",
        }
