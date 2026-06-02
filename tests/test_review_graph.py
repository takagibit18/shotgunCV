from __future__ import annotations

import json
from pathlib import Path

from langgraph.graph import StateGraph

from shotguncv_cli.main import run
import shotguncv_agents.review_graph as review_graph


def test_review_command_uses_small_batch_serial_path_for_three_or_fewer_jds(tmp_path: Path) -> None:
    run_dir = _write_review_ready_artifacts(tmp_path)

    exit_code, output = run(["review", "--run-dir", str(run_dir)])

    assert exit_code == 0, output
    review = _read_json(run_dir / "review" / "post_run_review.json")
    assert review["schema_version"] == "post-run-review-v4"
    assert review["graph_runtime"] == "small-batch-serial"
    assert review["parallel_topology"]["assess"] == "sequential"
    assert review["parallel_topology"]["inspect"] == "sequential"
    assert review["parallel_topology"]["fan_in_nodes"] == []
    assert review["parallel_topology"]["small_batch_bypass_max_jds"] == 3
    assert review["jd_ids"] == ["jd-high", "jd-low"]

    events = _read_events(run_dir)
    summarize_events = _finished_node_events(events, "summarize_decision_context")
    gap_events = _finished_node_events(events, "generate_gap_report_from_artifacts")

    # summarize_decision_context is run-level (no per-JD fanout) → single event
    assert len(summarize_events) == 1
    assert summarize_events[0]["jd_id"] is None
    assert summarize_events[0]["graph_runtime"] == "small-batch-serial"
    assert isinstance(summarize_events[0]["duration_ms"], int)

    # generate_gap_report_from_artifacts is run-level → single event
    assert len(gap_events) == 1
    assert gap_events[0]["jd_id"] is None

    # Verify no legacy fanout-node events are emitted
    assert _finished_node_events(events, "assess_evidence_from_artifacts") == []
    assert _finished_node_events(events, "inspect_score_and_gates") == []
    assert _finished_node_events(events, "merge_evidence_assessment") == []
    assert _finished_node_events(events, "merge_review_paths") == []


def test_review_command_runs_langgraph_for_four_jds(tmp_path: Path) -> None:
    run_dir = _write_review_ready_artifacts(tmp_path)
    _add_two_extra_jds(run_dir)

    exit_code, output = run(["review", "--run-dir", str(run_dir)])

    assert exit_code == 0, output
    review = _read_json(run_dir / "review" / "post_run_review.json")
    assert review["graph_runtime"].startswith("langgraph")
    assert review["parallel_topology"]["assess"] == "sequential"
    assert review["parallel_topology"]["inspect"] == "sequential"
    assert review["jd_ids"] == ["jd-high", "jd-low", "jd-extra-1", "jd-extra-2"]


def test_review_graph_reuses_compiled_langgraph_between_runs(monkeypatch, tmp_path: Path) -> None:
    clear_cache = getattr(review_graph, "_clear_compiled_review_graph_cache", lambda: None)
    clear_cache()
    compile_calls = 0
    original_compile = StateGraph.compile

    def _counting_compile(self: StateGraph, *args: object, **kwargs: object) -> object:
        nonlocal compile_calls
        compile_calls += 1
        return original_compile(self, *args, **kwargs)

    monkeypatch.setattr(StateGraph, "compile", _counting_compile)
    try:
        first_run_dir = _write_review_ready_artifacts(tmp_path / "first")
        _add_two_extra_jds(first_run_dir)
        second_run_dir = _write_review_ready_artifacts(tmp_path / "second")
        _add_two_extra_jds(second_run_dir)

        first_exit_code, first_output = run(["review", "--run-dir", str(first_run_dir)])
        second_exit_code, second_output = run(["review", "--run-dir", str(second_run_dir)])

        assert first_exit_code == 0, first_output
        assert second_exit_code == 0, second_output
        assert compile_calls == 1
    finally:
        clear_cache()


def test_review_graph_routes_low_evidence_jds_to_gap_report(tmp_path: Path) -> None:
    run_dir = _write_review_ready_artifacts(tmp_path)

    exit_code, output = run(["review", "--run-dir", str(run_dir)])

    assert exit_code == 0, output
    review = _read_json(run_dir / "review" / "post_run_review.json")
    decisions = {item["jd_id"]: item for item in review["decision_review"]}
    assert decisions["jd-high"]["evidence_status"] == "sufficient"
    assert decisions["jd-low"]["evidence_status"] == "insufficient"
    assert review["evidence_assessment"]["low_evidence_jd_count"] == 1
    assert len(review["evidence_gap_reports"]) == 1
    gap_report = review["evidence_gap_reports"][0]
    assert gap_report["jd_id"] == "jd-low"
    assert gap_report["evidence_count"] == 0
    assert gap_report["gap_reason"] == "preflight gate needs_review: hard-gate evidence missing"
    assert gap_report["recommended_evidence"] == [
        "补充与 Contracts / Legal Operations 直接相关的项目、职责或成果证据。",
        "标注可复核来源，例如原简历条目、项目材料或过往申请反馈。",
        "证据不足前不要生成模板化面试题、参考答案或简历改写任务。",
    ]
    # Verify missing_requirements are populated from requirement_matrix
    assert len(gap_report["missing_requirements"]) == 1
    assert gap_report["missing_requirements"][0]["requirement_text"] == "Contracts / Legal Operations"
    assert gap_report["missing_requirements"][0]["evidence_status"] == "missing"
    assert gap_report["missing_requirements"][0]["fabrication_policy"] == "never_fabricate"


def test_review_graph_requires_verified_candidate_evidence_for_sufficient_status(tmp_path: Path) -> None:
    run_dir = _write_review_ready_artifacts(tmp_path)
    matrix = _read_json(run_dir / "analyze" / "requirement_matrix.json")
    for item in matrix:
        if item["jd_id"] == "jd-high":
            item["evidence_status"] = "inferred"
    _write_json(run_dir / "analyze" / "requirement_matrix.json", matrix)

    exit_code, output = run(["review", "--run-dir", str(run_dir)])

    assert exit_code == 0, output
    review = _read_json(run_dir / "review" / "post_run_review.json")
    decisions = {item["jd_id"]: item for item in review["decision_review"]}
    assert decisions["jd-high"]["evidence_status"] == "insufficient"
    assert decisions["jd-high"]["apply_decision"] == "evidence_needed"
    assert decisions["jd-high"]["gate_status"] == "evidence_insufficient"
    assert "no verified candidate evidence" in decisions["jd-high"]["ranking_summary"]


def test_interview_prep_generates_from_structured_artifacts(tmp_path: Path) -> None:
    run_dir = _write_review_ready_artifacts(tmp_path)

    exit_code, output = run(["interview-prep", "--run-dir", str(run_dir)])

    assert exit_code == 0, output
    result = _read_json(run_dir / "review" / "interview_prep.json")
    assert result["schema_version"] == "interview-prep-v2"
    assert result["candidate_id"] == "cand-001"
    assert result["jd_ids"] == ["jd-high", "jd-low"]
    # jd-low has missing hard gate -> no evidence citations (absent from map)
    assert "jd-low" not in result["evidence_citations_by_jd"]
    # jd-high has 2 verified requirements with evidence_refs
    assert result["evidence_citations_by_jd"]["jd-high"] >= 1
    assert len(result["interview_questions"]) >= 1
    question = result["interview_questions"][0]
    assert question["jd_id"] == "jd-high"
    assert question["generation"]["provider"] == "deterministic"
    assert question["evidence_citations"]


def test_interview_prep_respects_jd_id_filter(tmp_path: Path) -> None:
    run_dir = _write_review_ready_artifacts(tmp_path)

    exit_code, output = run(["interview-prep", "--run-dir", str(run_dir), "--jd-id", "jd-high"])

    assert exit_code == 0, output
    result = _read_json(run_dir / "review" / "interview_prep.json")
    assert result["jd_ids"] == ["jd-high"]
    assert {q["jd_id"] for q in result["interview_questions"]} == {"jd-high"}


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


def _add_two_extra_jds(run_dir: Path) -> None:
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
