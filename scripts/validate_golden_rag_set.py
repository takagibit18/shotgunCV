from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "rag-golden-v1"
REQUIRED_CASE_TYPES = {"common_question", "multi_document", "no_answer", "stale_or_conflicting"}
REQUIRED_SAMPLE_FIELDS = {
    "question_id",
    "question",
    "case_type",
    "expected_documents",
    "golden_answer",
    "must_cover_points",
    "forbidden_claims",
    "answer_policy",
    "metadata",
}


def validate_golden_set(golden_file: Path) -> dict[str, Any]:
    payload = json.loads(golden_file.read_text(encoding="utf-8"))
    errors: list[str] = []
    if not isinstance(payload, dict):
        return _report(errors=["Golden set must be a JSON object."])
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != SCHEMA_VERSION:
        errors.append(f"Unsupported schema_version: {schema_version or '<missing>'}.")
    samples = payload.get("samples")
    if not isinstance(samples, list):
        errors.append("Golden set requires a samples list.")
        samples = []
    if not 30 <= len(samples) <= 50:
        errors.append("Golden set must contain 30-50 samples.")

    question_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    case_type_counts: Counter[str] = Counter()
    source_type_counts: Counter[str] = Counter()
    retriever_labels: set[str] = set()
    for index, sample in enumerate(samples, start=1):
        if not isinstance(sample, dict):
            errors.append(f"Sample #{index} must be an object.")
            continue
        question_id = str(sample.get("question_id") or "").strip()
        if question_id in question_ids:
            duplicate_ids.add(question_id)
        if question_id:
            question_ids.add(question_id)
        _validate_sample(sample, index, errors)
        case_type = str(sample.get("case_type") or "")
        if case_type:
            case_type_counts[case_type] += 1
        for document in sample.get("expected_documents") or []:
            if not isinstance(document, dict):
                continue
            source_type = str(document.get("source_type") or "").strip()
            if source_type:
                source_type_counts[source_type] += 1
            label = _document_label(document)
            if label:
                retriever_labels.add(label)
    for question_id in sorted(duplicate_ids):
        errors.append(f"Duplicate question_id: {question_id}.")
    missing_case_types = sorted(REQUIRED_CASE_TYPES - set(case_type_counts))
    if missing_case_types:
        errors.append(f"Missing required case_type coverage: {', '.join(missing_case_types)}.")
    return _report(
        schema_version=schema_version,
        sample_count=len(samples),
        case_type_counts=dict(sorted(case_type_counts.items())),
        source_type_counts=dict(sorted(source_type_counts.items())),
        retriever_label_count=len(retriever_labels),
        errors=errors,
    )


def _validate_sample(sample: dict[str, Any], index: int, errors: list[str]) -> None:
    question_id = str(sample.get("question_id") or f"sample #{index}").strip()
    missing = sorted(field for field in REQUIRED_SAMPLE_FIELDS if field not in sample)
    if missing:
        errors.append(f"{question_id} missing required fields: {', '.join(missing)}.")
    for field in ["question_id", "question", "case_type", "golden_answer", "answer_policy"]:
        if not isinstance(sample.get(field), str) or not str(sample.get(field) or "").strip():
            errors.append(f"{question_id} requires a non-empty {field}.")
    case_type = str(sample.get("case_type") or "")
    if case_type and case_type not in REQUIRED_CASE_TYPES:
        errors.append(f"{question_id} has unsupported case_type: {case_type}.")
    expected_documents = sample.get("expected_documents")
    if not isinstance(expected_documents, list):
        errors.append(f"{question_id} expected_documents must be a list.")
        expected_documents = []
    if case_type == "no_answer" and expected_documents:
        errors.append(f"{question_id} no_answer samples must not include expected_documents.")
    if case_type != "no_answer" and not expected_documents:
        errors.append(f"{question_id} answerable samples require expected_documents.")
    for document_index, document in enumerate(expected_documents, start=1):
        _validate_document(question_id, document_index, document, errors)
    for field in ["must_cover_points", "forbidden_claims"]:
        value = sample.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
            errors.append(f"{question_id} requires a non-empty string list for {field}.")
    metadata = sample.get("metadata")
    if not isinstance(metadata, dict):
        errors.append(f"{question_id} metadata must be an object.")
    else:
        for field in ["bucket", "jd_count", "input_media_types", "candidate_scope"]:
            if field not in metadata:
                errors.append(f"{question_id} metadata missing {field}.")


def _validate_document(question_id: str, document_index: int, document: Any, errors: list[str]) -> None:
    if not isinstance(document, dict):
        errors.append(f"{question_id} expected_documents[{document_index}] must be an object.")
        return
    source_type = str(document.get("source_type") or "").strip()
    if not source_type:
        errors.append(f"{question_id} expected_documents[{document_index}] requires source_type.")
    if not _document_label(document):
        errors.append(f"{question_id} expected_documents[{document_index}] requires label, source_id, or chunk_id.")
    role = str(document.get("role") or "primary")
    if role not in {"primary", "supporting", "stale", "conflicting"}:
        errors.append(f"{question_id} expected_documents[{document_index}] has unsupported role: {role}.")


def _document_label(document: dict[str, Any]) -> str:
    for field in ["label", "source_id", "chunk_id"]:
        value = str(document.get(field) or "").strip()
        if value:
            return value
    return ""


def _report(
    *,
    schema_version: str = "",
    sample_count: int = 0,
    case_type_counts: dict[str, int] | None = None,
    source_type_counts: dict[str, int] | None = None,
    retriever_label_count: int = 0,
    errors: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "sample_count": sample_count,
        "status": "failed" if errors else "passed",
        "errors": errors,
        "case_type_counts": case_type_counts or {},
        "source_type_counts": source_type_counts or {},
        "retriever_label_count": retriever_label_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a rag-golden-v1 manual golden set.")
    parser.add_argument("golden_file", type=Path)
    args = parser.parse_args()
    report = validate_golden_set(args.golden_file)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
