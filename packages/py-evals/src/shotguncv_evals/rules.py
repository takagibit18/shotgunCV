from __future__ import annotations

import re
from dataclasses import dataclass

from shotguncv_core.models import CandidateProfile, GapItem, JDProfile, ResumeVariant


@dataclass(slots=True)
class RuleEvaluation:
    keyword_coverage: float
    evidence_binding: float
    untraceable_claim_flags: list[str]
    rewrite_distance: float
    cluster_reuse_efficiency: float
    fit_score: float
    ats_score: float
    evidence_score: float
    stretch_score: float
    gap_risk_score: float
    rewrite_cost_score: float
    overall_score: float
    gaps: list[GapItem]


def evaluate_resume_fit(jd: JDProfile, candidate: CandidateProfile, variant: ResumeVariant) -> RuleEvaluation:
    candidate_text = _normalize(
        " ".join(
            candidate.experiences
            + candidate.projects
            + candidate.skills
            + candidate.industry_tags
            + candidate.strengths
        )
    )
    variant_text = _normalize(
        " ".join([variant.summary] + variant.emphasized_strengths + variant.stretch_points)
    )
    jd_text = _normalize(" ".join(jd.responsibilities + jd.requirements + jd.keywords + jd.bonuses))

    keyword_hits = [keyword for keyword in jd.keywords if _normalize(keyword) in variant_text or _normalize(keyword) in candidate_text]
    keyword_coverage = _ratio(len(keyword_hits), len(jd.keywords))

    evidence_hits = [strength for strength in variant.emphasized_strengths if _normalize(strength) in candidate_text]
    evidence_binding = _ratio(len(evidence_hits), len(variant.emphasized_strengths))

    untraceable_claim_flags = [
        point for point in variant.stretch_points if _normalize(point) not in candidate_text and _normalize(point) not in jd_text
    ]
    flag_ratio = _ratio(len(untraceable_claim_flags), max(1, len(variant.stretch_points)))

    rewrite_distance = 0.28 if variant.variant_type == "cluster" else 0.42
    cluster_reuse_efficiency = 0.85 if variant.variant_type == "cluster" else 0.55

    fit_score = _bounded_round((keyword_coverage * 0.6) + (evidence_binding * 0.4))
    ats_score = _bounded_round(keyword_coverage)
    evidence_score = _bounded_round(evidence_binding)
    stretch_score = _bounded_round(max(0.1, 0.9 - flag_ratio))
    gap_risk_score = _bounded_round(
        min(0.95, ((1 - keyword_coverage) * 0.45) + ((1 - evidence_binding) * 0.35) + (flag_ratio * 0.2))
    )
    rewrite_cost_score = _bounded_round(1 - cluster_reuse_efficiency + (rewrite_distance * 0.15))
    overall_score = _bounded_round(
        (fit_score * 0.32)
        + (ats_score * 0.16)
        + (evidence_score * 0.2)
        + (stretch_score * 0.1)
        + ((1 - gap_risk_score) * 0.17)
        + ((1 - rewrite_cost_score) * 0.05)
    )

    return RuleEvaluation(
        keyword_coverage=keyword_coverage,
        evidence_binding=evidence_binding,
        untraceable_claim_flags=untraceable_claim_flags,
        rewrite_distance=rewrite_distance,
        cluster_reuse_efficiency=cluster_reuse_efficiency,
        fit_score=fit_score,
        ats_score=ats_score,
        evidence_score=evidence_score,
        stretch_score=stretch_score,
        gap_risk_score=gap_risk_score,
        rewrite_cost_score=rewrite_cost_score,
        overall_score=overall_score,
        gaps=_build_gap_items(jd, candidate, keyword_hits),
    )


def _build_gap_items(jd: JDProfile, candidate: CandidateProfile, keyword_hits: list[str]) -> list[GapItem]:
    candidate_text = _normalize(" ".join(candidate.experiences + candidate.projects + candidate.skills))
    missing_keywords = [keyword for keyword in jd.keywords if _normalize(keyword) not in candidate_text]
    if not missing_keywords:
        return []

    priority = "high" if len(missing_keywords) >= 2 else "medium"
    return [
        GapItem(
            area="Role alignment",
            current_state="Relevant foundation from current resume and projects",
            target_state=f"Confidently discuss {', '.join(missing_keywords[:2])}",
            priority=priority,
            catch_up_concepts=missing_keywords[:3],
            weak_points=[f"Evidence for {keyword} is currently indirect." for keyword in missing_keywords[:2]],
        )
    ]


def _normalize(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]+", " ", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _ratio(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return _bounded_round(part / total)


def _bounded_round(value: float) -> float:
    return round(max(0.0, min(0.99, value)), 2)
