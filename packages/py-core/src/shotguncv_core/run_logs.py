from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

from shotguncv_core.run_config import default_run_config, load_run_config
from shotguncv_core.run_status import StageName, now_iso
from shotguncv_core.storage import ensure_directory, to_plain_data


LOG_PATH = Path("logs") / "run_events.jsonl"


def append_event(run_dir: Path, event: dict[str, Any]) -> Path:
    path = run_dir / LOG_PATH
    ensure_directory(path.parent)
    import json

    payload = {"timestamp": now_iso(), **event}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(to_plain_data(payload), ensure_ascii=False, separators=(",", ":")) + "\n")
    return path


def log_run_started(
    run_dir: Path,
    *,
    trigger_entrypoint: str,
    argv: list[str],
    input_scale: dict[str, int],
) -> None:
    append_event(
        run_dir,
        {
            "event": "run_started",
            "trigger_entrypoint": trigger_entrypoint,
            "input_scale": input_scale,
            "model_config": _model_config_summary(run_dir),
            "cli_command_summary": _sanitize_argv(argv),
        },
    )


def log_run_finished(run_dir: Path, *, status: str, duration_ms: int) -> None:
    append_event(run_dir, {"event": "run_finished", "status": status, "duration_ms": duration_ms})


def log_input_resolved(
    run_dir: Path,
    *,
    cli_cv_sources: int,
    cli_jd_sources: int,
    resolved_cv_files: int,
    resolved_jd_files: int,
    jd_text_blocks: int,
) -> None:
    append_event(
        run_dir,
        {
            "event": "input_resolved",
            "stage": "ingest",
            "cli_cv_sources": cli_cv_sources,
            "cli_jd_sources": cli_jd_sources,
            "resolved_cv_files": resolved_cv_files,
            "resolved_jd_files": resolved_jd_files,
            "jd_text_blocks": jd_text_blocks,
        },
    )


def log_input_extracted(
    run_dir: Path,
    *,
    role: str,
    provider: str,
    status: str,
    text_chars: int,
    fallback_from: str | None = None,
    warning: str | None = None,
) -> None:
    append_event(
        run_dir,
        {
            "event": "input_extracted",
            "stage": "ingest",
            "role": role,
            "provider": provider,
            "status": status,
            "text_chars": text_chars,
            "fallback_from": fallback_from,
            "warning": warning,
        },
    )
    log_tool_call_finished(
        run_dir,
        stage="ingest",
        tool=provider or "input_extraction",
        input_type=role,
        duration_ms=None,
        status=status,
        output_summary={"text_chars": text_chars, "warning": warning},
    )


def log_model_resolved(
    run_dir: Path,
    *,
    stage: StageName,
    role: str,
    provider: str,
    configured_model: str,
    resolved_model: str,
    base_url: str | None = None,
) -> None:
    append_event(
        run_dir,
        {
            "event": "model_resolved",
            "stage": stage,
            "role": role,
            "provider": provider,
            "configured_model": configured_model,
            "resolved_model": resolved_model,
            "base_url_host": _base_url_host(base_url),
        },
    )


def log_llm_call_started(
    run_dir: Path,
    *,
    stage: StageName,
    operation: str,
    provider: str,
    model: str,
) -> float:
    append_event(
        run_dir,
        {
            "event": "llm_call_started",
            "stage": stage,
            "operation": operation,
            "provider": provider,
            "model": model,
        },
    )
    return perf_counter()


def log_llm_call_finished(
    run_dir: Path,
    *,
    stage: StageName,
    operation: str,
    provider: str,
    model: str,
    started: float,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
    output_parse_status: str,
) -> None:
    append_event(
        run_dir,
        {
            "event": "llm_call_finished",
            "stage": stage,
            "operation": operation,
            "provider": provider,
            "model": model,
            "duration_ms": _duration_ms(started),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "output_parse_status": output_parse_status,
        },
    )


def log_llm_call_failed(
    run_dir: Path,
    *,
    stage: StageName,
    operation: str,
    provider: str,
    model: str,
    started: float,
    error: Exception,
    fallback_used: bool,
) -> None:
    append_event(
        run_dir,
        {
            "event": "llm_call_failed",
            "stage": stage,
            "operation": operation,
            "provider": provider,
            "model": model,
            "duration_ms": _duration_ms(started),
            "error_type": error.__class__.__name__,
            "error_summary": (str(error).strip() or error.__class__.__name__)[:500],
            "fallback_used": fallback_used,
        },
    )


def log_tool_call_finished(
    run_dir: Path,
    *,
    stage: StageName,
    tool: str,
    input_type: str,
    duration_ms: int | None,
    status: str,
    output_summary: dict[str, Any],
) -> None:
    append_event(
        run_dir,
        {
            "event": "tool_call_finished",
            "stage": stage,
            "tool": tool,
            "input_type": input_type,
            "duration_ms": duration_ms,
            "status": status,
            "output_summary": output_summary,
        },
    )


def log_fallback_used(
    run_dir: Path,
    *,
    stage: StageName,
    operation: str,
    from_provider: str,
    to_provider: str,
    reason: str,
) -> None:
    append_event(
        run_dir,
        {
            "event": "fallback_used",
            "stage": stage,
            "operation": operation,
            "from_provider": from_provider,
            "to_provider": to_provider,
            "reason": reason[:500],
        },
    )


def log_quality_gate_checked(
    run_dir: Path,
    *,
    stage: StageName,
    gate: str,
    status: str,
    checks: dict[str, Any],
    action: str,
) -> None:
    append_event(
        run_dir,
        {
            "event": "quality_gate_checked",
            "stage": stage,
            "gate": gate,
            "status": status,
            "checks": checks,
            "action": action,
        },
    )


def log_agent_reasoning_summary(
    run_dir: Path,
    *,
    stage: StageName,
    agent: str,
    summary: str,
    decision_inputs: list[str],
) -> None:
    append_event(
        run_dir,
        {
            "event": "agent_reasoning_summary",
            "stage": stage,
            "agent": agent,
            "summary": summary[:500],
            "decision_inputs": decision_inputs[:12],
        },
    )


def log_stage_started(run_dir: Path, stage: StageName) -> float:
    append_event(run_dir, {"event": "stage_started", "stage": stage})
    return perf_counter()


def log_stage_finished(run_dir: Path, stage: StageName, started: float) -> None:
    append_event(run_dir, {"event": "stage_finished", "stage": stage, "duration_ms": _duration_ms(started)})


def log_stage_failed(run_dir: Path, stage: StageName, started: float, error: Exception) -> None:
    summary = str(error).strip() or error.__class__.__name__
    append_event(
        run_dir,
        {
            "event": "stage_failed",
            "stage": stage,
            "duration_ms": _duration_ms(started),
            "error_code": error.__class__.__name__,
            "error_summary": summary[:500],
        },
    )


def _duration_ms(started: float) -> int:
    return int((perf_counter() - started) * 1000)


def _base_url_host(base_url: str | None) -> str | None:
    if not base_url:
        return None
    parsed = urlparse(base_url)
    return parsed.netloc or parsed.path or None


def _model_config_summary(run_dir: Path) -> dict[str, dict[str, str]]:
    try:
        config = load_run_config(run_dir)
    except Exception:
        config = default_run_config()
    return {
        "analyzer": {"provider": config.analyzer.provider, "model": config.analyzer.model},
        "generator": {"provider": config.generator.provider, "model": config.generator.model},
        "judge": {"provider": config.judge.provider, "model": config.judge.model},
        "planner": {"provider": config.planner.provider, "model": config.planner.model},
    }


def _sanitize_argv(argv: list[str]) -> list[str]:
    sanitized: list[str] = []
    hide_next = False
    for item in argv:
        if hide_next:
            sanitized.append("<value>")
            hide_next = False
            continue
        sanitized.append(item)
        if item in {"--candidate-id", "--ocr-languages"}:
            hide_next = True
    return sanitized
