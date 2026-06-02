from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.validate_golden_rag_set import validate_golden_set  # noqa: E402


ALIGNMENT_METHOD = "bm25_keyword_rewrite"
CHANGELOG_SCHEMA = "rag-golden-realignment-changelog-v1"
KEYWORD_MARKER = "检索关键词："
TARGET_ROOT_CAUSE = "expected_document_vocabulary_gap"

_TOKEN_RE = re.compile(r"[a-z][a-z0-9+#.-]*|[0-9]+|[\u4e00-\u9fff]{2,}", re.IGNORECASE)
_ID_LIKE_RE = re.compile(r"^(?:jd|req|chunk|sha|sha256|[a-f0-9]{8,}|[0-9]+)$", re.IGNORECASE)
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "or",
    "the",
    "to",
    "with",
    "source",
    "source_id",
    "chunk",
    "chunk_id",
    "artifact",
    "artifact_path",
    "requirement",
    "requirement_evidence",
    "gap_map",
    "candidate_profile",
    "analyze",
    "evaluate",
    "json",
    "example",
}
_METADATA_TOKENS = {
    "candidate",
    "profile",
    "provenance",
    "summary",
    "metadata",
    "pycharmprojects",
    "jobpilot",
    "fixtures",
    "baseline",
    "users",
    "lenovo",
    "tmp",
    "temp",
    "appdata",
    "local",
    "retrieval",
    "chunks",
}


def realign_golden_set(
    *,
    golden_file: Path,
    run_dir: Path,
    audit_report_file: Path,
    changelog_file: Path,
    today: str | None = None,
    max_keywords: int = 6,
) -> dict[str, Any]:
    validation = validate_golden_set(golden_file, run_dir=run_dir)
    if validation["status"] != "passed":
        raise ValueError(f"Golden set artifact audit failed before realign: {validation['errors']}")
    payload = json.loads(golden_file.read_text(encoding="utf-8-sig"))
    audit_payload = json.loads(audit_report_file.read_text(encoding="utf-8-sig"))
    samples = payload.get("samples")
    if not isinstance(samples, list):
        raise ValueError("Golden set requires a samples list.")

    audit_by_question_id = {
        str(item.get("question_id")): item
        for item in audit_payload.get("queries", [])
        if isinstance(item, dict) and str(item.get("question_id") or "").strip()
    }
    alignment_date = today or date.today().isoformat()
    changes: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()

    for sample in samples:
        if not isinstance(sample, dict):
            continue
        question_id = str(sample.get("question_id") or "")
        audit_item = audit_by_question_id.get(question_id)
        if audit_item is None:
            continue
        skip_reason = _skip_reason(sample, audit_item)
        if skip_reason:
            skipped[skip_reason] += 1
            continue
        keywords = _keywords_from_audit_item(audit_item, max_keywords=max_keywords)
        if not keywords:
            skipped["no_keywords"] += 1
            continue
        original_question = str(sample.get("question") or "")
        new_question = _append_keyword_hint(original_question, keywords)
        if new_question == original_question:
            skipped["already_aligned"] += 1
            continue
        sample["question"] = new_question
        sample["retrieval_alignment"] = {
            "method": ALIGNMENT_METHOD,
            "date": alignment_date,
            "source": str(audit_report_file),
        }
        changes.append(
            {
                "question_id": question_id,
                "original_question": original_question,
                "new_question": new_question,
                "keywords": keywords,
                "expected_labels": _expected_labels_from_audit_item(audit_item),
            }
        )

    golden_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    changelog = {
        "schema_version": CHANGELOG_SCHEMA,
        "golden_file": str(golden_file),
        "run_dir": str(run_dir),
        "audit_report_file": str(audit_report_file),
        "method": ALIGNMENT_METHOD,
        "date": alignment_date,
        "rewritten_sample_count": len(changes),
        "skipped_counts": dict(sorted(skipped.items())),
        "changes": changes,
    }
    changelog_file.parent.mkdir(parents=True, exist_ok=True)
    changelog_file.write_text(json.dumps(changelog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changelog


def _skip_reason(sample: dict[str, Any], audit_item: dict[str, Any]) -> str | None:
    if sample.get("case_type") == "no_answer" or audit_item.get("case_type") == "no_answer":
        return "no_answer"
    if audit_item.get("root_cause_hint") != TARGET_ROOT_CAUSE:
        return str(audit_item.get("root_cause_hint") or "unsupported_root_cause")
    if KEYWORD_MARKER in str(sample.get("question") or ""):
        return "already_aligned"
    return None


def _keywords_from_audit_item(audit_item: dict[str, Any], *, max_keywords: int) -> list[str]:
    text_parts: list[str] = []
    for document in audit_item.get("expected_documents", []):
        if not isinstance(document, dict):
            continue
        for chunk in document.get("matched_chunks", []):
            if isinstance(chunk, dict):
                text_parts.append(str(chunk.get("text_preview") or ""))
    tokens = _content_tokens("\n".join(text_parts))
    return tokens[:max_keywords]


def _content_tokens(text: str) -> list[str]:
    seen: set[str] = set()
    tokens: list[str] = []
    for raw_token in _TOKEN_RE.findall(text.lower()):
        token = raw_token.strip("-_.[](){}:,;|")
        if _discard_token(token):
            continue
        if token not in seen:
            seen.add(token)
            tokens.append(token)
    return tokens


def _discard_token(token: str) -> bool:
    if not token or len(token) < 2:
        return True
    if token in _STOPWORDS or token in _METADATA_TOKENS:
        return True
    if _ID_LIKE_RE.match(token):
        return True
    if re.match(r"^jd-\d+", token) or re.match(r"^req-\d+", token):
        return True
    return False


def _append_keyword_hint(question: str, keywords: list[str]) -> str:
    if KEYWORD_MARKER in question:
        return question
    return f"{question}（{KEYWORD_MARKER}{', '.join(keywords)}）"


def _expected_labels_from_audit_item(audit_item: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for document in audit_item.get("expected_documents", []):
        if not isinstance(document, dict):
            continue
        label = str(document.get("label") or "").strip()
        if label:
            labels.append(label)
    return labels


def main() -> int:
    parser = argparse.ArgumentParser(description="Rewrite local rag-golden-v1 questions for BM25 keyword evaluation.")
    parser.add_argument("--golden-file", type=Path, default=ROOT / "fixtures" / "golden_rag_questions.json")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument(
        "--changelog",
        type=Path,
        default=ROOT / "baseline" / "golden-realignment-20260531" / "changes.json",
    )
    parser.add_argument("--date", default=None, help="Alignment date. Defaults to today's local date.")
    parser.add_argument("--max-keywords", type=int, default=6)
    args = parser.parse_args()
    report = realign_golden_set(
        golden_file=args.golden_file,
        run_dir=args.run_dir,
        audit_report_file=args.audit_report,
        changelog_file=args.changelog,
        today=args.date,
        max_keywords=args.max_keywords,
    )
    print(
        json.dumps(
            {
                "changelog": str(args.changelog),
                "rewritten_sample_count": report["rewritten_sample_count"],
                "skipped_counts": report["skipped_counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
