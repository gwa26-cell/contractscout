"""Локальный архив проектов и проверенных договоров — источник для просмотра."""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def extract_contract_title(text: str) -> str:
    """Название договора из текста (не имя файла)."""
    for line in (text or "").replace("\r\n", "\n").splitlines():
        raw = line.strip()
        if not raw:
            continue
        s = re.sub(r"^#+\s*", "", raw).strip()
        s = re.sub(r"^[\*_\s]+|[\*_\s]+$", "", s)
        up = s.upper().replace("Ё", "Е")
        if any(key in up for key in ("ДОГОВОР", "СОГЛАШЕНИЕ", "КОНТРАКТ")):
            s = re.sub(r"\s*№\s*.*$", "", s, flags=re.I).strip()
            s = re.sub(r"\s{2,}", " ", s)
            return s[:180]
    for line in (text or "").splitlines():
        s = re.sub(r"^#+\s*", "", line.strip()).strip()
        if len(s) >= 12 and not s.lower().endswith((".md", ".docx", ".pdf", ".txt")):
            return s[:180]
    return ""


def _looks_like_filename(title: str) -> bool:
    t = (title or "").strip().lower()
    if not t:
        return True
    return t.endswith((".md", ".docx", ".doc", ".pdf", ".txt", ".rtf")) or t.startswith("черновик ")


class ProjectArchive:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = root / "index.json"
        self.files = root / "texts"
        self.files.mkdir(exist_ok=True)

    def _read(self) -> List[Dict[str, Any]]:
        if not self.path.is_file():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        rows = raw.get("projects") if isinstance(raw, dict) else raw
        return [row for row in (rows or []) if isinstance(row, dict)]

    def _write(self, rows: List[Dict[str, Any]]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"projects": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def add(
        self,
        *,
        kind: str,
        filename: str,
        text: str,
        contract_kind: str = "auto",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        pid = uuid.uuid4().hex[:12]
        text_path = self.files / f"{pid}.txt"
        text_path.write_text(text or "", encoding="utf-8")
        contract_title = extract_contract_title(text) or (filename or "без названия")
        rec: Dict[str, Any] = {
            "id": pid,
            "kind": kind,
            "filename": filename,
            "title": contract_title,
            "contract_kind": contract_kind,
            "status": "stored",
            "created_at": _now(),
            "preview": (text or "").replace("\n", " ")[:280],
            "chars": len(text or ""),
            "report": None,
            "in_pinecone": False,
        }
        if extra:
            rec.update(extra)
            # если в extra передали title=filename — не затираем извлечённое имя договора
            if _looks_like_filename(str(rec.get("title") or "")):
                rec["title"] = contract_title
        with _lock:
            rows = self._read()
            rows.insert(0, rec)
            self._write(rows)
        return rec

    def list(self) -> List[Dict[str, Any]]:
        with _lock:
            rows = self._read()
            dirty = False
            for row in rows:
                if _looks_like_filename(str(row.get("title") or "")):
                    text = ""
                    path = self.files / f"{row.get('id')}.txt"
                    if path.is_file():
                        try:
                            text = path.read_text(encoding="utf-8")
                        except OSError:
                            text = ""
                    extracted = extract_contract_title(text) or extract_contract_title(
                        str(row.get("preview") or "")
                    )
                    if extracted:
                        row["title"] = extracted
                        dirty = True
            if dirty:
                self._write(rows)
            return rows

    def get(self, project_id: str) -> Optional[Dict[str, Any]]:
        with _lock:
            for row in self._read():
                if row.get("id") == project_id:
                    rec = dict(row)
                    rec["text"] = self.read_text(project_id)
                    if _looks_like_filename(str(rec.get("title") or "")):
                        extracted = extract_contract_title(rec.get("text") or "")
                        if extracted:
                            rec["title"] = extracted
                    return rec
        return None

    def read_text(self, project_id: str) -> str:
        path = self.files / f"{project_id}.txt"
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")

    def update(self, project_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        with _lock:
            rows = self._read()
            found = None
            for row in rows:
                if row.get("id") == project_id:
                    row.update(fields)
                    row["updated_at"] = _now()
                    found = dict(row)
                    break
            if found is None:
                return None
            self._write(rows)
            found["text"] = self.read_text(project_id)
            return found


def public_summary(row: Dict[str, Any]) -> Dict[str, Any]:
    report = row.get("report") if isinstance(row.get("report"), dict) else {}
    return {
        "id": row.get("id"),
        "kind": row.get("kind"),
        "filename": row.get("filename"),
        "title": row.get("title"),
        "contract_kind": row.get("contract_kind"),
        "status": row.get("status"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "preview": row.get("preview"),
        "chars": row.get("chars"),
        "in_pinecone": bool(row.get("in_pinecone")),
        "is_example": bool(row.get("is_example")),
        "pinecone_action": row.get("pinecone_action"),
        "verdict": report.get("verdict"),
        "overall_score": report.get("overall_score"),
        "mode": report.get("mode"),
    }
