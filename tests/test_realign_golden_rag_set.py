from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.realign_golden_rag_set import realign_golden_set


def test_realign_golden_set_appends_expected_chunk_keywords_and_preserves_labels(tmp_path: Path) -> None:
    golden_path = tmp_path / "golden.json"
    payload = _golden_payload()
    _write_json(golden_path, payload)
    run_dir = _write_good_run(tmp_path / "run", payload)
    audit_path = tmp_path / "audit.json"
    _write_json(audit_path, _audit_payload())
    changelog_path = tmp_path / "changes.json"

    report = realign_golden_set(
        golden_file=golden_path,
        run_dir=run_dir,
        audit_report_file=audit_path,
        changelog_file=changelog_path,
        today="2026-05-31",
    )

    rewritten = json.loads(golden_path.read_text(encoding="utf-8"))
    sample = rewritten["samples"][0]
    assert report["rewritten_sample_count"] == 1
    assert "检索关键词：education, roles, missing" in sample["question"]
    assert sample["expected_documents"] == payload["samples"][0]["expected_documents"]
    assert sample["retrieval_alignment"] == {
        "method": "bm25_keyword_rewrite",
        "date": "2026-05-31",
        "source": str(audit_path),
    }
    assert "jd-001-req-014" not in sample["question"]
    assert "requirement_evidence" not in sample["question"]
    assert "sha256" not in sample["question"]
    assert "pycharmprojects" not in sample["question"]
    assert "jobpilot" not in sample["question"]
    assert "fixtures" not in sample["question"]

    for untouched in rewritten["samples"][1:4]:
        assert untouched["question_id"] in {"rag-golden-002", "rag-golden-003", "rag-golden-004"}
        assert "检索关键词：" not in untouched["question"]
        assert "retrieval_alignment" not in untouched

    changelog = json.loads(changelog_path.read_text(encoding="utf-8"))
    assert changelog["schema_version"] == "rag-golden-realignment-changelog-v1"
    assert changelog["rewritten_sample_count"] == 1
    assert changelog["changes"][0]["question_id"] == "rag-golden-001"
    assert changelog["changes"][0]["keywords"] == ["education", "roles", "missing"]


def test_realign_golden_set_is_idempotent_when_keywords_already_exist(tmp_path: Path) -> None:
    golden_path = tmp_path / "golden.json"
    payload = _golden_payload()
    payload["samples"][0]["question"] += "（检索关键词：education, roles, missing）"
    payload["samples"][0]["retrieval_alignment"] = {
        "method": "bm25_keyword_rewrite",
        "date": "2026-05-30",
        "source": "old-audit.json",
    }
    _write_json(golden_path, payload)
    run_dir = _write_good_run(tmp_path / "run", payload)
    audit_path = tmp_path / "audit.json"
    _write_json(audit_path, _audit_payload())
    changelog_path = tmp_path / "changes.json"

    report = realign_golden_set(
        golden_file=golden_path,
        run_dir=run_dir,
        audit_report_file=audit_path,
        changelog_file=changelog_path,
        today="2026-05-31",
    )

    rewritten = json.loads(golden_path.read_text(encoding="utf-8"))
    assert report["rewritten_sample_count"] == 0
    assert rewritten["samples"][0]["question"].count("检索关键词：") == 1
    assert rewritten["samples"][0]["retrieval_alignment"]["date"] == "2026-05-30"


def test_realign_golden_set_rejects_bad_requirement_artifact_before_rewrite(tmp_path: Path) -> None:
    golden_path = tmp_path / "golden.json"
    payload = _golden_payload()
    _write_json(golden_path, payload)
    run_dir = tmp_path / "run"
    _write_bad_run(run_dir)
    audit_path = tmp_path / "audit.json"
    _write_json(audit_path, _audit_payload())

    with pytest.raises(ValueError, match="Golden set artifact audit failed"):
        realign_golden_set(
            golden_file=golden_path,
            run_dir=run_dir,
            audit_report_file=audit_path,
            changelog_file=tmp_path / "changes.json",
            today="2026-05-31",
        )


def _golden_payload() -> dict[str, object]:
    samples = []
    case_types = ["common_question", "common_question", "no_answer", "multi_document"]
    for index, case_type in enumerate(case_types, start=1):
        expected_documents = []
        if case_type != "no_answer":
            expected_documents = [
                {
                    "source_type": "requirement_evidence",
                    "source_id": f"jd-001-req-{index:03d}",
                    "label": f"jd-001-req-{index:03d}",
                    "role": "primary",
                }
            ]
        samples.append(
            {
                "question_id": f"rag-golden-{index:03d}",
                "question": f"Question {index}?",
                "case_type": case_type,
                "expected_documents": expected_documents,
                "golden_answer": "Use cited evidence.",
                "must_cover_points": ["Use cited evidence."],
                "forbidden_claims": ["Invented claim."],
                "answer_policy": "Use only cited artifacts.",
                "metadata": {
                    "bucket": "full_raw_library_text_pdf_image",
                    "jd_count": 27,
                    "input_media_types": ["text"],
                    "candidate_scope": "candidate-profile-global",
                },
            }
        )
    # Keep validator-compatible sample count and case coverage for callers that validate later.
    for index in range(5, 31):
        samples.append(
            {
                "question_id": f"rag-golden-{index:03d}",
                "question": f"Filler question {index}?",
                "case_type": "stale_or_conflicting" if index == 30 else "common_question",
                "expected_documents": [
                    {
                        "source_type": "requirement_evidence",
                        "source_id": f"jd-002-req-{index:03d}",
                        "label": f"jd-002-req-{index:03d}",
                        "role": "primary",
                    }
                ],
                "golden_answer": "Use cited evidence.",
                "must_cover_points": ["Use cited evidence."],
                "forbidden_claims": ["Invented claim."],
                "answer_policy": "Use only cited artifacts.",
                "metadata": {
                    "bucket": "full_raw_library_text_pdf_image",
                    "jd_count": 27,
                    "input_media_types": ["text"],
                    "candidate_scope": "candidate-profile-global",
                },
            }
        )
    return {"schema_version": "rag-golden-v1", "dataset_id": "test", "samples": samples}


def _audit_payload() -> dict[str, object]:
    return {
        "schema_version": "rag-zero-hit-audit-v1",
        "queries": [
            {
                "question_id": "rag-golden-001",
                "case_type": "common_question",
                "root_cause_hint": "expected_document_vocabulary_gap",
                "expected_documents": [
                    {
                        "label": "jd-001-req-014",
                        "matched_chunk_count": 1,
                        "matched_chunks": [
                            {
                                "chunk_id": "sha256-deadbeef",
                                "source_type": "requirement_evidence",
                                "source_id": "jd-001-req-014",
                                "artifact_path": "analyze/requirement_matrix.json",
                                "text_preview": "[Education Roles | Example] Education Roles missing E:/PycharmProjects/jobPilot/fixtures",
                            }
                        ],
                    }
                ],
            },
            {
                "question_id": "rag-golden-002",
                "case_type": "common_question",
                "root_cause_hint": "missing_expected_document_label",
                "expected_documents": [],
            },
            {
                "question_id": "rag-golden-003",
                "case_type": "no_answer",
                "root_cause_hint": "expected_document_vocabulary_gap",
                "expected_documents": [],
            },
            {
                "question_id": "rag-golden-004",
                "case_type": "multi_document",
                "root_cause_hint": "retrieval_ranking_failure",
                "expected_documents": [],
            },
        ],
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_good_run(run_dir: Path, payload: dict[str, object]) -> Path:
    (run_dir / "analyze").mkdir(parents=True)
    samples = payload["samples"]
    requirement_ids = [
        str(document["source_id"])
        for sample in samples  # type: ignore[assignment]
        for document in sample.get("expected_documents", [])
        if document.get("source_type") == "requirement_evidence"
    ]
    _write_json(
        run_dir / "analyze" / "requirement_matrix.json",
        [
            {
                "jd_id": requirement_id.split("-req-", 1)[0],
                "requirement_id": requirement_id,
                "tier": "high_priority",
                "requirement_text": f"Build verified retrieval evidence for {requirement_id}",
                "evidence_status": "verified",
                "evidence_refs": [f"Built verified retrieval evidence for {requirement_id}."],
            }
            for requirement_id in requirement_ids
        ],
    )
    return run_dir


def _write_bad_run(run_dir: Path) -> None:
    (run_dir / "analyze").mkdir(parents=True)
    _write_json(
        run_dir / "analyze" / "requirement_matrix.json",
        [
            {
                "jd_id": "jd-001",
                "requirement_id": "jd-001-req-001",
                "tier": "high_priority",
                "requirement_text": "Responsibilities:",
                "evidence_status": "verified",
                "evidence_refs": ["Source: fixtures/candidates/base_resume.md"],
            }
        ],
    )
