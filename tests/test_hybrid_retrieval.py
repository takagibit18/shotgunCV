from __future__ import annotations

from shotguncv_core.rag.retrieval import InMemoryHybridRetriever


class _MisleadingEmbeddingModel:
    def embed(self, text: str) -> list[float]:
        normalized = text.lower()
        if "generic" in normalized or "management" in normalized:
            return [1.0, 0.0]
        if "jd-001-req-007" in normalized:
            return [0.0, 1.0]
        return [0.0, 0.0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


def test_hybrid_retriever_promotes_exact_bm25_match_over_dense_misrank() -> None:
    retriever = InMemoryHybridRetriever.from_chunks(
        [
            {
                "text": "Generic management experience without the required source label.",
                "metadata": {"source_type": "candidate_evidence", "source_id": "generic-candidate"},
            },
            {
                "text": "Requirement evidence for targeted backend retrieval.",
                "metadata": {"source_type": "requirement_evidence", "source_id": "jd-001-req-007"},
            },
        ],
        embedding_model=_MisleadingEmbeddingModel(),
        vector_weight=0.35,
        bm25_weight=0.65,
    )

    results = retriever.search("jd-001-req-007 backend retrieval", limit=2)

    assert results[0].metadata["source_id"] == "jd-001-req-007"
    assert results[0].metadata["source_type"] == "requirement_evidence"
    assert results[0].score > results[1].score


def test_hybrid_retriever_keeps_existing_metadata_filters() -> None:
    retriever = InMemoryHybridRetriever.from_chunks(
        [
            {
                "text": "Requirement evidence for jd-001-req-007.",
                "metadata": {"source_type": "requirement_evidence", "source_id": "jd-001-req-007", "jd_id": "jd-001"},
            },
            {
                "text": "Requirement evidence for jd-002-req-007.",
                "metadata": {"source_type": "requirement_evidence", "source_id": "jd-002-req-007", "jd_id": "jd-002"},
            },
        ],
        embedding_model=_MisleadingEmbeddingModel(),
    )

    results = retriever.search("req-007", limit=5, jd_id="jd-002")

    assert [result.metadata["source_id"] for result in results] == ["jd-002-req-007"]
