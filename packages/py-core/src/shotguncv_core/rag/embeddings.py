from __future__ import annotations

import hashlib
import math
from functools import cached_property, lru_cache
from typing import Protocol

from shotguncv_core.db.schema import EMBEDDING_DIMENSIONS

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"


class EmbeddingModel(Protocol):
    def embed(self, text: str) -> list[float]:
        ...


def embed_many(texts: list[str], embedding_model: EmbeddingModel | None = None) -> list[list[float]]:
    model = embedding_model or get_default_embedding_model()
    embed_many_fn = getattr(model, "embed_many", None)
    if callable(embed_many_fn):
        return embed_many_fn(texts)
    return [model.embed(text) for text in texts]


class SentenceTransformerEmbeddingModel:
    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL) -> None:
        self.model_name = model_name

    @cached_property
    def _model(self) -> object:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install ShotgunCV with the `rag` extra to use BAAI/bge-m3 embeddings.") from exc
        return SentenceTransformer(self.model_name)

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode([text or " " for text in texts], normalize_embeddings=True)
        rows = vectors.tolist() if hasattr(vectors, "tolist") else list(vectors)
        embedded: list[list[float]] = []
        for row in rows:
            values = list(row)
            if len(values) != EMBEDDING_DIMENSIONS:
                raise RuntimeError(
                    f"Embedding model {self.model_name} returned {len(values)} dimensions; "
                    f"expected {EMBEDDING_DIMENSIONS}."
                )
            embedded.append([float(value) for value in values])
        return embedded


@lru_cache(maxsize=1)
def get_default_embedding_model() -> EmbeddingModel:
    return SentenceTransformerEmbeddingModel()


def embed_text(text: str, embedding_model: EmbeddingModel | None = None) -> list[float]:
    return (embedding_model or get_default_embedding_model()).embed(text)


def deterministic_embedding(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    vector = [0.0] * dimensions
    tokens = [token for token in text.lower().replace("\n", " ").split(" ") if token]
    for token in tokens or [text]:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % dimensions
        vector[index] += 1.0
    magnitude = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / magnitude, 6) for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))
