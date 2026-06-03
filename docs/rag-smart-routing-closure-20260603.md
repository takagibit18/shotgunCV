# RAG 智能路由闭环记录 - 2026-06-03

## 范围

本轮目标是在 `rag-smart-routing-plan-20260603.md` 的基础上，完成一个最小可观测闭环：

- 引入 non-oracle smart router，不读取 `expected_documents`、`case_type`、`robustness_category` 做真实路由决策。
- 只基于 query 文本、broad top hits、hit metadata 生成 query plan。
- 将 route plan、rewrite、decomposition、support gate、win/loss examples 写入 retriever report。
- 跑四路对照：BM25 single、hybrid single、smart router、decomposed oracle upper bound。

最终实现落点：

- `packages/py-core/src/shotguncv_core/rag/retrieval.py`
  - `SmartRouterRetriever`
  - `build_smart_query_plan`
  - semantic rewrite / complex query / risk query / strong claim detectors
- `packages/py-core/src/shotguncv_core/rag/metrics.py`
  - query-level `query_plan`
  - query-level `case_type` / `golden_layer` / `robustness_category` 观测透传
- `scripts/evaluate_rag_layers.py`
  - `--query-strategy smart`
  - `--router-broad-limit`
  - `--enable-support-gate`
  - `smart_routing_observability`
  - no-answer `support_gate_summary`

## 评测设置

Golden set：

```powershell
fixtures\golden_rag_questions.json
```

Run artifact：

```powershell
baseline\real-cv-golden-rebuild-20260602
```

Coverage gate：

```text
expected labels: 35
matched labels: 35
coverage_ratio: 1.0
```

输出目录：

```powershell
baseline\smart-routing-20260603\
```

报告文件：

```powershell
baseline\smart-routing-20260603\bm25-single.json
baseline\smart-routing-20260603\hybrid-single.json
baseline\smart-routing-20260603\smart-router-rule-based.json
baseline\smart-routing-20260603\decomposed-oracle-upper-bound.json
```

## 路由构建思路

### 1. 永远先做 broad observation

`SmartRouterRetriever.search()` 会先跑 broad BM25 和 broad hybrid retrieval。router 只读取可观测 hit metadata：

- `source_type`
- `jd_id`
- `source_id`
- `artifact_path`
- score distribution
- source type distribution
- JD distribution

这样可以保持 oracle-free，同时给 router 足够上下文判断 query 是简单事实、语义模糊、多文档、风险/缺口，还是 no-answer 强推断问题。

### 2. hybrid 是生产 anchor，不是被替换对象

这轮最大的设计修正是：smart routing 不应该替换所有 query 的 hybrid single。Hybrid single 已经是最强真实 baseline。Smart routing 应该：

- 在 hybrid 已经排对时保留 hybrid top results；
- 只在能提升覆盖时追加 route-specific evidence；
- 把 broad retrieval 当兜底补位，而不是一开始填满 top-k。

有路由信号的 query，最终 route 形态大致如下：

```json
[
  {"name": "hybrid_anchor", "retriever_mode": "hybrid", "limit": 5},
  {"name": "rewrite", "retriever_mode": "hybrid"},
  {"name": "candidate_context", "retriever_mode": "hybrid"},
  {"name": "requirement_context", "retriever_mode": "hybrid"},
  {"name": "jd_context", "retriever_mode": "hybrid"},
  {"name": "risk_primary_context", "retriever_mode": "hybrid"},
  {"name": "gap_context", "retriever_mode": "hybrid"},
  {"name": "ranking_context", "retriever_mode": "hybrid"},
  {"name": "broad_fallback", "retriever_mode": "hybrid"}
]
```

不是每条 query 都会得到所有 route，具体 route 由信号触发。

### 3. 使用路由信号，不使用 golden 标签

当前信号族：

| 信号 | 来源 | 行为 |
| --- | --- | --- |
| semantic alias | query text | 追加规范化技术词，走 hybrid rewrite |
| complex connector | query text | 追加 candidate / requirement / JD context stages |
| broad multi-source-type | broad hits | 追加 context stages |
| broad multi-JD | broad hits | 保留 top 3 JD contexts，而不是只赌一个 JD |
| risk/gap intent | query text 或 broad hits | 追加 primary requirement + gap/ranking stages |
| strong claim | query text | 对 candidate evidence 运行 no-answer support gate |

### 4. route quota 是软组合

router 不把最终结果硬过滤成单一 source type。它会运行 stage-specific searches，按 result key 去重，然后用 fallback 补齐剩余位置。这样即使某个 route 判断不准，也不会成为唯一证据路径。

## 中途踩的坑与修正

### 坑 1：用错 run 目录，导致无法观测

一开始使用：

```powershell
apps\runs\xinyuxing-v030-default-llm
```

这个 run 和当前 golden set 不匹配，coverage gate 失败：

```text
matched labels: 0 / 35
```

根因：

- 当前 `fixtures\golden_rag_questions.json` 对应 real CV rebuild baseline。
- 正确 run 是 `baseline\real-cv-golden-rebuild-20260602`。

修正：

- 跑 retrieval metrics 前先用正确 run 校验 golden coverage。
- 把 coverage gate failure 视为观测设置问题，而不是 router 策略问题。

### 坑 2：broad route 抢占 top-k，smart routes 根本没生效

第一版 smart plan 把 `broad` 放在第一位：

```json
[
  {"name": "broad", "retriever_mode": "bm25", "limit": 20},
  {"name": "rewrite", "retriever_mode": "hybrid"},
  {"name": "gap_context", "retriever_mode": "hybrid"}
]
```

由于结果组合逻辑在 top-k 填满后就停止，后面的 rewrite / gap / ranking route 没机会加入结果集。报告内部看起来有 smart route，但指标和 BM25 完全一致。

修正：

- 将 broad retrieval 移到最后，命名为 `broad_fallback`。
- 只有没有任何 smart routing 信号时，才单独使用 `broad` route。

影响：

- smart route 开始真正区别于 BM25。
- 第一版有效 smart 指标达到 MRR `0.649090`，高于 BM25 `0.598436`。

### 坑 3：route-specific stages 提升覆盖但拉低 MRR

broad fallback 修正后，smart routing 的 All Expected 从 `0.764706` 提到 `0.803922`，但 MRR 下滑，因为 stage route 把不够精确的 context 插到了 hybrid 已经排好的好结果前面。

根因：

- router 当时像 replacement ranker，而不是 hybrid enhancer。
- hybrid single 对很多 simple / OCR query 已经很强。

修正：

- 在 route-specific stages 前加入 `hybrid_anchor`。
- 将 anchor 从 top 3 调到 top 5。

结果：

- anchor top 3：覆盖提升，但 MRR 仍下降。
- anchor top 5：All Expected 追平 hybrid，但 MRR 仍落后，直到 default/fallback 也切到 hybrid。

### 坑 4：复杂多 JD query 只猜一个 JD

多个 loss case 来自从 broad hits 中只选了一个 `jd_id`：

- 期望 `jd-015` + `jd-019`，却推断为 `jd-021`
- 期望 `jd-006` + `jd-020`，却推断为 `jd-002`
- 期望 `jd-018`，却推断为 `jd-021`

根因：

- 多文档问题经常需要多个 JD context。
- broad top hit 中出现频率最高的 JD，不一定是 expected JD。

修正：

- 从 broad hits 保留 top 3 JD contexts。
- 每个 JD context 内使用 hybrid requirement evidence retrieval。

### 坑 5：risk/gap route 找到 gap，却漏 primary evidence

典型模式：

- `gap_context` 找到了 `jd-019:gap-map`。
- primary requirement `jd-019-req-002` 掉出 top-k。

根因：

- risk route 过度偏向 `gap_map` 和 `ranking_explanation`。
- 没有给 primary requirement evidence 预留 quota。

修正：

- 在 `gap_context` 和 `ranking_context` 前新增 `risk_primary_context`。

### 坑 6：观测报告丢失切片元数据

route report 中 `case_type: null`、`robustness_category: null`，但 query specs 里其实有这些字段。

根因：

- `evaluate_labeled_retrieval_queries()` 没有把 slice metadata 透传到 per-query report。

修正：

- 每条 query report 增加 `case_type`、`golden_layer`、`robustness_category`。

注意：这些字段只用于离线分析，不参与真实路由决策。

### 坑 7：no-answer support gate 有触发，但 aggregate 没体现

per no-answer query 里有 `support_gate`，但 aggregate report 没有 trigger/block 汇总。

修正：

- 新增 `no_answer_behavior.support_gate_summary`。

当前 smart report：

```text
support trigger rate: 0.666667
support block rate:   0.222222
false positives:      0 / 9
```

## 性能优化过程

### 初始 baseline

| Route | MRR | Recall@10 | All Expected | All Primary | no-answer FP |
| --- | ---: | ---: | ---: | ---: | ---: |
| BM25 single | 0.598436 | 0.774510 | 0.705882 | 0.803922 | 4 |
| Hybrid single | 0.651572 | 0.872549 | 0.823529 | 0.862745 | 0 |
| Decomposed oracle | 0.737473 | 0.931373 | 0.901961 | 0.921569 | 0 |

### Smart router 迭代过程

| 版本 | 主要变化 | MRR | Recall@10 | All Expected | All Primary | no-answer FP |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| v0 | broad first，BM25 fallback | 0.598436 | 0.774510 | 0.705882 | 0.803922 | 0 |
| v1 | smart routes before broad fallback | 0.649090 | 0.852941 | 0.764706 | 0.862745 | 0 |
| v2 | hybrid anchor + multi-JD + risk primary | 0.629482 | 0.882353 | 0.803922 | 0.882353 | 0 |
| v3 | anchor top 5 | 0.624743 | 0.892157 | 0.823529 | 0.901961 | 0 |
| v4 | default 和 fallback 切到 hybrid | 0.658224 | 0.892157 | 0.823529 | 0.901961 | 0 |

### 最终四路对照

| Route | MRR | Recall@10 | All Expected | All Primary | no-answer FP |
| --- | ---: | ---: | ---: | ---: | ---: |
| BM25 single | 0.598436 | 0.774510 | 0.705882 | 0.803922 | 4 |
| Hybrid single | 0.651572 | 0.872549 | 0.823529 | 0.862745 | 0 |
| Smart router non-oracle | 0.658224 | 0.892157 | 0.823529 | 0.901961 | 0 |
| Decomposed oracle upper bound | 0.737473 | 0.931373 | 0.901961 | 0.921569 | 0 |

最终 smart router 状态：

- MRR 比 hybrid single 高 `+0.006652`。
- Recall@10 比 hybrid single 高 `+0.019608`。
- All Expected 与 hybrid single 持平。
- All Primary 比 hybrid single 高 `+0.039216`。
- no-answer false positives 保持 `0 / 9`。

## 当前判断

这是第一版达到最小实用门槛的 smart router：

- 没有牺牲 no-answer 安全性。
- 提升了 top-10 recall。
- 提升了 primary evidence coverage。
- All Expected 不低于 hybrid。
- 仍明显低于 oracle decomposition，这是预期内的，因为它不读 golden labels。

当前最大剩余缺口是 supporting evidence 的完整覆盖。Smart router 已经能保护 hybrid 的优势，并补一部分多证据覆盖，但还没有 oracle 那种“明确知道哪个 supporting document 必须进来”的能力。

## 使用命令

校验：

```powershell
.\.venv\Scripts\python.exe scripts\validate_golden_rag_set.py fixtures\golden_rag_questions.json --run-dir baseline\real-cv-golden-rebuild-20260602
```

BM25：

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_rag_layers.py --layer retriever --retriever-mode bm25 --golden-file fixtures\golden_rag_questions.json --run-dir baseline\real-cv-golden-rebuild-20260602 --output baseline\smart-routing-20260603\bm25-single.json
```

Hybrid：

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_rag_layers.py --layer retriever --retriever-mode hybrid --vector-weight 0.7 --bm25-weight 0.3 --golden-file fixtures\golden_rag_questions.json --run-dir baseline\real-cv-golden-rebuild-20260602 --output baseline\smart-routing-20260603\hybrid-single.json
```

Smart：

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_rag_layers.py --layer retriever --retriever-mode hybrid --vector-weight 0.7 --bm25-weight 0.3 --query-strategy smart --router-broad-limit 20 --enable-support-gate --golden-file fixtures\golden_rag_questions.json --run-dir baseline\real-cv-golden-rebuild-20260602 --output baseline\smart-routing-20260603\smart-router-rule-based.json
```

Oracle upper bound：

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_rag_layers.py --layer retriever --retriever-mode hybrid --vector-weight 0.7 --bm25-weight 0.3 --query-strategy decomposed --golden-file fixtures\golden_rag_questions.json --run-dir baseline\real-cv-golden-rebuild-20260602 --output baseline\smart-routing-20260603\decomposed-oracle-upper-bound.json
```

测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_retrieval_metrics.py tests\test_evaluate_rag_layers.py
```

最终测试结果：

```text
25 passed
```

## 备注

Hybrid 和 smart 评测在当前 sandbox 中会出现 HuggingFace cache 权限 warning：

```text
Could not cache non-existence of file. Will ignore error and continue.
```

这些 warning 不阻塞评测。命令 exit 0，报告正常写出。

## 下一轮迭代方向

不要在没有单独验证前继续扩大 router 复杂度。建议逐项测试：

- 按 slice 调 route quota，尤其是 `multi_document` 和 `cross_section`。
- 为 `gap_map` 和 `ranking_explanation` 设计更强的 supporting evidence query terms。
- JD candidate selection 不只看频率，还看 score gap 和 source type balance。
- 增加 route-level ablation report，记录每个 expected label 是由哪个 stage 加入的。
- 强化 support gate，区分 lexical overlap 和真正 entailment，尤其是 strong no-answer claims。
