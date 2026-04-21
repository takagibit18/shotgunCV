from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from shotguncv_core.models import CandidateProfile, JDProfile, ResumeVariant


@dataclass(slots=True)
class JudgeFeedback:
    rationale: str
    application_worthiness: str


class ResumeGeneratorProvider(Protocol):
    def build_cluster_summary(self, cluster: str, candidate: CandidateProfile, jds: list[JDProfile]) -> str:
        ...

    def build_jd_summary(self, jd: JDProfile, candidate: CandidateProfile) -> str:
        ...


class JudgeProvider(Protocol):
    def review(self, jd: JDProfile, candidate: CandidateProfile, variant: ResumeVariant, overall_score: float) -> JudgeFeedback:
        ...


class DeterministicGeneratorProvider:
    def build_cluster_summary(self, cluster: str, candidate: CandidateProfile, jds: list[JDProfile]) -> str:
        primary_strength = candidate.strengths[0] if candidate.strengths else "AI workflow delivery"
        return f"{cluster} cluster resume emphasizing {primary_strength} across {len(jds)} related roles."

    def build_jd_summary(self, jd: JDProfile, candidate: CandidateProfile) -> str:
        lead_strength = candidate.strengths[0] if candidate.strengths else "cross-functional execution"
        return f"{jd.title} variant focused on {lead_strength}, {jd.keywords[0]}, and evidence-backed delivery."


class DeterministicJudgeProvider:
    def review(self, jd: JDProfile, candidate: CandidateProfile, variant: ResumeVariant, overall_score: float) -> JudgeFeedback:
        risk_phrase = "manageable risk" if overall_score >= 0.7 else "meaningful catch-up risk"
        worthiness = "apply" if overall_score >= 0.7 else "stretch"
        rationale = (
            f"{variant.variant_type} variant aligns {candidate.candidate_id} with {jd.title}; "
            f"score indicates {risk_phrase} for this batch."
        )
        return JudgeFeedback(rationale=rationale, application_worthiness=worthiness)
