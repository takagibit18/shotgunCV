from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_golden_rag_zero_hits import audit_zero_hit_queries


def test_audit_zero_hit_queries_reports_expected_document_vocabulary_gap(tmp_path: Path) -> None:
    golden_path = tmp_path / "golden.json"
    payload = _golden_payload()
    _write_json(golden_path, payload)
    run_dir = _write_run(tmp_path / "run")
    report_path = tmp_path / "retriever.json"
    _write_json(
        report_path,
        {
            "schema_version": "rag-retriever-layer-metrics-v1",
            "run_id": "run",
            "metrics": {
                "queries": [
                    {
                        "query_id": "rag-golden-001",
                        "query": "是否有 LangGraph RAG review pipeline 的真实项目证据？",
                        "filter_scope": "single_jd",
                        "filters": {"jd_id": "jd-001"},
                        "expected_chunks": ["jd-001-req-001"],
                        "ranked_ids": ["jd-001-req-002"],
                        "ranked_relevance": [False],
                        "metrics": {"mrr": 0.0},
                        "hits": [
                            {
                                "source_type": "requirement_evidence",
                                "source_id": "jd-001-req-002",
                                "artifact_path": "analyze/requirement_matrix.json",
                                "score": 3.0,
                            }
                        ],
                    },
                    {
                        "query_id": "rag-golden-002",
                        "query": "already solved",
                        "expected_chunks": ["jd-001-req-002"],
                        "metrics": {"mrr": 1.0},
                        "hits": [],
                    },
                ]
            },
        },
    )

    audit = audit_zero_hit_queries(
        run_dir=run_dir,
        golden_file=golden_path,
        retriever_report_file=report_path,
        output_path=tmp_path / "audit.json",
    )

    assert audit["schema_version"] == "rag-zero-hit-audit-v1"
    assert audit["audited_query_count"] == 1
    assert audit["root_cause_hint_counts"] == {"expected_document_vocabulary_gap": 1}
    item = audit["queries"][0]
    assert item["question_id"] == "rag-golden-001"
    assert item["root_cause_hint"] == "expected_document_vocabulary_gap"
    assert item["expected_labels"] == ["jd-001-req-001"]
    assert item["expected_documents"][0]["matched_chunk_count"] == 1
    assert "Education Roles" in item["expected_documents"][0]["matched_chunks"][0]["text_preview"]
    assert item["token_overlap"]["query_expected_overlap_tokens"] == []
    assert "langgraph" in item["token_overlap"]["missing_query_tokens_in_expected_documents"]
    assert audit["queries"][0]["top_hits"][0]["source_id"] == "jd-001-req-002"
    assert item["retrieval_diagnostics"] == {
        "filter_scope": "single_jd",
        "filters": {"jd_id": "jd-001"},
        "first_relevant_rank": None,
        "top_hit_matches_expected": False,
        "expected_label_count": 1,
        "hit_label_count": 0,
        "missing_labels": ["jd-001-req-001"],
        "expected_role_counts": {"primary": 1},
        "hit_role_counts": {},
    }


def test_audit_zero_hit_queries_reports_missing_expected_label(tmp_path: Path) -> None:
    golden_path = tmp_path / "golden.json"
    payload = _golden_payload()
    payload["samples"][0]["expected_documents"] = [
        {
            "source_type": "requirement_evidence",
            "source_id": "jd-999-req-001",
            "label": "jd-999-req-001",
            "role": "primary",
        }
    ]
    _write_json(golden_path, payload)
    run_dir = _write_run(tmp_path / "run")
    report_path = tmp_path / "retriever.json"
    _write_json(
        report_path,
        {
            "schema_version": "rag-retriever-layer-metrics-v1",
            "metrics": {
                "queries": [
                    {
                        "query_id": "rag-golden-001",
                        "query": "missing label",
                        "expected_chunks": ["jd-999-req-001"],
                        "metrics": {"mrr": 0.0},
                        "hits": [],
                    }
                ]
            },
        },
    )

    audit = audit_zero_hit_queries(
        run_dir=run_dir,
        golden_file=golden_path,
        retriever_report_file=report_path,
        output_path=tmp_path / "audit.json",
    )

    assert audit["root_cause_hint_counts"] == {"missing_expected_document_label": 1}
    assert audit["queries"][0]["root_cause_hint"] == "missing_expected_document_label"
    assert audit["queries"][0]["expected_documents"][0]["matched_chunk_count"] == 0


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
                    "source_id": f"jd-001-req-{index:03d}",
                    "label": f"jd-001-req-{index:03d}",
                    "role": "primary",
                }
            ]
        samples.append(
            {
                "question_id": f"rag-golden-{index:03d}",
                "question": f"What evidence supports sample {index}?",
                "case_type": case_type,
                "expected_documents": expected_documents,
                "golden_answer": "Use cited evidence and state uncertainty when evidence is absent.",
                "must_cover_points": ["Use cited evidence.", "State uncertainty when evidence is absent."],
                "forbidden_claims": ["Invented production SLA."],
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
    return {"schema_version": "rag-golden-v1", "dataset_id": "test", "samples": samples}


def _write_run(run_dir: Path) -> Path:
    (run_dir / "ingest").mkdir(parents=True)
    (run_dir / "analyze").mkdir()
    (run_dir / "evaluate").mkdir()
    _write_json(run_dir / "ingest" / "manifest.json", {"candidate_id": "cand-001", "jd_inputs": []})
    _write_json(run_dir / "analyze" / "candidate_profile.json", {"candidate_id": "cand-001"})
    _write_json(
        run_dir / "analyze" / "jd_profiles.json",
        [
            {
                "jd_id": "jd-001",
                "title": "Education Roles",
                "company": "Example",
                "requirements": ["curriculum operations"],
                "must_have_requirements": [],
            }
        ],
    )
    _write_json(
        run_dir / "analyze" / "requirement_matrix.json",
        [
            {
                "jd_id": "jd-001",
                "requirement_id": "jd-001-req-001",
                "requirement_text": "Education Roles",
                "evidence_status": "missing",
                "evidence_refs": [],
            },
            {
                "jd_id": "jd-001",
                "requirement_id": "jd-001-req-002",
                "requirement_text": "LangGraph RAG review pipeline",
                "evidence_status": "verified",
                "evidence_refs": ["Built a retriever evaluation workflow."],
            },
        ],
    )
    _write_json(run_dir / "evaluate" / "gap_maps.json", [])
    return run_dir


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
