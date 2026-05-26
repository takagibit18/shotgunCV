from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_golden_rag_set import validate_golden_set


def test_validate_golden_set_accepts_complete_rag_schema(tmp_path: Path) -> None:
    golden_path = tmp_path / "golden_rag.json"
    _write_json(golden_path, _golden_payload())

    report = validate_golden_set(golden_path)

    assert report["schema_version"] == "rag-golden-v1"
    assert report["sample_count"] == 30
    assert report["status"] == "passed"
    assert report["case_type_counts"] == {
        "common_question": 12,
        "multi_document": 8,
        "no_answer": 5,
        "stale_or_conflicting": 5,
    }
    assert report["source_type_counts"]["requirement_evidence"] == 25
    assert report["retriever_label_count"] == 38


def test_validate_golden_set_rejects_incomplete_distribution(tmp_path: Path) -> None:
    payload = _golden_payload()
    payload["samples"] = payload["samples"][:29]
    golden_path = tmp_path / "golden_rag.json"
    _write_json(golden_path, payload)

    report = validate_golden_set(golden_path)

    assert report["status"] == "failed"
    assert "Golden set must contain 30-50 samples." in report["errors"]


def test_validate_golden_set_rejects_invalid_no_answer_docs(tmp_path: Path) -> None:
    payload = _golden_payload()
    payload["samples"][20]["expected_documents"] = [
        {"source_type": "candidate_evidence", "label": "candidate-profile", "role": "primary"}
    ]
    golden_path = tmp_path / "golden_rag.json"
    _write_json(golden_path, payload)

    report = validate_golden_set(golden_path)

    assert report["status"] == "failed"
    assert "rag-golden-021 no_answer samples must not include expected_documents." in report["errors"]


def _golden_payload() -> dict[str, object]:
    samples = []
    case_types = (
        ["common_question"] * 12
        + ["multi_document"] * 8
        + ["no_answer"] * 5
        + ["stale_or_conflicting"] * 5
    )
    for index, case_type in enumerate(case_types, start=1):
        expected_documents = []
        if case_type != "no_answer":
            expected_documents = [
                {
                    "source_type": "requirement_evidence",
                    "source_id": f"jd-{index:03d}-req-001",
                    "label": f"jd-{index:03d}-req-001",
                    "role": "primary",
                }
            ]
            if case_type in {"multi_document", "stale_or_conflicting"}:
                expected_documents.append(
                    {
                        "source_type": "gap_map",
                        "source_id": f"jd-{index:03d}:gap-map",
                        "label": f"jd-{index:03d}:gap-map",
                        "role": "supporting",
                    }
                )
        samples.append(
            {
                "question_id": f"rag-golden-{index:03d}",
                "question": f"What evidence supports sample {index}?",
                "case_type": case_type,
                "expected_documents": expected_documents,
                "golden_answer": "Answer from current artifacts only.",
                "must_cover_points": ["Use cited evidence.", "State uncertainty when evidence is absent."],
                "forbidden_claims": ["Do not invent missing employer outcomes."],
                "answer_policy": "Use only cited run artifacts; say the current knowledge base cannot confirm when evidence is absent.",
                "metadata": {
                    "bucket": "full_raw_library_text_pdf_image",
                    "jd_count": 27,
                    "input_media_types": ["text", "pdf", "image"],
                    "candidate_scope": "candidate-profile-global",
                },
            }
        )
    return {
        "schema_version": "rag-golden-v1",
        "dataset_id": "rag-golden-v1-20260526",
        "samples": samples,
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
