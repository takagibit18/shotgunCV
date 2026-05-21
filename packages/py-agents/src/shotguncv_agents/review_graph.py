from __future__ import annotations

import math
import operator
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from time import perf_counter
from typing import Annotated, Any, TypedDict

from shotguncv_core.rag.retrieval import PgVectorRetriever, RetrievalResult
from shotguncv_core.run_logs import (
    log_fallback_used,
    log_graph_node_finished,
    log_graph_node_started,
    log_retrieval_query,
)
from shotguncv_core.storage import dump_json, load_json, stage_dir


EVIDENCE_THRESHOLD = 3
GRAPH_NAME = "post_run_review"
REVIEW_SKIPPED_NODES = [
    "inspect_score_and_gates",
    "generate_interview_questions",
    "generate_reference_answers",
    "generate_revision_tasks",
]


class _ReviewGraphState(TypedDict, total=False):
    run_dir: Path
    requested_jd_id: str | None
    database_url: str | None
    evidence_threshold: int
    graph_runtime: str
    run_id: str
    candidate_id: str
    candidate_profile: dict[str, Any]
    jd_ids: list[str]
    jd_id: str
    jd_profiles: list[dict[str, Any]]
    scorecards: list[dict[str, Any]]
    gates: list[dict[str, Any]]
    explanations: list[dict[str, Any]]
    strategies: list[dict[str, Any]]
    requirement_matrix: list[dict[str, Any]]
    retrieval_chunks: list[dict[str, Any]]
    retrieval_results: Annotated[list[dict[str, Any]], operator.add]
    retrieval_misses: Annotated[list[str], operator.add]
    evidence_records: Annotated[list[dict[str, Any]], operator.add]
    evidence_record: dict[str, Any]
    decision_review: Annotated[list[dict[str, Any]], operator.add]
    evidence_gap_reports: Annotated[list[dict[str, Any]], operator.add]
    interview_questions: Annotated[list[dict[str, Any]], operator.add]
    reference_answers: Annotated[list[dict[str, Any]], operator.add]
    revision_tasks: Annotated[list[dict[str, Any]], operator.add]
    validation: dict[str, Any]
    review: dict[str, Any]


def run_post_run_review(
    run_dir: Path,
    *,
    jd_id: str | None = None,
    database_url: str | None = None,
    evidence_threshold: int = EVIDENCE_THRESHOLD,
) -> dict[str, Any]:
    initial_state: _ReviewGraphState = {
        "run_dir": run_dir.resolve(),
        "requested_jd_id": jd_id,
        "database_url": database_url,
        "evidence_threshold": evidence_threshold,
        "retrieval_results": [],
        "retrieval_misses": [],
        "evidence_records": [],
        "decision_review": [],
        "evidence_gap_reports": [],
    }
    graph_result = _run_langgraph(initial_state)
    if graph_result is not None:
        return graph_result["review"]
    return _run_threadpool_fallback(initial_state)["review"]


def _run_langgraph(state: _ReviewGraphState) -> _ReviewGraphState | None:
    try:
        from langgraph.graph import END, START, StateGraph
        from langgraph.types import Send
    except Exception:
        return None

    try:
        send_cls = Send
        graph = StateGraph(_ReviewGraphState)
        graph.add_node("load_run_context", _logged_node("load_run_context", _load_run_context))
        graph.add_node("retrieve_relevant_evidence", _logged_node("retrieve_relevant_evidence", _retrieve_relevant_evidence))
        graph.add_node("merge_retrieval_results", _logged_node("merge_retrieval_results", _merge_retrieval_results))
        graph.add_node("inspect_score_and_gates", _logged_node("inspect_score_and_gates", _inspect_score_and_gates))
        graph.add_node("generate_evidence_gap_report", _logged_node("generate_evidence_gap_report", _generate_evidence_gap_report))
        graph.add_node("merge_review_paths", _logged_node("merge_review_paths", _merge_review_paths))
        graph.add_node("generate_interview_questions", _logged_node("generate_interview_questions", _generate_interview_questions))
        graph.add_node("generate_reference_answers", _logged_node("generate_reference_answers", _generate_reference_answers))
        graph.add_node("generate_revision_tasks", _logged_node("generate_revision_tasks", _generate_revision_tasks))
        graph.add_node("validate_against_fabrication_policy", _logged_node("validate_against_fabrication_policy", _validate_against_fabrication_policy))
        graph.add_node("write_review_artifact", _logged_node("write_review_artifact", _write_review_artifact))

        def _send_retrieve_jobs(state: _ReviewGraphState) -> list[Any]:
            return [
                send_cls(
                    "retrieve_relevant_evidence",
                    {
                        **_shared_branch_context(state),
                        "jd_id": jd_id,
                    },
                )
                for jd_id in state["jd_ids"]
            ]

        def _send_review_path_jobs(state: _ReviewGraphState) -> list[Any]:
            records = _evidence_records_by_jd(state)
            jobs: list[Any] = []
            for jd_id in state["jd_ids"]:
                record = records[jd_id]
                node = "inspect_score_and_gates" if record["evidence_status"] == "sufficient" else "generate_evidence_gap_report"
                jobs.append(
                    send_cls(
                        node,
                        {
                            **_shared_branch_context(state),
                            "jd_id": jd_id,
                            "evidence_record": record,
                        },
                    )
                )
            return jobs

        def _route_after_review_paths(state: _ReviewGraphState) -> str:
            return "generate" if _sufficient_jd_ids(state) else "validate"

        graph.add_edge(START, "load_run_context")
        graph.add_conditional_edges("load_run_context", _send_retrieve_jobs, ["retrieve_relevant_evidence"])
        graph.add_edge("retrieve_relevant_evidence", "merge_retrieval_results")
        graph.add_conditional_edges(
            "merge_retrieval_results",
            _send_review_path_jobs,
            ["inspect_score_and_gates", "generate_evidence_gap_report"],
        )
        graph.add_edge("inspect_score_and_gates", "merge_review_paths")
        graph.add_edge("generate_evidence_gap_report", "merge_review_paths")
        graph.add_conditional_edges(
            "merge_review_paths",
            _route_after_review_paths,
            {"generate": "generate_interview_questions", "validate": "validate_against_fabrication_policy"},
        )
        graph.add_edge("generate_interview_questions", "generate_reference_answers")
        graph.add_edge("generate_reference_answers", "generate_revision_tasks")
        graph.add_edge("generate_revision_tasks", "validate_against_fabrication_policy")
        graph.add_edge("validate_against_fabrication_policy", "write_review_artifact")
        graph.add_edge("write_review_artifact", END)
        return graph.compile().invoke({**state, "graph_runtime": "langgraph-send"})
    except Exception as exc:
        run_dir = state["run_dir"]
        log_fallback_used(
            run_dir,
            stage="review",
            operation="post_run_review_graph",
            from_provider="langgraph-send",
            to_provider="threadpool-fallback",
            reason=f"{exc.__class__.__name__}: {str(exc)[:300]}",
        )
        return None


def _run_threadpool_fallback(state: _ReviewGraphState) -> _ReviewGraphState:
    state = _apply_update(state, _logged_node("load_run_context", _load_run_context)({**state, "graph_runtime": "threadpool-fallback"}))
    shared_context = _shared_branch_context(state)
    retrieval_states: list[_ReviewGraphState] = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(state["jd_ids"])))) as executor:
        futures = {
            executor.submit(
                _logged_node("retrieve_relevant_evidence", _retrieve_relevant_evidence),
                {**shared_context, "jd_id": jd_id},
            ): jd_id
            for jd_id in state["jd_ids"]
        }
        for future in as_completed(futures):
            retrieval_states.append(future.result())
    for item in retrieval_states:
        state["retrieval_results"].extend(item.get("retrieval_results", []))
        state["retrieval_misses"].extend(item.get("retrieval_misses", []))
        state["evidence_records"].extend(item.get("evidence_records", []))
    state = _apply_update(state, _logged_node("merge_retrieval_results", _merge_retrieval_results)(state))

    branch_states: list[_ReviewGraphState] = []
    records = _evidence_records_by_jd(state)
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(state["jd_ids"])))) as executor:
        futures = {}
        for jd_id in state["jd_ids"]:
            record = records[jd_id]
            node = _inspect_score_and_gates if record["evidence_status"] == "sufficient" else _generate_evidence_gap_report
            name = "inspect_score_and_gates" if record["evidence_status"] == "sufficient" else "generate_evidence_gap_report"
            futures[
                executor.submit(
                    _logged_node(name, node),
                    {**_shared_branch_context(state), "jd_id": jd_id, "evidence_record": record},
                )
            ] = jd_id
        for future in as_completed(futures):
            branch_states.append(future.result())
    for item in branch_states:
        state["decision_review"].extend(item.get("decision_review", []))
        state["evidence_gap_reports"].extend(item.get("evidence_gap_reports", []))
    state = _apply_update(state, _logged_node("merge_review_paths", _merge_review_paths)(state))
    if _sufficient_jd_ids(state):
        state = _apply_update(state, _logged_node("generate_interview_questions", _generate_interview_questions)(state))
        state = _apply_update(state, _logged_node("generate_reference_answers", _generate_reference_answers)(state))
        state = _apply_update(state, _logged_node("generate_revision_tasks", _generate_revision_tasks)(state))
    state = _apply_update(state, _logged_node("validate_against_fabrication_policy", _validate_against_fabrication_policy)(state))
    return _apply_update(state, _logged_node("write_review_artifact", _write_review_artifact)(state))


def _apply_update(state: _ReviewGraphState, updates: _ReviewGraphState) -> _ReviewGraphState:
    return {**state, **updates}


def _shared_branch_context(state: _ReviewGraphState) -> dict[str, Any]:
    return {
        "run_dir": state["run_dir"],
        "requested_jd_id": state.get("requested_jd_id"),
        "database_url": state.get("database_url"),
        "evidence_threshold": state["evidence_threshold"],
        "graph_runtime": state["graph_runtime"],
        "run_id": state["run_id"],
        "candidate_id": state["candidate_id"],
        "candidate_profile": state["candidate_profile"],
        "jd_ids": state["jd_ids"],
        "jd_profiles": state["jd_profiles"],
        "scorecards": state["scorecards"],
        "gates": state["gates"],
        "explanations": state["explanations"],
        "strategies": state["strategies"],
        "requirement_matrix": state["requirement_matrix"],
        "retrieval_chunks": state["retrieval_chunks"],
    }


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
        "retrieval_chunks": _build_retrieval_chunks(run_dir, candidate, jd_profiles),
    }


def _retrieve_relevant_evidence(state: _ReviewGraphState) -> _ReviewGraphState:
    jd_id = state["jd_id"]
    query = _query_for_jd(state, jd_id)
    chunks = state["retrieval_chunks"]
    started = perf_counter()
    if state.get("database_url"):
        retriever = PgVectorRetriever(str(state["database_url"]))
        retriever_type = "PgVectorRetriever"
        jd_results = _retrieval_results_to_dicts(
            retriever.search(query, limit=8, candidate_id=state["candidate_id"], jd_id=jd_id)
        )
    else:
        retriever = None
        retriever_type = "ArtifactTokenRetriever"
        jd_results = _search_chunks(chunks, query, limit=8, jd_id=jd_id)
    log_retrieval_query(
        state["run_dir"],
        stage="review",
        query=query,
        retriever_type=retriever_type,
        filters={"candidate_id": state["candidate_id"], "jd_id": jd_id} if retriever else {"jd_id": jd_id},
        limit=8,
        hit_count=len(jd_results),
        started=started,
    )
    started = perf_counter()
    if retriever:
        candidate_results = _retrieval_results_to_dicts(
            retriever.search(
                query,
                limit=8,
                candidate_id=state["candidate_id"],
                source_type="candidate_evidence",
            )
        )
    else:
        candidate_results = _search_chunks(
            chunks,
            query,
            limit=8,
            candidate_id=state["candidate_id"],
            source_type="candidate_evidence",
        )
    log_retrieval_query(
        state["run_dir"],
        stage="review",
        query=query,
        retriever_type=retriever_type,
        filters={"candidate_id": state["candidate_id"], "source_type": "candidate_evidence"},
        limit=8,
        hit_count=len(candidate_results),
        started=started,
    )
    results = _dedupe_results([*candidate_results, *jd_results])
    supporting = [result for result in results if _is_supporting_evidence(result)]
    evidence_count = len(supporting)
    threshold = int(state.get("evidence_threshold") or EVIDENCE_THRESHOLD)
    record = {
        "jd_id": jd_id,
        "evidence_count": evidence_count,
        "minimum_required": threshold,
        "evidence_status": "sufficient" if evidence_count >= threshold else "insufficient",
        "result_count": len(results),
    }
    return {
        "retrieval_results": [_serializable_result(jd_id, result) for result in results],
        "retrieval_misses": [] if results else [jd_id],
        "evidence_records": [record],
    }


def _merge_retrieval_results(state: _ReviewGraphState) -> _ReviewGraphState:
    return {}


def _inspect_score_and_gates(state: _ReviewGraphState) -> _ReviewGraphState:
    jd_id = state["jd_id"]
    scorecard = _first_match(state["scorecards"], jd_id=jd_id) or {}
    gate = _first_match(state["gates"], jd_id=jd_id) or {}
    explanation = _first_match(state["explanations"], jd_id=jd_id) or {}
    strategy = _first_match(state["strategies"], jd_id=jd_id) or {}
    record = state["evidence_record"]
    decision = {
        "jd_id": jd_id,
        "title": (_first_match(state["jd_profiles"], jd_id=jd_id) or {}).get("title", ""),
        "company": (_first_match(state["jd_profiles"], jd_id=jd_id) or {}).get("company", ""),
        "evidence_status": "sufficient",
        "evidence_count": record["evidence_count"],
        "minimum_required": record["minimum_required"],
        "gate_status": gate.get("status") or scorecard.get("gate_status") or "unknown",
        "final_score": scorecard.get("final_overall_score") or scorecard.get("overall_score") or 0,
        "decision_source": scorecard.get("final_decision_source", ""),
        "ranking_summary": explanation.get("decision_summary", ""),
        "apply_decision": strategy.get("apply_decision", "review"),
        "skipped_nodes": [],
    }
    return {"decision_review": [decision]}


def _generate_evidence_gap_report(state: _ReviewGraphState) -> _ReviewGraphState:
    jd_id = state["jd_id"]
    record = state["evidence_record"]
    jd = _first_match(state["jd_profiles"], jd_id=jd_id) or {}
    focus = _gap_focus_for_jd(jd)
    report = {
        "jd_id": jd_id,
        "evidence_count": record["evidence_count"],
        "minimum_required": record["minimum_required"],
        "recommended_evidence": [
            f"补充与 {focus} 直接相关的项目、职责或成果证据。",
            "标注可复核来源，例如原简历条目、项目材料或过往申请反馈。",
            "证据不足前不要生成模板化面试题、参考答案或简历改写任务。",
        ],
    }
    decision = {
        "jd_id": jd_id,
        "title": jd.get("title", ""),
        "company": jd.get("company", ""),
        "evidence_status": "insufficient",
        "evidence_count": record["evidence_count"],
        "minimum_required": record["minimum_required"],
        "gate_status": "evidence_insufficient",
        "final_score": None,
        "decision_source": "evidence-gap-report",
        "ranking_summary": "证据不足，跳过评分检查和生成节点，先补证据。",
        "apply_decision": "evidence_needed",
        "skipped_nodes": REVIEW_SKIPPED_NODES,
    }
    return {"decision_review": [decision], "evidence_gap_reports": [report]}


def _merge_review_paths(state: _ReviewGraphState) -> _ReviewGraphState:
    return {}


def _generate_interview_questions(state: _ReviewGraphState) -> _ReviewGraphState:
    sufficient_jd_ids = [state["jd_id"]] if state.get("jd_id") else _sufficient_jd_ids(state)
    questions: list[dict[str, Any]] = []
    for jd_id in sufficient_jd_ids:
        jd = _first_match(state["jd_profiles"], jd_id=jd_id) or {}
        focus_items = jd.get("interview_focus_areas") or jd.get("keywords") or ["项目证据"]
        for focus in focus_items[:3]:
            questions.append(
                {
                    "jd_id": jd_id,
                    "question": f"请说明你在 {focus} 相关项目中的具体职责、证据和结果。",
                    "evidence_citations": _citations_for_jd(state, jd_id)[:2],
                }
            )
    return {"interview_questions": questions}


def _generate_reference_answers(state: _ReviewGraphState) -> _ReviewGraphState:
    jd_id = _node_jd_id(state)
    answers: list[dict[str, Any]] = []
    for question in state.get("interview_questions", []):
        if jd_id and question.get("jd_id") != jd_id:
            continue
        answers.append(
            {
                "jd_id": question["jd_id"],
                "question": question["question"],
                "answer": "围绕已验证经历回答，先说任务背景，再说个人动作，最后说明可复核结果；不要补充没有证据的硬事实。",
                "evidence_citations": question.get("evidence_citations", []),
            }
        )
    return {"reference_answers": answers}


def _generate_revision_tasks(state: _ReviewGraphState) -> _ReviewGraphState:
    jd_id = _node_jd_id(state)
    sufficient_jd_ids = {jd_id} if jd_id else set(_sufficient_jd_ids(state))
    tasks: list[dict[str, Any]] = []
    for strategy in state["strategies"]:
        jd_id = strategy.get("jd_id")
        if jd_id not in sufficient_jd_ids:
            continue
        for item in strategy.get("resume_revision_tasks", []) or strategy.get("recommended_actions", []):
            tasks.append(
                {
                    "jd_id": jd_id,
                    "task": str(item),
                    "evidence_policy": "rewrite_only",
                    "source": "plan/application_strategies.json",
                }
            )
    return {"revision_tasks": tasks}


def _validate_against_fabrication_policy(state: _ReviewGraphState) -> _ReviewGraphState:
    blocked_needles = ["学历", "学位", "专业", "证书", "雇主", "工作年限", "论文", "奖项", "work authorization"]
    safe_tasks: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    for task in state.get("revision_tasks", []):
        text = str(task.get("task", "")).lower()
        if any(needle.lower() in text for needle in blocked_needles) and "证据" not in text:
            removed.append(task)
            continue
        safe_tasks.append(task)
    validation = {
        "fabrication_policy": "passed",
        "unsupported_hard_fact_tasks_removed": removed,
        "warnings": [] if not state.get("retrieval_misses") else ["部分 JD 未检索到相关证据。"],
    }
    return {"revision_tasks": safe_tasks, "validation": validation}


def _write_review_artifact(state: _ReviewGraphState) -> _ReviewGraphState:
    run_dir = state["run_dir"]
    review_dir = stage_dir(run_dir, "review")
    decisions = _ordered_by_jd(state["decision_review"], state["jd_ids"])
    evidence_records = _ordered_by_jd(state["evidence_records"], state["jd_ids"])
    review = {
        "schema_version": "post-run-review-v2",
        "run_id": state["run_id"],
        "candidate_id": state["candidate_id"],
        "jd_ids": state["jd_ids"],
        "provider": {"provider": "deterministic-review-agent", "model": "artifact-rag-v2"},
        "graph_runtime": state.get("graph_runtime", "unknown"),
        "parallel_topology": {
            "retrieve": "fanout_by_jd",
            "inspect": "fanout_by_jd",
            "generation": "run_level_evidence_sufficient_only",
            "evidence_threshold": state["evidence_threshold"],
            "fan_in_nodes": ["merge_retrieval_results", "merge_review_paths"],
        },
        "decision_review": decisions,
        "retrieval": {
            "result_count": len(state.get("retrieval_results", [])),
            "misses": state.get("retrieval_misses", []),
            "low_evidence_jd_count": sum(1 for item in evidence_records if item.get("evidence_status") == "insufficient"),
            "evidence_by_jd": evidence_records,
        },
        "evidence_citations": _evidence_citations(state.get("retrieval_results", [])),
        "evidence_gap_reports": _ordered_by_jd(state.get("evidence_gap_reports", []), state["jd_ids"]),
        "interview_questions": state.get("interview_questions", []),
        "reference_answers": state.get("reference_answers", []),
        "revision_tasks": state.get("revision_tasks", []),
        "validation": state["validation"],
    }
    dump_json(review_dir / "post_run_review.json", review)
    (review_dir / "interview_prep.md").write_text(_render_interview_prep(review), encoding="utf-8")
    return {"review": review}


def _build_retrieval_chunks(
    run_dir: Path,
    candidate: dict[str, Any],
    jd_profiles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    candidate_id = str(candidate.get("candidate_id") or "unknown")
    for field in ["experiences", "projects", "skills", "strengths", "core_claims", "verified_evidence"]:
        for index, text in enumerate(_safe_list(candidate.get(field))):
            chunks.append(
                _chunk(
                    text=text,
                    source_type="candidate_evidence",
                    source_id=f"candidate_profile.{field}.{index}",
                    candidate_id=candidate_id,
                    jd_id=None,
                    run_id=run_dir.name,
                    artifact_path="analyze/candidate_profile.json",
                    provenance_summary=f"candidate_profile.{field}",
                )
            )
    for item in _read_json(run_dir / "analyze" / "requirement_matrix.json", []):
        evidence_refs = _safe_list(item.get("evidence_refs"))
        text = " ".join([str(item.get("requirement_text") or ""), *evidence_refs]).strip()
        chunks.append(
            _chunk(
                text=text,
                source_type="requirement_evidence",
                source_id=str(item.get("requirement_id") or ""),
                candidate_id=candidate_id,
                jd_id=str(item.get("jd_id") or ""),
                run_id=run_dir.name,
                artifact_path="analyze/requirement_matrix.json",
                provenance_summary=f"requirement evidence: {item.get('evidence_status')}",
                evidence_status=str(item.get("evidence_status") or ""),
                evidence_refs=evidence_refs,
            )
        )
    for explanation in _read_json(run_dir / "evaluate" / "ranking_explanations.json", []):
        chunks.append(
            _chunk(
                text=" ".join(
                    [
                        str(explanation.get("decision_summary") or ""),
                        " ".join(_safe_list(explanation.get("positive_signals"))),
                        " ".join(_safe_list(explanation.get("risk_flags"))),
                        " ".join(_safe_list(explanation.get("evidence_refs"))),
                    ]
                ),
                source_type="ranking_explanation",
                source_id=str(explanation.get("variant_id") or ""),
                candidate_id=candidate_id,
                jd_id=str(explanation.get("jd_id") or ""),
                run_id=run_dir.name,
                artifact_path="evaluate/ranking_explanations.json",
                provenance_summary="ranking explanation",
            )
        )
    for strategy in _read_json(run_dir / "plan" / "application_strategies.json", []):
        chunks.append(
            _chunk(
                text=" ".join(
                    [
                        str(strategy.get("reason_summary") or ""),
                        " ".join(_safe_list(strategy.get("decision_drivers"))),
                        " ".join(_safe_list(strategy.get("recommended_actions"))),
                        " ".join(_safe_list(strategy.get("resume_revision_tasks"))),
                    ]
                ),
                source_type="application_strategy",
                source_id=str(strategy.get("recommended_variant_id") or ""),
                candidate_id=candidate_id,
                jd_id=str(strategy.get("jd_id") or ""),
                run_id=run_dir.name,
                artifact_path="plan/application_strategies.json",
                provenance_summary="application strategy",
            )
        )
    for jd in jd_profiles:
        chunks.append(
            _chunk(
                text=_query_text_for_jd(jd),
                source_type="jd_profile",
                source_id=str(jd.get("jd_id") or ""),
                candidate_id=candidate_id,
                jd_id=str(jd.get("jd_id") or ""),
                run_id=run_dir.name,
                artifact_path="analyze/jd_profiles.json",
                provenance_summary="JD profile",
            )
        )
    return [chunk for chunk in chunks if chunk["text"].strip()]


def _chunk(
    *,
    text: str,
    source_type: str,
    source_id: str,
    candidate_id: str,
    jd_id: str | None,
    run_id: str,
    artifact_path: str,
    provenance_summary: str,
    **metadata: Any,
) -> dict[str, Any]:
    return {
        "text": text,
        "metadata": {
            "source_type": source_type,
            "source_id": source_id,
            "candidate_id": candidate_id,
            "jd_id": jd_id,
            "run_id": run_id,
            "artifact_path": artifact_path,
            "provenance_summary": provenance_summary,
            **metadata,
        },
    }


def _search_chunks(
    chunks: list[dict[str, Any]],
    query: str,
    *,
    limit: int,
    candidate_id: str | None = None,
    jd_id: str | None = None,
    source_type: str | None = None,
) -> list[dict[str, Any]]:
    query_tokens = _tokens(query)
    results: list[dict[str, Any]] = []
    for chunk in chunks:
        metadata = chunk["metadata"]
        if candidate_id and metadata.get("candidate_id") != candidate_id:
            continue
        if jd_id and metadata.get("jd_id") != jd_id:
            continue
        if source_type and metadata.get("source_type") != source_type:
            continue
        text_tokens = _tokens(chunk["text"])
        overlap = query_tokens & text_tokens
        if not overlap:
            continue
        score = len(overlap) / math.sqrt(max(1, len(query_tokens)) * max(1, len(text_tokens)))
        results.append({"text": chunk["text"], "metadata": metadata, "score": round(score, 6)})
    return sorted(results, key=lambda item: (-item["score"], str(item["metadata"].get("source_id"))))[:limit]


def _retrieval_results_to_dicts(results: list[RetrievalResult]) -> list[dict[str, Any]]:
    return [{"text": item.text, "metadata": item.metadata, "score": item.score} for item in results]


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", text.lower())
        if token not in {"and", "or", "the", "with", "for", "to", "of", "in", "a", "an"}
    }


def _is_supporting_evidence(result: dict[str, Any]) -> bool:
    metadata = result["metadata"]
    if metadata.get("source_type") == "candidate_evidence":
        return float(result.get("score") or 0.0) >= 0.15
    if metadata.get("source_type") == "requirement_evidence":
        return metadata.get("evidence_status") in {"verified", "inferred", "simulatable"} and bool(metadata.get("evidence_refs"))
    return False


def _serializable_result(jd_id: str, result: dict[str, Any]) -> dict[str, Any]:
    return {"jd_id": jd_id, "text": result["text"], "metadata": result["metadata"], "score": result["score"]}


def _dedupe_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str | None]] = set()
    deduped: list[dict[str, Any]] = []
    for result in results:
        metadata = result["metadata"]
        key = (str(metadata.get("source_type")), str(metadata.get("source_id")), metadata.get("jd_id"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(result)
    return deduped


def _query_for_jd(state: _ReviewGraphState, jd_id: str) -> str:
    jd = _first_match(state["jd_profiles"], jd_id=jd_id) or {}
    return _query_text_for_jd(jd) or jd_id


def _query_text_for_jd(jd: dict[str, Any]) -> str:
    return " ".join(
        [
            str(jd.get("title") or ""),
            str(jd.get("company") or ""),
            " ".join(_safe_list(jd.get("keywords"))),
            " ".join(_safe_list(jd.get("requirements"))),
            " ".join(_safe_list(jd.get("must_have_requirements"))),
            " ".join(_safe_list(jd.get("interview_focus_areas"))),
        ]
    ).strip()


def _evidence_records_by_jd(state: _ReviewGraphState) -> dict[str, dict[str, Any]]:
    records = {str(item["jd_id"]): item for item in state.get("evidence_records", [])}
    missing = [jd_id for jd_id in state["jd_ids"] if jd_id not in records]
    if missing:
        raise ValueError(f"Missing retrieval evidence records for: {', '.join(missing)}")
    return records


def _sufficient_jd_ids(state: _ReviewGraphState) -> list[str]:
    decisions = {str(item.get("jd_id")): item for item in state.get("decision_review", [])}
    return [jd_id for jd_id in state["jd_ids"] if decisions.get(jd_id, {}).get("evidence_status") == "sufficient"]


def _citations_for_jd(state: _ReviewGraphState, jd_id: str) -> list[dict[str, Any]]:
    return [
        citation
        for citation in _evidence_citations(state.get("retrieval_results", []))
        if citation.get("jd_id") in {None, jd_id} or citation.get("review_jd_id") == jd_id
    ]


def _evidence_citations(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str | None, str]] = set()
    for result in results:
        metadata = result["metadata"]
        key = (
            str(metadata.get("source_type")),
            str(metadata.get("source_id")),
            metadata.get("jd_id"),
            str(result.get("jd_id")),
        )
        if key in seen:
            continue
        seen.add(key)
        citations.append(
            {
                "review_jd_id": result.get("jd_id"),
                "source_type": metadata.get("source_type"),
                "source_id": metadata.get("source_id"),
                "candidate_id": metadata.get("candidate_id"),
                "jd_id": metadata.get("jd_id"),
                "run_id": metadata.get("run_id"),
                "artifact_path": metadata.get("artifact_path"),
                "provenance_summary": metadata.get("provenance_summary"),
                "text": result["text"],
                "score": result["score"],
            }
        )
    return citations


def _render_interview_prep(review: dict[str, Any]) -> str:
    lines = [f"# 面试准备 - {review['run_id']}", "", "## 证据", ""]
    for citation in review["evidence_citations"][:8]:
        if citation.get("review_jd_id") not in {None, *[item["jd_id"] for item in review["interview_questions"]]}:
            continue
        lines.append(f"- {citation['provenance_summary']}：{str(citation['text'])[:140]}")
    lines.extend(["", "## 问题与参考回答", ""])
    for answer in review["reference_answers"]:
        lines.append(f"### {answer['question']}")
        lines.append("")
        lines.append(answer["answer"])
        lines.append("")
    lines.extend(["## 简历修订任务", ""])
    for task in review["revision_tasks"]:
        lines.append(f"- {task['task']}")
    return "\n".join(lines).strip() + "\n"


def _state_summary(state: _ReviewGraphState) -> dict[str, Any]:
    run_dir = state.get("run_dir")
    return {
        "run_id": state.get("run_id") or (run_dir.name if isinstance(run_dir, Path) else None),
        "requested_jd_id": state.get("requested_jd_id"),
        "jd_id": state.get("jd_id"),
        "jd_count": len(state.get("jd_ids", [])),
        "retrieval_result_count": len(state.get("retrieval_results", [])),
        "retrieval_miss_count": len(state.get("retrieval_misses", [])),
        "evidence_record_count": len(state.get("evidence_records", [])),
        "decision_count": len(state.get("decision_review", [])),
        "evidence_gap_count": len(state.get("evidence_gap_reports", [])),
        "question_count": len(state.get("interview_questions", [])),
        "answer_count": len(state.get("reference_answers", [])),
        "revision_task_count": len(state.get("revision_tasks", [])),
    }


def _node_jd_id(state: _ReviewGraphState) -> str | None:
    if state.get("jd_id"):
        return str(state["jd_id"])
    for key in ["interview_questions", "reference_answers", "revision_tasks"]:
        jd_ids = {str(item.get("jd_id")) for item in state.get(key, []) if item.get("jd_id")}
        if len(jd_ids) == 1:
            return next(iter(jd_ids))
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
