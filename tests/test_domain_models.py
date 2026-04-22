from __future__ import annotations

from shotguncv_core.models import (
    ApplicationStrategy,
    CandidateProfile,
    GapItem,
    GapMap,
    JDProfile,
    RankingExplanation,
    ResumeVariant,
    ScoreCard,
)


def test_scorecard_and_strategy_capture_v1_fields() -> None:
    jd = JDProfile(
        jd_id="jd-001",
        title="LLM Product Engineer",
        company="Example AI",
        cluster="ai-product",
        responsibilities=["Ship evaluation pipelines"],
        requirements=["Prompt engineering", "Python"],
        keywords=["evaluation", "python", "llm"],
        seniority="mid",
        bonuses=["Agent workflow experience"],
        risk_signals=["Fast-moving scope"],
        source_type="text",
        source_value="LLM Product Engineer at Example AI",
    )
    candidate = CandidateProfile(
        candidate_id="cand-001",
        base_resume_path="fixtures/candidates/base_resume.md",
        experiences=["Built internal tooling for LLM workflows"],
        projects=["Resume scoring prototype"],
        skills=["Python", "Prompt design"],
        industry_tags=["AI tooling"],
        strengths=["Fast iteration"],
        constraints=["No production ML platform ownership"],
        preferences=["Product-oriented AI roles"],
    )
    variant = ResumeVariant(
        variant_id="variant-cluster-001",
        variant_type="cluster",
        cluster="ai-product",
        target_jd_ids=["jd-001"],
        summary="AI product oriented resume variant",
        emphasized_strengths=["LLM workflow tooling"],
        stretch_points=["Frame internal tooling as resume ops platform work"],
        source_resume_path="fixtures/candidates/base_resume.md",
    )
    scorecard = ScoreCard(
        jd_id=jd.jd_id,
        variant_id=variant.variant_id,
        fit_score=0.82,
        ats_score=0.79,
        evidence_score=0.76,
        stretch_score=0.68,
        gap_risk_score=0.42,
        rewrite_cost_score=0.25,
        overall_score=0.81,
        ranking_version="v0.2.0-explainable-ranking",
        judge_rationale="Strong fit with manageable concept catch-up.",
    )
    explanation = RankingExplanation(
        jd_id=jd.jd_id,
        variant_id=variant.variant_id,
        ranking_version="v0.2.0-explainable-ranking",
        dimension_reasons={
            "fit": "keyword coverage and evidence binding are both strong",
            "ats": "python and evaluation keywords are present",
            "evidence": "resume bullets support the emphasized strengths",
            "stretch": "stretch claims remain discussable in interviews",
            "gap_risk": "missing large-scale benchmark ownership raises risk",
            "rewrite_cost": "jd-specific version needs moderate tailoring",
            "overall": "worth applying with light interview prep",
        },
        positive_signals=["LLM workflow tooling", "Resume scoring prototype"],
        risk_flags=["No production ML platform ownership"],
        evidence_refs=["Built internal tooling for LLM workflows", "Resume scoring prototype"],
        decision_summary="High-fit role with bounded catch-up risk.",
    )
    gap_map = GapMap(
        jd_id=jd.jd_id,
        candidate_id=candidate.candidate_id,
        items=[
            GapItem(
                area="Evaluation design",
                current_state="Has prototype exposure",
                target_state="Can discuss offline ranking metrics",
                priority="high",
                catch_up_concepts=["precision@k", "evaluation rubric"],
                weak_points=["No large-scale benchmark ownership"],
            )
        ],
    )

    strategy = ApplicationStrategy(
        jd_id=jd.jd_id,
        recommended_variant_id=variant.variant_id,
        priority_rank=1,
        apply_decision="apply",
        reason_summary="High-fit role with bounded catch-up risk.",
        needs_jd_specific_variant=True,
        decision_drivers=["Strong evidence binding", "Good keyword coverage"],
        watchouts=["Do not overstate production ML ownership"],
        recommended_actions=["Review offline evaluation metrics before interviews."],
        catch_up_notes=[
            "Review offline evaluation metrics before interviews.",
            "Avoid overstating production ownership.",
        ],
    )

    assert jd.cluster == "ai-product"
    assert candidate.constraints == ["No production ML platform ownership"]
    assert variant.variant_type == "cluster"
    assert scorecard.overall_score > scorecard.gap_risk_score
    assert scorecard.ranking_version == explanation.ranking_version
    assert explanation.dimension_reasons["overall"] == "worth applying with light interview prep"
    assert gap_map.items[0].catch_up_concepts == ["precision@k", "evaluation rubric"]
    assert strategy.needs_jd_specific_variant is True
    assert strategy.decision_drivers == ["Strong evidence binding", "Good keyword coverage"]
    assert strategy.recommended_actions == ["Review offline evaluation metrics before interviews."]


def test_strategy_sort_key_prefers_high_score_and_lower_gap_risk() -> None:
    stronger = ScoreCard(
        jd_id="jd-001",
        variant_id="v-1",
        fit_score=0.9,
        ats_score=0.9,
        evidence_score=0.86,
        stretch_score=0.75,
        gap_risk_score=0.3,
        rewrite_cost_score=0.2,
        overall_score=0.88,
        ranking_version="v0.2.0-explainable-ranking",
        judge_rationale="High priority.",
    )
    weaker = ScoreCard(
        jd_id="jd-002",
        variant_id="v-2",
        fit_score=0.78,
        ats_score=0.74,
        evidence_score=0.72,
        stretch_score=0.62,
        gap_risk_score=0.55,
        rewrite_cost_score=0.45,
        overall_score=0.7,
        ranking_version="v0.2.0-explainable-ranking",
        judge_rationale="Lower payoff.",
    )

    ranked = sorted([weaker, stronger], key=ScoreCard.ranking_key, reverse=True)

    assert [card.jd_id for card in ranked] == ["jd-001", "jd-002"]
