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
STRUCTURED_PROMPT_BUDGET = 4000   # Module instructions + evidence, Chinese ~2 chars/token
STRUCTURED_COMPLETION_BUDGET = 3000  # Multi-layer answers: points + ref + follow-ups + mistakes + rubric
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
    completion_budget: int = COMPLETION_TOKEN_BUDGET,
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
            max_completion_tokens=completion_budget,
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
            max_completion_tokens=completion_budget,
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
        max_completion_tokens=completion_budget,
    )
    try:
        body = _openai_json_call(configured, prompt, max_tokens=completion_budget)
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
            max_completion_tokens=completion_budget,
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
            max_completion_tokens=completion_budget,
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
            max_completion_tokens=completion_budget,
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


def _openai_json_call(config: dict[str, str], prompt: str, max_tokens: int = COMPLETION_TOKEN_BUDGET) -> dict[str, Any]:
    payload = json.dumps(
        {
            "model": config["model"],
            "messages": [
                {
                    "role": "system",
                    "content": "Return strict JSON only. Use only the supplied evidence. Do not fabricate facts. All content must be in Chinese.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
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


def _bounded_prompt(prompt: str, budget: int = PROMPT_TOKEN_BUDGET) -> str:
    """Truncate prompt to fit within token budget.

    Uses budget * 2 for character limit (Chinese ~2 chars/token, English ~4).
    This is a conservative estimate that works for mixed Chinese/English text.
    """
    estimated = _estimate_tokens(prompt)
    if estimated <= budget:
        return prompt
    return prompt[: budget * 2]


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


# ── Structured question generation (module-aware, multi-layer answers) ──

def generate_module_questions(
    *,
    run_dir: Path,
    jd_id: str,
    jd_profile: dict[str, Any],
    module_key: str,
    module_name_cn: str,
    evidence_citations: list[dict[str, Any]],
    target_count: int = 3,
) -> list[dict[str, Any]]:
    """Generate interview questions for a specific module with full answer structure.

    Each question includes: question, answer_points, reference_answer,
    follow_up_questions, common_mistakes, and evaluation_rubric.
    """
    prompt = _bounded_prompt(
        _structured_question_prompt(
            jd_id=jd_id,
            jd_profile=jd_profile,
            module_key=module_key,
            module_name_cn=module_name_cn,
            evidence_citations=evidence_citations,
            target_count=target_count,
        ),
        budget=STRUCTURED_PROMPT_BUDGET,
    )
    payload, generation = _run_json_generation(
        run_dir=run_dir,
        stage="review",
        operation=f"generate_{module_key}_questions",
        prompt=prompt,
        fallback=lambda: _deterministic_structured_questions(
            jd_id, jd_profile, module_key, module_name_cn, evidence_citations, target_count, {}
        ),
        completion_budget=STRUCTURED_COMPLETION_BUDGET,
    )
    questions = payload.get("questions") if isinstance(payload, dict) else []
    if not isinstance(questions, list):
        questions = []
    normalized: list[dict[str, Any]] = []
    for item in questions[:target_count]:
        if not isinstance(item, dict):
            continue
        question_text = str(item.get("question") or "").strip()
        if not question_text:
            continue
        normalized.append(
            {
                "question_id": str(item.get("question_id") or f"{jd_id}-{module_key}-{len(normalized) + 1:03d}"),
                "jd_id": jd_id,
                "module": module_key,
                "module_name": module_name_cn,
                "question": question_text,
                "answer_points": _string_list(item.get("answer_points")),
                "reference_answer": str(item.get("reference_answer") or "").strip(),
                "follow_up_questions": _string_list(item.get("follow_up_questions")),
                "common_mistakes": _string_list(item.get("common_mistakes")),
                "evaluation_rubric": item.get("evaluation_rubric") if isinstance(item.get("evaluation_rubric"), dict) else {},
                "evidence_citations": _select_citations(item.get("evidence_citations"), evidence_citations),
                "provenance_citation_count": len(_select_citations(item.get("evidence_citations"), evidence_citations)),
                "generation": generation,
            }
        )
    if not normalized:
        return _deterministic_structured_questions(
            jd_id, jd_profile, module_key, module_name_cn, evidence_citations, target_count, generation,
        )
    return normalized


def _structured_question_prompt(
    *,
    jd_id: str,
    jd_profile: dict[str, Any],
    module_key: str,
    module_name_cn: str,
    evidence_citations: list[dict[str, Any]],
    target_count: int,
) -> str:
    role = f"{jd_profile.get('title', '')} @ {jd_profile.get('company', '')}"
    requirements = "\n".join(_string_list(jd_profile.get("requirements", []))[:10])
    keywords = ", ".join(_string_list(jd_profile.get("keywords", []))[:15])

    module_instructions = _MODULE_INSTRUCTIONS.get(module_key, "")
    prompts = [
        f"你是一位资深面试官。请为以下岗位生成 {target_count} 道「{module_name_cn}」模块的中文面试题。",
        f"JD: {jd_id} | {role}",
        f"关键词: {keywords}",
        f"岗位要求:\n{requirements}",
        "",
        f"--- 本模块出题要求 ---",
        module_instructions,
        "",
        "--- 证据上下文 ---",
        _context_block(evidence_citations),
        "",
        "--- 输出格式 ---",
        "返回JSON，每道题必须包含以下完整字段：",
        "{",
        '  "questions": [{',
        '    "question_id": "' + f'{jd_id}-{module_key}-001' + '",',
        '    "question": "中文面试问题",',
        '    "answer_points": ["回答要点1", "回答要点2", "回答要点3"],',
        '    "reference_answer": "中文参考回答（200-500字，包含项目背景、技术方案、核心难点、效果指标、复盘改进）",',
        '    "follow_up_questions": ["追问1", "追问2"],',
        '    "common_mistakes": ["常见错误1", "常见错误2"],',
        '    "evaluation_rubric": {"优秀": "标准...", "合格": "标准...", "不合格": "标准..."},',
        '    "evidence_citations": [{"source_id": "证据ID"}]',
        "  }]",
        "}",
        "",
        "要求：问题必须结合候选人的真实项目经历和岗位要求，参考回答必须有具体技术细节。禁止编造不存在的经历。使用中文。",
    ]
    return _bounded_prompt("\n".join(prompts))


def _deterministic_structured_questions(
    jd_id: str,
    jd_profile: dict[str, Any],
    module_key: str,
    module_name_cn: str,
    evidence_citations: list[dict[str, Any]],
    target_count: int,
    generation: dict[str, Any],
) -> list[dict[str, Any]]:
    citations = _select_citations(None, evidence_citations)
    evidence = _evidence_phrase(citations)
    title = jd_profile.get("title", "该岗位")
    questions: list[dict[str, Any]] = []
    for i in range(target_count):
        questions.append(
            {
                "question_id": f"{jd_id}-{module_key}-{i + 1:03d}",
                "jd_id": jd_id,
                "module": module_key,
                "module_name": module_name_cn,
                "question": f"请结合实际项目经历，回答关于{title}的{module_name_cn}问题（{i + 1}/{target_count}）。",
                "answer_points": ["项目背景与个人职责", "技术方案与核心难点", "效果指标与复盘改进"],
                "reference_answer": f"回答应基于 {evidence} 中的证据。先描述问题背景，再说明技术方案，最后阐述效果与改进方向。避免编造硬事实。",
                "follow_up_questions": ["为什么选择这个技术方案？", "如果重做会怎么改进？"],
                "common_mistakes": ["回答过于笼统缺乏具体技术细节", "将团队成果包装为个人贡献"],
                "evaluation_rubric": {"优秀": "有具体数据和技术细节", "合格": "基本覆盖要点但缺乏深度", "不合格": "无法回答或明显虚构"},
                "evidence_citations": citations,
                "provenance_citation_count": len(citations),
                "generation": generation,
            }
        )
    return questions


# ── Per-module instruction templates ──────────────────────────────────

_MODULE_INSTRUCTIONS: dict[str, str] = {
    "self_intro_match": """生成定制化自我介绍与岗位匹配问题。
从JD中抽取核心能力要求，从CV中找对应证据。
问题应强制要求候选人完成：岗位需求 → 自身经历 → 技术证据 → 项目结果。
示例：你的简历里有几个项目，哪个项目和这个岗位最相关？为什么？""",

    "jd_core_calibration": """考察候选人是否真正理解JD为什么需要这些能力。
不是问"会不会"，而是问"你怎么理解这个岗位为什么需要它"。
根据JD中的技术栈和业务场景，生成针对性理解题。
示例：这个岗位提到RAG和Agent，你怎么理解二者在工程实践上的区别？""",

    "fundamentals": """根据JD和CV技术栈动态生成基础概念题。后端：HTTP/HTTPS、RESTful、进程线程协程、Redis、MySQL索引、事务ACID、消息队列。Python/Agent：async/await、asyncio、Pydantic、FastAPI、LLM超时重试。LLM应用：embedding、向量vs关键词检索、RAG流程、rerank、prompt engineering、tool calling、Agent vs workflow。""",

    "tech_stack_deep_dive": """根据CV中写过的具体技术栈生成深度追问。追问到框架选择理由、具体配置、参数调优、工程实践。如CV写了FastAPI+Qdrant+Redis就追问为什么选FastAPI、Qdrant的collection/point/payload、Redis职责、限流日志。核心原则：简历写了什么就必须问到可以判断真假。""",

    "project_interrogation": """最核心模块。按顺序拷打项目经历：项目背景→个人职责→技术方案→核心难点→关键取舍→失败案例→性能效果→可维护性。每道题追问1-2个方向，结合候选人真实项目生成具体问题。禁止泛泛而问。""",

    "system_design": """考察架构能力和工程取舍。根据岗位级别生成相应难度的系统设计题。
示例：设计一个支持1000 QPS的RAG服务，你会怎么设计系统架构？包括API网关、检索层、生成层、缓存策略、监控告警。
追问：为什么这样分模块？单点故障怎么处理？如何灰度发布？""",

    "behavioral": """考察协作、沟通、抗压、冲突处理能力。
示例：请描述一次你和产品经理就技术方案产生分歧的经历，你是怎么处理的？最终结果如何？
如果项目排期很紧，你会如何平衡技术质量与交付时间？""",

    "counter_question": """模拟真实面试中的反问环节。生成候选人应该在面试结束时反问面试官的问题。
这些问题应体现候选人对岗位、团队、技术方向的深入思考。
示例：团队目前在LLM应用开发中最大的技术挑战是什么？团队对Agent的自主程度是怎么考虑的？""",

    "llm_agent_specialized": """LLM/Agent岗专项，三个方向：1.RAG：chunk/embedding/rerank/评估。2.Agent：tool calling/memory/planner/多Agent。3.工程可控性：trace/fallback/权限/injection防护/HITL。每方向1-3题。""",
}
