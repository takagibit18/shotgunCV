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

## Indeed MCP 岗位导入后置规划

Indeed MCP 岗位导入属于 RAG、数据库投影、LangGraph 复盘 Agent 等基础能力稳定后的后置扩展，不进入当前基础优化优先级。该能力的目标不是自动投递，而是在 JD 信息输入阶段新增一个 `Indeed 导入` 来源：用户输入关键词、地点、工作类型等条件，系统搜索 Indeed 岗位，用户勾选目标 JD，后端拉取 Job Detail，并把完整 JD 标准化为当前 pipeline 已支持的文本 JD，再写入同一套 run draft。

当前规划边界：
- 保持 `run_dir` 与 Python pipeline 为业务真源；Indeed 只作为 JD 输入来源，不改变 `ingest -> analyze -> generate -> evaluate -> plan -> report`。
- 首期只做“搜索、预览、勾选、导入”，不做账号登录、浏览器自动化、ATS 自动提交或代用户申请。
- 导入后的 JD 需要保留来源元数据，例如 `sourceProvider=indeed`、Indeed job id、申请链接、抓取时间、搜索条件和公司/岗位显示名，但 Web 主界面仍避免暴露内部路径和完整原文。
- 技术可达性需要单独 spike：Indeed 官方 MCP 文档当前标注 beta 且 only available for Claude Connector。直接 MCP client 是否可调用取决于 Indeed 对 OAuth client、connector host 或授权策略的限制。

推荐后续验证顺序：
1. 先完成 RAG、数据库投影、LangGraph review、检索观测事件和质量基线。
2. 做一个只读技术 spike，验证 `https://mcp.indeed.com/claude/mcp` 是否接受通用 MCP client 的 `initialize`、OAuth discovery 和 `tools/list`。
3. 如果直接 MCP 不开放，优先评估 Claude MCP connector bridge：由 Claude 连接 Indeed MCP，jobPilot 只接收结构化 JD JSON 并落到现有草稿入口。
4. 若该能力进入生产化，再评估 Indeed 官方 API/Partner 路线，避免把 beta connector 作为唯一长期依赖。

该功能只有在基础 RAG 和 Agent 工作流稳定、JD/简历来源追溯字段完成、并且合规调用路径明确后，才进入产品实现阶段。

## 2026-05-20 当前有效 JD 基线

从本节开始，正式 baseline 记录只以 `baseline-formal-*` run 为准；更早的 `baseline-rag-*`、`baseline-next-*`、`baseline-ocr-*` run 和对应 JSON 已删除，不进入后续优化前后对比。

当前 raw JD 素材库统一为 `baseline/jd_corpus_supplement_20260520/`。该目录现在包含 19 个文本 JD、1 个 PDF JD 和 7 张图片 JD。PDF `量化派AI Native 全栈工程师如LLM  Agent AI应用开发.pdf` 已通过 `local_pdf` 提取出可用文本；图片 JD 已通过本机 Tesseract OCR 以 `eng+chi_sim` 抽取文本。本轮不启用 vision fallback。

正式 baseline 采用 7 个组合模板，每个模板重复 3 次，共 21 个 deterministic CLI run，并在每个 run 后执行 `shotguncv review`：

- `baseline-formal-r{1,2,3}-small-high-image-pdf-20260520`：少 JD，高优先，包含图片和 PDF。
- `baseline-formal-r{1,2,3}-small-image-only-20260520`：少 JD，图片-only。
- `baseline-formal-r{1,2,3}-small-low-plus-image-20260520`：少 JD，低优先，包含图片。
- `baseline-formal-r{1,2,3}-mixed-balanced-media-20260520`：少到中等规模，混合优先，包含图片和 PDF。
- `baseline-formal-r{1,2,3}-many-high-priority-media-20260520`：多 JD，高优先，包含图片和 PDF。
- `baseline-formal-r{1,2,3}-many-low-medium-media-20260520`：多 JD，中低优先，包含图片。
- `baseline-formal-r{1,2,3}-full-raw-library-20260520`：全量 raw JD，共 27 个文件：19 txt、1 pdf、7 png。

机器可读当前基线：

- `baseline/baseline_runs_formal_20260520.json`：正式 run 清单、重复轮次、JD 来源、优先级桶、媒体类型计数和事件计数。
- `baseline/baseline_metrics_formal_20260520.json`：正式聚合指标、重复采样分布、节点耗时、数据库指标和分流决策分布。

当前正式聚合结果：21 个 run，跨 run 共 204 个 JD 输入，覆盖 raw 库中 27 个唯一 JD 文件；review 阶段 `retrieval_query` 204 条，`graph_node_finished` 168 条；InMemory retrieval 耗时 avg 0.74ms、p50 1ms、p95 2ms、p99 3ms；命中数分布为 204/204 条 query 均命中 5 条，miss 率 0。

数据库基线已在 PostgreSQL + pgvector Docker 容器上完成。仅索引正式 `baseline-formal-*` runs，使用 `baseline/runs-formal-20260520` 作为索引目录，避免历史 run 混入统计。索引结果：21 条 `index_batch`，总 chunk 数 4866；index 耗时 avg 608.38ms、p50 436ms、p95 1663ms、p99 1773ms。

PgVector retrieve 采样已扩展到 30 条代表查询，覆盖高相关 AI/Agent/RAG、中相关产品/数据/客户成功、低相关 HR/法务/销售/财务/市场、图片 OCR、PDF 和无关边界 query；30/30 条均返回 5 个结果，miss 率 0；PgVector retrieve 耗时 avg 17.47ms、p50 16ms、p95 30ms、p99 33ms。

分流决策分布已纳入正式 baseline。204 个 JD 决策样本中，strategy/review 决策分布为 `apply=51`、`hold=111`、`needs_review=42`；preflight 分布为 `pass=162`、`needs_review=42`；`final_overall_score` avg 0.4185、p50 0.55、p95 0.84，作为后续按匹配度分流阈值的基准。

## 2026-05-25 埋点与 retriever NLP 评估补齐

本轮补齐了 post-run review 与 retriever 质量评估的可观测闭环，目标是把“能检索到结果”拆成可复核的事件、标签覆盖和排序质量指标。

埋点补齐包括：
- `retrieval_query` 事件继续作为检索主事件，记录 `query_preview`、`query_chars`、`retriever_type`、`retrieval_scope`、`filters`、`limit`、`hit_count`、`miss`、`duration_ms`。
- `retrieval_query` 扩展了检索质量观测字段：`raw_hit_count`、`unique_hit_count`、`supporting_hit_count`、`score_distribution`、`hit_source_refs`、`source_type_hit_counts`、`source_type_available_counts`、`precision`。
- `graph_node_finished` 记录 review 节点耗时与输出摘要，并带有 `timing_ms.business`、`timing_ms.log_write`，用于区分节点业务耗时和 JSONL 日志写入成本。
- interview/review LLM 生成链路记录 `prompt_tokens`、`completion_tokens`、`total_tokens`、`max_completion_tokens`、`fallback_used` 和 `status`，用于确认后续 RAG 生成是否引入额外 token 成本。

retriever NLP/IR 评估补齐包括：
- 新增 retriever golden schema `retriever-golden-v1`，支持 `queries`、`query_id`、`expected_chunks`、`metrics` 与 `default_k_values`。
- 评估脚本输出 `retriever-metrics-v1` 报告，包含 `label_coverage`、`label_inventory`、逐 query `hits`、`ranked_ids`、`ranked_relevance` 和聚合指标。
- 当前支持的排序质量指标为 `precision_at_k`、`recall_at_k`、`mrr`、`ndcg_at_k`。
- golden questions 与评估输出属于本地评估资产，已通过 `.gitignore` 忽略 `fixtures/golden_*.json` 与 `baseline/` 下的输出，不进入仓库提交。

本地评估使用 `baseline/runs-formal-20260520` 中 3 个 full-raw repeat：
- `baseline-formal-r1-full-raw-library-20260520`
- `baseline-formal-r2-full-raw-library-20260520`
- `baseline-formal-r3-full-raw-library-20260520`

评估结果写入本地 `baseline/retriever-quality-20260525-full-raw/aggregate.json`。本轮聚合结果：
- `run_count=3`
- `query_evaluations=30`
- `chunk_count_total=1926`
- `missing_expected_chunk_refs=0`
- `mrr_avg_by_run=0.8`
- `precision_at_k`: `@1=0.7`, `@3=0.5667`, `@5=0.36`, `@10=0.2`
- `recall_at_k`: `@1=0.35`, `@3=0.85`, `@5=0.9`, `@10=1.0`
- `ndcg_at_k`: `@1=0.7`, `@3=0.8`, `@5=0.8264`, `@10=0.8667`

结论：retriever 评估链路已经从“只看是否返回结果”推进到可复核的 label 覆盖与排序质量评估。full-raw baseline 上 `missing_expected_chunk_refs=0`，说明 golden target 已经对齐真实 `retrieval_chunks`；`MRR=0.8`、`precision@1=0.7`、`recall@10=1.0` 表明当前 InMemory retriever 在该样本上可作为 baseline sanity check 与回归保护使用。该结果不作为全 21-run 的全局质量结论。

## 2026-05-26 BGE-M3 retriever 21-run 正式质量门

本轮把 retriever 评估从 3 个 full-raw repeat 扩展为正式 21-run baseline，并将 `label_coverage` 提升为先验质量门。评估脚本现在支持：
- 单 run 报告 `retriever-metrics-v1`，包含 `quality_gate`、`label_coverage.coverage_ratio`、`source_type_metrics`。
- 21-run 聚合报告 `retriever-baseline-metrics-v1`，按 `bucket` 输出独立指标，并汇总 `candidate_evidence`、`requirement_evidence`、`jd_description`、`gap_map`、`resume_variant` 等 source type 召回质量。
- golden schema 继续固定为 `retriever-golden-v1`，不再接受 legacy list；bucket-specific query 通过 `applicable_buckets` 限定，避免不同 bucket 中重复的 `jd-001` / `variant-jd-jd-001` 被误当成同一个语义标签。
- 当适用 query 的 `label_coverage < 1.0` 时，脚本直接失败，不允许解释 precision / recall / MRR / NDCG。

版本记录：
- 日期：`2026-05-26`
- 分支：`codex/embedding_provider`
- HEAD：`8695b5a`
- embedding：`BAAI/bge-m3`
- 维度：`1024`
- 输出：`baseline/retriever-quality-bge-m3-20260526-21run/aggregate.json`

正式评估命令：
```powershell
.\.venv\Scripts\python.exe scripts\evaluate_retriever_metrics.py `
  --runs-root baseline\runs-formal-20260520 `
  --baseline-runs-file baseline\baseline_runs_formal_20260520.json `
  --golden-file fixtures\golden_retrieval_questions.json `
  --output baseline\retriever-quality-bge-m3-20260526-21run `
  --k 1 --k 3 --k 5 --k 10
```

输出写入本地忽略目录 `baseline/retriever-quality-bge-m3-20260526-21run/`。本轮质量门结果：
- `run_count=21`
- `bucket_count=7`
- `quality_gate.status=passed`
- `failed_run_ids=[]`
- 每个 bucket 的适用 query label coverage 均为 `1.0`

全局聚合结果：
| 指标 | @1 | @3 | @5 | @10 |
|------|----|----|----|-----|
| precision | 0.2174 | 0.1739 | 0.1304 | 0.0826 |
| recall | 0.1087 | 0.3696 | 0.4565 | 0.5217 |
| NDCG | 0.2174 | 0.2965 | 0.3358 | 0.3662 |

`MRR=0.3732`。

完整全局指标：
| scope | precision@1 | precision@3 | precision@5 | precision@10 | recall@1 | recall@3 | recall@5 | recall@10 | NDCG@1 | NDCG@3 | NDCG@5 | NDCG@10 | MRR |
|-------|-------------|-------------|-------------|--------------|----------|----------|----------|-----------|--------|--------|--------|---------|-----|
| `overall` | 0.2174 | 0.1739 | 0.1304 | 0.0826 | 0.1087 | 0.3696 | 0.4565 | 0.5217 | 0.2174 | 0.2965 | 0.3358 | 0.3662 | 0.3732 |

bucket 级结果：
| bucket | queries | precision@1 | recall@5 | MRR |
|--------|---------|-------------|----------|-----|
| `small_high_image_pdf` | 6 | 0.5000 | 0.6667 | 0.7500 |
| `small_image_only` | 6 | 0.5000 | 0.6667 | 0.7500 |
| `small_low_plus_image` | 6 | 0.5000 | 0.6667 | 0.7500 |
| `mixed_balanced_media` | 6 | 0.5000 | 1.0000 | 0.7500 |
| `many_high_priority_media` | 6 | 0.0000 | 0.7500 | 0.5000 |
| `many_low_medium_media` | 6 | 0.5000 | 1.0000 | 0.6667 |
| `full_raw_library_text_pdf_image` | 33 | 0.0000 | 0.0909 | 0.0227 |

完整 bucket 指标：
| bucket | precision@1 | precision@3 | precision@5 | precision@10 | recall@1 | recall@3 | recall@5 | recall@10 | NDCG@1 | NDCG@3 | NDCG@5 | NDCG@10 | MRR |
|--------|-------------|-------------|-------------|--------------|----------|----------|----------|-----------|--------|--------|--------|---------|-----|
| `full_raw_library_text_pdf_image` | 0.0000 | 0.0000 | 0.0182 | 0.0091 | 0.0000 | 0.0000 | 0.0909 | 0.0909 | 0.0000 | 0.0000 | 0.0392 | 0.0392 | 0.0227 |
| `many_high_priority_media` | 0.0000 | 0.3333 | 0.2000 | 0.1000 | 0.0000 | 0.7500 | 0.7500 | 0.7500 | 0.0000 | 0.5089 | 0.5089 | 0.5089 | 0.5000 |
| `many_low_medium_media` | 0.5000 | 0.3333 | 0.3000 | 0.1500 | 0.2500 | 0.7500 | 1.0000 | 1.0000 | 0.5000 | 0.5566 | 0.6752 | 0.6752 | 0.6667 |
| `mixed_balanced_media` | 0.5000 | 0.3333 | 0.3000 | 0.2000 | 0.5000 | 0.7500 | 1.0000 | 1.2500 | 0.5000 | 0.6934 | 0.8120 | 0.9212 | 0.7500 |
| `small_high_image_pdf` | 0.5000 | 0.3333 | 0.2000 | 0.1000 | 0.1667 | 0.6667 | 0.6667 | 0.6667 | 0.5000 | 0.5501 | 0.5501 | 0.5501 | 0.7500 |
| `small_image_only` | 0.5000 | 0.3333 | 0.2000 | 0.1500 | 0.1667 | 0.6667 | 0.6667 | 0.8333 | 0.5000 | 0.5501 | 0.5501 | 0.6283 | 0.7500 |
| `small_low_plus_image` | 0.5000 | 0.3333 | 0.2000 | 0.2000 | 0.1667 | 0.6667 | 0.6667 | 1.0000 | 0.5000 | 0.5501 | 0.5501 | 0.7119 | 0.7500 |

source type 级结果：
| source_type | queries | labels | precision@1 | recall@5 | MRR |
|-------------|---------|--------|-------------|----------|-----|
| `candidate_evidence` | 21 | 21 | 0.1429 | 1.0000 | 0.5119 |
| `jd_description` | 18 | 18 | 0.3333 | 0.8333 | 0.5278 |
| `requirement_evidence` | 36 | 60 | 0.1667 | 0.1667 | 0.1786 |
| `gap_map` | 21 | 24 | 0.0000 | 0.1429 | 0.0286 |
| `resume_variant` | 3 | 3 | 0.0000 | 0.0000 | 0.0000 |

完整 source type 指标：
| source_type | precision@1 | precision@3 | precision@5 | precision@10 | recall@1 | recall@3 | recall@5 | recall@10 | NDCG@1 | NDCG@3 | NDCG@5 | NDCG@10 | MRR |
|-------------|-------------|-------------|-------------|--------------|----------|----------|----------|-----------|--------|--------|--------|---------|-----|
| `candidate_evidence` | 0.1429 | 0.2857 | 0.2000 | 0.1000 | 0.1429 | 0.8571 | 1.0000 | 1.0000 | 0.1429 | 0.5748 | 0.6363 | 0.6363 | 0.5119 |
| `gap_map` | 0.0000 | 0.0000 | 0.0286 | 0.0143 | 0.0000 | 0.0000 | 0.1429 | 0.1429 | 0.0000 | 0.0000 | 0.0553 | 0.0553 | 0.0286 |
| `jd_description` | 0.3333 | 0.2222 | 0.1667 | 0.1333 | 0.3333 | 0.6667 | 0.8333 | 1.3333 | 0.3333 | 0.5436 | 0.6081 | 0.7824 | 0.5278 |
| `requirement_evidence` | 0.1667 | 0.0556 | 0.0333 | 0.0250 | 0.1667 | 0.1667 | 0.1667 | 0.2500 | 0.1667 | 0.1667 | 0.1667 | 0.1944 | 0.1786 |
| `resume_variant` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

解读：BGE-M3 已经比 SHA-256 临时 embedding 更适合做正式质量基线，但当前 21-run 结果还不能视为高质量 retriever。小/中 bucket 的可评估标签较少，precision@1 与 MRR 尚可；full-raw bucket 在 642 chunks 的规模下明显退化，尤其是 `gap_map`、`resume_variant` 和部分 `requirement_evidence` 召回很弱。下一轮优化应优先处理 source_type-aware query、chunk text 构造和低相关阈值/重排，而不是只看整体 hit count。

## 2026-05-26 真实业务 RAG 路径统一

本轮将 post-run review 的默认无数据库检索路径从 `ArtifactTokenRetriever` 替换为 `InMemoryVectorRetriever`，并继续使用 `BAAI/bge-m3` 作为默认 embedding。这样正式 retriever baseline 与真实业务 review 默认路径使用同一类向量检索语义，避免评估脚本测 BGE、真实流程却走 token overlap 的错位。

当前后端选择规则：

| 场景 | 默认 retriever | 说明 |
|------|----------------|------|
| `shotguncv review` 未设置 `SHOTGUNCV_DATABASE_URL` | `InMemoryVectorRetriever` | 基于当前 `run_dir` artifacts 构建本地向量索引，使用 BGE-M3 embedding。 |
| `shotguncv review` 设置了 `SHOTGUNCV_DATABASE_URL` | `PgVectorRetriever` | 保留为显式可选数据库后端，用于跨 run / 历史索引实验。 |
| `shotguncv retrieve` | `PgVectorRetriever` | 仍是数据库 smoke query 命令，要求数据库 URL。 |
| `shotguncv index` | PostgreSQL projection | 仍只负责可选数据库投影和 pgvector chunk 写入。 |

实现约束：

- `run_dir` 继续是真实业务执行真源；默认 review 不依赖 PostgreSQL 或 pgvector。
- 默认 review 在 `load_run_context` 阶段构建并预热一次 `InMemoryVectorRetriever`，后续每个 JD 分支复用同一个 retriever，避免每个 JD 重复 embedding 全量 chunks。
- `retrieval_query.retriever_type` 现在可用于确认真实路径：默认无 DB 应为 `InMemoryVectorRetriever`；显式 DB 路径应为 `PgVectorRetriever`。
- PgVector 路径暂不删除，只降级为可选后端；后续如无跨 run 检索需求，可再进一步收缩。

同日补齐统一 golden set 的分层评估入口：

- `scripts\validate_golden_rag_set.py` 校验 `rag-golden-v1`，当前本地 `fixtures\golden_rag_questions.json` 为 30 条样本，覆盖 common_question、multi_document、no_answer、stale_or_conflicting。
- `scripts\evaluate_rag_layers.py --layer retriever` 从同一份 `rag-golden-v1` 生成 retriever query specs，输出 precision@k、recall@k、MRR、NDCG、label_coverage、case_type_metrics 和 no_answer 行为观测。
- `scripts\evaluate_rag_layers.py --layer generator` 读取 generator answer file，在跳过 retriever、使用 golden expected documents 的前提下评估 faithfulness、answer_relevance、must_cover_coverage、forbidden_claim_violation 和 citation_accuracy。
- retriever 指标口径已修正：同一个 expected label 被多个 chunk 命中时只计一次，避免 recall@k / NDCG 因重复 label 膨胀。

本地 smoke 使用 `baseline-formal-r3-full-raw-library-20260520` 跑通 retriever layer，输出为 `baseline\rag-layered-20260526\retriever-full-raw-r3.json`。质量门 `label_coverage=1.0`，但指标仍偏弱：precision@10 `0.0120`、recall@10 `0.0800`、MRR `0.0168`；5 条 no_answer query 全部仍返回非空结果，说明后续必须补充低相关阈值或 abstention 逻辑，不能只依赖 top-k 向量召回。

## 2026-05-25 接下来改进顺序安排

在 retriever 细粒度埋点和 full-raw 本地 NLP/IR 评估链路补齐后，下一轮改进按以下顺序推进：

1. Evidence gate 阈值 A/B 验证

   优先验证 `result_count < threshold` 这条证据门槛，而不是先改图结构。当前阈值固定为 3，并且已有 30 个 JD 进入 low-evidence / gap report 路径；新补齐的 `retrieval_query` 细粒度字段、`source_type` 命中分布和 `graph_node_finished.timing_ms` 已经足够支撑 `2/3/4/5` 四组阈值对比。该步骤的目标是确认不同阈值下 gap report 数量、review 决策分布、retrieval supporting hit 分布和节点耗时是否合理。

   本轮已新增本地 A/B runner：`scripts/run_evidence_gate_ab_test.py`。它会把已有 run artifact 复制到阈值隔离目录，排除旧 `logs` 与 `review` 输出后重新执行 post-run review，并输出 `evidence-gate-ab-v1` 聚合报告。首轮验证使用 `baseline/runs-formal-20260520` 下 3 个 full-raw repeat：
   - `baseline-formal-r1-full-raw-library-20260520`
   - `baseline-formal-r2-full-raw-library-20260520`
   - `baseline-formal-r3-full-raw-library-20260520`

   输出写入本地忽略目录 `baseline/evidence-gate-ab-20260525-full-raw-v2/aggregate.json`。该样本共 81 个 JD，4 组阈值全部执行成功，`failure_count=0`。结果摘要：
   - threshold 2：low-evidence/gap report = 12/81，apply/hold/needs_review/evidence_needed = 21/36/12/12。
   - threshold 3：low-evidence/gap report = 12/81，决策分布与 threshold 2 相同。
   - threshold 4：low-evidence/gap report = 39/81，apply/hold/needs_review/evidence_needed = 21/15/6/39。
   - threshold 5：low-evidence/gap report = 57/81，apply/hold/needs_review/evidence_needed = 15/6/3/57。

   全量 21-run 复核使用 `baseline/runs-formal-20260520` 下全部 21 个 run，共 204 个 JD，4 组阈值全部执行成功，`failure_count=0`。输出写入 `baseline/evidence-gate-ab-20260525-full-21run/aggregate.json`。结果摘要：

	   | 阈值 | low-evidence / gap report | 占比 | apply/hold/needs_review/evidence_needed |
	   |------|--------------------------|------|----------------------------------------|
	   | 2 | 30/204 | 14.7% | 51/87/36/30 |
	   | 3（当前默认） | 30/204 | 14.7% | 51/87/36/30（与 threshold 2 完全一致） |
	   | 4 | 102/204 | 50.0% | 51/39/12/102 |
	   | 5 | 147/204 | 72.1% | 39/15/3/147 |

	   retrieval supporting hit 均值在四组阈值中保持 `3.3498`，各 source_type hit 分布完全一致。阈值 2 与 3 在全量样本上仍无分流差异；阈值 4 恰好卡在 50% 分水岭；阈值 5 将 72% 的 JD 拦入 gap report。

	   **结论：保持默认 threshold 3。** 21-run 全量验证与首轮 3-run full-raw 样本结论一致 —— 阈值 2 没有额外放行任何 JD，阈值 4/5 过度收紧。该阈值配置已充分验证，无需再复核。

	   **通俗版 A/B 测试解读**

	   这个测试的核心问题很简单：系统在审查 JD 时，会根据检索到的"证据条数"决定这个 JD 能不能自动通过。如果证据不够，就扔进 gap report（缺口报告），需要人工介入。目前门槛是 3 条 —— 少于 3 条就算"证据不足"。

	   先用 3 个 full-raw run（81 JD）做首轮验证，再用全量 21 个 run（204 JD）做复核，两轮结论一致：

	   | 阈值 | 3-run gap report | 21-run gap report | 解读 |
	   |------|-----------------|-------------------|------|
	   | 2 | 12/81 (14.8%) | 30/204 (14.7%) | 和阈值 3 完全一致，没有 JD 恰好卡在 2 条证据 |
	   | 3（当前默认） | 12/81 (14.8%) | 30/204 (14.7%) | 基准线，约 15% 的 JD 需要人工关注 |
	   | 4 | 39/81 (48.1%) | 102/204 (50.0%) | 大幅收紧，半数 JD 被拦下 |
	   | 5 | 57/81 (70.4%) | 147/204 (72.1%) | 过于严苛，七成 JD 走人工，自动化失去意义 |

	   两轮结果比例高度一致（14.7~14.8% / 48~50% / 70~72%），说明样本量放大后结论稳定。门槛 3 是最合理的平衡点。

	   **控制变量方法：为什么结论是可靠的**

	   A/B 测试中有一个常见的坑：你改了阈值，但如果检索结果本身也在波动（比如重复跑同一 JD 返回的证据数不同），你就分不清差异到底来自阈值还是来自检索不稳定。

	   本次测试采用的校验方法：在四组阈值的聚合报告中，直接对比 `retrieval_supporting_hit_count`（检索命中数）的均值：

	   | 指标 | threshold=2 | threshold=3 | threshold=4 | threshold=5 |
	   |------|-------------|-------------|-------------|-------------|
	   | 3-run: retrieval_supporting_hit_count avg | 3.5556 | 3.5556 | 3.5556 | 3.5556 |
	   | 21-run: retrieval_supporting_hit_count avg | 3.3498 | 3.3498 | 3.3498 | 3.3498 |
	   | retrieval_source_type_hit_counts | 完全一致 | 完全一致 | 完全一致 | 完全一致 |

	   四组阈值下检索命中数**完全不变**，包括各 source_type（candidate_evidence、requirement_evidence 等）的命中分布也完全相同。这验证了两个关键事实：

	   1. **检索层是稳定的** —— 同一批 JD 重复跑返回的证据数量一致，不存在随机波动干扰。即使样本从 81 扩大到 204 JD，这个稳定性依然保持（3-run avg=3.5556，21-run avg=3.3498，两个值分别在不同样本组合中各阈值间完全恒定）。
	   2. **差异 100% 来自阈值分流，不是检索质量变化** —— 既然检索结果恒定，那么 gap report 数量的变化就纯粹是门槛高低导致的，排除了"可能某次跑检索质量变差导致更多 JD 被判不足"的混淆因素。

	   这个方法可以作为后续所有 evidence gate 相关 A/B 测试的标准校验步骤：每次改阈值或改检索策略，都先确认 `retrieval_supporting_hit_count` 和 `source_type_hit_counts` 在对照组中是否保持不变，确保只有你改动的变量在起作用。

2. 小批量 bypass

   在阈值口径确认后，再处理小 JD 数 bucket 的固定成本问题。3-4 JD 样本下 fan-out 收益很弱，graph 编译、state 序列化和调度成本占比过高；因此可在 `JD <= 3` 时绕过 fan-out，使用串行路径，目标是降低小批量 review 耗时，同时保持 run artifact 和日志语义不变。

   本轮已实现保守 bypass：`JD <= 3` 的 post-run review 直接走 `small-batch-serial`，`parallel_topology.retrieve/inspect` 记录为 `serial_by_jd`；`JD >= 4` 继续走原 `langgraph-send` fan-out。串行路径仍执行同一批 review 节点，继续写入 `graph_node_started`、`graph_node_finished`、`retrieval_query`、LLM token/fallback 日志和相同的 review artifact。

   本地验证使用 `baseline/runs-formal-20260520` 中 9 个 small bucket run 重新执行 threshold=3 review，输出写入忽略目录 `baseline/small-batch-bypass-20260525/`，`failure_count=0`。其中只有 `small_image_only` bucket 为 3 JD，实际触发 bypass；两个 4 JD bucket 按保守阈值继续作为 fan-out 对照。与 `baseline/baseline_metrics_formal_20260520.json` 中旧基线对比：
   - `small_image_only`：旧 fan-out review avg `94.33ms`、p50 `95ms`；新 `small-batch-serial` review avg `76.0ms`、p50 `75ms`，平均耗时下降 `18.33ms`，约 `19.4%`。
   - `small_high_image_pdf`：4 JD，未触发 bypass，仍为 `langgraph-send`；本轮 review avg `451.67ms`，旧基线 avg `560.0ms`，该差异不计入 bypass 收益。
   - `small_low_plus_image`：4 JD，未触发 bypass，仍为 `langgraph-send`；本轮 review avg `113.33ms`，旧基线 avg `124.0ms`，该差异不计入 bypass 收益。

   结论：当前保守口径下，实际优化收益只对 `JD <= 3` 生效；已观察到 3-JD bucket 约 `19.4%` review stage 耗时下降，并且 4-JD bucket 没有被误切到串行路径。若后续希望覆盖 4-JD bucket，应单独把阈值从 `<=3` 扩到 `<=4` 后再做一轮对照。

3. 保守节点合并

   节点合并放在 bypass 之后，只合并确认没有外部副作用的纯数据段。当前 `generate_interview_questions` 和 `generate_reference_answers` 已调用 `interview_llm`，并记录 token、fallback 和 status，不应按旧判断当作纯数据变换直接合并。任何合并都必须保留现有事件、LLM 调用边界和 artifact 输出。

4. Graph 编译缓存

   graph 结构稳定后，再考虑模块级缓存 `StateGraph.compile()` 结果。该项属于工程优化，优先级低于阈值验证、小批量 bypass 和保守节点合并。

   2026-05-26 已实现模块级 compiled graph 缓存：同一 Python 进程内首次 LangGraph review 会执行 `StateGraph.compile()`，后续 review 复用 compiled graph。单元回归验证两次 review 的 compile 调用从 2 次降为 1 次。当前 benchmark artifact 尚未记录 `compile_duration_ms` 或 cache hit 字段，因此该项的收益只能确认为“重复 compile 次数减少”，不能从聚合报告中直接换算为稳定 wall-clock ms。

   同日完成保守节点合并：`small-batch-serial` 与 `threadpool-fallback` 路径不再执行 `merge_retrieval_results`、`merge_review_paths` 两个空 fan-in 节点；LangGraph fan-out 路径仍保留这两个 barrier 节点，因为并行分支需要汇合。

   使用正式 baseline 同口径重跑 threshold=3 review：

   ```powershell
   .\.venv\Scripts\python.exe scripts\run_evidence_gate_ab_test.py `
     --source-runs-root baseline\runs-formal-20260520 `
     --output-root baseline\graph-cache-node-merge-20260526-full-21run-rerun `
     --threshold 3
   ```

   输出写入本地忽略目录 `baseline/graph-cache-node-merge-20260526-full-21run-rerun/`，`failure_count=0`。业务与检索口径保持不变：

   | 指标 | 2026-05-25 21-run A/B threshold=3 | 2026-05-26 rerun |
   |------|------------------------------------|------------------|
   | run_count | 21 | 21 |
   | JD count | 204 | 204 |
   | review_low_evidence_jd_count | 30 | 30 |
   | review_sufficient_evidence_jd_count | 174 | 174 |
   | retrieval_combined_query_count | 204 | 204 |
   | retrieval_supporting_hit_count avg | 3.3498 | 3.3498 |
   | apply/hold/needs_review/evidence_needed | 51/87/36/30 | 51/87/36/30 |

   已验证的结构性收益：

   | 指标 | 2026-05-25 21-run A/B threshold=3 | 2026-05-26 rerun | 变化 |
   |------|------------------------------------|------------------|------|
   | graph_node_finished 总数 | 576 | 570 | -6（-1.0%） |
   | `small_image_only` bucket graph nodes | 42 | 36 | -6（-14.3%） |
   | `merge_retrieval_results` 事件数 | 21 | 18 | -3 |
   | `merge_review_paths` 事件数 | 21 | 18 | -3 |

   解释：21 个正式 run 中只有 3 个 `small_image_only` run 满足 `JD <= 3` 并走 `small-batch-serial`，每个 run 少两个空 merge 节点，因此全量只减少 6 个 graph node。其余 18 个 LangGraph fan-out run 继续保留 merge barrier，节点数不变。

   负向性能观测也必须保留：本轮同口径 rerun 没有观察到 wall-clock 或 review stage 耗时提升，反而慢于 2026-05-25 的旧 21-run A/B 输出。

   | 指标 | 2026-05-25 21-run A/B threshold=3 | 2026-05-26 rerun | 观察 |
   |------|------------------------------------|------------------|------|
   | review stage avg | 267.57ms | 457.14ms | 变慢 |
   | review stage p50 | 188ms | 240ms | 变慢 |
   | review wall avg | 360.47ms | 603.84ms | 变慢 |
   | review wall p50 | 280.57ms | 394.99ms | 变慢 |
   | graph node duration avg | 28.97ms | 41.35ms | 变慢 |

   bucket 层面最明显的异常来自 `full-raw-library`：旧 21-run A/B 的 review stage avg 为 `622.0ms`，本轮 rerun 为 `1576.0ms`。该 bucket 仍走 `langgraph-send`，没有触发保守节点合并，因此这类耗时上升不能归因为少量空节点移除本身，更可能是本机运行时、文件 IO、进程冷启动或当次负载波动。当前结论应写为：**节点数和重复 compile 次数有结构性下降，但本轮同口径 wall-clock 性能没有提升，不能把该改动宣称为端到端耗时优化。**

   后续如果要量化 Graph 编译缓存的真实性能收益，需要把 `compiled_graph_cache_hit`、`compile_duration_ms` 或类似字段写入 review 事件；否则 compile 缓存收益会被 review 节点耗时、日志写入、文件 IO 和机器波动淹没。

5. 检索 hit rate 修复

   检索 hit rate 修复现在可以基于真实 embedding / pgvector 路径继续推进。当前默认 embedding 已切换为 `BAAI/bge-m3`，向量维度为 1024；后续 query rewrite 或 fallback 调整应基于重新索引后的 BGE 结果评估，而不是旧的 deterministic SHA-256 baseline。

## 2026-05-26 no-answer threshold + abstention gate results

Local real-run check used `baseline/runs-formal-20260520/baseline-formal-r3-full-raw-library-20260520` with `fixtures/golden_rag_questions.json` and wrote the ignored report `baseline/tmp-codex-no-answer-abstention-rerun.json`.

| Metric | Previous retriever report | threshold + abstention gate |
|------|----------------------------|-----------------------------|
| sample_count | 30 | 30 |
| answerable_sample_count | 25 | 25 |
| no_answer_sample_count | 5 | 5 |
| no_answer weak top-k passed to generator | 5/5 | 0/5 |
| no_answer abstention_rate | 0.0 | 1.0 |
| no_answer gate status | not present | passed |
| no_answer non_abstained_count | not present | 0 |
| answerable precision@10 | 0.0120 | 0.0120 |
| answerable recall@10 | 0.0800 | 0.0800 |
| answerable MRR | 0.0168 | 0.0168 |

The five no-answer top scores were `0.594330`, `0.602601`, `0.606408`, `0.599532`, and `0.598400`. Threshold sweep on this run showed `0.55` still leaks 5/5 no-answer samples, `0.60` leaks 2/5, and `0.65+` leaks 0/5. The current default `0.8` is conservative for this sample. This result measures retriever-layer blocking of weak evidence before generator input; it does not by itself prove e2e answer text quality.

### Generator-layer gate check

To check whether the retriever abstention gate actually blocks generator-layer answers, a temporary malicious answers file was generated at `baseline/tmp-codex-generator-gate-answers.json`. It intentionally filled all five `no_answer` samples with unsupported confident claims. Two generator-layer reports were produced:

- Without retriever gate: `baseline/tmp-codex-generator-without-gate.json`
- With retriever gate: `baseline/tmp-codex-generator-with-gate.json`, using `--retriever-report baseline/tmp-codex-no-answer-abstention-rerun.json`

| Metric | without retriever gate | with retriever gate |
|------|-------------------------|---------------------|
| answered_sample_count | 30 | 25 |
| no_answer_answered_count | 5/5 | 0/5 |
| no_answer_blocked_count | 0/5 | 5/5 |
| no_answer answer_chars | 105 each | 0 each |
| retriever_gate.enabled | false | true |
| retriever_gate.blocked_question_ids | none | rag-golden-003, rag-golden-018, rag-golden-019, rag-golden-020, rag-golden-021 |

Conclusion: the generator layer now consumes the retriever report and blocks all no-answer samples that were marked `abstained` by the retriever gate, even when the answers file contains fabricated text. This check validates the gate wiring; it is still an offline layered-evaluation check rather than a full production RAG endpoint test.
