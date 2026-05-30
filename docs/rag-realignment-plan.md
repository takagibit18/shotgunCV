# RAG 架构纠偏计划

日期：2026-05-30
分支：`docs/rag-realignment-plan`
状态：规划阶段，待实施

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

## 待重构

| 改动 | 涉及文件 | 原因 | 工作量 |
|------|----------|------|--------|
| 砍掉 RAG evidence gate | `review_graph.py:_retrieve_relevant_evidence` | 与 evaluate requirement_matrix+preflight_gate 冗余 | 0.5天 |
| 废弃 hybrid/dense 为默认路径 | `review_graph.py:_build_review_retriever` | 任何权重下 hybrid < 纯BM25 | 0.5天 |
| 拆出 interview_prep 为独立模块 | 新建 `interview_prep.py`，从 `review_graph.py` 移出 | 面试题生成不需要检索，直接消费 analyze artifact | 1-2天 |
| 简化 review graph | `review_graph.py:_compile_review_graph` | 砍掉冗余 merge 节点和 RAG-dependent 节点 | 1天 |
| inspect_score 改为读 artifact | `review_graph.py:_inspect_score_and_gates` | 不依赖检索结果，直接读 scorecards/preflight_gates | 0.5天 |
| gap_report 改为读结构化数据 | `review_graph.py:_generate_evidence_gap_report` | 从 requirement_matrix.missing/mismatch 生成，不依赖检索 | 0.5天 |
| BM25 仅用于 artifact search | `retrieval.py` | 保留 InMemoryBM25Retriever，移除 InMemoryHybridRetriever 默认使用 | 0.5天 |
| dense/hybrid 降级为实验模式 | CLI 参数 `--retriever experimental` | 保留代码但不进入默认路径 | 0.5天 |

## 待新增

| 新增 | 说明 | 工作量 |
|------|------|--------|
| `shotguncv query` CLI 命令 | 跨 artifact 自由查询入口，BM25+metadata filter | 1-2天 |
| artifact_search 评估模式 | `evaluate_rag_layers.py --layer artifact_search`，评估"给自然语言query找最相关chunk" | 1天 |
| Golden set 扩展 | 追加 `artifact_query` 类样本（"我的K8s经验在哪些JD被提到"等） | 0.5天 |
| RAG 决策日志条目 | 在 `docs/decision-log.md` 记录 hybrid 废弃、evidence gate 砍掉、RAG 重新定位的决策 | 0.5天 |

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

## 实施路线图

| 序号 | 任务 | 工作量 | 前置依赖 | 预期效果 |
|------|------|--------|----------|----------|
| 1 | 新建分支 + 写本文档 | 0.5天 | 无 | 记录诊断结论和纠偏方案 |
| 2 | 砍掉 RAG evidence gate | 0.5天 | 1 | 消除与evaluate的重复判定 |
| 3 | 简化 review graph | 1天 | 2 | 节点从9个减到5个，职责清晰 |
| 4 | 废弃 dense/hybrid 默认路径 | 0.5天 | 2 | 降低复杂度，BM25-only 默认 |
| 5 | 拆出 interview_prep | 1-2天 | 1 | 面试题生成走结构化artifact，质量更稳 |
| 6 | inspect_score/gap_report 改为读 artifact | 0.5天 | 2,5 | 不依赖检索，直接消费结构化数据 |
| 7 | 兼容旧 review artifact | 0.5天 | 2-6 | 旧run的review产物仍可读 |
| 8 | 更新 decision-log | 0.5天 | 2-6 | 记录架构决策 |
| 9 | 扩展 golden set（artifact_query类） | 0.5天 | 7 | 适配新定位的评估样本 |
| 10 | 新增 artifact_search 评估模式 | 1天 | 9 | 评估开放自然语言query的检索质量 |
| 11 | 实现 shotguncv query CLI | 1-2天 | 8 | RAG放到真正不可替代的位置 |
| 12 | 回归测试 | 0.5天 | 2-11 | 确保 pipeline、deterministic fixtures 不受影响 |

## 设计原则

- `run_dir` 继续是唯一业务执行真源
- RAG 只读 artifact，不写入核心评分/排序/判定
- 旧 run 缺少新产物时兼容降级
- deterministic fixtures 可回放性不受影响
- BM25 为默认检索器，dense/hybrid 保留为实验模式
- 文档中文、代码注释英文、commit message 英文
