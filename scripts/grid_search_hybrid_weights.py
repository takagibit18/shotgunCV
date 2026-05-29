"""Grid search for hybrid retriever vector_weight / bm25_weight.

Precomputes vector and BM25 results once, then evaluates every weight
combination offline — avoids recomputing embeddings for each grid point.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "cli" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "py-core" / "src"))

from scripts.evaluate_rag_layers import _label_coverage, _load_valid_golden, _quality_gate, _samples, _sample_to_query_spec  # noqa: E402
from shotguncv_core.db.indexer import build_projection_batch  # noqa: E402
from shotguncv_core.rag.retrieval import InMemoryBM25Retriever, InMemoryVectorRetriever, RetrievalResult  # noqa: E402


Key = tuple[str, str, str, str]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Grid search hybrid retriever weights.")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--golden-file", type=Path, default=ROOT / "fixtures" / "golden_rag_questions.json")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "grid_search_hybrid_weights.json")
    parser.add_argument("--step", type=float, default=0.05)
    parser.add_argument("--k", type=int, action="append", default=[1, 3, 5, 10])
    return parser.parse_args()


def _result_key(result: RetrievalResult) -> Key:
    return (
        str(result.metadata.get("source_type") or ""),
        str(result.metadata.get("source_id") or ""),
        str(result.metadata.get("chunk_index") or ""),
        str(result.metadata.get("artifact_path") or ""),
    )


def _ranked_label_for_result(result: RetrievalResult, expected: list[str]) -> str:
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


def _mrr(ranked_ids: list[str], relevant: set[str]) -> float:
    for index, item in enumerate(ranked_ids, start=1):
        if item in relevant:
            return 1.0 / index
    return 0.0


def _precision_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    return len({item for item in ranked_ids[:k] if item in relevant}) / k


def _recall_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len({item for item in ranked_ids[:k] if item in relevant}) / len(relevant)


def _ndcg_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    if not relevant or k <= 0:
        return 0.0
    seen: set[str] = set()
    dcg = 0.0
    for index, item in enumerate(ranked_ids[:k], start=1):
        if item not in relevant or item in seen:
            continue
        seen.add(item)
        dcg += 1.0 / math.log2(index + 1)
    ideal_hits = min(len(relevant), k)
    ideal_dcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    return dcg / ideal_dcg if ideal_dcg else 0.0


def _evaluate_weights(
    precomputed: list[dict[str, Any]],
    vector_weight: float,
    bm25_weight: float,
    *,
    search_limit: int = 10,
) -> dict[str, float]:
    query_metrics: list[dict[str, float]] = []
    for pq in precomputed:
        vector_scores: dict[Key, float] = pq["vector_scores"]
        bm25_scores: dict[Key, float] = pq["bm25_scores"]
        all_keys: list[Key] = pq["keys"]
        key_to_label: dict[Key, str] = pq["key_to_label"]
        relevant: set[str] = pq["relevant"]

        scored = [
            (k, vector_weight * vector_scores.get(k, 0.0) + bm25_weight * bm25_scores.get(k, 0.0))
            for k in all_keys
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        # Truncate to match evaluate_labeled_retrieval_queries behaviour
        ranked_ids = [key_to_label[k] for k, _ in scored[:search_limit]]

        query_metrics.append({
            "mrr": _mrr(ranked_ids, relevant),
            "precision_at_1": _precision_at_k(ranked_ids, relevant, 1),
            "recall_at_10": _recall_at_k(ranked_ids, relevant, 10),
            "ndcg_at_10": _ndcg_at_k(ranked_ids, relevant, 10),
        })

    n = len(query_metrics)
    return {
        "mrr": sum(m["mrr"] for m in query_metrics) / n if n else 0.0,
        "precision_at_1": sum(m["precision_at_1"] for m in query_metrics) / n if n else 0.0,
        "recall_at_10": sum(m["recall_at_10"] for m in query_metrics) / n if n else 0.0,
        "ndcg_at_10": sum(m["ndcg_at_10"] for m in query_metrics) / n if n else 0.0,
    }


def main() -> int:
    args = _parse_args()

    # --- Load golden and build projection batch (once) ---
    payload = _load_valid_golden(args.golden_file)
    samples = _samples(payload)
    batch = build_projection_batch(args.run_dir)
    chunks = batch.retrieval_chunks

    # Build base retrievers once
    print("Building vector retriever and computing embeddings...")
    vector_retriever = InMemoryVectorRetriever.from_chunks(chunks)
    print("Building BM25 retriever...")
    bm25_retriever = InMemoryBM25Retriever.from_chunks(chunks)

    # --- Extract query specs ---
    query_specs = [_sample_to_query_spec(sample) for sample in samples if sample.get("case_type") != "no_answer"]
    coverage = _label_coverage(chunks, query_specs)
    quality_gate = _quality_gate(coverage)
    if quality_gate["status"] != "passed":
        print(f"ERROR: Label coverage gate failed: {coverage['matched_label_count']}/{coverage['expected_label_count']}")
        return 1
    print(f"Label coverage gate passed: {coverage['matched_label_count']}/{coverage['expected_label_count']}")

    # --- Precompute per-query vector and BM25 results ---
    precomputed: list[dict[str, Any]] = []
    chunk_count = len(chunks)
    for spec in query_specs:
        query = str(spec["query"])
        expected = [str(item) for item in spec.get("expected_chunks", []) if str(item).strip()]
        search_kwargs: dict[str, Any] = {"limit": chunk_count}
        for filter_key in ("candidate_id", "jd_id", "source_type"):
            value = spec.get(filter_key)
            if value:
                search_kwargs[filter_key] = value

        vector_results = vector_retriever.search(query, **search_kwargs)
        bm25_results = bm25_retriever.search(query, **search_kwargs)

        vector_scores: dict[Key, float] = {_result_key(r): max(0.0, min(1.0, r.score)) for r in vector_results}
        bm25_scores: dict[Key, float] = {_result_key(r): max(0.0, r.score) / (max(0.0, r.score) + 1.0) for r in bm25_results}

        all_keys = list({**vector_scores, **bm25_scores}.keys())
        key_to_result: dict[Key, RetrievalResult] = {}
        for r in vector_results + bm25_results:
            k = _result_key(r)
            if k not in key_to_result:
                key_to_result[k] = r

        precomputed.append({
            "query_id": spec.get("query_id"),
            "query": query,
            "relevant": set(expected),
            "vector_scores": vector_scores,
            "bm25_scores": bm25_scores,
            "keys": all_keys,
            "key_to_label": {k: _ranked_label_for_result(key_to_result[k], expected) for k in all_keys},
        })

    print(f"Precomputed results for {len(precomputed)} queries.")

    # --- Grid search over weights ---
    step = args.step
    max_k = max(args.k) if args.k else 10
    weight_values = [round(i * step, 3) for i in range(0, int(1.0 / step) + 1)]
    results: list[dict[str, Any]] = []
    total = len(weight_values) ** 2 - 1  # exclude (0, 0)
    count = 0

    for vw in weight_values:
        for bw in weight_values:
            if vw == 0.0 and bw == 0.0:
                continue
            count += 1
            total_weight = vw + bw
            nvw = vw / total_weight
            nbw = bw / total_weight

            metrics = _evaluate_weights(precomputed, nvw, nbw, search_limit=max_k)
            results.append({
                "vector_weight": nvw,
                "bm25_weight": nbw,
                **metrics,
            })

            if count % 20 == 0 or count == 1 or count == total:
                print(f"[{count}/{total}] vector={nvw:.3f} bm25={nbw:.3f}  MRR={metrics['mrr']:.4f}  P@1={metrics['precision_at_1']:.4f}")

    results.sort(key=lambda r: r["mrr"], reverse=True)

    # --- Output ---
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({
        "config": {
            "run_dir": str(args.run_dir),
            "golden_file": str(args.golden_file),
            "step": step,
        },
        "total_combinations": len(results),
        "best_mrr": results[0]["mrr"] if results else 0.0,
        "baseline_bm25_mrr": 0.333,
        "baseline_hybrid_mrr": 0.312,
        "top_10": results[:10],
        "all_results": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== Top 10 Combinations ===")
    print(f"{'Rank':<6}{'vector_w':<12}{'bm25_w':<12}{'MRR':<10}{'P@1':<10}{'R@10':<10}{'nDCG@10':<10}")
    print("-" * 68)
    for i, entry in enumerate(results[:10], start=1):
        print(
            f"{i:<6}{entry['vector_weight']:<12.3f}{entry['bm25_weight']:<12.3f}"
            f"{entry['mrr']:<10.4f}{entry['precision_at_1']:<10.4f}"
            f"{entry['recall_at_10']:<10.4f}{entry['ndcg_at_10']:<10.4f}"
        )

    print(f"\nFull results → {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
