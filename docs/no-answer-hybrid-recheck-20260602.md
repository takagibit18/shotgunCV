# No-Answer Gate and Hybrid Retrieval Recheck

Date: 2026-06-02

Branch: `codex/p0-real-cv-report-guardrails`

## Goal

Recheck whether the current no-answer line is fixed after adding `false_positive_audit`, then compare BM25 with a conservative hybrid retriever.

## Artifacts

- Baseline run: `baseline/real-cv-golden-rebuild-20260602`
- Golden set: `fixtures/golden_rag_questions.json`
- Output directory: `baseline/p0-no-answer-current-20260602`
- BM25 report: `baseline/p0-no-answer-current-20260602/bm25-current.json`
- High-threshold diagnostic report: `baseline/p0-no-answer-current-20260602/bm25-threshold-12.json`
- Hybrid report: `baseline/p0-no-answer-current-20260602/hybrid-v03-b07-current.json`

## Golden Validation

Command:

```powershell
.\.venv\Scripts\python.exe scripts\validate_golden_rag_set.py fixtures\golden_rag_questions.json --run-dir baseline\real-cv-golden-rebuild-20260602
```

Result:

- `sample_count=60`
- `status=passed`
- `case_type_counts`: `common_question=34`, `multi_document=11`, `no_answer=9`, `stale_or_conflicting=6`
- `golden_layer_counts`: `core_high_info=38`, `ocr_regression=7`, `low_info_stress=6`, `non_target_negative=9`
- `retriever_label_count=35`

## BM25 Current Result

Command:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_rag_layers.py `
  --layer retriever `
  --retriever-mode bm25 `
  --golden-file fixtures\golden_rag_questions.json `
  --run-dir baseline\real-cv-golden-rebuild-20260602 `
  --output baseline\p0-no-answer-current-20260602\bm25-current.json
```

BM25 retrieval metrics:

| Metric | Value |
| --- | ---: |
| MRR | 0.590 |
| P@1 | 0.471 |
| R@10 | 0.745 |
| Weighted R@10 | 0.753 |
| All Primary Hit | 0.784 |
| All Expected Hit | 0.627 |

No-answer gate:

| Metric | Value |
| --- | ---: |
| no_answer query count | 9 |
| abstained count | 5 |
| abstention rate | 0.556 |
| false positive count | 4 |
| gate status | failed |
| blocks generator | true |

False-positive samples:

| Query | Question | Top score |
| --- | --- | ---: |
| `rag-golden-030` | 候选人是 Java 微服务专家吗？ | 3.317 |
| `rag-golden-047` | 会 FastAPI 是否就能证明他是资深后端架构师？ | 2.947 |
| `rag-golden-048` | 有 RAG 评测是不是等于做过模型训练或微调？ | 1.924 |
| `rag-golden-049` | 他用 Claude Code/Codex 能否证明有 OpenAI 平台工程经验？ | 11.626 |

Interpretation:

The current default no-answer gate is not fixed. The issue is not empty retrieval; it is high-scoring similar candidate evidence. BM25 correctly finds candidate-profile text containing related terms such as `Claude Code`, `Codex`, `FastAPI`, and `RAG`, but those hits do not entail the stronger claims in the no-answer questions.

## Threshold Diagnostic

Command:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_rag_layers.py `
  --layer retriever `
  --retriever-mode bm25 `
  --golden-file fixtures\golden_rag_questions.json `
  --run-dir baseline\real-cv-golden-rebuild-20260602 `
  --output baseline\p0-no-answer-current-20260602\bm25-threshold-12.json `
  --no-answer-score-threshold 12
```

Result:

- `false_positive_count=0`
- `abstention_rate=1.0`
- `quality_gate.status=passed`

Interpretation:

Raising the threshold to `12` can force this dataset's no-answer gate to pass, but it is a blunt diagnostic rather than a root-cause fix. It may over-abstain in real candidate-evidence queries and does not solve entailment.

## Hybrid Retrieval Check

Command:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_rag_layers.py `
  --layer retriever `
  --retriever-mode hybrid `
  --vector-weight 0.3 `
  --bm25-weight 0.7 `
  --golden-file fixtures\golden_rag_questions.json `
  --run-dir baseline\real-cv-golden-rebuild-20260602 `
  --output baseline\p0-no-answer-current-20260602\hybrid-v03-b07-current.json
```

Hybrid retrieval metrics:

| Metric | BM25 | Hybrid 0.3/0.7 |
| --- | ---: | ---: |
| MRR | 0.590 | 0.639 |
| P@1 | 0.471 | 0.529 |
| R@10 | 0.745 | 0.833 |
| Weighted R@10 | 0.753 | 0.825 |
| All Primary Hit | 0.784 | 0.804 |
| All Expected Hit | 0.627 | 0.765 |
| no-answer false positives | 4 | 1 |
| no-answer abstention rate | 0.556 | 0.889 |
| no-answer gate | failed | failed |

Remaining hybrid false positive:

| Query | Question |
| --- | --- |
| `rag-golden-049` | 他用 Claude Code/Codex 能否证明有 OpenAI 平台工程经验？ |

Interpretation:

Hybrid retrieval with a conservative semantic weight improves answerable retrieval and reduces no-answer false positives from `4/9` to `1/9`. It is a useful retrieval optimization, but it does not fully repair the no-answer line. The remaining failure is a support-relation problem: the candidate evidence really mentions Claude Code/Codex, but it does not prove OpenAI platform engineering experience.

## Decision

Current recommended direction:

1. Keep `hybrid --vector-weight 0.3 --bm25-weight 0.7` as a promising retrieval candidate because it improves MRR, R@10, all expected hit, and no-answer leakage.
2. Do not treat hybrid as the no-answer fix. It still fails the quality gate.
3. Add a second-stage no-answer support check for strong inference questions. Queries containing patterns such as `能否证明`, `是否等于`, `专家`, `资深`, `平台工程经验`, `模型训练`, or `微调` should require direct entailment from evidence. Similar-term retrieval alone should route to abstain or needs_review.
4. Keep `false_positive_audit` in retriever reports as the default guardrail observability field so future retrieval changes cannot silently regress no-answer behavior.
