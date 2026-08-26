"""Опциональный индекс обезличенных договоров в Pinecone: проверка, примеры, поиск."""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

from contract_scout.config import Settings
from contract_scout.embeddings import EmbeddingBackend
from contract_scout.redact import redact_requisites

logger = logging.getLogger("contract_scout.pinecone")

# cosine: чем выше, тем похожее. Для hash-эмбеддингов порог ниже.
DEFAULT_SIMILAR_THRESHOLD = 0.78
HASH_SIMILAR_THRESHOLD = 0.55


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


class PineconeArchive:
    def __init__(self, settings: Settings, embedder: EmbeddingBackend) -> None:
        self.settings = settings
        self.embedder = embedder
        self.enabled = False
        self._index = None
        if not settings.pinecone_api_key:
            return
        try:
            from pinecone import Pinecone

            client = Pinecone(api_key=settings.pinecone_api_key)
            self._index = client.Index(settings.pinecone_index_name)
            self.enabled = True
            logger.info(
                "Pinecone archive index=%s ns=%s",
                settings.pinecone_index_name,
                settings.pinecone_namespace,
            )
        except Exception:
            logger.exception("Pinecone недоступен — архив остаётся локальным")

    @property
    def similar_threshold(self) -> float:
        if self.settings.local_only or self.settings.embedding_provider == "hash":
            return HASH_SIMILAR_THRESHOLD
        return DEFAULT_SIMILAR_THRESHOLD

    def _safe_chunks(self, chunks: List[str], *, limit: int = 12) -> List[str]:
        safe: List[str] = []
        for chunk in chunks:
            text, _ = redact_requisites(chunk)
            text = (text or "").strip()
            if text:
                safe.append(text[:2000])
            if len(safe) >= limit:
                break
        return safe

    def upsert_document(
        self,
        project_id: str,
        *,
        filename: str,
        title: str,
        contract_kind: str,
        chunks: List[str],
        role: str = "review",
        risk_score: Optional[int] = None,
        is_example: bool = False,
    ) -> bool:
        """Записать/обновить договор в индексе (чанки с общей метаданной)."""
        if not self.enabled or self._index is None:
            return False
        safe = self._safe_chunks(chunks)
        if not safe:
            # один чанк из title, чтобы вектор всё же был
            blob, _ = redact_requisites(f"{title}\n{filename}")
            safe = [(blob or title or filename)[:2000]]
        try:
            self.delete_project(project_id)
            vectors_emb = self.embedder.embed_texts(safe)
            role_final = "example" if is_example else (role or "review")
            payload = []
            for i, (text, emb) in enumerate(zip(safe, vectors_emb)):
                payload.append(
                    {
                        "id": f"{project_id}-{i}",
                        "values": emb,
                        "metadata": {
                            "project_id": project_id,
                            "filename": (filename or "")[:200],
                            "title": (title or filename or "")[:200],
                            "text": text[:800],
                            "kind": "contract",
                            "contract_kind": (contract_kind or "auto")[:40],
                            "role": role_final,
                            "is_example": bool(is_example),
                            "risk_score": int(risk_score) if risk_score is not None else -1,
                        },
                    }
                )
            self._index.upsert(vectors=payload, namespace=self.settings.pinecone_namespace)
            return True
        except Exception:
            logger.exception("Pinecone upsert failed project=%s", project_id)
            return False

    def upsert_chunks(self, project_id: str, filename: str, chunks: List[str]) -> bool:
        """Обратная совместимость: обычная индексация проверки."""
        return self.upsert_document(
            project_id,
            filename=filename,
            title=filename,
            contract_kind="auto",
            chunks=chunks,
            role="review",
            is_example=False,
        )

    def delete_project(self, project_id: str) -> bool:
        if not self.enabled or self._index is None or not project_id:
            return False
        try:
            # удаляем по префиксу id; в новых SDK — delete filter по metadata
            for attempt in (
                lambda: self._index.delete(
                    filter={"project_id": {"$eq": project_id}},
                    namespace=self.settings.pinecone_namespace,
                ),
                lambda: self._index.delete(
                    ids=[f"{project_id}-{i}" for i in range(24)],
                    namespace=self.settings.pinecone_namespace,
                ),
            ):
                try:
                    attempt()
                    return True
                except Exception:
                    continue
            return False
        except Exception:
            logger.exception("Pinecone delete failed project=%s", project_id)
            return False

    def find_similar(
        self,
        text: str,
        *,
        top_k: int = 6,
        role: Optional[str] = None,
        exclude_project_id: str = "",
    ) -> List[Dict[str, Any]]:
        if not (text or "").strip():
            return []
        q, _ = redact_requisites(text[:4000])
        if not self.enabled or self._index is None:
            return []
        try:
            emb = self.embedder.embed_query(q)
            kwargs: Dict[str, Any] = {
                "vector": emb,
                "top_k": max(top_k * 3, top_k),
                "namespace": self.settings.pinecone_namespace,
                "include_metadata": True,
            }
            if role:
                kwargs["filter"] = {"role": {"$eq": role}}
            result = self._index.query(**kwargs)
            matches = getattr(result, "matches", None)
            if matches is None and isinstance(result, dict):
                matches = result.get("matches") or []
            hits: List[Dict[str, Any]] = []
            seen = set()
            for match in matches or []:
                meta = getattr(match, "metadata", None)
                if meta is None and isinstance(match, dict):
                    meta = match.get("metadata")
                meta = meta or {}
                pid = str(meta.get("project_id") or "")
                if not pid or pid == exclude_project_id or pid in seen:
                    continue
                score = getattr(match, "score", None)
                if score is None and isinstance(match, dict):
                    score = match.get("score")
                seen.add(pid)
                hits.append(
                    {
                        "project_id": pid,
                        "filename": meta.get("filename"),
                        "title": meta.get("title") or meta.get("filename"),
                        "score": float(score or 0),
                        "snippet": meta.get("text") or "",
                        "role": meta.get("role") or "review",
                        "is_example": bool(meta.get("is_example")),
                        "risk_score": meta.get("risk_score"),
                        "contract_kind": meta.get("contract_kind"),
                    }
                )
                if len(hits) >= top_k:
                    break
            return hits
        except Exception:
            logger.exception("Pinecone query failed")
            return []

    def search(self, query: str, top_k: int = 5, *, examples_only: bool = False) -> List[Dict[str, Any]]:
        if not self.enabled or self._index is None or not (query or "").strip():
            return []
        role = "example" if examples_only else None
        return self.find_similar(query, top_k=top_k, role=role)
