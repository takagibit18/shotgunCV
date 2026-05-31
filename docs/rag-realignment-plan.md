# RAG 架构纠偏计划

日期：2026-05-30（更新于同日）
分支：`docs/rag-realignment-plan` → `refactor/simplify-review-graph`（已合并 main）
状态：阶段一（纠偏重构）已完成，阶段二（RAG 优化）规划中

## 诊断结论

经过多轮评估（grid search 440组权重、30条golden set、21-run baseline），得出以下核心结论：

1. **Hybrid search 在任何权重下均差于纯 BM25**（最优 hybrid MRR=0.316 vs 纯BM25 MRR=0.333）。jd_id 过滤后搜索空间坍缩到 5-30 chunks，BM25 的 keyword matching 已提供最优排序信号，dense embedding（BGE-M3）等价于注入噪声。

2. **RAG evidence gate 与 evaluate 阶段冗余**。evaluate 已有 `requirement_matrix.evidence_status` + `evidence_refs` + `preflight_gates` + `fabrication_policy`，RAG gate 把结构化判定降级成了 chunk 搜索后计数。

3. **面试题生成不需要 RAG**。所需数据（JD画像、CV经历、需求矩阵）全部在 analyze artifact 中，是 prompt engineering + 结构化数据拼接，不是检索任务。

4. **RAG 真正不可替代的场景**：跨 artifact 自由查询、跨 run 历史记忆、JD 相似度检索。但这些依赖多 run 数据积累或功能重新定位。

## 保留资产

以下已有资产继续保留，无需重建：

| 资产 | 路径 | 保留原因 |
|------|------|----------|
| Golden RAG question set | `fixtures/golden_rag_questions.json` | 30条样本覆盖4种case type，label coverage=1.0，已验证可用 |
| 评估脚本 | `scripts/evaluate_rag_layers.py` | retriever+generator两阶段评估，precision/recall/MRR/NDCG全覆盖 |
| Grid search 框架 | `scripts/grid_search_hybrid_weights.py` | 预计算+离线搜索，后续 reranker/RRF 实验可直接复用 |
| 黄金集校验器 | `scripts/validate_golden_rag_set.py` | schema校验，保持黄金集质量 |
| 核心指标模块 | `packages/py-core/src/shotguncv_core/rag/metrics.py` | 无需改动 |
| InMemoryBM25Retriever | `packages/py-core/src/shotguncv_core/rag/retrieval.py` | MRR=0.333，稳定可用，作为默认检索器 |
| Chunk 构建逻辑 | `review_graph.py:_build_retrieval_chunks()` | 已覆盖5类source_type，后续补gap_map和resume_variant |
| Embedding 模型加载 | `packages/py-core/src/shotguncv_core/rag/embeddings.py` | 保留为可选/实验路径 |
| 检索 chunk DB schema | `packages/py-core/src/shotguncv_core/db/schema.py` | PostgreSQL+pgvector可选后端已就绪 |
| 21-run baseline 数据 | `baseline/` | 评估基线，后续对比参照 |
| 评估文档 | `docs/rag-retrieval-quality-analysis.md` | 记录 P0/P1 修复历史和 benchmark |
| no-answer abstention gate | `evaluate_rag_layers.py` | 已验证通过（0/5 leakage），后续 artifact search 场景复用 |

## 待重构（阶段一：纠偏 —— 已完成）

| 改动 | 涉及文件 | 原因 | 状态 |
|------|----------|------|------|
| 砍掉 RAG evidence gate | `review_graph.py:_retrieve_relevant_evidence` | 与 evaluate requirement_matrix+preflight_gate 冗余 | ✅ PR #62 |
| 简化 review graph | `review_graph.py:_compile_review_graph` | 8节点 fanout → 5节点 sequential，节点耗时 197ms → 12ms（16x） | ✅ `refactor/simplify-review-graph` |
| 拆出 interview_prep 为独立模块 | 新建 `interview_prep.py`，从 `review_graph.py` 移出 | 面试题生成不需要检索，直接消费 analyze artifact | ✅ PR #63 |
| inspect_score 改为读 artifact | `review_graph.py:_summarize_decision_context` | 直接读 scorecards/preflight_gates/requirement_matrix，随 #3 一并完成 | ✅ 随 review graph 简化完成 |
| gap_report 改为读结构化数据 | `review_graph.py:_generate_gap_report_from_artifacts` | 从 requirement_matrix.missing/mismatch 生成，新增 missing_requirements 字段 | ✅ 随 review graph 简化完成 |
| 废弃 dense/hybrid 默认路径 | — | **有意跳过**：本项目是练手项目，hybrid search/rerank/chunking 等优化策略需要细粒度、有量化指标地做，详见下方阶段二 | ⏭️ 转为阶段二 |

### 阶段一效果

| 指标 | 旧值 | 新值 |
|------|------|------|
| review graph 节点数 | 8 | 5 |
| 27 JDs 节点总耗时 | 197ms | 12ms (16x) |
| 事件日志写盘次数 | ~60 次/run | 10 次/run |
| 测试通过率 | — | 32/32 (100%) |

详见 `docs/review-graph-simplification.md`。

## 待新增（阶段一剩余）

| 新增 | 说明 | 状态 |
|------|------|------|
| RAG 决策日志条目 | 在 `docs/decision-log.md` 记录 hybrid 废弃、evidence gate 砍掉、RAG 重新定位的决策 | ⬜ |
| 兼容旧 review artifact | 旧 run 的 review 产物仍可读，降级兼容 | ⬜ |
| Golden set 扩展 | 追加 `artifact_query` 类样本（"我的K8s经验在哪些JD被提到"等） | ⬜ |
| 新增 artifact_search 评估模式 | `evaluate_rag_layers.py --layer artifact_search`，评估"给自然语言query找最相关chunk" | ⬜ |
| 实现 shotguncv query CLI | 跨 artifact 自由查询入口，BM25+metadata filter | ⬜ |
| 回归测试 | 确保 pipeline、deterministic fixtures 不受影响 | ⬜ |
## 修正后的架构

### RAG 功能边界

```
RAG 的职责（修正后）:
  ✅ 当前 run 的 artifact 自由问答
  ✅ 多 run 历史记忆（需数据积累）
  ✅ JD/经验/反馈相似检索
  ✅ 为其他模块提供"补充上下文"（不参与核心判定）

RAG 不参与:
  ❌ 证据充分性判定（由 evaluate requirement_matrix+preflight_gate 负责）
  ❌ 评分、排序、gate（由 evaluate 负责）
  ❌ 面试题/简历修改生成（由独立模块消费 analyze artifact 负责）
  ❌ 覆盖或替代任何 pipeline 阶段产物
```

### 与主流程的关系

```
ingest → analyze → generate → evaluate → plan → report
                                     │
                                     ▼
                              RAG (独立，手动触发)
                               ├── artifact search (自由查询)
                               ├── cross-run memory (多run历史)
                               └── JD similarity (相似检索)

interview_prep (独立，手动触发)
  └── 消费 analyze artifact，不依赖 RAG
```

### review graph 简化方案

简化前（9个节点）：

```
load_run_context → retrieve_relevant_evidence → merge_retrieval_results
                                                      │
                                        ┌─────────────┤
                                        ▼             ▼
                              inspect_score    generate_evidence_gap
                              _and_gates       _report
                                        │             │
                                        ▼             ▼
                              generate_interview   merge_review
                              _questions           _paths
                                        │             │
                                        ▼             ▼
                              generate_reference  generate_revision
                              _answers            _tasks
                                        │             │
                                        └──────┬──────┘
                                               ▼
                                     validate_against
                                     _fabrication_policy
                                               │
                                               ▼
                                     write_review_artifact
```

简化后（保留5个核心节点 + 可选检索节点）：

```
load_run_context
       │
       ▼
summarize_decision_context (读 scorecards + preflight_gates + requirement_matrix)
       │
       ▼
generate_gap_report_from_artifacts (从 missing/mismatch 生成，不调检索)
       │
       ▼
validate_against_fabrication_policy
       │
       ▼
write_review_artifact

可选 RAG 节点（仅在需要时有条件触发）:
  answer_artifact_query    (用户主动搜索)
  find_related_history     (跨run历史)
  find_similar_jds         (JD相似度)
```

### 面试题生成独立模块

```
analyze artifacts (已有)
  ├── jd_profiles.json          → JD画像
  ├── candidate_profile.json    → CV经历
  └── requirement_matrix.json   → 证据强弱 + fabrication_policy
         │
         ▼
   interview_prep (新增，轻量)
  ┌──────────────────────────────────────────┐
  │ system prompt (预设)                      │
  │ + JD画像 (title + requirements +          │
  │           interview_focus_areas)          │
  │ + CV经历 (experiences + projects +       │
  │           skills + evidence)              │
  │ + 需求矩阵 (evidence_status +             │
  │            fabrication_policy)            │
  │                                          │
  │ → LLM 生成:                               │
  │   1. JD针对性知识考察题                    │
  │   2. CV经历深挖追问                        │
  │   3. 证据薄弱区探测题                      │
  │   4. 严格遵守 fabrication_policy          │
  └──────────────────────────────────────────┘
```

## 阶段二：RAG 检索质量优化

> **决策背景**：阶段一原计划"废弃 dense/hybrid 为默认路径"被有意跳过。本项目是初学找实习用的练手项目，hybrid search、rerank、chunking 等 RAG 优化策略正是需要细粒度、有量化指标地实践的核心技能。砍掉它们等于放弃了最有学习价值的部分。

### 当前基线

| 指标 | BM25 | Dense (BGE-M3) | Hybrid (0.75/0.25) |
|------|------|----------------|---------------------|
| MRR | **0.333** | 0.278 | 0.316 |
| precision@1 | **0.24** | 0.20 | 0.24 |
| recall@10 | 0.52 | 0.52 | 0.52 |
| nDCG@10 | **0.359** | 0.331 | 0.348 |
| 单次查询耗时 | **1.8s** | 44.6s | 42.9s |

jd_id 过滤后搜索空间：5-30 文档 → 15-90 chunks（RecursiveCharacterTextSplitter 碎片膨胀）

### Chunking 策略诊断

**核心发现**：chunking 策略与搜索空间不匹配。

| 维度 | 典型 RAG 场景 | 本项目场景 |
|------|-------------|-----------|
| 搜索空间 | 数千～数百万文档 | 5-30 文档（jd_id 过滤后） |
| 文档长度 | 数页 PDF、长文 | 200-500 字符（单条 requirement） |
| 文档结构 | 无结构长文本 | 结构化 JSON artifact（每条已是独立语义单元） |
| chunking 目的 | 将长文档切成可检索的语义单元 | **不需要**——数据本身已做了结构化切分 |

`RecursiveCharacterTextSplitter` 在已有自然边界的文档上又切一刀，创造了不存在的碎片。同一文档的多个 chunk 在 rank 中互相竞争位置，挤占其他相关文档的检索结果。

详见 `E:\PycharmProjects\知识库\Agent知识库\raw\sources\events\ShotgunCV RAG chunking 策略诊断与简历叙事事件.md`

### 优化路线图（按优先级）

```
P0: Chunking 按文档类型决策 ──→ P1: Cross-Encoder Reranker ──→ P2: Query Expansion
        │                              │                              │
        └──→ P3: 多尺寸 Chunking       │                              │
                                       │                              │
                              P4: Hybrid Search 修复 ←────────────────┘
                                       │
                              P5: Graded Relevance 评估升级
```

#### P0 — Chunking 按文档类型决策（0.5-1天）

| 项目 | 说明 |
|------|------|
| **问题** | 所有 7 种 source_type 无差别通过 `RecursiveCharacterTextSplitter(chunk_size=900)`，搜索空间从 5-30 文档膨胀为 15-90 chunks，碎片在 rank 中互相竞争 |
| **方案** | 结构化短文档不做 chunking，直接整文档向量化；仅长文档保留切分 |
| **涉及模块** | `rag/documents.py` |
| **量化指标** | precision@1、MRR（预期 +15-25%），搜索空间大小，检索延迟 |
| **面试价值** | ⭐⭐⭐ "chunking 不是 RAG 必选项" —— 展示工程判断力而非盲目套用标准流程 |

| source_type | 决策 | 理由 |
|-------------|------|------|
| `requirement_evidence` | **不切** | 200-500 chars，单条 requirement，语义自包含 |
| `jd_description` | **不切** | 300-800 chars，title+requirements 集合，语义自包含 |
| `gap_map` | **不切** | 200-600 chars，单条 gap item，语义自包含 |
| `candidate_evidence` | **切** | 500-2000 chars，多段多主题拼接 |
| `resume_variant` | **切** | 1000-3000 chars，完整简历变体 |
| `jd_input` | **切** | 变化大，原始输入文本 |

#### P1 — Cross-Encoder Reranker（2-3天）

| 项目 | 说明 |
|------|------|
| **问题** | 单阶段检索（BM25/dense/hybrid 直接出 top-k），无精排。Reranker 是 RAG 性能提升最成熟的手段 |
| **方案** | 新建 `rag/reranking.py`，集成 `BAAI/bge-reranker-v2-m3`。Retriever 召回 top-50 → Cross-Encoder 精排 top-10 |
| **涉及模块** | `rag/reranking.py`(新建)、`scripts/evaluate_rag_layers.py`(+--reranker flag)、`rag/retrieval.py` |
| **量化指标** | MRR、nDCG@10（预期 MRR 0.33 → 0.45-0.55） |
| **面试价值** | ⭐⭐⭐⭐⭐ 两阶段检索是 RAG 面试必考题：Bi-Encoder vs Cross-Encoder、精度-延迟 trade-off |

#### P2 — Query Expansion 中英文对齐（1-2天）

| 项目 | 说明 |
|------|------|
| **问题** | 30 条 query 全是中文自然语言，但 chunks 中技术标识符是英文（source_id、关键词）。BM25 分词器对中英混合处理不够好 |
| **方案** | 检索前对 query 做 expansion：提取技术关键词，追加英文对应词。基于 golden set 构建中文→英文技术词映射表 |
| **涉及模块** | `rag/retrieval.py`、`scripts/evaluate_rag_layers.py`(+--query-expansion) |
| **量化指标** | MRR、recall@10（预期 MRR 0.33 → 0.38-0.42） |
| **面试价值** | ⭐⭐⭐⭐ Query understanding 是 RAG 三大优化维度之一 |

#### P3 — 多尺寸 Chunking + 语义切分（3-4天）

| 项目 | 说明 |
|------|------|
| **问题** | 当前只有一种 chunk 尺寸（900/120），不同 source_type 的最优尺寸不同 |
| **方案** | 参数化 `_split_text()` 的 chunk_size/overlap，为每种长文档 source_type 配置不同参数。增加 `SemanticSplitter`（基于 embedding cosine similarity 检测语义边界） |
| **涉及模块** | `rag/documents.py`、`scripts/evaluate_rag_layers.py`(+--chunk-strategy) |
| **量化指标** | MRR 按 source_type 分组对比 |
| **面试价值** | ⭐⭐⭐⭐⭐ Chunking 策略是 RAG 工程中最被低估的环节 |

#### P4 — Hybrid Search 修复 + 权重细调（3-5天）

| 项目 | 说明 |
|------|------|
| **问题** | Hybrid 在任何权重下均劣于纯 BM25。需要诊断 dense 在哪些 query 上有正向贡献，做 query-level 动态权重 |
| **方案** | 1) 按 case_type 分组评估 hybrid vs BM25 2) query-level 自适应权重 3) 尝试不同 embedding 模型对比 |
| **涉及模块** | `rag/retrieval.py`、`scripts/evaluate_rag_layers.py`、`scripts/grid_search_hybrid_weights.py`、`rag/embeddings.py` |
| **量化指标** | 按 case_type 的 MRR、hybrid 超过 BM25 的 query 比例 |
| **面试价值** | ⭐⭐⭐⭐⭐ 面试高频：hybrid search 什么时候有效？为什么你的 hybrid 不如 BM25？ |

#### P5 — Graded Relevance + 评估体系升级（0.5-1天）

| 项目 | 说明 |
|------|------|
| **问题** | nDCG 使用 binary relevance。Golden set 已有 `document_roles`（primary/supporting/conflicting）可做 graded relevance |
| **方案** | 修改 `metrics.py:_ndcg_at_k()` 支持加权 relevance（primary=3, supporting=1, conflicting=0） |
| **涉及模块** | `rag/metrics.py`、`fixtures/golden_rag_questions.json`、`scripts/evaluate_rag_layers.py` |
| **量化指标** | nDCG graded vs binary 对比 |
| **面试价值** | ⭐⭐⭐ 理解 IR 评估指标的细节差异（MRR vs nDCG vs MAP） |

### 涉及模块总览

| 模块 | P0 | P1 | P2 | P3 | P4 | P5 |
|------|:--:|:--:|:--:|:--:|:--:|:--:|
| `rag/documents.py` | ✅ | | | ✅ | | |
| `rag/retrieval.py` | | ✅ | ✅ | | ✅ | |
| `rag/reranking.py` **(新建)** | | ✅ | | | | |
| `rag/metrics.py` | | | | | | ✅ |
| `rag/embeddings.py` | | | | | ✅ | |
| `scripts/evaluate_rag_layers.py` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `scripts/grid_search_hybrid_weights.py` | | | | | ✅ | |
| `fixtures/golden_rag_questions.json` | | | | | | ✅ |

## 设计原则

- `run_dir` 继续是唯一业务执行真源
- RAG 只读 artifact，不写入核心评分/排序/判定
- 旧 run 缺少新产物时兼容降级
- deterministic fixtures 可回放性不受影响
- BM25 为默认检索器，dense/hybrid 保留为实验模式（阶段二重点优化对象）
- Chunking 是有意识的选择，不是默认操作——按文档类型决策
- 所有 RAG 优化必须有量化的 before/after 指标对比
- 文档中文、代码注释英文、commit message 英文
