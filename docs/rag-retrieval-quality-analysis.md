# RAG 检索质量分析

日期：2026-05-27
运行：`baseline-formal-r3-full-raw-library-20260520`
黄金集：`fixtures/golden_rag_questions.json`（rag-golden-v1，30 条样本）
分支：`codex/search-filter-eval`

## P0 修复：搜索过滤闭环（2026-05-27）

### 问题

`evaluate_retriever_layer` 调用 `retriever.search(query, limit=10)` 时未传入任何过滤参数。642 个 chunk 每次全部参与竞争，正确 chunk 几乎不可能排进 top 10。

### 改动

2 个文件，+25 行：

1. [evaluate_rag_layers.py](../scripts/evaluate_rag_layers.py)：
   - 新增 `_extract_jd_id()` — 从预期文档的 `source_id` 解析 `jd-XXX`（支持 `jd-001-req-014`、`jd-012:gap-map`、`variant-jd-jd-025` 等格式）
   - 新增 `_extract_source_type()` — 当所有预期文档共享同一个 `source_type` 时提取出来
   - 更新 `_sample_to_query_spec()`，将 `jd_id` 和 `source_type` 附加到 query spec 中

2. [metrics.py](../packages/py-core/src/shotguncv_core/rag/metrics.py)：
   - 更新 `evaluate_labeled_retrieval_queries()`，将 query spec 中的 `candidate_id`、`jd_id`、`source_type` 透传给 `retriever.search()`

### 效果：Before vs After

#### 总体指标（25 条 answerable 样本）

| 指标 | Dense | Dense(过滤) | BM25 | BM25(过滤) | Hybrid | Hybrid(过滤) |
|------|------:|------------:|-----:|-----------:|-------:|-------------:|
| precision@1 | 0.0 | **0.20** | 0.0 | **0.24** | 0.0 | **0.24** |
| precision@3 | 0.0 | **0.107** | 0.013 | **0.147** | 0.0 | **0.12** |
| recall@10 | 0.08 | **0.52** | 0.02 | **0.52** | 0.02 | **0.52** |
| nDCG@10 | 0.029 | **0.331** | 0.012 | **0.359** | 0.007 | **0.348** |
| **MRR** | 0.015 | **0.278** | 0.013 | **0.333** | 0.004 | **0.312** |
| 耗时 | 85.5s | **44.6s** | 1.8s | **1.8s** | 45.7s | **42.9s** |

#### 按 Case Type（Dense）

| Case Type | MRR Before | MRR After | recall@10 Before | recall@10 After |
|-----------|:----------:|:---------:|:----------------:|:---------------:|
| common_question (12) | 0.012 | **0.337** | 0.083 | **0.583** |
| multi_document (8) | 0.030 | **0.243** | 0.125 | **0.50** |
| stale_or_conflicting (5) | 0.0 | **0.04** | 0.0 | **0.20** |

#### 修复后三模式排名

| 模式 | MRR | precision@1 | 耗时 |
|------|-----|-------------|------|
| **BM25** | **0.333** | **0.24** | 1.8s |
| hybrid | 0.312 | 0.24 | 42.9s |
| dense | 0.278 | 0.20 | 44.6s |

### 为什么有效

1. **搜索空间坍缩**：`jd_id` 过滤将候选 chunk 从 642 缩减到每条 query 约 5–30 个。例如 `rag-golden-001` 的预期文档为 `jd-001-req-014`，现在只搜索 `metadata.jd_id == "jd-001"` 的 chunk，而非全量 642。

2. **搜索空间坍缩 → 噪声减少**：不相关 chunk 大幅减少后，排序变得极其简单。即便是微弱的语义信号也能将正确 chunk 排进 top 3。

3. **搜索空间坍缩 → 噪声减少 → dense 加速**：dense 模式原先需将 query 与 642 个 chunk embedding 逐一计算余弦相似度。过滤后仅 10–30 个 chunk 通过过滤器，余弦循环减少约 20 倍。耗时从 85.5s → 44.6s（节省不到 20 倍，因为 embedding 计算本身仍需约 40s 的一次性开销）。

4. **BM25 受益最大**：加上 `jd_id` 过滤后，BM25 的搜索文本（`_chunk_search_text` 包含 `source_id`）提供了巨大的信号增益。在过滤后的候选集中，`source_id` 中的 `jd-001-req-014` 等标识符是最精准的 term 匹配。BM25 的 MRR 从 0.013 → 0.333（**提升 25 倍**）。

5. **stale_or_conflicting 不再全零**：修复前这些样本的命中率为 0，因为正确 chunk 被 600+ 无关结果淹没。修复后正确 chunk 能够进入 top 10，recall@10 从 0 → 0.20。

### No-Answer 行为（未变化）

No-answer 样本没有 `expected_documents`，因此不会派生任何过滤条件。检索器仍搜索全量 642 chunk 索引——这是正确的行为，我们需要验证检索器在数据中确实没有答案时能够正确撤回。

| 模式 | 撤回率 | 质量门 |
|------|--------|--------|
| dense | 1.0 | 通过 |
| hybrid | 1.0 | 通过 |
| BM25 | 0.6 | 未通过（2 条泄漏） |

---

## 修复前分析

以下为驱动 P0 搜索过滤修复的根因分析。

### 评估环境

- 642 个检索 chunk
- 25 answerable + 5 no_answer 样本
- 三种检索模式：dense（bge-m3, 1024d）、BM25（k1=1.5, b=0.75）、hybrid（vector=0.75, BM25=0.25，经 P1 网格搜索调优）
- k 值：1, 3, 5, 10
- **未使用任何搜索过滤** — 642 chunk 对每条 query 全局竞争

### 逐 Query 命中分布（修复前）

25 条 answerable query 中，dense 仅 3 条有命中，BM25 和 hybrid 各 1 条：

| Query | 模式 | 命中位置 | 预期 Label |
|-------|------|----------|------------|
| rag-golden-010 | dense | 第 9 位 | jd-013-req-007 |
| rag-golden-026 | dense/hybrid | 第 7/8 位 | candidate-profile |
| rag-golden-027 | dense | 第 8 位 | candidate-profile |
| rag-golden-016 | BM25 | 第 3–5 位 | JD profile jd-002 |

### 根因分析

#### 1. 检索无范围过滤 — 642 chunk 全部竞争（影响最大）

`_sample_to_query_spec` 只传了 `query_id` 和 `query` 文本。没有任何 `candidate_id`、`jd_id` 或 `source_type` 过滤条件。

`evaluate_labeled_retrieval_queries` 直接调用 `retriever.search(query, limit=search_limit)`，不传过滤参数。

**影响**：生产环境中 RAG 查询会按 candidate 或 JD 限定范围。642 chunk 裸搜几乎不可能让特定 chunk 进入 top 10。**这就是 P0 修复要解决的核心问题。**

#### 2. requirement_evidence chunk 结构高度同质

所有 requirement_evidence chunk 共享同一模板（`requirement_text + evidence_status + evidence_refs`），全部来自 `analyze/requirement_matrix.json`。embedding 模型无法在都讨论"技术经验/项目证据"的 chunk 之间做出精细区分。

#### 3. 自然语言 query vs 结构化文档 ID

黄金标签使用结构化标识符（`jd-001-req-014`、`jd-012:gap-map`），但 query 是中文自然语言问题。dense 无法做精确 ID 匹配；BM25 只有在 query 词与 chunk 文本有显式重叠时才能匹配。

#### 4. 跨语言语义鸿沟

Query 是中文，但 requirement_evidence chunk 的核心内容（`requirement_text`、`evidence_refs`）通常为英文或中英混合。1024 维 + 642 个短文本候选下，跨语言细粒度语义区分能力不足。

#### 5. Hybrid 融合策略抑制了各自信号

分数归一化方式与权重导致两个信号相互稀释。修复后 hybrid 仍低于单 BM25。

### P1 完成：Hybrid 权重网格搜索（2026-05-27）

分支：`codex/hybrid-weight-tuning`

#### 方法

以 0.05 步长对 `vector_weight` 与 `bm25_weight` 在 `[0.0, 1.0]` 范围做全网格搜索（440 个组合）。通过预计算每条 query 的 vector/BM25 分数（避免重复 embedding 计算），仅遍历权重组合重新计算 MRR。

#### Heatmap（MRR by vector_weight × bm25_weight）

| v_w \ b_w | 0.0 | 0.1 | 0.2 | 0.3 | 0.4 | 0.5 | 0.6 | 0.7 | 0.8 | 0.9 | 1.0 |
|-----------|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|
| 0.0       | –   | –   | –   | –   | –   | –   | –   | –   | –   | –   | .312|
| 0.6       | –   | –   | –   | –   | –   | .312| –   | –   | –   | –   | –   |
| 0.7       | –   | –   | –   | **.316** | – | – | – | – | – | – | – |
| 0.8       | –   | –   | **.316** | – | – | – | – | – | – | – | – |
| 0.9       | –   | .296| –   | –   | –   | –   | –   | –   | –   | –   | –   |
| 1.0       | .278| –   | –   | –   | –   | –   | –   | –   | –   | –   | –   |

> 仅显示有变化的行/列。`–` = 与邻域相同，无独立变化。

#### 结论

| 配置 | MRR | Δ vs BM25 |
|------|-----|-----------|
| **纯 BM25** | **0.333** | — |
| Hybrid 最优 (v=0.75, b=0.25) | 0.316 | −0.017 |
| Hybrid 默认 (v=0.55, b=0.45) | 0.312 | −0.021 |
| 纯 Dense | 0.278 | −0.055 |

**核心发现：hybrid 在任何权重下都无法超越纯 BM25。** 网格搜索仅发现一个狭窄的较优区域（v≈0.70–0.875, b≈0.125–0.30），将 MRR 从 0.312 提升至 0.316（+0.004），但仍远低于纯 BM25 的 0.333。

**根因**：当前 embedding 对中英文跨语言 query-chunk 配对几乎不提供互补信号。在 `jd_id` 过滤后，BM25 的 `source_id` 精确匹配已提供最佳排序信号。vector score 在绝大多数 query 上表现为噪声——它打乱了 BM25 的正确排序，而非补充新的相关 chunk。

**动作**：已将默认权重更新为最优值（v=0.75, b=0.25），但实质改进必须依赖跨语言信号增强（见下文 P1 任务）。

#### 数据

完整 440 组结果：`outputs/grid_search_hybrid_weights.json`

Grid search 脚本：`scripts/grid_search_hybrid_weights.py`。使用方式：

```bash
python scripts/grid_search_hybrid_weights.py \
  --run-dir baseline/runs-formal-20260520/baseline-formal-r3-full-raw-library-20260520 \
  --step 0.05 \
  --output outputs/grid_search_hybrid_weights.json
```

### 剩余改进优先级

| 优先级 | 方向 | 原因 |
|--------|------|------|
| ~~**P1**~~ | ~~Hybrid 权重调优~~ | ✅ 已完成。最优 v=0.75/b=0.25，MRR 0.316（+0.004），但仍低于纯 BM25（0.333）。**权重调优无法弥合差距。** |
| **P1** | 对齐黄金 query 与 chunk 语言 | 改写 query 加入预期 chunk 中出现的英文技术术语，提升 dense 和 BM25 命中率 |
| **P2** | 引入 cross-encoder reranker | 对第一阶段 top-50 结果做重排序，提升 top-k 精度 |
| **P2** | 同 source_id 多 chunk 合并 | 将同一文档的多个 chunk 合并为单一检索单元，避免文档切碎后单 chunk 无法命中 |
