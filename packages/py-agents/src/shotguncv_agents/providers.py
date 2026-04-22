from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib import request
from typing import Protocol

from shotguncv_core.models import CandidateProfile, JDProfile, ResumeVariant
from shotguncv_core.run_config import RunConfig

DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"


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
    with request.urlopen(response, timeout=30) as handle:
        body = json.loads(handle.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"].strip()
