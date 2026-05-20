from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from shotguncv_core.db.indexer import build_projection_batch
from shotguncv_core.rag.retrieval import InMemoryVectorRetriever, PgVectorRetriever, RetrievalResult
from shotguncv_core.run_logs import log_graph_node_finished, log_graph_node_started, log_retrieval_query
from shotguncv_core.storage import dump_json, load_json, stage_dir


def run_post_run_review(run_dir: Path, *, jd_id: str | None = None, database_url: str | None = None) -> dict[str, Any]:
    state: dict[str, Any] = {"run_dir": run_dir.resolve(), "requested_jd_id": jd_id, "database_url": database_url}
    nodes = [
        ("load_run_context", _load_run_context),
        ("retrieve_relevant_evidence", _retrieve_relevant_evidence),
        ("inspect_score_and_gates", _inspect_score_and_gates),
        ("generate_interview_questions", _generate_interview_questions),
        ("generate_reference_answers", _generate_reference_answers),
        ("generate_revision_tasks", _generate_revision_tasks),
        ("validate_against_fabrication_policy", _validate_against_fabrication_policy),
        ("write_review_artifact", _write_review_artifact),
    ]
    logged_nodes = _wrap_graph_nodes(nodes)
    graph_result = _run_langgraph_if_available(state, logged_nodes)
    if graph_result is not None:
        return graph_result["review"]
    state["graph_runtime"] = "sequential-fallback"
    for _, node in logged_nodes:
        state = node(state)
    return state["review"]


def _run_langgraph_if_available(
    state: dict[str, Any], nodes: list[tuple[str, Any]]
) -> dict[str, Any] | None:
    try:
        from langgraph.graph import END, StateGraph
    except ImportError:
        return None
    graph = StateGraph(dict)
    for name, node in nodes:
        graph.add_node(name, node)
    graph.set_entry_point(nodes[0][0])
    for (current_name, _), (next_name, _) in zip(nodes, nodes[1:]):
        graph.add_edge(current_name, next_name)
    graph.add_edge(nodes[-1][0], END)
    compiled = graph.compile()
    return compiled.invoke({**state, "graph_runtime": "langgraph"})


def _wrap_graph_nodes(nodes: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
    return [(name, _logged_node(name, node)) for name, node in nodes]


def _logged_node(name: str, node: Any) -> Any:
    def _run(state: dict[str, Any]) -> dict[str, Any]:
        run_dir: Path = state["run_dir"]
        graph_runtime = str(state.get("graph_runtime") or "unknown")
        run_id = str(state.get("run_id") or run_dir.name)
        jd_count = len(state.get("jd_ids") or [])
        input_summary = _state_summary(state)
        started = log_graph_node_started(
            run_dir,
            graph="post_run_review",
            graph_runtime=graph_runtime,
            node=name,
            run_id=run_id,
            jd_count=jd_count,
            input_summary=input_summary,
        )
        try:
            next_state = node(state)
        except Exception as exc:
            log_graph_node_finished(
                run_dir,
                graph="post_run_review",
                graph_runtime=graph_runtime,
                node=name,
                run_id=run_id,
                jd_count=jd_count,
                started=started,
                status="failed",
                input_summary=input_summary,
                output_summary={"error_type": exc.__class__.__name__, "error_summary": str(exc)[:500]},
            )
            raise
        log_graph_node_finished(
            run_dir,
            graph="post_run_review",
            graph_runtime=graph_runtime,
            node=name,
            run_id=str(next_state.get("run_id") or run_id),
            jd_count=len(next_state.get("jd_ids") or []),
            started=started,
            status="ok",
            input_summary=input_summary,
            output_summary=_state_summary(next_state),
        )
        return next_state

    return _run


def _state_summary(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": state.get("run_id") or Path(state["run_dir"]).name,
        "requested_jd_id": state.get("requested_jd_id"),
        "jd_count": len(state.get("jd_ids") or []),
        "retrieval_result_count": len(state.get("retrieval_results") or []),
        "retrieval_miss_count": len(state.get("retrieval_misses") or []),
        "decision_count": len(state.get("decision_review") or []),
        "question_count": len(state.get("interview_questions") or []),
        "answer_count": len(state.get("reference_answers") or []),
        "revision_task_count": len(state.get("revision_tasks") or []),
        "has_database_url": bool(state.get("database_url")),
    }


def _load_run_context(state: dict[str, Any]) -> dict[str, Any]:
    run_dir: Path = state["run_dir"]
    batch = build_projection_batch(run_dir)
    jd_profiles = _read_json(run_dir / "analyze" / "jd_profiles.json", [])
    scorecards = _read_json(run_dir / "evaluate" / "scorecards.json", [])
    gates = _read_json(run_dir / "analyze" / "preflight_gates.json", [])
    explanations = _read_json(run_dir / "evaluate" / "ranking_explanations.json", [])
    strategies = _read_json(run_dir / "plan" / "application_strategies.json", [])
    requested_jd_id = state.get("requested_jd_id")
    jd_ids = [requested_jd_id] if requested_jd_id else [str(item.get("jd_id")) for item in jd_profiles]
    return {
        **state,
        "batch": batch,
        "run_id": run_dir.name,
        "candidate_id": batch.run.candidate_id,
        "jd_profiles": jd_profiles,
        "scorecards": scorecards,
        "gates": gates,
        "explanations": explanations,
        "strategies": strategies,
        "jd_ids": [item for item in jd_ids if item],
    }


def _retrieve_relevant_evidence(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("database_url"):
        retriever = PgVectorRetriever(state["database_url"])
    else:
        retriever = InMemoryVectorRetriever.from_chunks(state["batch"].retrieval_chunks)
    retriever_type = type(retriever).__name__
    all_results: list[RetrievalResult] = []
    misses: list[str] = []
    for jd_id in state["jd_ids"]:
        query = _query_for_jd(state, jd_id)
        started = perf_counter()
        results = retriever.search(query, limit=5, candidate_id=state["candidate_id"], jd_id=jd_id)
        log_retrieval_query(
            state["run_dir"],
            stage="review",
            query=query,
            retriever_type=retriever_type,
            filters=_retrieval_filters(candidate_id=state["candidate_id"], jd_id=jd_id),
            limit=5,
            hit_count=len(results),
            started=started,
        )
        if not results:
            started = perf_counter()
            results = retriever.search(query, limit=5, candidate_id=state["candidate_id"], source_type="candidate_evidence")
            log_retrieval_query(
                state["run_dir"],
                stage="review",
                query=query,
                retriever_type=retriever_type,
                filters=_retrieval_filters(candidate_id=state["candidate_id"], source_type="candidate_evidence"),
                limit=5,
                hit_count=len(results),
                started=started,
            )
        if results:
            all_results.extend(results)
        else:
            misses.append(jd_id)
    return {**state, "retrieval_results": all_results, "retrieval_misses": misses}


def _retrieval_filters(**filters: str | None) -> dict[str, str]:
    return {key: value for key, value in filters.items() if value}


def _inspect_score_and_gates(state: dict[str, Any]) -> dict[str, Any]:
    decisions = []
    for jd_id in state["jd_ids"]:
        scorecard = _first_match(state["scorecards"], jd_id=jd_id)
        gate = _first_match(state["gates"], jd_id=jd_id)
        explanation = _first_match(state["explanations"], jd_id=jd_id)
        strategy = _first_match(state["strategies"], jd_id=jd_id)
        decisions.append(
            {
                "jd_id": jd_id,
                "gate_status": (gate or {}).get("status") or (scorecard or {}).get("gate_status") or "unknown",
                "final_score": (scorecard or {}).get("final_overall_score") or (scorecard or {}).get("overall_score") or 0,
                "decision_source": (scorecard or {}).get("final_decision_source", ""),
                "ranking_summary": (explanation or {}).get("decision_summary", ""),
                "apply_decision": (strategy or {}).get("apply_decision", "review"),
            }
        )
    return {**state, "decision_review": decisions}


def _generate_interview_questions(state: dict[str, Any]) -> dict[str, Any]:
    questions = []
    for decision in state["decision_review"]:
        jd = _first_match(state["jd_profiles"], jd_id=decision["jd_id"]) or {}
        focus = jd.get("interview_focus_areas") or jd.get("keywords") or ["项目证据"]
        for item in focus[:3]:
            questions.append({"jd_id": decision["jd_id"], "question": f"请说明你在 {item} 相关项目中的具体职责、证据和结果。"})
    return {**state, "interview_questions": questions}


def _generate_reference_answers(state: dict[str, Any]) -> dict[str, Any]:
    citations = _evidence_citations(state["retrieval_results"])
    answers = []
    for question in state["interview_questions"]:
        answer_citations = [item for item in citations if item.get("jd_id") in {None, question["jd_id"]}][:2] or citations[:2]
        answers.append(
            {
                "jd_id": question["jd_id"],
                "question": question["question"],
                "answer": "围绕已验证经历回答，先说任务背景，再说个人动作，最后说明可复核结果；不要补充没有证据的硬事实。",
                "evidence_citations": answer_citations,
            }
        )
    return {**state, "reference_answers": answers}


def _generate_revision_tasks(state: dict[str, Any]) -> dict[str, Any]:
    tasks = []
    for strategy in state["strategies"]:
        if state["requested_jd_id"] and strategy.get("jd_id") != state["requested_jd_id"]:
            continue
        for item in strategy.get("resume_revision_tasks", []) or strategy.get("recommended_actions", []):
            tasks.append(
                {
                    "jd_id": strategy.get("jd_id"),
                    "task": str(item),
                    "evidence_policy": "rewrite_only",
                    "source": "plan/application_strategies.json",
                }
            )
    return {**state, "revision_tasks": tasks}


def _validate_against_fabrication_policy(state: dict[str, Any]) -> dict[str, Any]:
    blocked_needles = ["学历", "学位", "专业", "证书", "雇主", "工作年限", "论文", "奖项", "work authorization"]
    safe_tasks = []
    removed = []
    for task in state["revision_tasks"]:
        text = task["task"].lower()
        if any(needle.lower() in text for needle in blocked_needles) and "证据" not in text:
            removed.append(task)
            continue
        safe_tasks.append(task)
    validation = {
        "fabrication_policy": "passed",
        "unsupported_hard_fact_tasks_removed": removed,
        "warnings": [] if not state["retrieval_misses"] else ["部分 JD 未检索到相关证据。"],
    }
    return {**state, "revision_tasks": safe_tasks, "validation": validation}


def _write_review_artifact(state: dict[str, Any]) -> dict[str, Any]:
    run_dir: Path = state["run_dir"]
    review_dir = stage_dir(run_dir, "review")
    citations = _evidence_citations(state["retrieval_results"])
    review = {
        "schema_version": "post-run-review-v1",
        "run_id": state["run_id"],
        "candidate_id": state["candidate_id"],
        "jd_ids": state["jd_ids"],
        "provider": {"provider": "deterministic-review-agent", "model": "artifact-rag-v1"},
        "graph_runtime": state.get("graph_runtime", "unknown"),
        "decision_review": state["decision_review"],
        "retrieval": {
            "result_count": len(state["retrieval_results"]),
            "misses": state["retrieval_misses"],
        },
        "evidence_citations": citations,
        "interview_questions": state["interview_questions"],
        "reference_answers": state["reference_answers"],
        "revision_tasks": state["revision_tasks"],
        "validation": state["validation"],
        "fallback_reason": None,
    }
    dump_json(review_dir / "post_run_review.json", review)
    (review_dir / "interview_prep.md").write_text(_render_interview_prep(review), encoding="utf-8")
    return {**state, "review": review}


def _render_interview_prep(review: dict[str, Any]) -> str:
    lines = [f"# 面试准备 - {review['run_id']}", "", "## 证据", ""]
    for citation in review["evidence_citations"][:6]:
        lines.append(f"- {citation['provenance_summary']}：{citation['text'][:140]}")
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


def _query_for_jd(state: dict[str, Any], jd_id: str) -> str:
    jd = _first_match(state["jd_profiles"], jd_id=jd_id) or {}
    return " ".join(
        [
            str(jd.get("title") or ""),
            " ".join(str(item) for item in jd.get("keywords", [])),
            " ".join(str(item) for item in jd.get("requirements", [])),
        ]
    ).strip() or jd_id


def _evidence_citations(results: list[RetrievalResult]) -> list[dict[str, Any]]:
    citations = []
    seen = set()
    for result in results:
        metadata = result.metadata
        key = (metadata.get("source_type"), metadata.get("source_id"), metadata.get("chunk_index"))
        if key in seen:
            continue
        seen.add(key)
        citations.append(
            {
                "source_type": metadata.get("source_type"),
                "source_id": metadata.get("source_id"),
                "candidate_id": metadata.get("candidate_id"),
                "jd_id": metadata.get("jd_id"),
                "run_id": metadata.get("run_id"),
                "artifact_path": metadata.get("artifact_path"),
                "provenance_summary": metadata.get("provenance_summary"),
                "text": result.text,
                "score": result.score,
            }
        )
    return citations


def _first_match(items: list[dict[str, Any]], **matches: str) -> dict[str, Any] | None:
    for item in items:
        if all(item.get(key) == value for key, value in matches.items()):
            return item
    return None


def _read_json(path: Path, fallback: Any) -> Any:
    return load_json(path) if path.exists() else fallback
