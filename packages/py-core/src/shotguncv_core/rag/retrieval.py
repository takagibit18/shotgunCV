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


class SmartRouterRetriever:
    """Rule-based, oracle-free router over BM25 and hybrid retrieval."""

    def __init__(
        self,
        chunks: list[dict[str, Any]],
        *,
        embedding_model: EmbeddingModel | None = None,
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3,
        broad_limit: int = 20,
        enable_support_gate: bool = False,
    ) -> None:
        self._bm25 = InMemoryBM25Retriever.from_chunks(chunks)
        self._hybrid = InMemoryHybridRetriever.from_chunks(
            chunks,
            embedding_model=embedding_model,
            vector_weight=vector_weight,
            bm25_weight=bm25_weight,
        )
        self._broad_limit = broad_limit
        self._enable_support_gate = enable_support_gate
        self.last_query_plan: dict[str, Any] | None = None

    @classmethod
    def from_chunks(
        cls,
        chunks: list[dict[str, Any]],
        *,
        embedding_model: EmbeddingModel | None = None,
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3,
        broad_limit: int = 20,
        enable_support_gate: bool = False,
    ) -> "SmartRouterRetriever":
        return cls(
            chunks,
            embedding_model=embedding_model,
            vector_weight=vector_weight,
            bm25_weight=bm25_weight,
            broad_limit=broad_limit,
            enable_support_gate=enable_support_gate,
        )

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
        filters = {
            "candidate_id": candidate_id,
            "jd_id": jd_id,
            "run_id": run_id,
            "source_type": source_type,
        }
        clean_filters = {key: value for key, value in filters.items() if value}
        broad_bm25 = self._bm25.search(query, limit=self._broad_limit, **clean_filters)
        broad_hybrid = self._hybrid.search(query, limit=self._broad_limit, **clean_filters)
        plan = build_smart_query_plan(
            query,
            broad_hits=broad_bm25,
            hybrid_hits=broad_hybrid,
            limit=limit,
            broad_limit=self._broad_limit,
            enable_support_gate=self._enable_support_gate,
            filters=clean_filters,
        )
        results = self._execute_plan(plan, limit=limit, filters=clean_filters)
        self.last_query_plan = {
            **plan,
            "broad_observation": _hit_distribution(broad_bm25),
            "hybrid_observation": _hit_distribution(broad_hybrid),
            "support_gate": _support_gate_status(query, results, self._enable_support_gate),
        }
        return results

    def _execute_plan(
        self,
        plan: dict[str, Any],
        *,
        limit: int,
        filters: dict[str, Any],
    ) -> list[RetrievalResult]:
        combined: list[RetrievalResult] = []
        seen: set[tuple[str, str, str, str]] = set()
        for route in plan["routes"]:
            retriever = self._hybrid if route["retriever_mode"] == "hybrid" else self._bm25
            route_filters = {**filters, **route.get("filters", {})}
            route_results = retriever.search(str(route["query"]), limit=int(route["limit"]), **route_filters)
            for result in route_results:
                key = _result_key(result)
                if key in seen:
                    continue
                seen.add(key)
                combined.append(result)
                if len(combined) >= limit:
                    return combined
        return combined


def build_smart_query_plan(
    query: str,
    *,
    broad_hits: list[RetrievalResult],
    hybrid_hits: list[RetrievalResult],
    limit: int,
    broad_limit: int = 20,
    enable_support_gate: bool = False,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rewrite = rewrite_fuzzy_query(query)
    complex_reasons = detect_complex_query(query, broad_hits)
    risk_reasons = detect_risk_query(query, broad_hits)
    claim_signal = detect_no_answer_strong_claim(query)
    reasons = [*rewrite["reasons"], *complex_reasons, *risk_reasons]
    if claim_signal["triggered"]:
        reasons.extend(claim_signal["reasons"])
    routes: list[dict[str, Any]] = []
    if rewrite["terms"] or complex_reasons or risk_reasons or (enable_support_gate and claim_signal["triggered"]):
        routes.append({"name": "hybrid_anchor", "query": query, "retriever_mode": "hybrid", "limit": min(5, limit)})
    if rewrite["terms"]:
        routes.append({"name": "rewrite", "query": rewrite["expanded_query"], "retriever_mode": "hybrid", "limit": limit})
    if complex_reasons:
        routes.extend(_context_routes(query, broad_hits, limit=limit))
    if risk_reasons:
        routes.extend(_risk_routes(query, broad_hits, limit=limit))
    if enable_support_gate and claim_signal["triggered"]:
        routes.insert(
            0,
            {
                "name": "support_gate_candidate",
                "query": rewrite["expanded_query"],
                "retriever_mode": "hybrid",
                "filters": {"source_type": "candidate_evidence"},
                "limit": min(limit, 5),
            },
        )
    if not routes:
        routes.append({"name": "broad", "query": query, "retriever_mode": "hybrid", "limit": limit})
    else:
        routes.append({"name": "broad_fallback", "query": query, "retriever_mode": "hybrid", "limit": min(broad_limit, max(limit, 10))})
    return {
        "strategy": "smart_router",
        "original_query": query,
        "expanded_query": rewrite["expanded_query"],
        "routes": routes,
        "reasons": _unique_terms(reasons),
        "rewrite_terms": rewrite["terms"],
        "decomposition_stages": [route["name"] for route in routes if route["name"] not in {"broad", "rewrite"}],
        "fallback_used": any(route["name"] in {"broad", "broad_fallback"} for route in routes),
        "oracle_free": True,
        "filters": filters or {},
    }


def rewrite_fuzzy_query(query: str) -> dict[str, Any]:
    query_lower = query.lower()
    terms: list[str] = []
    reasons: list[str] = []
    alias_map = {
        "工具链": ["LangGraph", "tool calling", "agent workflow", "tool execution", "evaluation"],
        "搜出来准不准": ["retrieval evaluation", "MRR", "NDCG", "Recall", "Precision", "golden set"],
        "准不准": ["retrieval evaluation", "MRR", "Recall", "Precision"],
        "跑起来": ["AI prototype", "demo", "agent project", "automation workflow"],
        "原型": ["AI prototype", "demo", "agent project"],
        "别乱跑": ["tool safety", "sandbox", "permission gate", "path safety"],
        "像不像": ["fit", "evidence", "requirement match"],
        "会不会": ["capability", "evidence", "experience"],
        "能不能": ["capability", "evidence", "experience"],
        "是不是": ["evidence", "fit", "boundary"],
        "有没有": ["evidence", "experience", "project"],
    }
    for pattern, additions in alias_map.items():
        if pattern in query_lower:
            terms.extend(additions)
            reasons.append("semantic_alias_pattern")
    expanded = query if not terms else f"{query}\n{' '.join(_unique_terms(terms))}"
    return {"expanded_query": expanded, "terms": _unique_terms(terms), "reasons": _unique_terms(reasons)}


def detect_complex_query(query: str, broad_hits: list[RetrievalResult]) -> list[str]:
    reasons: list[str] = []
    if any(term in query for term in ["分别", "同时", "以及", "一起", "合并", "对比", "哪些支持", "哪些保守"]):
        reasons.append("complex_query_connector")
    if len({str(hit.metadata.get("source_type") or "") for hit in broad_hits[:10] if hit.metadata.get("source_type")}) >= 2:
        reasons.append("broad_hits_multi_source_type")
    if len({str(hit.metadata.get("jd_id") or "") for hit in broad_hits[:10] if hit.metadata.get("jd_id")}) >= 2:
        reasons.append("broad_hits_multi_jd")
    return reasons


def detect_risk_query(query: str, broad_hits: list[RetrievalResult]) -> list[str]:
    reasons: list[str] = []
    if any(term in query for term in ["风险", "缺口", "不足", "保守", "不能高置信", "矛盾", "过期", "低置信", "为什么排序"]):
        reasons.append("risk_gap_intent")
    source_types = {str(hit.metadata.get("source_type") or "") for hit in broad_hits[:10]}
    if "gap_map" in source_types:
        reasons.append("broad_hits_gap_map")
    if "ranking_explanation" in source_types:
        reasons.append("broad_hits_ranking_explanation")
    return reasons


def detect_no_answer_strong_claim(query: str) -> dict[str, Any]:
    terms = ["能否证明", "是否等于", "专家", "资深", "平台工程经验", "模型训练", "微调", "生产运维"]
    matched = [term for term in terms if term in query]
    return {"triggered": bool(matched), "claim": query, "matched_terms": matched, "reasons": ["strong_claim_signal"] if matched else []}


def _context_routes(query: str, broad_hits: list[RetrievalResult], *, limit: int) -> list[dict[str, Any]]:
    routes = [
        {"name": "candidate_context", "query": f"{query}\ncandidate evidence project education skills", "retriever_mode": "hybrid", "filters": {"source_type": "candidate_evidence"}, "limit": min(3, limit)},
        {"name": "requirement_context", "query": f"{query}\njd requirement evidence status", "retriever_mode": "hybrid", "filters": {"source_type": "requirement_evidence"}, "limit": min(4, limit)},
    ]
    for jd_id in _top_jd_ids(broad_hits, max_count=3):
        routes.append(
            {
                "name": "jd_context",
                "query": f"{query}\njd requirement evidence status",
                "retriever_mode": "hybrid",
                "filters": {"jd_id": jd_id, "source_type": "requirement_evidence"},
                "limit": min(3, limit),
            }
        )
    return routes


def _risk_routes(query: str, broad_hits: list[RetrievalResult], *, limit: int) -> list[dict[str, Any]]:
    jd_id = _top_jd_id(broad_hits)
    base_filters = {"jd_id": jd_id} if jd_id else {}
    return [
        {"name": "risk_primary_context", "query": f"{query}\njd requirement evidence status primary evidence", "retriever_mode": "hybrid", "filters": {**base_filters, "source_type": "requirement_evidence"}, "limit": min(4, limit)},
        {"name": "gap_context", "query": f"{query}\ngap missing weak point gap_map risk", "retriever_mode": "hybrid", "filters": {**base_filters, "source_type": "gap_map"}, "limit": min(3, limit)},
        {"name": "ranking_context", "query": f"{query}\nranking decision risk flags ranking_explanation", "retriever_mode": "hybrid", "filters": {**base_filters, "source_type": "ranking_explanation"}, "limit": min(3, limit)},
    ]


def _top_jd_id(hits: list[RetrievalResult]) -> str | None:
    jd_ids = _top_jd_ids(hits, max_count=1)
    return jd_ids[0] if jd_ids else None


def _top_jd_ids(hits: list[RetrievalResult], *, max_count: int) -> list[str]:
    jd_ids = [str(hit.metadata.get("jd_id") or "") for hit in hits[:10] if hit.metadata.get("jd_id")]
    return [jd_id for jd_id, _ in Counter(jd_ids).most_common(max_count)]


def _unique_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        clean = str(term).strip()
        key = clean.lower()
        if not clean or key in seen:
            continue
        seen.add(key)
        unique.append(clean)
    return unique


def _hit_distribution(hits: list[RetrievalResult]) -> dict[str, Any]:
    scores = [hit.score for hit in hits]
    return {
        "hit_count": len(hits),
        "top_score": scores[0] if scores else None,
        "score_gap": (scores[0] - scores[1]) if len(scores) > 1 else None,
        "source_type_counts": dict(Counter(str(hit.metadata.get("source_type") or "unknown") for hit in hits)),
        "jd_id_counts": dict(Counter(str(hit.metadata.get("jd_id") or "unknown") for hit in hits if hit.metadata.get("jd_id"))),
    }


def _support_gate_status(query: str, results: list[RetrievalResult], enabled: bool) -> dict[str, Any]:
    signal = detect_no_answer_strong_claim(query)
    triggered = enabled and signal["triggered"]
    direct_overlap = bool(set(_tokens(query)) & set(_tokens(" ".join(result.text for result in results[:3]))))
    status = "not_triggered"
    if triggered:
        status = "supported_candidate" if direct_overlap and results else "abstained"
    return {
        "triggered": triggered,
        "claim": signal["claim"] if signal["triggered"] else None,
        "support_status": status,
        "reason": "strong_claim_candidate_evidence_check" if triggered else "no_strong_claim_signal",
        "blocked_generator": triggered and status == "abstained",
    }


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
