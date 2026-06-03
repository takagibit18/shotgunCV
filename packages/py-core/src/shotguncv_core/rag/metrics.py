from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any

from shotguncv_core.rag.retrieval import RetrievalResult


_ROLE_WEIGHTS = {
    "primary": 1.0,
    "conflicting": 1.0,
    "stale": 0.75,
    "supporting": 0.5,
}


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
        filters = {key: value for key, value in search_kwargs.items() if key != "limit"}
        decomposition = None
        if isinstance(spec.get("query_decomposition"), dict):
            results, decomposition = _search_decomposed(
                retriever=retriever,
                decomposition=spec["query_decomposition"],
                fallback_query=query,
                search_limit=search_limit,
                base_filters=filters,
            )
        else:
            results = retriever.search(query, **search_kwargs)
        query_plan = _consume_query_plan(retriever)
        ranked_ids = [_ranked_label_for_result(result, expected) for result in results]
        metrics = evaluate_ranked_retrieval(ranked_ids=ranked_ids, relevant_ids=set(expected), k_values=ks)
        role_weights = _role_weights(spec.get("expected_documents", []), expected)
        weighted_metrics = _weighted_retrieval_metrics(ranked_ids=ranked_ids, role_weights=role_weights, k_values=ks)
        evidence_coverage = _evidence_coverage(
            ranked_ids=ranked_ids,
            expected=expected,
            expected_documents=spec.get("expected_documents", []),
        )
        query_reports.append(
            {
                "query_id": spec.get("query_id"),
                "jd_id": spec.get("jd_id"),
                "filter_scope": spec.get("filter_scope"),
                "filters": filters,
                "query": query,
                "expected_chunks": expected,
                "ranked_ids": ranked_ids,
                "ranked_relevance": [ranked_id in set(expected) for ranked_id in ranked_ids],
                "metrics": metrics,
                "weighted_metrics": weighted_metrics,
                "evidence_coverage": evidence_coverage,
                "hits": [_result_summary(result) for result in results],
                **({"query_plan": query_plan} if query_plan is not None else {}),
                **({"decomposition": decomposition} if decomposition is not None else {}),
            }
        )
    return {
        "query_count": len(query_reports),
        "k_values": ks,
        "aggregate": _aggregate_query_metrics(query_reports, ks),
        "queries": query_reports,
    }


def _search_decomposed(
    *,
    retriever: Any,
    decomposition: dict[str, Any],
    fallback_query: str,
    search_limit: int,
    base_filters: dict[str, Any],
) -> tuple[list[RetrievalResult], dict[str, Any]]:
    stages = decomposition.get("stages")
    if not isinstance(stages, Sequence) or isinstance(stages, (str, bytes)) or not stages:
        results = retriever.search(fallback_query, limit=search_limit, **base_filters)
        return results, {"strategy": str(decomposition.get("strategy") or "fallback"), "stages": []}

    combined: list[RetrievalResult] = []
    seen: set[tuple[str, str, str, str]] = set()
    stage_reports: list[dict[str, Any]] = []
    for raw_stage in stages:
        if not isinstance(raw_stage, dict):
            continue
        query = str(raw_stage.get("query") or fallback_query)
        stage_filters = {
            str(key): value
            for key, value in (raw_stage.get("filters") or {}).items()
            if key in {"candidate_id", "jd_id", "source_type"} and value
        }
        filters = {**base_filters, **stage_filters}
        stage_limit = int(raw_stage.get("limit") or search_limit)
        stage_limit = max(1, min(stage_limit, search_limit))
        stage_results = retriever.search(query, limit=stage_limit, **filters)
        added = 0
        for result in stage_results:
            key = _result_key(result)
            if key in seen:
                continue
            seen.add(key)
            combined.append(result)
            added += 1
            if len(combined) >= search_limit:
                break
        stage_reports.append(
            {
                "name": str(raw_stage.get("name") or "stage"),
                "query": query,
                "filters": filters,
                "limit": stage_limit,
                "retrieved_count": len(stage_results),
                "added_count": added,
                "result_ids": [_result_summary(result)["source_id"] for result in stage_results],
            }
        )
        if len(combined) >= search_limit:
            break
    if len(combined) < search_limit:
        fallback_results = retriever.search(fallback_query, limit=search_limit, **base_filters)
        added = 0
        for result in fallback_results:
            key = _result_key(result)
            if key in seen:
                continue
            seen.add(key)
            combined.append(result)
            added += 1
            if len(combined) >= search_limit:
                break
        stage_reports.append(
            {
                "name": "fallback",
                "query": fallback_query,
                "filters": base_filters,
                "limit": search_limit,
                "retrieved_count": len(fallback_results),
                "added_count": added,
                "result_ids": [_result_summary(result)["source_id"] for result in fallback_results],
            }
        )
    return combined, {
        "strategy": str(decomposition.get("strategy") or "primary_then_related"),
        "stages": stage_reports,
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
    source_id = str(metadata.get("source_id") or "").strip()
    if source_id:
        return source_id
    return ":".join(
        [
            str(metadata.get("source_type") or "unknown"),
            str(metadata.get("source_id") or "unknown"),
            str(metadata.get("chunk_index") or "0"),
        ]
    )


def _role_weights(expected_documents: Any, expected: Sequence[str]) -> dict[str, float]:
    weights = {str(label): 1.0 for label in expected}
    if not isinstance(expected_documents, Sequence) or isinstance(expected_documents, (str, bytes)):
        return weights
    for document in expected_documents:
        if not isinstance(document, dict):
            continue
        label = _document_label(document)
        if not label or label not in weights:
            continue
        role = str(document.get("role") or "primary").strip().lower()
        weights[label] = _ROLE_WEIGHTS.get(role, 1.0)
    return weights


def _weighted_retrieval_metrics(
    *,
    ranked_ids: Sequence[str],
    role_weights: dict[str, float],
    k_values: Sequence[int],
) -> dict[str, Any]:
    total_weight = sum(role_weights.values())
    return {
        "role_weights": role_weights,
        "weighted_recall_at_k": {
            str(k): _weighted_recall_at_k(ranked_ids, role_weights, total_weight, k) for k in k_values
        },
        "weighted_ndcg_at_k": {str(k): _weighted_ndcg_at_k(ranked_ids, role_weights, k) for k in k_values},
    }


def _weighted_recall_at_k(
    ranked_ids: Sequence[str],
    role_weights: dict[str, float],
    total_weight: float,
    k: int,
) -> float:
    if total_weight <= 0.0 or k <= 0:
        return 0.0
    seen = {item for item in ranked_ids[:k] if item in role_weights}
    return sum(role_weights[item] for item in seen) / total_weight


def _weighted_ndcg_at_k(ranked_ids: Sequence[str], role_weights: dict[str, float], k: int) -> float:
    if not role_weights or k <= 0:
        return 0.0
    seen: set[str] = set()
    dcg = 0.0
    for index, item in enumerate(ranked_ids[:k], start=1):
        if item not in role_weights or item in seen:
            continue
        seen.add(item)
        dcg += role_weights[item] / math.log2(index + 1)
    ideal_weights = sorted(role_weights.values(), reverse=True)[:k]
    ideal_dcg = sum(weight / math.log2(index + 1) for index, weight in enumerate(ideal_weights, start=1))
    return dcg / ideal_dcg if ideal_dcg else 0.0


def _evidence_coverage(
    *,
    ranked_ids: Sequence[str],
    expected: Sequence[str],
    expected_documents: Any,
) -> dict[str, Any]:
    expected_set = {str(label) for label in expected}
    hit_labels = {item for item in ranked_ids if item in expected_set}
    role_by_label = _role_by_label(expected_documents, expected)
    primary_expected = {label for label, role in role_by_label.items() if role == "primary"}
    supporting_expected = {label for label, role in role_by_label.items() if role == "supporting"}
    return {
        "expected_label_count": len(expected_set),
        "hit_label_count": len(hit_labels),
        "missing_labels": sorted(expected_set - hit_labels),
        "primary_expected_count": len(primary_expected),
        "primary_hit_count": len(primary_expected & hit_labels),
        "supporting_expected_count": len(supporting_expected),
        "supporting_hit_count": len(supporting_expected & hit_labels),
        "all_expected_hit": bool(expected_set) and expected_set <= hit_labels,
        "all_primary_hit": bool(primary_expected) and primary_expected <= hit_labels,
    }


def _role_by_label(expected_documents: Any, expected: Sequence[str]) -> dict[str, str]:
    roles = {str(label): "primary" for label in expected}
    if not isinstance(expected_documents, Sequence) or isinstance(expected_documents, (str, bytes)):
        return roles
    for document in expected_documents:
        if not isinstance(document, dict):
            continue
        label = _document_label(document)
        if label in roles:
            roles[label] = str(document.get("role") or "primary").strip().lower() or "primary"
    return roles


def _document_label(document: dict[str, Any]) -> str:
    for field in ("label", "source_id", "chunk_id"):
        value = str(document.get(field) or "").strip()
        if value:
            return value
    return ""


def _result_summary(result: RetrievalResult) -> dict[str, Any]:
    return {
        "source_type": result.metadata.get("source_type"),
        "source_id": result.metadata.get("source_id"),
        "artifact_path": result.metadata.get("artifact_path"),
        "score": result.score,
    }


def _result_key(result: RetrievalResult) -> tuple[str, str, str, str]:
    return (
        str(result.metadata.get("source_type") or ""),
        str(result.metadata.get("source_id") or ""),
        str(result.metadata.get("chunk_index") or ""),
        str(result.metadata.get("artifact_path") or ""),
    )


def _consume_query_plan(retriever: Any) -> dict[str, Any] | None:
    plan = getattr(retriever, "last_query_plan", None)
    if isinstance(plan, dict):
        return plan
    return None


def _aggregate_query_metrics(query_reports: Sequence[dict[str, Any]], k_values: Sequence[int]) -> dict[str, Any]:
    if not query_reports:
        return {
            "precision_at_k": {str(k): 0.0 for k in k_values},
            "recall_at_k": {str(k): 0.0 for k in k_values},
            "ndcg_at_k": {str(k): 0.0 for k in k_values},
            "mrr": 0.0,
            "weighted_recall_at_k": {str(k): 0.0 for k in k_values},
            "weighted_ndcg_at_k": {str(k): 0.0 for k in k_values},
            "all_expected_hit_rate": 0.0,
            "all_primary_hit_rate": 0.0,
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
        "weighted_recall_at_k": {
            str(k): sum(float(item["weighted_metrics"]["weighted_recall_at_k"][str(k)]) for item in query_reports)
            / count
            for k in k_values
        },
        "weighted_ndcg_at_k": {
            str(k): sum(float(item["weighted_metrics"]["weighted_ndcg_at_k"][str(k)]) for item in query_reports)
            / count
            for k in k_values
        },
        "all_expected_hit_rate": sum(1 for item in query_reports if item["evidence_coverage"]["all_expected_hit"])
        / count,
        "all_primary_hit_rate": sum(1 for item in query_reports if item["evidence_coverage"]["all_primary_hit"])
        / count,
    }
