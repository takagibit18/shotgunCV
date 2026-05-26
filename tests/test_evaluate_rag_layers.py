from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from scripts.evaluate_rag_layers import evaluate_generator_layer, evaluate_retriever_layer


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
    )

    assert report["schema_version"] == "rag-retriever-layer-metrics-v1"
    assert report["quality_gate"]["status"] == "passed"
    assert report["sample_count"] == 30
    assert report["answerable_sample_count"] == 25
    assert report["no_answer_behavior"]["query_count"] == 5
    assert set(report["case_type_metrics"]) == {"common_question", "multi_document", "stale_or_conflicting"}


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
    assert report["aggregate"]["forbidden_claim_violation_count"] == 0
    assert report["aggregate"]["faithfulness"] > 0.9
    assert set(report["case_type_metrics"]) == {"common_question", "multi_document", "no_answer", "stale_or_conflicting"}


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
