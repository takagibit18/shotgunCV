"""Interview module definitions and question distribution logic.

Defines 9 interview modules with allocation ratios, evidence filtering rules,
and per-module prompt templates. Used by interview_prep.py to orchestrate
a structured mock interview.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Module definitions ──────────────────────────────────────────────

@dataclass(frozen=True)
class InterviewModule:
    key: str
    name_cn: str
    ratio: float | None  # None = conditional (only for LLM/Agent JDs)
    min_q: int
    max_q: int
    evidence_fields: list[str] = field(default_factory=list)
    description: str = ""


MODULES: list[InterviewModule] = [
    InterviewModule(
        key="self_intro_match",
        name_cn="自我介绍与岗位匹配",
        ratio=0.10,
        min_q=2,
        max_q=3,
        evidence_fields=["jd_profile", "candidate_profile", "requirement_matrix"],
        description="判断候选人是否理解岗位，CV经历与JD的匹配度",
    ),
    InterviewModule(
        key="jd_core_calibration",
        name_cn="JD核心能力校准",
        ratio=0.10,
        min_q=2,
        max_q=4,
        evidence_fields=["jd_profile", "requirement_matrix"],
        description="检查JD关键词是否真的掌握，理解岗位为什么需要这些能力",
    ),
    InterviewModule(
        key="fundamentals",
        name_cn="基础概念考察",
        ratio=0.15,
        min_q=4,
        max_q=6,
        evidence_fields=["jd_profile", "candidate_profile"],
        description="验证技术底层理解，根据JD和CV技术栈动态生成基础题",
    ),
    InterviewModule(
        key="tech_stack_deep_dive",
        name_cn="技术栈深挖",
        ratio=0.15,
        min_q=4,
        max_q=6,
        evidence_fields=["candidate_profile", "requirement_matrix"],
        description="针对CV中写过的技术栈追问工程细节，判断真假",
    ),
    InterviewModule(
        key="project_interrogation",
        name_cn="项目拷打",
        ratio=0.25,
        min_q=6,
        max_q=10,
        evidence_fields=["candidate_profile", "requirement_matrix"],
        description="最核心模块：项目背景→个人职责→技术方案→核心难点→取舍→失败案例→性能→可维护性",
    ),
    InterviewModule(
        key="system_design",
        name_cn="系统设计/工程设计",
        ratio=0.10,
        min_q=2,
        max_q=4,
        evidence_fields=["jd_profile", "candidate_profile"],
        description="看架构能力和工程取舍",
    ),
    InterviewModule(
        key="behavioral",
        name_cn="行为面试",
        ratio=0.05,
        min_q=1,
        max_q=3,
        evidence_fields=["jd_profile", "candidate_profile"],
        description="看协作、沟通、抗压、冲突处理",
    ),
    InterviewModule(
        key="counter_question",
        name_cn="反问环节",
        ratio=0.05,
        min_q=1,
        max_q=2,
        evidence_fields=["jd_profile"],
        description="模拟真实面试闭环，生成候选人应该反问面试官的问题",
    ),
    InterviewModule(
        key="llm_agent_specialized",
        name_cn="LLM/Agent专项",
        ratio=None,  # conditional: only for LLM/Agent/AI Engineer JDs
        min_q=4,
        max_q=8,
        evidence_fields=["jd_profile", "candidate_profile", "requirement_matrix"],
        description="RAG/Agent/Prompt Engineering/工程可控性专项考察",
    ),
]


# ── Distribution logic ───────────────────────────────────────────────

def is_llm_agent_jd(jd_profile: dict[str, Any]) -> bool:
    """Determine whether a JD requires LLM/Agent specialized questions."""
    keywords = _safe_list(jd_profile.get("keywords"))
    title = str(jd_profile.get("title", "")).lower()
    requirements = " ".join(_safe_list(jd_profile.get("requirements", []))).lower()

    llm_signals = {
        "llm", "rag", "agent", "prompt", "langchain", "langgraph",
        "embedding", "vector", "retrieval", "generative ai",
        "大模型", "智能体", "检索增强", "向量", "提示词",
    }
    if any(signal in title for signal in llm_signals):
        return True
    if any(signal in requirements for signal in llm_signals):
        return True
    return bool(set(k.lower() for k in keywords) & llm_signals)


def allocate_questions(
    jd_profile: dict[str, Any],
    *,
    total_questions: int = 25,
) -> dict[str, int]:
    """Allocate question counts per module for a given JD.

    Returns a dict mapping module key -> question count.
    """
    active_modules = [m for m in MODULES if m.ratio is not None]
    if is_llm_agent_jd(jd_profile):
        active_modules.append(
            next(m for m in MODULES if m.key == "llm_agent_specialized")
        )

    # Calculate base allocation from ratios
    ratio_total = sum(m.ratio for m in active_modules if m.ratio is not None)
    allocation: dict[str, int] = {}
    remaining = total_questions

    # Allocate by ratio, clamping to min/max
    for module in active_modules:
        if module.ratio is not None:
            qty = max(module.min_q, min(module.max_q, round(total_questions * module.ratio / ratio_total)))
        else:
            qty = module.min_q
        allocation[module.key] = qty
        remaining -= qty

    # Distribute remaining questions to modules with room to grow
    while remaining > 0:
        for module in active_modules:
            if remaining <= 0:
                break
            current = allocation[module.key]
            cap = module.max_q
            if current < cap:
                allocation[module.key] = current + 1
                remaining -= 1

    return allocation


def module_by_key(key: str) -> InterviewModule:
    for m in MODULES:
        if m.key == key:
            return m
    raise KeyError(f"Unknown interview module: {key}")


def _safe_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []
