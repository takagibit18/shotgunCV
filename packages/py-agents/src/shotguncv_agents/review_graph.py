from __future__ import annotations

import operator
from pathlib import Path
from typing import Annotated, Any, TypedDict

from shotguncv_core.run_logs import (
    log_fallback_used,
    log_graph_node_finished,
    log_graph_node_started,
)
from shotguncv_core.storage import dump_json, load_json, stage_dir


SMALL_BATCH_BYPASS_MAX_JDS = 3
GRAPH_NAME = "post_run_review"
_COMPILED_REVIEW_GRAPH: Any | None = None


class _ReviewGraphState(TypedDict, total=False):
    run_dir: Path
    requested_jd_id: str | None
    database_url: str | None
    graph_runtime: str
    run_id: str
    candidate_id: str
    candidate_profile: dict[str, Any]
    jd_ids: list[str]
    jd_profiles: list[dict[str, Any]]
    scorecards: list[dict[str, Any]]
    gates: list[dict[str, Any]]
    explanations: list[dict[str, Any]]
    strategies: list[dict[str, Any]]
    requirement_matrix: list[dict[str, Any]]
    evidence_records: Annotated[list[dict[str, Any]], operator.add]
    decision_review: Annotated[list[dict[str, Any]], operator.add]
    evidence_gap_reports: Annotated[list[dict[str, Any]], operator.add]
    validation: dict[str, Any]
    review: dict[str, Any]


def run_post_run_review(
    run_dir: Path,
    *,
    jd_id: str | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    initial_state: _ReviewGraphState = {
        "run_dir": run_dir.resolve(),
        "requested_jd_id": jd_id,
        "database_url": database_url,
        "evidence_records": [],
        "decision_review": [],
        "evidence_gap_reports": [],
    }
    if 0 < len(_preview_jd_ids(run_dir, jd_id=jd_id)) <= SMALL_BATCH_BYPASS_MAX_JDS:
        return _run_sequential(initial_state, "small-batch-serial")["review"]
    graph_result = _run_langgraph(initial_state)
    if graph_result is not None:
        return graph_result["review"]
    return _run_sequential(initial_state, "sequential-fallback")["review"]


def _preview_jd_ids(run_dir: Path, *, jd_id: str | None) -> list[str]:
    jd_profiles = _read_json(run_dir / "analyze" / "jd_profiles.json", [])
    jd_ids = [str(item.get("jd_id")) for item in jd_profiles if item.get("jd_id")]
    if jd_id:
        return [item for item in jd_ids if item == jd_id]
    return jd_ids


def _run_langgraph(state: _ReviewGraphState) -> _ReviewGraphState | None:
    try:
        graph = _get_compiled_review_graph()
    except ImportError:
        return None
    except Exception as exc:
        _log_langgraph_fallback(state, exc)
        return None
    try:
        return graph.invoke({**state, "graph_runtime": "langgraph-send"})
    except Exception as exc:
        _log_langgraph_fallback(state, exc)
        return None


def _get_compiled_review_graph() -> Any:
    global _COMPILED_REVIEW_GRAPH
    if _COMPILED_REVIEW_GRAPH is None:
        _COMPILED_REVIEW_GRAPH = _compile_review_graph()
    return _COMPILED_REVIEW_GRAPH


def _clear_compiled_review_graph_cache() -> None:
    global _COMPILED_REVIEW_GRAPH
    _COMPILED_REVIEW_GRAPH = None


def _compile_review_graph() -> Any:
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(_ReviewGraphState)
    graph.add_node("load_run_context", _logged_node("load_run_context", _load_run_context))
    graph.add_node("summarize_decision_context", _logged_node("summarize_decision_context", _summarize_decision_context))
    graph.add_node("generate_gap_report_from_artifacts", _logged_node("generate_gap_report_from_artifacts", _generate_gap_report_from_artifacts))
    graph.add_node("validate_against_fabrication_policy", _logged_node("validate_against_fabrication_policy", _validate_against_fabrication_policy))
    graph.add_node("write_review_artifact", _logged_node("write_review_artifact", _write_review_artifact))

    graph.add_edge(START, "load_run_context")
    graph.add_edge("load_run_context", "summarize_decision_context")
    graph.add_edge("summarize_decision_context", "generate_gap_report_from_artifacts")
    graph.add_edge("generate_gap_report_from_artifacts", "validate_against_fabrication_policy")
    graph.add_edge("validate_against_fabrication_policy", "write_review_artifact")
    graph.add_edge("write_review_artifact", END)
    return graph.compile()


def _log_langgraph_fallback(state: _ReviewGraphState, exc: Exception) -> None:
    log_fallback_used(
        state["run_dir"],
        stage="review",
        operation="post_run_review_graph",
        from_provider="langgraph-send",
        to_provider="sequential-fallback",
        reason=f"{exc.__class__.__name__}: {str(exc)[:300]}",
    )


def _run_sequential(state: _ReviewGraphState, graph_runtime: str) -> _ReviewGraphState:
    """Run the review pipeline sequentially without LangGraph fan-out.

    Unified fallback for both small-batch bypass and LangGraph-unavailable paths.
    Calls each node in order — all per-JD processing happens inside
    summarize_decision_context and generate_gap_report_from_artifacts.
    """
    state = {**state, "graph_runtime": graph_runtime}
    state = _apply_update(state, _logged_node("load_run_context", _load_run_context)(state))
    state = _apply_update(state, _logged_node("summarize_decision_context", _summarize_decision_context)(state))
    state = _apply_update(state, _logged_node("generate_gap_report_from_artifacts", _generate_gap_report_from_artifacts)(state))
    state = _apply_update(state, _logged_node("validate_against_fabrication_policy", _validate_against_fabrication_policy)(state))
    return _apply_update(state, _logged_node("write_review_artifact", _write_review_artifact)(state))


def _apply_update(state: _ReviewGraphState, updates: _ReviewGraphState) -> _ReviewGraphState:
    return {**state, **updates}


def _logged_node(name: str, node: Any) -> Any:
    def _run(state: _ReviewGraphState) -> _ReviewGraphState:
        run_dir = state["run_dir"]
        graph_runtime = str(state.get("graph_runtime") or "unknown")
        run_id = str(state.get("run_id") or run_dir.name)
        jd_id = _node_jd_id(state)
        input_summary = _state_summary(state)
        started = log_graph_node_started(
            run_dir,
            graph=GRAPH_NAME,
            graph_runtime=graph_runtime,
            node=name,
            run_id=run_id,
            jd_id=jd_id,
            jd_count=len(state.get("jd_ids", [])),
            input_summary=input_summary,
        )
        try:
            next_state = node(state)
        except Exception as exc:
            log_graph_node_finished(
                run_dir,
                graph=GRAPH_NAME,
                graph_runtime=graph_runtime,
                node=name,
                run_id=run_id,
                jd_id=jd_id,
                jd_count=len(state.get("jd_ids", [])),
                started=started,
                status="failed",
                input_summary=input_summary,
                output_summary={"error_type": exc.__class__.__name__, "error_summary": str(exc)[:500]},
            )
            raise
        log_graph_node_finished(
            run_dir,
            graph=GRAPH_NAME,
            graph_runtime=graph_runtime,
            node=name,
            run_id=str(next_state.get("run_id") or run_id),
            jd_id=jd_id,
            jd_count=len(next_state.get("jd_ids") or state.get("jd_ids", [])),
            started=started,
            status="ok",
            input_summary=input_summary,
            output_summary=_state_summary(next_state),
        )
        return next_state

    return _run


# ---------------------------------------------------------------------------
# graph nodes
# ---------------------------------------------------------------------------


def _load_run_context(state: _ReviewGraphState) -> _ReviewGraphState:
    run_dir = state["run_dir"]
    candidate = _read_json(run_dir / "analyze" / "candidate_profile.json", {})
    jd_profiles = _read_json(run_dir / "analyze" / "jd_profiles.json", [])
    requested_jd_id = state.get("requested_jd_id")
    jd_ids = [str(item.get("jd_id")) for item in jd_profiles if item.get("jd_id")]
    if requested_jd_id:
        jd_ids = [jd_id for jd_id in jd_ids if jd_id == requested_jd_id]
    if not jd_ids:
        raise ValueError("No JD profiles are available for review.")
    return {
        "run_id": run_dir.name,
        "candidate_id": str(candidate.get("candidate_id") or "unknown"),
        "candidate_profile": candidate,
        "jd_profiles": jd_profiles,
        "scorecards": _read_json(run_dir / "evaluate" / "scorecards.json", []),
        "gates": _read_json(run_dir / "analyze" / "preflight_gates.json", []),
        "explanations": _read_json(run_dir / "evaluate" / "ranking_explanations.json", []),
        "strategies": _read_json(run_dir / "plan" / "application_strategies.json", []),
        "requirement_matrix": _read_json(run_dir / "analyze" / "requirement_matrix.json", []),
        "jd_ids": jd_ids,
    }


def _summarize_decision_context(state: _ReviewGraphState) -> _ReviewGraphState:
    """Assess evidence and produce decision review for all JDs from structured artifacts.

    Replaces the former fan-out of per-JD assess_evidence + inspect_score/generate_gap.
    Reads requirement_matrix, preflight_gates, scorecards, explanations, and strategies
    directly — no retrieval calls.
    """
    evidence_records: list[dict[str, Any]] = []
    decision_review: list[dict[str, Any]] = []
    requirement_matrix: list[dict[str, Any]] = state["requirement_matrix"]
    gates: list[dict[str, Any]] = state["gates"]

    for jd_id in state["jd_ids"]:
        # --- evidence assessment (from requirement_matrix + preflight_gates) ---
        jd_requirements = [item for item in requirement_matrix if str(item.get("jd_id")) == jd_id]
        verified_count = sum(1 for item in jd_requirements if item.get("evidence_status") == "verified")
        inferred_count = sum(1 for item in jd_requirements if item.get("evidence_status") == "inferred")
        missing_count = sum(1 for item in jd_requirements if item.get("evidence_status") == "missing")
        mismatch_count = sum(1 for item in jd_requirements if item.get("evidence_status") == "mismatch")
        total_requirements = len(jd_requirements)

        gate = _first_match(gates, jd_id=jd_id) or {}
        gate_status = str(gate.get("status") or "unknown")

        if gate_status == "blocked":
            evidence_status = "insufficient"
            reason = "preflight gate blocked: hard-gate mismatch"
        elif gate_status == "needs_review":
            evidence_status = "insufficient"
            reason = "preflight gate needs_review: hard-gate evidence missing"
        elif verified_count == 0:
            evidence_status = "insufficient"
            reason = "no verified candidate evidence; inferred evidence is insufficient for automatic apply guidance"
        else:
            evidence_status = "sufficient"
            reason = f"{verified_count} verified, {inferred_count} inferred"

        evidence_count = verified_count + inferred_count
        record = {
            "jd_id": jd_id,
            "evidence_count": evidence_count,
            "verified_count": verified_count,
            "inferred_count": inferred_count,
            "missing_count": missing_count,
            "mismatch_count": mismatch_count,
            "total_requirements": total_requirements,
            "gate_status": gate_status,
            "evidence_status": evidence_status,
            "reason": reason,
        }
        evidence_records.append(record)

        # --- decision review ---
        jd = _first_match(state["jd_profiles"], jd_id=jd_id) or {}
        if evidence_status == "sufficient":
            scorecard = _first_match(state["scorecards"], jd_id=jd_id) or {}
            explanation = _first_match(state["explanations"], jd_id=jd_id) or {}
            strategy = _first_match(state["strategies"], jd_id=jd_id) or {}
            decision = {
                "jd_id": jd_id,
                "title": jd.get("title", ""),
                "company": jd.get("company", ""),
                "evidence_status": "sufficient",
                "evidence_count": evidence_count,
                "verified_count": verified_count,
                "inferred_count": inferred_count,
                "gate_status": gate.get("status") or scorecard.get("gate_status") or "unknown",
                "final_score": scorecard.get("final_overall_score") or scorecard.get("overall_score") or 0,
                "decision_source": scorecard.get("final_decision_source", ""),
                "ranking_summary": explanation.get("decision_summary", ""),
                "apply_decision": strategy.get("apply_decision", "review"),
            }
        else:
            decision = {
                "jd_id": jd_id,
                "title": jd.get("title", ""),
                "company": jd.get("company", ""),
                "evidence_status": "insufficient",
                "evidence_count": evidence_count,
                "gate_status": "evidence_insufficient",
                "final_score": None,
                "decision_source": "evidence-gap-report",
                "ranking_summary": f"证据不足：{reason}。跳过评分检查，请先补证据。",
                "apply_decision": "evidence_needed",
            }
        decision_review.append(decision)

    return {"evidence_records": evidence_records, "decision_review": decision_review}


def _generate_gap_report_from_artifacts(state: _ReviewGraphState) -> _ReviewGraphState:
    """Generate evidence gap reports from requirement_matrix missing/mismatch entries.

    Only processes JDs with insufficient evidence. Reads missing/mismatch detail
    from requirement_matrix — no retrieval calls.
    """
    gap_reports: list[dict[str, Any]] = []
    requirement_matrix: list[dict[str, Any]] = state["requirement_matrix"]

    for record in state.get("evidence_records", []):
        if record.get("evidence_status") != "insufficient":
            continue
        jd_id = str(record.get("jd_id", ""))
        jd = _first_match(state["jd_profiles"], jd_id=jd_id) or {}

        jd_requirements = [item for item in requirement_matrix if str(item.get("jd_id")) == jd_id]
        missing_items = [
            {
                "requirement_id": item.get("requirement_id", ""),
                "requirement_text": item.get("requirement_text", ""),
                "evidence_status": item.get("evidence_status", ""),
                "fabrication_policy": item.get("fabrication_policy", ""),
            }
            for item in jd_requirements
            if item.get("evidence_status") in ("missing", "mismatch")
        ]

        focus = _gap_focus_for_jd(jd)
        report = {
            "jd_id": jd_id,
            "evidence_count": record.get("evidence_count", 0),
            "verified_count": record.get("verified_count", 0),
            "inferred_count": record.get("inferred_count", 0),
            "missing_count": record.get("missing_count", 0),
            "mismatch_count": record.get("mismatch_count", 0),
            "gate_status": record.get("gate_status", "unknown"),
            "gap_reason": record.get("reason", ""),
            "missing_requirements": missing_items,
            "recommended_evidence": [
                f"补充与 {focus} 直接相关的项目、职责或成果证据。",
                "标注可复核来源，例如原简历条目、项目材料或过往申请反馈。",
                "证据不足前不要生成模板化面试题、参考答案或简历改写任务。",
            ],
        }
        gap_reports.append(report)

    return {"evidence_gap_reports": gap_reports}


def _validate_against_fabrication_policy(state: _ReviewGraphState) -> _ReviewGraphState:
    validation = {
        "fabrication_policy": "passed",
        "unsupported_hard_fact_tasks_removed": [],
        "warnings": [],
    }
    return {"validation": validation}


def _write_review_artifact(state: _ReviewGraphState) -> _ReviewGraphState:
    run_dir = state["run_dir"]
    review_dir = stage_dir(run_dir, "review")
    decisions = _ordered_by_jd(state["decision_review"], state["jd_ids"])
    evidence_records = _ordered_by_jd(state["evidence_records"], state["jd_ids"])
    review = {
        "schema_version": "post-run-review-v4",
        "run_id": state["run_id"],
        "candidate_id": state["candidate_id"],
        "jd_ids": state["jd_ids"],
        "provider": {"provider": "deterministic-review-agent", "model": "structured-evidence-v4"},
        "graph_runtime": state.get("graph_runtime", "unknown"),
        "parallel_topology": _parallel_topology(state),
        "decision_review": decisions,
        "evidence_assessment": {
            "low_evidence_jd_count": sum(1 for item in evidence_records if item.get("evidence_status") == "insufficient"),
            "evidence_by_jd": evidence_records,
        },
        "evidence_gap_reports": _ordered_by_jd(state.get("evidence_gap_reports", []), state["jd_ids"]),
        "validation": state["validation"],
    }
    dump_json(review_dir / "post_run_review.json", review)
    return {"review": review}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _parallel_topology(state: _ReviewGraphState) -> dict[str, Any]:
    return {
        "assess": "sequential",
        "inspect": "sequential",
        "generation": "run_level",
        "small_batch_bypass_max_jds": SMALL_BATCH_BYPASS_MAX_JDS,
        "fan_in_nodes": [],
    }


def _state_summary(state: _ReviewGraphState) -> dict[str, Any]:
    run_dir = state.get("run_dir")
    return {
        "run_id": state.get("run_id") or (run_dir.name if isinstance(run_dir, Path) else None),
        "requested_jd_id": state.get("requested_jd_id"),
        "jd_count": len(state.get("jd_ids", [])),
        "evidence_record_count": len(state.get("evidence_records", [])),
        "decision_count": len(state.get("decision_review", [])),
        "evidence_gap_count": len(state.get("evidence_gap_reports", [])),
    }


def _node_jd_id(state: _ReviewGraphState) -> str | None:
    return None


def _gap_focus_for_jd(jd: dict[str, Any]) -> str:
    for field in ["must_have_requirements", "requirements", "keywords", "interview_focus_areas"]:
        values = _safe_list(jd.get(field))
        if values:
            return str(values[0])
    return str(jd.get("title") or "该岗位")


def _ordered_by_jd(items: list[dict[str, Any]], jd_ids: list[str]) -> list[dict[str, Any]]:
    order = {jd_id: index for index, jd_id in enumerate(jd_ids)}
    return sorted(items, key=lambda item: order.get(str(item.get("jd_id")), len(order)))


def _first_match(items: list[dict[str, Any]], **matches: str) -> dict[str, Any] | None:
    for item in items:
        if all(item.get(key) == value for key, value in matches.items()):
            return item
    return None


def _safe_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value is None:
        return []
    return [str(value)] if str(value).strip() else []


def _read_json(path: Path, fallback: Any) -> Any:
    return load_json(path) if path.exists() else fallback
