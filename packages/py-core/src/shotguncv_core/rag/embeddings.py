from __future__ import annotations

import hashlib
import math

from shotguncv_core.db.schema import EMBEDDING_DIMENSIONS


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
