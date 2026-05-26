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


def test_index_runs_logs_per_run_batch_without_changing_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import shotguncv_core.db.indexer as indexer
    import shotguncv_core.db.session as session

    class FakeConnection:
        def __enter__(self) -> "FakeConnection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def commit(self) -> None:
            return None

    run_dir = _prepare_completed_run(tmp_path)
    upserted: list[str] = []

    monkeypatch.setattr(session, "connect", lambda database_url: FakeConnection())
    monkeypatch.setattr(indexer, "_ensure_schema", lambda conn: None)
    monkeypatch.setattr(indexer, "_upsert_batch", lambda conn, batch, *, skip_chunks: upserted.append(batch.run.run_id))

    first = indexer.index_runs(tmp_path, "postgresql://example/test")
    second = indexer.index_runs(tmp_path, "postgresql://example/test")

    assert first["runs"] == second["runs"] == 1
    assert first["chunks"] == second["chunks"]
    assert upserted == [run_dir.name, run_dir.name]
    events = _read_events(run_dir)
    index_batches = [event for event in events if event["event"] == "index_batch"]
    assert len(index_batches) == 2
    assert index_batches[0]["run_id"] == run_dir.name
    assert index_batches[0]["artifact_count"] > 0
    assert index_batches[0]["chunk_count"] == first["chunks"]
    assert index_batches[0]["skip_chunks"] is False
    assert any(event["event"] == "stage_started" and event["stage"] == "index" for event in events)
    assert any(event["event"] == "stage_finished" and event["stage"] == "index" for event in events)


def test_retriever_preserves_metadata_with_injected_embedding(tmp_path: Path) -> None:
    from shotguncv_core.db.indexer import build_projection_batch
    from shotguncv_core.rag.embeddings import deterministic_embedding
    from shotguncv_core.rag.retrieval import InMemoryVectorRetriever

    class DeterministicEmbeddingModel:
        def embed(self, text: str) -> list[float]:
            return deterministic_embedding(text)

    run_dir = _prepare_completed_run(tmp_path)
    chunks = build_projection_batch(run_dir).retrieval_chunks
    retriever = InMemoryVectorRetriever.from_chunks(chunks, embedding_model=DeterministicEmbeddingModel())

    results = retriever.search("Python automation evidence", limit=3, source_type="candidate_evidence")

    assert results
    assert results[0].metadata["source_type"] == "candidate_evidence"
    assert results[0].metadata["candidate_id"] == "cand-001"
    assert "provenance_summary" in results[0].metadata


def test_embedding_defaults_to_bge_m3_dimension() -> None:
    from shotguncv_core.db.schema import EMBEDDING_DIMENSIONS
    from shotguncv_core.rag.embeddings import DEFAULT_EMBEDDING_MODEL

    assert DEFAULT_EMBEDDING_MODEL == "BAAI/bge-m3"
    assert EMBEDDING_DIMENSIONS == 1024


def test_in_memory_retriever_uses_injected_embedding_model() -> None:
    from shotguncv_core.rag.retrieval import InMemoryVectorRetriever

    class KeywordEmbeddingModel:
        def embed(self, text: str) -> list[float]:
            normalized = text.lower()
            if "python" in normalized:
                return [1.0, 0.0, 0.0]
            if "sales" in normalized:
                return [0.0, 1.0, 0.0]
            return [0.0, 0.0, 1.0]

    chunks = [
        {
            "text": "Sales pipeline ownership",
            "metadata": {
                "source_type": "candidate_evidence",
                "source_id": "sales",
                "candidate_id": "cand-001",
                "provenance_summary": "sales",
            },
        },
        {
            "text": "Python automation evidence",
            "metadata": {
                "source_type": "candidate_evidence",
                "source_id": "python",
                "candidate_id": "cand-001",
                "provenance_summary": "python",
            },
        },
    ]
    retriever = InMemoryVectorRetriever.from_chunks(chunks, embedding_model=KeywordEmbeddingModel())

    results = retriever.search("Python role", limit=2)

    assert [result.metadata["source_id"] for result in results] == ["python", "sales"]


def test_review_command_writes_artifacts_with_citations_and_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shotguncv_agents.review_graph as review_graph
    from shotguncv_core.rag.embeddings import deterministic_embedding

    class DeterministicEmbeddingModel:
        def embed(self, text: str) -> list[float]:
            return deterministic_embedding(text)

        def embed_many(self, texts: list[str]) -> list[list[float]]:
            return [self.embed(text) for text in texts]

    monkeypatch.setattr(review_graph, "_REVIEW_EMBEDDING_MODEL", DeterministicEmbeddingModel())
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


def _read_events(run_dir: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (run_dir / "logs" / "run_events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


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
