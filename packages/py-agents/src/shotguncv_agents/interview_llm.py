from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib import request

from shotguncv_core.run_logs import (
    log_fallback_used,
    log_llm_call_failed,
    log_llm_call_finished,
    log_llm_call_started,
)


PROMPT_TOKEN_BUDGET = 3000
COMPLETION_TOKEN_BUDGET = 1000
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT_SEC = 30


def generate_interview_questions(
    *,
    run_dir: Path,
    jd_id: str,
    jd_profile: dict[str, Any],
    evidence_citations: list[dict[str, Any]],
    max_questions: int = 3,
) -> list[dict[str, Any]]:
    focus_items = _focus_items(jd_profile)[:max_questions]
    prompt = _bounded_prompt(
        _question_prompt(jd_id=jd_id, jd_profile=jd_profile, focus_items=focus_items, evidence_citations=evidence_citations)
    )
    payload, generation = _run_json_generation(
        run_dir=run_dir,
        stage="review",
        operation="generate_interview_questions",
        prompt=prompt,
        fallback=lambda: {"questions": _deterministic_questions(jd_id, jd_profile, focus_items, evidence_citations)},
    )
    questions = payload.get("questions") if isinstance(payload, dict) else []
    if not isinstance(questions, list):
        questions = []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(questions[:max_questions], start=1):
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        if not question:
            continue
        citations = _select_citations(item.get("evidence_citations"), evidence_citations)
        normalized.append(
            {
                "question_id": str(item.get("question_id") or f"{jd_id}-q-{index:03d}"),
                "jd_id": jd_id,
                "question": question,
                "expected_direction": str(item.get("expected_direction") or item.get("rationale") or ""),
                "evidence_citations": citations,
                "provenance_citation_count": len(citations),
                "generation": generation,
            }
        )
    return normalized or _deterministic_questions(jd_id, jd_profile, focus_items, evidence_citations, generation=generation)


def generate_reference_answers(
    *,
    run_dir: Path,
    questions: list[dict[str, Any]],
    evidence_citations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    prompt = _bounded_prompt(_answer_prompt(questions=questions, evidence_citations=evidence_citations))
    payload, generation = _run_json_generation(
        run_dir=run_dir,
        stage="review",
        operation="generate_reference_answers",
        prompt=prompt,
        fallback=lambda: {"answers": _deterministic_answers(questions, evidence_citations)},
    )
    answers = payload.get("answers") if isinstance(payload, dict) else []
    if not isinstance(answers, list):
        answers = []
    normalized: list[dict[str, Any]] = []
    by_question = {str(question.get("question_id")): question for question in questions}
    for item in answers:
        if not isinstance(item, dict):
            continue
        question_id = str(item.get("question_id") or "")
        question = by_question.get(question_id) or _first_question_for_jd(questions, str(item.get("jd_id") or ""))
        if not question:
            continue
        citations = _select_citations(item.get("evidence_citations"), question.get("evidence_citations") or evidence_citations)
        normalized.append(
            {
                "question_id": str(question.get("question_id")),
                "jd_id": str(question.get("jd_id")),
                "question": str(question.get("question") or item.get("question") or ""),
                "answer": str(item.get("answer") or "").strip(),
                "evidence_citations": citations,
                "provenance_citation_count": len(citations),
                "generation": generation,
            }
        )
    return normalized or _deterministic_answers(questions, evidence_citations, generation=generation)


def evaluate_interview_answer(
    *,
    run_dir: Path,
    question: dict[str, Any],
    answer: str,
    evidence_citations: list[dict[str, Any]],
) -> dict[str, Any]:
    prompt = _bounded_prompt(_evaluation_prompt(question=question, answer=answer, evidence_citations=evidence_citations))
    payload, generation = _run_json_generation(
        run_dir=run_dir,
        stage="interview",
        operation="evaluate_interview_answer",
        prompt=prompt,
        fallback=lambda: _deterministic_evaluation(question, answer, evidence_citations),
    )
    if not isinstance(payload, dict):
        payload = _deterministic_evaluation(question, answer, evidence_citations)
    score = _bounded_score(payload.get("score"))
    citations = _select_citations(payload.get("evidence_citations"), evidence_citations)
    return {
        "question_id": str(question.get("question_id")),
        "jd_id": str(question.get("jd_id")),
        "score": score,
        "status": "generated",
        "feedback": str(payload.get("feedback") or "Answer reviewed against available evidence."),
        "improvement_suggestions": _string_list(payload.get("improvement_suggestions"))[:5],
        "evidence_citations": citations,
        "generation": generation,
    }


def build_simulated_answer(question: dict[str, Any]) -> str:
    citations = question.get("evidence_citations") or []
    evidence = _evidence_phrase(citations)
    focus = str(question.get("expected_direction") or question.get("question") or "the requested capability")
    return (
        f"I would answer by grounding the story in {evidence}. "
        f"The core point is {focus}. I would describe the task, my direct action, "
        "the shipped artifact, and the measurable validation without adding unsupported facts."
    )


def _run_json_generation(
    *,
    run_dir: Path,
    stage: str,
    operation: str,
    prompt: str,
    fallback: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    configured = _llm_config()
    prompt_tokens = _estimate_tokens(prompt)
    if configured["provider"] == "deterministic":
        started = log_llm_call_started(
            run_dir,
            stage=stage,
            operation=operation,
            provider="deterministic",
            model="artifact-rag",
            prompt_tokens=prompt_tokens,
            max_completion_tokens=COMPLETION_TOKEN_BUDGET,
        )
        payload = fallback()
        completion_tokens = _estimate_tokens(json.dumps(payload, ensure_ascii=False))
        log_llm_call_finished(
            run_dir,
            stage=stage,
            operation=operation,
            provider="deterministic",
            model="artifact-rag",
            started=started,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            max_completion_tokens=COMPLETION_TOKEN_BUDGET,
            output_parse_status="success",
            fallback_used=False,
        )
        return payload, _generation_metadata("deterministic", "artifact-rag", prompt_tokens, completion_tokens, fallback_used=False)

    started = log_llm_call_started(
        run_dir,
        stage=stage,
        operation=operation,
        provider=configured["provider"],
        model=configured["model"],
        prompt_tokens=prompt_tokens,
        max_completion_tokens=COMPLETION_TOKEN_BUDGET,
    )
    try:
        body = _openai_json_call(configured, prompt)
        content = body["choices"][0]["message"]["content"]
        payload = _parse_json(content)
        usage = body.get("usage", {}) if isinstance(body, dict) else {}
        completion_tokens = _safe_int(usage.get("completion_tokens")) or _estimate_tokens(content)
        prompt_tokens = _safe_int(usage.get("prompt_tokens")) or prompt_tokens
        total_tokens = _safe_int(usage.get("total_tokens")) or prompt_tokens + completion_tokens
        log_llm_call_finished(
            run_dir,
            stage=stage,
            operation=operation,
            provider=configured["provider"],
            model=configured["model"],
            started=started,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            max_completion_tokens=COMPLETION_TOKEN_BUDGET,
            output_parse_status="success",
            fallback_used=False,
        )
        return payload, _generation_metadata(configured["provider"], configured["model"], prompt_tokens, completion_tokens, fallback_used=False)
    except Exception as exc:  # noqa: BLE001
        log_llm_call_failed(
            run_dir,
            stage=stage,
            operation=operation,
            provider=configured["provider"],
            model=configured["model"],
            started=started,
            error=exc,
            fallback_used=True,
        )
        log_fallback_used(
            run_dir,
            stage=stage,
            operation=operation,
            from_provider=configured["provider"],
            to_provider="deterministic",
            reason=f"{exc.__class__.__name__}: {str(exc)[:300]}",
        )
        fallback_started = log_llm_call_started(
            run_dir,
            stage=stage,
            operation=operation,
            provider="deterministic",
            model="artifact-rag",
            prompt_tokens=prompt_tokens,
            max_completion_tokens=COMPLETION_TOKEN_BUDGET,
        )
        payload = fallback()
        completion_tokens = _estimate_tokens(json.dumps(payload, ensure_ascii=False))
        log_llm_call_finished(
            run_dir,
            stage=stage,
            operation=operation,
            provider="deterministic",
            model="artifact-rag",
            started=fallback_started,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            max_completion_tokens=COMPLETION_TOKEN_BUDGET,
            output_parse_status="fallback_success",
            fallback_used=True,
        )
        return payload, _generation_metadata("deterministic", "artifact-rag", prompt_tokens, completion_tokens, fallback_used=True)


def _llm_config() -> dict[str, str]:
    requested = os.environ.get("SHOTGUNCV_INTERVIEW_LLM_PROVIDER", "auto").strip().lower() or "auto"
    api_key_env = os.environ.get("SHOTGUNCV_INTERVIEW_LLM_API_KEY_ENV", "OPENAI_API_KEY")
    api_key = os.environ.get(api_key_env, "").strip()
    if requested in {"auto", "openai", "openai-compatible"} and api_key:
        provider = "openai" if requested == "openai" else "openai-compatible"
        return {
            "provider": provider,
            "model": os.environ.get("SHOTGUNCV_INTERVIEW_LLM_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
            "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip() or "https://api.openai.com/v1",
            "api_key": api_key,
        }
    return {"provider": "deterministic", "model": "artifact-rag", "base_url": "", "api_key": ""}


def _openai_json_call(config: dict[str, str], prompt: str) -> dict[str, Any]:
    payload = json.dumps(
        {
            "model": config["model"],
            "messages": [
                {
                    "role": "system",
                    "content": "Return strict JSON only. Use only the supplied evidence. Do not fabricate facts.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": COMPLETION_TOKEN_BUDGET,
            "response_format": {"type": "json_object"},
        }
    ).encode("utf-8")
    req = request.Request(
        url=f"{config['base_url'].rstrip('/')}/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {config['api_key']}", "Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=DEFAULT_TIMEOUT_SEC) as handle:
        return json.loads(handle.read().decode("utf-8"))


def _question_prompt(
    *,
    jd_id: str,
    jd_profile: dict[str, Any],
    focus_items: list[str],
    evidence_citations: list[dict[str, Any]],
) -> str:
    return "\n".join(
        [
            "根据以下证据生成中文面试问题。所有问题和预期方向必须使用中文。",
            f"JD ID: {jd_id}",
            f"岗位: {jd_profile.get('title', '')} @ {jd_profile.get('company', '')}",
            f"考察方向: {json.dumps(focus_items, ensure_ascii=False)}",
            "证据上下文:",
            _context_block(evidence_citations),
            (
                "返回JSON: {\"questions\":[{\"question_id\":\"...\",\"question\":\"中文问题\","
                "\"expected_direction\":\"中文预期答题方向\",\"evidence_citations\":[{\"source_id\":\"...\"}]}]}"
            ),
            "每个问题必须引用至少一个证据source_id。问题和方向必须为中文。",
        ]
    )


def _answer_prompt(*, questions: list[dict[str, Any]], evidence_citations: list[dict[str, Any]]) -> str:
    compact_questions = [
        {
            "question_id": item.get("question_id"),
            "jd_id": item.get("jd_id"),
            "question": item.get("question"),
            "expected_direction": item.get("expected_direction"),
        }
        for item in questions
    ]
    return "\n".join(
        [
            "根据以下证据生成中文参考回答。所有回答必须使用中文。",
            f"问题列表: {json.dumps(compact_questions, ensure_ascii=False)}",
            "证据上下文:",
            _context_block(evidence_citations),
            (
                "返回JSON: {\"answers\":[{\"question_id\":\"...\",\"jd_id\":\"...\","
                "\"answer\":\"中文参考回答\",\"evidence_citations\":[{\"source_id\":\"...\"}]}]}"
            ),
            "回答必须引用具体证据，不得编造不存在的雇主、日期、学位、奖项或数据。回答必须为中文。",
        ]
    )


def _evaluation_prompt(*, question: dict[str, Any], answer: str, evidence_citations: list[dict[str, Any]]) -> str:
    return "\n".join(
        [
            "根据证据评估模拟面试回答。反馈和建议必须使用中文。",
            f"问题: {json.dumps(question, ensure_ascii=False)}",
            f"回答: {answer}",
            "证据上下文:",
            _context_block(evidence_citations),
            (
                "返回JSON: {\"score\":4.0,\"feedback\":\"中文反馈\","
                "\"improvement_suggestions\":[\"中文建议\"],\"evidence_citations\":[{\"source_id\":\"...\"}]}"
            ),
        ]
    )


def _bounded_prompt(prompt: str) -> str:
    if _estimate_tokens(prompt) <= PROMPT_TOKEN_BUDGET:
        return prompt
    return prompt[: PROMPT_TOKEN_BUDGET * 4]


def _context_block(citations: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for index, citation in enumerate(citations[:8], start=1):
        source_id = str(citation.get("source_id") or f"source-{index}")
        text = re.sub(r"\s+", " ", str(citation.get("text") or "")).strip()[:700]
        lines.append(
            json.dumps(
                {
                    "source_id": source_id,
                    "source_type": citation.get("source_type"),
                    "artifact_path": citation.get("artifact_path"),
                    "provenance_summary": citation.get("provenance_summary"),
                    "text": text,
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(lines)


def _deterministic_questions(
    jd_id: str,
    jd_profile: dict[str, Any],
    focus_items: list[str],
    evidence_citations: list[dict[str, Any]],
    *,
    generation: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    citations = _select_citations(None, evidence_citations)
    evidence = _evidence_phrase(citations)
    questions: list[dict[str, Any]] = []
    for index, focus in enumerate(focus_items or ["有证据支撑的项目交付"], start=1):
        questions.append(
            {
                "question_id": f"{jd_id}-q-{index:03d}",
                "jd_id": jd_id,
                "question": (
                    f"请描述一个与 {focus} 相关的具体项目经历，"
                    f"基于 {evidence} 中的证据。你做了什么、如何验证的、最大的技术取舍是什么？"
                ),
                "expected_direction": f"使用已有证据解释 {focus}，不得添加未经证实的事实。",
                "evidence_citations": citations,
                "provenance_citation_count": len(citations),
                "generation": generation or {},
            }
        )
    return questions


def _deterministic_answers(
    questions: list[dict[str, Any]],
    evidence_citations: list[dict[str, Any]],
    *,
    generation: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    answers: list[dict[str, Any]] = []
    for question in questions:
        citations = _select_citations(None, question.get("evidence_citations") or evidence_citations)
        evidence = _evidence_phrase(citations)
        answers.append(
            {
                "question_id": str(question.get("question_id")),
                "jd_id": str(question.get("jd_id")),
                "question": str(question.get("question") or ""),
                "answer": (
                    f"回答应基于 {evidence} 中的证据。先描述问题背景，再说明你直接负责的实施工作，"
                    "最后阐述产出物或验证结果。避免编造不存在的雇主、日期、学位、奖项等硬事实，"
                    "确保整个叙述与引用来源保持一致。"
                ),
                "evidence_citations": citations,
                "provenance_citation_count": len(citations),
                "generation": generation or {},
            }
        )
    return answers


def _deterministic_evaluation(question: dict[str, Any], answer: str, evidence_citations: list[dict[str, Any]]) -> dict[str, Any]:
    citations = _select_citations(None, question.get("evidence_citations") or evidence_citations)
    score = 4.0 if answer.strip() and citations else 2.5
    return {
        "score": score,
        "feedback": "回答与已有证据一致且避免编造硬事实时可用。",
        "improvement_suggestions": [
            "明确指出引用的证据来源。",
            "区分直接实施行为和可衡量的验证结果。",
        ],
        "evidence_citations": citations,
    }


def _focus_items(jd_profile: dict[str, Any]) -> list[str]:
    for field in ["interview_focus_areas", "keywords", "requirements", "must_have_requirements"]:
        values = _string_list(jd_profile.get(field))
        if values:
            return values
    title = str(jd_profile.get("title") or "").strip()
    return [title or "evidence-backed delivery"]


def _select_citations(requested: object, available: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_ids = (
        {str(item.get("source_id")) for item in requested if isinstance(item, dict) and item.get("source_id")}
        if isinstance(requested, list)
        else set()
    )
    selected = [citation for citation in available if str(citation.get("source_id")) in source_ids] if source_ids else available[:2]
    return [_compact_citation(item) for item in selected[:3]]


def _compact_citation(citation: dict[str, Any]) -> dict[str, Any]:
    return {
        "review_jd_id": citation.get("review_jd_id"),
        "source_type": citation.get("source_type"),
        "source_id": citation.get("source_id"),
        "artifact_path": citation.get("artifact_path"),
        "provenance_summary": citation.get("provenance_summary"),
        "text": str(citation.get("text") or "")[:500],
        "score": citation.get("score"),
    }


def _evidence_phrase(citations: object) -> str:
    if not isinstance(citations, list) or not citations:
        return "the retrieved evidence"
    first = citations[0] if isinstance(citations[0], dict) else {}
    source = str(first.get("source_id") or first.get("provenance_summary") or "the retrieved evidence")
    text = str(first.get("text") or "").strip()
    if text:
        return f"{source}: {text[:120]}"
    return source


def _first_question_for_jd(questions: list[dict[str, Any]], jd_id: str) -> dict[str, Any] | None:
    for question in questions:
        if str(question.get("jd_id")) == jd_id:
            return question
    return questions[0] if questions else None


def _generation_metadata(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    *,
    fallback_used: bool,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "mode": "rag_context",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "max_prompt_tokens": PROMPT_TOKEN_BUDGET,
        "max_completion_tokens": COMPLETION_TOKEN_BUDGET,
        "fallback_used": fallback_used,
    }


def _parse_json(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("LLM JSON root must be an object.")
    return parsed


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _safe_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bounded_score(value: object) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(5.0, score))


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []
