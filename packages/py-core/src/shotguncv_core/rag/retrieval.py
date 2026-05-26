from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from shotguncv_core.rag.embeddings import EmbeddingModel, cosine_similarity, embed_many, embed_text


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
    def __init__(self, chunks: list[dict[str, Any]], *, embedding_model: EmbeddingModel | None = None) -> None:
        self._chunks = chunks
        self._embedding_model = embedding_model
        self._chunk_embeddings: list[list[float]] | None = None

    @classmethod
    def from_chunks(
        cls, chunks: list[dict[str, Any]], *, embedding_model: EmbeddingModel | None = None
    ) -> "InMemoryVectorRetriever":
        return cls(chunks, embedding_model=embedding_model)

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
        query_embedding = embed_text(query, self._embedding_model)
        chunk_embeddings = self._get_chunk_embeddings()
        results: list[RetrievalResult] = []
        for chunk, chunk_embedding in zip(self._chunks, chunk_embeddings):
            metadata = chunk["metadata"]
            if candidate_id and metadata.get("candidate_id") != candidate_id:
                continue
            if jd_id and metadata.get("jd_id") != jd_id:
                continue
            if run_id and metadata.get("run_id") != run_id:
                continue
            if source_type and metadata.get("source_type") != source_type:
                continue
            score = cosine_similarity(query_embedding, chunk_embedding)
            results.append(RetrievalResult(text=chunk["text"], metadata=metadata, score=round(score, 6)))
        return sorted(results, key=lambda item: item.score, reverse=True)[:limit]

    def _get_chunk_embeddings(self) -> list[list[float]]:
        if self._chunk_embeddings is None:
            self._chunk_embeddings = embed_many([str(chunk.get("text") or "") for chunk in self._chunks], self._embedding_model)
        return self._chunk_embeddings


class PgVectorRetriever:
    def __init__(self, database_url: str, *, embedding_model: EmbeddingModel | None = None) -> None:
        self.database_url = database_url
        self._embedding_model = embedding_model

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
        embedding = embed_text(query, self._embedding_model)
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
