from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class JDProfile:
    jd_id: str
    title: str
    company: str
    cluster: str
    responsibilities: list[str]
    requirements: list[str]
    keywords: list[str]
    seniority: str
    bonuses: list[str]
    risk_signals: list[str]
    source_type: str
    source_value: str


@dataclass(slots=True)
class CandidateProfile:
    candidate_id: str
    base_resume_path: str
    experiences: list[str]
    projects: list[str]
    skills: list[str]
    industry_tags: list[str]
    strengths: list[str]
    constraints: list[str]
    preferences: list[str]


@dataclass(slots=True)
class ResumeVariant:
    variant_id: str
    variant_type: str
    cluster: str
    target_jd_ids: list[str]
    summary: str
    emphasized_strengths: list[str]
    stretch_points: list[str]
    source_resume_path: str


@dataclass(slots=True)
class ScoreCard:
    jd_id: str
    variant_id: str
    fit_score: float
    ats_score: float
    evidence_score: float
    stretch_score: float
    gap_risk_score: float
    rewrite_cost_score: float
    overall_score: float
    ranking_version: str
    judge_rationale: str

    @staticmethod
    def ranking_key(scorecard: "ScoreCard") -> tuple[float, float, float, float]:
        return (
            scorecard.overall_score,
            scorecard.fit_score,
            scorecard.evidence_score,
            -scorecard.gap_risk_score,
        )


@dataclass(slots=True)
class GapItem:
    area: str
    current_state: str
    target_state: str
    priority: str
    catch_up_concepts: list[str] = field(default_factory=list)
    weak_points: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GapMap:
    jd_id: str
    candidate_id: str
    items: list[GapItem] = field(default_factory=list)


@dataclass(slots=True)
class RankingExplanation:
    jd_id: str
    variant_id: str
    ranking_version: str
    dimension_reasons: dict[str, str]
    positive_signals: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    decision_summary: str = ""


@dataclass(slots=True)
class ApplicationStrategy:
    jd_id: str
    recommended_variant_id: str
    priority_rank: int
    apply_decision: str
    reason_summary: str
    needs_jd_specific_variant: bool
    decision_drivers: list[str] = field(default_factory=list)
    watchouts: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    catch_up_notes: list[str] = field(default_factory=list)
