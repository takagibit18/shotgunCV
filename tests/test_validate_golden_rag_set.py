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
    assert report["golden_layer_counts"] == {"core_high_info": 30}


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


def test_validate_golden_set_requires_supported_golden_layer(tmp_path: Path) -> None:
    payload = _golden_payload()
    del payload["samples"][0]["metadata"]["golden_layer"]  # type: ignore[index]
    payload["samples"][1]["metadata"]["golden_layer"] = "ocr_mixed_into_core"  # type: ignore[index]
    golden_path = tmp_path / "golden_rag.json"
    _write_json(golden_path, payload)

    report = validate_golden_set(golden_path)

    assert report["status"] == "failed"
    assert "rag-golden-001 metadata missing golden_layer." in report["errors"]
    assert "rag-golden-002 metadata has unsupported golden_layer: ocr_mixed_into_core." in report["errors"]


def test_validate_golden_set_rejects_mojibake_text(tmp_path: Path) -> None:
    payload = _golden_payload()
    payload["samples"][0]["question"] = "杩欎釜鍊欓€変汉鏄惁鏈?LangGraph 鐨勭湡瀹為」鐩瘉鎹紵"
    golden_path = tmp_path / "golden_rag.json"
    _write_json(golden_path, payload)

    report = validate_golden_set(golden_path)

    assert report["status"] == "failed"
    assert any("rag-golden-001 question contains mojibake" in error for error in report["errors"])


def test_validate_golden_set_rejects_bad_requirement_artifacts(tmp_path: Path) -> None:
    payload = _golden_payload()
    payload["samples"][0]["expected_documents"] = [
        {
            "source_type": "requirement_evidence",
            "source_id": "jd-026-req-001",
            "label": "jd-026-req-001",
            "role": "primary",
        }
    ]
    golden_path = tmp_path / "golden_rag.json"
    _write_json(golden_path, payload)
    run_dir = tmp_path / "run"
    _write_bad_run(run_dir)

    report = validate_golden_set(golden_path, run_dir=run_dir)

    assert report["status"] == "failed"
    assert any("jd-026-req-001 has low-quality requirement_text" in error for error in report["errors"])
    assert any("jd-026-req-001 has invalid evidence_refs" in error for error in report["errors"])
    assert any("jd-026-req-001 has duplicate evidence_refs" in error for error in report["errors"])


def test_validate_golden_set_rejects_broad_jd_level_expected_labels(tmp_path: Path) -> None:
    payload = _golden_payload()
    payload["samples"][0]["expected_documents"] = [
        {
            "source_type": "jd_description",
            "source_id": "jd-021",
            "label": "jd-021",
            "role": "primary",
        }
    ]
    golden_path = tmp_path / "golden_rag.json"
    _write_json(golden_path, payload)

    report = validate_golden_set(golden_path)

    assert report["status"] == "failed"
    assert any("uses broad JD-level label jd-021" in error for error in report["errors"])


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
                    "golden_layer": "core_high_info",
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


def _write_bad_run(run_dir: Path) -> None:
    (run_dir / "analyze").mkdir(parents=True)
    _write_json(
        run_dir / "analyze" / "requirement_matrix.json",
        [
            {
                "jd_id": "jd-026",
                "requirement_id": "jd-026-req-001",
                "tier": "high_priority",
                "requirement_text": "Responsibilities:",
                "evidence_status": "verified",
                "evidence_refs": [
                    "Source: E:/PycharmProjects/jobPilot/fixtures/candidates/base_resume.md",
                    "Source: E:/PycharmProjects/jobPilot/fixtures/candidates/base_resume.md",
                ],
            }
        ],
    )
