from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from scripts.evaluate_rag_layers import (
    _sample_to_query_spec,
    evaluate_generator_layer,
    evaluate_retriever_layer,
    prepare_query_specs,
    report_case_type_counts,
    report_layer_counts,
)


def test_evaluate_retriever_layer_uses_rag_golden_schema(tmp_path: Path) -> None:
    golden_path = tmp_path / "golden.json"
    payload = _golden_payload()
    _write_json(golden_path, payload)
    run_dir = _write_run_with_expected_documents(tmp_path / "run", payload)

    report = evaluate_retriever_layer(
        run_dir=run_dir,
        golden_file=golden_path,
        output_path=tmp_path / "retriever.json",
        k_values=[1, 3],
        embedding_model=_KeywordEmbeddingModel(),
        reranker_model=None,
    )

    assert report["schema_version"] == "rag-retriever-layer-metrics-v1"
    assert report["quality_gate"]["status"] == "passed"
    assert report["sample_count"] == 30
    assert report["answerable_sample_count"] == 25
    assert report["no_answer_behavior"]["query_count"] == 5
    assert report["no_answer_behavior"]["quality_gate"]["status"] == "passed"
    assert report["no_answer_behavior"]["score_threshold"] == 0.8
    assert report["no_answer_behavior"]["abstention_rate"] == 1.0
    assert report["golden_layer_metrics"]["core_high_info"]["query_count"] == 25
    assert report["golden_layer_metrics"]["core_high_info"]["aggregate"]["mrr"] == report["metrics"]["aggregate"]["mrr"]
    assert report["golden_layer_metrics"]["core_high_info"]["aggregate"]["weighted_recall_at_k"]["3"] == (
        report["metrics"]["aggregate"]["weighted_recall_at_k"]["3"]
    )
    assert report["golden_layer_metrics"]["core_high_info"]["aggregate"]["all_primary_hit_rate"] == (
        report["metrics"]["aggregate"]["all_primary_hit_rate"]
    )
    assert all(item["abstained"] for item in report["no_answer_behavior"]["queries"])
    assert all(item["effective_result_count"] == 0 for item in report["no_answer_behavior"]["queries"])
    assert {item["filter_scope"] for item in report["no_answer_behavior"]["queries"]} == {"candidate_evidence"}
    assert set(report["case_type_metrics"]) == {"common_question", "multi_document", "stale_or_conflicting"}


def test_real_cv_v2_golden_fixture_is_sixty_sample_layered_report() -> None:
    payload = json.loads(Path("fixtures/golden_rag_questions.json").read_text(encoding="utf-8"))
    samples = payload["samples"]

    assert payload["dataset_id"] == "rag-golden-v2-20260602-real-cv"
    assert len(samples) == 60
    assert report_layer_counts(samples) == {
        "core_high_info": 38,
        "low_info_stress": 6,
        "non_target_negative": 9,
        "ocr_regression": 7,
    }
    assert report_case_type_counts(samples) == {
        "common_question": 34,
        "multi_document": 11,
        "no_answer": 9,
        "stale_or_conflicting": 6,
    }


def test_evaluate_retriever_layer_fails_no_answer_gate_when_score_crosses_threshold(tmp_path: Path) -> None:
    golden_path = tmp_path / "golden.json"
    payload = _golden_payload()
    _write_json(golden_path, payload)
    run_dir = _write_run_with_expected_documents(tmp_path / "run", payload)

    report = evaluate_retriever_layer(
        run_dir=run_dir,
        golden_file=golden_path,
        output_path=tmp_path / "retriever.json",
        k_values=[1, 3],
        embedding_model=_KeywordEmbeddingModel(),
        no_answer_score_threshold=0.1,
        reranker_model=None,
    )

    gate = report["no_answer_behavior"]["quality_gate"]
    assert gate["status"] == "failed"
    assert gate["blocks_generator"] is True
    assert report["no_answer_behavior"]["abstention_rate"] == 0.0
    assert all(not item["abstained"] for item in report["no_answer_behavior"]["queries"])
    assert report["no_answer_behavior"]["false_positive_audit"]["false_positive_count"] == 5
    assert report["no_answer_behavior"]["false_positive_audit"]["needs_manual_audit"] is True
    assert report["no_answer_behavior"]["false_positive_audit"]["top_false_positive_examples"][0]["gate_status"] == "needs_review"


def test_evaluate_retriever_layer_can_select_hybrid_retriever(tmp_path: Path) -> None:
    golden_path = tmp_path / "golden.json"
    payload = _golden_payload()
    _write_json(golden_path, payload)
    run_dir = _write_run_with_expected_documents(tmp_path / "run", payload)

    report = evaluate_retriever_layer(
        run_dir=run_dir,
        golden_file=golden_path,
        output_path=tmp_path / "retriever.json",
        k_values=[1, 3],
        embedding_model=_KeywordEmbeddingModel(),
        retriever_mode="hybrid",
        reranker_model=None,
    )

    assert report["retriever_mode"] == "hybrid"
    assert report["retriever_type"] == "InMemoryHybridRetriever"
    assert report["metrics"]["query_count"] == 25


def test_evaluate_retriever_layer_wraps_smart_router_with_reranker(tmp_path: Path, monkeypatch) -> None:
    from shotguncv_core.rag import reranking

    class FakeReranker:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def rerank(self, query: str, results: list[object], *, top_k: int) -> list[object]:
            return results[:top_k]

    monkeypatch.setattr(reranking, "CrossEncoderReranker", FakeReranker)
    golden_path = tmp_path / "golden.json"
    payload = _golden_payload()
    _write_json(golden_path, payload)
    run_dir = _write_run_with_expected_documents(tmp_path / "run", payload)

    report = evaluate_retriever_layer(
        run_dir=run_dir,
        golden_file=golden_path,
        output_path=tmp_path / "retriever.json",
        k_values=[1, 3],
        embedding_model=_KeywordEmbeddingModel(),
        retriever_mode="hybrid",
        query_strategy="smart",
        reranker_model="fake-reranker",
        first_stage_limit=7,
    )

    assert report["query_strategy"] == "smart"
    assert report["reranker_model"] == "fake-reranker"
    assert report["first_stage_limit"] == 7
    assert "SmartRouterRetriever" in report["retriever_type"]
    assert "fake-reranker" in report["retriever_type"]
    assert any("query_plan" in item for item in report["metrics"]["queries"])


def test_evaluate_retriever_layer_enables_default_reranker(tmp_path: Path, monkeypatch) -> None:
    from scripts import evaluate_rag_layers
    from shotguncv_core.rag import reranking

    class FakeReranker:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def rerank(self, query: str, results: list[object], *, top_k: int) -> list[object]:
            return results[:top_k]

    monkeypatch.setattr(reranking, "CrossEncoderReranker", FakeReranker)
    golden_path = tmp_path / "golden.json"
    payload = _golden_payload()
    _write_json(golden_path, payload)
    run_dir = _write_run_with_expected_documents(tmp_path / "run", payload)

    report = evaluate_retriever_layer(
        run_dir=run_dir,
        golden_file=golden_path,
        output_path=tmp_path / "retriever.json",
        k_values=[1, 3],
        embedding_model=_KeywordEmbeddingModel(),
    )

    assert report["reranker_model"] == evaluate_rag_layers.DEFAULT_RERANKER_MODEL
    assert report["first_stage_limit"] == evaluate_rag_layers.DEFAULT_FIRST_STAGE_LIMIT
    assert evaluate_rag_layers.DEFAULT_RERANKER_MODEL in report["retriever_type"]


def test_evaluate_retriever_layer_can_filter_headline_golden_layer(tmp_path: Path) -> None:
    golden_path = tmp_path / "golden.json"
    payload = _golden_payload()
    for sample in payload["samples"][0:10]:  # type: ignore[index]
        sample["metadata"]["golden_layer"] = "low_info_stress"
    _write_json(golden_path, payload)
    run_dir = _write_run_with_expected_documents(tmp_path / "run", payload)

    report = evaluate_retriever_layer(
        run_dir=run_dir,
        golden_file=golden_path,
        output_path=tmp_path / "retriever.json",
        k_values=[1, 3],
        embedding_model=_KeywordEmbeddingModel(),
        golden_layers=["core_high_info"],
        reranker_model=None,
    )

    assert report["golden_layer_filter"] == ["core_high_info"]
    assert report["sample_count"] == 20
    assert report["answerable_sample_count"] == 15
    assert set(report["golden_layer_metrics"]) == {"core_high_info"}
    assert all(query["query_id"] >= "rag-golden-011" for query in report["metrics"]["queries"])


def test_sample_to_query_spec_does_not_apply_jd_filter_to_mixed_scope_docs() -> None:
    spec = _sample_to_query_spec(
        {
            "question_id": "rag-golden-027",
            "question": "What candidate profile and JD evidence support this fit?",
            "case_type": "multi_document",
            "expected_documents": [
                {
                    "source_type": "candidate_evidence",
                    "source_id": "cand-001:candidate-profile",
                    "label": "candidate-profile",
                    "role": "primary",
                },
                {
                    "source_type": "requirement_evidence",
                    "source_id": "jd-005-req-013",
                    "label": "jd-005-req-013",
                    "role": "supporting",
                },
            ],
        }
    )

    assert "jd_id" not in spec
    assert "source_type" not in spec
    assert spec["filter_scope"] == "mixed_scope"
    assert spec["filters"] == {}


def test_sample_to_query_spec_applies_jd_filter_only_for_single_jd_docs() -> None:
    spec = _sample_to_query_spec(
        {
            "question_id": "rag-golden-001",
            "question": "What evidence supports the JD requirements?",
            "case_type": "multi_document",
            "expected_documents": [
                {
                    "source_type": "requirement_evidence",
                    "source_id": "jd-001-req-001",
                    "label": "jd-001-req-001",
                    "role": "primary",
                },
                {
                    "source_type": "requirement_evidence",
                    "source_id": "jd-001-req-002",
                    "label": "jd-001-req-002",
                    "role": "supporting",
                },
            ],
        }
    )

    assert spec["jd_id"] == "jd-001"
    assert spec["source_type"] == "requirement_evidence"
    assert spec["filter_scope"] == "single_jd"
    assert spec["filters"] == {"jd_id": "jd-001", "source_type": "requirement_evidence"}


def test_sample_to_query_spec_applies_source_type_filter_for_global_same_type_docs() -> None:
    spec = _sample_to_query_spec(
        {
            "question_id": "rag-golden-global",
            "question": "What candidate evidence supports this profile?",
            "case_type": "multi_document",
            "expected_documents": [
                {
                    "source_type": "candidate_evidence",
                    "source_id": "cand-001:candidate-profile",
                    "label": "candidate-profile",
                    "role": "primary",
                },
                {
                    "source_type": "candidate_evidence",
                    "source_id": "cand-001:candidate-summary",
                    "label": "candidate-summary",
                    "role": "supporting",
                },
            ],
        }
    )

    assert "jd_id" not in spec
    assert spec["source_type"] == "candidate_evidence"
    assert spec["filter_scope"] == "single_source_type"
    assert spec["filters"] == {"source_type": "candidate_evidence"}


def test_prepare_query_specs_adds_decomposition_for_multi_document_and_cross_section() -> None:
    samples = [
        {
            "question_id": "rag-golden-cross-section",
            "question": "How do education, project evidence, and ranking risks fit together?",
            "case_type": "multi_document",
            "expected_documents": [
                {
                    "source_type": "candidate_evidence",
                    "source_id": "cand-001:candidate-profile",
                    "label": "candidate-profile",
                    "role": "primary",
                },
                {
                    "source_type": "requirement_evidence",
                    "source_id": "jd-005-req-013",
                    "label": "jd-005-req-013",
                    "role": "supporting",
                },
                {
                    "source_type": "ranking_explanation",
                    "source_id": "jd-005:ranking",
                    "label": "jd-005:ranking",
                    "role": "conflicting",
                },
            ],
            "metadata": {"golden_layer": "core_high_info", "robustness_category": "cross_section"},
        }
    ]

    specs = prepare_query_specs(samples, query_strategy="decomposed")

    spec = specs[0]
    assert spec["filter_scope"] == "mixed_scope"
    assert spec["query_decomposition"]["strategy"] == "primary_then_related"
    stages = spec["query_decomposition"]["stages"]
    assert [stage["name"] for stage in stages] == ["primary", "supporting", "conflicting"]
    assert stages[0]["filters"] == {"source_type": "candidate_evidence"}
    assert stages[1]["filters"] == {"jd_id": "jd-005", "source_type": "requirement_evidence"}
    assert stages[2]["filters"] == {"jd_id": "jd-005", "source_type": "ranking_explanation"}
    assert "primary evidence" in stages[0]["query"]
    assert "ranking decision risk" in stages[2]["query"]


def test_prepare_query_specs_rewrites_weak_ocr_queries() -> None:
    specs = prepare_query_specs(
        [
            {
                "question_id": "rag-golden-ocr",
                "question": "这个图片岗位是不是更像开发者工具和 AI 工作流方向？",
                "case_type": "common_question",
                "expected_documents": [
                    {"source_type": "requirement_evidence", "source_id": "jd-025-req-001", "label": "jd-025-req-001", "role": "primary"}
                ],
                "metadata": {"golden_layer": "ocr_regression", "robustness_category": "ocr_weak_keyword"},
            }
        ],
        query_strategy="single",
    )

    spec = specs[0]
    assert spec["query_rewrite"]["strategy"] == "ocr_alias"
    assert "developer tools" in spec["expanded_query"]
    assert "workflow" in spec["expanded_query"]
    assert "ocr noise" in spec["expanded_query"]


def test_evaluate_generator_layer_scores_answers_against_golden_set(tmp_path: Path) -> None:
    golden_path = tmp_path / "golden.json"
    payload = _golden_payload()
    _write_json(golden_path, payload)
    answers_path = tmp_path / "answers.json"
    _write_json(answers_path, _answers_payload(payload))
    run_dir = _write_run_with_expected_documents(tmp_path / "run", payload)

    report = evaluate_generator_layer(
        golden_file=golden_path,
        answers_file=answers_path,
        output_path=tmp_path / "generator.json",
        run_dir=run_dir,
    )

    assert report["schema_version"] == "rag-generator-layer-metrics-v1"
    assert report["sample_count"] == 30
    assert report["answered_sample_count"] == 30
    assert report["golden_layer_metrics"]["core_high_info"]["sample_count"] == 30
    assert report["golden_layer_metrics"]["core_high_info"]["aggregate"] == report["aggregate"]
    assert report["aggregate"]["forbidden_claim_violation_count"] == 0
    assert report["aggregate"]["faithfulness"] > 0.9
    assert set(report["case_type_metrics"]) == {"common_question", "multi_document", "no_answer", "stale_or_conflicting"}


def test_evaluate_generator_layer_can_filter_headline_golden_layer(tmp_path: Path) -> None:
    golden_path = tmp_path / "golden.json"
    payload = _golden_payload()
    for sample in payload["samples"][0:10]:  # type: ignore[index]
        sample["metadata"]["golden_layer"] = "low_info_stress"
    _write_json(golden_path, payload)
    answers_path = tmp_path / "answers.json"
    _write_json(answers_path, _answers_payload(payload))
    run_dir = _write_run_with_expected_documents(tmp_path / "run", payload)

    report = evaluate_generator_layer(
        golden_file=golden_path,
        answers_file=answers_path,
        output_path=tmp_path / "generator.json",
        run_dir=run_dir,
        golden_layers=["core_high_info"],
    )

    assert report["golden_layer_filter"] == ["core_high_info"]
    assert report["sample_count"] == 20
    assert set(report["golden_layer_metrics"]) == {"core_high_info"}
    assert all(sample["question_id"] >= "rag-golden-011" for sample in report["samples"])


def test_evaluate_generator_layer_blocks_no_answer_when_retriever_abstained(tmp_path: Path) -> None:
    golden_path = tmp_path / "golden.json"
    payload = _golden_payload()
    _write_json(golden_path, payload)
    answers_path = tmp_path / "answers.json"
    answers = _answers_payload(payload)
    for answer in answers["answers"]:  # type: ignore[index]
        if answer["question_id"] == "rag-golden-021":
            answer["answer"] = "Invented production SLA with confident unsupported details."
            answer["citations"] = [{"source_id": "unrelated"}]
    _write_json(answers_path, answers)
    retriever_report_path = tmp_path / "retriever.json"
    _write_json(
        retriever_report_path,
        {
            "schema_version": "rag-retriever-layer-metrics-v1",
            "no_answer_behavior": {
                "quality_gate": {"status": "passed", "non_abstained_count": 0},
                "queries": [
                    {
                        "question_id": "rag-golden-021",
                        "abstained": True,
                        "effective_result_count": 0,
                        "gate_status": "abstained",
                    }
                ],
            },
        },
    )

    report = evaluate_generator_layer(
        golden_file=golden_path,
        answers_file=answers_path,
        output_path=tmp_path / "generator.json",
        retriever_report_file=retriever_report_path,
    )

    blocked = next(item for item in report["samples"] if item["question_id"] == "rag-golden-021")
    assert blocked["blocked_by_retriever_gate"] is True
    assert blocked["answer_chars"] == 0
    assert blocked["faithfulness"] == 1.0
    assert blocked["answer_relevance"] == 1.0
    assert report["retriever_gate"]["blocked_no_answer_count"] == 1


class _KeywordEmbeddingModel:
    def embed(self, text: str) -> list[float]:
        dimensions = 64
        vector = [0.0] * dimensions
        for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            vector[int.from_bytes(digest[:2], "big") % dimensions] += 1.0
        magnitude = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / magnitude for value in vector]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


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
            if case_type in {"multi_document", "stale_or_conflicting"}:
                expected_documents.append(
                    {
                        "source_type": "gap_map",
                        "source_id": "jd-001:gap-map",
                        "label": "jd-001:gap-map",
                        "role": "supporting",
                    }
                )
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


def _answers_payload(payload: dict[str, object]) -> dict[str, object]:
    answers = []
    for sample in payload["samples"]:  # type: ignore[index]
        expected_documents = sample["expected_documents"]  # type: ignore[index]
        citations = []
        if expected_documents:
            first = expected_documents[0]
            citations = [{"source_id": first["source_id"], "label": first["label"]}]
        answers.append(
            {
                "question_id": sample["question_id"],  # type: ignore[index]
                "answer": "Use cited evidence. State uncertainty when evidence is absent.",
                "citations": citations,
            }
        )
    return {"schema_version": "rag-generator-answers-v1", "answers": answers}


def _write_run_with_expected_documents(run_dir: Path, payload: dict[str, object]) -> Path:
    (run_dir / "ingest").mkdir(parents=True)
    (run_dir / "analyze").mkdir()
    (run_dir / "evaluate").mkdir()
    _write_json(run_dir / "ingest" / "manifest.json", {"candidate_id": "cand-001", "jd_inputs": []})
    _write_json(
        run_dir / "analyze" / "candidate_profile.json",
        {"candidate_id": "cand-001", "core_claims": ["Use cited evidence for sample questions."]},
    )
    _write_json(
        run_dir / "analyze" / "jd_profiles.json",
        [
            {
                "jd_id": "jd-001",
                "title": "Layered RAG Evaluator",
                "company": "Example",
                "requirements": ["retriever", "generator"],
                "must_have_requirements": ["evaluation"],
            }
        ],
    )
    requirement_ids = sorted(
        {
            document["source_id"]
            for sample in payload["samples"]  # type: ignore[index]
            for document in sample["expected_documents"]  # type: ignore[index]
            if document["source_type"] == "requirement_evidence"
        }
    )
    _write_json(
        run_dir / "analyze" / "requirement_matrix.json",
        [
            {
                "jd_id": "jd-001",
                "requirement_id": requirement_id,
                "requirement_text": f"Evidence for {requirement_id}",
                "evidence_status": "verified",
                "evidence_refs": [f"Use cited evidence for {requirement_id}."],
            }
            for requirement_id in requirement_ids
        ],
    )
    _write_json(
        run_dir / "evaluate" / "gap_maps.json",
        [
            {
                "jd_id": "jd-001",
                "items": [
                    {
                        "gap": "jd-001:gap-map",
                        "risk": "State uncertainty when evidence is absent.",
                    }
                ],
            }
        ],
    )
    return run_dir


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
