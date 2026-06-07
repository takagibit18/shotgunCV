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
    must_have_requirements: list[str] = field(default_factory=list)
    nice_to_have_requirements: list[str] = field(default_factory=list)
    hidden_signals: list[str] = field(default_factory=list)
    interview_focus_areas: list[str] = field(default_factory=list)
    role_level_confidence: float = 0.0


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
    core_claims: list[str] = field(default_factory=list)
    verified_evidence: list[str] = field(default_factory=list)
    missing_evidence_areas: list[str] = field(default_factory=list)
    preferred_role_tracks: list[str] = field(default_factory=list)


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
    safe_rewrites: list[str] = field(default_factory=list)
    simulated_supplements: list[str] = field(default_factory=list)
    forbidden_gaps: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ResumeBasics:
    full_name: str
    headline: str = ""
    location: str = ""
    email: str = ""
    phone: str = ""
    links: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ResumeEntry:
    id: str
    title: str
    organization: str = ""
    period: str = ""
    bullets: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CustomizedResumeDocument:
    basics: ResumeBasics
    summary: str
    skills: list[str] = field(default_factory=list)
    experiences: list[ResumeEntry] = field(default_factory=list)
    projects: list[ResumeEntry] = field(default_factory=list)
    education: list[ResumeEntry] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ResumeProvenance:
    field_sources: dict[str, list[str]] = field(default_factory=dict)
    to_verify_fields: list[str] = field(default_factory=list)
    forbidden_fields: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GeneratedResume:
    resume_id: str
    target_jd_id: str
    status: str
    document: CustomizedResumeDocument
    provenance: ResumeProvenance
    display_name: str = ""
    target_variant_id: str = ""


@dataclass(slots=True)
class RequirementEvidence:
    jd_id: str
    requirement_id: str
    tier: str
    requirement_text: str
    evidence_status: str
    evidence_refs: list[str] = field(default_factory=list)
    fabrication_policy: str = "rewrite_only"
    risk_weight: float = 0.5


@dataclass(slots=True)
class PreflightGate:
    jd_id: str
    status: str
    reasons: list[str] = field(default_factory=list)
    skipped_stages: list[str] = field(default_factory=list)
    user_action: str = ""


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
    llm_role_fit_score: float = 0.0
    llm_evidence_score: float = 0.0
    llm_persuasion_score: float = 0.0
    llm_risk_score: float = 0.0
    llm_overall_score: float = 0.0
    final_overall_score: float = 0.0
    final_decision_source: str = "rules"
    guardrail_flags: list[str] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    verified_fit_score: float = 0.0
    rewrite_potential_score: float = 0.0
    risk_score: float = 0.0
    gate_status: str = "pass"
    gate_reasons: list[str] = field(default_factory=list)

    @staticmethod
    def ranking_key(scorecard: "ScoreCard") -> tuple[float, float, float, float]:
        primary_score = scorecard.final_overall_score or scorecard.overall_score
        return (
            primary_score,
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
class LLMAssessment:
    jd_id: str
    variant_id: str
    role_fit: float
    evidence_quality: float
    persuasiveness: float
    interview_pressure_risk: float
    application_worthiness: str
    must_fix_issues: list[str] = field(default_factory=list)
    evidence_citations: list[str] = field(default_factory=list)
    rewrite_opportunities: list[str] = field(default_factory=list)
    decision_rationale: str = ""
    provider: str = ""
    model: str = ""


@dataclass(slots=True)
class LLMFailure:
    jd_id: str
    variant_id: str
    stage: str
    provider: str
    model: str
    error_type: str
    error_message: str
    raw_output_excerpt: str = ""


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
    decision_confidence: float = 0.0
    interview_prep_points: list[str] = field(default_factory=list)
    resume_revision_tasks: list[str] = field(default_factory=list)
