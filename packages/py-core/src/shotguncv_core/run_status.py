from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree
from typing import Any, Literal

from shotguncv_core.storage import dump_json, load_json


StageName = Literal["ingest", "analyze", "generate", "evaluate", "plan", "report"]
RunState = Literal["draft", "queued", "running", "done", "failed"]
RunAction = Literal["run", "retry_full", "resume_failed", "draft_update", "delete"]


STAGES: tuple[StageName, ...] = ("ingest", "analyze", "generate", "evaluate", "plan", "report")
RUN_STATUS_PATH = Path("run_status.json")
REQUIRED_STAGE_FILES: dict[StageName, tuple[str, ...]] = {
    "ingest": ("ingest/manifest.json",),
    "analyze": ("analyze/candidate_profile.json", "analyze/jd_profiles.json"),
    "generate": ("generate/resume_variants.json",),
    "evaluate": ("evaluate/scorecards.json", "evaluate/gap_maps.json", "evaluate/eval_summary.json"),
    "plan": ("plan/application_strategies.json",),
    "report": ("report/summary.md",),
}


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_run_status(
    status: RunState,
    *,
    current_stage: StageName | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    error_stage: StageName | None = None,
    error_summary: str | None = None,
    last_action: RunAction = "run",
) -> dict[str, Any]:
    return {
        "status": status,
        "current_stage": current_stage,
        "started_at": started_at,
        "finished_at": finished_at,
        "error_stage": error_stage,
        "error_summary": error_summary,
        "last_action": last_action,
    }


def read_run_status(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / RUN_STATUS_PATH
    if not path.exists():
        return None
    payload = load_json(path)
    return payload if isinstance(payload, dict) else None


def write_run_status(run_dir: Path, payload: dict[str, Any]) -> Path:
    return dump_json(run_dir / RUN_STATUS_PATH, payload)


def mark_queued(run_dir: Path, *, action: RunAction) -> dict[str, Any]:
    status = build_run_status(
        "queued",
        current_stage=None,
        started_at=now_iso(),
        finished_at=None,
        last_action=action,
    )
    write_run_status(run_dir, status)
    return status


def mark_running(run_dir: Path, stage: StageName, *, started_at: str, action: RunAction) -> dict[str, Any]:
    status = build_run_status(
        "running",
        current_stage=stage,
        started_at=started_at,
        finished_at=None,
        last_action=action,
    )
    write_run_status(run_dir, status)
    return status


def mark_done(run_dir: Path, stage: StageName, *, started_at: str, action: RunAction) -> dict[str, Any]:
    status = build_run_status(
        "done",
        current_stage=stage,
        started_at=started_at,
        finished_at=now_iso(),
        last_action=action,
    )
    write_run_status(run_dir, status)
    return status


def mark_failed(
    run_dir: Path,
    stage: StageName,
    error: Exception,
    *,
    started_at: str,
    action: RunAction,
) -> dict[str, Any]:
    summary = str(error).strip() or error.__class__.__name__
    status = build_run_status(
        "failed",
        current_stage=stage,
        started_at=started_at,
        finished_at=now_iso(),
        error_stage=stage,
        error_summary=summary[:500],
        last_action=action,
    )
    write_run_status(run_dir, status)
    return status


def get_completed_stages(run_dir: Path) -> list[StageName]:
    completed: list[StageName] = []
    for stage in STAGES:
        if stage_is_complete(run_dir, stage):
            completed.append(stage)
    return completed


def stage_is_complete(run_dir: Path, stage: StageName) -> bool:
    return all((run_dir / relative_path).exists() for relative_path in REQUIRED_STAGE_FILES[stage])


def first_incomplete_stage(run_dir: Path) -> StageName:
    for stage in STAGES:
        if not stage_is_complete(run_dir, stage):
            return stage
    return "report"


def stages_from(stage: StageName) -> tuple[StageName, ...]:
    start = STAGES.index(stage)
    return STAGES[start:]


def cleanup_stages_from(run_dir: Path, stage: StageName) -> None:
    for stage_name in stages_from(stage):
        stage_path = run_dir / stage_name
        if stage_path.exists():
            rmtree(stage_path)
