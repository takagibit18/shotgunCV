from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib import request
from typing import Protocol

from shotguncv_core.models import ApplicationStrategy, CandidateProfile, JDProfile, LLMAssessment, ResumeVariant
from shotguncv_core.run_config import RunConfig

DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
DEFAULT_OPENAI_TIMEOUT_SEC = 90


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
    ) -> PlanFeedback:
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
            provider="deterministic",
            model="heuristic-v0.3.0",
        )


class DeterministicAnalyzeProvider:
    def analyze(self, candidate_id: str, candidate_resume_path: str, resume_text: str, jd_inputs: list[dict[str, str]]) -> AnalyzeFeedback:
        bullet_lines = [line.strip("- ").strip() for line in resume_text.splitlines() if line.strip().startswith("-")]
        lowered = " ".join(bullet_lines).lower()
        skills = []
        for keyword, label in (
            ("python", "Python"),
            ("llm", "LLM workflows"),
            ("resume", "Resume evaluation"),
            ("product", "Product collaboration"),
        ):
            if keyword in lowered:
                skills.append(label)

        candidate = CandidateProfile(
            candidate_id=candidate_id,
            base_resume_path=candidate_resume_path,
            experiences=bullet_lines,
            projects=[line for line in bullet_lines if "prototype" in line.lower() or "tool" in line.lower()],
            skills=skills or ["AI workflow delivery"],
            industry_tags=["AI tooling", "Resume ops"],
            strengths=bullet_lines[:2] or ["Structured AI workflow delivery"],
            constraints=["No explicit production ML platform ownership yet"],
            preferences=["Product-oriented AI roles"],
            core_claims=bullet_lines[:3],
            verified_evidence=bullet_lines[:4],
            missing_evidence_areas=["Large-scale online experiment ownership"],
            preferred_role_tracks=["LLM Product Engineer", "Applied AI Ops"],
        )
        jd_profiles: list[JDProfile] = []
        evidence_map: dict[str, object] = {"candidate": {}, "jds": {}, "risks": []}
        for jd_input in jd_inputs:
            source_type = jd_input["source_type"]
            source_value = jd_input["source_value"]
            blocks = [block.strip() for block in jd_input["content"].split("=== JD ===") if block.strip()]
            for index, block in enumerate(blocks, start=1):
                title = _extract_header(block, "Title")
                company = _extract_header(block, "Company")
                body_lines = _extract_body_lines(block)
                keyword_candidates = _extract_keywords(" ".join(body_lines))
                bonuses = [line.replace("Bonus for ", "").strip() for line in body_lines if "bonus" in line.lower()]
                must_have = body_lines[:2]
                nice_to_have = bonuses[:2]
                profile = JDProfile(
                    jd_id=f"jd-{index:03d}",
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
    def build_strategy(
        self,
        jd: JDProfile,
        candidate: CandidateProfile,
        assessment: LLMAssessment | None,
        top_variant: ResumeVariant,
        final_score: float,
        guardrail_flags: list[str],
    ) -> PlanFeedback:
        decision = "apply" if final_score >= 0.7 else "hold"
        confidence = round(min(0.95, max(0.35, final_score + 0.1)), 2)
        rationale = assessment.decision_rationale if assessment else "Guardrail fallback strategy."
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
    def __init__(self, model: str, base_url: str | None, api_key: str) -> None:
        self.model = model
        self.base_url = base_url or "https://api.openai.com/v1"
        self.api_key = api_key

    def build_cluster_summary(self, cluster: str, candidate: CandidateProfile, jds: list[JDProfile]) -> str:
        titles = ", ".join(jd.title for jd in jds)
        prompt = (
            "Write a concise resume summary for a cluster resume variant.\n"
            f"Cluster: {cluster}\n"
            f"Candidate strengths: {', '.join(candidate.strengths)}\n"
            f"Target titles: {titles}\n"
            "Return plain text only."
        )
        return _chat_completion(self.base_url, self.api_key, self.model, prompt)

    def build_jd_summary(self, jd: JDProfile, candidate: CandidateProfile) -> str:
        prompt = (
            "Write a concise resume summary for one JD-targeted variant.\n"
            f"JD title: {jd.title}\n"
            f"Company: {jd.company}\n"
            f"JD keywords: {', '.join(jd.keywords)}\n"
            f"Candidate strengths: {', '.join(candidate.strengths)}\n"
            "Return plain text only."
        )
        return _chat_completion(self.base_url, self.api_key, self.model, prompt)


class OpenAIJudgeProvider:
    def __init__(self, model: str, base_url: str | None, api_key: str) -> None:
        self.model = model
        self.base_url = base_url or "https://api.openai.com/v1"
        self.api_key = api_key

    def review(self, jd: JDProfile, candidate: CandidateProfile, variant: ResumeVariant, overall_score: float) -> JudgeFeedback:
        prompt = (
            "Write one short rationale for whether this resume variant is worth applying with.\n"
            f"JD title: {jd.title}\n"
            f"Candidate: {candidate.candidate_id}\n"
            f"Variant type: {variant.variant_type}\n"
            f"Overall score: {overall_score:.2f}\n"
            "Return plain text only."
        )
        rationale = _chat_completion(self.base_url, self.api_key, self.model, prompt)
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
            "Return STRICT JSON only with keys: role_fit,evidence_quality,persuasiveness,"
            "interview_pressure_risk,application_worthiness,must_fix_issues,evidence_citations,"
            "rewrite_opportunities,decision_rationale.\n"
            f"JD: {jd.title} @ {jd.company}\n"
            f"Variant: {variant.variant_id} ({variant.variant_type})\n"
            f"Rule overall score: {rule_overall_score:.2f}\n"
            f"Candidate strengths: {', '.join(candidate.strengths[:4])}\n"
            f"Evidence map: {json.dumps(evidence_map, ensure_ascii=False)}\n"
            "All score fields must be between 0 and 1."
        )
        raw = _chat_completion(self.base_url, self.api_key, self.model, prompt)
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
            provider="openai",
            model=self.model,
        )


class OpenAIAnalyzeProvider:
    def __init__(self, model: str, base_url: str | None, api_key: str) -> None:
        self.model = model
        self.base_url = base_url or "https://api.openai.com/v1"
        self.api_key = api_key

    def analyze(self, candidate_id: str, candidate_resume_path: str, resume_text: str, jd_inputs: list[dict[str, str]]) -> AnalyzeFeedback:
        prompt = (
            "Return STRICT JSON only with keys: candidate_profile,jd_profiles,evidence_map.\n"
            "candidate_profile must include: core_claims,verified_evidence,missing_evidence_areas,preferred_role_tracks.\n"
            "jd_profiles must include: must_have_requirements,nice_to_have_requirements,hidden_signals,"
            "interview_focus_areas,role_level_confidence.\n"
            f"candidate_id={candidate_id}\nresume_path={candidate_resume_path}\n"
            f"resume_text={resume_text}\n"
            f"jd_inputs={json.dumps(jd_inputs, ensure_ascii=False)}\n"
        )
        raw = _chat_completion(self.base_url, self.api_key, self.model, prompt)
        payload = _parse_json_payload(raw)
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
            jd_profiles.append(
                JDProfile(
                    jd_id=str(item.get("jd_id", "")),
                    title=str(item.get("title", "")),
                    company=str(item.get("company", "")),
                    cluster=str(item.get("cluster", "ai-operations")),
                    responsibilities=_safe_list(item.get("responsibilities")),
                    requirements=_safe_list(item.get("requirements")),
                    keywords=_safe_list(item.get("keywords")),
                    seniority=str(item.get("seniority", "mid")),
                    bonuses=_safe_list(item.get("bonuses")),
                    risk_signals=_safe_list(item.get("risk_signals")),
                    source_type=str(item.get("source_type", "file")),
                    source_value=str(item.get("source_value", "")),
                    must_have_requirements=_safe_list(item.get("must_have_requirements")),
                    nice_to_have_requirements=_safe_list(item.get("nice_to_have_requirements")),
                    hidden_signals=_safe_list(item.get("hidden_signals")),
                    interview_focus_areas=_safe_list(item.get("interview_focus_areas")),
                    role_level_confidence=_safe_score(item.get("role_level_confidence")),
                )
            )
        evidence_map = payload.get("evidence_map", {})
        if not jd_profiles or not candidate.experiences:
            return DeterministicAnalyzeProvider().analyze(candidate_id, candidate_resume_path, resume_text, jd_inputs)
        return AnalyzeFeedback(candidate_profile=candidate, jd_profiles=jd_profiles, evidence_map=evidence_map if isinstance(evidence_map, dict) else {})


class OpenAIPlannerProvider:
    def __init__(self, model: str, base_url: str | None, api_key: str) -> None:
        self.model = model
        self.base_url = base_url or "https://api.openai.com/v1"
        self.api_key = api_key

    def build_strategy(
        self,
        jd: JDProfile,
        candidate: CandidateProfile,
        assessment: LLMAssessment | None,
        top_variant: ResumeVariant,
        final_score: float,
        guardrail_flags: list[str],
    ) -> PlanFeedback:
        if assessment is None:
            return DeterministicPlannerProvider().build_strategy(jd, candidate, assessment, top_variant, final_score, guardrail_flags)
        prompt = (
            "Return STRICT JSON only with keys: apply_decision,decision_confidence,decision_drivers,watchouts,"
            "recommended_actions,interview_prep_points,resume_revision_tasks,reason_summary.\n"
            f"JD={jd.title} @ {jd.company}\n"
            f"Assessment={json.dumps(_llm_assessment_to_dict(assessment), ensure_ascii=False)}\n"
            f"Guardrails={json.dumps(guardrail_flags, ensure_ascii=False)}\n"
            f"Final score={final_score:.2f}\n"
        )
        raw = _chat_completion(self.base_url, self.api_key, self.model, prompt)
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
        return DeterministicGeneratorProvider()
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
        return OpenAIGeneratorProvider(
            model=runtime_model,
            base_url=runtime_base_url,
            api_key=api_key,
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
        return DeterministicAnalyzeProvider()
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
        return OpenAIAnalyzeProvider(model=runtime_model, base_url=runtime_base_url, api_key=api_key)
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
        return DeterministicJudgeProvider()
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
        return OpenAIJudgeProvider(
            model=runtime_model,
            base_url=runtime_base_url,
            api_key=api_key,
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
        return DeterministicPlannerProvider()
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
        return OpenAIPlannerProvider(model=runtime_model, base_url=runtime_base_url, api_key=api_key)
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


def _extract_header(block: str, label: str) -> str:
    marker = f"{label}:"
    for line in block.splitlines():
        if line.strip().startswith(marker):
            return line.split(":", maxsplit=1)[1].strip()
    return ""


def _extract_body_lines(block: str) -> list[str]:
    if "Body:" not in block:
        return []
    body = block.split("Body:", maxsplit=1)[1]
    return [line.strip("- ").strip() for line in body.splitlines() if line.strip().startswith("-")]


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
    lowered = f"{title} {' '.join(body_lines)}".lower()
    if "product" in lowered or "evaluation" in lowered or "prompt" in lowered:
        return "ai-product"
    return "ai-operations"


def _build_risk_signals(body_lines: list[str]) -> list[str]:
    signals = []
    lowered = " ".join(body_lines).lower()
    if "metrics" in lowered or "experimentation" in lowered:
        signals.append("Requires metrics storytelling")
    if "prompt" in lowered:
        signals.append("Prompt quality will be probed")
    return signals


def _parse_json_payload(raw: str) -> dict[str, object]:
    candidate = raw.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        candidate = candidate.replace("json", "", 1).strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Expected JSON from LLM provider, got invalid output: {raw[:160]}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Expected JSON object payload from LLM provider.")
    return payload


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


def _chat_completion(base_url: str, api_key: str, model: str, prompt: str) -> str:
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
    ).encode("utf-8")
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
    return body["choices"][0]["message"]["content"].strip()
