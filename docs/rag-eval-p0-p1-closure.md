# RAG Evaluation P0/P1 Closure - 2026-05-31

## Scope

本轮闭环两个目标：

- P0: 在不改变旧 MRR/precision/recall 口径的前提下，补充 role-aware / multi-document 解释性指标。
- P1: 对剩余 hard cases 输出可复跑诊断，明确下一步该修 golden、query、chunk 还是 retrieval strategy。

输入仍使用本地 aligned `fixtures/golden_rag_questions.json`，不改 golden，不改 retriever/reranker，不引入 LLM judge。

## P0: Weighted Multi-Document Metrics

新增指标位于 retriever report 的 `metrics.aggregate` 与每条 query report：

- `weighted_recall_at_k`: 按 `expected_documents.role` 加权的 recall。
- `weighted_ndcg_at_k`: 按 role gain 计算的 nDCG。
- `all_expected_hit_rate`: 每条 query 的所有 expected labels 是否都在 top-k 内命中。
- `all_primary_hit_rate`: 每条 query 的 primary expected labels 是否都在 top-k 内命中。
- `evidence_coverage`: 每条 query 的 primary/supporting/conflicting 命中拆解。

当前权重：

| role | weight |
|------|-------:|
| primary | 1.00 |
| conflicting | 1.00 |
| stale | 0.75 |
| supporting | 0.50 |

这些指标不替代 MRR，而是解释 MRR 背后的多文档覆盖情况。

## Re-evaluation

基准 run: `baseline-formal-r3-full-raw-library-20260520`

输出目录: `baseline/eval-p0-p1-20260531/`

| 配置 | MRR | P@1 | R@10 | nDCG@10 | weighted R@10 | weighted nDCG@10 | all expected hit | all primary hit |
|------|----:|----:|-----:|--------:|--------------:|-----------------:|-----------------:|----------------:|
| BM25 | 0.604 | 0.52 | 0.72 | 0.552 | 0.753 | 0.583 | 0.56 | 0.88 |
| BM25 + static | **0.631** | **0.56** | **0.72** | **0.568** | **0.753** | **0.600** | **0.56** | **0.88** |
| BM25@20 -> reranker | 0.540 | 0.44 | 0.64 | 0.512 | 0.667 | 0.521 | 0.48 | 0.76 |

Interpretation:

- BM25 + static 仍是当前最佳组合。
- `all_primary_hit_rate=0.88` 说明 primary evidence 大多数已经能进 top-10。
- `all_expected_hit_rate=0.56` 说明主要缺口在 multi-document 完整覆盖，尤其是 supporting/conflicting evidence。
- Reranker 不只 MRR 较低，weighted recall 和 all-primary-hit 也更低，说明它当前不是更好的生产默认路径。

## P1: Remaining Hard Cases

对最佳单阶段报告 `bm25-static.json` 跑 zero-hit audit 后，剩余 3 条，全部是 `retrieval_ranking_failure`：

| query | filter scope | missing labels | role mix | current diagnosis |
|-------|--------------|----------------|----------|-------------------|
| `rag-golden-004` | `single_jd`, `jd_id=jd-018` | `jd-018-req-014`, `jd-018:gap-map` | primary + supporting | Query 只强匹配到 `ai/agent`，top hits 是 JD description、req-001、resume variant；expected documents 更偏 Agent capability / gap-map synthesis，排序信号不足。 |
| `rag-golden-014` | `single_jd`, `jd_id=jd-001`, `source_type=requirement_evidence` | `jd-001-req-007` | primary | Expected chunk 是 LLM/multimodal system integration；top hit 是 broader API/AWS/ML requirement。更像同一 JD 内 requirement 粒度竞争，query 或 expected label 需要人工确认。 |
| `rag-golden-015` | `mixed_scope`, no filters | `jd-001-req-007`, `jd-002:gap-map` | primary + conflicting | Mixed-scope 正常，但 top hits 被 jd-001 的泛化 profile/education/product-collaboration 词吸走。这里更像 graded relevance / conflict evidence 评估问题，不适合继续靠 BM25 tuning 硬推。 |

Conclusion:

- P1 没发现新的 label coverage 问题。
- P1 没发现新的 scope filter 问题。
- 剩余失败都不是“文档找不到”，而是 expected evidence 与 top hits 在同一主题簇内竞争。

## Next Priorities

1. 对 `rag-golden-014` 做人工 expected-doc swap 审计：确认 `jd-001-req-007` 是否唯一正确，还是 top hit `jd-001-req-012` 也应被标为 acceptable。
2. 对 `rag-golden-015` 单独设计 conflict-aware scoring：命中 primary 但漏 conflicting，与命中 conflicting 但漏 primary，不应被同等解释。
3. 对 `rag-golden-004` 检查 query 是否过宽；如果目标是 Agent platform evidence，可能需要把 expected set 扩展到 JD profile / resume variant，或者把 query 收窄到 req-014 的具体词。
4. 暂停更大 reranker / embedding 投入，直到上述三条 hard case 的标注解释完成。

## Verification

Commands run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_evaluate_rag_layers.py tests\test_retrieval_metrics.py tests\test_audit_golden_rag_zero_hits.py tests\test_realign_golden_rag_set.py tests\test_validate_golden_rag_set.py
.\.venv\Scripts\python.exe scripts\validate_golden_rag_set.py fixtures\golden_rag_questions.json
.\.venv\Scripts\python.exe scripts\evaluate_rag_layers.py --layer retriever --retriever-mode bm25 --golden-file fixtures\golden_rag_questions.json --run-dir baseline\runs-formal-20260520\baseline-formal-r3-full-raw-library-20260520 --output baseline\eval-p0-p1-20260531\bm25.json
.\.venv\Scripts\python.exe scripts\evaluate_rag_layers.py --layer retriever --retriever-mode bm25 --query-expansion static --golden-file fixtures\golden_rag_questions.json --run-dir baseline\runs-formal-20260520\baseline-formal-r3-full-raw-library-20260520 --output baseline\eval-p0-p1-20260531\bm25-static.json
.\.venv\Scripts\python.exe scripts\evaluate_rag_layers.py --layer retriever --retriever-mode bm25 --reranker BAAI/bge-reranker-v2-m3 --first-stage-limit 20 --golden-file fixtures\golden_rag_questions.json --run-dir baseline\runs-formal-20260520\baseline-formal-r3-full-raw-library-20260520 --output baseline\eval-p0-p1-20260531\reranker-bm25-fs20.json
.\.venv\Scripts\python.exe scripts\audit_golden_rag_zero_hits.py --run-dir baseline\runs-formal-20260520\baseline-formal-r3-full-raw-library-20260520 --golden-file fixtures\golden_rag_questions.json --retriever-report baseline\eval-p0-p1-20260531\bm25-static.json --output baseline\eval-p0-p1-20260531\bm25-static-zero-hit-audit.json
```
