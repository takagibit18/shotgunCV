"""Standalone interview preparation module.

Generates interview questions and reference answers directly from
structured pipeline artifacts (jd_profiles.json, candidate_profile.json,
requirement_matrix.json). No retrieval step needed.

Usage:
    shotguncv interview-prep --run-dir ./runs/demo
    shotguncv interview-prep --run-dir ./runs/demo --jd-id jd-001
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shotguncv_agents.interview_llm import (
    generate_interview_questions as generate_llm_interview_questions,
    generate_reference_answers as generate_llm_reference_answers,
)
from shotguncv_core.storage import dump_json, load_json, stage_dir


def run_interview_prep(
    run_dir: Path,
    *,
    jd_id: str | None = None,
    max_questions_per_jd: int = 3,
) -> dict[str, Any]:
    """Generate interview questions and reference answers from structured artifacts.

    Reads jd_profiles.json, candidate_profile.json, and requirement_matrix.json
    directly. Builds evidence citations from verified/inferred requirements.
    No retrieval step needed.
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

    questions: list[dict[str, Any]] = []
    for target_jd_id in jd_ids:
        jd = _first_match(jd_profiles, jd_id=target_jd_id) or {}
        citations = evidence_map.get(target_jd_id, [])
        questions.extend(
            generate_llm_interview_questions(
                run_dir=run_dir,
                jd_id=target_jd_id,
                jd_profile=jd,
                evidence_citations=citations,
                max_questions=max_questions_per_jd,
            )
        )

    answers: list[dict[str, Any]] = []
    if questions:
        questions_by_jd: dict[str, list[dict[str, Any]]] = {}
        for question in questions:
            question_jd_id = str(question.get("jd_id") or "")
            questions_by_jd.setdefault(question_jd_id, []).append(question)
        for question_jd_id, jd_questions in questions_by_jd.items():
            citations = evidence_map.get(question_jd_id, [])
            answers.extend(
                generate_llm_reference_answers(
                    run_dir=run_dir,
                    questions=jd_questions,
                    evidence_citations=citations,
                )
            )

    result = {
        "schema_version": "interview-prep-v1",
        "run_id": run_dir.name,
        "candidate_id": candidate_id,
        "jd_ids": jd_ids,
        "evidence_citations_by_jd": {jd_id: len(citations) for jd_id, citations in evidence_map.items()},
        "interview_questions": questions,
        "reference_answers": answers,
    }

    review_dir = stage_dir(run_dir, "review")
    dump_json(review_dir / "interview_prep.json", result)
    return result


def _build_evidence_map(
    candidate: dict[str, Any],
    requirement_matrix: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Build per-JD evidence citations from requirement_matrix + candidate_profile.

    For each requirement with verified/inferred status, extract evidence_refs
    and match them against candidate profile entries to produce citation objects
    suitable for interview LLM prompts.
    """
    # Index candidate profile entries for matching
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
    """Index candidate profile text entries for evidence_ref matching."""
    entries: dict[str, dict[str, Any]] = {}
    for field in ["experiences", "projects", "skills", "strengths", "core_claims", "verified_evidence"]:
        for index, text in enumerate(_safe_list(candidate.get(field))):
            source_id = f"candidate_profile.{field}.{index}"
            entries[source_id] = {"field": field, "index": index, "source_id": source_id, "text": text}
    return entries


def _match_evidence_ref(ref: str, entries: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """Match an evidence_ref string against candidate profile entries.

    Tries exact match first, then substring match.
    """
    ref_lower = ref.lower().strip()
    if not ref_lower:
        return None

    # Try exact match
    for source_id, entry in entries.items():
        if entry["text"].lower().strip() == ref_lower:
            return entry

    # Try substring match (ref is part of entry text)
    for source_id, entry in entries.items():
        if ref_lower in entry["text"].lower():
            return entry

    # Try the reverse: entry text is part of ref
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
