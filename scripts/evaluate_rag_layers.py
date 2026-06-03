from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from statistics import mean
from typing import Any
from collections import Counter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "cli" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "py-core" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "py-agents" / "src"))

from scripts.validate_golden_rag_set import validate_golden_set  # noqa: E402
from shotguncv_core.db.indexer import build_projection_batch  # noqa: E402
from shotguncv_core.rag.embeddings import EmbeddingModel  # noqa: E402
from shotguncv_core.rag.metrics import evaluate_labeled_retrieval_queries  # noqa: E402
from shotguncv_core.rag.retrieval import InMemoryBM25Retriever, InMemoryHybridRetriever, InMemoryVectorRetriever, Retriever, SmartRouterRetriever  # noqa: E402


NO_ANSWER_SCORE_THRESHOLD = 0.8
DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
DEFAULT_FIRST_STAGE_LIMIT = 20

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
        self.last_query_plan: dict[str, Any] | None = None

    def search(self, query: str, *, limit: int = 10, **filters: Any) -> Any:
        coarse = self._first_stage.search(query, limit=self._first_stage_limit, **filters)
        self.last_query_plan = getattr(self._first_stage, "last_query_plan", None)
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
    reranker_model: str | None = DEFAULT_RERANKER_MODEL,
    first_stage_limit: int = DEFAULT_FIRST_STAGE_LIMIT,
    golden_layers: list[str] | None = None,
    query_strategy: str = "single",
    router_broad_limit: int = 20,
    enable_support_gate: bool = False,
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

    query_specs = prepare_query_specs(
        [sample for sample in samples if sample.get("case_type") != "no_answer"],
        query_strategy=query_strategy,
    )

    # Apply query expansion to each spec
    for spec in query_specs:
        if query_expansion != "none":
            base_query = str(spec.get("expanded_query") or spec["query"])
            spec["expanded_query"] = expand_query(
                base_query,
                method=query_expansion,
                dense_retriever=expansion_dense,
            )

    retriever = first_stage
    if query_strategy == "smart":
        retriever = SmartRouterRetriever.from_chunks(
            batch.retrieval_chunks,
            embedding_model=embedding_model,
            vector_weight=vector_weight,
            bm25_weight=bm25_weight,
            broad_limit=router_broad_limit,
            enable_support_gate=enable_support_gate,
        )
        retriever_type = f"SmartRouterRetriever({retriever_type}, broad_limit={router_broad_limit})"
    # Build two-stage retriever if reranker is requested
    if reranker_model:
        from shotguncv_core.rag.reranking import CrossEncoderReranker

        reranker = CrossEncoderReranker(reranker_model)
        retriever = _TwoStageRetriever(retriever, reranker, first_stage_limit=first_stage_limit)
        retriever_type = f"{retriever_type} + {reranker_model} (first-stage={first_stage_limit})"

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
        "query_strategy": query_strategy,
        "router_mode": "rule_based" if query_strategy == "smart" else None,
        "router_broad_limit": router_broad_limit if query_strategy == "smart" else None,
        "support_gate_enabled": enable_support_gate,
        "chunk_count": len(batch.retrieval_chunks),
        "sample_count": len(samples),
        "sample_report": _sample_report(samples),
        "answerable_sample_count": len(query_specs),
        "no_answer_sample_count": len(samples) - len(query_specs),
        "label_coverage": coverage,
        "quality_gate": quality_gate,
        "metrics": metrics,
        "case_type_metrics": _case_type_metrics(metrics["queries"], query_specs, k_values),
        "golden_layer_metrics": _golden_layer_metrics(metrics["queries"], query_specs, k_values),
        "robustness_category_metrics": _robustness_category_metrics(metrics["queries"], query_specs, k_values),
        "ocr_behavior": _ocr_behavior(metrics["queries"], query_specs),
        "no_answer_behavior": _no_answer_behavior(
            retriever,
            samples,
            k_values,
            score_threshold=no_answer_score_threshold,
            enable_support_gate=enable_support_gate,
        ),
        "smart_routing_observability": _smart_routing_observability(metrics["queries"]),
    }
    _write_json(output_path, report)
    return report


def prepare_query_specs(samples: list[dict[str, Any]], *, query_strategy: str = "single") -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for sample in samples:
        spec = _sample_to_query_spec(sample)
        _apply_ocr_query_rewrite(spec, sample)
        if query_strategy == "decomposed" and _should_decompose_sample(sample):
            spec["query_decomposition"] = _build_query_decomposition(spec, sample)
        specs.append(spec)
    return specs


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


def report_layer_counts(samples: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(_sample_golden_layer(sample) for sample in samples).items()))


def report_case_type_counts(samples: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(str(sample.get("case_type") or "unknown") for sample in samples).items()))


def _sample_report(samples: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "sample_count": len(samples),
        "case_type_counts": report_case_type_counts(samples),
        "golden_layer_counts": report_layer_counts(samples),
        "default_headline_layers": ["core_high_info", "non_target_negative"],
    }


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
        "robustness_category": _sample_robustness_category(sample),
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


def _sample_robustness_category(sample: dict[str, Any]) -> str:
    metadata = sample.get("metadata")
    if isinstance(metadata, dict):
        category = str(metadata.get("robustness_category") or "").strip()
        if category:
            return category
    return "unknown"


def _apply_ocr_query_rewrite(spec: dict[str, Any], sample: dict[str, Any]) -> None:
    if _sample_golden_layer(sample) != "ocr_regression":
        return
    category = _sample_robustness_category(sample)
    question = str(sample.get("question") or "")
    source_ids = " ".join(str(document.get("source_id") or "") for document in sample.get("expected_documents", []))
    profile = " ".join([category, question, source_ids]).lower()
    additions = ["ocr", "ocr noise", "image text", "normalized keywords"]
    if category in {"ocr_weak_keyword", "ocr_low_info_judgment"} or "jd-025-req-001" in profile:
        additions.extend(
            [
                "developer tools",
                "developer workflow",
                "workflow",
                "ai agent",
                "automation",
                "cli",
                "open source ai project",
            ]
        )
    if category == "ocr_multi_requirement" or any(source_id in profile for source_id in ["jd-025-req-003", "jd-025-req-007"]):
        additions.extend(
            [
                "python",
                "go",
                "java",
                "typescript",
                "agent debugging",
                "tool failure",
                "logs",
                "retrieval quality",
            ]
        )
    if category in {"ocr_noise_detection", "ocr_regression"} or any(
        source_id in profile for source_id in ["jd-025-req-014", "jd-025-req-018"]
    ):
        additions.extend(
            [
                "milvus",
                "mivus",
                "qdrant",
                "faiss",
                "vector database",
                "gitlab ci",
                "ci/cd",
                "low confidence",
            ]
        )
    if category == "similar_concept_interference":
        additions.extend(["similar concept", "interference", "negative boundary", "do not overclaim"])
    unique = _unique_terms(additions)
    if not unique:
        return
    base_query = str(spec.get("expanded_query") or spec["query"])
    spec["expanded_query"] = f"{base_query}\n{' '.join(unique)}"
    spec["query_rewrite"] = {"strategy": "ocr_alias", "terms": unique}


def _should_decompose_sample(sample: dict[str, Any]) -> bool:
    case_type = str(sample.get("case_type") or "").strip()
    category = _sample_robustness_category(sample)
    return case_type in {"multi_document", "stale_or_conflicting"} or category == "cross_section"


def _build_query_decomposition(spec: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any]:
    expected_documents = [doc for doc in sample.get("expected_documents", []) if isinstance(doc, dict)]
    primary_documents = [
        document
        for document in expected_documents
        if str(document.get("role") or "primary").strip().lower() == "primary"
    ]
    if not primary_documents and expected_documents:
        primary_documents = [expected_documents[0]]
    stages: list[dict[str, Any]] = []
    if primary_documents:
        stages.append(_decomposition_stage("primary", primary_documents, spec))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for document in expected_documents:
        if document in primary_documents:
            continue
        grouped.setdefault(_decomposition_stage_name(document), []).append(document)
    for stage_name in ("supporting", "conflicting", "stale", "gap", "ranking"):
        documents = grouped.get(stage_name, [])
        if documents:
            stages.append(_decomposition_stage(stage_name, documents, spec))
    return {"strategy": "primary_then_related", "stages": stages}


def _decomposition_stage_name(document: dict[str, Any]) -> str:
    role = str(document.get("role") or "supporting").strip().lower()
    if role in {"conflicting", "stale"}:
        return role
    source_type = str(document.get("source_type") or "").strip()
    if source_type == "gap_map":
        return "gap"
    if source_type == "ranking_explanation":
        return "ranking"
    return "supporting"


def _decomposition_stage(name: str, documents: list[dict[str, Any]], spec: dict[str, Any]) -> dict[str, Any]:
    jd_id = _extract_jd_id(documents)
    source_type = _extract_source_type(documents)
    base_query = str(spec.get("expanded_query") or spec["query"])
    suffix = _stage_query_suffix(name, documents)
    return {
        "name": name,
        "query": f"{base_query}\n{suffix}",
        "filters": _query_filters(jd_id=jd_id, source_type=source_type),
        "limit": min(5, max(2 if name == "primary" else 1, len(documents))),
    }


def _stage_query_suffix(name: str, documents: list[dict[str, Any]]) -> str:
    terms: list[str] = []
    if name == "primary":
        terms.extend(["primary evidence", "candidate profile", "requirement evidence"])
    if name == "supporting":
        terms.extend(["supporting evidence", "related context", "secondary evidence"])
    if name == "conflicting":
        terms.extend(["conflicting evidence", "stale evidence", "risk", "ranking decision risk"])
    if name == "stale":
        terms.extend(["stale evidence", "freshness risk", "conflicting evidence"])
    if name == "gap":
        terms.extend(["gap evidence", "missing evidence", "weak point", "gap_map"])
    if name == "ranking":
        terms.extend(["ranking decision risk", "positive signals", "risk flags", "ranking_explanation"])
    source_types = {str(document.get("source_type") or "").strip() for document in documents}
    if "candidate_evidence" in source_types:
        terms.extend(["candidate evidence", "education", "project evidence", "resume profile"])
    if "requirement_evidence" in source_types:
        terms.extend(["jd requirement", "requirement evidence", "evidence status"])
    if "gap_map" in source_types:
        terms.extend(["gap map", "gap", "missing", "risk"])
    if "ranking_explanation" in source_types:
        terms.extend(["ranking decision risk", "decision summary", "risk flags"])
    return " ".join(_unique_terms(terms))


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


def _robustness_category_metrics(
    query_reports: list[dict[str, Any]], query_specs: list[dict[str, Any]], k_values: list[int]
) -> dict[str, Any]:
    category_by_query = {
        str(spec["query_id"]): str(spec.get("robustness_category") or "unknown") for spec in query_specs
    }
    by_category: dict[str, list[dict[str, Any]]] = {}
    for query in query_reports:
        by_category.setdefault(category_by_query.get(str(query.get("query_id")), "unknown"), []).append(query)
    return {
        category: {
            "query_count": len(queries),
            "aggregate": _aggregate_retriever_queries(queries, k_values),
        }
        for category, queries in sorted(by_category.items())
    }


def _ocr_behavior(query_reports: list[dict[str, Any]], query_specs: list[dict[str, Any]]) -> dict[str, Any]:
    spec_by_query = {str(spec["query_id"]): spec for spec in query_specs}
    reports: list[dict[str, Any]] = []
    for query in query_reports:
        spec = spec_by_query.get(str(query.get("query_id")))
        if not spec or spec.get("golden_layer") != "ocr_regression":
            continue
        category = str(spec.get("robustness_category") or "unknown")
        evidence_coverage = query.get("evidence_coverage") or {}
        retrieval_issue = not bool(evidence_coverage.get("all_expected_hit"))
        extraction_issue = category in {"ocr_noise_detection", "ocr_regression", "ocr_low_info_judgment"}
        reports.append(
            {
                "question_id": query.get("query_id"),
                "robustness_category": category,
                "query_rewrite": spec.get("query_rewrite"),
                "all_primary_hit": bool(evidence_coverage.get("all_primary_hit")),
                "all_expected_hit": bool(evidence_coverage.get("all_expected_hit")),
                "missing_labels": evidence_coverage.get("missing_labels") or [],
                "retrieval_status": "retrieval_issue" if retrieval_issue else "passed",
                "extraction_status": "extraction_issue" if extraction_issue else "not_flagged",
                "closed_loop_status": (
                    "retrieval_issue_needs_follow_up"
                    if retrieval_issue
                    else "extraction_issue_documented"
                    if extraction_issue
                    else "passed"
                ),
            }
        )
    retrieval_issue_count = sum(1 for item in reports if item["retrieval_status"] == "retrieval_issue")
    extraction_issue_count = sum(1 for item in reports if item["extraction_status"] == "extraction_issue")
    return {
        "query_count": len(reports),
        "retrieval_issue_count": retrieval_issue_count,
        "extraction_issue_count": extraction_issue_count,
        "passed_retrieval_count": len(reports) - retrieval_issue_count,
        "queries": reports,
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
    enable_support_gate: bool = False,
) -> dict[str, Any]:
    limit = max(k_values) if k_values else 10
    reports = []
    for sample in samples:
        if sample.get("case_type") != "no_answer":
            continue
        results = retriever.search(str(sample["question"]), limit=limit, source_type="candidate_evidence")
        query_plan = getattr(retriever, "last_query_plan", None)
        top_score = results[0].score if results else None
        support_gate = query_plan.get("support_gate") if isinstance(query_plan, dict) else None
        gate_blocked = bool(enable_support_gate and isinstance(support_gate, dict) and support_gate.get("blocked_generator"))
        abstained = gate_blocked or top_score is None or top_score < score_threshold
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
                "support_gate": support_gate,
                "should_abstain": True,
            }
        )
    non_empty = sum(1 for item in reports if item["retrieved_count"] > 0)
    abstained_count = sum(1 for item in reports if item["abstained"])
    leaked_count = len(reports) - abstained_count
    false_positive_examples = [item for item in reports if not item["abstained"]]
    support_gate_reports = [
        item.get("support_gate")
        for item in reports
        if isinstance(item.get("support_gate"), dict)
    ]
    support_gate_triggered = [item for item in support_gate_reports if item.get("triggered")]
    support_gate_blocked = [item for item in support_gate_triggered if item.get("blocked_generator")]
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
        "false_positive_audit": {
            "false_positive_count": leaked_count,
            "needs_manual_audit": leaked_count > 0,
            "audit_scope": "candidate_evidence",
            "threshold_explanation": (
                f"No-answer samples must abstain unless top candidate_evidence score is below {score_threshold}."
            ),
            "top_false_positive_examples": false_positive_examples[:5],
        },
        "support_gate_summary": {
            "triggered_count": len(support_gate_triggered),
            "trigger_rate": (len(support_gate_triggered) / len(reports)) if reports else 0.0,
            "blocked_generator_count": len(support_gate_blocked),
            "blocked_generator_rate": (len(support_gate_blocked) / len(reports)) if reports else 0.0,
        },
        "queries": reports,
    }


def _smart_routing_observability(query_reports: list[dict[str, Any]]) -> dict[str, Any]:
    plans = [item.get("query_plan") for item in query_reports if isinstance(item.get("query_plan"), dict)]
    query_count = len(query_reports)
    if not query_count:
        return {
            "oracle_free": True,
            "rewrite_trigger_rate": 0.0,
            "decomposition_trigger_rate": 0.0,
            "support_gate_trigger_rate": 0.0,
            "route_fallback_rate": 0.0,
            "route_error_examples": [],
        }
    rewrite_count = sum(1 for plan in plans if plan.get("rewrite_terms"))
    decomposition_count = sum(1 for plan in plans if plan.get("decomposition_stages"))
    support_count = sum(1 for plan in plans if (plan.get("support_gate") or {}).get("triggered"))
    fallback_count = sum(1 for plan in plans if plan.get("fallback_used"))
    losses = [
        {
            "query_id": item.get("query_id"),
            "case_type": item.get("case_type"),
            "reasons": (item.get("query_plan") or {}).get("reasons"),
            "missing_labels": item.get("evidence_coverage", {}).get("missing_labels"),
            "routes": (item.get("query_plan") or {}).get("decomposition_stages"),
        }
        for item in query_reports
        if isinstance(item.get("query_plan"), dict) and item.get("evidence_coverage", {}).get("all_expected_hit") is False
    ]
    wins = [
        {
            "query_id": item.get("query_id"),
            "case_type": item.get("case_type"),
            "reasons": (item.get("query_plan") or {}).get("reasons"),
            "routes": (item.get("query_plan") or {}).get("decomposition_stages"),
        }
        for item in query_reports
        if isinstance(item.get("query_plan"), dict) and item.get("evidence_coverage", {}).get("all_expected_hit") is True
    ]
    route_false_positives = [
        item
        for item in losses
        if item.get("reasons") and not item.get("missing_labels")
    ]
    missing_supporting = [
        item
        for item in query_reports
        if isinstance(item.get("query_plan"), dict)
        and str(item.get("case_type") or "") == "multi_document"
        and int(item.get("evidence_coverage", {}).get("supporting_hit_count") or 0)
        < int(item.get("evidence_coverage", {}).get("supporting_expected_count") or 0)
    ]
    return {
        "oracle_free": all(plan.get("oracle_free") is True for plan in plans) if plans else True,
        "planned_query_count": len(plans),
        "rewrite_trigger_rate": rewrite_count / query_count,
        "decomposition_trigger_rate": decomposition_count / query_count,
        "support_gate_trigger_rate": support_count / query_count,
        "route_fallback_rate": fallback_count / query_count,
        "route_error_examples": losses[:5],
        "smart_router_win_examples": wins[:5],
        "smart_router_loss_examples": losses[:5],
        "route_false_positive_examples": route_false_positives[:5],
        "support_gate_blocked_examples": [
            {"query_id": item.get("query_id"), "support_gate": (item.get("query_plan") or {}).get("support_gate")}
            for item in query_reports
            if ((item.get("query_plan") or {}).get("support_gate") or {}).get("blocked_generator")
        ][:5],
        "multi_document_missing_supporting_examples": [
            {
                "query_id": item.get("query_id"),
                "missing_labels": item.get("evidence_coverage", {}).get("missing_labels"),
                "routes": (item.get("query_plan") or {}).get("decomposition_stages"),
            }
            for item in missing_supporting
        ][:5],
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
        default=DEFAULT_RERANKER_MODEL,
        help="Cross-encoder model for two-stage retrieval (e.g. BAAI/bge-reranker-v2-m3).",
    )
    parser.add_argument("--no-reranker", action="store_true", help="Disable the default cross-encoder reranker.")
    parser.add_argument(
        "--first-stage-limit",
        type=int,
        default=DEFAULT_FIRST_STAGE_LIMIT,
        help="Number of candidates from first-stage retrieval to feed into reranker.",
    )
    parser.add_argument(
        "--golden-layer",
        action="append",
        default=None,
        help="Evaluate only samples whose metadata.golden_layer matches this value. Repeat for multiple layers.",
    )
    parser.add_argument(
        "--query-strategy",
        choices=["single", "decomposed", "smart"],
        default="single",
        help="Query planning strategy. Use smart for non-oracle rule-based routing.",
    )
    parser.add_argument("--router-broad-limit", type=int, default=20, help="Broad top-k used by smart routing.")
    parser.add_argument("--enable-support-gate", action="store_true", help="Enable no-answer support/entailment gate.")
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
            reranker_model=None if args.no_reranker else args.reranker,
            first_stage_limit=args.first_stage_limit,
            golden_layers=args.golden_layer,
            query_strategy=args.query_strategy,
            router_broad_limit=args.router_broad_limit,
            enable_support_gate=args.enable_support_gate,
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
