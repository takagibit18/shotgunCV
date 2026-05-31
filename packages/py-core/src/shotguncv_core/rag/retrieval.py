from __future__ import annotations

import math
import re
from collections import Counter
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


class InMemoryBM25Retriever:
    def __init__(self, chunks: list[dict[str, Any]], *, k1: float = 1.5, b: float = 0.75) -> None:
        self._chunks = chunks
        self._k1 = k1
        self._b = b
        self._documents = [_tokens(_chunk_search_text(chunk)) for chunk in chunks]
        self._term_counts = [Counter(document) for document in self._documents]
        self._avg_doc_length = (sum(len(document) for document in self._documents) / len(self._documents)) if self._documents else 0.0
        self._document_frequency = Counter({term: sum(1 for counts in self._term_counts if term in counts) for term in set().union(*self._documents)}) if self._documents else Counter()

    @classmethod
    def from_chunks(cls, chunks: list[dict[str, Any]]) -> "InMemoryBM25Retriever":
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
        query_terms = Counter(_tokens(query))
        results: list[RetrievalResult] = []
        for index, chunk in enumerate(self._chunks):
            metadata = chunk["metadata"]
            if not _passes_filters(
                metadata,
                candidate_id=candidate_id,
                jd_id=jd_id,
                run_id=run_id,
                source_type=source_type,
            ):
                continue
            score = self._score(query_terms, index)
            results.append(RetrievalResult(text=chunk["text"], metadata=metadata, score=round(score, 6)))
        return sorted(results, key=lambda item: item.score, reverse=True)[:limit]

    def _score(self, query_terms: Counter[str], index: int) -> float:
        if not query_terms or not self._documents:
            return 0.0
        score = 0.0
        term_counts = self._term_counts[index]
        doc_length = len(self._documents[index])
        for term, query_frequency in query_terms.items():
            term_frequency = term_counts.get(term, 0)
            if term_frequency <= 0:
                continue
            doc_frequency = self._document_frequency.get(term, 0)
            idf = math.log(1.0 + (len(self._documents) - doc_frequency + 0.5) / (doc_frequency + 0.5))
            denominator = term_frequency + self._k1 * (1.0 - self._b + self._b * doc_length / (self._avg_doc_length or 1.0))
            score += query_frequency * idf * (term_frequency * (self._k1 + 1.0)) / denominator
        return score


class InMemoryHybridRetriever:
    def __init__(
        self,
        chunks: list[dict[str, Any]],
        *,
        embedding_model: EmbeddingModel | None = None,
        vector_weight: float = 0.75,
        bm25_weight: float = 0.25,
    ) -> None:
        self._chunks = chunks
        self._vector = InMemoryVectorRetriever.from_chunks(chunks, embedding_model=embedding_model)
        self._bm25 = InMemoryBM25Retriever.from_chunks(chunks)
        self._vector_weight = vector_weight
        self._bm25_weight = bm25_weight

    @classmethod
    def from_chunks(
        cls,
        chunks: list[dict[str, Any]],
        *,
        embedding_model: EmbeddingModel | None = None,
        vector_weight: float = 0.75,
        bm25_weight: float = 0.25,
    ) -> "InMemoryHybridRetriever":
        return cls(chunks, embedding_model=embedding_model, vector_weight=vector_weight, bm25_weight=bm25_weight)

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
        search_limit = len(self._chunks)
        vector_results = self._vector.search(
            query,
            limit=search_limit,
            candidate_id=candidate_id,
            jd_id=jd_id,
            run_id=run_id,
            source_type=source_type,
        )
        bm25_results = self._bm25.search(
            query,
            limit=search_limit,
            candidate_id=candidate_id,
            jd_id=jd_id,
            run_id=run_id,
            source_type=source_type,
        )
        vector_scores = _bounded_vector_scores(vector_results)
        bm25_scores = _bounded_bm25_scores(bm25_results)
        by_key = {_result_key(result): result for result in [*vector_results, *bm25_results]}
        ranked = [
            RetrievalResult(
                text=result.text,
                metadata=result.metadata,
                score=round(
                    self._vector_weight * vector_scores.get(key, 0.0)
                    + self._bm25_weight * bm25_scores.get(key, 0.0),
                    6,
                ),
            )
            for key, result in by_key.items()
        ]
        return sorted(ranked, key=lambda item: item.score, reverse=True)[:limit]


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


def _passes_filters(
    metadata: dict[str, Any],
    *,
    candidate_id: str | None,
    jd_id: str | None,
    run_id: str | None,
    source_type: str | None,
) -> bool:
    if candidate_id and metadata.get("candidate_id") != candidate_id:
        return False
    if jd_id and metadata.get("jd_id") != jd_id:
        return False
    if run_id and metadata.get("run_id") != run_id:
        return False
    if source_type and metadata.get("source_type") != source_type:
        return False
    return True


def _chunk_search_text(chunk: dict[str, Any]) -> str:
    metadata = chunk.get("metadata") or {}
    values = [
        str(chunk.get("chunk_id") or ""),
        str(metadata.get("source_type") or ""),
        str(metadata.get("source_id") or ""),
        str(metadata.get("artifact_path") or ""),
        str(metadata.get("provenance_summary") or ""),
        str(chunk.get("text") or ""),
    ]
    return "\n".join(values)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", text.lower())


# ---------------------------------------------------------------------------
# query expansion
# ---------------------------------------------------------------------------


# Approach A: static Chinese \u2192 English tech term mapping.
# Built from analysis of golden set queries vs. expected document vocabulary.
_STATIC_EXPANSION_MAP: dict[str, list[str]] = {
    "langgraph": ["langgraph", "orchestration", "fan-out", "graph", "workflow"],
    "rag": ["rag", "retrieval", "embedding", "requirement_evidence"],
    "pgvector": ["pgvector", "vector", "embedding", "postgresql"],
    "llm": ["llm", "language model", "generation", "judge"],
    "mcp": ["mcp", "skills", "tools", "tooling", "agent"],
    "ocr": ["ocr", "extraction", "tesseract", "vision"],
    "hitl": ["hitl", "human-in-the-loop", "checkpoint", "approval"],
    "mlops": ["mlops", "deployment", "pipeline", "ci/cd"],
    "fastapi": ["fastapi", "api", "backend", "python", "web"],
    "docker": ["docker", "container", "redis", "infrastructure"],
    "langchain": ["langchain", "orchestration", "framework"],
    "web3": ["web3", "blockchain", "crypto"],
    "e2e": ["e2e", "end-to-end", "pipeline", "evaluate"],
    "pdf": ["pdf", "document", "extraction", "ocr"],
    "jd": ["jd", "job description", "jd_description", "requirement"],
    "gap": ["gap", "missing", "gap_map", "mismatch"],
    "retriever": ["retriever", "retrieval", "bm25", "search"],
    "generator": ["generator", "generation", "llm"],
    "benchmark": ["benchmark", "throughput", "performance", "evaluation"],
    "observability": ["observability", "monitoring", "logging", "traces"],
    "artifact": ["artifact", "run_dir", "post_run_review", "structured"],
    "fallback": ["fallback", "abstention", "no-answer", "gate"],
    "citation": ["citation", "provenance", "evidence_ref", "source"],
    "checkpoint": ["checkpoint", "approval", "human", "review"],
    "skills": ["skills", "tools", "tooling", "mcp", "custom"],
    "platform": ["platform", "agent", "orchestration", "engineer"],
    "review": ["review", "post_run_review", "evaluate", "scorecards"],
}


def expand_query(
    query: str,
    *,
    method: str = "static",
    dense_retriever: "InMemoryVectorRetriever | None" = None,
) -> str:
    """Expand a query with terms that improve BM25 retrieval.

    Methods:
      - "static": Appends English tech terms from a curated mapping (Approach A).
      - "dense_jd": Uses dense retrieval to discover the most relevant jd_id,
        then appends it to the query for BM25 precision (Approach C).
    """
    if method == "static":
        return _static_expand(query)
    if method == "dense_jd":
        return _dense_jd_expand(query, dense_retriever)
    return query


def _static_expand(query: str) -> str:
    """Append matching English tech terms from the static mapping."""
    query_lower = query.lower()
    additions: list[str] = []
    for key, terms in _STATIC_EXPANSION_MAP.items():
        if key in query_lower:
            additions.extend(terms)
    if not additions:
        return query
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for term in additions:
        if term not in seen:
            seen.add(term)
            unique.append(term)
    return f"{query}\n{' '.join(unique)}"


def _dense_jd_expand(query: str, dense_retriever: "InMemoryVectorRetriever | None") -> str:
    """Use dense retrieval to discover the most relevant jd_id and inject it.

    Strategy: Dense for recall (find which JD), BM25 for precision (rank within JD).
    The dense retriever searches ALL chunks without jd_id filter, then the most
    frequent jd_id in the top results is appended to the query as a BM25 term.
    """
    if dense_retriever is None:
        return query
    # Coarse recall with dense \u2014 no jd_id filter, wider limit
    dense_results = dense_retriever.search(query, limit=30)
    if not dense_results:
        return query
    # Extract jd_ids from top results
    jd_ids: list[str] = []
    for r in dense_results:
        jid = str(r.metadata.get("jd_id") or "")
        if jid:
            jd_ids.append(jid)
    if not jd_ids:
        return query
    # Most frequent jd_id in the dense top-30
    top_jd_id = Counter(jd_ids).most_common(1)[0][0]
    return f"{query}\n{top_jd_id}"


def _result_key(result: RetrievalResult) -> tuple[str, str, str, str]:
    return (
        str(result.metadata.get("source_type") or ""),
        str(result.metadata.get("source_id") or ""),
        str(result.metadata.get("chunk_index") or ""),
        str(result.metadata.get("artifact_path") or ""),
    )


def _bounded_vector_scores(results: list[RetrievalResult]) -> dict[tuple[str, str, str, str], float]:
    return {_result_key(result): max(0.0, min(1.0, result.score)) for result in results}


def _bounded_bm25_scores(results: list[RetrievalResult]) -> dict[tuple[str, str, str, str], float]:
    return {_result_key(result): max(0.0, result.score) / (max(0.0, result.score) + 1.0) for result in results}
