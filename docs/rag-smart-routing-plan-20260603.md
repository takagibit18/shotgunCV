# RAG 智能路由闭环规划

日期：2026-06-03

分支背景：`muti_documents_enhancement`

## 背景

当前 RAG 评测已经区分了三个口径：

- `single`：真实 headline，不使用 `expected_documents` 做分流。
- `hybrid single`：真实候选策略，当前全量指标优于 BM25 single，但部分多文档切片退化。
- `decomposed oracle`：上限诊断。它读取 golden 的 `expected_documents` 来推导 `source_type`、`jd_id` 和 evidence role，因此不能作为真实未标注场景指标。

下一版目标不是继续堆 oracle decomposition，而是实现 **non-oracle 智能路由闭环**：只基于 query 文本、broad top hits 和可观测 metadata，决定是否 rewrite、是否 decomposition、是否启用 hybrid、是否触发 no-answer support check。

## 当前瓶颈

### 1. 语义模糊 / 口语表达

当前 `synonym_expression` 和 `fuzzy_colloquial` 对 BM25 不稳定：

- `synonym_expression`：BM25 single `Recall@3=0.000`，`All Expected=0.333`
- `fuzzy_colloquial`：BM25 single `All Expected=0.500`
- Hybrid 对 `fuzzy_colloquial` 有明显改善：`All Expected=0.750`

说明这类 query 的瓶颈是词面不匹配，需要 query rewrite / hybrid，而不是 source_type oracle filter。

### 2. 复杂多证据问题

当前 `multi_document` 与 `cross_section` 的 supporting evidence 覆盖弱：

- `multi_document`：BM25 single `All Primary=0.636`，`All Expected=0.273`
- `cross_section`：BM25 single `All Primary=0.667`，`All Expected=0.000`

Oracle decomposition 能提升一部分 `multi_document`，但 `cross_section` 仍弱，说明真实路线需要拆语义维度，而不只是套 `source_type` filter。

### 3. 矛盾 / 过期 / 风险类问题

`stale_or_conflicting` 对 source-type-aware routing 很敏感：

- BM25 single `All Expected=0.333`
- Hybrid single `All Expected=0.667`
- Decomposed oracle `All Expected=0.833`

说明这类 query 需要主动查 `gap_map`、`ranking_explanation`、risk flags 等 evidence layer。

### 4. no-answer 仍不是检索分数问题

当前 no-answer：

- BM25 single false positive：`4/9`
- Hybrid 0.3/0.7 false positive：`1/9`
- 两者 gate 仍为 `failed`

说明 hybrid 可以减少相似概念干扰，但不能替代 support / entailment 判断。

## 目标

下一版本实现一个可评测、可解释、非 oracle 的智能路由层。

目标能力：

1. 对语义模糊 query 自动 rewrite。
2. 对复杂多证据 query 触发 query decomposition。
3. 对矛盾、风险、差距类 query 主动加入 gap/ranking/risk evidence stage。
4. 对强推断 no-answer query 触发 support / entailment gate。
5. 所有路由决策都写入 report，能够审计为什么 rewrite、为什么 decomposition、为什么 abstain。

非目标：

- 不读取 `expected_documents`。
- 不把 decomposed oracle 指标当 headline。
- 不使用人工标注的 `case_type` / `robustness_category` 做真实路由。
- 不先引入大模型 router。第一版优先用可解释规则 + broad retrieval evidence。

## 设计原则

### 1. Non-oracle

真实路由只能使用：

- 原始 query 文本
- broad retrieval top-k hits
- hit metadata：`source_type`、`jd_id`、score、source_id、artifact_path
- corpus 可观测统计：source_type 分布、top score、score gap

禁止使用：

- `expected_documents`
- golden `case_type`
- golden `robustness_category`
- golden answer / must_cover_points

### 2. 先 broad，再 route

第一步永远先做一个 broad retrieval：

- BM25 broad top-k
- 可选 hybrid broad top-k
- 收集 source_type / jd_id / score 分布

然后根据 query intent 和 broad hits 决定后续是否 rewrite / decomposition。

### 3. 路由必须可解释

每个 query report 增加：

- `routing_strategy`
- `routing_reasons`
- `rewrite_terms`
- `decomposition_stages`
- `support_gate_status`
- `fallback_used`
- `oracle_free: true`

### 4. Headline 与诊断分离

未来报表至少保留四个口径：

| 口径 | 是否 headline | 用途 |
| --- | --- | --- |
| `bm25_single` | 是 | 保守真实基线 |
| `hybrid_single` | 是 | 当前真实候选 |
| `smart_router_non_oracle` | 是 | 下一版主策略 |
| `decomposed_oracle` | 否 | 上限诊断 |

## 路由策略

### A. 语义模糊类 Query Rewrite

触发条件：

- query 包含口语表达：`像不像`、`会不会`、`能不能做`、`是不是偏`、`有没有那种`
- query 包含同义表达：`工具链`、`搜出来准不准`、`别乱跑`、`idea 做成 demo`
- BM25 top score 低或 top hits 分散
- hybrid top-k 与 BM25 top-k 差异大

rewrite 行为：

- 保留原始 query。
- 追加规范化技术词和业务词。
- 追加 evidence layer hint，但不强制 source_type filter。

示例：

| 原始表达 | rewrite terms |
| --- | --- |
| `AI agent 工具链` | `LangGraph`, `tool calling`, `agent workflow`, `tool execution`, `evaluation` |
| `搜出来准不准的测试` | `retrieval evaluation`, `MRR`, `NDCG`, `Recall`, `Precision`, `golden set` |
| `能跑起来的 AI 产品原型` | `AI prototype`, `demo`, `agent project`, `automation workflow` |
| `工具别乱跑` | `tool safety`, `sandbox`, `permission gate`, `path safety` |

第一版实现方式：

- 规则词典 + `_tokens()`。
- 输出 `expanded_query`。
- report 写入 `query_rewrite.strategy = "semantic_alias"`。

验收指标：

- `synonym_expression` 的 `Recall@3` 高于 BM25 single。
- `fuzzy_colloquial` 的 `All Expected` 不低于 hybrid single。
- no-answer false positive 不增加。

### B. 复杂问题 Query Decomposition

触发条件：

- query 中有多子问题连接词：`分别`、`同时`、`以及`、`一起来看`、`合并`、`对比`、`哪些支持哪些保守`
- broad hits 覆盖多个 `source_type` 或多个 `jd_id`
- top-k 中 primary evidence 出现，但 supporting evidence 缺失

decomposition stage 类型：

| Stage | 目标 |
| --- | --- |
| `primary` | 找最直接回答 query 的证据 |
| `candidate_context` | 找候选人项目、教育、技能背景 |
| `requirement_context` | 找 JD requirement / evidence status |
| `gap_context` | 找缺口、风险、弱项 |
| `ranking_context` | 找 ranking explanation、decision summary、risk flags |
| `fallback` | 原 query broad retrieval 补足 top-k |

关键差异：

- stage 不从 `expected_documents` 生成。
- stage 由 query intent + broad hits 推断。
- `jd_id` 只允许来自 broad top hits 的高置信候选，而不是 golden label。

第一版实现方式：

- 新增 `smart` query strategy。
- `smart` 内部先跑 broad retrieval。
- 根据 broad hits 生成 stage filters。
- stage filter 使用 soft quota，不使用硬过滤替代 broad retrieval。

验收指标：

- `multi_document` 的 `All Expected` 高于 BM25 single。
- `cross_section` 的 `All Expected` 从 `0.000` 有可观测改善。
- `All Primary` 不低于 BM25 single 太多。

### C. 矛盾 / 风险 / 差距 Routing

触发条件：

- query 包含：`风险`、`缺口`、`不足`、`保守`、`不能高置信`、`矛盾`、`过期`、`低置信`、`为什么排序`
- broad hits 中存在 `gap_map` / `ranking_explanation`
- query 明确要求边界判断

行为：

- broad top-k 保留。
- 追加 `gap_context` stage。
- 追加 `ranking_context` stage。
- 对 OCR 低置信 query，追加 `low confidence`, `ocr noise`, `normalized keywords`。

验收指标：

- `stale_or_conflicting` 的 `All Expected` 接近 hybrid 或 oracle 上限。
- false positive 不增加。

### D. Adaptive Hybrid

固定 hybrid 0.3/0.7 全量表现好，但多文档和 cross_section 有退化。

下一版策略：

| Query 类型 | 检索策略 |
| --- | --- |
| 精确事实 / source_id / JD requirement | BM25 优先 |
| 口语 / 同义 / 低信息 | hybrid 0.3/0.7 |
| 多文档 / 跨章节 | BM25 broad + stage quota |
| 矛盾 / 风险 | hybrid broad + gap/ranking stage |
| no-answer 强推断 | candidate evidence + support gate |

验收指标：

- 全量 MRR 不低于 hybrid single。
- `multi_document` 不低于 BM25 single。
- no-answer false positive 不高于 hybrid single。

### E. no-answer Support / Entailment Gate

触发条件：

- query 包含强推断词：`能否证明`、`是否等于`、`专家`、`资深`、`平台工程经验`、`模型训练`、`微调`、`生产运维`
- 检索结果只是相似概念，但没有直接支持 claim
- top hit 分数高，但 evidence text 与 claim 有强弱不匹配

第一版规则：

- 只检索 `candidate_evidence` 作为候选支持证据。
- 判断 query claim 是否被候选证据直接支持。
- 若只有相似词命中，标为 `needs_review` 或 `abstained`。

report 增加：

- `support_gate.triggered`
- `support_gate.claim`
- `support_gate.support_status`
- `support_gate.reason`
- `support_gate.blocked_generator`

验收指标：

- no-answer false positive 从 hybrid 当前 `1/9` 降到 `0/9`。
- answerable query 的 All Primary 不明显下降。

## 评测设计

### 新增策略

建议新增 CLI 参数：

```powershell
--query-strategy smart
--router-mode rule_based
--router-broad-limit 20
--enable-support-gate
```

报表输出：

- `baseline/smart-routing-20260603/bm25-single.json`
- `baseline/smart-routing-20260603/hybrid-single.json`
- `baseline/smart-routing-20260603/smart-router-rule-based.json`
- `baseline/smart-routing-20260603/decomposed-oracle-upper-bound.json`

### 关键指标

整体：

- MRR
- Recall@3 / Recall@10
- Weighted Recall@10
- All Primary Hit
- All Expected Hit
- no-answer false positive count
- no-answer abstention rate

切片：

- `multi_document`
- `stale_or_conflicting`
- `cross_section`
- `synonym_expression`
- `fuzzy_colloquial`
- `ocr_regression`
- `similar_concept_interference`

新增路由指标：

- `rewrite_trigger_rate`
- `decomposition_trigger_rate`
- `support_gate_trigger_rate`
- `route_fallback_rate`
- `route_error_examples`
- `oracle_free = true`

## 实施步骤

### Step 1：抽象 query plan

新增轻量数据结构：

```python
{
  "strategy": "smart_router",
  "original_query": "...",
  "expanded_query": "...",
  "routes": [
    {"name": "broad", "query": "...", "retriever_mode": "bm25", "limit": 20},
    {"name": "rewrite", "query": "...", "retriever_mode": "hybrid", "limit": 10},
    {"name": "gap_context", "query": "...", "source_type": "gap_map", "limit": 3}
  ],
  "reasons": ["fuzzy_colloquial_pattern", "broad_hits_multi_source_type"],
  "oracle_free": True
}
```

### Step 2：实现 rule-based router

函数建议：

- `build_smart_query_plan(query, broad_hits, corpus_stats) -> QueryPlan`
- `rewrite_fuzzy_query(query) -> RewriteResult`
- `detect_complex_query(query) -> list[str]`
- `detect_no_answer_strong_claim(query) -> ClaimSignal`

### Step 3：接入评测脚本

- `--query-strategy smart`
- `evaluate_labeled_retrieval_queries()` 支持 `query_plan`
- report 记录 route stages 与路由原因

### Step 4：跑四路对照

必须同时跑：

1. BM25 single
2. Hybrid single
3. Smart router non-oracle
4. Decomposed oracle upper bound

只有第 1-3 个能进入 headline。

### Step 5：错误分析闭环

每轮至少输出：

- `smart_router_win_examples`
- `smart_router_loss_examples`
- `route_false_positive_examples`
- `support_gate_blocked_examples`
- `multi_document_missing_supporting_examples`

## 验收门槛

第一版 smart router 达标条件：

| 指标 | 目标 |
| --- | --- |
| 全量 MRR | >= Hybrid single - 0.02 |
| 全量 All Expected | >= Hybrid single - 0.02 |
| `multi_document` All Expected | > BM25 single |
| `cross_section` All Expected | > 0.000 |
| `stale_or_conflicting` All Expected | >= Hybrid single |
| no-answer false positives | 0 / 9 |
| oracle-free | true |

如果 smart router 全量略低于 hybrid，但 no-answer 和多文档显著改善，可以作为候选继续迭代；否则保持 hybrid single 作为主候选。

## 风险

1. 规则 router 可能过拟合当前 golden query 表达。
2. rewrite 可能增加 no-answer false positive。
3. stage filter 过硬会漏掉 supporting evidence。
4. hybrid 对 cross_section 可能继续退化。
5. support gate 如果太保守，会误伤 answerable query。

缓解方式：

- 所有 rewrite 保留原 query fallback。
- source_type filter 用 quota，不完全替代 broad retrieval。
- 每个 route 必须记录 reason。
- 报表必须同时展示 win/loss examples。
- headline 禁止使用 oracle 指标。

## 决策

下一版本优先实现 `smart_router_non_oracle`，不再扩大 oracle decomposition。短期目标是把当前三个独立优化方向串成闭环：

1. 模糊/同义 query → semantic rewrite + hybrid。
2. 复杂多证据 query → non-oracle decomposition + evidence quota。
3. 矛盾/风险 query → gap/ranking routing。
4. no-answer 强推断 query → support / entailment gate。

最终判断以真实 headline 为准：`BM25 single`、`Hybrid single`、`Smart router non-oracle`，而不是 `decomposed oracle`。
