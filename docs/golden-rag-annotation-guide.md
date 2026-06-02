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
- `metadata`: at least `bucket`, `jd_count`, `input_media_types`, `candidate_scope`, and `golden_layer`.

## Golden Layers

Every sample must declare `metadata.golden_layer`. This field is separate from `case_type`: `case_type` describes the question shape, while `golden_layer` describes the source quality and metric purpose.

See `docs/golden-rag-layering-design.md` for the full layer policy, current corpus classification, and the 2026-06-02 baseline observation.

Supported layers:

- `core_high_info`: high-information, stable samples used for the main RAG quality decision.
- `low_info_stress`: broad or vague real-market JDs used only as stress samples.
- `ocr_regression`: image/OCR-sensitive samples used to observe extraction and cleaning quality.
- `non_target_negative`: out-of-domain or absent-capability samples used to observe abstention and leakage.

Use `core_high_info` only when the raw JD and expected artifacts are clean enough for fair retrieval evaluation: no mojibake, no obvious OCR spacing, no label-only requirement, no path-only evidence, no broad `jd-xxx` expected label, and 100% expected-label coverage in the current clean run.

Do not mix the non-core layers into the headline RAG metrics. They should be reported as guardrails through `golden_layer_metrics`.

## Evidence Rules

Prefer stable artifact labels that match retrieval metadata, such as `jd-001-req-014`, `jd-012:gap-map`, `JD profile jd-002`, `variant-jd-jd-018`, or `candidate-profile`.

For `multi_document`, include at least two expected documents and mark their roles as `primary` or `supporting`.

For mixed-scope `multi_document` samples, do not assume a single JD filter applies. If `expected_documents` combine global candidate evidence such as `candidate-profile` with JD-local evidence such as `jd-005-req-013`, retriever evaluation must use `filter_scope=mixed_scope` and no derived `jd_id` filter. A JD filter is valid only when every expected document resolves to the same `jd-\d+`.

For `stale_or_conflicting`, use `role=conflicting` or `role=stale` for the document that should lower confidence or change the answer.

For `no_answer`, keep `expected_documents=[]`, make `golden_answer` explicitly say the current materials cannot confirm the claim, and list the missing evidence in `must_cover_points`.

## Validation

Run:

```powershell
.\.venv\Scripts\python.exe scripts\validate_golden_rag_set.py fixtures\golden_rag_questions.json
```

The validator checks the version, sample count, required fields, case-type coverage, document label structure, no-answer semantics, duplicate IDs, and retriever label count.

## Layered Evaluation

Retriever layer:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_rag_layers.py `
  --layer retriever `
  --run-dir baseline\runs-formal-20260520\baseline-formal-r3-full-raw-library-20260520 `
  --golden-file fixtures\golden_rag_questions.json `
  --output baseline\rag-layered-20260526\retriever.json `
  --k 1 --k 3 --k 5 --k 10
```

Zero-hit audit:

```powershell
.\.venv\Scripts\python.exe scripts\audit_golden_rag_zero_hits.py `
  --run-dir baseline\runs-formal-20260520\baseline-formal-r3-full-raw-library-20260520 `
  --golden-file fixtures\golden_rag_questions.json `
  --retriever-report baseline\rag-layered-20260526\retriever.json `
  --output baseline\rag-layered-20260526\zero-hit-audit.json
```

Use this before editing golden labels. The audit report separates missing labels, expected-document vocabulary gaps, and likely ranking failures so annotation fixes do not get mixed up with retriever tuning.

BM25 keyword realignment:

```powershell
.\.venv\Scripts\python.exe scripts\realign_golden_rag_set.py `
  --run-dir baseline\runs-formal-20260520\baseline-formal-r3-full-raw-library-20260520 `
  --golden-file fixtures\golden_rag_questions.json `
  --audit-report baseline\rag-layered-20260526\zero-hit-audit.json `
  --changelog baseline\golden-realignment-20260531\changes.json `
  --date 2026-05-31
```

Use this only after zero-hit audit shows `expected_document_vocabulary_gap`. The script keeps `expected_documents` unchanged and appends a short `检索关键词：...` hint from the expected chunk text, so BM25-style retriever evaluation measures ranking rather than dense-era semantic annotation mismatch. Do not use it for `missing_expected_document_label`, `retrieval_ranking_failure`, or `no_answer` cases.

Generator layer uses perfect documents from the golden set and evaluates an answer file. The answer file schema is:

```json
{
  "schema_version": "rag-generator-answers-v1",
  "answers": [
    {
      "question_id": "rag-golden-001",
      "answer": "...",
      "citations": [{"source_id": "jd-001-req-014"}]
    }
  ]
}
```

Run:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_rag_layers.py `
  --layer generator `
  --run-dir baseline\runs-formal-20260520\baseline-formal-r3-full-raw-library-20260520 `
  --golden-file fixtures\golden_rag_questions.json `
  --answers-file baseline\rag-layered-20260526\generator-answers.json `
  --output baseline\rag-layered-20260526\generator.json
```

The concrete golden JSON remains local and ignored by Git under `/fixtures/golden_*.json`; only this guide and the validator are intended to be committed.
