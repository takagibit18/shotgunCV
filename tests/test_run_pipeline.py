from __future__ import annotations

import json
from pathlib import Path

from shotguncv_core.pipeline import (
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
    assert len(generation.variants) >= 3
    assert len(evaluation.scorecards) >= 2
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
