from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shotguncv_agents.providers import (
    DeterministicPlannerProvider,
    build_analyzer_provider,
    build_generator_provider,
    build_judge_provider,
    build_planner_provider,
)
from shotguncv_core.models import (
    ApplicationStrategy,
    CandidateProfile,
    GapMap,
    JDProfile,
    LLMAssessment,
    RankingExplanation,
    ResumeVariant,
    ScoreCard,
)
from shotguncv_core.run_config import load_run_config, snapshot_run_config
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
    summary: dict[str, object]


@dataclass(slots=True)
class PlanArtifacts:
    strategies: list[ApplicationStrategy]


RANKING_VERSION = "v0.3.0-llm-eval"


def ingest_run(
    run_dir: Path,
    candidate_id: str,
    candidate_resume_path: Path,
    jd_sources: list[Path],
    config_path: Path | None = None,
) -> Path:
    ingest_directory = stage_dir(run_dir, "ingest")
    snapshot_run_config(run_dir, config_path)
    manifest = {
        "candidate_id": candidate_id,
        "candidate_resume_path": str(candidate_resume_path),
        "candidate_resume_text": candidate_resume_path.read_text(encoding="utf-8"),
        "jd_inputs": [
            {
                "source_type": "file",
                "source_value": str(source),
                "content": source.read_text(encoding="utf-8"),
            }
            for source in jd_sources
        ],
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
    return AnalysisArtifacts(candidate=feedback.candidate_profile, jd_profiles=feedback.jd_profiles, evidence_map=feedback.evidence_map)


def generate_run(run_dir: Path) -> GenerationArtifacts:
    config = load_run_config(run_dir)
    candidate = hydrate(CandidateProfile, load_json(run_dir / "analyze" / "candidate_profile.json"))
    jd_profiles = hydrate(list[JDProfile], load_json(run_dir / "analyze" / "jd_profiles.json"))
    generator = build_generator_provider(config, stage="generate", run_dir=run_dir)

    clusters: dict[str, list[JDProfile]] = {}
    for jd in jd_profiles:
        clusters.setdefault(jd.cluster, []).append(jd)

    variants: list[ResumeVariant] = []
    for cluster, cluster_jds in clusters.items():
        variants.append(
            ResumeVariant(
                variant_id=f"variant-cluster-{cluster}",
                variant_type="cluster",
                cluster=cluster,
                target_jd_ids=[jd.jd_id for jd in cluster_jds],
                summary=generator.build_cluster_summary(cluster, candidate, cluster_jds),
                emphasized_strengths=_select_emphasized_strengths(candidate, cluster_jds[0]),
                stretch_points=_build_stretch_points(cluster_jds[0], candidate),
                source_resume_path=candidate.base_resume_path,
            )
        )

    for jd in jd_profiles:
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
            )
        )

    dump_json(stage_dir(run_dir, "generate") / "resume_variants.json", variants)
    return GenerationArtifacts(variants=variants)


def evaluate_run(run_dir: Path) -> EvaluationArtifacts:
    config = load_run_config(run_dir)
    candidate = hydrate(CandidateProfile, load_json(run_dir / "analyze" / "candidate_profile.json"))
    jd_profiles = hydrate(list[JDProfile], load_json(run_dir / "analyze" / "jd_profiles.json"))
    variants = hydrate(list[ResumeVariant], load_json(run_dir / "generate" / "resume_variants.json"))
    evidence_map = _load_evidence_map(run_dir)
    judge = build_judge_provider(config, stage="evaluate", run_dir=run_dir)

    scorecards: list[ScoreCard] = []
    gap_maps: list[GapMap] = []
    explanations: list[RankingExplanation] = []
    llm_assessments: list[LLMAssessment] = []
    eval_summary: list[dict[str, object]] = []

    for jd in jd_profiles:
        relevant_variants = [variant for variant in variants if jd.jd_id in variant.target_jd_ids or variant.cluster == jd.cluster]
        best_gap_rule: RuleEvaluation | None = None
        best_gap_score = -1.0
        jd_scorecards: list[ScoreCard] = []

        for variant in relevant_variants:
            rule_eval = evaluate_resume_fit(jd, candidate, variant)
            judge_feedback = judge.review(jd, candidate, variant, rule_eval.overall_score)

            assessment: LLMAssessment | None = None
            try:
                assessment = judge.assess(jd, candidate, variant, evidence_map, rule_eval.overall_score)
                if not _assessment_has_minimum_fields(assessment):
                    assessment = None
            except Exception:
                assessment = None

            scorecard = _build_scorecard(
                jd=jd,
                candidate=candidate,
                variant=variant,
                rule_eval=rule_eval,
                assessment=assessment,
                judge_rationale=judge_feedback.rationale,
                provider=config.judge.provider,
                model=config.judge.model,
            )
            scorecards.append(scorecard)
            jd_scorecards.append(scorecard)
            explanations.append(
                _build_ranking_explanation(
                    jd=jd,
                    candidate=candidate,
                    variant=variant,
                    scorecard=scorecard,
                    assessment=assessment,
                    rule_eval=rule_eval,
                )
            )
            if assessment is not None:
                llm_assessments.append(assessment)

            if rule_eval.overall_score > best_gap_score:
                best_gap_score = rule_eval.overall_score
                best_gap_rule = rule_eval

        gap_items = best_gap_rule.gaps if best_gap_rule else []
        gap_map = GapMap(jd_id=jd.jd_id, candidate_id=candidate.candidate_id, items=gap_items)
        gap_maps.append(gap_map)

        best_scorecard = max(jd_scorecards, key=ScoreCard.ranking_key)
        best_explanation = next(
            explanation
            for explanation in explanations
            if explanation.jd_id == jd.jd_id and explanation.variant_id == best_scorecard.variant_id
        )
        eval_summary.append(
            {
                "jd_id": jd.jd_id,
                "title": jd.title,
                "top_variant_id": best_scorecard.variant_id,
                "gap_count": len(gap_items),
                "top_reasons": best_explanation.positive_signals[:2] or [best_explanation.dimension_reasons["overall"]],
            }
        )

    evaluate_directory = stage_dir(run_dir, "evaluate")
    dump_json(evaluate_directory / "scorecards.json", scorecards)
    dump_json(evaluate_directory / "gap_maps.json", gap_maps)
    dump_json(evaluate_directory / "ranking_explanations.json", explanations)
    dump_json(evaluate_directory / "llm_assessments.json", llm_assessments)
    dump_json(evaluate_directory / "eval_summary.json", eval_summary)
    return EvaluationArtifacts(
        scorecards=scorecards,
        gap_maps=gap_maps,
        explanations=explanations,
        llm_assessments=llm_assessments,
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
    fallback_planner = DeterministicPlannerProvider()

    strategies: list[ApplicationStrategy] = []
    for rank, scorecard in enumerate(ordered, start=1):
        jd = jd_index[scorecard.jd_id]
        variant = variant_index[scorecard.variant_id]
        assessment = assessment_index.get((scorecard.jd_id, scorecard.variant_id))
        try:
            feedback = planner.build_strategy(
                jd=jd,
                candidate=candidate,
                assessment=assessment,
                top_variant=variant,
                final_score=scorecard.final_overall_score or scorecard.overall_score,
                guardrail_flags=scorecard.guardrail_flags,
            )
        except Exception:
            feedback = fallback_planner.build_strategy(
                jd=jd,
                candidate=candidate,
                assessment=assessment,
                top_variant=variant,
                final_score=scorecard.final_overall_score or scorecard.overall_score,
                guardrail_flags=scorecard.guardrail_flags,
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


def _build_scorecard(
    jd: JDProfile,
    candidate: CandidateProfile,
    variant: ResumeVariant,
    rule_eval: RuleEvaluation,
    assessment: LLMAssessment | None,
    judge_rationale: str,
    provider: str,
    model: str,
) -> ScoreCard:
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
            final_overall_score=rule_eval.overall_score,
            final_decision_source="guardrail-fallback",
            guardrail_flags=["llm_assessment_missing"],
            provider=provider,
            model=model,
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
    final_score = llm_overall
    flags: list[str] = []

    if rule_eval.evidence_binding < 0.4:
        final_score = min(final_score, 0.65)
        flags.append("insufficient_evidence_cap")

    if rule_eval.untraceable_claim_flags:
        flags.append("untraceable_claims")

    candidate_text = " ".join(candidate.experiences + candidate.projects + candidate.skills + candidate.strengths).lower()
    missing_must_have = [item for item in jd.must_have_requirements if item.lower() not in candidate_text]
    if missing_must_have and assessment.application_worthiness == "strong_apply":
        final_score = min(final_score, 0.79)
        flags.append("missing_must_have_requirements")

    final_decision_source = "llm-primary" if not flags else "llm-primary+guardrail"

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
    )


def _build_ranking_explanation(
    jd: JDProfile,
    candidate: CandidateProfile,
    variant: ResumeVariant,
    scorecard: ScoreCard,
    assessment: LLMAssessment | None,
    rule_eval: RuleEvaluation,
) -> RankingExplanation:
    candidate_evidence = candidate.experiences + candidate.projects + candidate.skills + candidate.verified_evidence
    matched_evidence = [
        item
        for item in candidate_evidence
        if any(keyword.split()[0] in item.lower() for keyword in jd.keywords)
    ]
    summary = assessment.decision_rationale if assessment else f"Fallback to rules with overall score {rule_eval.overall_score:.2f}."
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
        evidence_refs=(assessment.evidence_citations if assessment else matched_evidence[:3]),
        decision_summary=summary,
    )


def _assessment_has_minimum_fields(assessment: LLMAssessment) -> bool:
    return bool(
        assessment.application_worthiness
        and assessment.decision_rationale
        and assessment.evidence_citations
    )


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
