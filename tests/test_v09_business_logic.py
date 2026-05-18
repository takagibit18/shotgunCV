from __future__ import annotations

from pathlib import Path

import pytest

from shotguncv_core.models import CandidateProfile, JDProfile
from shotguncv_core.pipeline import (
    _build_preflight_gates,
    _build_requirement_matrix,
    _classify_requirement_tier,
    _collect_jd_requirements,
    _evaluate_hard_gate,
    _matching_evidence_refs,
)
from shotguncv_agents import providers
from shotguncv_agents.providers import DeterministicAnalyzeProvider, OpenAIAnalyzeProvider, _extract_resume_sections


def test_hard_gate_allows_bachelor_when_jd_accepts_bachelor_or_master() -> None:
    requirement = "Bachelor of Engineering | Bachelor of Science | Master of Science"
    candidate_text = "Bachelor degree in Computer Science. Built Python AI systems."

    assert _evaluate_hard_gate(requirement.lower(), candidate_text.lower()) == "verified"


def test_requirement_matrix_does_not_block_bachelor_candidate_for_bachelor_or_master_jd() -> None:
    candidate = _candidate(skills=["Bachelor degree in Computer Science", "Python", "LLM"])
    jd = _jd(
        must_have_requirements=["Bachelor of Engineering | Bachelor of Science | Master of Science"],
        responsibilities=["Build LLM evaluation pipelines"],
        requirements=[],
    )

    matrix = _build_requirement_matrix(candidate, [jd])
    gates = _build_preflight_gates(matrix)

    education_item = next(item for item in matrix if "Bachelor of Engineering" in item.requirement_text)
    assert education_item.tier == "hard_gate"
    assert education_item.evidence_status == "verified"
    assert len(gates) == 1
    assert gates[0].jd_id == "jd-001"
    assert gates[0].status == "pass"


def test_collect_jd_requirements_filters_platform_ui_noise_from_responsibilities() -> None:
    jd = _jd(
        must_have_requirements=["Experience building RAG evaluation systems"],
        responsibilities=[
            "@ micro1",
            "Apply Save Copy link",
            "Published 16d ago",
            "USD 160K-300K Mid-level",
            "Perks/Benefits",
            "Mentoring",
            "Remote work",
            "Skills/Tech-stack",
            "Education",
            "Design agent evaluation workflows",
        ],
        requirements=[],
    )

    requirements = _collect_jd_requirements(jd)

    assert "Experience building RAG evaluation systems" in requirements
    assert "Design agent evaluation workflows" in requirements
    assert "@ micro1" not in requirements
    assert "Apply Save Copy link" not in requirements
    assert "Published 16d ago" not in requirements
    assert "USD 160K-300K Mid-level" not in requirements
    assert "Perks/Benefits" not in requirements
    assert "Mentoring" not in requirements
    assert "Remote work" not in requirements
    assert "Skills/Tech-stack" not in requirements
    assert "Education" not in requirements


def test_deterministic_analyzer_cleans_jd_ui_noise_before_profile_fields() -> None:
    feedback = DeterministicAnalyzeProvider().analyze(
        candidate_id="cand-001",
        candidate_resume_path="resume.md",
        resume_text="Technical Skills: Python, FastAPI, LangChain, Qdrant",
        jd_inputs=[
            {
                "source_type": "text",
                "source_value": "AI Engineer",
                "content": "\n".join(
                    [
                        "Title: AI Engineer",
                        "Company: Example",
                        "Body:",
                        "- Apply Save Copy link",
                        "- Published 16d ago",
                        "- Build RAG evaluation workflows",
                    ]
                ),
            }
        ],
    )

    jd = feedback.jd_profiles[0]
    assert jd.responsibilities == ["Build RAG evaluation workflows"]
    assert jd.requirements == ["Build RAG evaluation workflows"]


def test_candidate_profile_extracts_full_technical_stack_from_skill_sections() -> None:
    feedback = DeterministicAnalyzeProvider().analyze(
        candidate_id="cand-001",
        candidate_resume_path="resume.md",
        resume_text=(
            "Technical Skills: Python, Click, Pydantic, FastAPI, Docker, Redis, "
            "LangChain, LangGraph, Qdrant, BM25, RAGAS\n"
            "Projects: Built a RAG evaluation service."
        ),
        jd_inputs=[
            {
                "source_type": "text",
                "source_value": "AI Engineer",
                "content": "Title: AI Engineer\nCompany: Example\nBody:\n- Build AI systems",
            }
        ],
    )

    for expected in ["Python", "Click", "Pydantic", "FastAPI", "Docker", "Redis", "LangChain", "LangGraph", "Qdrant", "BM25", "RAGAS"]:
        assert expected in feedback.candidate_profile.skills


def test_resume_sections_keep_contact_education_and_intent_out_of_experiences() -> None:
    sections = _extract_resume_sections(
        "\n".join(
            [
                "基本信息",
                "邮箱: hual6641@gmail.com",
                "个人主页: https://example.com",
                "教育背景",
                "Bachelor degree in Computer Science, GPA: 3.6",
                "求职意向",
                "AI Engineer",
                "工作经历",
                "Built FastAPI services for RAG workflows",
            ]
        )
    )

    assert sections["experiences"] == ["Built FastAPI services for RAG workflows"]
    assert not any("邮箱" in item or "GPA" in item or "求职意向" in item for item in sections["experiences"])


def test_matching_evidence_refs_ignores_resume_metadata_contact_lines() -> None:
    refs = _matching_evidence_refs(
        "python rag evaluation",
        [
            "邮箱: hual6641@gmail.com",
            "个人主页: https://example.com",
            "Built Python RAG evaluation service",
        ],
    )

    assert refs == ["Built Python RAG evaluation service"]


def test_requirement_tier_uses_specific_context_not_broad_action_words() -> None:
    assert _classify_requirement_tier("Bachelor degree in Computer Science") == "hard_gate"
    assert _classify_requirement_tier("Own Python RAG evaluation pipelines") == "high_priority"
    assert _classify_requirement_tier("Own core platform roadmap") != "high_priority"
    assert _classify_requirement_tier("Participate in team collaboration") == "nice_to_have"


def test_openai_analyzer_prompt_constrains_structured_skill_and_jd_extraction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, str] = {}

    def fake_chat_completion(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured["prompt"] = args[3]
        raise RuntimeError("stop after prompt capture")

    monkeypatch.setattr(providers, "_chat_completion", fake_chat_completion)
    provider = OpenAIAnalyzeProvider(
        model="test",
        base_url=None,
        api_key="test",
        run_dir=tmp_path,
    )

    provider.analyze(
        candidate_id="cand-001",
        candidate_resume_path="resume.md",
        resume_text="Technical Skills: Python, FastAPI, LangChain",
        jd_inputs=[
            {
                "source_type": "text",
                "source_value": "AI Engineer",
                "content": "Title: AI Engineer\nCompany: Example\nBody:\n- Apply Save Copy link\n- Build RAG systems",
            }
        ],
    )

    prompt = captured["prompt"]
    assert "programming languages" in prompt
    assert "frameworks" in prompt
    assert "AI stack" in prompt
    assert "experiences are paid or internship work history" in prompt
    assert "projects are portfolio, coursework, or side projects" in prompt
    assert "ignore platform UI text" in prompt
    assert "Apply Save Copy link" not in prompt
    assert "Build RAG systems" in prompt


def test_openai_analyzer_filters_ui_noise_from_returned_jd_profiles(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_chat_completion(*args, **kwargs):  # type: ignore[no-untyped-def]
        return """
        {
          "candidate_profile": {
            "experiences": ["Built RAG systems"],
            "projects": [],
            "skills": ["Python", "FastAPI"],
            "industry_tags": [],
            "strengths": ["RAG delivery"],
            "constraints": [],
            "preferences": [],
            "core_claims": ["Built RAG systems"],
            "verified_evidence": ["Built RAG systems"],
            "missing_evidence_areas": [],
            "preferred_role_tracks": ["AI Engineer"]
          },
          "jd_profiles": [
            {
              "jd_id": "jd-001",
              "title": "AI Engineer",
              "company": "Example",
              "cluster": "ai-engineer",
              "responsibilities": ["Apply Save Copy link", "Published 16d ago", "Build RAG systems"],
              "requirements": ["Skills/Tech-stack", "Python"],
              "keywords": ["Python"],
              "seniority": "mid",
              "bonuses": ["Remote work"],
              "risk_signals": [],
              "source_type": "text",
              "source_value": "AI Engineer",
              "must_have_requirements": ["Education", "Python"],
              "nice_to_have_requirements": ["Perks/Benefits"],
              "hidden_signals": [],
              "interview_focus_areas": ["RAG"],
              "role_level_confidence": 0.8
            }
          ],
          "evidence_map": {}
        }
        """

    monkeypatch.setattr(providers, "_chat_completion", fake_chat_completion)
    provider = OpenAIAnalyzeProvider(
        model="test",
        base_url=None,
        api_key="test",
        run_dir=tmp_path,
    )

    feedback = provider.analyze(
        candidate_id="cand-001",
        candidate_resume_path="resume.md",
        resume_text="Built RAG systems",
        jd_inputs=[{"source_type": "text", "source_value": "AI Engineer", "content": "Build RAG systems"}],
    )

    jd = feedback.jd_profiles[0]
    assert jd.responsibilities == ["Build RAG systems"]
    assert jd.requirements == ["Python"]
    assert jd.bonuses == []
    assert jd.must_have_requirements == ["Python"]
    assert jd.nice_to_have_requirements == []


def _candidate(skills: list[str] | None = None) -> CandidateProfile:
    return CandidateProfile(
        candidate_id="cand-001",
        base_resume_path="resume.md",
        experiences=["Built production AI systems"],
        projects=[],
        skills=skills or [],
        industry_tags=[],
        strengths=[],
        constraints=[],
        preferences=[],
        core_claims=[],
        verified_evidence=skills or [],
    )


def _jd(
    must_have_requirements: list[str],
    responsibilities: list[str],
    requirements: list[str],
) -> JDProfile:
    return JDProfile(
        jd_id="jd-001",
        title="AI Engineer",
        company="Example",
        cluster="ai-engineer",
        responsibilities=responsibilities,
        requirements=requirements,
        keywords=[],
        seniority="mid",
        bonuses=[],
        risk_signals=[],
        source_type="text",
        source_value="AI Engineer",
        must_have_requirements=must_have_requirements,
        nice_to_have_requirements=[],
    )
