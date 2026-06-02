from __future__ import annotations

import argparse
import json
import re
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
_MOJIBAKE_MARKERS = ("锛", "鏄", "鐨", "杩", "妫", "绱", "€", "�")
_CONTENT_TOKEN_RE = re.compile(r"[a-z][a-z0-9+#.-]*|[0-9]+|[\u4e00-\u9fff]{2,}", re.IGNORECASE)
_JD_LEVEL_LABEL_RE = re.compile(r"^jd-\d{3}$", re.IGNORECASE)
_GENERIC_TOKENS = {
    "build",
    "built",
    "candidate",
    "experience",
    "project",
    "requirements",
    "responsibilities",
    "role",
    "skills",
    "source",
    "with",
    "工作",
    "岗位",
    "职责",
    "要求",
    "相关",
    "能力",
    "经验",
    "负责",
}


def validate_golden_set(golden_file: Path, *, run_dir: Path | None = None) -> dict[str, Any]:
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
    if run_dir is not None:
        _validate_expected_artifacts(samples, run_dir, errors)
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
    for field in ["question", "golden_answer", "answer_policy"]:
        _validate_text_quality(question_id, field, str(sample.get(field) or ""), errors)
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
        if isinstance(value, list):
            for item_index, item in enumerate(value, start=1):
                _validate_text_quality(question_id, f"{field}[{item_index}]", str(item), errors)
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
    if _is_broad_jd_level_document(document):
        errors.append(
            f"{question_id} expected_documents[{document_index}] uses broad JD-level label "
            f"{_document_label(document)}; use gap_map, ranking_explanation, or requirement_evidence instead."
        )
    role = str(document.get("role") or "primary")
    if role not in {"primary", "supporting", "stale", "conflicting"}:
        errors.append(f"{question_id} expected_documents[{document_index}] has unsupported role: {role}.")


def _validate_text_quality(question_id: str, field: str, text: str, errors: list[str]) -> None:
    if _looks_like_mojibake(text):
        errors.append(f"{question_id} {field} contains mojibake text.")


def _validate_expected_artifacts(samples: list[Any], run_dir: Path, errors: list[str]) -> None:
    matrix = _load_requirement_matrix(run_dir)
    matrix_by_id = {str(item.get("requirement_id") or ""): item for item in matrix if isinstance(item, dict)}
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        question_id = str(sample.get("question_id") or "<unknown>")
        for document in sample.get("expected_documents") or []:
            if not isinstance(document, dict):
                continue
            source_type = str(document.get("source_type") or "").strip()
            if source_type != "requirement_evidence":
                continue
            label = _document_label(document)
            item = matrix_by_id.get(str(document.get("source_id") or "")) or matrix_by_id.get(label)
            if item is None:
                errors.append(f"{question_id} expected requirement_evidence {label} is missing from run artifact.")
                continue
            _validate_requirement_artifact(label, item, errors)


def _validate_requirement_artifact(label: str, item: dict[str, Any], errors: list[str]) -> None:
    requirement_text = str(item.get("requirement_text") or "")
    evidence_refs = [str(ref) for ref in item.get("evidence_refs", []) if str(ref).strip()]
    invalid_refs = [ref for ref in evidence_refs if _is_invalid_evidence_ref(ref)]
    valid_refs = [ref for ref in evidence_refs if ref not in invalid_refs]
    if _is_low_quality_requirement(requirement_text):
        errors.append(f"{label} has low-quality requirement_text: {requirement_text}")
    if invalid_refs:
        errors.append(f"{label} has invalid evidence_refs: {invalid_refs[:2]}")
    if len(_dedupe_refs(evidence_refs)) != len(evidence_refs):
        errors.append(f"{label} has duplicate evidence_refs.")
    if str(item.get("evidence_status") or "") == "verified" and not valid_refs:
        errors.append(f"{label} is verified without usable evidence_refs.")


def _load_requirement_matrix(run_dir: Path) -> list[Any]:
    path = run_dir / "analyze" / "requirement_matrix.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else []


def _document_label(document: dict[str, Any]) -> str:
    for field in ["label", "source_id", "chunk_id"]:
        value = str(document.get(field) or "").strip()
        if value:
            return value
    return ""


def _is_broad_jd_level_document(document: dict[str, Any]) -> bool:
    source_type = str(document.get("source_type") or "").strip()
    label = _document_label(document)
    source_id = str(document.get("source_id") or "").strip()
    return source_type == "jd_description" and (
        bool(_JD_LEVEL_LABEL_RE.match(label)) or bool(_JD_LEVEL_LABEL_RE.match(source_id))
    )


def _is_low_quality_requirement(text: str) -> bool:
    stripped = text.strip()
    lowered = stripped.lower()
    if not stripped:
        return True
    if _looks_like_label_only(lowered) or _looks_like_mojibake(stripped) or _looks_like_ocr_spaced_cjk(stripped):
        return True
    if _is_invalid_evidence_ref(stripped):
        return True
    tokens = _content_tokens(stripped)
    if len(tokens) < 2 and not _has_hard_gate_keyword(lowered):
        return True
    return False


def _looks_like_label_only(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.strip().strip(":：").lower())
    return normalized in {
        "education",
        "skills",
        "requirements",
        "requirement",
        "responsibilities",
        "responsibility",
        "relevance bucket",
        "source signals",
        "source signal",
        "source",
    }


def _looks_like_mojibake(text: str) -> bool:
    marker_hits = sum(1 for marker in _MOJIBAKE_MARKERS if marker in text)
    replacement_hits = text.count("?") if any(marker in text for marker in _MOJIBAKE_MARKERS[:-1]) else 0
    return marker_hits >= 2 or (marker_hits >= 1 and replacement_hits >= 1)


def _looks_like_ocr_spaced_cjk(text: str) -> bool:
    return bool(re.search(r"(?:[\u4e00-\u9fff]\s+){3,}[\u4e00-\u9fff]", text))


def _has_hard_gate_keyword(text: str) -> bool:
    return any(term in text for term in ["学历", "本科", "硕士", "博士", "bachelor", "master", "phd", "degree"])


def _content_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for raw_token in _CONTENT_TOKEN_RE.findall(text.lower()):
        token = raw_token.strip("-_.[](){}:,;|")
        if not token or token in _GENERIC_TOKENS or len(token) < 2:
            continue
        if token not in seen:
            seen.add(token)
            tokens.append(token)
    return tokens


def _is_invalid_evidence_ref(ref: str) -> bool:
    text = ref.strip().lower()
    if not text:
        return True
    if text.startswith(("source:", "source：", "source path:", "source file:", "file:", "path:")):
        return True
    if re.fullmatch(r"(?:https?://|www\.)\S+", text):
        return True
    if re.search(r"[a-z]:[\\/][^\s]+", text):
        return True
    if re.search(r"(?:^|\s)/(?:users|home|tmp|var|mnt|private_inputs|pycharmprojects)[^\s]*", text):
        return True
    if re.search(r"(?:^|\s)(?:\.{1,2}[\\/])?[\w.-]+(?:[\\/][\w .-]+)+\.(?:md|pdf|docx?|txt|json|png|jpe?g)(?:\s|$)", text):
        return True
    return False


def _dedupe_refs(refs: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        key = re.sub(r"\s+", " ", str(ref)).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(ref)
    return deduped


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
    parser.add_argument("--run-dir", type=Path, default=None, help="Optional source run directory for artifact quality audit.")
    args = parser.parse_args()
    report = validate_golden_set(args.golden_file, run_dir=args.run_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
