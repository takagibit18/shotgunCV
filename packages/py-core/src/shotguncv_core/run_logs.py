from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

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
