from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Callable

from shotguncv_agents.providers import (
    DeterministicPlannerProvider,
    build_analyzer_provider,
    build_generator_provider,
    build_judge_provider,
    build_planner_provider,
)
from shotguncv_core.inputs import InputDocument, InputExtractionOptions, collect_input_documents
from shotguncv_core.models import (
    ApplicationStrategy,
    CandidateProfile,
    GapMap,
    JDProfile,
    LLMFailure,
    LLMAssessment,
    PreflightGate,
    RankingExplanation,
    RequirementEvidence,
    ResumeVariant,
    ScoreCard,
)
from shotguncv_core.run_config import load_run_config, snapshot_run_config
from shotguncv_core.run_logs import (
    log_agent_reasoning_summary,
    log_fallback_used,
    log_input_extracted,
    log_input_resolved,
    log_quality_gate_checked,
)
from shotguncv_core.run_status import update_quality_status
from shotguncv_core.storage import dump_json, hydrate, load_json, stage_dir
from shotguncv_evals.rules import RuleEvaluation, evaluate_resume_fit


@dataclass(slots=True)
class AnalysisArtifacts:
    candidate: CandidateProfile
    jd_profiles: list[JDProfile]
    evidence_map: dict[str, object]


@dataclass(slots=True)
class GenerationArtifacts:
    variants: list[ResumeVariant]


@dataclass(slots=True)
class EvaluationArtifacts:
    scorecards: list[ScoreCard]
    gap_maps: list[GapMap]
    explanations: list[RankingExplanation]
    llm_assessments: list[LLMAssessment]
    llm_failures: list[LLMFailure]
    summary: dict[str, object]


@dataclass(slots=True)
class PlanArtifacts:
    strategies: list[ApplicationStrategy]


RANKING_VERSION = "v0.3.0-llm-eval"
SCORING_VERSION = "v0.5.7-requirement-gate"
EVALUATE_MAX_WORKERS = 4
PROJECT_ROOT = Path(__file__).resolve().parents[4]
FIXTURES_ROOT = PROJECT_ROOT / "fixtures"
UPLOAD_MANIFEST_PATH = Path("ingest") / "upload_manifest.json"
GATED_SKIP_STAGES = ["generate", "evaluate", "llm_judge", "plan"]


@dataclass(slots=True)
class _EvaluateWorkItem:
    jd_index: int
    variant_index: int
    jd: JDProfile
    variant: ResumeVariant


@dataclass(slots=True)
class _EvaluateTaskResult:
    jd_index: int
    variant_index: int
    jd_id: str
    variant_id: str
    rule_eval: RuleEvaluation
    scorecard: ScoreCard
    explanation: RankingExplanation
    assessment: LLMAssessment | None
    assessment_failure: LLMFailure | None
    status: str
    duration_ms: int


@dataclass(slots=True)
class _UploadInputMetadata:
    role: str
    original_name: str
    display_name: str
    relative_path: str
    size_bytes: int


def ingest_run(
    run_dir: Path,
    candidate_id: str,
    candidate_resume_path: Path | None = None,
    jd_sources: list[Path] | None = None,
    config_path: Path | None = None,
    candidate_sources: list[Path] | None = None,
    jd_input_sources: list[Path] | None = None,
    vision_fallback_enabled: bool | None = None,
    ocr_languages: str | None = None,
) -> Path:
    ingest_directory = stage_dir(run_dir, "ingest")
    snapshot_run_config(
        run_dir,
        config_path,
        vision_fallback_enabled=vision_fallback_enabled,
        ocr_languages=ocr_languages,
    )
    config = load_run_config(run_dir)
    extraction_options = _build_input_extraction_options(
        run_dir=run_dir,
        config=config,
        vision_fallback_enabled=vision_fallback_enabled,
        ocr_languages=ocr_languages,
    )
    candidate_paths = _resolve_candidate_sources(candidate_resume_path, candidate_sources)
    jd_paths = _resolve_jd_sources(jd_sources, jd_input_sources)
    candidate_inputs = collect_input_documents(candidate_paths, options=extraction_options)
    jd_inputs = collect_input_documents(jd_paths, options=extraction_options)
    log_input_resolved(
        run_dir,
        cli_cv_sources=len(candidate_paths),
        cli_jd_sources=len(jd_paths),
        resolved_cv_files=len(candidate_inputs),
        resolved_jd_files=len(jd_inputs),
        jd_text_blocks=sum(1 for document in jd_inputs if document.text.strip()),
    )
    for document in candidate_inputs:
        _log_input_document_extracted(run_dir, "cv", document)
    for document in jd_inputs:
        _log_input_document_extracted(run_dir, "jd", document)
    upload_metadata = _load_upload_manifest_metadata(run_dir)
    if not candidate_inputs:
        raise ValueError("At least one CV input is required for ingest.")
    if not jd_inputs:
        raise ValueError("At least one JD input is required for ingest.")
    if not _has_extractable_text(candidate_inputs):
        raise ValueError("At least one CV input must contain extractable text.")
    if not _has_extractable_text(jd_inputs):
        raise ValueError("At least one JD input must contain extractable text.")
    candidate_resume_text = _join_input_text(candidate_inputs)
    primary_resume_path = candidate_inputs[0].source_value
    candidate_manifest_items = [
        _input_document_to_manifest_item(document, role="cv", run_dir=run_dir, upload_metadata=upload_metadata)
        for document in candidate_inputs
    ]
    jd_manifest_items = [
        _input_document_to_jd_input(document, run_dir=run_dir, upload_metadata=upload_metadata)
        for document in jd_inputs
    ]
    manifest = {
        "candidate_id": candidate_id,
        "candidate_resume_path": primary_resume_path,
        "candidate_resume_text": candidate_resume_text,
        "candidate_inputs": candidate_manifest_items,
        "jd_inputs": jd_manifest_items,
        "input_warnings": _build_input_warnings([*candidate_manifest_items, *jd_manifest_items]),
    }
    return dump_json(ingest_directory / "manifest.json", manifest)


def analyze_run(run_dir: Path) -> AnalysisArtifacts:
    config = load_run_config(run_dir)
    manifest = load_json(run_dir / "ingest" / "manifest.json")
    analyzer = build_analyzer_provider(config, stage="analyze", run_dir=run_dir)

    feedback = analyzer.analyze(
        candidate_id=manifest["candidate_id"],
        candidate_resume_path=manifest["candidate_resume_path"],
        resume_text=manifest["candidate_resume_text"],
        jd_inputs=manifest["jd_inputs"],
    )

    analyze_directory = stage_dir(run_dir, "analyze")
    dump_json(analyze_directory / "candidate_profile.json", feedback.candidate_profile)
    dump_json(analyze_directory / "jd_profiles.json", feedback.jd_profiles)
    dump_json(analyze_directory / "evidence_map.json", feedback.evidence_map)
    requirement_matrix = _build_requirement_matrix(feedback.candidate_profile, feedback.jd_profiles)
    preflight_gates = _build_preflight_gates(requirement_matrix)
    dump_json(analyze_directory / "requirement_matrix.json", requirement_matrix)
    dump_json(analyze_directory / "preflight_gates.json", preflight_gates)
    _record_analyze_quality(run_dir, manifest, feedback.candidate_profile, feedback.jd_profiles)
    return AnalysisArtifacts(candidate=feedback.candidate_profile, jd_profiles=feedback.jd_profiles, evidence_map=feedback.evidence_map)


def generate_run(run_dir: Path) -> GenerationArtifacts:
    config = load_run_config(run_dir)
    candidate = hydrate(CandidateProfile, load_json(run_dir / "analyze" / "candidate_profile.json"))
    jd_profiles = hydrate(list[JDProfile], load_json(run_dir / "analyze" / "jd_profiles.json"))
    preflight_gates = _load_preflight_gates(run_dir)
    gate_index = {gate.jd_id: gate for gate in preflight_gates}
    requirement_matrix = _load_requirement_matrix(run_dir)
    generator = build_generator_provider(config, stage="generate", run_dir=run_dir)

    variants: list[ResumeVariant] = []
    for jd in jd_profiles:
        gate = gate_index.get(jd.jd_id)
        if gate is not None and gate.status != "pass":
            continue
        jd_requirements = [item for item in requirement_matrix if item.jd_id == jd.jd_id]
        variants.append(
            ResumeVariant(
                variant_id=f"variant-jd-{jd.jd_id}",
                variant_type="jd-specific",
                cluster=jd.cluster,
                target_jd_ids=[jd.jd_id],
                summary=generator.build_jd_summary(jd, candidate),
                emphasized_strengths=_select_emphasized_strengths(candidate, jd),
                stretch_points=_build_stretch_points(jd, candidate),
                source_resume_path=candidate.base_resume_path,
                safe_rewrites=_build_safe_rewrites(jd_requirements),
                simulated_supplements=_build_simulated_supplements(jd_requirements),
                forbidden_gaps=_build_forbidden_gaps(jd_requirements),
            )
        )

    dump_json(stage_dir(run_dir, "generate") / "resume_variants.json", variants)
    return GenerationArtifacts(variants=variants)


def evaluate_run(
    run_dir: Path,
    progress_cb: Callable[[dict[str, object]], None] | None = None,
) -> EvaluationArtifacts:
    config = load_run_config(run_dir)
    candidate = hydrate(CandidateProfile, load_json(run_dir / "analyze" / "candidate_profile.json"))
    jd_profiles = hydrate(list[JDProfile], load_json(run_dir / "analyze" / "jd_profiles.json"))
    variants = hydrate(list[ResumeVariant], load_json(run_dir / "generate" / "resume_variants.json"))
    evidence_map = _load_evidence_map(run_dir)
    requirement_matrix = _load_requirement_matrix(run_dir)
    preflight_gates = _load_preflight_gates(run_dir)
    preflight_gate_index = {gate.jd_id: gate for gate in preflight_gates}
    judge = build_judge_provider(config, stage="evaluate", run_dir=run_dir)
    runtime_provider = getattr(judge, "runtime_provider", config.judge.provider)
    runtime_model = getattr(judge, "runtime_model", config.judge.model)

    work_items = _build_evaluate_work_items(jd_profiles, variants)
    total_tasks = len(work_items)
    completed_tasks = 0

    task_results: list[_EvaluateTaskResult] = []
    with ThreadPoolExecutor(max_workers=EVALUATE_MAX_WORKERS) as executor:
        future_to_item = {
            executor.submit(
                _evaluate_work_item,
                item=item,
                judge=judge,
                candidate=candidate,
                evidence_map=evidence_map,
                requirement_matrix=requirement_matrix,
                provider=runtime_provider,
                model=runtime_model,
            ): item
            for item in work_items
        }
        for future in as_completed(future_to_item):
            item = future_to_item[future]
            try:
                result = future.result()
            except Exception as exc:
                result = _build_fallback_task_result(
                    item=item,
                    candidate=candidate,
                    requirement_matrix=requirement_matrix,
                    provider=runtime_provider,
                    model=runtime_model,
                    error=exc,
                )
            task_results.append(result)
            completed_tasks += 1
            if progress_cb is not None:
                progress_cb(
                    {
                        "completed": completed_tasks,
                        "total": total_tasks,
                        "jd_id": result.jd_id,
                        "variant_id": result.variant_id,
                        "status": result.status,
                        "duration_ms": result.duration_ms,
                    }
                )

    ordered_results = sorted(task_results, key=lambda item: (item.jd_index, item.variant_index))
    scorecards: list[ScoreCard] = [item.scorecard for item in ordered_results]
    explanations: list[RankingExplanation] = [item.explanation for item in ordered_results]
    llm_assessments: list[LLMAssessment] = [item.assessment for item in ordered_results if item.assessment is not None]
    llm_failures: list[LLMFailure] = [item.assessment_failure for item in ordered_results if item.assessment_failure is not None]
    preflight_scorecards: list[ScoreCard] = []
    preflight_explanations: list[RankingExplanation] = []
    for jd in jd_profiles:
        gate = preflight_gate_index.get(jd.jd_id)
        if gate is None or gate.status == "pass":
            continue
        scorecard = _build_preflight_scorecard(jd, gate, runtime_provider, runtime_model)
        preflight_scorecards.append(scorecard)
        preflight_explanations.append(_build_preflight_explanation(jd, gate, scorecard))
    scorecards.extend(preflight_scorecards)
    explanations.extend(preflight_explanations)

    grouped_by_jd: dict[int, list[_EvaluateTaskResult]] = {}
    for item in ordered_results:
        grouped_by_jd.setdefault(item.jd_index, []).append(item)

    gap_maps: list[GapMap] = []
    eval_summary: list[dict[str, object]] = []
    for jd_index, jd in enumerate(jd_profiles):
        jd_items = grouped_by_jd.get(jd_index, [])
        best_gap_item = max(jd_items, key=lambda it: it.rule_eval.overall_score) if jd_items else None
        gap_items = best_gap_item.rule_eval.gaps if best_gap_item else []
        gap_maps.append(GapMap(jd_id=jd.jd_id, candidate_id=candidate.candidate_id, items=gap_items))

        if not jd_items:
            preflight_scorecard = next((scorecard for scorecard in preflight_scorecards if scorecard.jd_id == jd.jd_id), None)
            preflight_explanation = next((explanation for explanation in preflight_explanations if explanation.jd_id == jd.jd_id), None)
            if preflight_scorecard is not None:
                preflight_gate = preflight_gate_index.get(jd.jd_id)
                eval_summary.append(
                    {
                        "jd_id": jd.jd_id,
                        "title": jd.title,
                        "top_variant_id": preflight_scorecard.variant_id,
                        "gap_count": len(gap_items),
                        "top_reasons": (
                            preflight_explanation.risk_flags[:2]
                            if preflight_explanation
                            else (preflight_gate.reasons[:2] if preflight_gate else [])
                        )
                        or ["preflight gate blocked this JD"],
                    }
                )
            continue

        best_item = max(jd_items, key=lambda it: ScoreCard.ranking_key(it.scorecard))
        eval_summary.append(
            {
                "jd_id": jd.jd_id,
                "title": jd.title,
                "top_variant_id": best_item.variant_id,
                "gap_count": len(gap_items),
                "top_reasons": best_item.explanation.positive_signals[:2]
                or [best_item.explanation.dimension_reasons["overall"]],
            }
        )

    evaluate_directory = stage_dir(run_dir, "evaluate")
    dump_json(evaluate_directory / "scorecards.json", scorecards)
    dump_json(evaluate_directory / "gap_maps.json", gap_maps)
    dump_json(evaluate_directory / "ranking_explanations.json", explanations)
    dump_json(evaluate_directory / "llm_assessments.json", llm_assessments)
    dump_json(evaluate_directory / "llm_failures.json", llm_failures)
    dump_json(evaluate_directory / "eval_summary.json", eval_summary)
    _record_evaluate_quality(run_dir, scorecards, llm_failures)
    return EvaluationArtifacts(
        scorecards=scorecards,
        gap_maps=gap_maps,
        explanations=explanations,
        llm_assessments=llm_assessments,
        llm_failures=llm_failures,
        summary={"items": eval_summary},
    )


def plan_run(run_dir: Path) -> PlanArtifacts:
    config = load_run_config(run_dir)
    scorecards = hydrate(list[ScoreCard], load_json(run_dir / "evaluate" / "scorecards.json"))
    gap_maps = hydrate(list[GapMap], load_json(run_dir / "evaluate" / "gap_maps.json"))
    explanations = _load_explanations_with_fallback(run_dir, scorecards, gap_maps)
    jd_profiles = hydrate(list[JDProfile], load_json(run_dir / "analyze" / "jd_profiles.json"))
    candidate = hydrate(CandidateProfile, load_json(run_dir / "analyze" / "candidate_profile.json"))
    variants = hydrate(list[ResumeVariant], load_json(run_dir / "generate" / "resume_variants.json"))
    llm_assessments = _load_llm_assessments_with_fallback(run_dir)
    llm_failures = _load_llm_failures_with_fallback(run_dir)
    planner = build_planner_provider(config, stage="plan", run_dir=run_dir)

    best_by_jd: dict[str, ScoreCard] = {}
    for scorecard in scorecards:
        current = best_by_jd.get(scorecard.jd_id)
        if current is None or ScoreCard.ranking_key(scorecard) > ScoreCard.ranking_key(current):
            best_by_jd[scorecard.jd_id] = scorecard

    ordered = sorted(best_by_jd.values(), key=ScoreCard.ranking_key, reverse=True)
    gap_index = {gap_map.jd_id: gap_map for gap_map in gap_maps}
    explanation_index = {(explanation.jd_id, explanation.variant_id): explanation for explanation in explanations}
    jd_index = {jd.jd_id: jd for jd in jd_profiles}
    variant_index = {variant.variant_id: variant for variant in variants}
    assessment_index = {(item.jd_id, item.variant_id): item for item in llm_assessments}
    failure_index = {(item.jd_id, item.variant_id): item for item in llm_failures}
    fallback_planner = DeterministicPlannerProvider()

    strategies: list[ApplicationStrategy] = []
    for rank, scorecard in enumerate(ordered, start=1):
        jd = jd_index[scorecard.jd_id]
        if scorecard.gate_status != "pass":
            strategy = _build_preflight_strategy(jd, scorecard, rank)
            strategies.append(strategy)
            log_agent_reasoning_summary(
                run_dir,
                stage="plan",
                agent="planner",
                summary=strategy.reason_summary,
                decision_inputs=[
                    f"jd_id={strategy.jd_id}",
                    f"variant_id={strategy.recommended_variant_id}",
                    f"gate_status={scorecard.gate_status}",
                    f"decision={strategy.apply_decision}",
                ],
            )
            continue
        variant = variant_index[scorecard.variant_id]
        assessment = assessment_index.get((scorecard.jd_id, scorecard.variant_id))
        assessment_failure = failure_index.get((scorecard.jd_id, scorecard.variant_id))
        try:
            feedback = planner.build_strategy(
                jd=jd,
                candidate=candidate,
                assessment=assessment,
                top_variant=variant,
                final_score=scorecard.final_overall_score or scorecard.overall_score,
                guardrail_flags=scorecard.guardrail_flags,
                assessment_failure_reason=_format_llm_failure_reason(assessment_failure),
            )
        except Exception:
            feedback = fallback_planner.build_strategy(
                jd=jd,
                candidate=candidate,
                assessment=assessment,
                top_variant=variant,
                final_score=scorecard.final_overall_score or scorecard.overall_score,
                guardrail_flags=scorecard.guardrail_flags,
                assessment_failure_reason=_format_llm_failure_reason(assessment_failure),
            )

        strategy = feedback.strategy
        strategy.priority_rank = rank
        if not strategy.decision_drivers:
            explanation = explanation_index[(scorecard.jd_id, scorecard.variant_id)]
            strategy.decision_drivers = explanation.positive_signals[:3] or [explanation.dimension_reasons["overall"]]
        if not strategy.watchouts:
            strategy.watchouts = scorecard.guardrail_flags or ["No material watchouts surfaced by current checks."]
        if not strategy.recommended_actions:
            strategy.recommended_actions = ["Refine 2-3 evidence-backed bullets before applying."]
        if not strategy.interview_prep_points:
            strategy.interview_prep_points = jd.interview_focus_areas[:3]
        strategies.append(strategy)
        log_agent_reasoning_summary(
            run_dir,
            stage="plan",
            agent="planner",
            summary=strategy.reason_summary,
            decision_inputs=[
                f"jd_id={strategy.jd_id}",
                f"variant_id={strategy.recommended_variant_id}",
                f"final_score={(scorecard.final_overall_score or scorecard.overall_score):.2f}",
                f"decision={strategy.apply_decision}",
            ],
        )

    dump_json(stage_dir(run_dir, "plan") / "application_strategies.json", strategies)
    return PlanArtifacts(strategies=strategies)


def report_run(run_dir: Path) -> Path:
    load_run_config(run_dir)
    candidate = hydrate(CandidateProfile, load_json(run_dir / "analyze" / "candidate_profile.json"))
    jd_profiles = hydrate(list[JDProfile], load_json(run_dir / "analyze" / "jd_profiles.json"))
    scorecards = hydrate(list[ScoreCard], load_json(run_dir / "evaluate" / "scorecards.json"))
    strategies = hydrate(list[ApplicationStrategy], load_json(run_dir / "plan" / "application_strategies.json"))
    explanations = _load_explanations_with_fallback(run_dir, scorecards, hydrate(list[GapMap], load_json(run_dir / "evaluate" / "gap_maps.json")))

    jd_index = {jd.jd_id: jd for jd in jd_profiles}
    score_index = {(score.jd_id, score.variant_id): score for score in scorecards}
    explanation_index = {(explanation.jd_id, explanation.variant_id): explanation for explanation in explanations}

    lines = [
        "# ShotgunCV v0.3.0 LLM Eval Summary",
        "",
        f"- Candidate: `{candidate.candidate_id}`",
        f"- Run directory: `{run_dir}`",
        "",
        "## Ranked Application Strategy",
        "",
    ]

    for strategy in strategies:
        jd = jd_index[strategy.jd_id]
        scorecard = score_index[(strategy.jd_id, strategy.recommended_variant_id)]
        explanation = explanation_index[(strategy.jd_id, strategy.recommended_variant_id)]
        lines.extend(
            [
                f"### {strategy.priority_rank}. {jd.title} @ {jd.company}",
                f"- Apply decision: `{strategy.apply_decision}` (confidence `{strategy.decision_confidence:.2f}`)",
                f"- Why worth / not worth: {strategy.reason_summary}",
                f"- Evidence that holds: {', '.join(explanation.evidence_refs[:3]) or 'Evidence mapping is limited.'}",
                f"- Interview danger points: {', '.join(strategy.watchouts[:4])}",
                f"- If only revise 3 resume items: {', '.join(strategy.resume_revision_tasks[:3]) or ', '.join(strategy.recommended_actions[:3])}",
                f"- Final score: `{(scorecard.final_overall_score or scorecard.overall_score):.2f}` via `{scorecard.final_decision_source}`",
                "",
            ]
        )

    report_path = stage_dir(run_dir, "report") / "summary.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _build_requirement_matrix(candidate: CandidateProfile, jd_profiles: list[JDProfile]) -> list[RequirementEvidence]:
    matrix: list[RequirementEvidence] = []
    candidate_text = _candidate_search_text(candidate)
    for jd in jd_profiles:
        for index, requirement in enumerate(_collect_jd_requirements(jd), start=1):
            tier = _classify_requirement_tier(requirement)
            evidence_status, evidence_refs = _evaluate_requirement_evidence(requirement, tier, candidate, candidate_text)
            matrix.append(
                RequirementEvidence(
                    jd_id=jd.jd_id,
                    requirement_id=f"{jd.jd_id}-req-{index:03d}",
                    tier=tier,
                    requirement_text=requirement,
                    evidence_status=evidence_status,
                    evidence_refs=evidence_refs,
                    fabrication_policy=_fabrication_policy_for(tier, evidence_status),
                    risk_weight=_risk_weight_for_tier(tier),
                )
            )
    return matrix


def _build_preflight_gates(requirement_matrix: list[RequirementEvidence]) -> list[PreflightGate]:
    gates: list[PreflightGate] = []
    jd_ids = sorted({item.jd_id for item in requirement_matrix})
    for jd_id in jd_ids:
        jd_requirements = [item for item in requirement_matrix if item.jd_id == jd_id]
        mismatches = [
            item for item in jd_requirements if item.tier == "hard_gate" and item.evidence_status == "mismatch"
        ]
        missing = [item for item in jd_requirements if item.tier == "hard_gate" and item.evidence_status == "missing"]
        if mismatches:
            gates.append(
                PreflightGate(
                    jd_id=jd_id,
                    status="blocked",
                    reasons=[f"hard_gate_mismatch: {item.requirement_text}" for item in mismatches],
                    skipped_stages=GATED_SKIP_STAGES,
                    user_action="该 JD 的硬门槛与 CV 明确不符，默认不继续生成。",
                )
            )
        elif missing:
            gates.append(
                PreflightGate(
                    jd_id=jd_id,
                    status="needs_review",
                    reasons=[f"hard_gate_missing: {item.requirement_text}" for item in missing],
                    skipped_stages=GATED_SKIP_STAGES,
                    user_action="补充或确认硬门槛证据后再继续。",
                )
            )
        else:
            gates.append(PreflightGate(jd_id=jd_id, status="pass"))
    return gates


def _collect_jd_requirements(jd: JDProfile) -> list[str]:
    seen: set[str] = set()
    requirements: list[str] = []
    for source in [jd.must_have_requirements, jd.requirements, jd.responsibilities, jd.nice_to_have_requirements, jd.bonuses]:
        for raw_item in source:
            item = _normalize_jd_requirement_item(raw_item)
            key = item.lower()
            if not item or _is_jd_ui_noise(item) or key in seen:
                continue
            seen.add(key)
            requirements.append(item)
    return requirements


def _classify_requirement_tier(requirement: str) -> str:
    text = requirement.lower()
    if _is_hard_gate_requirement(text) or _has_explicit_year_requirement(text):
        return "hard_gate"
    high_needles = [
        "python",
        "llm",
        "automation",
        "agent",
        "evaluation",
        "ranking",
        "prompt",
        "rag",
        "langchain",
        "langgraph",
        "qdrant",
        "fastapi",
        "pydantic",
        "docker",
        "redis",
        "machine learning",
        "deep learning",
        "模型",
        "算法",
    ]
    if any(needle in text for needle in high_needles):
        return "high_priority"
    medium_needles = ["项目", "经历", "场景", "project", "experience", "case study"]
    if any(needle in text for needle in medium_needles):
        return "medium_priority"
    return "nice_to_have"


def _evaluate_requirement_evidence(
    requirement: str,
    tier: str,
    candidate: CandidateProfile,
    candidate_text: str,
) -> tuple[str, list[str]]:
    requirement_text = requirement.lower()
    candidate_evidence = candidate.experiences + candidate.projects + candidate.skills + candidate.verified_evidence + candidate.core_claims
    refs = _matching_evidence_refs(requirement_text, candidate_evidence)
    if tier == "hard_gate":
        status = _evaluate_hard_gate(requirement_text, candidate_text)
        return status, refs if status in {"verified", "inferred"} else []
    if refs:
        return "verified", refs
    if tier == "medium_priority":
        return "simulatable", []
    return "missing", []


def _evaluate_hard_gate(requirement: str, candidate_text: str) -> str:
    if _requires_master_only(requirement) and _has_bachelor(candidate_text) and not _has_master_or_above(candidate_text):
        return "mismatch"
    checks: list[bool] = []
    if any(item in requirement for item in ["学历", "本科", "bachelor", "degree"]):
        checks.append(any(item in candidate_text for item in ["本科", "bachelor", "degree", "硕士", "master", "phd", "博士"]))
    if any(item in requirement for item in ["硕士", "master"]) and not any(item in requirement for item in ["本科", "bachelor"]):
        checks.append(_has_master_or_above(candidate_text))
    if any(item in requirement for item in ["计算机", "专业", "computer", "cs"]):
        checks.append(any(item in candidate_text for item in ["计算机", "computer", "computer science", "cs", "software"]))
    if any(item in requirement for item in ["证书", "认证", "certificate", "certification", "pmp"]):
        cert_tokens = [token for token in ["pmp", "aws", "cpa", "cfa"] if token in requirement]
        checks.append(any(token in candidate_text for token in cert_tokens) if cert_tokens else "证书" in candidate_text)
    if _has_explicit_year_requirement(requirement):
        required_years = _extract_required_years(requirement)
        candidate_years = _extract_required_years(candidate_text)
        checks.append(candidate_years >= required_years if required_years else bool(candidate_years))
    if not checks:
        return "missing"
    return "verified" if all(checks) else "missing"


def _matching_evidence_refs(requirement: str, candidate_items: list[str]) -> list[str]:
    tokens = [token for token in _requirement_tokens(requirement) if len(token) >= 2]
    refs: list[str] = []
    for item in candidate_items:
        if _is_resume_metadata_evidence(item):
            continue
        lowered = item.lower()
        if any(token in lowered for token in tokens):
            refs.append(item)
    return refs[:3]


def _normalize_jd_requirement_item(item: str) -> str:
    return item.strip().strip("-*•").strip()


def _is_jd_ui_noise(item: str) -> bool:
    text = item.strip().lower()
    if not text:
        return True
    if text.startswith("@"):
        return True
    exact_noise = {
        "apply",
        "save",
        "copy link",
        "apply save copy link",
        "perks/benefits",
        "perks",
        "benefits",
        "mentoring",
        "remote work",
        "skills/tech-stack",
        "skills",
        "tech-stack",
        "education",
    }
    if text in exact_noise:
        return True
    noise_patterns = [
        r"\bpublished\b",
        r"\bposted\b",
        r"\bago\b",
        r"\busd\b",
        r"\$\s*\d",
        r"\b\d+\s*k\s*[-–]\s*\d+\s*k\b",
        r"\bmid[- ]level\b",
        r"\bsenior[- ]level\b",
    ]
    return any(re.search(pattern, text) for pattern in noise_patterns)


def _is_hard_gate_requirement(text: str) -> bool:
    if _looks_like_label_only(text):
        return False
    education_terms = ["学历", "本科", "硕士", "博士", "bachelor", "master", "phd", "degree"]
    credential_terms = ["证书", "认证", "持有", "certification", "certificate", "license", "pmp"]
    authorization_terms = ["工作许可", "签证", "work authorization", "visa", "sponsorship"]
    language_terms = ["cet", "ielts", "toefl"]
    if any(term in text for term in education_terms + credential_terms + authorization_terms + language_terms):
        return True
    if "专业" in text and any(term in text for term in ["学历", "本科", "硕士", "博士", "degree", "相关"]):
        return True
    return False


def _looks_like_label_only(text: str) -> bool:
    normalized = text.strip().strip(":：")
    return normalized in {"education", "skills", "requirements", "responsibilities", "perks", "benefits"}


def _requires_master_only(requirement: str) -> bool:
    text = requirement.lower()
    if not any(item in text for item in ["硕士", "master"]):
        return False
    if any(item in text for item in ["本科", "bachelor"]):
        return False
    if any(item in text for item in ["preferred", "nice to have", "plus", "加分", "优先"]):
        return False
    return True


def _has_bachelor(text: str) -> bool:
    return any(item in text for item in ["本科", "bachelor"])


def _has_master_or_above(text: str) -> bool:
    return any(item in text for item in ["硕士", "master", "博士", "phd"])


def _is_resume_metadata_evidence(item: str) -> bool:
    text = item.strip().lower()
    return any(
        marker in text
        for marker in [
            "邮箱",
            "email:",
            "e-mail:",
            "个人主页",
            "homepage:",
            "github:",
            "linkedin:",
            "电话",
            "phone:",
        ]
    )


def _requirement_tokens(text: str) -> list[str]:
    normalized = text.replace("，", " ").replace("、", " ").replace(",", " ").replace("/", " ")
    tokens = [token.strip("-().:; ") for token in normalized.split()]
    cjk_tokens = [chunk for chunk in normalized.replace(" ", "").split("。") if chunk]
    tokens.extend(cjk_tokens)
    return [token.lower() for token in tokens if token.strip()]


def _candidate_search_text(candidate: CandidateProfile) -> str:
    return " ".join(
        candidate.experiences
        + candidate.projects
        + candidate.skills
        + candidate.industry_tags
        + candidate.strengths
        + candidate.constraints
        + candidate.core_claims
        + candidate.verified_evidence
    ).lower()


def _has_explicit_year_requirement(text: str) -> bool:
    return _extract_required_years(text) > 0


def _extract_required_years(text: str) -> int:
    import re

    match = re.search(r"(\d+)\s*(?:\+|年以上|年以上|years?|yrs?)", text.lower())
    return int(match.group(1)) if match else 0


def _fabrication_policy_for(tier: str, evidence_status: str) -> str:
    if tier == "hard_gate" or evidence_status in {"missing", "mismatch"} and tier == "high_priority":
        return "never_fabricate"
    if tier == "medium_priority" and evidence_status == "simulatable":
        return "simulate_allowed"
    return "rewrite_only"


def _risk_weight_for_tier(tier: str) -> float:
    return {"hard_gate": 1.0, "high_priority": 0.7, "medium_priority": 0.45, "nice_to_have": 0.2}.get(tier, 0.4)


def _build_safe_rewrites(requirements: list[RequirementEvidence]) -> list[str]:
    verified = [item.requirement_text for item in requirements if item.evidence_status in {"verified", "inferred"}]
    return [f"Use verified evidence for: {item}" for item in verified[:3]]


def _build_simulated_supplements(requirements: list[RequirementEvidence]) -> list[str]:
    simulatable = [item.requirement_text for item in requirements if item.evidence_status == "simulatable"]
    return [f"待核实模拟补强：{item}" for item in simulatable[:3]]


def _build_forbidden_gaps(requirements: list[RequirementEvidence]) -> list[str]:
    forbidden = [
        item.requirement_text
        for item in requirements
        if item.fabrication_policy == "never_fabricate" and item.evidence_status in {"missing", "mismatch", "forbidden_to_fabricate"}
    ]
    return [f"禁止编造：{item}" for item in forbidden[:3]]


def _select_emphasized_strengths(candidate: CandidateProfile, jd: JDProfile) -> list[str]:
    strengths = []
    for keyword in jd.keywords:
        for candidate_line in candidate.experiences + candidate.skills:
            if keyword.split()[0] in candidate_line.lower():
                strengths.append(candidate_line)
                break
    return strengths[:3] or candidate.strengths[:2]


def _build_stretch_points(jd: JDProfile, candidate: CandidateProfile) -> list[str]:
    candidate_text = " ".join(candidate.experiences + candidate.projects + candidate.skills).lower()
    stretch_points = [keyword for keyword in jd.keywords if keyword.lower() not in candidate_text]
    return stretch_points[:3] or [jd.keywords[-1]]


def _resolve_candidate_sources(
    candidate_resume_path: Path | None,
    candidate_sources: list[Path] | None,
) -> list[Path]:
    sources = list(candidate_sources or [])
    if candidate_resume_path is not None:
        sources.insert(0, candidate_resume_path)
    return sources


def _resolve_jd_sources(
    jd_sources: list[Path] | None,
    jd_input_sources: list[Path] | None,
) -> list[Path]:
    sources = list(jd_input_sources or [])
    if jd_sources:
        sources = list(jd_sources) + sources
    return sources


def _join_input_text(documents: list[InputDocument]) -> str:
    chunks = []
    for document in documents:
        text = document.text.strip()
        if text:
            chunks.append(f"Source: {document.source_value}\n{text}")
    return "\n\n".join(chunk for chunk in chunks if chunk.strip())


def _log_input_document_extracted(run_dir: Path, role: str, document: InputDocument) -> None:
    fallback_from = None
    warning = document.extraction_error or None
    if document.media_type == "application/pdf" and document.extraction_status in {"ocr", "vision"}:
        fallback_from = "local_pdf"
    elif document.extraction_status in {"vision", "sidecar"} and document.extraction_error:
        fallback_from = "local_ocr"
    log_input_extracted(
        run_dir,
        role=role,
        provider=document.extraction_provider,
        status=document.extraction_status,
        text_chars=len(document.text or ""),
        fallback_from=fallback_from,
        warning=warning,
    )
    if fallback_from is not None and document.extraction_provider:
        log_fallback_used(
            run_dir,
            stage="ingest",
            operation=f"{role}_input_extraction",
            from_provider=fallback_from,
            to_provider=document.extraction_provider,
            reason=warning or f"{document.extraction_status} fallback used",
        )


def _record_analyze_quality(
    run_dir: Path,
    manifest: dict[str, object],
    candidate: CandidateProfile,
    jd_profiles: list[JDProfile],
) -> None:
    jd_inputs = manifest.get("jd_inputs", [])
    jd_text_count = sum(
        1
        for item in jd_inputs
        if isinstance(item, dict) and str(item.get("content") or item.get("text") or "").strip()
    )
    empty_title_count = sum(1 for jd in jd_profiles if not jd.title.strip())
    empty_responsibilities_count = sum(1 for jd in jd_profiles if not jd.responsibilities)
    empty_requirements_count = sum(1 for jd in jd_profiles if not jd.requirements)
    jd_gate_failed = bool(
        jd_text_count
        and jd_profiles
        and (empty_title_count or empty_responsibilities_count or empty_requirements_count)
    )
    log_quality_gate_checked(
        run_dir,
        stage="analyze",
        gate="jd_profile_completeness",
        status="failed" if jd_gate_failed else "ok",
        checks={
            "jd_count": len(jd_profiles),
            "jd_text_blocks": jd_text_count,
            "empty_title_count": empty_title_count,
            "empty_responsibilities_count": empty_responsibilities_count,
            "empty_requirements_count": empty_requirements_count,
        },
        action="warn" if jd_gate_failed else "continue",
    )

    resume_text = str(manifest.get("candidate_resume_text", ""))
    control_char_count = sum(1 for char in resume_text if ord(char) < 32 and char not in "\r\n\t")
    visible_chars = sum(1 for char in resume_text if char.isprintable() and not char.isspace())
    control_char_ratio = round(control_char_count / max(1, len(resume_text)), 4)
    cv_warning = visible_chars < 120 or control_char_ratio > 0.05 or not candidate.experiences
    log_quality_gate_checked(
        run_dir,
        stage="analyze",
        gate="cv_text_quality",
        status="warning" if cv_warning else "ok",
        checks={
            "text_chars": len(resume_text),
            "visible_chars": visible_chars,
            "control_char_ratio": control_char_ratio,
            "experience_count": len(candidate.experiences),
        },
        action="warn" if cv_warning else "continue",
    )

    summaries: list[str] = []
    if jd_gate_failed:
        summaries.append("JD profile fields are incomplete.")
    if cv_warning:
        summaries.append("CV extraction quality is low.")
    if summaries:
        update_quality_status(run_dir, "warning", " ".join(summaries))


def _record_evaluate_quality(run_dir: Path, scorecards: list[ScoreCard], llm_failures: list[LLMFailure]) -> None:
    fallback_count = sum(1 for scorecard in scorecards if scorecard.final_decision_source == "guardrail-fallback")
    weak_high_score_count = sum(
        1
        for scorecard in scorecards
        if (scorecard.overall_score >= 0.85 and scorecard.llm_evidence_score <= 0.35)
        or "llm_assessment_missing" in scorecard.guardrail_flags
    )
    status = "warning" if fallback_count or weak_high_score_count or llm_failures else "ok"
    log_quality_gate_checked(
        run_dir,
        stage="evaluate",
        gate="score_consistency",
        status=status,
        checks={
            "scorecard_count": len(scorecards),
            "fallback_count": fallback_count,
            "llm_failure_count": len(llm_failures),
            "weak_high_score_count": weak_high_score_count,
        },
        action="warn" if status == "warning" else "continue",
    )
    for failure in llm_failures:
        log_fallback_used(
            run_dir,
            stage="evaluate",
            operation="judge_assess",
            from_provider=failure.provider,
            to_provider="guardrail-fallback",
            reason=f"{failure.error_type}: {failure.error_message}",
        )
    if status == "warning":
        update_quality_status(run_dir, "warning", "Evaluation used fallback or score consistency warnings.")


def _has_extractable_text(documents: list[InputDocument]) -> bool:
    return any(document.text.strip() for document in documents)


def _build_input_warnings(items: list[dict[str, object]]) -> list[dict[str, object]]:
    warnings: list[dict[str, object]] = []
    for item in items:
        if item.get("extraction_status") != "unparseable":
            continue
        warnings.append(
            {
                "role": item.get("role", ""),
                "relative_path": item.get("relative_path", ""),
                "original_name": item.get("original_name", ""),
                "extraction_error": item.get("extraction_error", ""),
            }
        )
    return warnings


def _input_document_to_manifest_item(
    document: InputDocument,
    role: str,
    run_dir: Path,
    upload_metadata: dict[str, _UploadInputMetadata],
) -> dict[str, object]:
    source_path = Path(document.source_value)
    upload_item = upload_metadata.get(_normalize_manifest_path(_relative_to_run_dir(source_path, run_dir)))
    relative_path = upload_item.relative_path if upload_item is not None else _display_relative_path(source_path, run_dir)
    source_origin = _resolve_source_origin(source_path=source_path, upload_item=upload_item)
    return {
        "role": upload_item.role if upload_item is not None else role,
        "source_origin": source_origin,
        "source_type": document.source_type,
        "source_value": document.source_value,
        "original_name": upload_item.original_name if upload_item is not None else document.original_name or source_path.name,
        "display_name": upload_item.display_name if upload_item is not None else "",
        "relative_path": relative_path,
        "size_bytes": upload_item.size_bytes if upload_item is not None else document.size_bytes,
        "media_type": document.media_type,
        "text": document.text,
        "extraction_status": document.extraction_status,
        "extraction_provider": document.extraction_provider,
        "extraction_error": document.extraction_error,
    }


def _input_document_to_jd_input(
    document: InputDocument,
    run_dir: Path,
    upload_metadata: dict[str, _UploadInputMetadata],
) -> dict[str, object]:
    payload = _input_document_to_manifest_item(document, role="jd", run_dir=run_dir, upload_metadata=upload_metadata)
    payload["content"] = document.text
    return payload


def _load_upload_manifest_metadata(run_dir: Path) -> dict[str, _UploadInputMetadata]:
    manifest_path = run_dir / UPLOAD_MANIFEST_PATH
    if not manifest_path.exists():
        return {}
    payload = load_json(manifest_path)
    if not isinstance(payload, dict):
        return {}
    files = payload.get("files")
    if not isinstance(files, list):
        return {}
    metadata: dict[str, _UploadInputMetadata] = {}
    for item in files:
        if not isinstance(item, dict):
            continue
        relative_path = str(item.get("storedRelativePath", "")).replace("\\", "/").strip()
        if not relative_path:
            continue
        metadata[_normalize_manifest_path(relative_path)] = _UploadInputMetadata(
            role=str(item.get("role", "")),
            original_name=str(item.get("originalName", "")),
            display_name=str(item.get("displayName", "")),
            relative_path=relative_path,
            size_bytes=_coerce_int(item.get("sizeBytes")),
        )
    return metadata


def _relative_to_run_dir(path: Path, run_dir: Path) -> str:
    try:
        return path.resolve().relative_to(run_dir.resolve()).as_posix()
    except ValueError:
        return str(path).replace("\\", "/")


def _display_relative_path(path: Path, run_dir: Path) -> str:
    if _is_under(path, FIXTURES_ROOT):
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    try:
        return path.resolve().relative_to(run_dir.resolve()).as_posix()
    except ValueError:
        try:
            return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
        except ValueError:
            return str(path)


def _resolve_source_origin(source_path: Path, upload_item: _UploadInputMetadata | None) -> str:
    if upload_item is not None:
        return "upload"
    if _is_under(source_path, FIXTURES_ROOT):
        return "fixture"
    return "cli"


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _normalize_manifest_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def _coerce_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _build_input_extraction_options(
    run_dir: Path,
    config: object,
    vision_fallback_enabled: bool | None,
    ocr_languages: str | None,
) -> InputExtractionOptions:
    env_path = _resolve_env_file_path(run_dir=run_dir, env_file=config.openai.env_file)
    env_values = _load_dotenv(env_path) if env_path.exists() else {}
    vision_provider = config.input_extraction.vision_provider
    vision_enabled = vision_fallback_enabled if vision_fallback_enabled is not None else vision_provider != "disabled"
    if not vision_enabled:
        vision_provider = "disabled"
    resolved_ocr_languages = (
        ocr_languages
        or env_values.get("SHOTGUNCV_OCR_LANGUAGES", "").strip()
        or config.input_extraction.ocr_languages
        or "eng+chi_sim"
    )
    vision_model = (
        env_values.get("SHOTGUNCV_VISION_MODEL", "").strip()
        or config.input_extraction.vision_model
        or env_values.get("OPENAI_MODEL", "").strip()
        or "gpt-5.4-mini"
    )
    api_key_name = env_values.get("OPENAI_API_KEY_ENV", "").strip() or config.openai.api_key_env
    base_url = (
        env_values.get("OPENAI_BASE_URL", "").strip()
        or (config.openai.base_url or "").strip()
        or "https://api.openai.com/v1"
    )
    return InputExtractionOptions(
        ocr_provider=config.input_extraction.ocr_provider,
        vision_provider=vision_provider,
        vision_model=vision_model,
        ocr_languages=resolved_ocr_languages,
        vision_enabled=vision_enabled,
        openai_base_url=base_url,
        openai_api_key=env_values.get(api_key_name, "").strip(),
    )


def _resolve_env_file_path(run_dir: Path, env_file: str) -> Path:
    candidate = Path(env_file)
    if candidate.is_absolute():
        return candidate
    project_relative = Path.cwd() / candidate
    if project_relative.exists():
        return project_relative
    run_relative = run_dir / candidate
    if run_relative.exists():
        return run_relative
    return project_relative


def _load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, raw_value = line.split("=", maxsplit=1)
        key = key.strip()
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def _build_scorecard(
    jd: JDProfile,
    candidate: CandidateProfile,
    variant: ResumeVariant,
    rule_eval: RuleEvaluation,
    assessment: LLMAssessment | None,
    judge_rationale: str,
    requirement_matrix: list[RequirementEvidence],
    provider: str,
    model: str,
) -> ScoreCard:
    requirement_scores = _calculate_requirement_scores(jd.jd_id, requirement_matrix, rule_eval, assessment)
    if assessment is None:
        return ScoreCard(
            jd_id=jd.jd_id,
            variant_id=variant.variant_id,
            fit_score=rule_eval.fit_score,
            ats_score=rule_eval.ats_score,
            evidence_score=rule_eval.evidence_score,
            stretch_score=rule_eval.stretch_score,
            gap_risk_score=rule_eval.gap_risk_score,
            rewrite_cost_score=rule_eval.rewrite_cost_score,
            overall_score=rule_eval.overall_score,
            ranking_version=RANKING_VERSION,
            judge_rationale=judge_rationale,
            llm_role_fit_score=0.0,
            llm_evidence_score=0.0,
            llm_persuasion_score=0.0,
            llm_risk_score=0.0,
            llm_overall_score=0.0,
            final_overall_score=requirement_scores["final_overall_score"],
            final_decision_source="guardrail-fallback",
            guardrail_flags=["llm_assessment_missing"],
            provider=provider,
            model=model,
            verified_fit_score=requirement_scores["verified_fit_score"],
            rewrite_potential_score=requirement_scores["rewrite_potential_score"],
            risk_score=requirement_scores["risk_score"],
            gate_status="pass",
            gate_reasons=[],
        )

    llm_overall = round(
        (
            assessment.role_fit * 0.35
            + assessment.evidence_quality * 0.25
            + assessment.persuasiveness * 0.2
            + (1 - assessment.interview_pressure_risk) * 0.2
        ),
        2,
    )
    final_score = requirement_scores["final_overall_score"]
    flags: list[str] = []
    if _assessment_is_incomplete(assessment):
        flags.append("llm_assessment_incomplete")

    if rule_eval.evidence_binding < 0.4:
        final_score = min(final_score, 0.65)
        flags.append("insufficient_evidence_cap")

    if rule_eval.untraceable_claim_flags:
        flags.append("untraceable_claims")

    candidate_text = " ".join(candidate.experiences + candidate.projects + candidate.skills + candidate.strengths).lower()
    missing_must_have = [item for item in jd.must_have_requirements if item.lower() not in candidate_text]
    if not requirement_matrix and missing_must_have and assessment.application_worthiness == "strong_apply":
        final_score = min(final_score, 0.79)
        flags.append("missing_must_have_requirements")

    final_decision_source = "v0.5.7-requirement-score" if not flags else "v0.5.7-requirement-score+guardrail"

    return ScoreCard(
        jd_id=jd.jd_id,
        variant_id=variant.variant_id,
        fit_score=rule_eval.fit_score,
        ats_score=rule_eval.ats_score,
        evidence_score=rule_eval.evidence_score,
        stretch_score=rule_eval.stretch_score,
        gap_risk_score=rule_eval.gap_risk_score,
        rewrite_cost_score=rule_eval.rewrite_cost_score,
        overall_score=rule_eval.overall_score,
        ranking_version=RANKING_VERSION,
        judge_rationale=judge_rationale,
        llm_role_fit_score=assessment.role_fit,
        llm_evidence_score=assessment.evidence_quality,
        llm_persuasion_score=assessment.persuasiveness,
        llm_risk_score=assessment.interview_pressure_risk,
        llm_overall_score=llm_overall,
        final_overall_score=round(final_score, 2),
        final_decision_source=final_decision_source,
        guardrail_flags=flags,
        provider=assessment.provider or provider,
        model=assessment.model or model,
        verified_fit_score=requirement_scores["verified_fit_score"],
        rewrite_potential_score=requirement_scores["rewrite_potential_score"],
        risk_score=requirement_scores["risk_score"],
        gate_status="pass",
        gate_reasons=[],
    )


def _calculate_requirement_scores(
    jd_id: str,
    requirement_matrix: list[RequirementEvidence],
    rule_eval: RuleEvaluation,
    assessment: LLMAssessment | None,
) -> dict[str, float]:
    requirements = [item for item in requirement_matrix if item.jd_id == jd_id]
    if not requirements:
        risk = assessment.interview_pressure_risk if assessment is not None else rule_eval.gap_risk_score
        verified = round((rule_eval.fit_score * 0.45) + (rule_eval.evidence_score * 0.55), 2)
        rewrite = round(min(1.0, verified + max(0.0, 1 - rule_eval.rewrite_cost_score) * 0.15), 2)
        final = round((verified * 0.65) + (rewrite * 0.20) + ((1 - risk) * 0.15), 2)
        return {"verified_fit_score": verified, "rewrite_potential_score": rewrite, "risk_score": round(risk, 2), "final_overall_score": final}

    total_weight = sum(item.risk_weight for item in requirements) or 1.0
    verified_points = 0.0
    rewrite_points = 0.0
    risk_points = 0.0
    for item in requirements:
        weight = item.risk_weight
        if item.evidence_status == "verified":
            verified_points += weight
            rewrite_points += weight
        elif item.evidence_status == "inferred":
            verified_points += weight * 0.7
            rewrite_points += weight * 0.85
            risk_points += weight * 0.15
        elif item.evidence_status == "simulatable":
            rewrite_points += weight * 0.65
            risk_points += weight * 0.45
        elif item.evidence_status == "missing":
            risk_points += weight * (0.9 if item.tier == "hard_gate" else 0.55)
        elif item.evidence_status == "mismatch":
            risk_points += weight
    verified = round(max(0.0, min(1.0, verified_points / total_weight)), 2)
    rewrite = round(max(verified, min(1.0, rewrite_points / total_weight)), 2)
    base_risk = risk_points / total_weight
    llm_risk = assessment.interview_pressure_risk if assessment is not None else rule_eval.gap_risk_score
    risk = round(max(0.0, min(1.0, base_risk * 0.75 + llm_risk * 0.25)), 2)
    final = round((verified * 0.65) + (rewrite * 0.20) + ((1 - risk) * 0.15), 2)
    return {
        "verified_fit_score": verified,
        "rewrite_potential_score": rewrite,
        "risk_score": risk,
        "final_overall_score": final,
    }


def _build_preflight_scorecard(jd: JDProfile, gate: PreflightGate, provider: str, model: str) -> ScoreCard:
    risk_score = 0.99 if gate.status == "blocked" else 0.85
    return ScoreCard(
        jd_id=jd.jd_id,
        variant_id=f"preflight-{jd.jd_id}",
        fit_score=0.0,
        ats_score=0.0,
        evidence_score=0.0,
        stretch_score=0.0,
        gap_risk_score=risk_score,
        rewrite_cost_score=1.0,
        overall_score=0.0,
        ranking_version=SCORING_VERSION,
        judge_rationale="Preflight gate skipped generation and LLM judge.",
        final_overall_score=0.0,
        final_decision_source="preflight-gate",
        guardrail_flags=gate.reasons,
        provider=provider,
        model=model,
        verified_fit_score=0.0,
        rewrite_potential_score=0.0,
        risk_score=risk_score,
        gate_status=gate.status,
        gate_reasons=gate.reasons,
    )


def _build_preflight_explanation(jd: JDProfile, gate: PreflightGate, scorecard: ScoreCard) -> RankingExplanation:
    return RankingExplanation(
        jd_id=jd.jd_id,
        variant_id=scorecard.variant_id,
        ranking_version=SCORING_VERSION,
        dimension_reasons={
            "fit": "Preflight gate did not calculate a normal fit score.",
            "ats": "Preflight gate skipped ATS evaluation for this JD.",
            "evidence": "Hard gate evidence must be confirmed before generation.",
            "stretch": "No generated rewrite potential is counted before gate review.",
            "gap_risk": f"gate_status={gate.status}; risk_score={scorecard.risk_score:.2f}",
            "rewrite_cost": "Generation was skipped to avoid fabricating hard facts.",
            "overall": "; ".join(gate.reasons) or "Preflight gate blocked this JD.",
        },
        positive_signals=[],
        risk_flags=gate.reasons,
        evidence_refs=[],
        decision_summary="Preflight gate skipped generation/evaluation until hard gate evidence is confirmed.",
    )


def _build_preflight_strategy(jd: JDProfile, scorecard: ScoreCard, rank: int) -> ApplicationStrategy:
    decision = "blocked" if scorecard.gate_status == "blocked" else "needs_review"
    return ApplicationStrategy(
        jd_id=jd.jd_id,
        recommended_variant_id=scorecard.variant_id,
        priority_rank=rank,
        apply_decision=decision,
        reason_summary="; ".join(scorecard.gate_reasons) or f"Preflight gate status: {scorecard.gate_status}.",
        needs_jd_specific_variant=False,
        decision_drivers=["preflight-gate"],
        watchouts=scorecard.gate_reasons,
        recommended_actions=["补充或确认硬门槛证据后再重新运行。"],
        catch_up_notes=[],
        decision_confidence=1.0,
        interview_prep_points=jd.interview_focus_areas[:3],
        resume_revision_tasks=[],
    )


def _build_ranking_explanation(
    jd: JDProfile,
    candidate: CandidateProfile,
    variant: ResumeVariant,
    scorecard: ScoreCard,
    assessment: LLMAssessment | None,
    rule_eval: RuleEvaluation,
    assessment_failure: LLMFailure | None = None,
) -> RankingExplanation:
    candidate_evidence = candidate.experiences + candidate.projects + candidate.skills + candidate.verified_evidence
    matched_evidence = [
        item
        for item in candidate_evidence
        if any(keyword.split()[0] in item.lower() for keyword in jd.keywords)
    ]
    summary = assessment.decision_rationale if assessment else f"Fallback to rules with overall score {rule_eval.overall_score:.2f}."
    if assessment and not summary:
        summary = f"LLM assessment accepted with incomplete rationale; final score {scorecard.final_overall_score or scorecard.overall_score:.2f}."
    if assessment is None and assessment_failure is not None:
        summary = (
            f"LLM assessment unavailable: {_format_llm_failure_reason(assessment_failure)}. "
            f"Fallback to rules with overall score {rule_eval.overall_score:.2f}."
        )
    return RankingExplanation(
        jd_id=jd.jd_id,
        variant_id=variant.variant_id,
        ranking_version=RANKING_VERSION,
        dimension_reasons={
            "fit": f"rule_fit={rule_eval.fit_score:.2f}; llm_role_fit={scorecard.llm_role_fit_score:.2f}",
            "ats": f"keyword_coverage={rule_eval.keyword_coverage:.2f}",
            "evidence": f"rule_evidence={rule_eval.evidence_binding:.2f}; llm_evidence={scorecard.llm_evidence_score:.2f}",
            "stretch": f"stretch={rule_eval.stretch_score:.2f}",
            "gap_risk": f"gap_risk={rule_eval.gap_risk_score:.2f}",
            "rewrite_cost": f"rewrite_cost={rule_eval.rewrite_cost_score:.2f}",
            "overall": summary,
        },
        positive_signals=[
            f"final_score={scorecard.final_overall_score or scorecard.overall_score:.2f}",
            f"decision_source={scorecard.final_decision_source}",
        ],
        risk_flags=scorecard.guardrail_flags or list(rule_eval.untraceable_claim_flags[:2]),
        evidence_refs=(assessment.evidence_citations if assessment and assessment.evidence_citations else matched_evidence[:3]),
        decision_summary=summary,
    )


def _assessment_has_minimum_fields(assessment: LLMAssessment) -> bool:
    return bool(
        assessment.application_worthiness.strip()
        and all(
            0.0 <= score <= 1.0
            for score in (
                assessment.role_fit,
                assessment.evidence_quality,
                assessment.persuasiveness,
                assessment.interview_pressure_risk,
            )
        )
    )


def _assessment_is_incomplete(assessment: LLMAssessment) -> bool:
    return not assessment.decision_rationale.strip() or not assessment.evidence_citations


def estimate_evaluate_task_total(run_dir: Path) -> int:
    jd_profiles = hydrate(list[JDProfile], load_json(run_dir / "analyze" / "jd_profiles.json"))
    variants = hydrate(list[ResumeVariant], load_json(run_dir / "generate" / "resume_variants.json"))
    return len(_build_evaluate_work_items(jd_profiles, variants))


def _build_evaluate_work_items(jd_profiles: list[JDProfile], variants: list[ResumeVariant]) -> list[_EvaluateWorkItem]:
    work_items: list[_EvaluateWorkItem] = []
    for jd_index, jd in enumerate(jd_profiles):
        relevant_variants = _select_relevant_variants(jd, variants)
        for variant_index, variant in enumerate(relevant_variants):
            work_items.append(
                _EvaluateWorkItem(
                    jd_index=jd_index,
                    variant_index=variant_index,
                    jd=jd,
                    variant=variant,
                )
            )
    return work_items


def _select_relevant_variants(jd: JDProfile, variants: list[ResumeVariant]) -> list[ResumeVariant]:
    return [variant for variant in variants if jd.jd_id in variant.target_jd_ids]


def _evaluate_work_item(
    item: _EvaluateWorkItem,
    judge: object,
    candidate: CandidateProfile,
    evidence_map: dict[str, object],
    requirement_matrix: list[RequirementEvidence],
    provider: str,
    model: str,
) -> _EvaluateTaskResult:
    started = perf_counter()
    rule_eval = evaluate_resume_fit(item.jd, candidate, item.variant)
    assessment_failure: LLMFailure | None = None

    try:
        judge_feedback = judge.review(item.jd, candidate, item.variant, rule_eval.overall_score)
        judge_rationale = judge_feedback.rationale
    except Exception:
        judge_rationale = f"Review unavailable; fallback to rules with score {rule_eval.overall_score:.2f}."

    assessment: LLMAssessment | None = None
    try:
        assessment = judge.assess(item.jd, candidate, item.variant, evidence_map, rule_eval.overall_score)
        if not _assessment_has_minimum_fields(assessment):
            assessment_failure = _build_llm_failure(
                jd_id=item.jd.jd_id,
                variant_id=item.variant.variant_id,
                provider=provider,
                model=model,
                error=ValueError("assessment payload missing core fields"),
            )
            assessment = None
    except Exception as exc:
        assessment_failure = _build_llm_failure(
            jd_id=item.jd.jd_id,
            variant_id=item.variant.variant_id,
            provider=provider,
            model=model,
            error=exc,
        )
        assessment = None

    scorecard = _build_scorecard(
        jd=item.jd,
        candidate=candidate,
        variant=item.variant,
        rule_eval=rule_eval,
        assessment=assessment,
        judge_rationale=judge_rationale,
        requirement_matrix=requirement_matrix,
        provider=provider,
        model=model,
    )
    explanation = _build_ranking_explanation(
        jd=item.jd,
        candidate=candidate,
        variant=item.variant,
        scorecard=scorecard,
        assessment=assessment,
        rule_eval=rule_eval,
        assessment_failure=assessment_failure,
    )
    return _EvaluateTaskResult(
        jd_index=item.jd_index,
        variant_index=item.variant_index,
        jd_id=item.jd.jd_id,
        variant_id=item.variant.variant_id,
        rule_eval=rule_eval,
        scorecard=scorecard,
        explanation=explanation,
        assessment=assessment,
        assessment_failure=assessment_failure,
        status="ok" if assessment is not None else "fallback",
        duration_ms=int((perf_counter() - started) * 1000),
    )


def _build_fallback_task_result(
    item: _EvaluateWorkItem,
    candidate: CandidateProfile,
    requirement_matrix: list[RequirementEvidence],
    provider: str,
    model: str,
    error: Exception | None = None,
) -> _EvaluateTaskResult:
    started = perf_counter()
    rule_eval = evaluate_resume_fit(item.jd, candidate, item.variant)
    assessment_failure = _build_llm_failure(
        jd_id=item.jd.jd_id,
        variant_id=item.variant.variant_id,
        provider=provider,
        model=model,
        error=error or RuntimeError("evaluate task failed before LLM assessment completed"),
    )
    scorecard = _build_scorecard(
        jd=item.jd,
        candidate=candidate,
        variant=item.variant,
        rule_eval=rule_eval,
        assessment=None,
        judge_rationale=f"Task failed; fallback to rules with score {rule_eval.overall_score:.2f}.",
        requirement_matrix=requirement_matrix,
        provider=provider,
        model=model,
    )
    explanation = _build_ranking_explanation(
        jd=item.jd,
        candidate=candidate,
        variant=item.variant,
        scorecard=scorecard,
        assessment=None,
        rule_eval=rule_eval,
        assessment_failure=assessment_failure,
    )
    return _EvaluateTaskResult(
        jd_index=item.jd_index,
        variant_index=item.variant_index,
        jd_id=item.jd.jd_id,
        variant_id=item.variant.variant_id,
        rule_eval=rule_eval,
        scorecard=scorecard,
        explanation=explanation,
        assessment=None,
        assessment_failure=assessment_failure,
        status="fallback",
        duration_ms=int((perf_counter() - started) * 1000),
    )


def _load_requirement_matrix(run_dir: Path) -> list[RequirementEvidence]:
    path = run_dir / "analyze" / "requirement_matrix.json"
    if not path.exists():
        return []
    return hydrate(list[RequirementEvidence], load_json(path))


def _load_preflight_gates(run_dir: Path) -> list[PreflightGate]:
    path = run_dir / "analyze" / "preflight_gates.json"
    if not path.exists():
        return []
    return hydrate(list[PreflightGate], load_json(path))


def _load_evidence_map(run_dir: Path) -> dict[str, object]:
    path = run_dir / "analyze" / "evidence_map.json"
    if not path.exists():
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def _load_llm_assessments_with_fallback(run_dir: Path) -> list[LLMAssessment]:
    path = run_dir / "evaluate" / "llm_assessments.json"
    if not path.exists():
        return []
    return hydrate(list[LLMAssessment], load_json(path))


def _load_llm_failures_with_fallback(run_dir: Path) -> list[LLMFailure]:
    path = run_dir / "evaluate" / "llm_failures.json"
    if not path.exists():
        return []
    return hydrate(list[LLMFailure], load_json(path))


def _load_explanations_with_fallback(
    run_dir: Path, scorecards: list[ScoreCard], gap_maps: list[GapMap]
) -> list[RankingExplanation]:
    explanation_path = run_dir / "evaluate" / "ranking_explanations.json"
    loaded: list[RankingExplanation] = []
    if explanation_path.exists():
        loaded = hydrate(list[RankingExplanation], load_json(explanation_path))

    explanation_index = {(explanation.jd_id, explanation.variant_id): explanation for explanation in loaded}
    gap_index = {gap_map.jd_id: gap_map for gap_map in gap_maps}

    for scorecard in scorecards:
        key = (scorecard.jd_id, scorecard.variant_id)
        if key in explanation_index:
            continue
        gap_map = gap_index.get(scorecard.jd_id)
        explanation_index[key] = _build_legacy_ranking_explanation(scorecard, gap_map)

    return list(explanation_index.values())


def _build_llm_failure(
    jd_id: str,
    variant_id: str,
    provider: str,
    model: str,
    error: Exception,
) -> LLMFailure:
    message = str(error).strip() or error.__class__.__name__
    return LLMFailure(
        jd_id=jd_id,
        variant_id=variant_id,
        stage="evaluate",
        provider=provider,
        model=model,
        error_type=error.__class__.__name__,
        error_message=message,
        raw_output_excerpt=message[:200],
    )


def _format_llm_failure_reason(failure: LLMFailure | None) -> str | None:
    if failure is None:
        return None
    if failure.error_message:
        return f"{failure.error_type}: {failure.error_message}"
    return failure.error_type


def _build_legacy_ranking_explanation(scorecard: ScoreCard, gap_map: GapMap | None) -> RankingExplanation:
    weak_points = []
    if gap_map:
        for item in gap_map.items:
            weak_points.extend(item.weak_points[:1])

    risk_flags = weak_points[:2]
    score = scorecard.final_overall_score or scorecard.overall_score
    overall_summary = (
        f"Legacy run fallback for {scorecard.variant_id}: final_score={score:.2f}, "
        f"gap_risk_score={scorecard.gap_risk_score:.2f}."
    )
    return RankingExplanation(
        jd_id=scorecard.jd_id,
        variant_id=scorecard.variant_id,
        ranking_version=scorecard.ranking_version or RANKING_VERSION,
        dimension_reasons={
            "fit": "Legacy run fallback: fit reasoning not captured.",
            "ats": "Legacy run fallback: ATS reasoning not captured.",
            "evidence": "Legacy run fallback: evidence reasoning not captured.",
            "stretch": "Legacy run fallback: stretch reasoning not captured.",
            "gap_risk": f"gap_risk_score={scorecard.gap_risk_score:.2f} based on legacy scorecard.",
            "rewrite_cost": f"rewrite_cost_score={scorecard.rewrite_cost_score:.2f} based on legacy scorecard.",
            "overall": overall_summary,
        },
        positive_signals=[f"final_score={score:.2f} from legacy scorecard"],
        risk_flags=risk_flags,
        evidence_refs=[],
        decision_summary=scorecard.judge_rationale or overall_summary,
    )
