from __future__ import annotations

import json
from pathlib import Path

from shotguncv_core.pipeline import (
    _build_requirement_matrix,
    _build_scorecard,
    _candidate_search_text,
    _collect_jd_requirements,
    _evaluate_requirement_evidence,
    _is_resume_metadata_evidence,
    _matching_evidence_refs,
    _record_analyze_quality,
    _requirement_matrix_quality_checks,
    _select_relevant_variants,
    _sanitize_candidate_profile,
    analyze_run,
    estimate_evaluate_task_total,
    evaluate_run,
    generate_run,
    ingest_run,
    plan_run,
    report_run,
)
from shotguncv_agents.providers import AnalyzeFeedback
from shotguncv_core.models import CandidateProfile, JDProfile, LLMAssessment, RequirementEvidence, ResumeVariant
from shotguncv_evals.rules import RuleEvaluation


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
    assert (run_dir / "generate" / "generated_resumes.json").exists()
    assert (run_dir / "evaluate" / "scorecards.json").exists()
    assert (run_dir / "evaluate" / "gap_maps.json").exists()
    assert (run_dir / "evaluate" / "ranking_explanations.json").exists()
    assert (run_dir / "plan" / "application_strategies.json").exists()
    assert report_path == run_dir / "report" / "summary.md"

    assert analysis.candidate.candidate_id == "cand-001"
    assert len(analysis.jd_profiles) == 2
    assert len(generation.variants) == len(analysis.jd_profiles)
    assert len(generation.generated_resumes) == len(analysis.jd_profiles)
    assert all(variant.variant_type == "jd-specific" for variant in generation.variants)
    assert len(evaluation.scorecards) == len(analysis.jd_profiles)
    assert any(scorecard.final_overall_score > 0 for scorecard in evaluation.scorecards)
    assert len(evaluation.explanations) >= 2
    assert strategy.strategies[0].apply_decision in {"apply", "hold"}
    assert strategy.strategies[0].decision_drivers
    assert strategy.strategies[0].recommended_actions

    manifest = json.loads((run_dir / "ingest" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["candidate_inputs"][0]["role"] == "cv"
    assert manifest["candidate_inputs"][0]["source_origin"] == "fixture"
    assert manifest["candidate_inputs"][0]["original_name"] == "base_resume.md"
    assert manifest["candidate_inputs"][0]["relative_path"].endswith("fixtures/candidates/base_resume.md")
    assert manifest["candidate_inputs"][0]["size_bytes"] > 0
    assert manifest["jd_inputs"][0]["role"] == "jd"
    assert manifest["jd_inputs"][0]["source_origin"] == "fixture"
    assert manifest["jd_inputs"][0]["original_name"] == "sample_batch.txt"
    assert manifest["jd_inputs"][0]["relative_path"].endswith("fixtures/jds/sample_batch.txt")
    assert manifest["jd_inputs"][0]["content"] == manifest["jd_inputs"][0]["text"]

    generated_resumes = json.loads((run_dir / "generate" / "generated_resumes.json").read_text(encoding="utf-8"))
    first_resume = generated_resumes[0]
    assert first_resume["resume_id"] == "resume-jd-001"
    assert first_resume["target_jd_id"] == "jd-001"
    assert first_resume["status"] == "deliverable"
    assert set(first_resume["document"]) == {
        "basics",
        "summary",
        "skills",
        "experiences",
        "projects",
        "education",
        "certifications",
    }
    assert first_resume["document"]["summary"]
    assert first_resume["document"]["skills"]
    assert first_resume["document"]["experiences"]
    assert "markdown" not in first_resume
    assert first_resume["provenance"]["field_sources"]["document.summary"]
    assert isinstance(first_resume["provenance"]["to_verify_fields"], list)
    assert isinstance(first_resume["provenance"]["forbidden_fields"], list)

    report_text = report_path.read_text(encoding="utf-8")
    assert "LLM Product Engineer" in report_text
    assert "Final score" in report_text
    assert "Evidence that holds" in report_text
    assert "danger points" in report_text
    assert "revise 3 resume items" in report_text


def test_ingest_run_accepts_multiple_candidate_and_jd_sources(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    config_path = _write_deterministic_config(tmp_path)
    cv_dir = tmp_path / "cv"
    jd_dir = tmp_path / "jd"
    cv_dir.mkdir()
    jd_dir.mkdir()
    (cv_dir / "resume.md").write_text("- Built LLM workflow tools", encoding="utf-8")
    (cv_dir / "extra.txt").write_text("- Added evidence-backed ranking reports", encoding="utf-8")
    (jd_dir / "a.txt").write_text(
        "Title: Applied AI Engineer\nCompany: Example\nBody:\n- Build Python automation",
        encoding="utf-8",
    )
    (jd_dir / "b.txt").write_text(
        "Title: LLM Product Engineer\nCompany: Example\nBody:\n- Own LLM product metrics",
        encoding="utf-8",
    )

    ingest_run(
        run_dir=run_dir,
        candidate_id="cand-001",
        candidate_resume_path=None,
        jd_sources=None,
        config_path=config_path,
        candidate_sources=[cv_dir],
        jd_input_sources=[jd_dir],
    )
    analysis = analyze_run(run_dir)

    manifest = json.loads((run_dir / "ingest" / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["candidate_inputs"]) == 2
    assert [item["role"] for item in manifest["candidate_inputs"]] == ["cv", "cv"]
    assert [item["source_origin"] for item in manifest["candidate_inputs"]] == ["cli", "cli"]
    assert [item["original_name"] for item in manifest["candidate_inputs"]] == ["extra.txt", "resume.md"]
    assert [Path(item["relative_path"]).name for item in manifest["candidate_inputs"]] == ["extra.txt", "resume.md"]
    assert all(item["size_bytes"] > 0 for item in manifest["candidate_inputs"])
    assert "Added evidence-backed ranking reports" in manifest["candidate_resume_text"]
    assert len(manifest["jd_inputs"]) == 2
    assert [item["role"] for item in manifest["jd_inputs"]] == ["jd", "jd"]
    assert [item["source_origin"] for item in manifest["jd_inputs"]] == ["cli", "cli"]
    assert [item["original_name"] for item in manifest["jd_inputs"]] == ["a.txt", "b.txt"]
    assert all(item["content"] == item["text"] for item in manifest["jd_inputs"])
    assert len(analysis.jd_profiles) == 2
    assert [jd.jd_id for jd in analysis.jd_profiles] == ["jd-001", "jd-002"]


def test_ingest_run_matches_web_upload_manifest_metadata(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    config_path = _write_deterministic_config(tmp_path)
    cv_dir = run_dir / "input_files" / "cv"
    jd_dir = run_dir / "input_files" / "jd"
    cv_dir.mkdir(parents=True)
    jd_dir.mkdir(parents=True)
    (cv_dir / "resume.md").write_text("- Built LLM workflow tools", encoding="utf-8")
    (jd_dir / "jd.txt").write_text(
        "Title: Applied AI Engineer\nCompany: Example\nBody:\n- Build Python automation",
        encoding="utf-8",
    )
    ingest_dir = run_dir / "ingest"
    ingest_dir.mkdir()
    (ingest_dir / "upload_manifest.json").write_text(
        json.dumps(
            {
                "schemaVersion": "v0.5.1-upload-manifest",
                "candidateId": "cand-001",
                "label": "Upload smoke",
                "createdAt": "2026-04-25T08:30:00.000Z",
                "files": [
                    {
                        "role": "cv",
                        "originalName": "Original Resume.md",
                        "storedRelativePath": "input_files/cv/resume.md",
                        "sizeBytes": 26,
                        "contentType": "text/markdown",
                        "uploadedAt": "2026-04-25T08:30:00.000Z",
                    },
                    {
                        "role": "jd",
                        "originalName": "Original JD.txt",
                        "displayName": "Example - Applied AI Engineer",
                        "storedRelativePath": "input_files/jd/jd.txt",
                        "sizeBytes": 78,
                        "contentType": "text/plain",
                        "uploadedAt": "2026-04-25T08:30:00.000Z",
                    },
                ],
                "nextCommand": "shotguncv run --run-dir ./runs/upload-smoke --candidate-id cand-001",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    ingest_run(
        run_dir=run_dir,
        candidate_id="cand-001",
        candidate_resume_path=None,
        jd_sources=None,
        config_path=config_path,
        candidate_sources=[cv_dir],
        jd_input_sources=[jd_dir],
    )

    manifest = json.loads((run_dir / "ingest" / "manifest.json").read_text(encoding="utf-8"))
    candidate_item = manifest["candidate_inputs"][0]
    jd_item = manifest["jd_inputs"][0]
    assert candidate_item["role"] == "cv"
    assert candidate_item["source_origin"] == "upload"
    assert candidate_item["original_name"] == "Original Resume.md"
    assert candidate_item["relative_path"] == "input_files/cv/resume.md"
    assert candidate_item["size_bytes"] == 26
    assert jd_item["role"] == "jd"
    assert jd_item["source_origin"] == "upload"
    assert jd_item["original_name"] == "Original JD.txt"
    assert jd_item["display_name"] == "Example - Applied AI Engineer"
    assert jd_item["relative_path"] == "input_files/jd/jd.txt"
    assert jd_item["size_bytes"] == 78
    assert jd_item["content"] == jd_item["text"]


def test_ingest_run_records_unparseable_inputs_as_warnings(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    config_path = _write_deterministic_config(tmp_path)
    cv_dir = tmp_path / "cv"
    jd_dir = tmp_path / "jd"
    cv_dir.mkdir()
    jd_dir.mkdir()
    (cv_dir / "resume.md").write_text("- Built LLM workflow tools", encoding="utf-8")
    (cv_dir / "scan.jpg").write_bytes(b"not a real image")
    (jd_dir / "jd.txt").write_text(
        "Title: Applied AI Engineer\nCompany: Example\nBody:\n- Build Python automation",
        encoding="utf-8",
    )

    ingest_run(
        run_dir=run_dir,
        candidate_id="cand-001",
        candidate_resume_path=None,
        jd_sources=None,
        config_path=config_path,
        candidate_sources=[cv_dir],
        jd_input_sources=[jd_dir],
        vision_fallback_enabled=False,
    )

    manifest = json.loads((run_dir / "ingest" / "manifest.json").read_text(encoding="utf-8"))
    unparseable = manifest["candidate_inputs"][1]
    assert unparseable["original_name"] == "scan.jpg"
    assert unparseable["text"] == ""
    assert unparseable["extraction_status"] == "unparseable"
    assert unparseable["extraction_error"]
    assert manifest["candidate_resume_text"].strip().endswith("- Built LLM workflow tools")
    assert manifest["input_warnings"] == [
        {
            "role": "cv",
            "relative_path": unparseable["relative_path"],
            "original_name": "scan.jpg",
            "extraction_error": unparseable["extraction_error"],
        }
    ]


def test_ingest_run_logs_pdf_fallback_chain(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    run_dir = tmp_path / "run"
    config_path = _write_deterministic_config(tmp_path)
    cv_path = tmp_path / "resume.pdf"
    page_image = tmp_path / "resume-page-1.png"
    jd_path = tmp_path / "jd.txt"
    cv_path.write_bytes(b"%PDF-1.4 encoded")
    page_image.write_bytes(b"image")
    jd_path.write_text("Title: AI Engineer\nBody:\n- Build automation", encoding="utf-8")
    monkeypatch.setattr(
        "shotguncv_core.inputs._extract_pdf_text",
        lambda path: "> analyze -\nA\nB\nC\n\\001\\002\\003\\004\\005\\006\\007",
    )
    monkeypatch.setattr("shotguncv_core.inputs._render_pdf_pages_to_images", lambda path: [page_image])
    monkeypatch.setattr(
        "shotguncv_core.inputs._extract_image_text_with_ocr",
        lambda path, languages, **kw: "Bachelor degree in Computer Science. Built Python Agent systems.",
    )

    ingest_run(
        run_dir=run_dir,
        candidate_id="cand-001",
        candidate_resume_path=cv_path,
        jd_sources=[jd_path],
        config_path=config_path,
        vision_fallback_enabled=False,
    )

    manifest = json.loads((run_dir / "ingest" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["candidate_inputs"][0]["extraction_status"] == "ocr"
    events = [
        json.loads(line)
        for line in (run_dir / "logs" / "run_events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    extracted = [event for event in events if event["event"] == "input_extracted" and event["role"] == "cv"][0]
    assert extracted["provider"] == "local_ocr"
    assert extracted["fallback_from"] == "local_pdf"
    assert any(
        event["event"] == "fallback_used"
        and event["from_provider"] == "local_pdf"
        and event["to_provider"] == "local_ocr"
        for event in events
    )


def test_ingest_run_fails_when_all_cv_inputs_are_unparseable(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    config_path = _write_deterministic_config(tmp_path)
    cv_dir = tmp_path / "cv"
    jd_dir = tmp_path / "jd"
    cv_dir.mkdir()
    jd_dir.mkdir()
    (cv_dir / "scan.jpg").write_bytes(b"not a real image")
    (jd_dir / "jd.txt").write_text("Title: AI Engineer\nBody:\n- Build automation", encoding="utf-8")

    try:
        ingest_run(
            run_dir=run_dir,
            candidate_id="cand-001",
            candidate_resume_path=None,
            jd_sources=None,
            config_path=config_path,
            candidate_sources=[cv_dir],
            jd_input_sources=[jd_dir],
            vision_fallback_enabled=False,
        )
    except ValueError as exc:
        assert "At least one CV input must contain extractable text." in str(exc)
    else:
        raise AssertionError("ingest_run should fail when all CV inputs are unparseable")


def test_ingest_run_fails_when_all_jd_inputs_are_unparseable(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    config_path = _write_deterministic_config(tmp_path)
    cv_dir = tmp_path / "cv"
    jd_dir = tmp_path / "jd"
    cv_dir.mkdir()
    jd_dir.mkdir()
    (cv_dir / "resume.md").write_text("- Built LLM workflow tools", encoding="utf-8")
    (jd_dir / "scan.jpg").write_bytes(b"not a real image")

    try:
        ingest_run(
            run_dir=run_dir,
            candidate_id="cand-001",
            candidate_resume_path=None,
            jd_sources=None,
            config_path=config_path,
            candidate_sources=[cv_dir],
            jd_input_sources=[jd_dir],
            vision_fallback_enabled=False,
        )
    except ValueError as exc:
        assert "At least one JD input must contain extractable text." in str(exc)
    else:
        raise AssertionError("ingest_run should fail when all JD inputs are unparseable")


def test_ingest_run_blocks_unreadable_cv_text_before_analysis(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    config_path = _write_deterministic_config(tmp_path)
    cv_path = tmp_path / "cv.txt"
    jd_path = tmp_path / "jd.txt"
    cv_path.write_text("锛 鏄 鐨 杩 妫 绱 ???", encoding="utf-8")
    jd_path.write_text("Title: AI Engineer\nCompany: Example\nBody:\n- Build Python automation", encoding="utf-8")

    try:
        ingest_run(
            run_dir=run_dir,
            candidate_id="cand-001",
            candidate_resume_path=cv_path,
            jd_sources=[jd_path],
            config_path=config_path,
        )
    except ValueError as exc:
        assert "CV text quality check failed" in str(exc)
    else:
        raise AssertionError("ingest_run should block unreadable CV text")

    assert not (run_dir / "ingest" / "manifest.json").exists()
    events = [
        json.loads(line)
        for line in (run_dir / "logs" / "run_events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(
        event.get("event") == "pipeline_stage_status"
        and event.get("stage_key") == "parse_cv"
        and event.get("status") == "parse_error"
        for event in events
    )


def test_ingest_run_marks_bad_jd_as_partial_and_analyze_uses_only_valid_jds(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    config_path = _write_deterministic_config(tmp_path)
    cv_path = tmp_path / "cv.txt"
    jd_dir = tmp_path / "jds"
    jd_dir.mkdir()
    cv_path.write_text(
        "Built Python LLM workflow automation, LangGraph review tools, and evidence-backed ranking reports.",
        encoding="utf-8",
    )
    (jd_dir / "good.txt").write_text(
        "Title: AI Engineer\nCompany: Example\nBody:\n- Build Python automation\n- Own LLM evaluation metrics",
        encoding="utf-8",
    )
    (jd_dir / "bad.txt").write_text("Apply", encoding="utf-8")

    ingest_run(
        run_dir=run_dir,
        candidate_id="cand-001",
        candidate_resume_path=cv_path,
        jd_input_sources=[jd_dir],
        config_path=config_path,
    )
    analysis = analyze_run(run_dir)

    manifest = json.loads((run_dir / "ingest" / "manifest.json").read_text(encoding="utf-8"))
    bad_jd = next(item for item in manifest["jd_inputs"] if item["original_name"] == "bad.txt")
    assert bad_jd["text_quality_status"] == "failed"
    assert bad_jd["analysis_eligible"] is False
    assert len(analysis.jd_profiles) == 1
    assert analysis.jd_profiles[0].source_value.endswith("good.txt")
    status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    assert status["quality_status"] == "warning"
    assert status["status_kind"] == "partial_failed"


def test_analyze_run_rejects_incomplete_structured_artifacts(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    run_dir = tmp_path / "run"
    config_path = _write_deterministic_config(tmp_path)
    cv_path = tmp_path / "cv.txt"
    jd_path = tmp_path / "jd.txt"
    cv_path.write_text(
        "Built Python LLM workflow automation, LangGraph review tools, and evidence-backed ranking reports.",
        encoding="utf-8",
    )
    jd_path.write_text("Title: AI Engineer\nCompany: Example\nBody:\n- Build Python automation", encoding="utf-8")
    ingest_run(
        run_dir=run_dir,
        candidate_id="cand-001",
        candidate_resume_path=cv_path,
        jd_sources=[jd_path],
        config_path=config_path,
    )

    class _IncompleteAnalyzer:
        def analyze(self, candidate_id, candidate_resume_path, resume_text, jd_inputs):  # type: ignore[no-untyped-def]
            return AnalyzeFeedback(
                candidate_profile=CandidateProfile(
                    candidate_id=candidate_id,
                    base_resume_path=candidate_resume_path,
                    experiences=[],
                    projects=[],
                    skills=[],
                    industry_tags=[],
                    strengths=[],
                    constraints=[],
                    preferences=[],
                    core_claims=[],
                    verified_evidence=[],
                ),
                jd_profiles=[
                    JDProfile(
                        jd_id="jd-001",
                        title="",
                        company="",
                        cluster="",
                        responsibilities=[],
                        requirements=[],
                        keywords=[],
                        seniority="",
                        bonuses=[],
                        risk_signals=[],
                        source_type="text",
                        source_value="jd.txt",
                    )
                ],
                evidence_map={},
            )

    monkeypatch.setattr(
        "shotguncv_core.pipeline.build_analyzer_provider",
        lambda config, stage, run_dir: _IncompleteAnalyzer(),
    )

    try:
        analyze_run(run_dir)
    except ValueError as exc:
        assert "Structured analysis validation failed" in str(exc)
    else:
        raise AssertionError("analyze_run should reject incomplete structured artifacts")

    assert not (run_dir / "analyze" / "candidate_profile.json").exists()


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
    assert plan_payload[0]["apply_decision"] in {"apply", "hold"}
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


def test_requirement_matrix_filters_bad_requirements_and_dedupes_valid_evidence() -> None:
    candidate = CandidateProfile(
        candidate_id="cand-001",
        base_resume_path="fixtures/candidates/base_resume.md",
        experiences=[
            "Built LangGraph RAG review pipeline with retrieval metrics.",
            "Built LangGraph RAG review pipeline with retrieval metrics.",
        ],
        projects=[
            "Source: E:/PycharmProjects/jobPilot/fixtures/candidates/base_resume.md",
            "https://example.com",
        ],
        skills=["Python", "LangGraph", "RAG"],
        industry_tags=[],
        strengths=[],
        constraints=[],
        preferences=[],
        core_claims=["Source: fixtures/candidates/base_resume.md"],
        verified_evidence=["Built LangGraph RAG review pipeline with retrieval metrics."],
    )
    jd = JDProfile(
        jd_id="jd-026",
        title="AI Platform Engineer",
        company="ThetaWave",
        cluster="ai-platform",
        responsibilities=["Responsibilities:", "A I 平 台 架 构 设 计"],
        requirements=[
            "Relevance bucket",
            "Source signals",
            "Build LangGraph RAG review pipeline with retrieval metrics",
        ],
        keywords=["langgraph", "rag", "retrieval"],
        seniority="mid",
        bonuses=[],
        risk_signals=[],
        source_type="text",
        source_value="jd.txt",
    )

    requirements = _collect_jd_requirements(jd)
    matrix = _build_requirement_matrix(candidate, [jd])

    assert requirements == ["Build LangGraph RAG review pipeline with retrieval metrics"]
    assert [item.requirement_text for item in matrix] == requirements
    assert matrix[0].evidence_status == "verified"
    assert matrix[0].evidence_refs == ["Built LangGraph RAG review pipeline with retrieval metrics."]


def test_metadata_evidence_filter_rejects_source_paths_and_url_only_refs() -> None:
    metadata_items = [
        "Source: E:/PycharmProjects/jobPilot/fixtures/candidates/base_resume.md",
        "Source: fixtures/candidates/base_resume.md",
        "C:\\Users\\Lenovo\\resume.pdf",
        "/tmp/jobPilot/base_resume.md",
        "https://example.com/profile",
    ]

    assert all(_is_resume_metadata_evidence(item) for item in metadata_items)
    assert _matching_evidence_refs(
        "build langgraph rag review pipeline",
        [
            *metadata_items,
            "Built LangGraph RAG review pipeline with retrieval metrics.",
            "Built LangGraph RAG review pipeline with retrieval metrics.",
        ],
    ) == ["Built LangGraph RAG review pipeline with retrieval metrics."]


def test_candidate_profile_sanitizer_removes_metadata_before_artifacts() -> None:
    candidate = CandidateProfile(
        candidate_id="cand-001",
        base_resume_path="fixtures/candidates/base_resume.md",
        experiences=[
            "Source: fixtures/candidates/base_resume.md",
            "Built LangGraph RAG review pipeline with retrieval metrics.",
            "Built LangGraph RAG review pipeline with retrieval metrics.",
        ],
        projects=["https://example.com"],
        skills=["Python"],
        industry_tags=[],
        strengths=["Source: E:/PycharmProjects/jobPilot/fixtures/candidates/base_resume.md"],
        constraints=[],
        preferences=[],
        core_claims=["C:\\Users\\Lenovo\\resume.pdf"],
        verified_evidence=["Built LangGraph RAG review pipeline with retrieval metrics."],
    )

    clean = _sanitize_candidate_profile(candidate)

    assert clean.experiences == ["Built LangGraph RAG review pipeline with retrieval metrics."]
    assert clean.projects == []
    assert clean.strengths == []
    assert clean.core_claims == []
    assert clean.verified_evidence == ["Built LangGraph RAG review pipeline with retrieval metrics."]


def test_requirement_evidence_requires_distinctive_overlap_not_single_token() -> None:
    weak_candidate = CandidateProfile(
        candidate_id="cand-001",
        base_resume_path="fixtures/candidates/base_resume.md",
        experiences=["Built Python data scripts for reporting."],
        projects=[],
        skills=["Python"],
        industry_tags=[],
        strengths=[],
        constraints=[],
        preferences=[],
        core_claims=["Source: fixtures/candidates/base_resume.md"],
        verified_evidence=[],
    )
    requirement = "Build Python LangGraph RAG review pipeline"

    status, refs = _evaluate_requirement_evidence(
        requirement,
        "high_priority",
        weak_candidate,
        _candidate_search_text(weak_candidate),
    )

    assert status == "missing"
    assert refs == []


def test_verified_hard_gate_keeps_traceable_evidence_refs() -> None:
    candidate = CandidateProfile(
        candidate_id="cand-sean",
        base_resume_path="cv.pdf",
        experiences=[],
        projects=[],
        skills=["Python"],
        industry_tags=[],
        strengths=[],
        constraints=[],
        preferences=[],
        core_claims=["中央民族大学（985）｜计算机科学与技术（本科）"],
        verified_evidence=[
            "中央民族大学（985）｜计算机科学与技术（本科）",
            "核心课程：数据结构、操作系统、计算机网络、数据库系统、软件工程",
        ],
    )
    jd = JDProfile(
        jd_id="jd-pdd",
        title="后端研发工程师",
        company="PDD",
        cluster="backend",
        responsibilities=[],
        requirements=["本科及以上学历，计算机相关专业"],
        keywords=[],
        seniority="new-grad",
        bonuses=[],
        risk_signals=[],
        source_type="text",
        source_value="pdd.txt",
        must_have_requirements=["本科及以上学历，计算机相关专业"],
    )

    matrix = _build_requirement_matrix(candidate, [jd])
    hard_gate = matrix[0]
    checks = _requirement_matrix_quality_checks([jd], matrix)

    assert hard_gate.evidence_status == "verified"
    assert hard_gate.evidence_refs == ["中央民族大学（985）｜计算机科学与技术（本科）"]
    assert checks["verified_without_valid_refs_count"] == 0


def test_collect_jd_requirements_filters_chinese_platform_noise_and_section_labels() -> None:
    jd = JDProfile(
        jd_id="jd-wave",
        title="AI Agent 服务端开发工程师",
        company="Wave",
        cluster="ai-agent",
        responsibilities=[
            "该职位来源于BOSS直聘",
            "【岗位职责】",
            "工作地点：北京",
            "2026届校园招聘",
            "负责 AI Agent 服务端开发，建设可复用 Agent 工作流与工具调用能力",
        ],
        requirements=[
            "【任职要求】",
            "熟悉 LLM 技术栈，了解 LangChain / LangGraph / RAG 等框架或方法",
            "有 AI Agent / AI App 项目经验",
        ],
        keywords=["AI Agent", "LLM", "LangGraph"],
        seniority="mid",
        bonuses=["【加分项】", "有个人产品或开源项目"],
        risk_signals=[],
        source_type="text",
        source_value="wave.txt",
        nice_to_have_requirements=["【我们提供】"],
    )

    requirements = _collect_jd_requirements(jd)

    assert "该职位来源于BOSS直聘" not in requirements
    assert "【岗位职责】" not in requirements
    assert "【任职要求】" not in requirements
    assert "【加分项】" not in requirements
    assert "【我们提供】" not in requirements
    assert "工作地点：北京" not in requirements
    assert "2026届校园招聘" not in requirements
    assert requirements == [
        "熟悉 LLM 技术栈，了解 LangChain / LangGraph / RAG 等框架或方法",
        "有 AI Agent / AI App 项目经验",
        "负责 AI Agent 服务端开发，建设可复用 Agent 工作流与工具调用能力",
        "有个人产品或开源项目",
    ]


def test_wave_agent_requirements_match_candidate_profile_skills_projects_and_claims() -> None:
    candidate = CandidateProfile(
        candidate_id="cand-sean",
        base_resume_path="cv.pdf",
        experiences=[],
        projects=[
            "MergeWarden 代码审查与调试 Agent",
            "面向本地仓库、PR patch 与错误日志构建代码审查 / 调试 Agent，输出结构化 JSON",
            "设计 5 阶段 Agent 编排循环：prepare -> analyze -> execute_tools -> format -> continue/stop",
        ],
        skills=["Python", "FastAPI", "Redis", "LangChain", "LangGraph", "Qdrant", "RAG", "LLM", "Docker"],
        industry_tags=[],
        strengths=["MergeWarden 代码审查与调试 Agent"],
        constraints=[],
        preferences=[],
        core_claims=["个人项目 MergeWarden，覆盖 Agent 编排、工具调用、评测与测试模块"],
        verified_evidence=[
            "技术栈：Python、OpenAI-compatible API、Tool Calling、ReAct Loop、Docker、Pytest",
            "项目累计约 9.5K 行 Python，覆盖 Agent 编排、工具系统、评测与测试模块",
        ],
    )
    jd = JDProfile(
        jd_id="jd-wave",
        title="AI Agent 服务端开发工程师",
        company="Wave",
        cluster="ai-agent",
        responsibilities=["负责 AI Agent 服务端开发，建设可复用 Agent 工作流与工具调用能力"],
        requirements=[
            "熟悉 LLM 技术栈，了解 LangChain / LangGraph / RAG 等框架或方法",
            "有 AI Agent / AI App 项目经验",
        ],
        keywords=["AI Agent", "LLM", "LangGraph"],
        seniority="mid",
        bonuses=["有个人产品或开源项目"],
        risk_signals=[],
        source_type="text",
        source_value="wave.txt",
    )

    matrix = _build_requirement_matrix(candidate, [jd])

    by_text = {item.requirement_text: item for item in matrix}
    assert by_text["负责 AI Agent 服务端开发，建设可复用 Agent 工作流与工具调用能力"].evidence_status == "verified"
    assert _evaluate_requirement_evidence(
        "开发全球领先的 AI Agent / AI APP",
        "high_priority",
        candidate,
        _candidate_search_text(candidate),
    )[0] == "verified"
    assert by_text["熟悉 LLM 技术栈，了解 LangChain / LangGraph / RAG 等框架或方法"].evidence_status == "verified"
    assert by_text["有 AI Agent / AI App 项目经验"].evidence_status == "verified"
    assert by_text["有个人产品或开源项目"].evidence_status == "verified"


def test_score_conflict_marks_needs_review_and_uses_conservative_fusion() -> None:
    jd = JDProfile(
        jd_id="jd-wave",
        title="AI Agent 服务端开发工程师",
        company="Wave",
        cluster="ai-agent",
        responsibilities=[],
        requirements=[],
        keywords=["AI Agent"],
        seniority="mid",
        bonuses=[],
        risk_signals=[],
        source_type="text",
        source_value="wave.txt",
    )
    candidate = CandidateProfile(
        candidate_id="cand-sean",
        base_resume_path="cv.pdf",
        experiences=[],
        projects=["MergeWarden Agent project"],
        skills=["Python", "LLM"],
        industry_tags=[],
        strengths=[],
        constraints=[],
        preferences=[],
    )
    variant = ResumeVariant(
        variant_id="variant-jd-wave",
        variant_type="jd-specific",
        cluster="ai-agent",
        target_jd_ids=["jd-wave"],
        summary="Agent resume",
        emphasized_strengths=[],
        stretch_points=[],
        source_resume_path="cv.pdf",
    )
    rule_eval = RuleEvaluation(
        keyword_coverage=0.9,
        evidence_binding=0.9,
        untraceable_claim_flags=[],
        rewrite_distance=0.2,
        cluster_reuse_efficiency=0.8,
        fit_score=0.96,
        ats_score=0.96,
        evidence_score=0.96,
        stretch_score=0.9,
        gap_risk_score=0.1,
        rewrite_cost_score=0.4,
        overall_score=0.96,
        gaps=[],
    )
    assessment = LLMAssessment(
        jd_id="jd-wave",
        variant_id="variant-jd-wave",
        role_fit=0.85,
        evidence_quality=0.9,
        persuasiveness=0.8,
        interview_pressure_risk=0.25,
        application_worthiness="apply",
        evidence_citations=["MergeWarden Agent project"],
        decision_rationale="Strong Agent evidence.",
    )
    low_quality_matrix = [
        RequirementEvidence(
            jd_id="jd-wave",
            requirement_id="jd-wave-req-001",
            tier="high_priority",
            requirement_text="AI Agent 服务端开发",
            evidence_status="missing",
            risk_weight=0.7,
        )
    ]

    scorecard = _build_scorecard(
        jd,
        candidate,
        variant,
        rule_eval,
        assessment,
        "review",
        low_quality_matrix,
        "deterministic",
        "test",
    )

    assert scorecard.llm_overall_score - scorecard.final_overall_score <= 0.30
    assert "score_conflict" in scorecard.guardrail_flags
    assert "needs_review" in scorecard.guardrail_flags
    assert scorecard.final_decision_source == "v0.5.7-conservative-fusion+guardrail"


def test_report_run_surfaces_quality_warning_and_score_conflict(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    for stage in ["config", "analyze", "evaluate", "generate", "plan", "report"]:
        (run_dir / stage).mkdir(parents=True, exist_ok=True)
    (run_dir / "config" / "run_config.json").write_text(
        json.dumps(
            {
                "analyzer": {"provider": "deterministic", "model": ""},
                "generator": {"provider": "deterministic", "model": ""},
                "judge": {"provider": "deterministic", "model": ""},
                "planner": {"provider": "deterministic", "model": ""},
                "openai": {"base_url": None, "api_key_env": "OPENAI_API_KEY", "env_file": ".env"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "run_status.json").write_text(
        json.dumps({"status": "done", "quality_status": "warning", "quality_summary": "CV extraction quality is low."}),
        encoding="utf-8",
    )
    (run_dir / "analyze" / "candidate_profile.json").write_text(
        json.dumps(
            {
                "candidate_id": "cand-sean",
                "base_resume_path": "cv.pdf",
                "experiences": [],
                "projects": ["MergeWarden Agent project"],
                "skills": ["Python", "LLM"],
                "industry_tags": [],
                "strengths": [],
                "constraints": [],
                "preferences": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "analyze" / "jd_profiles.json").write_text(
        json.dumps(
            [
                {
                    "jd_id": "jd-wave",
                    "title": "AI Agent 服务端开发工程师",
                    "company": "Wave",
                    "cluster": "ai-agent",
                    "responsibilities": [],
                    "requirements": [],
                    "keywords": ["AI Agent"],
                    "seniority": "mid",
                    "bonuses": [],
                    "risk_signals": [],
                    "source_type": "text",
                    "source_value": "wave.txt",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "generate" / "resume_variants.json").write_text("[]", encoding="utf-8")
    (run_dir / "evaluate" / "gap_maps.json").write_text("[]", encoding="utf-8")
    (run_dir / "evaluate" / "scorecards.json").write_text(
        json.dumps(
            [
                {
                    "jd_id": "jd-wave",
                    "variant_id": "variant-jd-wave",
                    "fit_score": 0.96,
                    "ats_score": 0.96,
                    "evidence_score": 0.96,
                    "stretch_score": 0.9,
                    "gap_risk_score": 0.1,
                    "rewrite_cost_score": 0.4,
                    "overall_score": 0.96,
                    "ranking_version": "v0.3.0-llm-eval",
                    "judge_rationale": "Strong Agent evidence.",
                    "llm_overall_score": 0.83,
                    "final_overall_score": 0.53,
                    "final_decision_source": "v0.5.7-conservative-fusion+guardrail",
                    "guardrail_flags": ["score_conflict", "needs_review"],
                    "verified_fit_score": 0.0,
                    "rewrite_potential_score": 0.0,
                    "risk_score": 0.48,
                    "gate_status": "pass",
                    "gate_reasons": [],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "evaluate" / "ranking_explanations.json").write_text(
        json.dumps(
            [
                {
                    "jd_id": "jd-wave",
                    "variant_id": "variant-jd-wave",
                    "ranking_version": "v0.3.0-llm-eval",
                    "dimension_reasons": {"overall": "Strong Agent evidence; requirement scorer needs review."},
                    "positive_signals": ["real Agent project evidence"],
                    "risk_flags": ["score_conflict"],
                    "evidence_refs": ["MergeWarden Agent project"],
                    "decision_summary": "Strong Agent evidence; requirement scorer needs review.",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "plan" / "application_strategies.json").write_text(
        json.dumps(
            [
                {
                    "jd_id": "jd-wave",
                    "recommended_variant_id": "variant-jd-wave",
                    "priority_rank": 1,
                    "apply_decision": "manual_review",
                    "reason_summary": "岗位真实短板需与评分器证据漏判分开复核。",
                    "needs_jd_specific_variant": True,
                    "decision_confidence": 0.53,
                    "watchouts": ["score_conflict"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report_path = report_run(run_dir)
    report = report_path.read_text(encoding="utf-8")

    assert "该最终分数需复核/可靠性较低" in report
    assert "CV extraction quality is low." in report
    assert "score_conflict" in report
    assert "Final score requires manual review" in report


def test_analyze_quality_gate_reports_requirement_matrix_pollution(tmp_path: Path) -> None:
    candidate = CandidateProfile(
        candidate_id="cand-001",
        base_resume_path="fixtures/candidates/base_resume.md",
        experiences=["Built LangGraph RAG review pipeline with retrieval metrics."],
        projects=[],
        skills=["Python", "LangGraph"],
        industry_tags=[],
        strengths=[],
        constraints=[],
        preferences=[],
    )
    jd = JDProfile(
        jd_id="jd-026",
        title="AI Platform Engineer",
        company="ThetaWave",
        cluster="ai-platform",
        responsibilities=["Responsibilities:"],
        requirements=["Build LangGraph RAG review pipeline"],
        keywords=["langgraph", "rag"],
        seniority="mid",
        bonuses=[],
        risk_signals=[],
        source_type="text",
        source_value="jd.txt",
    )
    polluted_matrix = [
        RequirementEvidence(
            jd_id="jd-026",
            requirement_id="jd-026-req-001",
            tier="high_priority",
            requirement_text="Responsibilities:",
            evidence_status="verified",
            evidence_refs=[
                "Source: E:/PycharmProjects/jobPilot/fixtures/candidates/base_resume.md",
                "Source: E:/PycharmProjects/jobPilot/fixtures/candidates/base_resume.md",
            ],
        )
    ]

    _record_analyze_quality(
        tmp_path,
        {
            "jd_inputs": [{"content": "Title: AI Platform Engineer\nRequirements:\n- Build LangGraph RAG review pipeline"}],
            "candidate_resume_text": "Built LangGraph RAG review pipeline with retrieval metrics.",
        },
        candidate,
        [jd],
        polluted_matrix,
    )

    events = [
        json.loads(line)
        for line in (tmp_path / "logs" / "run_events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    gate = next(event for event in events if event.get("gate") == "requirement_matrix_quality")

    assert gate["status"] == "failed"
    assert gate["action"] == "block_golden_export"
    assert gate["checks"]["matrix_low_quality_requirement_count"] == 1
    assert gate["checks"]["invalid_evidence_ref_count"] == 1
    assert gate["checks"]["duplicate_evidence_ref_count"] == 1
    assert gate["checks"]["verified_without_valid_refs_count"] == 1


def test_analyze_quality_gate_blocks_zero_requirement_matrix_for_extracted_jd(tmp_path: Path) -> None:
    candidate = CandidateProfile(
        candidate_id="cand-001",
        base_resume_path="fixtures/candidates/base_resume.md",
        experiences=["Built LangGraph RAG review pipeline with retrieval metrics."],
        projects=[],
        skills=["Python", "LangGraph"],
        industry_tags=[],
        strengths=[],
        constraints=[],
        preferences=[],
    )
    jd = JDProfile(
        jd_id="jd-027",
        title="AI Platform Engineer",
        company="ThetaWave",
        cluster="ai-platform",
        responsibilities=["岗位职责", "职位标签"],
        requirements=["任职要求", "教育", "福利"],
        keywords=[],
        seniority="mid",
        bonuses=[],
        risk_signals=[],
        source_type="image/png",
        source_value="jd.png",
    )

    _record_analyze_quality(
        tmp_path,
        {
            "jd_inputs": [{"content": "岗位职责\n职位标签\n教育\n福利"}],
            "candidate_resume_text": "Built LangGraph RAG review pipeline with retrieval metrics.",
        },
        candidate,
        [jd],
        [],
    )

    events = [
        json.loads(line)
        for line in (tmp_path / "logs" / "run_events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    gate = next(event for event in events if event.get("gate") == "requirement_matrix_quality")

    assert gate["status"] == "failed"
    assert gate["action"] == "block_golden_export"
    assert gate["checks"]["zero_requirement_matrix_jd_count"] == 1
    assert gate["checks"]["zero_requirement_matrix_jd_examples"] == ["jd-027"]


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
