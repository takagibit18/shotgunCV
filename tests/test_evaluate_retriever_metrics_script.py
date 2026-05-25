from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate_retriever_metrics import evaluate_run_dir


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
    _write_json(
        golden_path,
        [
            {
                "jd_id": "jd-001",
                "query": "Python LangGraph RAG pipeline",
                "expected_chunks": ["candidate-profile"],
            }
        ],
    )
    output_path = tmp_path / "report.json"

    report = evaluate_run_dir(
        run_dir=run_dir,
        golden_file=golden_path,
        output_path=output_path,
        k_values=[1, 3],
    )

    assert output_path.exists()
    assert report["run_id"] == "completed-run"
    assert report["chunk_count"] == 1
    assert report["label_coverage"]["expected_label_count"] == 1
    assert report["label_coverage"]["matched_label_count"] == 1
    assert report["label_coverage"]["missing_expected_chunks"] == []
    assert report["label_inventory"][0]["source_id"] == "cand-001:candidate-profile"
    assert report["metrics"]["query_count"] == 1
    assert report["metrics"]["aggregate"]["recall_at_k"]["3"] == 1.0


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
    )

    assert report["golden_schema_version"] == "retriever-golden-v1"
    assert report["metrics"]["queries"][0]["query_id"] == "rag-pipeline"
    assert report["metrics"]["aggregate"]["mrr"] == 1.0


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
