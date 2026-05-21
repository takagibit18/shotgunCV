from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from shotguncv_cli.main import run
from shotguncv_core.pipeline import analyze_run, evaluate_run, generate_run, ingest_run, plan_run


ROOT = Path(__file__).resolve().parents[1]


def test_projection_normalizes_run_artifacts_idempotently(tmp_path: Path) -> None:
    from shotguncv_core.db.indexer import build_projection_batch

    run_dir = _prepare_completed_run(tmp_path)

    first = build_projection_batch(run_dir)
    second = build_projection_batch(run_dir)

    assert first == second
    assert first.run.run_id == run_dir.name
    assert first.candidates[0]["candidate_id"] == "cand-001"
    assert {artifact["artifact_path"] for artifact in first.run_artifacts} >= {
        "ingest/manifest.json",
        "analyze/candidate_profile.json",
        "evaluate/scorecards.json",
        "plan/application_strategies.json",
    }
    assert first.scorecards
    assert first.retrieval_chunks
    for chunk in first.retrieval_chunks:
        metadata = chunk["metadata"]
        assert metadata["source_type"]
        assert metadata["source_id"]
        assert metadata["candidate_id"] == "cand-001"
        assert "provenance_summary" in metadata


def test_cli_index_requires_db_only_for_index_command(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("SHOTGUNCV_DATABASE_URL", raising=False)

    exit_code, output = run(["index", "--runs-dir", str(tmp_path)])

    assert exit_code == 1
    assert "SHOTGUNCV_DATABASE_URL" in output


def test_index_runs_against_postgres_when_database_url_is_configured(tmp_path: Path) -> None:
    from shotguncv_core.db.indexer import index_runs

    database_url = os.environ.get("SHOTGUNCV_TEST_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("Set SHOTGUNCV_TEST_DATABASE_URL to run PostgreSQL projection integration tests.")
    _prepare_completed_run(tmp_path)

    first = index_runs(tmp_path, database_url)
    second = index_runs(tmp_path, database_url)

    assert first["runs"] == second["runs"] == 1
    assert first["chunks"] == second["chunks"]


def test_deterministic_retriever_preserves_metadata(tmp_path: Path) -> None:
    from shotguncv_core.db.indexer import build_projection_batch
    from shotguncv_core.rag.retrieval import InMemoryVectorRetriever

    run_dir = _prepare_completed_run(tmp_path)
    chunks = build_projection_batch(run_dir).retrieval_chunks
    retriever = InMemoryVectorRetriever.from_chunks(chunks)

    results = retriever.search("Python automation evidence", limit=3, source_type="candidate_evidence")

    assert results
    assert results[0].metadata["source_type"] == "candidate_evidence"
    assert results[0].metadata["candidate_id"] == "cand-001"
    assert "provenance_summary" in results[0].metadata


def test_review_command_writes_artifacts_with_citations_and_validation(tmp_path: Path) -> None:
    run_dir = _prepare_completed_run(tmp_path)

    exit_code, output = run(["review", "--run-dir", str(run_dir)])

    assert exit_code == 0, output
    review = json.loads((run_dir / "review" / "post_run_review.json").read_text(encoding="utf-8"))
    prep = (run_dir / "review" / "interview_prep.md").read_text(encoding="utf-8")
    assert review["run_id"] == run_dir.name
    assert review["evidence_citations"]
    assert review["retrieval"]["misses"] == []
    assert review["validation"]["fabrication_policy"] == "passed"
    assert "unsupported_hard_fact_tasks_removed" in review["validation"]
    assert "面试准备" in prep
    assert "证据" in prep


def _prepare_completed_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "completed-run"
    config_path = _write_deterministic_config(tmp_path)
    ingest_run(
        run_dir=run_dir,
        candidate_id="cand-001",
        candidate_resume_path=ROOT / "fixtures" / "candidates" / "base_resume.md",
        jd_sources=[ROOT / "fixtures" / "jds" / "sample_batch.txt"],
        config_path=config_path,
    )
    analyze_run(run_dir)
    generate_run(run_dir)
    evaluate_run(run_dir)
    plan_run(run_dir)
    return run_dir


def _write_deterministic_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "deterministic-run-config.json"
    config_path.write_text(
        json.dumps(
            {
                "analyzer": {"provider": "deterministic", "model": ""},
                "generator": {"provider": "deterministic", "model": ""},
                "judge": {"provider": "deterministic", "model": ""},
                "planner": {"provider": "deterministic", "model": ""},
                "openai": {"base_url": None, "api_key_env": "OPENAI_API_KEY", "env_file": ".env"},
                "run_metadata": {"label": "pytest-deterministic"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return config_path
