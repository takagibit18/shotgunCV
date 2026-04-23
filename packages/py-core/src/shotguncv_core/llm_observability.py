from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from shotguncv_core.models import LLMCallRecord, LLMRunSummary, LLMStageSummary
from shotguncv_core.storage import dump_json, ensure_directory, to_plain_data

_APPEND_LOCK = Lock()


def stage_logs_dir(run_dir: Path) -> Path:
    return ensure_directory(run_dir / "logs")


def append_llm_call(run_dir: Path, record: LLMCallRecord) -> Path:
    path = stage_logs_dir(run_dir) / "llm_calls.jsonl"
    line = json.dumps(to_plain_data(record), ensure_ascii=False)
    with _APPEND_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")
    return path


def build_llm_summary(run_dir: Path) -> LLMRunSummary:
    calls_path = stage_logs_dir(run_dir) / "llm_calls.jsonl"
    summary = LLMRunSummary()
    if calls_path.exists():
        for raw_line in calls_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            stage = str(payload.get("stage", "")).strip() or "unknown"
            stage_summary = summary.by_stage.setdefault(stage, LLMStageSummary())
            _accumulate(stage_summary, payload)
            _accumulate(summary.totals, payload)
    dump_json(stage_logs_dir(run_dir) / "llm_summary.json", summary)
    return summary


def _accumulate(target: LLMStageSummary, payload: dict[str, object]) -> None:
    usage = payload.get("usage", {})
    target.call_count += 1
    if payload.get("status") == "success":
        target.success_count += 1
    else:
        target.failure_count += 1
    if isinstance(usage, dict):
        target.prompt_tokens += _safe_int(usage.get("prompt_tokens"))
        target.completion_tokens += _safe_int(usage.get("completion_tokens"))
        target.total_tokens += _safe_int(usage.get("total_tokens"))


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
