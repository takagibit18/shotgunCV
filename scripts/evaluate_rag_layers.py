from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from statistics import mean
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "cli" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "py-core" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "py-agents" / "src"))

from scripts.validate_golden_rag_set import validate_golden_set  # noqa: E402
from shotguncv_core.db.indexer import build_projection_batch  # noqa: E402
from shotguncv_core.rag.embeddings import EmbeddingModel  # noqa: E402
from shotguncv_core.rag.metrics import evaluate_labeled_retrieval_queries  # noqa: E402
from shotguncv_core.rag.retrieval import InMemoryBM25Retriever, InMemoryHybridRetriever, InMemoryVectorRetriever, Retriever  # noqa: E402


NO_ANSWER_SCORE_THRESHOLD = 0.8

_JD_ID_RE = re.compile(r"jd-\d+")


class _TwoStageRetriever:
    """Thin adapter: first-stage coarse retrieval → cross-encoder reranker → top-k.

    Exposes the same ``search(query, limit, **filters)`` interface so
    ``evaluate_labeled_retrieval_queries`` works without modification.
    """

    def __init__(
        self,
        first_stage: Any,
        reranker: Any,
        first_stage_limit: int = 50,
    ) -> None:
        self._first_stage = first_stage
        self._reranker = reranker
        self._first_stage_limit = first_stage_limit

    def search(self, query: str, *, limit: int = 10, **filters: Any) -> Any:
        coarse = self._first_stage.search(query, limit=self._first_stage_limit, **filters)
        return self._reranker.rerank(query, coarse, top_k=limit)


def evaluate_retriever_layer(
    *,
    run_dir: Path,
    golden_file: Path,
    output_path: Path,
    k_values: list[int],
    embedding_model: EmbeddingModel | None = None,
    no_answer_score_threshold: float = NO_ANSWER_SCORE_THRESHOLD,
    retriever_mode: str = "dense",
    vector_weight: float = 0.75,
    bm25_weight: float = 0.25,
    query_expansion: str = "none",
    reranker_model: str | None = None,
    first_stage_limit: int = 50,
    golden_layers: list[str] | None = None,
) -> dict[str, Any]:
    from shotguncv_core.rag.retrieval import InMemoryVectorRetriever, expand_query

    payload = _load_valid_golden(golden_file)
    samples = _filter_samples_by_golden_layer(_samples(payload), golden_layers)
    batch = build_projection_batch(run_dir)
    first_stage, retriever_type = _build_retriever(
        batch.retrieval_chunks,
        retriever_mode=retriever_mode,
        embedding_model=embedding_model,
        vector_weight=vector_weight,
        bm25_weight=bm25_weight,
    )
    # Build dense retriever for query expansion if needed
    expansion_dense = None
    if query_expansion == "dense_jd":
        expansion_dense = InMemoryVectorRetriever.from_chunks(
            batch.retrieval_chunks, embedding_model=embedding_model
        )

    query_specs = [_sample_to_query_spec(sample) for sample in samples if sample.get("case_type") != "no_answer"]

    # Apply query expansion to each spec
    for spec in query_specs:
        if query_expansion != "none":
            spec["expanded_query"] = expand_query(
                str(spec["query"]),
                method=query_expansion,
                dense_retriever=expansion_dense,
            )

    # Build two-stage retriever if reranker is requested
    if reranker_model:
        from shotguncv_core.rag.reranking import CrossEncoderReranker

        reranker = CrossEncoderReranker(reranker_model)
        retriever = _TwoStageRetriever(first_stage, reranker, first_stage_limit=first_stage_limit)
        retriever_type = f"{retriever_type} + {reranker_model} (first-stage={first_stage_limit})"
    else:
        retriever = first_stage

    coverage = _label_coverage(batch.retrieval_chunks, query_specs)
    quality_gate = _quality_gate(coverage)
    if quality_gate["status"] != "passed":
        raise ValueError(
            "RAG golden label coverage failed: "
            f"{coverage['matched_label_count']}/{coverage['expected_label_count']} labels matched; "
            f"missing={coverage['missing_expected_chunks']}"
        )
    metrics = evaluate_labeled_retrieval_queries(retriever=retriever, query_specs=query_specs, k_values=k_values)
    report = {
        "schema_version": "rag-retriever-layer-metrics-v1",
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "golden_file": str(golden_file),
        "golden_schema_version": payload["schema_version"],
        "golden_layer_filter": _normalized_golden_layers(golden_layers),
        "retriever_mode": retriever_mode,
        "retriever_type": retriever_type,
        "reranker_model": reranker_model,
        "first_stage_limit": first_stage_limit if reranker_model else None,
        "query_expansion": query_expansion,
        "chunk_count": len(batch.retrieval_chunks),
        "sample_count": len(samples),
        "answerable_sample_count": len(query_specs),
        "no_answer_sample_count": len(samples) - len(query_specs),
        "label_coverage": coverage,
        "quality_gate": quality_gate,
        "metrics": metrics,
        "case_type_metrics": _case_type_metrics(metrics["queries"], query_specs, k_values),
        "golden_layer_metrics": _golden_layer_metrics(metrics["queries"], query_specs, k_values),
        "no_answer_behavior": _no_answer_behavior(
            retriever,
            samples,
            k_values,
            score_threshold=no_answer_score_threshold,
        ),
    }
    _write_json(output_path, report)
    return report


def evaluate_generator_layer(
    *,
    golden_file: Path,
    answers_file: Path,
    output_path: Path,
    run_dir: Path | None = None,
    retriever_report_file: Path | None = None,
    golden_layers: list[str] | None = None,
) -> dict[str, Any]:
    payload = _load_valid_golden(golden_file)
    samples = _filter_samples_by_golden_layer(_samples(payload), golden_layers)
    answers = _load_answers(answers_file)
    chunks = build_projection_batch(run_dir).retrieval_chunks if run_dir else []
    retriever_gate = _load_retriever_gate(retriever_report_file)
    sample_reports = [
        _evaluate_generator_sample(
            sample,
            answers.get(str(sample["question_id"]), {}),
            chunks,
            retriever_gate.get(str(sample["question_id"])),
        )
        for sample in samples
    ]
    report = {
        "schema_version": "rag-generator-layer-metrics-v1",
        "golden_file": str(golden_file),
        "answers_file": str(answers_file),
        "run_dir": str(run_dir) if run_dir else None,
        "retriever_report_file": str(retriever_report_file) if retriever_report_file else None,
        "golden_schema_version": payload["schema_version"],
        "golden_layer_filter": _normalized_golden_layers(golden_layers),
        "sample_count": len(samples),
        "answered_sample_count": sum(1 for item in sample_reports if item["answer_chars"] > 0),
        "retriever_gate": _retriever_gate_summary(retriever_gate, sample_reports),
        "aggregate": _aggregate_generator_samples(sample_reports),
        "case_type_metrics": _generator_case_type_metrics(sample_reports),
        "golden_layer_metrics": _generator_golden_layer_metrics(sample_reports),
        "samples": sample_reports,
    }
    _write_json(output_path, report)
    return report


def _load_valid_golden(golden_file: Path) -> dict[str, Any]:
    validation = validate_golden_set(golden_file)
    if validation["status"] != "passed":
        raise ValueError(f"Invalid RAG golden set: {validation['errors']}")
    payload = json.loads(golden_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Golden set must be a JSON object.")
    return payload


def _samples(payload: dict[str, Any]) -> list[dict[str, Any]]:
    samples = payload.get("samples")
    if not isinstance(samples, list):
        raise ValueError("Golden set requires a samples list.")
    return [sample for sample in samples if isinstance(sample, dict)]


def _normalized_golden_layers(golden_layers: list[str] | None) -> list[str]:
    return sorted({str(layer).strip() for layer in golden_layers or [] if str(layer).strip()})


def _filter_samples_by_golden_layer(
    samples: list[dict[str, Any]], golden_layers: list[str] | None
) -> list[dict[str, Any]]:
    allowed = set(_normalized_golden_layers(golden_layers))
    if not allowed:
        return samples
    return [sample for sample in samples if _sample_golden_layer(sample) in allowed]


def _sample_to_query_spec(sample: dict[str, Any]) -> dict[str, Any]:
    expected_docs = sample.get("expected_documents", [])
    jd_id = _extract_jd_id(expected_docs)
    source_type = _extract_source_type(expected_docs)
    filters = _query_filters(jd_id=jd_id, source_type=source_type)
    spec: dict[str, Any] = {
        "query_id": sample["question_id"],
        "query": sample["question"],
        "case_type": sample.get("case_type"),
        "golden_layer": _sample_golden_layer(sample),
        "expected_chunks": [_document_label(document) for document in expected_docs],
        "expected_documents": expected_docs,
        "filter_scope": _filter_scope(jd_id=jd_id, source_type=source_type),
        "filters": filters,
    }
    if jd_id:
        spec["jd_id"] = jd_id
    if source_type:
        spec["source_type"] = source_type
    return spec


def _sample_golden_layer(sample: dict[str, Any]) -> str:
    metadata = sample.get("metadata")
    if isinstance(metadata, dict):
        layer = str(metadata.get("golden_layer") or "").strip()
        if layer:
            return layer
    return "unknown"


def _extract_jd_id(expected_documents: list[dict[str, Any]]) -> str | None:
    jd_ids = [_document_jd_id(doc) for doc in expected_documents]
    if not jd_ids or any(jd_id is None for jd_id in jd_ids):
        return None
    unique_jd_ids = set(jd_ids)
    return unique_jd_ids.pop() if len(unique_jd_ids) == 1 else None


def _document_jd_id(document: dict[str, Any]) -> str | None:
    source_type = str(document.get("source_type") or "").strip().lower()
    label = str(document.get("label") or "")
    source_id = str(document.get("source_id") or "")
    if source_type == "candidate_evidence":
        return None
    if "candidate-profile" in f"{label}\n{source_id}".lower():
        return None
    jd_ids: set[str] = set()
    for value in (source_id, label):
        m = _JD_ID_RE.search(value)
        if m:
            jd_ids.add(m.group(0))
    return jd_ids.pop() if len(jd_ids) == 1 else None


def _extract_source_type(expected_documents: list[dict[str, Any]]) -> str | None:
    source_types: set[str] = {str(doc.get("source_type") or "").strip() for doc in expected_documents}
    source_types.discard("")
    return source_types.pop() if len(source_types) == 1 else None


def _query_filters(*, jd_id: str | None, source_type: str | None) -> dict[str, str]:
    filters: dict[str, str] = {}
    if jd_id:
        filters["jd_id"] = jd_id
    if source_type:
        filters["source_type"] = source_type
    return filters


def _filter_scope(*, jd_id: str | None, source_type: str | None) -> str:
    if jd_id:
        return "single_jd"
    if source_type:
        return "single_source_type"
    return "mixed_scope"


def _label_coverage(chunks: list[dict[str, Any]], query_specs: list[dict[str, Any]]) -> dict[str, Any]:
    expected = sorted({label for spec in query_specs for label in spec.get("expected_chunks", []) if str(label).strip()})
    matched = [_matched_label_summary(chunks, label) for label in expected if any(_chunk_matches_label(chunk, label) for chunk in chunks)]
    missing = [label for label in expected if not any(item["label"] == label for item in matched)]
    return {
        "expected_label_count": len(expected),
        "matched_label_count": len(expected) - len(missing),
        "coverage_ratio": ((len(expected) - len(missing)) / len(expected)) if expected else 1.0,
        "missing_expected_chunks": missing,
        "matched_labels": matched,
    }


def _quality_gate(coverage: dict[str, Any]) -> dict[str, Any]:
    passed = float(coverage.get("coverage_ratio", 0.0)) == 1.0
    return {
        "status": "passed" if passed else "failed",
        "label_coverage_required": 1.0,
        "label_coverage_actual": coverage.get("coverage_ratio", 0.0),
        "blocks_metric_interpretation": not passed,
    }


def _case_type_metrics(
    query_reports: list[dict[str, Any]], query_specs: list[dict[str, Any]], k_values: list[int]
) -> dict[str, Any]:
    case_type_by_query = {str(spec["query_id"]): str(spec.get("case_type") or "unknown") for spec in query_specs}
    by_case_type: dict[str, list[dict[str, Any]]] = {}
    for query in query_reports:
        by_case_type.setdefault(case_type_by_query.get(str(query.get("query_id")), "unknown"), []).append(query)
    return {
        case_type: {
            "query_count": len(queries),
            "aggregate": _aggregate_retriever_queries(queries, k_values),
        }
        for case_type, queries in sorted(by_case_type.items())
    }


def _golden_layer_metrics(
    query_reports: list[dict[str, Any]], query_specs: list[dict[str, Any]], k_values: list[int]
) -> dict[str, Any]:
    layer_by_query = {str(spec["query_id"]): str(spec.get("golden_layer") or "unknown") for spec in query_specs}
    by_layer: dict[str, list[dict[str, Any]]] = {}
    for query in query_reports:
        by_layer.setdefault(layer_by_query.get(str(query.get("query_id")), "unknown"), []).append(query)
    return {
        layer: {
            "query_count": len(queries),
            "aggregate": _aggregate_retriever_queries(queries, k_values),
        }
        for layer, queries in sorted(by_layer.items())
    }


def _aggregate_retriever_queries(query_reports: list[dict[str, Any]], k_values: list[int]) -> dict[str, Any]:
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
    return {
        "precision_at_k": {
            str(k): mean(float(item["metrics"]["precision_at_k"][str(k)]) for item in query_reports) for k in k_values
        },
        "recall_at_k": {
            str(k): mean(float(item["metrics"]["recall_at_k"][str(k)]) for item in query_reports) for k in k_values
        },
        "ndcg_at_k": {
            str(k): mean(float(item["metrics"]["ndcg_at_k"][str(k)]) for item in query_reports) for k in k_values
        },
        "mrr": mean(float(item["metrics"]["mrr"]) for item in query_reports),
        "weighted_recall_at_k": {
            str(k): mean(float(item["weighted_metrics"]["weighted_recall_at_k"][str(k)]) for item in query_reports)
            for k in k_values
        },
        "weighted_ndcg_at_k": {
            str(k): mean(float(item["weighted_metrics"]["weighted_ndcg_at_k"][str(k)]) for item in query_reports)
            for k in k_values
        },
        "all_expected_hit_rate": mean(
            1.0 if item["evidence_coverage"]["all_expected_hit"] else 0.0 for item in query_reports
        ),
        "all_primary_hit_rate": mean(
            1.0 if item["evidence_coverage"]["all_primary_hit"] else 0.0 for item in query_reports
        ),
    }


def _no_answer_behavior(
    retriever: Retriever,
    samples: list[dict[str, Any]],
    k_values: list[int],
    *,
    score_threshold: float,
) -> dict[str, Any]:
    limit = max(k_values) if k_values else 10
    reports = []
    for sample in samples:
        if sample.get("case_type") != "no_answer":
            continue
        results = retriever.search(str(sample["question"]), limit=limit, source_type="candidate_evidence")
        top_score = results[0].score if results else None
        abstained = top_score is None or top_score < score_threshold
        reports.append(
            {
                "question_id": sample["question_id"],
                "retrieved_count": len(results),
                "effective_result_count": 0 if abstained else len(results),
                "top_score": top_score,
                "score_threshold": score_threshold,
                "filter_scope": "candidate_evidence",
                "abstained": abstained,
                "gate_status": "abstained" if abstained else "needs_review",
                "should_abstain": True,
            }
        )
    non_empty = sum(1 for item in reports if item["retrieved_count"] > 0)
    abstained_count = sum(1 for item in reports if item["abstained"])
    leaked_count = len(reports) - abstained_count
    return {
        "query_count": len(reports),
        "non_empty_result_count": non_empty,
        "empty_result_rate": ((len(reports) - non_empty) / len(reports)) if reports else 1.0,
        "score_threshold": score_threshold,
        "abstained_count": abstained_count,
        "abstention_rate": (abstained_count / len(reports)) if reports else 1.0,
        "quality_gate": {
            "status": "passed" if leaked_count == 0 else "failed",
            "max_allowed_non_abstained": 0,
            "non_abstained_count": leaked_count,
            "blocks_generator": leaked_count > 0,
        },
        "queries": reports,
    }


def _build_retriever(
    chunks: list[dict[str, Any]],
    *,
    retriever_mode: str,
    embedding_model: EmbeddingModel | None,
    vector_weight: float = 0.75,
    bm25_weight: float = 0.25,
) -> tuple[Retriever, str]:
    if retriever_mode == "dense":
        return InMemoryVectorRetriever.from_chunks(chunks, embedding_model=embedding_model), "InMemoryVectorRetriever"
    if retriever_mode == "bm25":
        return InMemoryBM25Retriever.from_chunks(chunks), "InMemoryBM25Retriever"
    if retriever_mode == "hybrid":
        return (
            InMemoryHybridRetriever.from_chunks(
                chunks,
                embedding_model=embedding_model,
                vector_weight=vector_weight,
                bm25_weight=bm25_weight,
            ),
            "InMemoryHybridRetriever",
        )
    raise ValueError(f"Unsupported retriever mode: {retriever_mode}")


def _load_answers(answers_file: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(answers_file.read_text(encoding="utf-8"))
    items: Any
    if isinstance(payload, dict) and isinstance(payload.get("answers"), list):
        items = payload["answers"]
    elif isinstance(payload, list):
        items = payload
    else:
        raise ValueError("Answers file must be a list or an object with an answers list.")
    answers: dict[str, dict[str, Any]] = {}
    for item in items:
        if isinstance(item, dict) and str(item.get("question_id") or "").strip():
            answers[str(item["question_id"])] = item
    return answers


def _load_retriever_gate(retriever_report_file: Path | None) -> dict[str, dict[str, Any]]:
    if retriever_report_file is None:
        return {}
    payload = json.loads(retriever_report_file.read_text(encoding="utf-8"))
    no_answer_behavior = payload.get("no_answer_behavior") if isinstance(payload, dict) else {}
    queries = no_answer_behavior.get("queries") if isinstance(no_answer_behavior, dict) else []
    if not isinstance(queries, list):
        return {}
    return {
        str(item["question_id"]): item
        for item in queries
        if isinstance(item, dict) and str(item.get("question_id") or "").strip()
    }


def _retriever_gate_summary(retriever_gate: dict[str, dict[str, Any]], samples: list[dict[str, Any]]) -> dict[str, Any]:
    blocked = [sample for sample in samples if sample.get("blocked_by_retriever_gate")]
    return {
        "enabled": bool(retriever_gate),
        "blocked_no_answer_count": len(blocked),
        "blocked_question_ids": [str(sample["question_id"]) for sample in blocked],
    }


def _evaluate_generator_sample(
    sample: dict[str, Any],
    answer_record: dict[str, Any],
    chunks: list[dict[str, Any]],
    retriever_gate_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    blocked_by_gate = _blocked_by_retriever_gate(sample, retriever_gate_record)
    answer = str(answer_record.get("answer") or "")
    expected_labels = [_document_label(document) for document in sample.get("expected_documents", [])]
    citations = answer_record.get("citations") or answer_record.get("evidence_citations") or []
    if not isinstance(citations, list):
        citations = []
    if blocked_by_gate:
        answer = ""
        citations = []
    perfect_documents = [_matched_label_summary(chunks, label) for label in expected_labels] if chunks else []
    must_cover = _coverage(answer, sample.get("must_cover_points", []))
    forbidden = _matched_forbidden_claims(answer, sample.get("forbidden_claims", []))
    citation_accuracy = _citation_accuracy(citations, expected_labels)
    faithfulness = 1.0 if blocked_by_gate else _faithfulness(answer, forbidden, citation_accuracy, bool(expected_labels))
    relevance = 1.0 if blocked_by_gate else _answer_relevance(answer, sample)
    return {
        "question_id": sample["question_id"],
        "case_type": sample.get("case_type"),
        "golden_layer": _sample_golden_layer(sample),
        "answer_chars": len(answer),
        "blocked_by_retriever_gate": blocked_by_gate,
        "retriever_gate_status": (retriever_gate_record or {}).get("gate_status"),
        "expected_labels": expected_labels,
        "perfect_document_count": len(perfect_documents),
        "faithfulness": faithfulness,
        "answer_relevance": relevance,
        "must_cover_coverage": must_cover,
        "forbidden_claim_violation_count": len(forbidden),
        "forbidden_claims_matched": forbidden,
        "citation_accuracy": citation_accuracy,
    }


def _blocked_by_retriever_gate(sample: dict[str, Any], retriever_gate_record: dict[str, Any] | None) -> bool:
    if sample.get("case_type") != "no_answer" or not retriever_gate_record:
        return False
    if retriever_gate_record.get("abstained") is True:
        return True
    return int(retriever_gate_record.get("effective_result_count") or 0) == 0


def _aggregate_generator_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        return _empty_generator_aggregate()
    return {
        "faithfulness": mean(float(item["faithfulness"]) for item in samples),
        "answer_relevance": mean(float(item["answer_relevance"]) for item in samples),
        "must_cover_coverage": mean(float(item["must_cover_coverage"]) for item in samples),
        "citation_accuracy": mean(float(item["citation_accuracy"]) for item in samples),
        "forbidden_claim_violation_count": sum(int(item["forbidden_claim_violation_count"]) for item in samples),
    }


def _generator_case_type_metrics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    by_case_type: dict[str, list[dict[str, Any]]] = {}
    for item in samples:
        by_case_type.setdefault(str(item.get("case_type") or "unknown"), []).append(item)
    return {
        case_type: {"sample_count": len(items), "aggregate": _aggregate_generator_samples(items)}
        for case_type, items in sorted(by_case_type.items())
    }


def _generator_golden_layer_metrics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    by_layer: dict[str, list[dict[str, Any]]] = {}
    for item in samples:
        by_layer.setdefault(str(item.get("golden_layer") or "unknown"), []).append(item)
    return {
        layer: {"sample_count": len(items), "aggregate": _aggregate_generator_samples(items)}
        for layer, items in sorted(by_layer.items())
    }


def _empty_generator_aggregate() -> dict[str, Any]:
    return {
        "faithfulness": 0.0,
        "answer_relevance": 0.0,
        "must_cover_coverage": 0.0,
        "citation_accuracy": 0.0,
        "forbidden_claim_violation_count": 0,
    }


def _coverage(answer: str, points: Any) -> float:
    values = [str(item).strip() for item in points if str(item).strip()] if isinstance(points, list) else []
    if not values:
        return 1.0
    return sum(1 for point in values if _contains_point(answer, point)) / len(values)


def _contains_point(answer: str, point: str) -> bool:
    answer_norm = _normalize(answer)
    point_norm = _normalize(point)
    if not point_norm:
        return False
    if point_norm in answer_norm:
        return True
    point_tokens = set(_tokens(point))
    if not point_tokens:
        return False
    answer_tokens = set(_tokens(answer))
    return len(point_tokens & answer_tokens) / len(point_tokens) >= 0.5


def _matched_forbidden_claims(answer: str, claims: Any) -> list[str]:
    values = [str(item).strip() for item in claims if str(item).strip()] if isinstance(claims, list) else []
    return [claim for claim in values if _contains_point(answer, claim)]


def _citation_accuracy(citations: list[Any], expected_labels: list[str]) -> float:
    if not expected_labels:
        return 1.0 if not citations else 0.0
    if not citations:
        return 0.0
    expected = {_normalize(label) for label in expected_labels}
    valid = 0
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        label = _normalize(_document_label(citation))
        if label in expected:
            valid += 1
    return valid / len(citations)


def _faithfulness(answer: str, forbidden_claims: list[str], citation_accuracy: float, expects_citations: bool) -> float:
    if not answer.strip():
        return 0.0
    if forbidden_claims:
        return 0.0
    if expects_citations:
        return max(0.0, min(1.0, 0.5 + (0.5 * citation_accuracy)))
    return 1.0


def _answer_relevance(answer: str, sample: dict[str, Any]) -> float:
    if not answer.strip():
        return 0.0
    target_tokens = set(
        _tokens(
            " ".join(
                [
                    str(sample.get("question") or ""),
                    str(sample.get("golden_answer") or ""),
                    " ".join(str(item) for item in sample.get("must_cover_points", []) if str(item).strip()),
                ]
            )
        )
    )
    if not target_tokens:
        return 1.0
    answer_tokens = set(_tokens(answer))
    return min(1.0, len(target_tokens & answer_tokens) / max(1, min(len(target_tokens), 20)))


def _chunk_matches_label(chunk: dict[str, Any], label: str) -> bool:
    metadata = chunk.get("metadata") or {}
    haystack = "\n".join(
        [
            str(chunk.get("chunk_id") or ""),
            str(metadata.get("source_type") or ""),
            str(metadata.get("source_id") or ""),
            str(metadata.get("artifact_path") or ""),
            str(metadata.get("provenance_summary") or ""),
            str(chunk.get("text") or ""),
        ]
    ).lower()
    return label.lower() in haystack


def _matched_label_summary(chunks: list[dict[str, Any]], label: str) -> dict[str, Any]:
    matches = [chunk for chunk in chunks if _chunk_matches_label(chunk, label)]
    return {
        "label": label,
        "source_types": sorted({str((chunk.get("metadata") or {}).get("source_type") or "unknown") for chunk in matches}),
        "source_ids": sorted({str((chunk.get("metadata") or {}).get("source_id") or "") for chunk in matches})[:10],
    }


def _document_label(document: dict[str, Any]) -> str:
    for field in ["label", "source_id", "chunk_id"]:
        value = str(document.get(field) or "").strip()
        if value:
            return value
    return ""


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", text.lower())


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate RAG layers from a rag-golden-v1 dataset.")
    parser.add_argument("--layer", choices=["retriever", "generator"], required=True)
    parser.add_argument("--golden-file", type=Path, default=ROOT / "fixtures" / "golden_rag_questions.json")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--answers-file", type=Path)
    parser.add_argument("--retriever-report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--k", type=int, action="append", default=[1, 3, 5, 10])
    parser.add_argument("--retriever-mode", choices=["dense", "bm25", "hybrid"], default="dense")
    parser.add_argument(
        "--no-answer-score-threshold",
        type=float,
        default=NO_ANSWER_SCORE_THRESHOLD,
        help="Minimum top retrieval score required before a no-answer sample is treated as non-abstained.",
    )
    parser.add_argument("--vector-weight", type=float, default=0.75, help="Hybrid retriever vector weight.")
    parser.add_argument("--bm25-weight", type=float, default=0.25, help="Hybrid retriever BM25 weight.")
    parser.add_argument(
        "--query-expansion",
        choices=["none", "static", "dense_jd"],
        default="none",
        help="Query expansion strategy: static term mapping, or dense-driven jd_id discovery.",
    )
    parser.add_argument(
        "--reranker",
        default=None,
        help="Cross-encoder model for two-stage retrieval (e.g. BAAI/bge-reranker-v2-m3).",
    )
    parser.add_argument(
        "--first-stage-limit",
        type=int,
        default=50,
        help="Number of candidates from first-stage retrieval to feed into reranker.",
    )
    parser.add_argument(
        "--golden-layer",
        action="append",
        default=None,
        help="Evaluate only samples whose metadata.golden_layer matches this value. Repeat for multiple layers.",
    )
    args = parser.parse_args()
    if args.layer == "retriever":
        if not args.run_dir:
            parser.error("--layer retriever requires --run-dir")
        report = evaluate_retriever_layer(
            run_dir=args.run_dir,
            golden_file=args.golden_file,
            output_path=args.output,
            k_values=args.k,
            no_answer_score_threshold=args.no_answer_score_threshold,
            retriever_mode=args.retriever_mode,
            vector_weight=args.vector_weight,
            bm25_weight=args.bm25_weight,
            query_expansion=args.query_expansion,
            reranker_model=args.reranker,
            first_stage_limit=args.first_stage_limit,
            golden_layers=args.golden_layer,
        )
        print(json.dumps({"output": str(args.output), "aggregate": report["metrics"]["aggregate"]}, ensure_ascii=False, indent=2))
        return 0
    if not args.answers_file:
        parser.error("--layer generator requires --answers-file")
    report = evaluate_generator_layer(
        golden_file=args.golden_file,
        answers_file=args.answers_file,
        output_path=args.output,
        run_dir=args.run_dir,
        retriever_report_file=args.retriever_report,
        golden_layers=args.golden_layer,
    )
    print(json.dumps({"output": str(args.output), "aggregate": report["aggregate"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
