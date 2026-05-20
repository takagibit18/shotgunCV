# 数据库 RAG 与复盘 Agent 扩展

## 定位

该扩展把现有 `run_dir` 产物投影到 PostgreSQL，并在其上增加检索与复盘能力。它不改变主流程：

```text
ingest -> analyze -> generate -> evaluate -> plan -> report
```

`run_dir` 仍然是业务执行真源；数据库只用于查询、检索、历史记忆和 post-run review。未调用 `index`、`retrieve` 或 `review` 时，现有 pipeline 不需要数据库、pgvector、LangChain 或 LangGraph。

## 安装与配置

可选依赖安装：

```bash
pip install -e ".[rag]"
```

数据库连接通过环境变量提供，不写入 `run_config.json`：

```bash
set SHOTGUNCV_DATABASE_URL=postgresql://user:password@localhost:5432/shotguncv
```

迁移入口位于 `shotguncv_core.db.migrations`。当前迁移会创建投影表与 `retrieval_chunks`，并启用 `pgvector` 扩展。

## CLI

索引已有 run：

```bash
shotguncv index --runs-dir ./runs
```

只索引关系投影、不写入检索 chunks：

```bash
shotguncv index --runs-dir ./runs --skip-chunks
```

检索 smoke test：

```bash
shotguncv retrieve --query "Python automation evidence" --candidate-id cand-001
```

生成 run-local 复盘产物：

```bash
shotguncv review --run-dir ./runs/demo
```

输出：

- `review/post_run_review.json`
- `review/interview_prep.md`

## 数据边界

投影实体包括 `candidates`、`candidate_sources`、`companies`、`jd_inputs`、`runs`、`run_artifacts`、`resume_variants`、`requirement_evidence`、`preflight_gates`、`scorecards`、`gap_maps`、`ranking_explanations`、`application_strategies`、`application_feedback` 与 `retrieval_chunks`。

检索 chunk 必须保留：

- `source_type`
- `source_id`
- `candidate_id`
- `jd_id`（如适用）
- `run_id`（如适用）
- `artifact_path`（如适用）
- `provenance_summary`

RAG 只能提供证据召回、解释和复盘上下文，不能覆盖 `ScoreCard`、`PreflightGate` 或既有排序契约。

## 明确非目标

- 不做自动投递。
- 不做招聘网站或公司网站抓取。
- 不做浏览器自动化、账号登录、LinkedIn/Boss/拉勾/ATS 自动化。
- 不把 PostgreSQL 变成第一版业务执行真源。
- 不在 Web 主界面暴露完整 CV/JD 原文；默认只展示摘要、证据来源和 artifact 标签。

## 观测事件与基线采集

RAG、数据库投影和 post-run review 的观测事件继续写入对应 run 的 `logs/run_events.jsonl`。这些事件只服务于性能和质量基线，不改变主 pipeline 的 6 个阶段完成判定，也不把 PostgreSQL 变成业务执行真源。

新增事件：

- `graph_node_started` / `graph_node_finished`：记录 `stage=review`、`graph`、`graph_runtime`、`node`、`run_id`、`jd_count`、`duration_ms`、`status`、`input_summary`、`output_summary`。摘要只保留计数和关键 ID，不写完整 CV、JD、问题或回答正文。
- `retrieval_query`：记录 `stage`、`query_preview`、`query_chars`、`retriever_type`、`filters`、`limit`、`hit_count`、`miss`、`duration_ms`。默认只保留 query 前 160 字和长度，避免把完整岗位文本或简历文本扩散到日志。
- `index_batch`：记录 `stage=index`、`run_id`、`artifact_count`、`chunk_count`、`duration_ms`、`skip_chunks`，用于比较每个 run 的投影与 chunk 生成成本。

基线采集建议先跑 20 个以上代表性 run，并至少覆盖多 JD、低命中 JD、PDF/图片输入、完整 evaluate/plan/report 产物和 review 产物。采集后统计：

- 每 JD 检索耗时分布：avg、max、p99。
- post-run review 8 个节点的耗时占比，定位并行和分流优化的优先级。
- 每 JD 检索命中数分布，作为后续低命中分流阈值依据。
- 检索 miss 率，作为后续 RAG 召回率优化的 baseline。
- 每 run 的 chunk 总数和 index 耗时，作为索引效率和 LLM 索引成本对比基线。
- 当前 review 流没有新增 LLM token 消耗；后续引入 LLM review 或 LLM index 时，使用主 pipeline 已有 token 日志做增量对比。
