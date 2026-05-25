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
from shotguncv_core.rag.metrics import evaluate_labeled_retrieval_queries  # noqa: E402
from shotguncv_core.rag.retrieval import InMemoryVectorRetriever  # noqa: E402


def evaluate_run_dir(
    *,
    run_dir: Path,
    golden_file: Path,
    output_path: Path,
    k_values: list[int],
) -> dict[str, Any]:
    batch = build_projection_batch(run_dir)
    retriever = InMemoryVectorRetriever.from_chunks(batch.retrieval_chunks)
    golden_schema_version, query_specs = _load_golden_query_specs(golden_file)
    metrics = evaluate_labeled_retrieval_queries(
        retriever=retriever,
        query_specs=query_specs,
        k_values=k_values,
    )
    report = {
        "schema_version": "retriever-metrics-v1",
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "golden_file": str(golden_file),
        "golden_schema_version": golden_schema_version,
        "retriever_type": "InMemoryVectorRetriever",
        "chunk_count": len(batch.retrieval_chunks),
        "label_coverage": _label_coverage(batch.retrieval_chunks, query_specs),
        "label_inventory": _label_inventory(batch.retrieval_chunks),
        "metrics": metrics,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _load_golden_query_specs(golden_file: Path) -> tuple[str, list[dict[str, Any]]]:
    payload = json.loads(golden_file.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return "legacy-list", _validate_query_specs(payload, golden_file)
    if not isinstance(payload, dict):
        raise ValueError(f"Golden retriever file must be a JSON object or list: {golden_file}")
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
        expected_chunks = spec.get("expected_chunks")
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
    missing = [label for label in expected if not any(_chunk_matches_label(chunk, label) for chunk in chunks)]
    return {
        "expected_label_count": len(expected),
        "matched_label_count": len(expected) - len(missing),
        "missing_expected_chunks": missing,
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
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--golden-file", type=Path, default=ROOT / "fixtures" / "golden_retrieval_questions.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--k", type=int, action="append", default=[1, 3, 5, 10])
    args = parser.parse_args()
    report = evaluate_run_dir(
        run_dir=args.run_dir,
        golden_file=args.golden_file,
        output_path=args.output,
        k_values=args.k,
    )
    print(json.dumps({"output": str(args.output), "aggregate": report["metrics"]["aggregate"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
