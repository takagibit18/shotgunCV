from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shotguncv_agents.interview_llm import build_simulated_answer, evaluate_interview_answer
from shotguncv_core.run_logs import (
    log_interview_answer_submitted,
    log_interview_evaluation_generated,
    log_interview_question_deleted,
    log_interview_question_modified,
)
from shotguncv_core.storage import dump_json, load_json, stage_dir
from shotguncv_core.run_status import now_iso


SESSION_SCHEMA_VERSION = "interview-session-v1"
QUESTIONS_SCHEMA_VERSION = "interview-questions-v1"
ANSWERS_SCHEMA_VERSION = "interview-answers-v1"
EVALUATION_SCHEMA_VERSION = "interview-evaluation-v1"


def run_interview_session(
    run_dir: Path,
    *,
    jd_id: str | None = None,
    auto_approve: bool = False,
    answers_json: Path | None = None,
    reviewed_questions_json: Path | None = None,
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    review = _load_review(run_dir)
    interview_dir = stage_dir(run_dir, "interview")
    session_path = interview_dir / "session.json"
    questions_path = interview_dir / "questions.json"

    session = _load_existing_session(session_path, run_dir)
    questions_payload = _load_existing_questions(questions_path)
    if not questions_payload:
        questions = _normalize_questions(review.get("interview_questions", []), jd_id=jd_id)
        questions_payload = {
            "schema_version": QUESTIONS_SCHEMA_VERSION,
            "run_id": run_dir.name,
            "session_id": session["session_id"],
            "review_status": "pending",
            "questions": questions,
        }
        session.update(
            {
                "status": "awaiting_question_review",
                "jd_id": jd_id,
                "question_count": len(questions),
                "interrupt_after": "generate_questions",
                "artifacts": {
                    "questions": "interview/questions.json",
                    "answers": "interview/answers.json",
                    "evaluation": "interview/evaluation.json",
                },
            }
        )
        _upsert_checkpoint(session, "generate_questions", "completed")
        dump_json(questions_path, questions_payload)
        dump_json(session_path, session)

    if not auto_approve:
        return session

    questions_payload = _apply_question_review(
        run_dir,
        session_id=str(session["session_id"]),
        questions_payload=questions_payload,
        reviewed_questions_json=reviewed_questions_json,
    )
    approved_questions = [item for item in questions_payload.get("questions", []) if not item.get("deleted")]
    questions_payload["review_status"] = "approved"
    questions_payload["approved_at"] = now_iso()
    dump_json(questions_path, questions_payload)

    session["status"] = "answering"
    session["interrupt_after"] = "candidate_answer"
    _upsert_checkpoint(session, "human_review", "completed")
    dump_json(session_path, session)

    answers = _build_answers(run_dir, str(session["session_id"]), approved_questions, answers_json)
    dump_json(
        interview_dir / "answers.json",
        {
            "schema_version": ANSWERS_SCHEMA_VERSION,
            "run_id": run_dir.name,
            "session_id": session["session_id"],
            "answers": answers,
        },
    )
    _upsert_checkpoint(session, "candidate_answer", "completed")

    evaluations: list[dict[str, Any]] = []
    for answer in answers:
        question = _question_by_id(approved_questions, str(answer["question_id"]))
        evaluation = evaluate_interview_answer(
            run_dir=run_dir,
            question=question,
            answer=str(answer["answer"]),
            evidence_citations=question.get("evidence_citations", []),
        )
        evaluations.append(evaluation)
        log_interview_evaluation_generated(
            run_dir,
            session_id=str(session["session_id"]),
            question_id=str(evaluation["question_id"]),
            jd_id=str(evaluation["jd_id"]),
            score=float(evaluation["score"]),
        )

    dump_json(
        interview_dir / "evaluation.json",
        {
            "schema_version": EVALUATION_SCHEMA_VERSION,
            "run_id": run_dir.name,
            "session_id": session["session_id"],
            "evaluations": evaluations,
        },
    )
    session["status"] = "completed"
    session["completed_at"] = now_iso()
    session["answer_count"] = len(answers)
    session["evaluation_count"] = len(evaluations)
    session["interrupt_after"] = None
    _upsert_checkpoint(session, "ai_evaluation", "completed")
    dump_json(session_path, session)
    return session


def _load_review(run_dir: Path) -> dict[str, Any]:
    review_path = run_dir / "review" / "post_run_review.json"
    if not review_path.exists():
        raise ValueError("Run `shotguncv review --run-dir <run-dir>` before starting an interview session.")
    review = load_json(review_path)
    if not isinstance(review, dict):
        raise ValueError("Review artifact must be a JSON object.")
    return review


def _load_existing_session(path: Path, run_dir: Path) -> dict[str, Any]:
    if path.exists():
        session = load_json(path)
        if isinstance(session, dict):
            return session
    return {
        "schema_version": SESSION_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "session_id": f"{run_dir.name}-interview",
        "status": "created",
        "created_at": now_iso(),
        "graph_runtime": "artifact-checkpoint-hitl",
        "checkpoints": [],
    }


def _load_existing_questions(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = load_json(path)
    return payload if isinstance(payload, dict) else None


def _normalize_questions(questions: object, *, jd_id: str | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    if not isinstance(questions, list):
        return normalized
    for index, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            continue
        question_jd_id = str(question.get("jd_id") or "")
        if jd_id and question_jd_id != jd_id:
            continue
        question_id = str(question.get("question_id") or f"{question_jd_id}-q-{index:03d}")
        normalized.append(
            {
                **question,
                "question_id": question_id,
                "jd_id": question_jd_id,
                "review_status": "pending",
                "deleted": False,
            }
        )
    return normalized


def _apply_question_review(
    run_dir: Path,
    *,
    session_id: str,
    questions_payload: dict[str, Any],
    reviewed_questions_json: Path | None,
) -> dict[str, Any]:
    if reviewed_questions_json is None:
        for question in questions_payload.get("questions", []):
            question["review_status"] = "accepted"
        return questions_payload

    reviewed = load_json(reviewed_questions_json)
    reviewed_questions = reviewed.get("questions") if isinstance(reviewed, dict) else None
    if not isinstance(reviewed_questions, list):
        raise ValueError("Reviewed questions JSON must contain a `questions` list.")

    original_by_id = {str(item.get("question_id")): item for item in questions_payload.get("questions", [])}
    next_questions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in reviewed_questions:
        if not isinstance(item, dict):
            continue
        question_id = str(item.get("question_id") or "")
        original = original_by_id.get(question_id)
        if original is None:
            continue
        seen_ids.add(question_id)
        merged = {**original, **item, "review_status": "accepted"}
        next_questions.append(merged)
        if str(original.get("question")) != str(merged.get("question")):
            log_interview_question_modified(
                run_dir,
                session_id=session_id,
                question_id=question_id,
                jd_id=str(merged.get("jd_id") or ""),
            )

    for question_id, original in original_by_id.items():
        if question_id in seen_ids:
            continue
        deleted = {**original, "deleted": True, "review_status": "deleted"}
        next_questions.append(deleted)
        log_interview_question_deleted(
            run_dir,
            session_id=session_id,
            question_id=question_id,
            jd_id=str(original.get("jd_id") or ""),
        )

    questions_payload["questions"] = next_questions
    return questions_payload


def _build_answers(
    run_dir: Path,
    session_id: str,
    questions: list[dict[str, Any]],
    answers_json: Path | None,
) -> list[dict[str, Any]]:
    provided_answers = _load_answer_map(answers_json)
    answers: list[dict[str, Any]] = []
    for question in questions:
        question_id = str(question.get("question_id"))
        answer = provided_answers.get(question_id) or build_simulated_answer(question)
        answers.append(
            {
                "question_id": question_id,
                "jd_id": str(question.get("jd_id") or ""),
                "answer": answer,
                "submitted_at": now_iso(),
                "source": "provided" if question_id in provided_answers else "simulated",
            }
        )
        log_interview_answer_submitted(
            run_dir,
            session_id=session_id,
            question_id=question_id,
            jd_id=str(question.get("jd_id") or ""),
            answer_chars=len(answer),
        )
    return answers


def _load_answer_map(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("answers"), dict):
        return {str(key): str(value) for key, value in payload["answers"].items()}
    if isinstance(payload, dict):
        return {str(key): str(value) for key, value in payload.items()}
    raise ValueError("Answers JSON must be an object or contain an `answers` object.")


def _question_by_id(questions: list[dict[str, Any]], question_id: str) -> dict[str, Any]:
    for question in questions:
        if str(question.get("question_id")) == question_id:
            return question
    raise ValueError(f"Missing question for answer: {question_id}")


def _upsert_checkpoint(session: dict[str, Any], name: str, status: str) -> None:
    checkpoints = session.setdefault("checkpoints", [])
    for checkpoint in checkpoints:
        if checkpoint.get("name") == name:
            checkpoint.update({"status": status, "updated_at": now_iso()})
            return
    checkpoints.append({"name": name, "status": status, "updated_at": now_iso()})
