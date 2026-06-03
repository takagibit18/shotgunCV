# 多文档与 OCR 检索复测记录

日期：2026-06-02

分支：`muti_documents_enhancement`

## 目标

本轮目标是闭环多证据问题和 OCR/弱关键词问题的检索表现：

- 针对 `multi_document`、`cross_section`、`stale_or_conflicting`，验证 query decomposition 是否能提升多证据覆盖。
- 针对 OCR artifact，增加可检索 alias 和 normalized keywords，并对弱关键词 OCR query 做 rewrite。
- 报表默认观察 `all_primary_hit_rate`、`all_expected_hit_rate`、robustness category 切片，以及 OCR extraction vs retrieval 诊断。

## 重要口径

当前 `decomposed` 策略是 **oracle-assisted upper bound**，不能作为真实未标注场景的 headline 指标。

原因：当前 decomposed query spec 会读取 golden 样本里的 `expected_documents`，并用其中的 `source_type`、`jd_id`、`role` 构造 primary/supporting/conflicting/stale stage。这相当于评测时提前知道目标证据类型和目标 JD，会导致指标虚高。

因此本轮记录采用以下口径：

- `bm25-single-current.json`：真实 headline。该口径不使用 `expected_documents` 做 source-type decomposition。
- `bm25-decomposed.json`：oracle 上限诊断。只用于判断 source-type-aware routing 是否有潜力。
- `bm25-decomposed-ocr.json`：OCR 子集诊断。用于确认 alias/rewrite 能否闭环 OCR retrieval。

## 实现说明

- `scripts/evaluate_rag_layers.py` 新增 `--query-strategy single|decomposed`。
- `decomposed` query spec 会生成按证据角色划分的 stage，并在 stage 未填满 top-k 时用原始 query fallback fill。
- `packages/py-core/src/shotguncv_core/rag/metrics.py` 记录每条 query 的 decomposition stages，并对 stage result 去重。
- `packages/py-core/src/shotguncv_core/rag/documents.py` 为 OCR/image-derived chunk 注入 alias，例如 `milvus`、`qdrant`、`faiss`、`ci/cd`、`developer tools`、`workflow`、`retrieval quality`。

## 产物

- Golden set：`fixtures/golden_rag_questions.json`
- Baseline run：`baseline/real-cv-golden-rebuild-20260602`
- 输出目录：`baseline/multi-documents-enhancement-20260602`
- 当前 single headline 报表：`baseline/multi-documents-enhancement-20260602/bm25-single-current.json`
- 历史 single 报表：`baseline/multi-documents-enhancement-20260602/bm25-single.json`
- Hybrid 0.3/0.7 single 报表：`baseline/multi-documents-enhancement-20260602/hybrid-v03-b07-single-current.json`
- Decomposed oracle 报表：`baseline/multi-documents-enhancement-20260602/bm25-decomposed.json`
- OCR-only decomposed 报表：`baseline/multi-documents-enhancement-20260602/bm25-decomposed-ocr.json`
- no-answer / hybrid 复测记录：`docs/no-answer-hybrid-recheck-20260602.md`

## 运行命令

```powershell
.\.venv\Scripts\python.exe scripts\validate_golden_rag_set.py fixtures\golden_rag_questions.json --run-dir baseline\real-cv-golden-rebuild-20260602

.\.venv\Scripts\python.exe scripts\evaluate_rag_layers.py `
  --layer retriever `
  --retriever-mode hybrid `
  --vector-weight 0.3 `
  --bm25-weight 0.7 `
  --query-strategy single `
  --golden-file fixtures\golden_rag_questions.json `
  --run-dir baseline\real-cv-golden-rebuild-20260602 `
  --output baseline\multi-documents-enhancement-20260602\hybrid-v03-b07-single-current.json

.\.venv\Scripts\python.exe scripts\evaluate_rag_layers.py `
  --layer retriever `
  --retriever-mode bm25 `
  --query-strategy single `
  --golden-file fixtures\golden_rag_questions.json `
  --run-dir baseline\real-cv-golden-rebuild-20260602 `
  --output baseline\multi-documents-enhancement-20260602\bm25-single-current.json

.\.venv\Scripts\python.exe scripts\evaluate_rag_layers.py `
  --layer retriever `
  --retriever-mode bm25 `
  --query-strategy decomposed `
  --golden-file fixtures\golden_rag_questions.json `
  --run-dir baseline\real-cv-golden-rebuild-20260602 `
  --output baseline\multi-documents-enhancement-20260602\bm25-decomposed.json

.\.venv\Scripts\python.exe scripts\evaluate_rag_layers.py `
  --layer retriever `
  --retriever-mode bm25 `
  --query-strategy decomposed `
  --golden-layer ocr_regression `
  --golden-file fixtures\golden_rag_questions.json `
  --run-dir baseline\real-cv-golden-rebuild-20260602 `
  --output baseline\multi-documents-enhancement-20260602\bm25-decomposed-ocr.json
```

## Golden 校验

Golden 校验通过：

- `sample_count=60`
- `case_type_counts`：`common_question=34`，`multi_document=11`，`no_answer=9`，`stale_or_conflicting=6`
- `golden_layer_counts`：`core_high_info=38`，`low_info_stress=6`，`non_target_negative=9`，`ocr_regression=7`
- `retriever_label_count=35`

## 当前真实 Headline 指标

当前真实 headline 使用 `bm25-single-current.json`。

| 指标 | Current Single BM25 |
| --- | ---: |
| MRR | 0.598 |
| P@1 | 0.490 |
| Recall@3 | 0.588 |
| Recall@10 | 0.775 |
| Weighted Recall@10 | 0.782 |
| All Primary Hit | 0.804 |
| All Expected Hit | 0.706 |
| no-answer false positives | 4 / 9 |
| no-answer gate | failed |

## Hybrid 对比

Hybrid 当前使用 `vector_weight=0.3`、`bm25_weight=0.7`，并保持 `--query-strategy single`，因此它不是 oracle decomposition。

整体对比：

| 指标 | BM25 Single | Hybrid 0.3/0.7 Single | Decomposed Oracle |
| --- | ---: | ---: | ---: |
| MRR | 0.598 | 0.641 | 0.642 |
| P@1 | 0.490 | 0.510 | 0.510 |
| Recall@3 | 0.588 | 0.647 | 0.667 |
| Recall@10 | 0.775 | 0.863 | 0.853 |
| Weighted Recall@10 | 0.782 | 0.861 | 0.866 |
| All Primary Hit | 0.804 | 0.863 | 0.882 |
| All Expected Hit | 0.706 | 0.804 | 0.804 |
| no-answer false positives | 4 / 9 | 1 / 9 | 4 / 9 |
| no-answer abstention rate | 0.556 | 0.889 | 0.556 |
| no-answer gate | failed | failed | failed |

Hybrid 重点切片：

| 切片 | Count | BM25 All Primary | Hybrid All Primary | BM25 All Expected | Hybrid All Expected |
| --- | ---: | ---: | ---: | ---: | ---: |
| `multi_document` | 11 | 0.636 | 0.545 | 0.273 | 0.364 |
| `stale_or_conflicting` | 6 | 0.500 | 0.833 | 0.333 | 0.667 |
| `cross_section` | 3 | 0.667 | 0.333 | 0.000 | 0.000 |
| `synonym_expression` | 3 | 0.667 | 0.667 | 0.333 | 0.333 |
| `fuzzy_colloquial` | 4 | 0.500 | 0.750 | 0.500 | 0.750 |

解读：Hybrid 是当前真实可用策略里最强的全量候选，整体 MRR、Recall@10、All Expected 和 no-answer 泄漏都优于 BM25 single。但它不是单向度胜利：`multi_document` 的 All Primary 下降，`cross_section` 也下降；它对 `stale_or_conflicting`、`fuzzy_colloquial` 和 no-answer 相似概念干扰更有效。因此 hybrid 可以作为真实候选路线继续推进，但仍不能替代 no-answer entailment gate。

当前 single 重点切片：

| 切片 | Count | MRR | Recall@3 | All Primary | All Expected |
| --- | ---: | ---: | ---: | ---: | ---: |
| `multi_document` | 11 | 0.503 | 0.364 | 0.636 | 0.273 |
| `stale_or_conflicting` | 6 | 0.565 | 0.333 | 0.500 | 0.333 |
| `cross_section` | 3 | - | 0.333 | 0.667 | 0.000 |
| `synonym_expression` | 3 | - | 0.000 | 0.667 | 0.333 |
| `fuzzy_colloquial` | 4 | - | 0.500 | 0.500 | 0.500 |

## Oracle 上限诊断

`bm25-decomposed.json` 只能作为 oracle 上限诊断。它使用 `expected_documents` 推导 stage role、`source_type` 和 `jd_id` filter，因此不能代表真实未标注场景。

整体对比：

| 指标 | Single | Decomposed Oracle |
| --- | ---: | ---: |
| MRR | 0.598 | 0.642 |
| Recall@3 | 0.588 | 0.667 |
| All Primary Hit | 0.804 | 0.882 |
| All Expected Hit | 0.706 | 0.804 |

Oracle 重点切片：

| 切片 | Count | Single All Primary | Decomposed Oracle All Primary | Single All Expected | Decomposed Oracle All Expected |
| --- | ---: | ---: | ---: | ---: | ---: |
| `multi_document` | 11 | 0.636 | 0.818 | 0.273 | 0.455 |
| `stale_or_conflicting` | 6 | 0.500 | 0.833 | 0.333 | 0.833 |
| `cross_section` | 3 | 0.667 | 1.000 | 0.000 | 0.000 |
| `synonym_expression` | 3 | 0.667 | 0.667 | 0.333 | 0.667 |
| `fuzzy_colloquial` | 4 | 0.500 | 0.500 | 0.500 | 0.500 |

解读：decomposed oracle 的提升说明 source-type-aware routing 有潜力，尤其对 `stale_or_conflicting` 很明显。但由于它使用了 golden label 信息，这些数值不能进入 headline。

## OCR 子集诊断

OCR-only decomposed BM25：

| 指标 | Value |
| --- | ---: |
| MRR | 0.550 |
| Recall@3 | 0.714 |
| All Primary Hit | 1.000 |
| All Expected Hit | 1.000 |
| OCR retrieval issues | 0 / 7 |
| OCR extraction issues documented | 4 / 7 |

解读：当前 fixture 下 OCR retrieval 已闭环。弱关键词、多 requirement 和 OCR noise 样本都能命中 expected evidence。剩余 4 条被标记为 extraction issue，原因是文本本身存在低置信 OCR 噪声，例如 `Mivus`、`GitLab Cl`、`CVCD`。

## 当前判断

1. 当前真实 headline 应使用 `single-current`，不是 `decomposed`。
2. `decomposed` 是 oracle 上限，用来衡量 source-type-aware routing 的潜力。
3. 真实可上线版本需要实现 non-oracle router：只能基于 query 文本、broad top hits 和可观测 metadata 推断 source_type / jd_id，不能读取 `expected_documents`。
4. no-answer 仍未修复：full BM25 报表中 `false_positive_count=4`，`abstention_rate=0.556`，`quality_gate.status=failed`。后续需要 second-stage support / entailment gate。
