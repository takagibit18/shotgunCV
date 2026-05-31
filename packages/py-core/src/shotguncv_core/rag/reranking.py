from __future__ import annotations

from typing import Any

from shotguncv_core.rag.retrieval import RetrievalResult


class CrossEncoderReranker:
    """Two-stage retrieval: cross-encoder re-ranks coarse retrieval candidates.

    Uses ``sentence_transformers.CrossEncoder`` under the hood.
    The model is loaded lazily — no GPU memory is consumed until the first
    ``rerank()`` call.
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3") -> None:
        self._model_name = model_name
        self._model: Any = None

    def rerank(
        self,
        query: str,
        candidates: list[RetrievalResult],
        *,
        top_k: int = 10,
    ) -> list[RetrievalResult]:
        """Re-rank *candidates* with a cross-encoder and return *top_k* results.

        Args:
            query: Original natural-language query.
            candidates: Coarse retrieval results (e.g. BM25 top-50).
            top_k: Number of results to keep after re-ranking.

        Returns:
            Re-ranked results with cross-encoder scores (0-1 range).
            Original metadata is preserved; only the score is replaced.
        """
        if not candidates:
            return []
        if self._model is None:
            self._load_model()

        pairs = [(query, candidate.text) for candidate in candidates]
        scores = self._model.predict(pairs, show_progress_bar=False)

        reranked = sorted(
            [(float(score), candidate) for score, candidate in zip(scores, candidates)],
            key=lambda item: item[0],
            reverse=True,
        )
        return [
            RetrievalResult(
                text=candidate.text,
                metadata=candidate.metadata,
                score=round(score, 6),
            )
            for score, candidate in reranked[:top_k]
        ]

    def _load_model(self) -> None:
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(self._model_name, trust_remote_code=True)
