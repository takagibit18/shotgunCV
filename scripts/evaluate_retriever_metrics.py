from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "cli" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "py-core" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "py-agents" / "src"))

from shotguncv_core.db.indexer import build_projection_batch  # noqa: E402
from shotguncv_core.rag.embeddings import EmbeddingModel  # noqa: E402
from shotguncv_core.rag.metrics import evaluate_labeled_retrieval_queries, evaluate_ranked_retrieval  # noqa: E402
from shotguncv_core.rag.retrieval import InMemoryVectorRetriever  # noqa: E402


def evaluate_run_dir(
    *,
    run_dir: Path,
    golden_file: Path,
    output_path: Path,
    k_values: list[int],
    embedding_model: EmbeddingModel | None = None,
    query_specs: list[dict[str, Any]] | None = None,
    fail_on_incomplete_coverage: bool = True,
    run_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    batch = build_projection_batch(run_dir)
    retriever = InMemoryVectorRetriever.from_chunks(batch.retrieval_chunks, embedding_model=embedding_model)
    golden_schema_version, loaded_query_specs = _load_golden_query_specs(golden_file)
    selected_query_specs = query_specs if query_specs is not None else loaded_query_specs
    coverage = _label_coverage(batch.retrieval_chunks, selected_query_specs)
    quality_gate = _quality_gate(coverage)
    if fail_on_incomplete_coverage and quality_gate["status"] != "passed":
        raise ValueError(
            "Label coverage gate failed: "
            f"{coverage['matched_label_count']}/{coverage['expected_label_count']} labels matched; "
            f"missing={coverage['missing_expected_chunks']}"
        )
    metrics = evaluate_labeled_retrieval_queries(
        retriever=retriever,
        query_specs=selected_query_specs,
        k_values=k_values,
    )
    report = {
        "schema_version": "retriever-metrics-v1",
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "run_metadata": run_metadata or {},
        "golden_file": str(golden_file),
        "golden_schema_version": golden_schema_version,
        "retriever_type": "InMemoryVectorRetriever",
        "chunk_count": len(batch.retrieval_chunks),
        "label_coverage": coverage,
        "quality_gate": quality_gate,
        "label_inventory": _label_inventory(batch.retrieval_chunks),
        "metrics": metrics,
        "source_type_metrics": _source_type_metrics(metrics["queries"], coverage, k_values),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def evaluate_baseline_runs(
    *,
    runs_root: Path,
    baseline_runs_file: Path,
    golden_file: Path,
    output_root: Path,
    k_values: list[int],
    embedding_model: EmbeddingModel | None = None,
) -> dict[str, Any]:
    run_entries = _load_baseline_run_entries(baseline_runs_file)
    _, all_query_specs = _load_golden_query_specs(golden_file)
    run_reports: list[dict[str, Any]] = []
    skipped_queries_by_run: dict[str, list[dict[str, Any]]] = {}
    for entry in run_entries:
        run_id = str(entry["run_id"])
        run_dir = runs_root / run_id
        batch = build_projection_batch(run_dir)
        applicable, skipped = _applicable_query_specs(
            batch.retrieval_chunks,
            all_query_specs,
            bucket=str(entry.get("bucket") or ""),
        )
        skipped_queries_by_run[run_id] = skipped
        report = evaluate_run_dir(
            run_dir=run_dir,
            golden_file=golden_file,
            output_path=output_root / "runs" / f"{run_id}.json",
            k_values=k_values,
            embedding_model=embedding_model,
            query_specs=applicable,
            fail_on_incomplete_coverage=True,
            run_metadata=entry,
        )
        report["skipped_queries"] = skipped
        report["applicable_query_count"] = len(applicable)
        (output_root / "runs" / f"{run_id}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        run_reports.append(report)
    bucket_reports = _bucket_reports(run_reports, k_values)
    aggregate = _aggregate_reports(run_reports, k_values)
    quality_gate = _baseline_quality_gate(run_reports)
    report = {
        "schema_version": "retriever-baseline-metrics-v1",
        "runs_root": str(runs_root),
        "baseline_runs_file": str(baseline_runs_file),
        "golden_file": str(golden_file),
        "run_count": len(run_reports),
        "bucket_count": len(bucket_reports),
        "quality_gate": quality_gate,
        "metrics": aggregate,
        "source_type_metrics": _aggregate_source_type_reports(run_reports, k_values),
        "buckets": bucket_reports,
        "runs": [
            {
                "run_id": report["run_id"],
                "bucket": report.get("run_metadata", {}).get("bucket"),
                "repeat": report.get("run_metadata", {}).get("repeat"),
                "chunk_count": report["chunk_count"],
                "applicable_query_count": report.get("applicable_query_count", report["metrics"]["query_count"]),
                "skipped_query_count": len(skipped_queries_by_run.get(report["run_id"], [])),
                "quality_gate": report["quality_gate"],
                "output": str(output_root / "runs" / f"{report['run_id']}.json"),
            }
            for report in run_reports
        ],
    }
    for bucket, bucket_report in bucket_reports.items():
        bucket_path = output_root / "buckets" / f"{bucket}.json"
        bucket_path.parent.mkdir(parents=True, exist_ok=True)
        bucket_path.write_text(json.dumps(bucket_report, ensure_ascii=False, indent=2), encoding="utf-8")
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "aggregate.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _load_golden_query_specs(golden_file: Path) -> tuple[str, list[dict[str, Any]]]:
    payload = json.loads(golden_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Golden retriever file must be a retriever-golden-v1 JSON object: {golden_file}")
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "retriever-golden-v1":
        raise ValueError(f"Unsupported golden retriever schema_version: {schema_version or '<missing>'}")
    queries = payload.get("queries")
    if not isinstance(queries, list):
        raise ValueError("Golden retriever schema retriever-golden-v1 requires a queries list.")
    return schema_version, _validate_query_specs(queries, golden_file)


def _validate_query_specs(query_specs: list[Any], golden_file: Path) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    for index, spec in enumerate(query_specs):
        if not isinstance(spec, dict):
            raise ValueError(f"Golden retriever query #{index + 1} must be an object: {golden_file}")
        query = spec.get("query")
        query_id = spec.get("query_id")
        expected_chunks = spec.get("expected_chunks")
        if not isinstance(query_id, str) or not query_id.strip():
            raise ValueError(f"Golden retriever query #{index + 1} requires a non-empty query_id.")
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"Golden retriever query #{index + 1} requires a non-empty query string.")
        if not isinstance(expected_chunks, list) or not all(isinstance(item, str) and item.strip() for item in expected_chunks):
            raise ValueError(f"Golden retriever query #{index + 1} requires non-empty expected_chunks.")
        validated.append(spec)
    return validated


def _label_coverage(chunks: list[dict[str, Any]], query_specs: list[dict[str, Any]]) -> dict[str, Any]:
    expected = sorted(
        {
            str(label)
            for spec in query_specs
            for label in spec.get("expected_chunks", [])
            if str(label).strip()
        }
    )
    matched_labels = [_matched_label_summary(chunks, label) for label in expected if any(_chunk_matches_label(chunk, label) for chunk in chunks)]
    missing = [label for label in expected if not any(item["label"] == label for item in matched_labels)]
    coverage_ratio = (len(expected) - len(missing)) / len(expected) if expected else 1.0
    return {
        "expected_label_count": len(expected),
        "matched_label_count": len(expected) - len(missing),
        "coverage_ratio": coverage_ratio,
        "missing_expected_chunks": missing,
        "matched_labels": matched_labels,
    }


def _chunk_matches_label(chunk: dict[str, Any], label: str) -> bool:
    metadata = chunk.get("metadata") or {}
    haystack = "\n".join(
        [
            str(metadata.get("source_id") or ""),
            str(metadata.get("artifact_path") or ""),
            str(metadata.get("provenance_summary") or ""),
            str(chunk.get("text") or ""),
        ]
    ).lower()
    return label.lower() in haystack


def _matched_label_summary(chunks: list[dict[str, Any]], label: str) -> dict[str, Any]:
    matches = [chunk for chunk in chunks if _chunk_matches_label(chunk, label)]
    source_types = sorted({str((chunk.get("metadata") or {}).get("source_type") or "unknown") for chunk in matches})
    source_ids = sorted({str((chunk.get("metadata") or {}).get("source_id") or "") for chunk in matches})
    return {"label": label, "source_types": source_types, "source_ids": source_ids[:10]}


def _quality_gate(coverage: dict[str, Any]) -> dict[str, Any]:
    status = "passed" if float(coverage.get("coverage_ratio", 0.0)) == 1.0 else "failed"
    return {
        "status": status,
        "label_coverage_required": 1.0,
        "label_coverage_actual": coverage.get("coverage_ratio", 0.0),
        "blocks_metric_interpretation": status != "passed",
    }


def _source_type_metrics(query_reports: list[dict[str, Any]], coverage: dict[str, Any], k_values: list[int]) -> dict[str, Any]:
    label_to_source_types: dict[str, list[str]] = {
        str(item["label"]): [str(source_type) for source_type in item.get("source_types", [])]
        for item in coverage.get("matched_labels", [])
    }
    source_types = sorted({source_type for values in label_to_source_types.values() for source_type in values})
    reports: dict[str, Any] = {}
    for source_type in source_types:
        per_query = []
        expected_label_count = 0
        for query in query_reports:
            relevant = [
                label
                for label in query.get("expected_chunks", [])
                if source_type in label_to_source_types.get(str(label), [])
            ]
            if not relevant:
                continue
            expected_label_count += len(relevant)
            metrics = evaluate_ranked_retrieval(
                ranked_ids=query.get("ranked_ids", []),
                relevant_ids=set(relevant),
                k_values=k_values,
            )
            per_query.append(
                {
                    "query_id": query.get("query_id"),
                    "jd_id": query.get("jd_id"),
                    "expected_chunks": relevant,
                    "metrics": metrics,
                }
            )
        reports[source_type] = {
            "query_count": len(per_query),
            "expected_label_count": expected_label_count,
            "aggregate": _aggregate_query_metrics(per_query, k_values),
            "queries": per_query,
        }
    return reports


def _aggregate_query_metrics(query_reports: list[dict[str, Any]], k_values: list[int]) -> dict[str, Any]:
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


def _load_baseline_run_entries(baseline_runs_file: Path) -> list[dict[str, Any]]:
    payload = json.loads(baseline_runs_file.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Baseline runs file must be a JSON list.")
    entries = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict) or not str(item.get("run_id") or "").strip():
            raise ValueError(f"Baseline run entry #{index + 1} requires run_id.")
        entries.append(item)
    return entries


def _applicable_query_specs(
    chunks: list[dict[str, Any]], query_specs: list[dict[str, Any]], *, bucket: str | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    applicable = []
    skipped = []
    for spec in query_specs:
        applicable_buckets = spec.get("applicable_buckets")
        if bucket and isinstance(applicable_buckets, list) and bucket not in {str(item) for item in applicable_buckets}:
            skipped.append({"query_id": spec.get("query_id"), "reason": "bucket_not_applicable"})
            continue
        missing = [
            label
            for label in spec.get("expected_chunks", [])
            if not any(_chunk_matches_label(chunk, str(label)) for chunk in chunks)
        ]
        if missing:
            skipped.append({"query_id": spec.get("query_id"), "missing_expected_chunks": missing})
            continue
        applicable.append(spec)
    return applicable, skipped


def _bucket_reports(run_reports: list[dict[str, Any]], k_values: list[int]) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for report in run_reports:
        bucket = str(report.get("run_metadata", {}).get("bucket") or "unknown")
        buckets.setdefault(bucket, []).append(report)
    return {
        bucket: {
            "bucket": bucket,
            "run_count": len(reports),
            "run_ids": [report["run_id"] for report in reports],
            "quality_gate": _baseline_quality_gate(reports),
            "metrics": _aggregate_reports(reports, k_values),
            "source_type_metrics": _aggregate_source_type_reports(reports, k_values),
        }
        for bucket, reports in sorted(buckets.items())
    }


def _aggregate_reports(run_reports: list[dict[str, Any]], k_values: list[int]) -> dict[str, Any]:
    queries = [query for report in run_reports for query in report.get("metrics", {}).get("queries", [])]
    return {
        "query_count": len(queries),
        "k_values": sorted({int(k) for k in k_values}),
        "aggregate": _aggregate_query_metrics(queries, sorted({int(k) for k in k_values})),
    }


def _aggregate_source_type_reports(run_reports: list[dict[str, Any]], k_values: list[int]) -> dict[str, Any]:
    by_source_type: dict[str, list[dict[str, Any]]] = {}
    expected_counts: dict[str, int] = {}
    for report in run_reports:
        for source_type, source_report in report.get("source_type_metrics", {}).items():
            by_source_type.setdefault(source_type, []).extend(source_report.get("queries", []))
            expected_counts[source_type] = expected_counts.get(source_type, 0) + int(source_report.get("expected_label_count", 0))
    return {
        source_type: {
            "query_count": len(queries),
            "expected_label_count": expected_counts.get(source_type, 0),
            "aggregate": _aggregate_query_metrics(queries, k_values),
        }
        for source_type, queries in sorted(by_source_type.items())
    }


def _baseline_quality_gate(run_reports: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [report["run_id"] for report in run_reports if report.get("quality_gate", {}).get("status") != "passed"]
    return {
        "status": "failed" if failed else "passed",
        "failed_run_ids": failed,
        "label_coverage_required": 1.0,
        "blocks_metric_interpretation": bool(failed),
    }


def _label_inventory(chunks: list[dict[str, Any]], *, limit: int = 200) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        key = (
            str(metadata.get("source_type") or ""),
            str(metadata.get("source_id") or ""),
            str(metadata.get("artifact_path") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        inventory.append(
            {
                "source_type": key[0],
                "source_id": key[1],
                "artifact_path": key[2],
                "provenance_summary": metadata.get("provenance_summary"),
            }
        )
        if len(inventory) >= limit:
            break
    return inventory


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate retriever quality with precision@k, recall@k, MRR, and NDCG.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--run-dir", type=Path)
    target.add_argument("--runs-root", type=Path)
    parser.add_argument("--baseline-runs-file", type=Path)
    parser.add_argument("--golden-file", type=Path, default=ROOT / "fixtures" / "golden_retrieval_questions.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--k", type=int, action="append", default=[1, 3, 5, 10])
    args = parser.parse_args()
    if args.runs_root:
        if not args.baseline_runs_file:
            parser.error("--runs-root requires --baseline-runs-file")
        report = evaluate_baseline_runs(
            runs_root=args.runs_root,
            baseline_runs_file=args.baseline_runs_file,
            golden_file=args.golden_file,
            output_root=args.output,
            k_values=args.k,
        )
        output = args.output / "aggregate.json"
        aggregate = report["metrics"]["aggregate"]
    else:
        report = evaluate_run_dir(
            run_dir=args.run_dir,
            golden_file=args.golden_file,
            output_path=args.output,
            k_values=args.k,
        )
        output = args.output
        aggregate = report["metrics"]["aggregate"]
    print(json.dumps({"output": str(output), "aggregate": aggregate}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
