from __future__ import annotations

import json
from pathlib import Path

from shotguncv_cli.main import run


def test_review_command_uses_small_batch_serial_path_for_three_or_fewer_jds(tmp_path: Path) -> None:
    run_dir = _write_review_ready_artifacts(tmp_path)

    exit_code, output = run(["review", "--run-dir", str(run_dir)])

    assert exit_code == 0, output
    review = _read_json(run_dir / "review" / "post_run_review.json")
    assert review["schema_version"] == "post-run-review-v2"
    assert review["graph_runtime"] == "small-batch-serial"
    assert review["parallel_topology"]["retrieve"] == "serial_by_jd"
    assert review["parallel_topology"]["inspect"] == "serial_by_jd"
    assert review["parallel_topology"]["small_batch_bypass_max_jds"] == 3
    assert review["parallel_topology"]["evidence_threshold"] == 3
    assert review["jd_ids"] == ["jd-high", "jd-low"]

    events = _read_events(run_dir)
    retrieve_events = _finished_node_events(events, "retrieve_relevant_evidence")
    inspect_events = _finished_node_events(events, "inspect_score_and_gates")
    gap_events = _finished_node_events(events, "generate_evidence_gap_report")

    assert {event["jd_id"] for event in retrieve_events} == {"jd-high", "jd-low"}
    assert {event["jd_id"] for event in inspect_events} == {"jd-high"}
    assert {event["jd_id"] for event in gap_events} == {"jd-low"}
    assert all(event["graph_runtime"] == "small-batch-serial" for event in retrieve_events)
    assert all(isinstance(event["duration_ms"], int) for event in retrieve_events)

    retrieval_queries = [event for event in events if event["event"] == "retrieval_query" and event["stage"] == "review"]
    assert {event["filters"].get("jd_id") for event in retrieval_queries if event["filters"].get("jd_id")} >= {"jd-high", "jd-low"}
    assert all("query_preview" in event and "query" not in event for event in retrieval_queries)
    scopes_by_jd: dict[str, set[str]] = {}
    for event in retrieval_queries:
        jd_id = event["filters"].get("jd_id")
        if isinstance(jd_id, str):
            scopes_by_jd.setdefault(jd_id, set()).add(str(event["retrieval_scope"]))
        assert isinstance(event["raw_hit_count"], int)
        assert isinstance(event["unique_hit_count"], int)
        assert isinstance(event["supporting_hit_count"], int)
        assert isinstance(event["source_type_available_counts"], dict)
        assert event["precision"] is None
        assert "query" not in event
    assert scopes_by_jd["jd-high"] == {"jd_filtered", "combined_deduped"}
    assert scopes_by_jd["jd-low"] == {"jd_filtered", "combined_deduped"}
    combined_events = [event for event in retrieval_queries if event["retrieval_scope"] == "combined_deduped"]
    assert {event["filters"]["jd_id"] for event in combined_events} == {"jd-high", "jd-low"}
    assert all(event["unique_hit_count"] == event["hit_count"] for event in combined_events)


def test_review_command_keeps_fanout_for_four_jds(tmp_path: Path) -> None:
    run_dir = _write_review_ready_artifacts(tmp_path)
    jd_profiles = _read_json(run_dir / "analyze" / "jd_profiles.json")
    jd_profiles.extend(
        [
            {
                "jd_id": "jd-extra-1",
                "title": "Finance Operations Analyst",
                "company": "Finance Co",
                "requirements": ["reconciliation", "budgeting"],
                "keywords": ["finance", "budgeting"],
                "must_have_requirements": ["Finance operations"],
                "interview_focus_areas": ["budget controls"],
            },
            {
                "jd_id": "jd-extra-2",
                "title": "Sales Operations Analyst",
                "company": "Sales Co",
                "requirements": ["CRM", "pipeline reporting"],
                "keywords": ["sales", "CRM"],
                "must_have_requirements": ["Sales operations"],
                "interview_focus_areas": ["pipeline operations"],
            },
        ]
    )
    _write_json(run_dir / "analyze" / "jd_profiles.json", jd_profiles)

    exit_code, output = run(["review", "--run-dir", str(run_dir)])

    assert exit_code == 0, output
    review = _read_json(run_dir / "review" / "post_run_review.json")
    assert review["graph_runtime"].startswith("langgraph")
    assert review["parallel_topology"]["retrieve"] == "fanout_by_jd"
    assert review["parallel_topology"]["inspect"] == "fanout_by_jd"
    assert review["jd_ids"] == ["jd-high", "jd-low", "jd-extra-1", "jd-extra-2"]


def test_review_graph_routes_low_evidence_jds_to_gap_report(tmp_path: Path) -> None:
    run_dir = _write_review_ready_artifacts(tmp_path)

    exit_code, output = run(["review", "--run-dir", str(run_dir)])

    assert exit_code == 0, output
    review = _read_json(run_dir / "review" / "post_run_review.json")
    decisions = {item["jd_id"]: item for item in review["decision_review"]}
    assert decisions["jd-high"]["evidence_status"] == "sufficient"
    assert decisions["jd-high"]["skipped_nodes"] == []
    assert decisions["jd-low"]["evidence_status"] == "insufficient"
    assert decisions["jd-low"]["skipped_nodes"] == [
        "inspect_score_and_gates",
        "generate_interview_questions",
        "generate_reference_answers",
        "generate_revision_tasks",
    ]
    assert review["retrieval"]["low_evidence_jd_count"] == 1
    assert review["evidence_gap_reports"] == [
        {
            "jd_id": "jd-low",
            "evidence_count": 0,
            "minimum_required": 3,
            "recommended_evidence": [
                "补充与 Contracts / Legal Operations 直接相关的项目、职责或成果证据。",
                "标注可复核来源，例如原简历条目、项目材料或过往申请反馈。",
                "证据不足前不要生成模板化面试题、参考答案或简历改写任务。",
            ],
        }
    ]
    assert {item["jd_id"] for item in review["interview_questions"]} == {"jd-high"}
    assert {item["jd_id"] for item in review["reference_answers"]} == {"jd-high"}
    assert {item["jd_id"] for item in review["revision_tasks"]} == {"jd-high"}
    assert "jd-low" not in (run_dir / "review" / "interview_prep.md").read_text(encoding="utf-8")


def test_review_graph_generates_only_for_sufficient_evidence_jds_with_timing_breakdown(tmp_path: Path) -> None:
    run_dir = _write_review_ready_artifacts(tmp_path)

    exit_code, output = run(["review", "--run-dir", str(run_dir)])

    assert exit_code == 0, output
    review = _read_json(run_dir / "review" / "post_run_review.json")
    assert review["parallel_topology"]["generation"] == "run_level_evidence_sufficient_only"

    events = _read_events(run_dir)
    question_events = _finished_node_events(events, "generate_interview_questions")
    answer_events = _finished_node_events(events, "generate_reference_answers")
    task_events = _finished_node_events(events, "generate_revision_tasks")

    assert len(question_events) == 1
    assert len(answer_events) == 1
    assert len(task_events) == 1
    assert all("timing_ms" in event for event in [*question_events, *answer_events, *task_events])
    assert all("business" in event["timing_ms"] for event in [*question_events, *answer_events, *task_events])
    assert all("log_write" in event["timing_ms"] for event in [*question_events, *answer_events, *task_events])
    assert {item["jd_id"] for item in review["interview_questions"]} == {"jd-high"}
    assert {item["jd_id"] for item in review["reference_answers"]} == {"jd-high"}
    assert {item["jd_id"] for item in review["revision_tasks"]} == {"jd-high"}


def test_review_graph_uses_rag_llm_generation_and_logs_llm_budget(tmp_path: Path) -> None:
    run_dir = _write_review_ready_artifacts(tmp_path)

    exit_code, output = run(["review", "--run-dir", str(run_dir)])

    assert exit_code == 0, output
    review = _read_json(run_dir / "review" / "post_run_review.json")
    question = review["interview_questions"][0]
    answer = review["reference_answers"][0]
    assert question["generation"]["provider"] == "deterministic"
    assert question["generation"]["mode"] == "rag_context"
    assert question["evidence_citations"]
    assert "LangGraph" in question["question"]
    assert answer["provenance_citation_count"] >= 1

    events = _read_events(run_dir)
    llm_finished = [event for event in events if event["event"] == "llm_call_finished" and event["stage"] == "review"]
    assert {event["operation"] for event in llm_finished} >= {
        "generate_interview_questions",
        "generate_reference_answers",
    }
    assert all(event["prompt_tokens"] <= 3000 for event in llm_finished)
    assert all(event["max_completion_tokens"] <= 1000 for event in llm_finished)


def _write_review_ready_artifacts(tmp_path: Path) -> Path:
    run_dir = tmp_path / "review-run"
    for stage in ["analyze", "evaluate", "plan"]:
        (run_dir / stage).mkdir(parents=True)

    _write_json(
        run_dir / "analyze" / "candidate_profile.json",
        {
            "candidate_id": "cand-001",
            "base_resume_path": "fixtures/candidates/base_resume.md",
            "experiences": [
                "Built Python LangGraph retrieval review graph with fan-out orchestration.",
                "Created RAG scoring evidence pipelines for resume and JD matching.",
            ],
            "projects": ["Generated interview preparation artifacts from verified candidate evidence."],
            "skills": ["Python", "LangGraph", "RAG", "retrieval evaluation"],
            "industry_tags": ["AI"],
            "strengths": ["Evidence-bound AI workflow delivery"],
            "constraints": [],
            "preferences": [],
            "core_claims": ["Can build artifact-backed review automation."],
            "verified_evidence": ["LangGraph fan-out review graph shipped in local pipeline."],
            "missing_evidence_areas": [],
            "preferred_role_tracks": ["AI platform"],
        },
    )
    _write_json(
        run_dir / "analyze" / "jd_profiles.json",
        [
            {
                "jd_id": "jd-high",
                "title": "AI Platform Engineer",
                "company": "Example AI",
                "cluster": "ai-platform",
                "responsibilities": ["Build LangGraph review automation"],
                "requirements": ["Python", "RAG", "retrieval evaluation"],
                "keywords": ["Python", "LangGraph", "RAG"],
                "seniority": "mid",
                "bonuses": [],
                "risk_signals": [],
                "source_type": "text",
                "source_value": "high.txt",
                "must_have_requirements": ["Python LangGraph RAG delivery"],
                "nice_to_have_requirements": [],
                "hidden_signals": [],
                "interview_focus_areas": ["LangGraph orchestration", "retrieval evaluation"],
                "role_level_confidence": 0.9,
            },
            {
                "jd_id": "jd-low",
                "title": "Contracts Legal Operations Specialist",
                "company": "Legal Co",
                "cluster": "legal-ops",
                "responsibilities": ["Review vendor contracts"],
                "requirements": ["contracts", "legal operations", "procurement"],
                "keywords": ["contracts", "legal", "procurement"],
                "seniority": "mid",
                "bonuses": [],
                "risk_signals": [],
                "source_type": "text",
                "source_value": "low.txt",
                "must_have_requirements": ["Contracts / Legal Operations"],
                "nice_to_have_requirements": [],
                "hidden_signals": [],
                "interview_focus_areas": ["contract review"],
                "role_level_confidence": 0.7,
            },
        ],
    )
    _write_json(
        run_dir / "analyze" / "requirement_matrix.json",
        [
            {
                "jd_id": "jd-high",
                "requirement_id": "jd-high-req-001",
                "tier": "high_priority",
                "requirement_text": "Python LangGraph RAG delivery",
                "evidence_status": "verified",
                "evidence_refs": ["Built Python LangGraph retrieval review graph."],
                "fabrication_policy": "rewrite_only",
                "risk_weight": 0.8,
            },
            {
                "jd_id": "jd-high",
                "requirement_id": "jd-high-req-002",
                "tier": "high_priority",
                "requirement_text": "retrieval evaluation",
                "evidence_status": "verified",
                "evidence_refs": ["Created RAG scoring evidence pipelines."],
                "fabrication_policy": "rewrite_only",
                "risk_weight": 0.8,
            },
            {
                "jd_id": "jd-low",
                "requirement_id": "jd-low-req-001",
                "tier": "hard_gate",
                "requirement_text": "Contracts / Legal Operations",
                "evidence_status": "missing",
                "evidence_refs": [],
                "fabrication_policy": "never_fabricate",
                "risk_weight": 1.0,
            },
        ],
    )
    _write_json(
        run_dir / "analyze" / "preflight_gates.json",
        [
            {"jd_id": "jd-high", "status": "pass", "reasons": [], "skipped_stages": [], "user_action": ""},
            {"jd_id": "jd-low", "status": "needs_review", "reasons": ["hard_gate_missing: Contracts / Legal Operations"], "skipped_stages": [], "user_action": "补充合同运营证据。"},
        ],
    )
    _write_json(
        run_dir / "evaluate" / "scorecards.json",
        [
            {
                "jd_id": "jd-high",
                "variant_id": "variant-jd-high",
                "fit_score": 0.86,
                "ats_score": 0.8,
                "evidence_score": 0.88,
                "stretch_score": 0.7,
                "gap_risk_score": 0.1,
                "rewrite_cost_score": 0.2,
                "overall_score": 0.84,
                "ranking_version": "test",
                "judge_rationale": "Strong artifact-backed fit.",
                "final_overall_score": 0.86,
                "final_decision_source": "rules",
                "guardrail_flags": [],
                "provider": "deterministic",
                "model": "",
                "verified_fit_score": 0.86,
                "rewrite_potential_score": 0.9,
                "risk_score": 0.1,
                "gate_status": "pass",
                "gate_reasons": [],
            },
            {
                "jd_id": "jd-low",
                "variant_id": "preflight-jd-low",
                "fit_score": 0.0,
                "ats_score": 0.0,
                "evidence_score": 0.0,
                "stretch_score": 0.0,
                "gap_risk_score": 0.9,
                "rewrite_cost_score": 1.0,
                "overall_score": 0.0,
                "ranking_version": "test",
                "judge_rationale": "Missing hard gate evidence.",
                "final_overall_score": 0.0,
                "final_decision_source": "preflight-gate",
                "guardrail_flags": ["hard_gate_missing: Contracts / Legal Operations"],
                "provider": "deterministic",
                "model": "",
                "verified_fit_score": 0.0,
                "rewrite_potential_score": 0.0,
                "risk_score": 0.9,
                "gate_status": "needs_review",
                "gate_reasons": ["hard_gate_missing: Contracts / Legal Operations"],
            },
        ],
    )
    _write_json(
        run_dir / "evaluate" / "ranking_explanations.json",
        [
            {
                "jd_id": "jd-high",
                "variant_id": "variant-jd-high",
                "ranking_version": "test",
                "dimension_reasons": {"overall": "Strong fit with evidence."},
                "positive_signals": ["final_score=0.86"],
                "risk_flags": [],
                "evidence_refs": ["Built Python LangGraph retrieval review graph."],
                "decision_summary": "Strong fit with evidence.",
            },
            {
                "jd_id": "jd-low",
                "variant_id": "preflight-jd-low",
                "ranking_version": "test",
                "dimension_reasons": {"overall": "Evidence missing."},
                "positive_signals": [],
                "risk_flags": ["hard_gate_missing: Contracts / Legal Operations"],
                "evidence_refs": [],
                "decision_summary": "Evidence missing.",
            },
        ],
    )
    _write_json(
        run_dir / "plan" / "application_strategies.json",
        [
            {
                "jd_id": "jd-high",
                "recommended_variant_id": "variant-jd-high",
                "priority_rank": 1,
                "apply_decision": "apply",
                "reason_summary": "Strong AI platform fit.",
                "needs_jd_specific_variant": True,
                "decision_drivers": ["LangGraph", "RAG"],
                "watchouts": [],
                "recommended_actions": ["Tighten the LangGraph fan-out evidence bullet."],
                "catch_up_notes": [],
                "decision_confidence": 0.9,
                "interview_prep_points": ["LangGraph orchestration"],
                "resume_revision_tasks": ["Rewrite the review graph bullet with concrete latency evidence."],
            },
            {
                "jd_id": "jd-low",
                "recommended_variant_id": "preflight-jd-low",
                "priority_rank": 2,
                "apply_decision": "needs_review",
                "reason_summary": "Missing legal operations evidence.",
                "needs_jd_specific_variant": False,
                "decision_drivers": ["preflight-gate"],
                "watchouts": ["hard_gate_missing: Contracts / Legal Operations"],
                "recommended_actions": ["补充合同运营证据。"],
                "catch_up_notes": [],
                "decision_confidence": 1.0,
                "interview_prep_points": [],
                "resume_revision_tasks": [],
            },
        ],
    )
    return run_dir


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_events(run_dir: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (run_dir / "logs" / "run_events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _finished_node_events(events: list[dict[str, object]], node: str) -> list[dict[str, object]]:
    return [event for event in events if event["event"] == "graph_node_finished" and event["node"] == node]
