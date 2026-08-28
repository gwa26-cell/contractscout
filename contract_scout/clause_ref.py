"""Поиск номера пункта договора рядом с цитатой или маркером риска."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_CLAUSE_PREFIX = r"(?:статья|раздел|пункт|п\.|пп\.|подпункт)\s*"
_CLAUSE_LINE_RE = re.compile(
    rf"^\s*(?:{_CLAUSE_PREFIX})?(\d+(?:\.\d+)*\.?)\s+.+",
    re.I | re.M,
)
_SIMPLE_NUM_RE = re.compile(r"^\s*(\d+)\.\s+\S", re.M)


def _normalize_ref(num: str) -> str:
    cleaned = (num or "").strip().rstrip(".")
    return f"п. {cleaned}" if cleaned else ""


def clause_ref_at_line(line: str) -> str:
    stripped = (line or "").strip()
    if not stripped:
        return ""
    m = _CLAUSE_LINE_RE.match(stripped)
    if m:
        return _normalize_ref(m.group(1))
    m2 = re.match(r"^\s*(\d+)\.\s+", stripped)
    if m2:
        return _normalize_ref(m2.group(1))
    return ""


def find_clause_for_position(text: str, pos: int) -> str:
    if not text or pos < 0:
        return ""
    before = text[: max(0, pos)]
    for line in reversed(before.splitlines()[-60:]):
        ref = clause_ref_at_line(line)
        if ref:
            return ref
    return ""


def find_clause_for_quote(text: str, quote: str) -> str:
    quote = (quote or "").strip()
    if not quote or not text:
        return ""
    for candidate in (quote, quote[:80], quote[:40]):
        if len(candidate) < 6:
            continue
        pos = text.find(candidate)
        if pos >= 0:
            return find_clause_for_position(text, pos)
    return ""


def find_clause_for_keyword(text: str, keyword: str) -> str:
    kw = (keyword or "").strip()
    if not kw or not text:
        return ""
    pos = text.lower().find(kw.lower())
    if pos < 0:
        return ""
    return find_clause_for_position(text, pos)


def excerpt_at_keyword(text: str, keyword: str, *, max_len: int = 220) -> str:
    kw = (keyword or "").strip()
    if not kw or not text:
        return kw
    low = text.lower()
    pos = low.find(kw.lower())
    if pos < 0:
        return kw
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    if end < 0:
        end = len(text)
    line = text[start:end].strip()
    if len(line) <= max_len:
        return line
    rel = pos - start
    half = max_len // 2
    cut_start = max(0, rel - half)
    cut_end = min(len(line), cut_start + max_len)
    snippet = line[cut_start:cut_end].strip()
    if cut_start > 0:
        snippet = "…" + snippet
    if cut_end < len(line):
        snippet += "…"
    return snippet


def enrich_bottleneck(b: Dict[str, Any], full_text: str) -> Dict[str, Any]:
    if not isinstance(b, dict):
        return b
    ref = str(b.get("clause_ref") or "").strip()
    quote = str(b.get("quote") or "").strip()
    if not ref and quote:
        ref = find_clause_for_quote(full_text, quote)
    if not ref:
        risk_id = str(b.get("related_risk_id") or "")
        # rule hits may only have keyword list in quote
        for part in re.split(r"[,;]", quote):
            part = part.strip()
            if part:
                ref = find_clause_for_keyword(full_text, part)
                if ref:
                    break
    if ref:
        b["clause_ref"] = ref
    if full_text and quote and len(quote) < 40:
        # rule-only: quote is often just keywords — replace with line from contract
        kw = quote.split(",")[0].strip()
        excerpt = excerpt_at_keyword(full_text, kw)
        if excerpt and len(excerpt) > len(quote):
            b["quote"] = excerpt
    return b


def enrich_bottlenecks(bottlenecks: List[Dict[str, Any]], full_text: str) -> List[Dict[str, Any]]:
    if not bottlenecks or not full_text:
        return bottlenecks
    return [enrich_bottleneck(dict(b), full_text) for b in bottlenecks]
