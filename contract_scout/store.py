"""Локальное векторное хранилище (JSON) — как RAG в учебных ботах, без обязательного Pinecone."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from contract_scout.config import Settings
from contract_scout.embeddings import EmbeddingBackend

logger = logging.getLogger("contract_scout.store")


def _dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class VectorStore:
    def __init__(self, settings: Settings, embedder: EmbeddingBackend) -> None:
        self.settings = settings
        self.embedder = embedder
        self.path = Path(settings.data_dir) / "vector_store.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.is_file():
            self._write({"documents": []})

    def _read(self) -> Dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"documents": []}

    def _write(self, data: Dict[str, Any]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def ping(self) -> Dict[str, Any]:
        with self._lock:
            docs = self._read().get("documents") or []
        return {"ok": True, "backend": "local", "count": len(docs), "path": str(self.path)}

    def replace_namespace(self, namespace: str, rows: List[Dict[str, Any]]) -> int:
        """Полностью заменить документы одного namespace (knowledge / user contract)."""
        if not rows:
            with self._lock:
                data = self._read()
                kept = [d for d in (data.get("documents") or []) if (d.get("metadata") or {}).get("ns") != namespace]
                self._write({"documents": kept})
            return 0
        texts = [row["content"] for row in rows]
        vectors = self.embedder.embed_texts(texts)
        incoming = []
        for row, vec in zip(rows, vectors):
            meta = dict(row.get("metadata") or {})
            meta["ns"] = namespace
            incoming.append(
                {
                    "id": str(uuid.uuid4()),
                    "content": row["content"],
                    "metadata": meta,
                    "embedding": vec,
                }
            )
        with self._lock:
            data = self._read()
            kept = [d for d in (data.get("documents") or []) if (d.get("metadata") or {}).get("ns") != namespace]
            self._write({"documents": kept + incoming})
        logger.info("namespace=%s upserted=%s", namespace, len(incoming))
        return len(incoming)

    def search(
        self,
        query: str,
        *,
        namespace: Optional[str] = None,
        top_k: int = 8,
        extra_filter: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        q = self.embedder.embed_query(query)
        with self._lock:
            docs = list(self._read().get("documents") or [])
        scored: List[tuple[float, Dict[str, Any]]] = []
        for doc in docs:
            meta = doc.get("metadata") or {}
            if namespace and meta.get("ns") != namespace:
                continue
            if extra_filter:
                skip = False
                for key, value in extra_filter.items():
                    if str(meta.get(key) or "") != value:
                        skip = True
                        break
                if skip:
                    continue
            emb = doc.get("embedding") or []
            if not emb or len(emb) != len(q):
                continue
            scored.append((_dot(q, emb), doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, doc in scored[:top_k]:
            out.append(
                {
                    "id": doc.get("id"),
                    "content": doc.get("content") or "",
                    "metadata": doc.get("metadata") or {},
                    "score": score,
                }
            )
        return out
