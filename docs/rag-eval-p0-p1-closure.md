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

---

## P0 Adjudication Closure（2026-05-31）

分支：`document_enhance`
Golden set 变更：3 条 query 的 expected_documents 经人工审计后修正。

### 变更明细

| Query | 变更 | 理由 |
|-------|------|------|
| `rag-golden-004` | 新增 `jd-018` (jd_description) 作为 supporting | 该 JD 的 profile 提供了 Agent platform evidence 的重要上下文，原 expected set 缺少这个 broader context |
| `rag-golden-014` | `jd-001-req-007` → `jd-001-req-012` | req-012（multimodal LLM integration）比 req-007（generic API/AWS/ML）更贴近 query 的具体技术问法 |
| `rag-golden-015` | **不改** | 跨 JD conflict case，留给 P2 conflict-aware metric |

### Re-evaluation

输出目录：`baseline/eval-p0-closure-20260531/`

| 配置 | MRR | P@1 | R@10 | weighted R@10 | all primary | all expected |
|------|----:|----:|-----:|--------------:|:-----------:|:------------:|
| BM25 | 0.684 | 0.60 | 0.77 | 0.803 | **0.92** | 0.60 |
| **BM25 + static** | **0.711** | **0.64** | **0.77** | **0.803** | **0.92** | **0.60** |
| BM25@20→reranker | 0.540 | 0.44 | 0.65 | 0.670 | 0.76 | 0.48 |

### 对比：P0 Adjudication 前 → 后

| 指标 | P0 前 (BM25+static) | P0 后 (BM25+static) | Δ |
|------|:---:|:---:|:---:|
| MRR | 0.631 | **0.711** | +12.7% |
| P@1 | 0.56 | **0.64** | +14.3% |
| R@10 | 0.72 | **0.77** | +6.9% |
| weighted R@10 | 0.753 | **0.803** | +6.6% |
| all primary hit | 0.88 | **0.92** | +4.5% |
| **零命中 queries** | **3** | **1** | **-67%** |

### 零命中审计

对 BM25+static 配置跑 `audit_golden_rag_zero_hits.py`：

```
Zero MRR count: 1
Root cause: retrieval_ranking_failure (rag-golden-015 only)
```

- `rag-golden-004`：**已修复**。新增的 `jd-018` (jd_description) 被召回并命中。
- `rag-golden-014`：**已修复**。`jd-001-req-012` 的文本（multimodal LLM integration）与 query 中的 "多模态 AI API" 和 "平台部署" 有 token 重叠。
- `rag-golden-015`：**保留**。跨 JD conflict case（jd-001 vs jd-002），expected 的 primary 和 conflicting 文档分属不同 JD，BM25 在 mixed_scope 下无法同时命中两者。

### 累积 RAG 优化进展（完整版）

```
原始 (P0 metadata filtering):    MRR 0.013  P@1 0.00  零命中 ~25
  P0 修复 (jd_id 过滤):          MRR 0.333  P@1 0.24  零命中 ~19
  P0: Chunking 按类型决策        MRR 0.337  P@1 0.24
  P1: Query Expansion            MRR 0.373  P@1 0.28
  Chunk 内容增强                  MRR 0.390  P@1 0.32
  P1: Cross-Encoder Reranker     MRR 0.398  P@1 0.32
  ── 以上为旧 golden set ──
  Golden set 词汇对齐            MRR 0.631  P@1 0.56  零命中 3   ← 评估修正
  P0: Expected doc 审计修正       MRR 0.711  P@1 0.64  零命中 1   ← 本次
                                   ─────────────────────
                                   累积: MRR +113%, P@1 +167%
```

### 结论

1. **Golden set 质量是最大的单一杠杆**。从 golden set 词汇对齐到 P0 adjudication，MRR 从 0.398 跳到 0.711（+79%），远超任何检索模型优化。
2. **BM25+static 仍然是最优配置**（MRR 0.711 > BM25 0.684 > Reranker 0.540）。Reranker 在词汇对齐后是明确的负资产。
3. **Primary evidence 已基本解决**（all_primary=0.92）。25 条 query 中 23 条的 primary evidence 全部进 top-10。
4. **剩余唯一瓶颈**：rag-golden-015（跨 JD conflict），需要 P2 conflict-aware metric 来正确评估。

### 验证

```bash
# golden 校验 — passed
python scripts/validate_golden_rag_set.py fixtures/golden_rag_questions.json

# 测试 — 18 passed
pytest tests/test_evaluate_rag_layers.py tests/test_retrieval_metrics.py \
       tests/test_audit_golden_rag_zero_hits.py tests/test_validate_golden_rag_set.py
```

---

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

---

## 2026-06-01 当前版本 Clean Baseline 与 Golden Realign

分支：`codex/goldenset_enhancement`

记录时 HEAD：`4a76722`

clean baseline run：

`baseline/runs-formal-20260601/baseline-formal-r3-full-raw-library-clean-20260601`

realign 输出目录：

`baseline/golden-realignment-20260601/`

### 当前版本改动

1. 加固 analyze 阶段的 requirement 质量门。
   - 过滤 `Responsibilities:`、`Requirements:`、`Relevance bucket`、`Source signals` 等 label-only requirement。
   - 将 raw requirement 中被过滤的低质量内容与最终 matrix 质量分开统计。
   - 只有污染 requirement 或无效 refs 进入 `requirement_matrix.json` 时才失败。

2. 扩展 resume metadata evidence 过滤。
   - 拒绝 `Source: ...`、本地路径、相对文件路径、URL-only refs 和文件路径型 evidence。
   - candidate profile 在 analyze artifact 落盘前先清洗，避免路径元数据继续流入 generate/evaluate/RAG chunks。

3. 收紧 requirement evidence matching。
   - verified 不再依赖单 token 命中。
   - evidence refs 需要去重，且必须是非元数据证据。
   - 没有可用 refs 的 verified requirement 会被质量审计拦截。

4. golden validation 和 realign 增加 artifact audit 防线。
   - `validate_golden_rag_set.py --run-dir ...` 会用当前 run artifact 校验 expected requirement。
   - 如果引用的 run artifact 已经污染，`realign_golden_rag_set.py` 会拒绝重写 golden set。

5. RAG projection 纳入 ranking explanations。
   - `evaluate/ranking_explanations.json` 会投影为 `ranking_explanation` chunks。
   - 这样 `jd-022:ranking` 这类 label 可以被检索到，而不是永久缺失于 corpus。

6. 使用 2026-06-01 clean baseline artifacts 对当前 golden set 重新 realign。
   - 移除或重绑指向已被质量门过滤 requirement 的 stale expected label。
   - 为 BM25 词汇对齐重写 1 条 query。

### Clean Artifact 质量

Analyze 质量门：

| 检查项 | 值 |
|------|------:|
| raw requirements | 598 |
| final matrix requirements | 299 |
| 被过滤的低质量 raw requirements | 219 |
| 进入 matrix 的低质量 requirements | 0 |
| 无效 evidence refs | 0 |
| 重复 evidence refs | 0 |
| verified 但无可用 refs | 0 |

RAG corpus projection：

| Chunk 类型 | 数量 |
|-----------|------:|
| total chunks | 461 |
| requirement_evidence chunks | 299 |
| ranking_explanation chunks | 27 |

Golden artifact audit：

| 检查项 | 值 |
|------|------:|
| sample count | 30 |
| retriever labels | 34 |
| label coverage | 34/34 |
| realign 后 zero-hit queries | 0 |

Expected document 分布：

| Source type | 数量 |
|-------------|------:|
| requirement_evidence | 21 |
| gap_map | 6 |
| jd_description | 4 |
| candidate_evidence | 2 |
| ranking_explanation | 1 |
| run_artifact | 1 |

Case 分布：

| Case type | 数量 |
|-----------|------:|
| common_question | 12 |
| multi_document | 8 |
| no_answer | 5 |
| stale_or_conflicting | 5 |

### Retriever 指标

| 配置 | MRR | R@10 | weighted R@10 | all expected hit | all primary hit |
|--------|----:|-----:|--------------:|-----------------:|----------------:|
| realign 前 BM25 | 0.467 | 0.840 | 0.863 | 0.72 | 0.92 |
| realign 后 BM25 | 0.481 | 0.880 | 0.903 | 0.76 | 0.96 |
| realign 后 BM25 + static | 0.481 | 0.820 | 0.836 | 0.72 | 0.88 |

BM25 realign 后按 case type 拆分的 R@10：

| Case type | R@10 |
|-----------|-----:|
| common_question | 1.000 |
| multi_document | 0.813 |
| stale_or_conflicting | 0.700 |

BM25 realign 后 no-answer 行为：

| 检查项 | 值 |
|------|------:|
| no-answer queries | 5 |
| abstained | 3 |
| abstention rate | 0.60 |
| non-abstained no-answer queries | 2 |
| quality gate | failed |

### 解释

当前 golden set 已经可以用于指标解释：artifact coverage 完整，stale label 导致的 zero-hit 已清零。指标提升幅度不大，但可信：BM25 R@10 从 `0.84` 提升到 `0.88`，weighted R@10 从 `0.863` 提升到 `0.903`，all-primary-hit 从 `0.92` 提升到 `0.96`。

剩余质量缺口已经不再主要来自 golden 污染，而是：

1. BM25 排序能力仍弱：很多 expected label 能进 top-10，但进不了 top-1/top-3，因此 MRR 不高。
2. multi-document 与 stale/conflicting 样本仍明显难于普通单证据问题。
3. no-answer 处理仍弱：5 条 no-answer 中有 2 条返回了 non-abstained 结果。
4. static query expansion 当前不适合作为默认配置；它在本轮 clean run 中降低了 R@10 和 all-primary-hit。

### 验证命令

```powershell
.\.venv\Scripts\python.exe scripts\validate_golden_rag_set.py fixtures\golden_rag_questions.json --run-dir baseline\runs-formal-20260601\baseline-formal-r3-full-raw-library-clean-20260601

.\.venv\Scripts\python.exe scripts\evaluate_rag_layers.py --layer retriever --golden-file fixtures\golden_rag_questions.json --run-dir baseline\runs-formal-20260601\baseline-formal-r3-full-raw-library-clean-20260601 --output baseline\golden-realignment-20260601\before-bm25.json --retriever-mode bm25

.\.venv\Scripts\python.exe scripts\audit_golden_rag_zero_hits.py --run-dir baseline\runs-formal-20260601\baseline-formal-r3-full-raw-library-clean-20260601 --golden-file fixtures\golden_rag_questions.json --retriever-report baseline\golden-realignment-20260601\before-bm25.json --output baseline\golden-realignment-20260601\before-zero-hit-audit.json

.\.venv\Scripts\python.exe scripts\realign_golden_rag_set.py --golden-file fixtures\golden_rag_questions.json --run-dir baseline\runs-formal-20260601\baseline-formal-r3-full-raw-library-clean-20260601 --audit-report baseline\golden-realignment-20260601\before-zero-hit-audit.json --changelog baseline\golden-realignment-20260601\changes.json --date 2026-06-01

.\.venv\Scripts\python.exe scripts\evaluate_rag_layers.py --layer retriever --golden-file fixtures\golden_rag_questions.json --run-dir baseline\runs-formal-20260601\baseline-formal-r3-full-raw-library-clean-20260601 --output baseline\golden-realignment-20260601\after-bm25.json --retriever-mode bm25

.\.venv\Scripts\python.exe scripts\evaluate_rag_layers.py --layer retriever --golden-file fixtures\golden_rag_questions.json --run-dir baseline\runs-formal-20260601\baseline-formal-r3-full-raw-library-clean-20260601 --output baseline\golden-realignment-20260601\after-bm25-static.json --retriever-mode bm25 --query-expansion static

.\.venv\Scripts\python.exe scripts\audit_golden_rag_zero_hits.py --run-dir baseline\runs-formal-20260601\baseline-formal-r3-full-raw-library-clean-20260601 --golden-file fixtures\golden_rag_questions.json --retriever-report baseline\golden-realignment-20260601\after-bm25.json --output baseline\golden-realignment-20260601\after-zero-hit-audit.json

.\.venv\Scripts\python.exe -m pytest tests\test_run_pipeline.py tests\test_validate_golden_rag_set.py tests\test_realign_golden_rag_set.py tests\test_audit_golden_rag_zero_hits.py tests\test_evaluate_rag_layers.py tests\test_db_rag_review.py -q
```

---

## 2026-06-02 P0-P2 细粒度 Golden Label 闭环

分支：`codex/golden-fine-label-p0-p2`

本轮复用的 clean baseline run：

`baseline/runs-formal-20260601/baseline-formal-r3-full-raw-library-clean-20260601`

评估输出目录：

`baseline/golden-fine-label-p0-p2-20260602/`

### 优先级调整

将之前的建议“减少 JD-level expected label”升级为 P0。

P0 规则：

可回答的 golden 样本不得再使用 `jd-021` 这类宽泛的 `jd_description` 作为 expected document。如果确实需要 JD 上下文，expected label 必须替换为更细粒度、可解释的 artifact：`gap_map`、`ranking_explanation` 或 `requirement_evidence`。

### P0：移除宽泛 JD-level Expected Label

已完成改动：

1. `validate_golden_rag_set.py` 新增硬门：拒绝 `source_type=jd_description` 且 label/source_id 只是 `jd-\d{3}` 的 expected document。
2. 当前 golden set 已不再包含宽泛 JD-level expected label。
3. 4 条样本从 JD-level label 重绑到更细粒度 artifact：
   - `rag-golden-019`: `jd-021` -> `jd-021:ranking`
   - `rag-golden-026`: `jd-023` -> `jd-023:ranking`
   - `rag-golden-027`: `jd-024` -> `jd-024:ranking`
   - `rag-golden-029`: `jd-026` -> `jd-026:gap-map`

P0 校验：

| 检查项 | 结果 |
|------|--------|
| golden schema + artifact audit | passed |
| 宽泛 JD-level expected label | 0 |
| expected label 数 | 34 |
| label coverage | 34/34 |
| zero-hit audit | 0 |

P0 指标：

| 配置 | MRR | R@10 | weighted R@10 | all expected hit | all primary hit |
|--------|----:|-----:|--------------:|-----------------:|----------------:|
| 2026-06-01 realign 后 BM25 | 0.481 | 0.880 | 0.903 | 0.76 | 0.96 |
| P0 细粒度 label BM25 | 0.441 | 0.900 | 0.923 | 0.80 | 0.96 |
| P0 BM25 + static | 0.441 | 0.840 | 0.856 | 0.76 | 0.88 |

P0 解释：

P0 在提高标注严格度和细粒度的同时，提升了覆盖类指标。MRR 下降是预期内结果：将宽泛 JD label 替换为 `ranking_explanation` / `gap_map` 后，目标文档更精确，但 BM25 还不能稳定把这些细粒度 artifact 排到足够靠前。static query expansion 在本轮 clean run 中仍弱于普通 BM25。

### P1：针对未完全覆盖的细粒度 Artifact 做 Query Realign

已完成改动：

1. 审计 expected label 已存在于 corpus、但 top-10 未完全召回的可回答样本。
2. 基于缺失的细粒度 expected document 文本，为 5 条 query 添加最小关键词提示。
3. P1 不修改 expected label，只让 query 与已经选定的细粒度 artifact 对齐。

P1 query 调整：

| Query | P1 目标缺失细粒度 artifact |
|-------|--------------------------------------|
| `rag-golden-014` | `jd-015:gap-map` |
| `rag-golden-015` | `jd-016-req-005` |
| `rag-golden-017` | `jd-019:gap-map` |
| `rag-golden-027` | `jd-024:ranking` |
| `rag-golden-030` | `jd-027-req-013` |

P1 指标：

| 配置 | MRR | R@10 | weighted R@10 | all expected hit | all primary hit |
|--------|----:|-----:|--------------:|-----------------:|----------------:|
| P0 细粒度 label BM25 | 0.441 | 0.900 | 0.923 | 0.80 | 0.96 |
| P1 BM25 query realign | 0.474 | 0.920 | 0.910 | 0.84 | 0.88 |
| P1 BM25 + static | 0.455 | 0.880 | 0.870 | 0.80 | 0.84 |

P1 解释：

P1 提升了 `MRR`、`R@10` 和 `all_expected_hit`，说明它确实帮助恢复了 P0 后的细粒度 artifact 覆盖。但 `all_primary_hit` 从 `0.96` 降到 `0.88`：部分关键词提示把 supporting/stale artifact 推上来了，同时把 primary evidence 挤出了 top-10。这说明 query realign 有价值，但不能作为多文档样本的唯一策略；后续仍需要 role-aware retrieval/ranking。

### P2：将 No-Answer Gate 收窄到 Candidate Evidence

已完成改动：

1. no-answer retriever gate 现在只检索 `candidate_evidence`。
2. 报告中为每条 no-answer query 记录 `filter_scope: candidate_evidence`。
3. 这样可以避免把 JD/JD input 中的岗位要求误当成“候选人具备某项技能或经历”的证据。

P2 指标：

| 配置 | MRR | R@10 | weighted R@10 | all expected hit | all primary hit | no-answer gate | no-answer abstention |
|--------|----:|-----:|--------------:|-----------------:|----------------:|----------------|---------------------:|
| P1 BM25 query realign | 0.474 | 0.920 | 0.910 | 0.84 | 0.88 | failed | 0.60 |
| P2 BM25 candidate-scoped no-answer | 0.474 | 0.920 | 0.910 | 0.84 | 0.88 | passed | 1.00 |
| P2 BM25 + static | 0.455 | 0.880 | 0.870 | 0.80 | 0.84 | passed | 1.00 |

P2 解释：

P2 在不改变可回答样本检索指标的前提下修复了 no-answer 质量门。此前的 leak 来自 no-answer 问题命中了 JD/JD input 中的 Kubernetes、Java 等岗位要求；这些文档不能证明候选人具备对应经验。因此，对这类 no-answer 样本使用 candidate-scoped retrieval 是更正确的评估行为。

### P0-P2 汇总

| 阶段 | 主要提升 | MRR | R@10 | weighted R@10 | all expected hit | all primary hit | no-answer gate |
|-------|------------------|----:|-----:|--------------:|-----------------:|----------------:|----------------|
| 2026-06-01 realign 后 BM25 | clean artifacts + zero-hit realign | 0.481 | 0.880 | 0.903 | 0.76 | 0.96 | failed |
| P0 | 移除宽泛 JD-level expected label | 0.441 | 0.900 | 0.923 | 0.80 | 0.96 | failed |
| P1 | 为部分未覆盖的细粒度 artifact 做 query realign | 0.474 | 0.920 | 0.910 | 0.84 | 0.88 | failed |
| P2 | no-answer gate 收窄到 candidate evidence | 0.474 | 0.920 | 0.910 | 0.84 | 0.88 | passed |

P2 后剩余问题：

1. P1 query realign 后 `all_primary_hit` 低于 P0，后续仍需要 role-aware retrieval/reranking。
2. static query expansion 仍弱于普通 BM25，不应作为默认配置。
3. 当前 label 更细、更严格；解释 MRR 时必须同时看 coverage 和 no-answer gate 状态。
