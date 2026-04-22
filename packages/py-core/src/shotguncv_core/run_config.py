from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shotguncv_core.storage import dump_json, load_json, stage_dir


@dataclass(slots=True)
class ProviderConfig:
    provider: str
    model: str = ""


@dataclass(slots=True)
class OpenAIConfig:
    base_url: str | None = None
    api_key_env: str = "OPENAI_API_KEY"
    env_file: str = ".env"


@dataclass(slots=True)
class RunMetadata:
    label: str = ""


@dataclass(slots=True)
class RunConfig:
    analyzer: ProviderConfig
    generator: ProviderConfig
    judge: ProviderConfig
    planner: ProviderConfig
    openai: OpenAIConfig
    run_metadata: RunMetadata


RUN_CONFIG_PATH = Path("config") / "run_config.json"
DEFAULT_PROVIDER = "openai"


def default_run_config() -> RunConfig:
    return RunConfig(
        analyzer=ProviderConfig(provider=DEFAULT_PROVIDER),
        generator=ProviderConfig(provider=DEFAULT_PROVIDER),
        judge=ProviderConfig(provider=DEFAULT_PROVIDER),
        planner=ProviderConfig(provider=DEFAULT_PROVIDER),
        openai=OpenAIConfig(),
        run_metadata=RunMetadata(),
    )


def snapshot_run_config(run_dir: Path, source_path: Path | None = None) -> Path:
    config = default_run_config() if source_path is None else _from_payload(load_json(source_path))
    normalized = _normalize_run_config(config)
    return dump_json(run_dir / RUN_CONFIG_PATH, normalized)


def load_run_config(run_dir: Path) -> RunConfig:
    config_path = run_dir / RUN_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(
            f"Missing `{config_path.name}` in `{config_path.parent}`. Run `shotguncv ingest --run-dir {run_dir}` first."
        )
    return _normalize_run_config(_from_payload(load_json(config_path)))


def config_stage_dir(run_dir: Path) -> Path:
    return stage_dir(run_dir, "config")


def _normalize_run_config(config: RunConfig) -> RunConfig:
    analyzer = ProviderConfig(provider=config.analyzer.provider, model=config.analyzer.model or "")
    generator = ProviderConfig(provider=config.generator.provider, model=config.generator.model or "")
    judge = ProviderConfig(provider=config.judge.provider, model=config.judge.model or "")
    planner = ProviderConfig(provider=config.planner.provider, model=config.planner.model or "")
    openai = OpenAIConfig(
        base_url=config.openai.base_url or None,
        api_key_env=config.openai.api_key_env or "OPENAI_API_KEY",
        env_file=config.openai.env_file or ".env",
    )
    metadata = RunMetadata(label=config.run_metadata.label or "")
    return RunConfig(
        analyzer=analyzer,
        generator=generator,
        judge=judge,
        planner=planner,
        openai=openai,
        run_metadata=metadata,
    )


def _from_payload(payload: Any) -> RunConfig:
    if not isinstance(payload, dict):
        raise ValueError("Run config payload must be a JSON object.")
    analyzer_data = payload.get("analyzer")
    generator_data = payload.get("generator")
    judge_data = payload.get("judge")
    planner_data = payload.get("planner")
    openai_data = payload.get("openai")
    metadata_data = payload.get("run_metadata")

    analyzer = ProviderConfig(
        provider=str(analyzer_data.get("provider", DEFAULT_PROVIDER)) if isinstance(analyzer_data, dict) else DEFAULT_PROVIDER,
        model=str(analyzer_data.get("model", "")) if isinstance(analyzer_data, dict) else "",
    )
    generator = ProviderConfig(
        provider=str(generator_data.get("provider", DEFAULT_PROVIDER)) if isinstance(generator_data, dict) else DEFAULT_PROVIDER,
        model=str(generator_data.get("model", "")) if isinstance(generator_data, dict) else "",
    )
    judge = ProviderConfig(
        provider=str(judge_data.get("provider", DEFAULT_PROVIDER)) if isinstance(judge_data, dict) else DEFAULT_PROVIDER,
        model=str(judge_data.get("model", "")) if isinstance(judge_data, dict) else "",
    )
    planner = ProviderConfig(
        provider=str(planner_data.get("provider", DEFAULT_PROVIDER)) if isinstance(planner_data, dict) else DEFAULT_PROVIDER,
        model=str(planner_data.get("model", "")) if isinstance(planner_data, dict) else "",
    )

    openai = OpenAIConfig(
        base_url=str(openai_data.get("base_url")) if isinstance(openai_data, dict) and openai_data.get("base_url") else None,
        api_key_env=str(openai_data.get("api_key_env", "OPENAI_API_KEY")) if isinstance(openai_data, dict) else "OPENAI_API_KEY",
        env_file=str(openai_data.get("env_file", ".env")) if isinstance(openai_data, dict) else ".env",
    )
    metadata = RunMetadata(label=str(metadata_data.get("label", "")) if isinstance(metadata_data, dict) else "")
    return RunConfig(
        analyzer=analyzer,
        generator=generator,
        judge=judge,
        planner=planner,
        openai=openai,
        run_metadata=metadata,
    )
