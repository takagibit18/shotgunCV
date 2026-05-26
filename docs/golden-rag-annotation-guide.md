# RAG Golden Set Annotation Guide

## Scope

This guide defines the first manual `rag-golden-v1` dataset for layered RAG evaluation. The set is shared by retriever, generator, and end-to-end checks.

The first version must contain 30-50 samples and cover four case types:

- `common_question`: answerable from one or a small number of clear artifacts.
- `multi_document`: requires combining multiple source types, JDs, or artifacts.
- `no_answer`: the current knowledge base cannot confirm the answer.
- `stale_or_conflicting`: evidence is outdated, OCR-sensitive, or conflicts across artifacts.

## Required Fields

Each sample must include:

- `question_id`: stable ID used by reports and regressions.
- `question`: user-facing question.
- `case_type`: one of the four supported case types.
- `expected_documents`: evidence objects with `source_type` plus `label`, `source_id`, or `chunk_id`. Use an empty list only for `no_answer`.
- `golden_answer`: concise human-approved answer.
- `must_cover_points`: required answer points.
- `forbidden_claims`: claims the generator must not make.
- `answer_policy`: how to answer when evidence is absent, conflicting, stale, or incomplete.
- `metadata`: at least `bucket`, `jd_count`, `input_media_types`, and `candidate_scope`.

## Evidence Rules

Prefer stable artifact labels that match retrieval metadata, such as `jd-001-req-014`, `jd-012:gap-map`, `JD profile jd-002`, `variant-jd-jd-018`, or `candidate-profile`.

For `multi_document`, include at least two expected documents and mark their roles as `primary` or `supporting`.

For `stale_or_conflicting`, use `role=conflicting` or `role=stale` for the document that should lower confidence or change the answer.

For `no_answer`, keep `expected_documents=[]`, make `golden_answer` explicitly say the current materials cannot confirm the claim, and list the missing evidence in `must_cover_points`.

## Validation

Run:

```powershell
.\.venv\Scripts\python.exe scripts\validate_golden_rag_set.py fixtures\golden_rag_questions.json
```

The validator checks the version, sample count, required fields, case-type coverage, document label structure, no-answer semantics, duplicate IDs, and retriever label count.

The concrete golden JSON remains local and ignored by Git under `/fixtures/golden_*.json`; only this guide and the validator are intended to be committed.
