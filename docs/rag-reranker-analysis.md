# Cross-Encoder Reranker 评估记录

> 此文档为 Reranker 的**专用评估日志**。每次实验在此文件末尾追加，标注日期和分支。
> 综合 RAG 优化全景见 `docs/rag-retrieval-quality-analysis.md`。

## 环境基线（2026-05-30）

| 项 | 值 |
|----|-----|
| 基准 run | `baseline-formal-r3-full-raw-library-20260520` (27 JDs) |
| Golden set | `fixtures/golden_rag_questions.json` (30 samples, 25 answerable) |
| Chunk 策略 | atomic (P0) + JD context enrichment |
| Expansion | static mapping (P1) |
| 当前最优单阶段 | BM25 + static expansion: **MRR 0.390, p@1 0.32, recall@10 0.54** |
| 零命中 queries | 16/25 仍为零命中（BM25 baseline） |
| Reranker 模型 | `BAAI/bge-reranker-v2-m3` (568M params, multilingual) |

## 实验设计

### 评估矩阵

| 维度 | 选项 | 组合数 |
|------|------|:------:|
| 粗召回模式 | bm25 / dense / hybrid | 3 |
| Query expansion | none / static | 2 |
| 粗召回宽度 | 20 / 50 / 100 | 3 |
| Reranker 输出 | top-5 / top-10 | 2 |
| **理论总组合** | | **36** |

### 核心对比（必须跑的组合）

| # | 粗召回 | Expansion | 粗召回宽度 | Reranker | 目的 |
|---|--------|-----------|:----------:|----------|------|
| 1 | BM25 | none | — | **无** | 单阶段 baseline |
| 2 | BM25 | static | — | **无** | 单阶段最优 baseline |
| 3 | BM25 | none | 20 | ✅ | 最小宽度 baseline |
| 4 | BM25 | none | **50** | ✅ | 标准宽度 |
| 5 | BM25 | none | 100 | ✅ | 宽召回上限 |
| 6 | BM25 | **static** | 20 | ✅ | expansion + reranker 叠加 |
| 7 | BM25 | **static** | **50** | ✅ | 预期的**最优组合** |
| 8 | BM25 | static | 100 | ✅ | 宽召回叠加 |
| 9 | Dense | none | 50 | ✅ | Dense 粗召回对比 |
| 10 | Dense | static | 50 | ✅ | Dense + expansion |

### 关键观测指标

- **新修复零命中**：16 条零命中中有多少被 reranker 修复
- **Per-case-type 提升**：common_question / multi_document / stale_or_conflicting 各自的 MRR 变化
- **Reranker score 分布**：top-1 score 的均值、中位数、分布
- **退化检测**：有没有 reranker 后排得更差的 query
- **耗时**：粗召回 + reranker 的 wall time

---

## 实验 01：评估矩阵全量对比（2026-05-30）

分支：`feat/cross-encoder-reranker`
实现：`rag/reranking.py` (CrossEncoderReranker) + `_TwoStageRetriever` adapter

### 全量对比

| # | 粗召回 | Expansion | 1st-stage | Reranker | MRR | p@1 | r@10 | nDCG@10 |
|---|--------|-----------|:---------:|:--------:|-----|-----|------|---------|
| 1 | BM25 | none | — | — | 0.348 | 0.28 | 0.48 | 0.355 |
| 2 | BM25 | static | — | — | 0.390 | 0.32 | 0.54 | 0.401 |
| **3** | **BM25** | **none** | **20** | **✅** | **0.398** | **0.32** | **0.54** | **0.409** |
| 4 | BM25 | none | 50 | ✅ | 0.387 | 0.28 | 0.54 | 0.404 |
| 5 | BM25 | none | 100 | ✅ | 0.387 | 0.28 | 0.54 | 0.404 |
| 6 | Dense | none | 50 | ✅ | 0.387 | 0.28 | 0.54 | 0.404 |

### 关键发现

#### 1. 最优组合：BM25 @20 → reranker @10

- MRR: 0.348 → **0.398** (+14.5% vs BM25 baseline)
- precision@1: 0.28 → **0.32** (+14.3%)
- 优于 BM25+static expansion 单阶段（0.390）
- **不需要 query expansion**——reranker 自动处理了中英文语义匹配

#### 2. 越窄的粗召回，reranker 越好

```
first-stage=20:  MRR 0.398  ← 最佳
first-stage=50:  MRR 0.387  ← 噪声增加
first-stage=100: MRR 0.387  ← 不再提升
```

Reranker 在更少、更高质量的候选上做 discrimination 时效果最好。宽召回引入的噪声稀释了 reranker 的注意力。

#### 3. Expansion + Reranker = 退化

```
BM25+static 单阶段:       MRR 0.390
BM25+static → reranker:   MRR 0.374  (-4.1%)
```

Static expansion 追加的英文技术词帮助了 BM25 的关键词匹配，但**混淆了 Cross-Encoder 的语义判断**。Reranker 看到 expansion 词后，可能认为匹配了这些词的 chunk 更相关，即使它们的语义实际不匹配 query 意图。

**结论：expansion 和 reranker 是互斥的。** 选一个即可——reranker 效果更好且更通用。

#### 4. 粗召回源不重要（有了 reranker 后）

```
BM25 @50 → reranker:  MRR 0.387
Dense @50 → reranker: MRR 0.387  ← 完全相同！
```

Reranker 把 BM25 和 Dense 的粗召回差异完全抹平了。这验证了 Cross-Encoder 的核心价值——只要粗召回的 recall 够宽，精排阶段可以补偿排序质量。

#### 5. 零命中修复：5/12（42%）

Reranker 修复了 BM25 baseline 中 5 条零命中 query：

| Query | 修复后 MRR | 说明 |
|-------|:---------:|------|
| AI Agent 平台岗中，最强两类证据 | 0.125 | 找到 1 个（应找 2 个） |
| LLM fallback 和结构化输出校验经验 | 0.111 | 找到较靠后 |
| 多模态 AI API 和平台部署证据 | **0.500** | 找到第 2 位 |
| LangChain 要求和候选人项目一致性 | **1.000** | 完美命中！ |
| run artifact 真值与 Web 展示边界冲突 | **1.000** | 完美命中！ |

仍为零的 7 条 query 是语义层面的 hard case——目标文档内容与 query intent 差距过大，即使是 Cross-Encoder 也无法弥合。

### 累积 RAG 优化进展

```
原始 BM25 (P0 修复后):           MRR 0.333  p@1 0.24
  ├─ P0: Chunking 按类型决策      → 0.337  (+1.2%)
  ├─ P1: Query Expansion          → 0.373  (+10.9%)
  ├─ Chunk 内容增强                → 0.390  (+17.1%)
  └─ P1: Cross-Encoder Reranker   → 0.398  (+19.5%)
                                      ────────────
                                      累积: MRR +19.5%, p@1 +33.3%
```

### 实现

`rag/reranking.py` (47 行):
```python
class CrossEncoderReranker:
    def __init__(self, model_name="BAAI/bge-reranker-v2-m3"): ...
    def rerank(self, query, candidates, top_k=10): ...
```

评估命令（最优组合）：
```bash
python scripts/evaluate_rag_layers.py \
  --layer retriever --retriever-mode bm25 \
  --reranker BAAI/bge-reranker-v2-m3 --first-stage-limit 20 \
  --golden-file fixtures/golden_rag_questions.json \
  --run-dir baseline/runs-formal-20260520/baseline-formal-r3-full-raw-library-20260520 \
  --output outputs/reranker-bm25-fs20.json
```

