from __future__ import annotations

import json
from pathlib import Path

from shotguncv_agents.interview_llm import generate_interview_questions, generate_reference_answers


def test_interview_llm_generates_evidence_bound_questions_and_token_logs(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-llm"
    citations = [
        {
            "review_jd_id": "jd-001",
            "source_type": "candidate_evidence",
            "source_id": "candidate_profile.experiences.0",
            "artifact_path": "analyze/candidate_profile.json",
            "provenance_summary": "candidate_profile.experiences",
            "text": "Built a Python LangGraph RAG review pipeline with fan-out retrieval.",
            "score": 0.82,
        }
    ]

    questions = generate_interview_questions(
        run_dir=run_dir,
        jd_id="jd-001",
        jd_profile={
            "title": "AI Platform Engineer",
            "company": "Example AI",
            "interview_focus_areas": ["LangGraph orchestration"],
            "keywords": ["Python", "LangGraph", "RAG"],
        },
        evidence_citations=citations,
    )
    answers = generate_reference_answers(run_dir=run_dir, questions=questions, evidence_citations=citations)

    assert questions
    assert questions[0]["jd_id"] == "jd-001"
    assert questions[0]["generation"]["provider"] == "deterministic"
    assert questions[0]["evidence_citations"][0]["source_id"] == "candidate_profile.experiences.0"
    assert "LangGraph" in questions[0]["question"]
    assert answers[0]["evidence_citations"]
    assert answers[0]["provenance_citation_count"] >= 1

    events = _read_events(run_dir)
    finished = [event for event in events if event["event"] == "llm_call_finished"]
    assert {event["operation"] for event in finished} == {
        "generate_interview_questions",
        "generate_reference_answers",
    }
    assert all(event["stage"] == "review" for event in finished)
    assert all(event["prompt_tokens"] <= 3000 for event in finished)
    assert all(event["max_completion_tokens"] <= 1000 for event in finished)
    assert all(event["fallback_used"] is False for event in finished)


def _read_events(run_dir: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (run_dir / "logs" / "run_events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
