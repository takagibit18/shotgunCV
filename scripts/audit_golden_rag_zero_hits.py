from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "cli" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "py-core" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "py-agents" / "src"))

from scripts.evaluate_rag_layers import _chunk_matches_label, _document_label, _load_valid_golden, _samples  # noqa: E402
from shotguncv_core.db.indexer import build_projection_batch  # noqa: E402


_TOKEN_RE = re.compile(r"[a-z][a-z0-9+#.-]*|[0-9]+|[\u4e00-\u9fff]{2,}", re.IGNORECASE)
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "for",
    "from",
    "in",
    "is",
    "of",
    "or",
    "the",
    "to",
    "what",
    "with",
    "是否有",
    "有没有",
    "什么",
    "哪些",
    "如何",
    "证据",
    "真实",
    "项目",
}


def audit_zero_hit_queries(
    *,
    run_dir: Path,
    golden_file: Path,
    retriever_report_file: Path,
    output_path: Path | None = None,
    question_ids: list[str] | None = None,
    include_nonzero: bool = False,
    max_text_chars: int = 320,
) -> dict[str, Any]:
    payload = _load_valid_golden(golden_file)
    samples_by_id = {str(sample["question_id"]): sample for sample in _samples(payload)}
    report = json.loads(retriever_report_file.read_text(encoding="utf-8"))
    chunks = build_projection_batch(run_dir).retrieval_chunks
    selected_question_ids = {str(item) for item in question_ids or []}

    audited: list[dict[str, Any]] = []
    zero_mrr_query_count = 0
    for query_report in _query_reports(report):
        query_id = str(query_report.get("query_id") or "")
        if selected_question_ids and query_id not in selected_question_ids:
            continue
        if _is_zero_mrr(query_report):
            zero_mrr_query_count += 1
        elif not include_nonzero:
            continue
        sample = samples_by_id.get(query_id)
        if sample is None:
            continue
        audited.append(
            _audit_query(
                sample=sample,
                query_report=query_report,
                chunks=chunks,
                max_text_chars=max_text_chars,
            )
        )

    root_cause_counts = Counter(str(item["root_cause_hint"]) for item in audited)
    result = {
        "schema_version": "rag-zero-hit-audit-v1",
        "run_id": str(report.get("run_id") or run_dir.name),
        "run_dir": str(run_dir),
        "golden_file": str(golden_file),
        "retriever_report_file": str(retriever_report_file),
        "zero_mrr_query_count": zero_mrr_query_count,
        "audited_query_count": len(audited),
        "root_cause_hint_counts": dict(sorted(root_cause_counts.items())),
        "queries": audited,
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _query_reports(report: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = report.get("metrics") if isinstance(report, dict) else {}
    queries = metrics.get("queries") if isinstance(metrics, dict) else report.get("queries")
    if not isinstance(queries, list):
        return []
    return [item for item in queries if isinstance(item, dict)]


def _is_zero_mrr(query_report: dict[str, Any]) -> bool:
    metrics = query_report.get("metrics")
    if not isinstance(metrics, dict) or "mrr" not in metrics:
        return False
    try:
        return float(metrics["mrr"]) == 0.0
    except (TypeError, ValueError):
        return False


def _audit_query(
    *,
    sample: dict[str, Any],
    query_report: dict[str, Any],
    chunks: list[dict[str, Any]],
    max_text_chars: int,
) -> dict[str, Any]:
    expected_documents = [
        _expected_document_summary(document, chunks, max_text_chars=max_text_chars)
        for document in sample.get("expected_documents", [])
        if isinstance(document, dict)
    ]
    expected_text = "\n".join(
        chunk["text_preview"]
        for document in expected_documents
        for chunk in document.get("matched_chunks", [])
        if isinstance(chunk, dict)
    )
    top_hits = [
        _top_hit_summary(hit, chunks, max_text_chars=max_text_chars)
        for hit in query_report.get("hits", [])
        if isinstance(hit, dict)
    ]
    top_hit_text = "\n".join(str(hit.get("text_preview") or "") for hit in top_hits)
    query_text = str(query_report.get("query") or sample.get("question") or "")
    token_overlap = _token_overlap(query_text, expected_text, top_hit_text)
    missing_expected_labels = [
        str(document["label"])
        for document in expected_documents
        if int(document.get("matched_chunk_count") or 0) == 0
    ]
    root_cause_hint = _root_cause_hint(
        missing_expected_labels=missing_expected_labels,
        query_expected_overlap_tokens=token_overlap["query_expected_overlap_tokens"],
        expected_text=expected_text,
    )
    return {
        "question_id": sample["question_id"],
        "case_type": sample.get("case_type"),
        "question": query_text,
        "metrics": query_report.get("metrics", {}),
        "expected_labels": [str(document["label"]) for document in expected_documents],
        "expected_documents": expected_documents,
        "top_hits": top_hits,
        "retrieval_diagnostics": _retrieval_diagnostics(query_report, expected_documents),
        "token_overlap": token_overlap,
        "root_cause_hint": root_cause_hint,
        "root_cause_explanation": _root_cause_explanation(root_cause_hint),
    }


def _expected_document_summary(
    document: dict[str, Any],
    chunks: list[dict[str, Any]],
    *,
    max_text_chars: int,
) -> dict[str, Any]:
    label = _document_label(document)
    matches = [chunk for chunk in chunks if _chunk_matches_label(chunk, label)]
    return {
        "label": label,
        "source_type": document.get("source_type"),
        "source_id": document.get("source_id"),
        "role": document.get("role"),
        "matched_chunk_count": len(matches),
        "matched_chunks": [_chunk_summary(chunk, max_text_chars=max_text_chars) for chunk in matches],
    }


def _top_hit_summary(hit: dict[str, Any], chunks: list[dict[str, Any]], *, max_text_chars: int) -> dict[str, Any]:
    matches = _chunks_for_hit(hit, chunks)
    summary = {
        "source_type": hit.get("source_type"),
        "source_id": hit.get("source_id"),
        "artifact_path": hit.get("artifact_path"),
        "score": hit.get("score"),
        "matched_chunk_count": len(matches),
        "text_preview": _preview(matches[0].get("text", ""), max_text_chars) if matches else "",
    }
    return summary


def _retrieval_diagnostics(
    query_report: dict[str, Any],
    expected_documents: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_labels = [str(document.get("label") or "") for document in expected_documents if str(document.get("label") or "")]
    expected_set = set(expected_labels)
    ranked_ids = [str(item) for item in query_report.get("ranked_ids", []) if str(item)]
    hit_labels = {item for item in ranked_ids if item in expected_set}
    ranked_relevance = query_report.get("ranked_relevance", [])
    first_relevant_rank = None
    if isinstance(ranked_relevance, list):
        for index, value in enumerate(ranked_relevance, start=1):
            if value is True:
                first_relevant_rank = index
                break
    if first_relevant_rank is None:
        for index, label in enumerate(ranked_ids, start=1):
            if label in expected_set:
                first_relevant_rank = index
                break
    return {
        "filter_scope": query_report.get("filter_scope"),
        "filters": query_report.get("filters", {}),
        "first_relevant_rank": first_relevant_rank,
        "top_hit_matches_expected": bool(ranked_ids and ranked_ids[0] in expected_set),
        "expected_label_count": len(expected_set),
        "hit_label_count": len(hit_labels),
        "missing_labels": sorted(expected_set - hit_labels),
        "expected_role_counts": _role_counts(expected_documents, expected_set),
        "hit_role_counts": _role_counts(expected_documents, hit_labels),
    }


def _role_counts(expected_documents: list[dict[str, Any]], labels: set[str]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for document in expected_documents:
        label = str(document.get("label") or "")
        if label not in labels:
            continue
        role = str(document.get("role") or "primary").strip().lower() or "primary"
        counts[role] += 1
    return dict(sorted(counts.items()))


def _chunks_for_hit(hit: dict[str, Any], chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_type = str(hit.get("source_type") or "")
    source_id = str(hit.get("source_id") or "")
    artifact_path = str(hit.get("artifact_path") or "")
    matches = []
    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        if source_type and str(metadata.get("source_type") or "") != source_type:
            continue
        if source_id and str(metadata.get("source_id") or "") != source_id:
            continue
        if artifact_path and str(metadata.get("artifact_path") or "") != artifact_path:
            continue
        matches.append(chunk)
    return matches


def _chunk_summary(chunk: dict[str, Any], *, max_text_chars: int) -> dict[str, Any]:
    metadata = chunk.get("metadata") or {}
    return {
        "chunk_id": chunk.get("chunk_id"),
        "source_type": metadata.get("source_type"),
        "source_id": metadata.get("source_id"),
        "artifact_path": metadata.get("artifact_path"),
        "jd_id": metadata.get("jd_id"),
        "chunk_index": metadata.get("chunk_index"),
        "text_preview": _preview(chunk.get("text", ""), max_text_chars),
    }


def _preview(text: Any, max_chars: int) -> str:
    clean = re.sub(r"\s+", " ", str(text)).strip()
    if len(clean) <= max_chars:
        return clean
    return clean[: max(0, max_chars - 1)].rstrip() + "…"


def _token_overlap(query_text: str, expected_text: str, top_hit_text: str) -> dict[str, Any]:
    query_tokens = _content_tokens(query_text)
    expected_tokens = _content_tokens(expected_text)
    top_hit_tokens = _content_tokens(top_hit_text)
    expected_set = set(expected_tokens)
    top_hit_set = set(top_hit_tokens)
    query_expected = [token for token in query_tokens if token in expected_set]
    query_top_hit = [token for token in query_tokens if token in top_hit_set]
    return {
        "query_tokens": query_tokens,
        "expected_document_tokens": expected_tokens,
        "top_hit_tokens": top_hit_tokens,
        "query_expected_overlap_tokens": query_expected,
        "query_top_hit_overlap_tokens": query_top_hit,
        "missing_query_tokens_in_expected_documents": [token for token in query_tokens if token not in expected_set],
    }


def _content_tokens(text: str) -> list[str]:
    seen: set[str] = set()
    tokens: list[str] = []
    for match in _TOKEN_RE.findall(text.lower()):
        token = match.strip("-_.")
        if not token or token in _STOPWORDS or len(token) < 2:
            continue
        if token not in seen:
            seen.add(token)
            tokens.append(token)
    return tokens


def _root_cause_hint(
    *,
    missing_expected_labels: list[str],
    query_expected_overlap_tokens: list[str],
    expected_text: str,
) -> str:
    if missing_expected_labels:
        return "missing_expected_document_label"
    if expected_text.strip() and not query_expected_overlap_tokens:
        return "expected_document_vocabulary_gap"
    if query_expected_overlap_tokens:
        return "retrieval_ranking_failure"
    return "needs_human_review"


def _root_cause_explanation(root_cause_hint: str) -> str:
    explanations = {
        "missing_expected_document_label": (
            "At least one expected label could not be matched to any retrieval chunk. "
            "This points to stale or incorrect golden annotations."
        ),
        "expected_document_vocabulary_gap": (
            "Expected chunks exist, but the query has no content-token overlap with their text. "
            "This is the main signal for annotation/content mismatch rather than another model-tuning problem."
        ),
        "retrieval_ranking_failure": (
            "Expected chunks share content tokens with the query but were still not retrieved in a relevant rank. "
            "This points to retrieval/ranking behavior rather than label coverage."
        ),
        "needs_human_review": "The automatic signals are inconclusive; inspect the expected chunks and top hits manually.",
    }
    return explanations[root_cause_hint]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit zero-MRR RAG golden queries against expected chunk text.")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--golden-file", type=Path, default=ROOT / "fixtures" / "golden_rag_questions.json")
    parser.add_argument("--retriever-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--question-id", action="append", default=None, help="Limit audit to one or more question IDs.")
    parser.add_argument("--include-nonzero", action="store_true", help="Audit selected queries even when MRR is non-zero.")
    parser.add_argument("--max-text-chars", type=int, default=320)
    args = parser.parse_args()
    report = audit_zero_hit_queries(
        run_dir=args.run_dir,
        golden_file=args.golden_file,
        retriever_report_file=args.retriever_report,
        output_path=args.output,
        question_ids=args.question_id,
        include_nonzero=args.include_nonzero,
        max_text_chars=args.max_text_chars,
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "audited_query_count": report["audited_query_count"],
                "root_cause_hint_counts": report["root_cause_hint_counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
