from __future__ import annotations

import json
from pathlib import Path

from shotguncv_core.pipeline import (
    _select_relevant_variants,
    analyze_run,
    estimate_evaluate_task_total,
    evaluate_run,
    generate_run,
    ingest_run,
    plan_run,
    report_run,
)


ROOT = Path(__file__).resolve().parents[1]


def test_stage_pipeline_writes_expected_run_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    config_path = _write_deterministic_config(tmp_path)

    ingest_run(
        run_dir=run_dir,
        candidate_id="cand-001",
        candidate_resume_path=ROOT / "fixtures" / "candidates" / "base_resume.md",
        jd_sources=[ROOT / "fixtures" / "jds" / "sample_batch.txt"],
        config_path=config_path,
    )
    analysis = analyze_run(run_dir)
    generation = generate_run(run_dir)
    evaluation = evaluate_run(run_dir)
    strategy = plan_run(run_dir)
    report_path = report_run(run_dir)

    assert (run_dir / "ingest" / "manifest.json").exists()
    assert (run_dir / "analyze" / "candidate_profile.json").exists()
    assert (run_dir / "analyze" / "jd_profiles.json").exists()
    assert (run_dir / "generate" / "resume_variants.json").exists()
    assert (run_dir / "evaluate" / "scorecards.json").exists()
    assert (run_dir / "evaluate" / "gap_maps.json").exists()
    assert (run_dir / "evaluate" / "ranking_explanations.json").exists()
    assert (run_dir / "plan" / "application_strategies.json").exists()
    assert report_path == run_dir / "report" / "summary.md"

    assert analysis.candidate.candidate_id == "cand-001"
    assert len(analysis.jd_profiles) == 2
    assert len(generation.variants) == len(analysis.jd_profiles)
    assert all(variant.variant_type == "jd-specific" for variant in generation.variants)
    assert len(evaluation.scorecards) == len(analysis.jd_profiles)
    assert len(evaluation.explanations) >= 2
    assert strategy.strategies[0].apply_decision == "apply"
    assert strategy.strategies[0].decision_drivers
    assert strategy.strategies[0].recommended_actions

    report_text = report_path.read_text(encoding="utf-8")
    assert "LLM Product Engineer" in report_text
    assert "Final score" in report_text
    assert "Evidence that holds" in report_text
    assert "danger points" in report_text
    assert "revise 3 resume items" in report_text


def test_plan_stage_sorts_by_score_and_gap_risk(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
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
    plan_result = plan_run(run_dir)

    ranked_ids = [strategy.jd_id for strategy in plan_result.strategies]

    assert ranked_ids == ["jd-001", "jd-002"]
    assert plan_result.strategies[0].priority_rank == 1
    assert plan_result.strategies[0].catch_up_notes

    plan_payload = json.loads((run_dir / "plan" / "application_strategies.json").read_text(encoding="utf-8"))
    assert plan_payload[0]["jd_id"] == "jd-001"
    assert plan_payload[0]["apply_decision"] == "apply"
    assert plan_payload[0]["decision_drivers"]
    assert plan_payload[0]["watchouts"]
    assert plan_payload[0]["recommended_actions"]

    explanation_payload = json.loads((run_dir / "evaluate" / "ranking_explanations.json").read_text(encoding="utf-8"))
    assert explanation_payload[0]["ranking_version"] == "v0.3.0-llm-eval"
    assert explanation_payload[0]["dimension_reasons"]["overall"]

    eval_summary_payload = json.loads((run_dir / "evaluate" / "eval_summary.json").read_text(encoding="utf-8"))
    assert eval_summary_payload[0]["top_reasons"]


def test_plan_and_report_support_legacy_runs_without_explanations(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
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
    explanation_path = run_dir / "evaluate" / "ranking_explanations.json"
    explanation_path.unlink()

    plan_result = plan_run(run_dir)
    report_path = report_run(run_dir)

    assert plan_result.strategies
    strategy = plan_result.strategies[0]
    assert strategy.decision_drivers
    assert strategy.watchouts
    assert strategy.recommended_actions

    plan_payload = json.loads((run_dir / "plan" / "application_strategies.json").read_text(encoding="utf-8"))
    assert plan_payload[0]["decision_drivers"]
    assert plan_payload[0]["watchouts"]
    assert plan_payload[0]["recommended_actions"]
    assert "Final score" in plan_payload[0]["decision_drivers"][0]

    report_text = report_path.read_text(encoding="utf-8")
    assert "Evidence mapping is limited." in report_text


def test_evaluate_run_reports_progress_for_each_task(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
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

    events: list[dict[str, object]] = []
    evaluation = evaluate_run(run_dir, progress_cb=events.append)

    assert events
    assert len(events) == len(evaluation.scorecards)
    assert events[-1]["completed"] == events[-1]["total"] == len(evaluation.scorecards)
    for event in events:
        assert {"completed", "total", "jd_id", "variant_id", "status", "duration_ms"} <= set(event.keys())


def test_select_relevant_variants_matches_only_target_jd_ids() -> None:
    from shotguncv_core.models import JDProfile, ResumeVariant

    jd = JDProfile(
        jd_id="jd-002",
        title="Finance Manager",
        company="Example Co",
        cluster="finance-manager",
        responsibilities=[],
        requirements=[],
        keywords=[],
        seniority="mid",
        bonuses=[],
        risk_signals=[],
        source_type="text",
        source_value="Finance Manager",
    )
    variants = [
        ResumeVariant(
            variant_id="variant-jd-jd-001",
            variant_type="jd-specific",
            cluster="finance-manager",
            target_jd_ids=["jd-001"],
            summary="wrong target",
            emphasized_strengths=[],
            stretch_points=[],
            source_resume_path="resume.md",
        ),
        ResumeVariant(
            variant_id="variant-jd-jd-002",
            variant_type="jd-specific",
            cluster="other-cluster",
            target_jd_ids=["jd-002"],
            summary="right target",
            emphasized_strengths=[],
            stretch_points=[],
            source_resume_path="resume.md",
        ),
    ]

    relevant = _select_relevant_variants(jd, variants)

    assert [variant.variant_id for variant in relevant] == ["variant-jd-jd-002"]


def test_evaluate_run_keeps_stable_order_across_repeated_runs(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
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

    first = evaluate_run(run_dir)
    second = evaluate_run(run_dir)

    first_pairs = [(item.jd_id, item.variant_id) for item in first.scorecards]
    second_pairs = [(item.jd_id, item.variant_id) for item in second.scorecards]
    assert first_pairs == second_pairs


def test_evaluate_run_fallbacks_single_failed_assess_without_aborting(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    run_dir = tmp_path / "run"
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

    class _FlakyJudge:
        def review(self, jd, candidate, variant, overall_score):  # type: ignore[no-untyped-def]
            class _Feedback:
                def __init__(self, rationale: str) -> None:
                    self.rationale = rationale

            return _Feedback(rationale=f"{variant.variant_id} review")

        def assess(self, jd, candidate, variant, evidence_map, rule_overall_score):  # type: ignore[no-untyped-def]
            if variant.variant_id == "variant-jd-jd-001":
                raise RuntimeError("simulated assess failure")
            from shotguncv_core.models import LLMAssessment

            return LLMAssessment(
                jd_id=jd.jd_id,
                variant_id=variant.variant_id,
                role_fit=0.8,
                evidence_quality=0.8,
                persuasiveness=0.8,
                interview_pressure_risk=0.2,
                application_worthiness="apply",
                must_fix_issues=[],
                evidence_citations=["e1"],
                rewrite_opportunities=["r1"],
                decision_rationale="ok",
                provider="deterministic",
                model="test",
            )

    monkeypatch.setattr(
        "shotguncv_core.pipeline.build_judge_provider",
        lambda config, stage, run_dir: _FlakyJudge(),
    )

    evaluation = evaluate_run(run_dir)

    assert len(evaluation.scorecards) == estimate_evaluate_task_total(run_dir)
    assert any(card.final_decision_source == "guardrail-fallback" for card in evaluation.scorecards)
    assert len(evaluation.llm_assessments) < len(evaluation.scorecards)


def test_evaluate_run_accepts_incomplete_assessment_and_marks_guardrail(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    run_dir = tmp_path / "run"
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

    class _IncompleteJudge:
        def review(self, jd, candidate, variant, overall_score):  # type: ignore[no-untyped-def]
            class _Feedback:
                def __init__(self, rationale: str) -> None:
                    self.rationale = rationale

            return _Feedback(rationale=f"{variant.variant_id} review")

        def assess(self, jd, candidate, variant, evidence_map, rule_overall_score):  # type: ignore[no-untyped-def]
            from shotguncv_core.models import LLMAssessment

            return LLMAssessment(
                jd_id=jd.jd_id,
                variant_id=variant.variant_id,
                role_fit=0.82,
                evidence_quality=0.74,
                persuasiveness=0.73,
                interview_pressure_risk=0.24,
                application_worthiness="apply",
                must_fix_issues=[],
                evidence_citations=[],
                rewrite_opportunities=["补一条更强的指标证据"],
                decision_rationale="",
                provider="deterministic",
                model="test-incomplete",
            )

    monkeypatch.setattr(
        "shotguncv_core.pipeline.build_judge_provider",
        lambda config, stage, run_dir: _IncompleteJudge(),
    )

    evaluation = evaluate_run(run_dir)

    assert len(evaluation.llm_assessments) == len(evaluation.scorecards)
    assert any("llm_assessment_incomplete" in card.guardrail_flags for card in evaluation.scorecards)
    assert all("llm_assessment_missing" not in card.guardrail_flags for card in evaluation.scorecards)


def test_evaluate_run_records_llm_failure_details_and_plan_uses_them(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    run_dir = tmp_path / "run"
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

    class _FlakyJudge:
        def review(self, jd, candidate, variant, overall_score):  # type: ignore[no-untyped-def]
            class _Feedback:
                def __init__(self, rationale: str) -> None:
                    self.rationale = rationale

            return _Feedback(rationale=f"{variant.variant_id} review")

        def assess(self, jd, candidate, variant, evidence_map, rule_overall_score):  # type: ignore[no-untyped-def]
            if jd.jd_id == "jd-001" and variant.variant_id == "variant-jd-jd-001":
                raise RuntimeError("simulated assess failure for diagnostics")
            from shotguncv_core.models import LLMAssessment

            return LLMAssessment(
                jd_id=jd.jd_id,
                variant_id=variant.variant_id,
                role_fit=0.84,
                evidence_quality=0.77,
                persuasiveness=0.76,
                interview_pressure_risk=0.19,
                application_worthiness="apply",
                must_fix_issues=[],
                evidence_citations=["候选人在项目中负责 Prompt 编排"],
                rewrite_opportunities=["补一条量化结果"],
                decision_rationale="整体可投。",
                provider="deterministic",
                model="test",
            )

    monkeypatch.setattr(
        "shotguncv_core.pipeline.build_judge_provider",
        lambda config, stage, run_dir: _FlakyJudge(),
    )

    evaluation = evaluate_run(run_dir)
    strategy = plan_run(run_dir)

    failure_payload = json.loads((run_dir / "evaluate" / "llm_failures.json").read_text(encoding="utf-8"))

    assert failure_payload
    assert failure_payload[0]["error_type"] == "RuntimeError"
    assert "simulated assess failure for diagnostics" in failure_payload[0]["error_message"]
    assert "variant-jd-jd-001" in {item["variant_id"] for item in failure_payload}
    assert any("simulated assess failure for diagnostics" in item.reason_summary for item in strategy.strategies)
    assert any("llm_assessment_missing" in card.guardrail_flags for card in evaluation.scorecards)


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
