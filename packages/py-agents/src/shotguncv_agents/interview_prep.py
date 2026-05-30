"""Standalone interview preparation module with structured module-based questions.

Generates a complete mock interview with module-aware question distribution,
multi-layer answers (points + reference + follow-ups + mistakes + rubric).
Reads structured pipeline artifacts directly — no retrieval step needed.

Usage:
    shotguncv interview-prep --run-dir ./runs/demo
    shotguncv interview-prep --run-dir ./runs/demo --jd-id jd-001 --total-questions 30
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from shotguncv_agents.interview_llm import generate_module_questions
from shotguncv_agents.interview_modules import (
    allocate_questions,
    is_llm_agent_jd,
    module_by_key,
)
from shotguncv_core.storage import dump_json, load_json, stage_dir


def run_interview_prep(
    run_dir: Path,
    *,
    jd_id: str | None = None,
    total_questions: int = 25,
) -> dict[str, Any]:
    """Generate a complete structured mock interview.

    Reads jd_profiles.json, candidate_profile.json, and requirement_matrix.json
    directly. Allocates questions across interview modules, generates per-module
    questions with full answer structure via LLM.
    """
    candidate = _read_json(run_dir / "analyze" / "candidate_profile.json", {})
    jd_profiles = _read_json(run_dir / "analyze" / "jd_profiles.json", [])
    requirement_matrix = _read_json(run_dir / "analyze" / "requirement_matrix.json", [])

    candidate_id = str(candidate.get("candidate_id") or "unknown")
    jd_ids = [str(item.get("jd_id")) for item in jd_profiles if item.get("jd_id")]
    if jd_id:
        jd_ids = [item for item in jd_ids if item == jd_id]
    if not jd_ids:
        raise ValueError("No JD profiles are available for interview preparation.")

    # Build structured evidence citations from artifacts
    evidence_map = _build_evidence_map(candidate, requirement_matrix)

    all_questions: list[dict[str, Any]] = []
    module_summary: dict[str, dict[str, Any]] = {}

    for target_jd_id in jd_ids:
        jd = _first_match(jd_profiles, jd_id=target_jd_id) or {}
        citations = evidence_map.get(target_jd_id, [])
        is_llm_jd = is_llm_agent_jd(jd)

        # Allocate questions per module for this JD
        allocation = allocate_questions(jd, total_questions=total_questions)

        jd_questions: list[dict[str, Any]] = []
        module_keys = [k for k, v in allocation.items() if v > 0]
        for i, module_key in enumerate(module_keys):
            count = allocation[module_key]
            if i > 0:
                time.sleep(3.0)  # Rate limit for free-tier endpoints
            module_def = module_by_key(module_key)
            questions = generate_module_questions(
                run_dir=run_dir,
                jd_id=target_jd_id,
                jd_profile=jd,
                module_key=module_key,
                module_name_cn=module_def.name_cn,
                evidence_citations=citations,
                target_count=count,
            )
            jd_questions.extend(questions)

        all_questions.extend(jd_questions)
        module_summary[target_jd_id] = {
            "title": jd.get("title", ""),
            "company": jd.get("company", ""),
            "is_llm_agent_jd": is_llm_jd,
            "allocation": allocation,
            "question_count": len(jd_questions),
        }

    result = {
        "schema_version": "interview-prep-v2",
        "run_id": run_dir.name,
        "candidate_id": candidate_id,
        "jd_ids": jd_ids,
        "total_questions_requested": total_questions,
        "total_questions_generated": len(all_questions),
        "evidence_citations_by_jd": {jd_id: len(citations) for jd_id, citations in evidence_map.items()},
        "module_summary": module_summary,
        "interview_questions": all_questions,
    }

    review_dir = stage_dir(run_dir, "review")
    dump_json(review_dir / "interview_prep.json", result)
    return result


def _build_evidence_map(
    candidate: dict[str, Any],
    requirement_matrix: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Build per-JD evidence citations from requirement_matrix + candidate_profile."""
    candidate_entries = _index_candidate_entries(candidate)
    evidence_map: dict[str, list[dict[str, Any]]] = {}
    for item in requirement_matrix:
        status = str(item.get("evidence_status") or "")
        if status not in {"verified", "inferred"}:
            continue
        jd_id = str(item.get("jd_id") or "")
        if not jd_id:
            continue
        evidence_refs = _safe_list(item.get("evidence_refs"))
        if not evidence_refs:
            continue
        for ref in evidence_refs:
            matched = _match_evidence_ref(ref, candidate_entries)
            if matched is not None:
                evidence_map.setdefault(jd_id, []).append(
                    {
                        "source_type": "candidate_evidence",
                        "source_id": matched["source_id"],
                        "artifact_path": "analyze/candidate_profile.json",
                        "provenance_summary": f"candidate_profile.{matched['field']}",
                        "text": matched["text"],
                        "score": 1.0,
                    }
                )
    return evidence_map


def _index_candidate_entries(candidate: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for field in ["experiences", "projects", "skills", "strengths", "core_claims", "verified_evidence"]:
        for index, text in enumerate(_safe_list(candidate.get(field))):
            source_id = f"candidate_profile.{field}.{index}"
            entries[source_id] = {"field": field, "index": index, "source_id": source_id, "text": text}
    return entries


def _match_evidence_ref(ref: str, entries: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    ref_lower = ref.lower().strip()
    if not ref_lower:
        return None
    for source_id, entry in entries.items():
        if entry["text"].lower().strip() == ref_lower:
            return entry
    for source_id, entry in entries.items():
        if ref_lower in entry["text"].lower():
            return entry
    for source_id, entry in entries.items():
        if entry["text"].lower().strip() in ref_lower:
            return entry
    return None


def _first_match(items: list[dict[str, Any]], **matches: str) -> dict[str, Any] | None:
    for item in items:
        if all(item.get(key) == value for key, value in matches.items()):
            return item
    return None


def _safe_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _read_json(path: Path, fallback: Any) -> Any:
    return load_json(path) if path.exists() else fallback
