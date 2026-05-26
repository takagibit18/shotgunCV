from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate_retriever_metrics import evaluate_baseline_runs, evaluate_run_dir


class KeywordEmbeddingModel:
    def embed(self, text: str) -> list[float]:
        normalized = text.lower()
        if "requirement" in normalized:
            return [0.0, 1.0, 0.0]
        if "python" in normalized or "candidate" in normalized:
            return [1.0, 0.0, 0.0]
        return [0.0, 0.0, 1.0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


def test_evaluate_run_dir_writes_retriever_metric_report(tmp_path: Path) -> None:
    run_dir = tmp_path / "completed-run"
    _write_json(run_dir / "ingest" / "manifest.json", {"candidate_id": "cand-001", "jd_inputs": []})
    _write_json(
        run_dir / "analyze" / "candidate_profile.json",
        {
            "candidate_id": "cand-001",
            "experiences": ["Built Python LangGraph RAG review pipeline evidence."],
        },
    )
    _write_json(run_dir / "analyze" / "jd_profiles.json", [])
    _write_json(run_dir / "analyze" / "requirement_matrix.json", [])
    golden_path = tmp_path / "golden.json"
    _write_json(golden_path, _golden_payload([{"query": "Python LangGraph RAG pipeline", "expected_chunks": ["candidate-profile"]}]))
    output_path = tmp_path / "report.json"

    report = evaluate_run_dir(
        run_dir=run_dir,
        golden_file=golden_path,
        output_path=output_path,
        k_values=[1, 3],
        embedding_model=KeywordEmbeddingModel(),
    )

    assert output_path.exists()
    assert report["run_id"] == "completed-run"
    assert report["chunk_count"] == 1
    assert report["label_coverage"]["expected_label_count"] == 1
    assert report["label_coverage"]["matched_label_count"] == 1
    assert report["label_coverage"]["coverage_ratio"] == 1.0
    assert report["quality_gate"]["status"] == "passed"
    assert report["label_coverage"]["missing_expected_chunks"] == []
    assert report["label_inventory"][0]["source_id"] == "cand-001:candidate-profile"
    assert report["metrics"]["query_count"] == 1
    assert report["metrics"]["aggregate"]["recall_at_k"]["3"] == 1.0
    assert report["source_type_metrics"]["candidate_evidence"]["aggregate"]["recall_at_k"]["3"] == 1.0


def test_evaluate_run_dir_accepts_versioned_golden_schema(tmp_path: Path) -> None:
    run_dir = tmp_path / "completed-run"
    _write_json(run_dir / "ingest" / "manifest.json", {"candidate_id": "cand-001", "jd_inputs": []})
    _write_json(
        run_dir / "analyze" / "candidate_profile.json",
        {
            "candidate_id": "cand-001",
            "experiences": ["Built Python LangGraph RAG review pipeline evidence."],
        },
    )
    _write_json(run_dir / "analyze" / "jd_profiles.json", [])
    _write_json(run_dir / "analyze" / "requirement_matrix.json", [])
    golden_path = tmp_path / "golden.json"
    _write_json(
        golden_path,
        {
            "schema_version": "retriever-golden-v1",
            "metrics": ["precision_at_k", "recall_at_k", "mrr", "ndcg_at_k"],
            "queries": [
                {
                    "query_id": "rag-pipeline",
                    "jd_id": "jd-001",
                    "query": "Python LangGraph RAG pipeline",
                    "expected_chunks": ["candidate-profile"],
                }
            ],
        },
    )
    output_path = tmp_path / "report.json"

    report = evaluate_run_dir(
        run_dir=run_dir,
        golden_file=golden_path,
        output_path=output_path,
        k_values=[1, 3],
        embedding_model=KeywordEmbeddingModel(),
    )

    assert report["golden_schema_version"] == "retriever-golden-v1"
    assert report["metrics"]["queries"][0]["query_id"] == "rag-pipeline"
    assert report["metrics"]["aggregate"]["mrr"] == 1.0


def test_evaluate_run_dir_rejects_legacy_golden_schema(tmp_path: Path) -> None:
    run_dir = tmp_path / "completed-run"
    _write_json(run_dir / "ingest" / "manifest.json", {"candidate_id": "cand-001", "jd_inputs": []})
    _write_json(run_dir / "analyze" / "candidate_profile.json", {"candidate_id": "cand-001", "experiences": ["Python"]})
    _write_json(run_dir / "analyze" / "jd_profiles.json", [])
    _write_json(run_dir / "analyze" / "requirement_matrix.json", [])
    golden_path = tmp_path / "legacy-golden.json"
    _write_json(golden_path, [{"query": "Python", "expected_chunks": ["candidate-profile"]}])

    try:
        evaluate_run_dir(
            run_dir=run_dir,
            golden_file=golden_path,
            output_path=tmp_path / "report.json",
            k_values=[1],
            embedding_model=KeywordEmbeddingModel(),
        )
    except ValueError as exc:
        assert "retriever-golden-v1" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("legacy golden schema should fail")


def test_evaluate_run_dir_fails_before_metrics_when_label_coverage_is_incomplete(tmp_path: Path) -> None:
    run_dir = tmp_path / "completed-run"
    _write_json(run_dir / "ingest" / "manifest.json", {"candidate_id": "cand-001", "jd_inputs": []})
    _write_json(run_dir / "analyze" / "candidate_profile.json", {"candidate_id": "cand-001", "experiences": ["Python"]})
    _write_json(run_dir / "analyze" / "jd_profiles.json", [])
    _write_json(run_dir / "analyze" / "requirement_matrix.json", [])
    golden_path = tmp_path / "golden.json"
    _write_json(golden_path, _golden_payload([{"query": "Python", "expected_chunks": ["missing-label"]}]))

    try:
        evaluate_run_dir(
            run_dir=run_dir,
            golden_file=golden_path,
            output_path=tmp_path / "report.json",
            k_values=[1],
            embedding_model=KeywordEmbeddingModel(),
        )
    except ValueError as exc:
        assert "Label coverage gate failed" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("missing golden labels should fail before metrics")


def test_evaluate_baseline_runs_groups_bucket_and_source_type_metrics(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    _write_completed_run(runs_root / "run-a", "cand-001", requirement_text="Requirement Python evidence")
    _write_completed_run(runs_root / "run-b", "cand-001", requirement_text="Requirement Python evidence")
    baseline_file = tmp_path / "baseline_runs.json"
    _write_json(
        baseline_file,
        [
            {"run_id": "run-a", "bucket": "bucket_alpha", "repeat": 1},
            {"run_id": "run-b", "bucket": "bucket_alpha", "repeat": 2},
        ],
    )
    golden_path = tmp_path / "golden.json"
    _write_json(
        golden_path,
        _golden_payload(
            [
                {"query_id": "candidate", "query": "Python candidate", "expected_chunks": ["candidate-profile"]},
                {"query_id": "requirement", "query": "Requirement evidence", "expected_chunks": ["jd-001-req-001"]},
            ]
        ),
    )
    output_root = tmp_path / "retriever-quality"

    report = evaluate_baseline_runs(
        runs_root=runs_root,
        baseline_runs_file=baseline_file,
        golden_file=golden_path,
        output_root=output_root,
        k_values=[1, 3],
        embedding_model=KeywordEmbeddingModel(),
    )

    assert report["schema_version"] == "retriever-baseline-metrics-v1"
    assert report["run_count"] == 2
    assert report["bucket_count"] == 1
    assert report["quality_gate"]["status"] == "passed"
    assert report["buckets"]["bucket_alpha"]["run_count"] == 2
    assert report["buckets"]["bucket_alpha"]["metrics"]["query_count"] == 4
    assert set(report["buckets"]["bucket_alpha"]["source_type_metrics"]) >= {"candidate_evidence", "requirement_evidence"}
    assert (output_root / "aggregate.json").exists()
    assert (output_root / "runs" / "run-a.json").exists()


def _golden_payload(queries: list[dict[str, object]]) -> dict[str, object]:
    normalized_queries = []
    for index, query in enumerate(queries, start=1):
        normalized_queries.append({"query_id": f"query-{index}", **query})
    return {
        "schema_version": "retriever-golden-v1",
        "metrics": ["precision_at_k", "recall_at_k", "mrr", "ndcg_at_k"],
        "default_k_values": [1, 3],
        "queries": normalized_queries,
    }


def _write_completed_run(run_dir: Path, candidate_id: str, *, requirement_text: str) -> None:
    _write_json(run_dir / "ingest" / "manifest.json", {"candidate_id": candidate_id, "jd_inputs": []})
    _write_json(
        run_dir / "analyze" / "candidate_profile.json",
        {"candidate_id": candidate_id, "experiences": ["Python candidate evidence"]},
    )
    _write_json(
        run_dir / "analyze" / "jd_profiles.json",
        [{"jd_id": "jd-001", "title": "Python role", "company": "Example", "requirements": ["Requirement Python evidence"]}],
    )
    _write_json(
        run_dir / "analyze" / "requirement_matrix.json",
        [{"jd_id": "jd-001", "requirement_id": "jd-001-req-001", "requirement_text": requirement_text}],
    )


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
