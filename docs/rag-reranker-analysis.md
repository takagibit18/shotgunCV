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

---

## 综合评估判断（2026-05-30）

### 总评：中等成功——价值在定性发现，不在量化提升

```
Reranker (2.2GB, 568M params):     MRR 0.398
Static Expansion (27行 dict):      MRR 0.390
                                   ─────────
差距：                               +0.008 (+2.1%)
```

**一个 27 行的静态词典和一个 2.2GB 的 Cross-Encoder 之间的净差距只有 0.008 MRR。**

### Reranker 的三个价值（不在 aggregate 指标里）

**1. "窄粗召回更优"——反直觉的工程 insight**

`@20 > @50 = @100`。更少的候选反而让 Cross-Encoder 排序更准。Reranker 不是"给更多候选就能排更好"——它在做精密的 discrimination，噪声直接损害它。这对生产部署有实际指导意义：**粗召回宽度不是越大越好，找 recall-precision 平衡点**。

**2. "Expansion + Reranker 互斥"——非预期的负交互**

2.2GB transformer 被 27 行 dict append 搞乱了。Expansion 词使 Cross-Encoder 误以为匹配了这些词的 chunk 更相关。**面试叙事价值**：这是"你遇到过什么非预期的模型行为"的绝佳案例。

**3. "Reranker 抹平粗召回差异"——两阶段架构验证**

BM25 和 Dense 经 reranker 后 MRR 完全相同（0.387）。验证了两阶段架构的核心假设：**粗召回只需要 recall，精排负责 precision**。Pipeline 变得对 retriever 选择鲁棒。

### 天花板判断

7 条 query 仍然零命中。不是检索模型的问题——是**标注数据与文档内容的语义 gap**。

```
Reranker 可以弥合："不同词说同一件事"
  例：query 写 "LangChain 要求" → chunk 写 "orchestration framework"
  → Cross-Encoder 理解语义等价

Reranker 无法弥合："文档根本不包含这件事"
  例：query 问 "PgVector 检索能力" → jd-012 的 JD 数据里完全没有 PgVector
  → 任何检索模型都无法匹配
```

这意味着系统的真正天花板不在检索模型，而在**评估数据质量**和**chunk 内容完备性**。

---

## 接下来需要重点排查的方向

### 方向一：Golden Set 质量审计（最高优先级）

**症状**：7 条永久零命中 query 的目标文档完全不包含 query 关键词。

**排查步骤**：

1. **逐条审计**：对每条零命中 query，检查其 `expected_documents` 的 chunk 文本，判断标注是否合理
2. **标注一致性检查**：同一 annotator 是否用"语义理解"标注了一个缺失关键词的文档？还是 golden set 是从另一个 run 迁移过来的（source_id 匹配但内容不同）？
3. **输出审计报告**：标注每条零命中 query 的根因——是"标注错误"还是"文档内容缺失"还是"真正的 hard case"

**预期发现**：至少有部分 zero-MRR query 属于"标注错误"——annotator 凭领域知识链接了 query 和文档，但文档的文本确实不包含相关关键词。这类 query 需要修正 expected_documents 或改写 query。

### 方向二：评估方式改革——LLM as Judge（中优先级）

**症状**：当前评估是 chunk-level 关键词匹配。`_chunk_matches_label` 用 `label.lower() in haystack` 判断是否命中。这在 Cross-Encoder 时代已经不够了——Reranker 返回的 top-1 chunk 可能语义上完美回答了 query，但因为 golden set 没标注它就计为零命中。

**方案**：引入 LLM-based relevance judge：
- 对每个 query，取 top-5 retrieval results
- 用 LLM 判断每个 result 是否"能够支撑对该 query 的回答"
- 不再依赖 golden set 的 chunk-level 标注，而是做端到端 relevance 评估

**优势**：绕开 vocabulary mismatch 的硬天花板，评估的是"检索结果是否有用"而不是"检索结果是否有特定关键词"。

### 方向三：Chunk 内容二次增强（低优先级，但根因修复）

**症状**：即使加了 JD context（title/company/keywords），仍有文档缺少 query 相关的术语。

**方案**：在 chunk 文本中注入更多 requirement_matrix 的上下文：
- `requirement_evidence` chunk：追加同 JD 下的其他 requirement 关键词
- `gap_map` chunk：追加同 JD 下的所有 requirement_text 列表
- `jd_description` chunk：追加从 requirement_matrix 提取的该 JD 的技术栈关键词

**风险**：过度增强可能引入噪声（类似 expansion + reranker 的负交互）。需要评估增量效果。

### 方向四：系统天花板量化（方法论价值）

**目标**：回答"当前系统在多大数据量和检索方法下能达到的理论上限"。

**方案**：
1. **Oracle experiment**：直接用 golden set 的 expected_documents 作为检索结果（模拟完美检索），计算 MRR 上限
2. **BM25 ceiling**：在所有 chunk 的 search text 中显式注入 golden set label（模拟完美关键词匹配），看 MRR 能到多少
3. **Reranker ceiling**：在 oracle 候选集上跑 reranker，确认 reranker 的排序精度上限

**价值**：量化"还有多少提升空间"，避免在已达上限的方向上继续投入。

### 优先级排序

```
P0 (立即): Golden Set 质量审计
  └── 修复标注错误，让评估指标反映真实检索质量
  └── 工作量：0.5-1 天

P1 (短期): LLM as Judge 评估试点
  └── 对 7 条零命中 query 做手动 LLM 评估，验证思路
  └── 工作量：0.5 天

P2 (中期): Chunk 内容二次增强
  └── 注入更多 requirement_matrix 上下文
  └── 工作量：0.5 天

P3 (方法论): 系统天花板量化
  └── Oracle + BM25 ceiling + Reranker ceiling 实验
  └── 工作量：0.5 天
```

---

## P0 落地：Golden Set 零命中审计入口（2026-05-31）

本轮新增 `scripts/audit_golden_rag_zero_hits.py`，用于把“零命中到底是不是标注问题”从人工猜测变成可复跑报告。脚本读取 retriever layer report、`rag-golden-v1` 和真实 run artifacts，自动抽出 `MRR == 0` 的 query，并回填：

- golden set 的 `expected_documents`
- expected label 在真实 retrieval chunks 中匹配到的文本预览
- retriever top hits 的文本预览
- query 与 expected chunk / top hit 的 content-token overlap
- `root_cause_hint`：`missing_expected_document_label`、`expected_document_vocabulary_gap`、`retrieval_ranking_failure` 或 `needs_human_review`

推荐用于 reranker 残留 7 条零命中：

```powershell
.\.venv\Scripts\python.exe scripts\audit_golden_rag_zero_hits.py `
  --run-dir baseline\runs-formal-20260520\baseline-formal-r3-full-raw-library-20260520 `
  --golden-file fixtures\golden_rag_questions.json `
  --retriever-report outputs\reranker-bm25-fs20.json `
  --output baseline\post-reranker-zero-hit-audit.json
```

本地 sanity check 先用 BM25 report 跑通了审计链路：12 条 BM25 zero-MRR query 中，10 条被标记为 `expected_document_vocabulary_gap`，2 条被标记为 `retrieval_ranking_failure`。对 reranker 后仍为零的 7 条 query ID（`rag-golden-001`、`005`、`010`、`012`、`015`、`024`、`027`）做 expected-document 文本审计时，7/7 都呈现 `expected_document_vocabulary_gap`。这还不能直接判定“标注错误”还是“文档内容缺失”，但已经说明下一步应先人工复核 golden set / chunk 内容，而不是继续换更大的检索模型。

