from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from urllib import request
from typing import Protocol

from shotguncv_core.models import ApplicationStrategy, CandidateProfile, JDProfile, LLMAssessment, ResumeVariant
from shotguncv_core.run_config import RunConfig
from shotguncv_agents.prompts import build_system_prompt as _shared_system_prompt
from shotguncv_agents.structured import parse_json_object

DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
DEFAULT_OPENAI_TIMEOUT_SEC = 90
DEFAULT_LLM_RETRY_TIMES = 2
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
_ASCII_LETTER_PATTERN = re.compile(r"[A-Za-z]")
_IDENTIFIER_LIKE_PATTERN = re.compile(r"^[A-Za-z0-9_.:/@#\-\[\]]+$")
_CLUSTER_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def log_model_resolved(*args: object, **kwargs: object) -> None:
    from shotguncv_core.run_logs import log_model_resolved as _log_model_resolved

    _log_model_resolved(*args, **kwargs)


def log_llm_call_started(*args: object, **kwargs: object) -> float:
    from shotguncv_core.run_logs import log_llm_call_started as _log_llm_call_started

    return _log_llm_call_started(*args, **kwargs)


def log_llm_call_finished(*args: object, **kwargs: object) -> None:
    from shotguncv_core.run_logs import log_llm_call_finished as _log_llm_call_finished

    _log_llm_call_finished(*args, **kwargs)


def log_llm_call_failed(*args: object, **kwargs: object) -> None:
    from shotguncv_core.run_logs import log_llm_call_failed as _log_llm_call_failed

    _log_llm_call_failed(*args, **kwargs)


def log_fallback_used(*args: object, **kwargs: object) -> None:
    from shotguncv_core.run_logs import log_fallback_used as _log_fallback_used

    _log_fallback_used(*args, **kwargs)


@dataclass(slots=True)
class JudgeFeedback:
    rationale: str
    application_worthiness: str


@dataclass(slots=True)
class AnalyzeFeedback:
    candidate_profile: CandidateProfile
    jd_profiles: list[JDProfile]
    evidence_map: dict[str, object]


@dataclass(slots=True)
class PlanFeedback:
    strategy: ApplicationStrategy


class ResumeGeneratorProvider(Protocol):
    def build_cluster_summary(self, cluster: str, candidate: CandidateProfile, jds: list[JDProfile]) -> str:
        ...

    def build_jd_summary(self, jd: JDProfile, candidate: CandidateProfile) -> str:
        ...


class JudgeProvider(Protocol):
    def review(self, jd: JDProfile, candidate: CandidateProfile, variant: ResumeVariant, overall_score: float) -> JudgeFeedback:
        ...

    def assess(
        self,
        jd: JDProfile,
        candidate: CandidateProfile,
        variant: ResumeVariant,
        evidence_map: dict[str, object],
        rule_overall_score: float,
    ) -> LLMAssessment:
        ...


class AnalyzeProvider(Protocol):
    def analyze(self, candidate_id: str, candidate_resume_path: str, resume_text: str, jd_inputs: list[dict[str, str]]) -> AnalyzeFeedback:
        ...


class PlannerProvider(Protocol):
    def build_strategy(
        self,
        jd: JDProfile,
        candidate: CandidateProfile,
        assessment: LLMAssessment | None,
        top_variant: ResumeVariant,
        final_score: float,
        guardrail_flags: list[str],
        assessment_failure_reason: str | None = None,
    ) -> PlanFeedback:
        ...


class DeterministicGeneratorProvider:
    def __init__(self, provider: str = "deterministic", model: str = "heuristic-v0.3.0") -> None:
        self.runtime_provider = provider
        self.runtime_model = model

    def build_cluster_summary(self, cluster: str, candidate: CandidateProfile, jds: list[JDProfile]) -> str:
        primary_strength = candidate.strengths[0] if candidate.strengths else "AI workflow delivery"
        return f"{cluster} cluster resume emphasizing {primary_strength} across {len(jds)} related roles."

    def build_jd_summary(self, jd: JDProfile, candidate: CandidateProfile) -> str:
        lead_strength = candidate.strengths[0] if candidate.strengths else "cross-functional execution"
        return f"{jd.title} variant focused on {lead_strength}, {jd.keywords[0]}, and evidence-backed delivery."


class DeterministicJudgeProvider:
    def __init__(self, provider: str = "deterministic", model: str = "heuristic-v0.3.0") -> None:
        self.runtime_provider = provider
        self.runtime_model = model

    def review(self, jd: JDProfile, candidate: CandidateProfile, variant: ResumeVariant, overall_score: float) -> JudgeFeedback:
        risk_phrase = "manageable risk" if overall_score >= 0.7 else "meaningful catch-up risk"
        worthiness = "apply" if overall_score >= 0.7 else "stretch"
        rationale = (
            f"{variant.variant_type} variant aligns {candidate.candidate_id} with {jd.title}; "
            f"score indicates {risk_phrase} for this batch."
        )
        return JudgeFeedback(rationale=rationale, application_worthiness=worthiness)

    def assess(
        self,
        jd: JDProfile,
        candidate: CandidateProfile,
        variant: ResumeVariant,
        evidence_map: dict[str, object],
        rule_overall_score: float,
    ) -> LLMAssessment:
        role_fit = round(min(0.99, max(0.0, rule_overall_score + 0.03)), 2)
        evidence_quality = 0.8 if candidate.verified_evidence else 0.62
        persuasiveness = 0.76 if variant.variant_type == "jd-specific" else 0.68
        interview_pressure_risk = round(max(0.0, 1 - role_fit), 2)
        worthiness = "strong_apply" if role_fit >= 0.8 else ("apply" if role_fit >= 0.65 else "hold")
        return LLMAssessment(
            jd_id=jd.jd_id,
            variant_id=variant.variant_id,
            role_fit=role_fit,
            evidence_quality=evidence_quality,
            persuasiveness=persuasiveness,
            interview_pressure_risk=interview_pressure_risk,
            application_worthiness=worthiness,
            must_fix_issues=[] if worthiness != "hold" else ["Core evidence is too weak for this role level."],
            evidence_citations=candidate.verified_evidence[:3],
            rewrite_opportunities=variant.stretch_points[:2],
            decision_rationale=f"Deterministic LLM-assessment fallback based on rule score {rule_overall_score:.2f}.",
            provider=self.runtime_provider,
            model=self.runtime_model,
        )


class DeterministicAnalyzeProvider:
    def __init__(self, provider: str = "deterministic", model: str = "heuristic-v0.3.0") -> None:
        self.runtime_provider = provider
        self.runtime_model = model

    def analyze(self, candidate_id: str, candidate_resume_path: str, resume_text: str, jd_inputs: list[dict[str, str]]) -> AnalyzeFeedback:
        resume_sections = _extract_resume_sections(resume_text)
        evidence_lines = resume_sections["evidence"]
        lowered = " ".join(evidence_lines).lower()
        skills = []
        for keyword, label in (
            ("python", "Python"),
            ("llm", "LLM workflows"),
            ("resume", "Resume evaluation"),
            ("product", "Product collaboration"),
            ("computer science", "Computer Science"),
            ("计算机", "计算机专业"),
            ("pmp", "PMP"),
            ("certificate", "Certificates"),
            ("证书", "证书"),
        ):
            if keyword in lowered:
                skills.append(label)
        skills = _extract_skill_labels("\n".join([resume_text, *evidence_lines])) or skills

        candidate = CandidateProfile(
            candidate_id=candidate_id,
            base_resume_path=candidate_resume_path,
            experiences=resume_sections["experiences"],
            projects=resume_sections["projects"],
            skills=skills or ["AI workflow delivery"],
            industry_tags=["AI tooling", "Resume ops"],
            strengths=resume_sections["strengths"][:2] or ["Structured AI workflow delivery"],
            constraints=["No explicit production ML platform ownership yet"],
            preferences=["Product-oriented AI roles"],
            core_claims=evidence_lines[:4],
            verified_evidence=evidence_lines[:8],
            missing_evidence_areas=["Large-scale online experiment ownership"],
            preferred_role_tracks=["LLM Product Engineer", "Applied AI Ops"],
        )
        jd_profiles: list[JDProfile] = []
        evidence_map: dict[str, object] = {"candidate": {}, "jds": {}, "risks": []}
        jd_counter = 0
        for jd_input in jd_inputs:
            source_type = jd_input["source_type"]
            source_value = jd_input["source_value"]
            content = _clean_jd_text_content(jd_input["content"])
            blocks = [block.strip() for block in content.split("=== JD ===") if block.strip()]
            for block in blocks:
                jd_counter += 1
                title = _extract_header(block, "Title") or str(jd_input.get("display_name", "")).strip() or _first_meaningful_line(block)
                company = _extract_header(block, "Company")
                body_lines = _extract_body_lines(block)
                keyword_candidates = _extract_keywords(" ".join(body_lines))
                bonuses = [line.replace("Bonus for ", "").strip() for line in body_lines if "bonus" in line.lower()]
                must_have = body_lines[:2]
                nice_to_have = bonuses[:2]
                profile = JDProfile(
                    jd_id=f"jd-{jd_counter:03d}",
                    title=title,
                    company=company,
                    cluster=_classify_cluster(title, body_lines),
                    responsibilities=body_lines,
                    requirements=body_lines[:2],
                    keywords=keyword_candidates,
                    seniority="mid",
                    bonuses=bonuses,
                    risk_signals=_build_risk_signals(body_lines),
                    source_type=source_type,
                    source_value=source_value,
                    must_have_requirements=must_have,
                    nice_to_have_requirements=nice_to_have,
                    hidden_signals=[signal for signal in _build_risk_signals(body_lines) if "metrics" in signal.lower()],
                    interview_focus_areas=keyword_candidates[:3],
                    role_level_confidence=0.72,
                )
                jd_profiles.append(profile)
                evidence_map["jds"][profile.jd_id] = {
                    "must_have": must_have,
                    "source_snippets": body_lines[:3],
                    "risk_signals": profile.risk_signals,
                }
        evidence_map["candidate"] = {
            "core_claims": candidate.core_claims,
            "verified_evidence": candidate.verified_evidence,
            "missing_evidence_areas": candidate.missing_evidence_areas,
        }
        evidence_map["risks"] = candidate.missing_evidence_areas
        return AnalyzeFeedback(candidate_profile=candidate, jd_profiles=jd_profiles, evidence_map=evidence_map)


class DeterministicPlannerProvider:
    def __init__(self, provider: str = "deterministic", model: str = "heuristic-v0.3.0") -> None:
        self.runtime_provider = provider
        self.runtime_model = model

    def build_strategy(
        self,
        jd: JDProfile,
        candidate: CandidateProfile,
        assessment: LLMAssessment | None,
        top_variant: ResumeVariant,
        final_score: float,
        guardrail_flags: list[str],
        assessment_failure_reason: str | None = None,
    ) -> PlanFeedback:
        decision = "apply" if final_score >= 0.7 else "hold"
        confidence = round(min(0.95, max(0.35, final_score + 0.1)), 2)
        rationale = assessment.decision_rationale if assessment else "Guardrail fallback strategy."
        if not assessment and assessment_failure_reason:
            rationale = f"LLM assessment unavailable: {assessment_failure_reason}"
        return PlanFeedback(
            strategy=ApplicationStrategy(
                jd_id=jd.jd_id,
                recommended_variant_id=top_variant.variant_id,
                priority_rank=0,
                apply_decision=decision,
                reason_summary=rationale,
                needs_jd_specific_variant=top_variant.variant_type == "jd-specific",
                decision_drivers=[f"Final score {final_score:.2f}", f"Variant type: {top_variant.variant_type}"],
                watchouts=guardrail_flags or candidate.missing_evidence_areas[:2],
                recommended_actions=assessment.rewrite_opportunities[:2] if assessment else ["Refine core evidence bullets."],
                catch_up_notes=candidate.missing_evidence_areas[:2] or ["No critical catch-up themes."],
                decision_confidence=confidence,
                interview_prep_points=jd.interview_focus_areas[:3],
                resume_revision_tasks=assessment.must_fix_issues[:3] if assessment else [],
            )
        )


class OpenAIGeneratorProvider:
    def __init__(self, model: str, base_url: str | None, api_key: str, provider: str = "openai", run_dir: Path | None = None) -> None:
        self.model = model
        self.base_url = base_url or "https://api.openai.com/v1"
        self.api_key = api_key
        self.runtime_provider = provider
        self.runtime_model = model
        self.run_dir = run_dir

    def build_cluster_summary(self, cluster: str, candidate: CandidateProfile, jds: list[JDProfile]) -> str:
        titles = ", ".join(jd.title for jd in jds)
        prompt = (
            "请基于以下信息，撰写一段简洁的中文简历摘要，用于“岗位簇版本”。\n"
            f"岗位簇：{cluster}\n"
            f"候选人优势：{', '.join(candidate.strengths)}\n"
            f"目标岗位标题：{titles}\n"
            "只返回纯文本，不要添加编号或解释。"
        )
        try:
            return _chat_completion(
                self.base_url,
                self.api_key,
                self.model,
                prompt,
                expect_json=False,
                run_dir=self.run_dir,
                stage="generate",
                operation="build_cluster_summary",
                provider=self.runtime_provider,
            )
        except Exception as exc:
            if self.run_dir is not None:
                log_fallback_used(
                    self.run_dir,
                    stage="generate",
                    operation="build_cluster_summary",
                    from_provider=self.runtime_provider,
                    to_provider="deterministic",
                    reason=str(exc).strip() or exc.__class__.__name__,
                )
            return DeterministicGeneratorProvider().build_cluster_summary(cluster, candidate, jds)

    def build_jd_summary(self, jd: JDProfile, candidate: CandidateProfile) -> str:
        prompt = (
            "请基于以下信息，撰写一段简洁的中文简历摘要，用于“单岗位定制版本”。\n"
            f"岗位标题：{jd.title}\n"
            f"公司：{jd.company}\n"
            f"岗位关键词：{', '.join(jd.keywords)}\n"
            f"候选人优势：{', '.join(candidate.strengths)}\n"
            "只返回纯文本，不要添加编号或解释。"
        )
        try:
            return _chat_completion(
                self.base_url,
                self.api_key,
                self.model,
                prompt,
                expect_json=False,
                run_dir=self.run_dir,
                stage="generate",
                operation="build_jd_summary",
                provider=self.runtime_provider,
            )
        except Exception as exc:
            if self.run_dir is not None:
                log_fallback_used(
                    self.run_dir,
                    stage="generate",
                    operation="build_jd_summary",
                    from_provider=self.runtime_provider,
                    to_provider="deterministic",
                    reason=str(exc).strip() or exc.__class__.__name__,
                )
            return DeterministicGeneratorProvider().build_jd_summary(jd, candidate)


class OpenAIJudgeProvider:
    def __init__(self, model: str, base_url: str | None, api_key: str, provider: str = "openai", run_dir: Path | None = None) -> None:
        self.model = model
        self.base_url = base_url or "https://api.openai.com/v1"
        self.api_key = api_key
        self.runtime_provider = provider
        self.runtime_model = model
        self.run_dir = run_dir

    def review(self, jd: JDProfile, candidate: CandidateProfile, variant: ResumeVariant, overall_score: float) -> JudgeFeedback:
        prompt = (
            "请用一句简洁中文，说明这个简历版本是否值得投递。\n"
            f"岗位标题：{jd.title}\n"
            f"候选人：{candidate.candidate_id}\n"
            f"版本类型：{variant.variant_type}\n"
            f"综合分：{overall_score:.2f}\n"
            "只返回纯文本，不要附加说明。"
        )
        try:
            rationale = _chat_completion(
                self.base_url,
                self.api_key,
                self.model,
                prompt,
                expect_json=False,
                run_dir=self.run_dir,
                stage="evaluate",
                operation="judge_review",
                provider=self.runtime_provider,
            )
        except Exception as exc:
            if self.run_dir is not None:
                log_fallback_used(
                    self.run_dir,
                    stage="evaluate",
                    operation="judge_review",
                    from_provider=self.runtime_provider,
                    to_provider="deterministic",
                    reason=str(exc).strip() or exc.__class__.__name__,
                )
            rationale = DeterministicJudgeProvider().review(jd, candidate, variant, overall_score).rationale
        worthiness = "apply" if overall_score >= 0.7 else "stretch"
        return JudgeFeedback(rationale=rationale, application_worthiness=worthiness)

    def assess(
        self,
        jd: JDProfile,
        candidate: CandidateProfile,
        variant: ResumeVariant,
        evidence_map: dict[str, object],
        rule_overall_score: float,
    ) -> LLMAssessment:
        prompt = (
            "请仅返回严格 JSON（不要 markdown 代码块、不要额外解释），键必须是："
            "role_fit,evidence_quality,persuasiveness,interview_pressure_risk,"
            "application_worthiness,must_fix_issues,evidence_citations,rewrite_opportunities,decision_rationale。\n"
            f"岗位：{jd.title} @ {jd.company}\n"
            f"简历版本：{variant.variant_id} ({variant.variant_type})\n"
            f"规则综合分：{rule_overall_score:.2f}\n"
            f"候选人优势：{', '.join(candidate.strengths[:4])}\n"
            f"证据映射：{json.dumps(evidence_map, ensure_ascii=False)}\n"
            "所有分数字段范围必须在 0 到 1 之间。"
        )
        raw = _chat_completion(
            self.base_url,
            self.api_key,
            self.model,
            prompt,
            expect_json=True,
            json_language_fields={"decision_rationale"},
            run_dir=self.run_dir,
            stage="evaluate",
            operation="judge_assess",
            provider=self.runtime_provider,
        )
        payload = _parse_json_payload(raw)
        return LLMAssessment(
            jd_id=jd.jd_id,
            variant_id=variant.variant_id,
            role_fit=_safe_score(payload.get("role_fit")),
            evidence_quality=_safe_score(payload.get("evidence_quality")),
            persuasiveness=_safe_score(payload.get("persuasiveness")),
            interview_pressure_risk=_safe_score(payload.get("interview_pressure_risk")),
            application_worthiness=str(payload.get("application_worthiness", "apply")),
            must_fix_issues=_safe_list(payload.get("must_fix_issues")),
            evidence_citations=_safe_list(payload.get("evidence_citations")),
            rewrite_opportunities=_safe_list(payload.get("rewrite_opportunities")),
            decision_rationale=str(payload.get("decision_rationale", "")).strip(),
            provider=self.runtime_provider,
            model=self.runtime_model,
        )


class OpenAIAnalyzeProvider:
    def __init__(self, model: str, base_url: str | None, api_key: str, provider: str = "openai", run_dir: Path | None = None) -> None:
        self.model = model
        self.base_url = base_url or "https://api.openai.com/v1"
        self.api_key = api_key
        self.runtime_provider = provider
        self.runtime_model = model
        self.run_dir = run_dir

    def analyze(self, candidate_id: str, candidate_resume_path: str, resume_text: str, jd_inputs: list[dict[str, str]]) -> AnalyzeFeedback:
        cleaned_jd_inputs = _clean_jd_inputs(jd_inputs)
        prompt = (
            "请仅返回严格 JSON（不要 markdown 代码块、不要额外解释），顶层键必须是："
            "candidate_profile,jd_profiles,evidence_map。\n"
            "candidate_profile 必须包含：core_claims,verified_evidence,missing_evidence_areas,preferred_role_tracks。\n"
            "抽取 candidate_profile 时必须尽量保留 CV 中可追溯硬事实：学历、学校、专业、证书、语言、公司、岗位、年限、项目、技能。"
            "不要因为 PDF 文本没有 bullet 就忽略段落；把教育/证书/语言等硬事实放入 verified_evidence 和 core_claims，"
            "把工作和项目证据放入 experiences/projects/strengths。\n"
            "For candidate_profile.skills, extract concrete technical keywords and group coverage across programming languages, "
            "frameworks, AI stack, tools, and domain knowledge. Do not collapse skills to a major or degree.\n"
            "Definitions: experiences are paid or internship work history with employer/team context; "
            "projects are portfolio, coursework, or side projects; strengths are evidence-backed reusable advantages.\n"
            "For jd_profiles, ignore platform UI text, salary cards, company metadata, apply/save buttons, posted dates, "
            "benefits-only labels, and section headers. Extract only job-related responsibilities and requirements.\n"
            "jd_profiles 必须包含：must_have_requirements,nice_to_have_requirements,hidden_signals,"
            "interview_focus_areas,role_level_confidence。\n"
            f"candidate_id={candidate_id}\nresume_path={candidate_resume_path}\n"
            f"resume_text={resume_text}\n"
            f"jd_inputs={json.dumps(cleaned_jd_inputs, ensure_ascii=False)}\n"
        )
        try:
            raw = _chat_completion(
                self.base_url,
                self.api_key,
                self.model,
                prompt,
                expect_json=True,
                run_dir=self.run_dir,
                stage="analyze",
                operation="analyze_resume_and_jds",
                provider=self.runtime_provider,
            )
            payload = _parse_json_payload(raw)
        except Exception as exc:
            if self.run_dir is not None:
                log_fallback_used(
                    self.run_dir,
                    stage="analyze",
                    operation="analyze_resume_and_jds",
                    from_provider=self.runtime_provider,
                    to_provider="deterministic",
                    reason=str(exc).strip() or exc.__class__.__name__,
                )
            return DeterministicAnalyzeProvider().analyze(candidate_id, candidate_resume_path, resume_text, cleaned_jd_inputs)
        candidate_payload = payload.get("candidate_profile", {})
        candidate = CandidateProfile(
            candidate_id=candidate_id,
            base_resume_path=candidate_resume_path,
            experiences=_safe_list(candidate_payload.get("experiences")),
            projects=_safe_list(candidate_payload.get("projects")),
            skills=_safe_list(candidate_payload.get("skills")),
            industry_tags=_safe_list(candidate_payload.get("industry_tags")),
            strengths=_safe_list(candidate_payload.get("strengths")),
            constraints=_safe_list(candidate_payload.get("constraints")),
            preferences=_safe_list(candidate_payload.get("preferences")),
            core_claims=_safe_list(candidate_payload.get("core_claims")),
            verified_evidence=_safe_list(candidate_payload.get("verified_evidence")),
            missing_evidence_areas=_safe_list(candidate_payload.get("missing_evidence_areas")),
            preferred_role_tracks=_safe_list(candidate_payload.get("preferred_role_tracks")),
        )
        jd_profiles = []
        for item in payload.get("jd_profiles", []):
            if not isinstance(item, dict):
                continue
            responsibilities = _clean_jd_items(_safe_list(item.get("responsibilities")))
            cluster = str(item.get("cluster", "")).strip() or _classify_cluster(str(item.get("title", "")), responsibilities)
            jd_profiles.append(
                JDProfile(
                    jd_id=str(item.get("jd_id", "")),
                    title=str(item.get("title", "")),
                    company=str(item.get("company", "")),
                    cluster=cluster,
                    responsibilities=responsibilities,
                    requirements=_clean_jd_items(_safe_list(item.get("requirements"))),
                    keywords=_safe_list(item.get("keywords")),
                    seniority=str(item.get("seniority", "mid")),
                    bonuses=_clean_jd_items(_safe_list(item.get("bonuses"))),
                    risk_signals=_safe_list(item.get("risk_signals")),
                    source_type=str(item.get("source_type", "file")),
                    source_value=str(item.get("source_value", "")),
                    must_have_requirements=_clean_jd_items(_safe_list(item.get("must_have_requirements"))),
                    nice_to_have_requirements=_clean_jd_items(_safe_list(item.get("nice_to_have_requirements"))),
                    hidden_signals=_safe_list(item.get("hidden_signals")),
                    interview_focus_areas=_safe_list(item.get("interview_focus_areas")),
                    role_level_confidence=_safe_score(item.get("role_level_confidence")),
                )
            )
        evidence_map = payload.get("evidence_map", {})
        if not jd_profiles or not candidate.experiences:
            return DeterministicAnalyzeProvider().analyze(candidate_id, candidate_resume_path, resume_text, cleaned_jd_inputs)
        return AnalyzeFeedback(candidate_profile=candidate, jd_profiles=jd_profiles, evidence_map=evidence_map if isinstance(evidence_map, dict) else {})


class OpenAIPlannerProvider:
    def __init__(self, model: str, base_url: str | None, api_key: str, provider: str = "openai", run_dir: Path | None = None) -> None:
        self.model = model
        self.base_url = base_url or "https://api.openai.com/v1"
        self.api_key = api_key
        self.runtime_provider = provider
        self.runtime_model = model
        self.run_dir = run_dir

    def build_strategy(
        self,
        jd: JDProfile,
        candidate: CandidateProfile,
        assessment: LLMAssessment | None,
        top_variant: ResumeVariant,
        final_score: float,
        guardrail_flags: list[str],
        assessment_failure_reason: str | None = None,
    ) -> PlanFeedback:
        if assessment is None:
            return DeterministicPlannerProvider().build_strategy(
                jd,
                candidate,
                assessment,
                top_variant,
                final_score,
                guardrail_flags,
                assessment_failure_reason=assessment_failure_reason,
            )
        prompt = (
            "请仅返回严格 JSON（不要 markdown 代码块、不要额外解释），键必须是："
            "apply_decision,decision_confidence,decision_drivers,watchouts,"
            "recommended_actions,interview_prep_points,resume_revision_tasks,reason_summary。\n"
            f"岗位：{jd.title} @ {jd.company}\n"
            f"评估结果：{json.dumps(_llm_assessment_to_dict(assessment), ensure_ascii=False)}\n"
            f"护栏标记：{json.dumps(guardrail_flags, ensure_ascii=False)}\n"
            f"最终分：{final_score:.2f}\n"
        )
        raw = _chat_completion(
            self.base_url,
            self.api_key,
            self.model,
            prompt,
            expect_json=True,
            json_language_fields={"reason_summary"},
            run_dir=self.run_dir,
            stage="plan",
            operation="build_strategy",
            provider=self.runtime_provider,
        )
        payload = _parse_json_payload(raw)
        return PlanFeedback(
            strategy=ApplicationStrategy(
                jd_id=jd.jd_id,
                recommended_variant_id=top_variant.variant_id,
                priority_rank=0,
                apply_decision=str(payload.get("apply_decision", "hold")),
                reason_summary=str(payload.get("reason_summary", assessment.decision_rationale)),
                needs_jd_specific_variant=top_variant.variant_type == "jd-specific",
                decision_drivers=_safe_list(payload.get("decision_drivers")),
                watchouts=_safe_list(payload.get("watchouts")) or guardrail_flags,
                recommended_actions=_safe_list(payload.get("recommended_actions")),
                catch_up_notes=candidate.missing_evidence_areas[:2],
                decision_confidence=_safe_score(payload.get("decision_confidence")),
                interview_prep_points=_safe_list(payload.get("interview_prep_points")),
                resume_revision_tasks=_safe_list(payload.get("resume_revision_tasks")),
            )
        )


def build_generator_provider(config: RunConfig, stage: str, run_dir: Path) -> ResumeGeneratorProvider:
    env_path = _resolve_env_file_path(run_dir=run_dir, env_file=config.openai.env_file)
    env_values = _load_dotenv(env_path) if env_path.exists() else {}
    provider = _resolve_provider(config.generator.provider)
    model = _resolve_model(
        configured_model=config.generator.model,
        env_values=env_values,
        role_model_env_key="SHOTGUNCV_GENERATOR_MODEL",
    )
    if provider == "deterministic":
        log_model_resolved(
            run_dir,
            stage="generate",
            role="generator",
            provider=provider,
            configured_model=config.generator.model,
            resolved_model="heuristic-v0.3.0",
            base_url=None,
        )
        return DeterministicGeneratorProvider(provider=provider)
    if provider in {"openai", "openai-compatible"}:
        runtime_model, runtime_base_url, api_key = _resolve_openai_runtime(
            stage=stage,
            provider=provider,
            configured_model=model,
            configured_base_url=config.openai.base_url,
            api_key_env=config.openai.api_key_env,
            env_path=env_path,
            env_values=env_values,
        )
        log_model_resolved(
            run_dir,
            stage="generate",
            role="generator",
            provider=provider,
            configured_model=config.generator.model,
            resolved_model=runtime_model,
            base_url=runtime_base_url,
        )
        return OpenAIGeneratorProvider(
            model=runtime_model,
            base_url=runtime_base_url,
            api_key=api_key,
            provider=provider,
            run_dir=run_dir,
        )
    raise ValueError(f"Unsupported generator provider `{provider}` for stage `{stage}`.")


def build_analyzer_provider(config: RunConfig, stage: str, run_dir: Path) -> AnalyzeProvider:
    env_path = _resolve_env_file_path(run_dir=run_dir, env_file=config.openai.env_file)
    env_values = _load_dotenv(env_path) if env_path.exists() else {}
    provider = _resolve_provider(config.analyzer.provider)
    model = _resolve_model(
        configured_model=config.analyzer.model,
        env_values=env_values,
        role_model_env_key="SHOTGUNCV_ANALYZER_MODEL",
    )
    if provider == "deterministic":
        log_model_resolved(
            run_dir,
            stage="analyze",
            role="analyzer",
            provider=provider,
            configured_model=config.analyzer.model,
            resolved_model="heuristic-v0.3.0",
            base_url=None,
        )
        return DeterministicAnalyzeProvider(provider=provider)
    if provider in {"openai", "openai-compatible"}:
        runtime_model, runtime_base_url, api_key = _resolve_openai_runtime(
            stage=stage,
            provider=provider,
            configured_model=model,
            configured_base_url=config.openai.base_url,
            api_key_env=config.openai.api_key_env,
            env_path=env_path,
            env_values=env_values,
        )
        log_model_resolved(
            run_dir,
            stage="analyze",
            role="analyzer",
            provider=provider,
            configured_model=config.analyzer.model,
            resolved_model=runtime_model,
            base_url=runtime_base_url,
        )
        return OpenAIAnalyzeProvider(model=runtime_model, base_url=runtime_base_url, api_key=api_key, provider=provider, run_dir=run_dir)
    raise ValueError(f"Unsupported analyzer provider `{provider}` for stage `{stage}`.")


def build_judge_provider(config: RunConfig, stage: str, run_dir: Path) -> JudgeProvider:
    env_path = _resolve_env_file_path(run_dir=run_dir, env_file=config.openai.env_file)
    env_values = _load_dotenv(env_path) if env_path.exists() else {}
    provider = _resolve_provider(config.judge.provider)
    model = _resolve_model(
        configured_model=config.judge.model,
        env_values=env_values,
        role_model_env_key="SHOTGUNCV_JUDGE_MODEL",
    )
    if provider == "deterministic":
        log_model_resolved(
            run_dir,
            stage="evaluate",
            role="judge",
            provider=provider,
            configured_model=config.judge.model,
            resolved_model="heuristic-v0.3.0",
            base_url=None,
        )
        return DeterministicJudgeProvider(provider=provider)
    if provider in {"openai", "openai-compatible"}:
        runtime_model, runtime_base_url, api_key = _resolve_openai_runtime(
            stage=stage,
            provider=provider,
            configured_model=model,
            configured_base_url=config.openai.base_url,
            api_key_env=config.openai.api_key_env,
            env_path=env_path,
            env_values=env_values,
        )
        log_model_resolved(
            run_dir,
            stage="evaluate",
            role="judge",
            provider=provider,
            configured_model=config.judge.model,
            resolved_model=runtime_model,
            base_url=runtime_base_url,
        )
        return OpenAIJudgeProvider(
            model=runtime_model,
            base_url=runtime_base_url,
            api_key=api_key,
            provider=provider,
            run_dir=run_dir,
        )
    raise ValueError(f"Unsupported judge provider `{provider}` for stage `{stage}`.")


def build_planner_provider(config: RunConfig, stage: str, run_dir: Path) -> PlannerProvider:
    env_path = _resolve_env_file_path(run_dir=run_dir, env_file=config.openai.env_file)
    env_values = _load_dotenv(env_path) if env_path.exists() else {}
    provider = _resolve_provider(config.planner.provider)
    model = _resolve_model(
        configured_model=config.planner.model,
        env_values=env_values,
        role_model_env_key="SHOTGUNCV_PLANNER_MODEL",
    )
    if provider == "deterministic":
        log_model_resolved(
            run_dir,
            stage="plan",
            role="planner",
            provider=provider,
            configured_model=config.planner.model,
            resolved_model="heuristic-v0.3.0",
            base_url=None,
        )
        return DeterministicPlannerProvider(provider=provider)
    if provider in {"openai", "openai-compatible"}:
        runtime_model, runtime_base_url, api_key = _resolve_openai_runtime(
            stage=stage,
            provider=provider,
            configured_model=model,
            configured_base_url=config.openai.base_url,
            api_key_env=config.openai.api_key_env,
            env_path=env_path,
            env_values=env_values,
        )
        log_model_resolved(
            run_dir,
            stage="plan",
            role="planner",
            provider=provider,
            configured_model=config.planner.model,
            resolved_model=runtime_model,
            base_url=runtime_base_url,
        )
        return OpenAIPlannerProvider(model=runtime_model, base_url=runtime_base_url, api_key=api_key, provider=provider, run_dir=run_dir)
    raise ValueError(f"Unsupported planner provider `{provider}` for stage `{stage}`.")


def _resolve_openai_runtime(
    stage: str,
    provider: str,
    configured_model: str,
    configured_base_url: str | None,
    api_key_env: str,
    env_path: Path,
    env_values: dict[str, str],
) -> tuple[str, str, str]:
    if not env_path.exists():
        raise RuntimeError(
            f"Stage `{stage}` failed for provider `{provider}`: missing `.env` file `{env_path}`."
        )
    resolved_model = configured_model.strip() or DEFAULT_OPENAI_MODEL
    resolved_base_url = (
        env_values.get("OPENAI_BASE_URL", "").strip()
        or (configured_base_url or "").strip()
        or "https://api.openai.com/v1"
    )
    api_key_name = env_values.get("OPENAI_API_KEY_ENV", "").strip() or api_key_env
    api_key = env_values.get(api_key_name, "").strip()
    if api_key:
        return resolved_model, resolved_base_url, api_key
    raise RuntimeError(
        f"Stage `{stage}` failed for provider `{provider}` model `{resolved_model}`: missing key `{api_key_name}` in `{env_path}`."
    )


def _resolve_provider(configured_provider: str) -> str:
    return (configured_provider or "deterministic").strip().lower()


def _resolve_model(configured_model: str, env_values: dict[str, str], role_model_env_key: str) -> str:
    return (
        env_values.get(role_model_env_key, "").strip()
        or env_values.get("OPENAI_MODEL", "").strip()
        or configured_model.strip()
        or DEFAULT_OPENAI_MODEL
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


def _clean_jd_inputs(jd_inputs: list[dict[str, str]]) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for item in jd_inputs:
        copied = dict(item)
        copied["content"] = _clean_jd_text_content(str(item.get("content", "")))
        cleaned.append(copied)
    return cleaned


def _clean_jd_text_content(content: str) -> str:
    cleaned_lines: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            cleaned_lines.append(raw_line)
            continue
        marker = ""
        body = line
        if line.startswith("-"):
            marker = "- "
            body = line.strip("- ").strip()
        if _is_jd_ui_noise(body):
            continue
        cleaned_lines.append(f"{marker}{body}" if marker else raw_line)
    return "\n".join(cleaned_lines)


def _clean_jd_items(items: list[str]) -> list[str]:
    cleaned: list[str] = []
    for item in items:
        normalized = item.strip().strip("-*•").strip()
        if normalized and not _is_jd_ui_noise(normalized):
            cleaned.append(normalized)
    return _dedupe_preserve_order(cleaned)


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


def _extract_skill_labels(text: str) -> list[str]:
    lowered = text.lower()
    known_skills = [
        ("python", "Python"),
        ("click", "Click"),
        ("pydantic", "Pydantic"),
        ("fastapi", "FastAPI"),
        ("docker", "Docker"),
        ("redis", "Redis"),
        ("langchain", "LangChain"),
        ("langgraph", "LangGraph"),
        ("qdrant", "Qdrant"),
        ("bm25", "BM25"),
        ("ragas", "RAGAS"),
        ("rag", "RAG"),
        ("llm", "LLM"),
        ("sql", "SQL"),
        ("java", "Java"),
        ("computer science", "Computer Science"),
        ("pmp", "PMP"),
        ("certificate", "Certificates"),
        ("certification", "Certificates"),
    ]
    return _dedupe_preserve_order([label for keyword, label in known_skills if keyword in lowered])


def _extract_header(block: str, label: str) -> str:
    marker = f"{label}:"
    for line in block.splitlines():
        if line.strip().startswith(marker):
            return line.split(":", maxsplit=1)[1].strip()
    return ""


def _extract_body_lines(block: str) -> list[str]:
    if "Body:" in block:
        body = block.split("Body:", maxsplit=1)[1]
        lines = [
            line.strip("- ").strip()
            for line in body.splitlines()
            if line.strip().startswith("-") and not _is_jd_ui_noise(line.strip("- ").strip())
        ]
        if lines:
            return lines
    ignored_prefixes = ("Title:", "Company:")
    lines: list[str] = []
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(ignored_prefixes):
            continue
        normalized = line.lstrip("-0123456789.、)） ").strip()
        if len(normalized) >= 6 and not _is_jd_ui_noise(normalized):
            lines.append(normalized)
    return lines[:24]


def _extract_resume_sections(resume_text: str) -> dict[str, list[str]]:
    lines: list[str] = []
    for raw_line in resume_text.splitlines():
        normalized = _normalize_resume_line(raw_line)
        if normalized:
            lines.extend(_split_inline_resume_sections(normalized))
    if not lines:
        return {"experiences": [], "projects": [], "skills": [], "strengths": [], "evidence": []}

    experiences: list[str] = []
    projects: list[str] = []
    skills: list[str] = []
    hard_facts: list[str] = []
    current_section = ""
    for line in lines:
        if _is_resume_metadata_line(line):
            continue
        section = _resume_section_name(line)
        if section:
            current_section = section
            remainder = _strip_resume_heading(line)
            if not remainder:
                continue
            line = remainder
        if _is_resume_metadata_line(line):
            continue
        target_section = current_section or _infer_resume_section(line)
        if target_section == "ignore":
            continue
        if target_section == "project":
            projects.append(line)
        elif target_section == "skill":
            skills.append(line)
        elif target_section == "hard_fact":
            hard_facts.append(line)
        else:
            experiences.append(line)

    evidence = _dedupe_preserve_order(hard_facts + experiences + projects + skills)
    strengths = _dedupe_preserve_order(experiences + projects + skills)
    return {
        "experiences": _dedupe_preserve_order(experiences)[:12],
        "projects": _dedupe_preserve_order(projects)[:8],
        "skills": _dedupe_preserve_order(skills)[:12],
        "strengths": strengths[:6],
        "evidence": evidence[:16],
    }


def _normalize_resume_line(line: str) -> str:
    normalized = line.strip().lstrip("-*•·0123456789.、)） ").strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _split_inline_resume_sections(line: str) -> list[str]:
    markers = [
        "Education:",
        "Certificate:",
        "Certificates:",
        "Certification:",
        "Experience:",
        "Work Experience:",
        "Projects:",
        "Skills:",
        "Technical Skills:",
        "教育背景：",
        "教育经历：",
        "证书：",
        "工作经历：",
        "项目经历：",
        "专业技能：",
    ]
    pattern = "|".join(re.escape(marker) for marker in sorted(markers, key=len, reverse=True))
    parts = re.split(f"(?=\\b(?:{pattern}))", line)
    return [part.strip(" .") for part in parts if part.strip(" .")]


def _is_resume_metadata_line(line: str) -> bool:
    lowered = line.lower().strip()
    metadata_markers = [
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
    return any(marker in lowered for marker in metadata_markers)


def _resume_section_name(line: str) -> str:
    lowered = line.lower().strip(":：")
    section_map = {
        "basic information": "ignore",
        "contact": "ignore",
        "contact information": "ignore",
        "基本信息": "ignore",
        "个人信息": "ignore",
        "联系方式": "ignore",
        "求职意向": "ignore",
        "education background": "hard_fact",
        "教育": "hard_fact",
        "教育背景": "hard_fact",
        "教育经历": "hard_fact",
        "学历": "hard_fact",
        "工作经历": "experience",
        "工作经验": "experience",
        "实习经历": "experience",
        "项目经历": "project",
        "项目": "project",
        "技能": "skill",
        "专业技能": "skill",
        "education": "hard_fact",
        "教育": "hard_fact",
        "教育经历": "hard_fact",
        "学历": "hard_fact",
        "certifications": "hard_fact",
        "certificates": "hard_fact",
        "证书": "hard_fact",
        "语言": "hard_fact",
        "languages": "hard_fact",
        "experience": "experience",
        "work experience": "experience",
        "工作经历": "experience",
        "实习经历": "experience",
        "professional experience": "experience",
        "projects": "project",
        "project experience": "project",
        "项目经历": "project",
        "项目": "project",
        "skills": "skill",
        "technical skills": "skill",
        "技能": "skill",
        "专业技能": "skill",
    }
    for heading, section in section_map.items():
        if lowered == heading or lowered.startswith(f"{heading}:") or lowered.startswith(f"{heading}："):
            return section
    return ""


def _strip_known_resume_heading(line: str) -> str:
    headings = [
        "basic information",
        "contact information",
        "contact",
        "education background",
        "education",
        "certifications",
        "certification",
        "certificates",
        "certificate",
        "languages",
        "work experience",
        "professional experience",
        "experience",
        "project experience",
        "projects",
        "project",
        "technical skills",
        "skills",
        "基本信息",
        "个人信息",
        "联系方式",
        "求职意向",
        "教育背景",
        "教育经历",
        "教育",
        "学历",
        "证书",
        "语言",
        "工作经历",
        "工作经验",
        "实习经历",
        "项目经历",
        "项目",
        "专业技能",
        "技能",
    ]
    lowered = line.lower()
    stripped = line.strip()
    for heading in sorted(headings, key=len, reverse=True):
        heading_lower = heading.lower()
        if lowered == heading_lower:
            return ""
        for separator in (":", "："):
            prefix = f"{heading_lower}{separator}"
            if lowered.startswith(prefix):
                return stripped[len(prefix) :].strip()
    return stripped


def _strip_resume_heading(line: str) -> str:
    known = _strip_known_resume_heading(line)
    if known != line.strip():
        return known
    return re.sub(
        r"^(education|certifications?|languages?|experience|work experience|professional experience|projects?|skills|"
        r"教育经历|教育|学历|证书|语言|工作经历|实习经历|项目经历|项目|专业技能|技能)\s*[:：]\s*",
        "",
        line,
        flags=re.IGNORECASE,
    ).strip()


def _infer_resume_section(line: str) -> str:
    lowered = line.lower()
    hard_fact_needles = [
        "bachelor",
        "master",
        "phd",
        "degree",
        "university",
        "college",
        "computer science",
        "certificate",
        "certification",
        "pmp",
        "本科",
        "硕士",
        "博士",
        "大学",
        "学院",
        "计算机",
        "专业",
        "证书",
        "英语",
    ]
    if any(needle in lowered for needle in hard_fact_needles):
        return "hard_fact"
    if any(needle in lowered for needle in ["project", "prototype", "项目", "平台", "系统", "工具"]):
        return "project"
    if any(needle in lowered for needle in ["python", "llm", "sql", "java", "技能", "skills", "automation"]):
        return "skill"
    return "experience"


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _first_meaningful_line(block: str) -> str:
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if line and not line.startswith(("Title:", "Company:", "Body:")):
            return line[:80]
    return ""


def _extract_keywords(text: str) -> list[str]:
    keyword_map = [
        ("evaluation", "evaluation"),
        ("ranking", "ranking"),
        ("python", "python"),
        ("prompt", "prompt engineering"),
        ("product", "product collaboration"),
        ("automation", "automation"),
        ("metrics", "metrics"),
        ("experimentation", "experimentation"),
        ("llm", "llm"),
    ]
    lowered = text.lower()
    keywords = [label for needle, label in keyword_map if needle in lowered]
    return keywords[:5] or ["python", "ai workflows"]


def _classify_cluster(title: str, body_lines: list[str]) -> str:
    for source in [title, " ".join(body_lines)]:
        tokens = _CLUSTER_TOKEN_PATTERN.findall(source.lower())
        if tokens:
            return "-".join(tokens[:4])
    return "general"


def _build_risk_signals(body_lines: list[str]) -> list[str]:
    signals = []
    lowered = " ".join(body_lines).lower()
    if "metrics" in lowered or "experimentation" in lowered:
        signals.append("Requires metrics storytelling")
    if "prompt" in lowered:
        signals.append("Prompt quality will be probed")
    return signals


def _parse_json_payload(raw: str) -> dict[str, object]:
    return parse_json_object(raw)


def _safe_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _safe_score(value: object) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(max(0.0, min(1.0, numeric)), 2)


def _llm_assessment_to_dict(assessment: LLMAssessment) -> dict[str, object]:
    return {
        "jd_id": assessment.jd_id,
        "variant_id": assessment.variant_id,
        "role_fit": assessment.role_fit,
        "evidence_quality": assessment.evidence_quality,
        "persuasiveness": assessment.persuasiveness,
        "interview_pressure_risk": assessment.interview_pressure_risk,
        "application_worthiness": assessment.application_worthiness,
        "must_fix_issues": assessment.must_fix_issues,
        "evidence_citations": assessment.evidence_citations,
        "rewrite_opportunities": assessment.rewrite_opportunities,
        "decision_rationale": assessment.decision_rationale,
        "provider": assessment.provider,
        "model": assessment.model,
    }


def _build_system_prompt(expect_json: bool) -> str:
    return _shared_system_prompt(expect_json=expect_json)


def _is_chinese_dominant(text: str, min_ratio: float = 0.45) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    cjk_count = len(_CJK_PATTERN.findall(stripped))
    ascii_count = len(_ASCII_LETTER_PATTERN.findall(stripped))
    if cjk_count == 0:
        return False
    if ascii_count == 0:
        return True
    ratio = cjk_count / (cjk_count + ascii_count)
    return ratio >= min_ratio


def _is_identifier_like(value: str) -> bool:
    text = value.strip()
    if not text:
        return True
    if _IDENTIFIER_LIKE_PATTERN.fullmatch(text):
        return True
    if len(text) <= 5 and _ASCII_LETTER_PATTERN.search(text):
        return True
    return False


def _iter_string_values(payload: object) -> list[str]:
    values: list[str] = []
    if isinstance(payload, dict):
        for value in payload.values():
            values.extend(_iter_string_values(value))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(_iter_string_values(item))
    elif isinstance(payload, str):
        values.append(payload)
    return values


def _iter_field_string_values(payload: object, field_names: set[str]) -> list[str]:
    values: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in field_names:
                values.extend(_iter_string_values(value))
            values.extend(_iter_field_string_values(value, field_names))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(_iter_field_string_values(item, field_names))
    return values


def _json_values_chinese_dominant(payload: dict[str, object], field_names: set[str] | None = None) -> bool:
    has_natural_language = False
    string_values = _iter_field_string_values(payload, field_names) if field_names else _iter_string_values(payload)
    for value in string_values:
        text = value.strip()
        if not text:
            continue
        if _is_identifier_like(text):
            continue
        has_natural_language = True
        if not _is_chinese_dominant(text):
            return False
    if field_names is not None:
        return True if not has_natural_language else has_natural_language
    return has_natural_language


def _chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    expect_json: bool,
    json_language_fields: set[str] | None = None,
    run_dir: Path | None = None,
    stage: str | None = None,
    operation: str = "chat_completion",
    provider: str = "openai",
) -> str:
    messages = [
        {"role": "system", "content": _build_system_prompt(expect_json=expect_json)},
        {"role": "user", "content": prompt},
    ]
    last_output = ""
    last_error: Exception | None = None

    for _ in range(DEFAULT_LLM_RETRY_TIMES):
        call_started = None
        if run_dir is not None and stage is not None:
            call_started = log_llm_call_started(
                run_dir,
                stage=stage,
                operation=operation,
                provider=provider,
                model=model,
            )
        payload = json.dumps(
            {
                "model": model,
                "messages": messages,
                "temperature": 0.2,
            }
        ).encode("utf-8")
        try:
            response = request.Request(
                url=f"{base_url.rstrip('/')}/chat/completions",
                data=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with request.urlopen(response, timeout=DEFAULT_OPENAI_TIMEOUT_SEC) as handle:
                body = json.loads(handle.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            if run_dir is not None and stage is not None and call_started is not None:
                log_llm_call_failed(
                    run_dir,
                    stage=stage,
                    operation=operation,
                    provider=provider,
                    model=model,
                    started=call_started,
                    error=exc,
                    fallback_used=False,
                )
            continue
        usage = body.get("usage", {}) if isinstance(body, dict) else {}
        content = body["choices"][0]["message"]["content"].strip()
        last_output = content

        try:
            if expect_json:
                parsed = _parse_json_payload(content)
                if json_language_fields and not _json_values_chinese_dominant(parsed, json_language_fields):
                    raise ValueError("JSON value language check failed")
            else:
                if not _is_chinese_dominant(content):
                    raise ValueError("text language check failed")
            if run_dir is not None and stage is not None and call_started is not None:
                log_llm_call_finished(
                    run_dir,
                    stage=stage,
                    operation=operation,
                    provider=provider,
                    model=model,
                    started=call_started,
                    prompt_tokens=_safe_optional_int(usage.get("prompt_tokens")),
                    completion_tokens=_safe_optional_int(usage.get("completion_tokens")),
                    total_tokens=_safe_optional_int(usage.get("total_tokens")),
                    output_parse_status="success",
                )
            return content
        except Exception as exc:
            last_error = exc
            if run_dir is not None and stage is not None and call_started is not None:
                log_llm_call_failed(
                    run_dir,
                    stage=stage,
                    operation=operation,
                    provider=provider,
                    model=model,
                    started=call_started,
                    error=exc,
                    fallback_used=False,
                )
            continue

    if last_error is not None:
        raise ValueError(f"LLM output failed Chinese dominance check: {last_output[:200]}") from last_error
    raise ValueError("LLM returned empty output.")


def _safe_optional_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
