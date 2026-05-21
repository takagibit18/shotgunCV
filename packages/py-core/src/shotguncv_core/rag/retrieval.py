from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from shotguncv_core.rag.embeddings import cosine_similarity, deterministic_embedding


@dataclass(frozen=True)
class RetrievalResult:
    text: str
    metadata: dict[str, Any]
    score: float


class Retriever(Protocol):
    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        candidate_id: str | None = None,
        jd_id: str | None = None,
        run_id: str | None = None,
        source_type: str | None = None,
    ) -> list[RetrievalResult]:
        ...


class InMemoryVectorRetriever:
    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        self._chunks = chunks

    @classmethod
    def from_chunks(cls, chunks: list[dict[str, Any]]) -> "InMemoryVectorRetriever":
        return cls(chunks)

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        candidate_id: str | None = None,
        jd_id: str | None = None,
        run_id: str | None = None,
        source_type: str | None = None,
    ) -> list[RetrievalResult]:
        query_embedding = deterministic_embedding(query)
        results: list[RetrievalResult] = []
        for chunk in self._chunks:
            metadata = chunk["metadata"]
            if candidate_id and metadata.get("candidate_id") != candidate_id:
                continue
            if jd_id and metadata.get("jd_id") != jd_id:
                continue
            if run_id and metadata.get("run_id") != run_id:
                continue
            if source_type and metadata.get("source_type") != source_type:
                continue
            score = cosine_similarity(query_embedding, deterministic_embedding(chunk["text"]))
            results.append(RetrievalResult(text=chunk["text"], metadata=metadata, score=round(score, 6)))
        return sorted(results, key=lambda item: item.score, reverse=True)[:limit]


class PgVectorRetriever:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        candidate_id: str | None = None,
        jd_id: str | None = None,
        run_id: str | None = None,
        source_type: str | None = None,
    ) -> list[RetrievalResult]:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install ShotgunCV with the `rag` extra to use PostgreSQL retrieval.") from exc
        embedding = deterministic_embedding(query)
        filters = []
        params: list[Any] = [embedding]
        if candidate_id:
            filters.append("candidate_id = %s")
            params.append(candidate_id)
        if jd_id:
            filters.append("jd_id = %s")
            params.append(jd_id)
        if run_id:
            filters.append("run_id = %s")
            params.append(run_id)
        if source_type:
            filters.append("source_type = %s")
            params.append(source_type)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        sql = f"""
            SELECT text, metadata, 1 - (embedding <=> %s::vector) AS score
            FROM retrieval_chunks
            {where}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        params.insert(len(params) - 1, embedding)
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return [RetrievalResult(text=row[0], metadata=row[1], score=float(row[2])) for row in cur.fetchall()]
