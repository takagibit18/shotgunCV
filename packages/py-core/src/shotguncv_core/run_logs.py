from __future__ import annotations

from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Any, Literal, TypedDict
from urllib.parse import urlparse

from shotguncv_core.run_config import default_run_config, load_run_config
from shotguncv_core.run_status import StageName, now_iso
from shotguncv_core.storage import ensure_directory, to_plain_data


LOG_PATH = Path("logs") / "run_events.jsonl"
LogStageName = StageName | Literal["index", "retrieve", "review", "interview"]
_LOG_WRITE_LOCK = Lock()


class GraphNodeTimer(TypedDict):
    started: float
    start_log_write_ms: int


def append_event(run_dir: Path, event: dict[str, Any]) -> Path:
    path = run_dir / LOG_PATH
    ensure_directory(path.parent)
    import json

    payload = {"timestamp": now_iso(), **event}
    line = json.dumps(to_plain_data(payload), ensure_ascii=False, separators=(",", ":")) + "\n"
    with _LOG_WRITE_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
    return path


def _append_event_with_duration(run_dir: Path, event: dict[str, Any]) -> tuple[Path, int]:
    started = perf_counter()
    path = append_event(run_dir, event)
    return path, _duration_ms(started)


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
    stage: LogStageName,
    operation: str,
    provider: str,
    model: str,
    prompt_tokens: int | None = None,
    max_completion_tokens: int | None = None,
) -> float:
    append_event(
        run_dir,
        {
            "event": "llm_call_started",
            "stage": stage,
            "operation": operation,
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "max_completion_tokens": max_completion_tokens,
        },
    )
    return perf_counter()


def log_llm_call_finished(
    run_dir: Path,
    *,
    stage: LogStageName,
    operation: str,
    provider: str,
    model: str,
    started: float,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
    output_parse_status: str,
    max_completion_tokens: int | None = None,
    status: str = "ok",
    fallback_used: bool = False,
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
            "status": status,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "max_completion_tokens": max_completion_tokens,
            "output_parse_status": output_parse_status,
            "fallback_used": fallback_used,
        },
    )


def log_llm_call_failed(
    run_dir: Path,
    *,
    stage: LogStageName,
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


def log_interview_question_modified(
    run_dir: Path,
    *,
    session_id: str,
    question_id: str,
    jd_id: str,
) -> None:
    _log_interview_event(
        run_dir,
        event="interview_question_modified",
        session_id=session_id,
        question_id=question_id,
        jd_id=jd_id,
    )


def log_interview_question_deleted(
    run_dir: Path,
    *,
    session_id: str,
    question_id: str,
    jd_id: str,
) -> None:
    _log_interview_event(
        run_dir,
        event="interview_question_deleted",
        session_id=session_id,
        question_id=question_id,
        jd_id=jd_id,
    )


def log_interview_answer_submitted(
    run_dir: Path,
    *,
    session_id: str,
    question_id: str,
    jd_id: str,
    answer_chars: int,
) -> None:
    _log_interview_event(
        run_dir,
        event="interview_answer_submitted",
        session_id=session_id,
        question_id=question_id,
        jd_id=jd_id,
        answer_chars=answer_chars,
    )


def log_interview_evaluation_generated(
    run_dir: Path,
    *,
    session_id: str,
    question_id: str,
    jd_id: str,
    score: float,
) -> None:
    _log_interview_event(
        run_dir,
        event="interview_evaluation_generated",
        session_id=session_id,
        question_id=question_id,
        jd_id=jd_id,
        score=score,
    )


def _log_interview_event(run_dir: Path, *, event: str, **payload: Any) -> None:
    append_event(run_dir, {"event": event, "stage": "interview", **payload})


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


def log_graph_node_started(
    run_dir: Path,
    *,
    graph: str,
    graph_runtime: str,
    node: str,
    run_id: str,
    jd_count: int,
    input_summary: dict[str, Any],
    jd_id: str | None = None,
) -> GraphNodeTimer:
    _, log_write_ms = _append_event_with_duration(
        run_dir,
        {
            "event": "graph_node_started",
            "stage": "review",
            "graph": graph,
            "graph_runtime": graph_runtime,
            "node": node,
            "run_id": run_id,
            "jd_id": jd_id,
            "jd_count": jd_count,
            "input_summary": input_summary,
        },
    )
    return {"started": perf_counter(), "start_log_write_ms": log_write_ms}


def log_graph_node_finished(
    run_dir: Path,
    *,
    graph: str,
    graph_runtime: str,
    node: str,
    run_id: str,
    jd_count: int,
    started: float | GraphNodeTimer,
    status: str,
    input_summary: dict[str, Any],
    output_summary: dict[str, Any],
    jd_id: str | None = None,
) -> None:
    started_at = started["started"] if isinstance(started, dict) else started
    business_duration_ms = _duration_ms(started_at)
    start_log_write_ms = started.get("start_log_write_ms") if isinstance(started, dict) else None
    append_event(
        run_dir,
        {
            "event": "graph_node_finished",
            "stage": "review",
            "graph": graph,
            "graph_runtime": graph_runtime,
            "node": node,
            "run_id": run_id,
            "jd_id": jd_id,
            "jd_count": jd_count,
            "duration_ms": business_duration_ms,
            "timing_ms": {
                "total": business_duration_ms,
                "business": business_duration_ms,
                "log_write": start_log_write_ms,
            },
            "status": status,
            "input_summary": input_summary,
            "output_summary": output_summary,
        },
    )


def _score_distribution(results: list[dict[str, Any]]) -> dict[str, float] | None:
    scores = [float(r.get("score") or 0.0) for r in results]
    if not scores:
        return None
    sorted_scores = sorted(scores)
    n = len(sorted_scores)
    if n % 2 == 1:
        median = sorted_scores[n // 2]
    else:
        median = (sorted_scores[n // 2 - 1] + sorted_scores[n // 2]) / 2.0
    return {
        "min": round(min(scores), 4),
        "max": round(max(scores), 4),
        "mean": round(sum(scores) / n, 4),
        "median": round(median, 4),
    }


def _hit_source_refs(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for r in results:
        meta = r.get("metadata") or {}
        refs.append({
            "source_type": meta.get("source_type"),
            "source_id": meta.get("source_id"),
            "score": round(float(r.get("score") or 0.0), 4),
        })
    return refs


def _source_type_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in results:
        st = (r.get("metadata") or {}).get("source_type") or "unknown"
        counts[st] = counts.get(st, 0) + 1
    return counts


def log_retrieval_query(
    run_dir: Path,
    *,
    stage: LogStageName,
    retrieval_scope: str,
    query: str,
    retriever_type: str,
    filters: dict[str, Any],
    limit: int,
    hit_count: int,
    started: float,
    results: list[dict[str, Any]] | None = None,
    supporting_count: int | None = None,
    source_type_available_counts: dict[str, int] | None = None,
    raw_hit_count: int | None = None,
    unique_hit_count: int | None = None,
) -> None:
    payload: dict[str, Any] = {
        "event": "retrieval_query",
        "stage": stage,
        "retrieval_scope": retrieval_scope,
        "query_preview": query[:160],
        "query_chars": len(query),
        "retriever_type": retriever_type,
        "filters": filters,
        "limit": limit,
        "hit_count": hit_count,
        "raw_hit_count": raw_hit_count if raw_hit_count is not None else hit_count,
        "unique_hit_count": unique_hit_count if unique_hit_count is not None else hit_count,
        "miss": hit_count == 0,
        "duration_ms": _duration_ms(started),
        "score_distribution": _score_distribution(results) if results else None,
        "hit_source_refs": _hit_source_refs(results) if results else None,
        "source_type_hit_counts": _source_type_counts(results) if results else None,
        "source_type_available_counts": source_type_available_counts or {},
        "supporting_hit_count": supporting_count,
        "precision": None,
    }
    append_event(run_dir, payload)


def log_index_batch(
    run_dir: Path,
    *,
    run_id: str,
    artifact_count: int,
    chunk_count: int,
    started: float,
    skip_chunks: bool,
) -> None:
    append_event(
        run_dir,
        {
            "event": "index_batch",
            "stage": "index",
            "run_id": run_id,
            "artifact_count": artifact_count,
            "chunk_count": chunk_count,
            "duration_ms": _duration_ms(started),
            "skip_chunks": skip_chunks,
        },
    )


def log_stage_started(run_dir: Path, stage: LogStageName) -> float:
    append_event(run_dir, {"event": "stage_started", "stage": stage})
    return perf_counter()


def log_stage_finished(run_dir: Path, stage: LogStageName, started: float) -> None:
    append_event(run_dir, {"event": "stage_finished", "stage": stage, "duration_ms": _duration_ms(started)})


def log_stage_failed(run_dir: Path, stage: LogStageName, started: float, error: Exception) -> None:
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
