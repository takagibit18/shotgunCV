from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any

from shotguncv_core.rag.retrieval import RetrievalResult


def evaluate_labeled_retrieval_queries(
    *,
    retriever: Any,
    query_specs: Sequence[dict[str, Any]],
    k_values: Sequence[int] = (1, 3, 5, 10),
    limit: int | None = None,
) -> dict[str, Any]:
    ks = _normalized_k_values(k_values)
    search_limit = limit or (max(ks) if ks else 10)
    query_reports: list[dict[str, Any]] = []
    for spec in query_specs:
        query = str(spec.get("expanded_query") or spec["query"])
        expected = [str(item) for item in spec.get("expected_chunks", []) if str(item).strip()]
        search_kwargs: dict[str, Any] = {"limit": search_limit}
        for filter_key in ("candidate_id", "jd_id", "source_type"):
            value = spec.get(filter_key)
            if value:
                search_kwargs[filter_key] = value
        results = retriever.search(query, **search_kwargs)
        ranked_ids = [_ranked_label_for_result(result, expected) for result in results]
        metrics = evaluate_ranked_retrieval(ranked_ids=ranked_ids, relevant_ids=set(expected), k_values=ks)
        query_reports.append(
            {
                "query_id": spec.get("query_id"),
                "jd_id": spec.get("jd_id"),
                "query": query,
                "expected_chunks": expected,
                "ranked_ids": ranked_ids,
                "ranked_relevance": [ranked_id in set(expected) for ranked_id in ranked_ids],
                "metrics": metrics,
                "hits": [_result_summary(result) for result in results],
            }
        )
    return {
        "query_count": len(query_reports),
        "k_values": ks,
        "aggregate": _aggregate_query_metrics(query_reports, ks),
        "queries": query_reports,
    }


def evaluate_ranked_retrieval(
    *,
    ranked_ids: Sequence[str],
    relevant_ids: Iterable[str],
    k_values: Sequence[int] = (1, 3, 5, 10),
) -> dict[str, Any]:
    relevant = {str(item) for item in relevant_ids}
    ranked = [str(item) for item in ranked_ids]
    ks = _normalized_k_values(k_values)
    return {
        "retrieved_count": len(ranked),
        "relevant_count": len(relevant),
        "precision_at_k": {str(k): _precision_at_k(ranked, relevant, k) for k in ks},
        "recall_at_k": {str(k): _recall_at_k(ranked, relevant, k) for k in ks},
        "mrr": _mean_reciprocal_rank(ranked, relevant),
        "ndcg_at_k": {str(k): _ndcg_at_k(ranked, relevant, k) for k in ks},
    }


def _normalized_k_values(k_values: Sequence[int]) -> list[int]:
    return sorted({int(k) for k in k_values if int(k) > 0})


def _precision_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    return _hit_count_at_k(ranked, relevant, k) / k


def _recall_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return _hit_count_at_k(ranked, relevant, k) / len(relevant)


def _mean_reciprocal_rank(ranked: Sequence[str], relevant: set[str]) -> float:
    for index, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1.0 / index
    return 0.0


def _ndcg_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    if not relevant or k <= 0:
        return 0.0
    seen: set[str] = set()
    dcg = 0.0
    for index, item in enumerate(ranked[:k], start=1):
        if item not in relevant or item in seen:
            continue
        seen.add(item)
        dcg += 1.0 / math.log2(index + 1)
    ideal_hits = min(len(relevant), k)
    ideal_dcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    return dcg / ideal_dcg if ideal_dcg else 0.0


def _hit_count_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> int:
    return len({item for item in ranked[:k] if item in relevant})


def _ranked_label_for_result(result: RetrievalResult, expected: Sequence[str]) -> str:
    haystack_values = [
        str(result.metadata.get("source_id") or ""),
        str(result.metadata.get("artifact_path") or ""),
        str(result.metadata.get("provenance_summary") or ""),
        result.text,
    ]
    haystack = "\n".join(haystack_values).lower()
    for label in expected:
        if label.lower() in haystack:
            return label
    metadata = result.metadata
    return ":".join(
        [
            str(metadata.get("source_type") or "unknown"),
            str(metadata.get("source_id") or "unknown"),
            str(metadata.get("chunk_index") or "0"),
        ]
    )


def _result_summary(result: RetrievalResult) -> dict[str, Any]:
    return {
        "source_type": result.metadata.get("source_type"),
        "source_id": result.metadata.get("source_id"),
        "artifact_path": result.metadata.get("artifact_path"),
        "score": result.score,
    }


def _aggregate_query_metrics(query_reports: Sequence[dict[str, Any]], k_values: Sequence[int]) -> dict[str, Any]:
    if not query_reports:
        return {
            "precision_at_k": {str(k): 0.0 for k in k_values},
            "recall_at_k": {str(k): 0.0 for k in k_values},
            "ndcg_at_k": {str(k): 0.0 for k in k_values},
            "mrr": 0.0,
        }
    count = len(query_reports)
    return {
        "precision_at_k": {
            str(k): sum(float(item["metrics"]["precision_at_k"][str(k)]) for item in query_reports) / count
            for k in k_values
        },
        "recall_at_k": {
            str(k): sum(float(item["metrics"]["recall_at_k"][str(k)]) for item in query_reports) / count
            for k in k_values
        },
        "ndcg_at_k": {
            str(k): sum(float(item["metrics"]["ndcg_at_k"][str(k)]) for item in query_reports) / count
            for k in k_values
        },
        "mrr": sum(float(item["metrics"]["mrr"]) for item in query_reports) / count,
    }
