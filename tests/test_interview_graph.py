from __future__ import annotations

import json
from pathlib import Path

from shotguncv_cli.main import run
from test_review_graph import _read_events, _read_json, _write_review_ready_artifacts


def test_interview_command_stops_at_question_review_checkpoint(tmp_path: Path) -> None:
    run_dir = _write_review_ready_artifacts(tmp_path)
    exit_code, output = run(["review", "--run-dir", str(run_dir)])
    assert exit_code == 0, output

    exit_code, output = run(["interview", "--run-dir", str(run_dir)])

    assert exit_code == 0, output
    assert "awaiting_question_review" in output
    session = _read_json(run_dir / "interview" / "session.json")
    questions = _read_json(run_dir / "interview" / "questions.json")
    assert session["status"] == "awaiting_question_review"
    assert session["checkpoints"][-1]["name"] == "generate_questions"
    assert questions["questions"]
    assert not (run_dir / "interview" / "evaluation.json").exists()


def test_interview_command_resumes_and_completes_simulated_hitl_loop(tmp_path: Path) -> None:
    run_dir = _write_review_ready_artifacts(tmp_path)
    exit_code, output = run(["review", "--run-dir", str(run_dir)])
    assert exit_code == 0, output
    exit_code, output = run(["interview", "--run-dir", str(run_dir)])
    assert exit_code == 0, output

    exit_code, output = run(["interview", "--run-dir", str(run_dir), "--auto-approve"])

    assert exit_code == 0, output
    assert "completed" in output
    session = _read_json(run_dir / "interview" / "session.json")
    questions = _read_json(run_dir / "interview" / "questions.json")
    evaluation = _read_json(run_dir / "interview" / "evaluation.json")
    assert session["status"] == "completed"
    assert questions["review_status"] == "approved"
    assert evaluation["evaluations"]
    assert {item["status"] for item in evaluation["evaluations"]} == {"generated"}

    events = _read_events(run_dir)
    event_names = [event["event"] for event in events]
    assert "interview_answer_submitted" in event_names
    assert "interview_evaluation_generated" in event_names
    assert any(event["event"] == "stage_finished" and event["stage"] == "interview" for event in events)


def test_golden_retrieval_fixture_contains_manual_targets() -> None:
    payload = json.loads(Path("fixtures/golden_retrieval_questions.json").read_text(encoding="utf-8"))

    assert payload["schema_version"] == "retriever-golden-v1"
    assert set(payload["metrics"]) >= {"precision_at_k", "recall_at_k", "mrr", "ndcg_at_k"}
    assert len(payload["queries"]) >= 10
    for item in payload["queries"]:
        assert item["query_id"]
        assert item["jd_id"]
        assert item["query"]
        assert item["expected_chunks"]
        assert item["expected_question_direction"]
        assert 0 <= item["relevance_threshold"] <= 1
