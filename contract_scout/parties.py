"""Локальная книга реквизитов сторон: сохранение и поиск по названию."""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from contract_scout.draft import DraftBrief

_lock = threading.Lock()


def _norm(name: str) -> str:
    text = (name or "").lower().replace("ё", "е")
    text = re.sub(r"[«»\"'`.,]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class PartyBook:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> List[Dict[str, Any]]:
        if not self.path.is_file():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        rows = raw.get("parties") if isinstance(raw, dict) else raw
        return [row for row in (rows or []) if isinstance(row, dict)]

    def _write(self, rows: List[Dict[str, Any]]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"parties": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def upsert(self, card: Dict[str, Any]) -> None:
        name = str(card.get("name") or "").strip()
        if len(name) < 2:
            return
        card = {**card, "name": name, "key": _norm(name), "updated_at": datetime.now(timezone.utc).isoformat()}
        with _lock:
            rows = self._read()
            key = card["key"]
            rows = [row for row in rows if row.get("key") != key]
            rows.insert(0, card)
            self._write(rows[:200])

    def search(self, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        needle = _norm(query)
        with _lock:
            rows = self._read()
        if not needle:
            return rows[:limit]
        scored: List[tuple[int, Dict[str, Any]]] = []
        for row in rows:
            hay = str(row.get("key") or "")
            if hay == needle:
                scored.append((0, row))
            elif hay.startswith(needle) or needle in hay:
                scored.append((1, row))
        scored.sort(key=lambda item: (item[0], str(item[1].get("name") or "")))
        return [row for _, row in scored[:limit]]

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        key = _norm(name)
        if not key:
            return None
        with _lock:
            for row in self._read():
                if row.get("key") == key:
                    return row
        return None


def card_from_brief(brief: DraftBrief, side: str) -> Dict[str, Any]:
    prefix = "customer_" if side == "customer" else "contractor_"
    return {
        "name": getattr(brief, f"{prefix}name"),
        "person_type": getattr(brief, f"{prefix}person_type"),
        "form_label": getattr(brief, f"{prefix}form_label", ""),
        "inn_kpp": getattr(brief, f"{prefix}inn_kpp"),
        "address": getattr(brief, f"{prefix}address"),
        "phone": getattr(brief, f"{prefix}phone"),
        "email": getattr(brief, f"{prefix}email"),
        "rs": getattr(brief, f"{prefix}rs"),
        "bank": getattr(brief, f"{prefix}bank"),
        "bik": getattr(brief, f"{prefix}bik"),
        "ks": getattr(brief, f"{prefix}ks"),
        "ogrn": getattr(brief, f"{prefix}ogrn", ""),
        "rep_title": getattr(brief, f"{prefix}rep_title", ""),
        "rep": getattr(brief, f"{prefix}rep", ""),
        "basis": getattr(brief, f"{prefix}basis", ""),
    }
