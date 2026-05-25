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

3. 保守节点合并

   节点合并放在 bypass 之后，只合并确认没有外部副作用的纯数据段。当前 `generate_interview_questions` 和 `generate_reference_answers` 已调用 `interview_llm`，并记录 token、fallback 和 status，不应按旧判断当作纯数据变换直接合并。任何合并都必须保留现有事件、LLM 调用边界和 artifact 输出。

4. Graph 编译缓存

   graph 结构稳定后，再考虑模块级缓存 `StateGraph.compile()` 结果。该项属于工程优化，优先级低于阈值验证、小批量 bypass 和保守节点合并。

5. 检索 hit rate 修复

   检索 hit rate 修复放在真实 embedding / pgvector 路径进入实现期之后。当前 deterministic SHA-256 embedding 无法表达语义相似性，过早做 query rewrite 或 fallback 调整容易优化到临时向量实现上；该方向不作为当前近端性能闭环的第一步。
