"""Локальные эмбеддинги MiniLM или OpenAI-совместимый API."""

from __future__ import annotations

from functools import lru_cache
from typing import List

from contract_scout.config import Settings


def _hash_embed(texts: List[str], dim: int = 256) -> List[List[float]]:
    """Запасной вектор без PyTorch, чтобы локально поднять сервис без MiniLM."""
    import hashlib
    import math

    out: List[List[float]] = []
    for text in texts:
        vec = [0.0] * dim
        tokens = (text or "").lower().split()
        if not tokens:
            tokens = ["_empty_"]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8", errors="ignore")).digest()
            for i in range(0, min(len(digest), dim // 2)):
                vec[i % dim] += (digest[i] - 128) / 128.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        out.append([x / norm for x in vec])
    return out


@lru_cache(maxsize=1)
def _local_model(model_name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


class EmbeddingBackend:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._openai = None
        if (
            not settings.local_only
            and settings.embedding_provider == "openai"
            and settings.openai_api_key
        ):
            from openai import OpenAI

            self._openai = OpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            )

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if self._settings.local_only or self._settings.embedding_provider == "hash":
            return _hash_embed(texts)
        if self._openai is not None:
            resp = self._openai.embeddings.create(
                model=self._settings.openai_embedding_model,
                input=texts,
            )
            by_idx = {item.index: item.embedding for item in resp.data}
            return [by_idx[i] for i in range(len(texts))]
        try:
            model = _local_model(self._settings.embedding_model)
            vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            return [v.tolist() for v in vectors]
        except Exception:
            return _hash_embed(texts)

    def embed_query(self, text: str) -> List[float]:
        return self.embed_texts([text])[0]
