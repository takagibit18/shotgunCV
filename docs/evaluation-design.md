# ShotgunCV 评估设计

## 定位与目标

评估系统是核心子系统，不是辅助脚本。系统必须用结构化评分判断“值得投递程度”，而不是依赖生成文本的主观观感。

## 核心流程

评估流程分为两层：

1. 规则评估（Rule-based）
2. 结构化判分（LLM Judge）

两层结果统一汇总为评分卡（`ScoreCard`），再进入排序阶段。

## 数据对象与接口

评分卡（`ScoreCard`）字段固定为：

- `fit_score`
- `ats_score`
- `evidence_score`
- `stretch_score`
- `gap_risk_score`
- `rewrite_cost_score`
- `overall_score`
- `judge_rationale`

判分接口约束：

- 输入：`JDProfile` + `ResumeVariant` + `CandidateProfile`
- 输出：结构化评分字段，不接受自由格式文本作为最终接口

## 评估与质量门禁

规则评估维度：

- `schema_validity`
- `keyword_coverage`
- `evidence_binding`
- `untraceable_claim_flags`
- `rewrite_distance`
- `cluster_reuse_efficiency`

判分维度：

- `role_fit`
- `evidence_quality`
- `persuasiveness`
- `interview_pressure_risk`
- `application_worthiness`

门禁要求：

- 证据不足内容必须抬高 `gap_risk_score` 或进入 `catch-up notes`。
- 排序结果必须能回溯到评分卡字段与判分理由。
- 规则或提示词变化必须通过回归验证后才可发布。

## 非目标与边界

- v1 不承诺真实面试转化率预测，只提供可解释代理评分。
- v1 不将判分模型输出作为唯一依据，规则层始终保留硬约束。
- v1 不接受无法追溯来源的高分结论。

## 2026-05-26 RAG Golden Set 与分层评估设计

RAG 后续优化需要先建立人工标注 golden set。该数据集是 retriever、generator 和 e2e 三层诊断的共同真值来源，优先级为 `P0-1`，高于继续调参、引入 RAGAS 或扩大自动化指标。没有人工 golden set 时，precision、recall、faithfulness 或 answer relevance 都只能作为局部 sanity check，不能作为正式质量门。

### Golden Set 规模与字段

首版目标为 30-50 条人工标注样本。每条样本至少包含：

| 字段 | 说明 |
|------|------|
| `question_id` | 稳定问题 ID，后续指标和回归报告只引用该 ID。 |
| `question` | 用户问题，尽量贴近真实 review / 面试准备 / 投递决策场景。 |
| `case_type` | 测试集类型，例如常见问题、多文档综合、知识库无答案、信息过时或矛盾。 |
| `expected_documents` | 正确文档或 chunk 列表，包含 source_type、source_id、chunk_id 或可稳定匹配的 label。 |
| `golden_answer` | 人工认可的标准答案。 |
| `must_cover_points` | 答案必须覆盖的关键点。 |
| `forbidden_claims` | 不允许编造或不应下结论的内容。 |
| `answer_policy` | 无答案、矛盾答案、过时信息等情况下应如何回答。 |
| `metadata` | bucket、JD 数量、输入媒体类型、候选人/JD 范围等辅助字段。 |

### 测试集类型

| 类型 | 目的 | 设计要点 |
|------|------|----------|
| 常见问题覆盖 | 覆盖真实高频用户问题 | 问题应能由单个或少量明确文档回答，用于验证基础召回和答案稳定性。 |
| 多文档综合题 | 检查跨 source_type、跨 JD 或跨 artifact 的综合能力 | `expected_documents` 应包含多个相关文档，答案需要合并信息而不是只摘一个片段。 |
| 知识库中没有的题 | 检查系统会不会乱答 | `expected_documents=[]`，`golden_answer` 应明确表达无法从当前资料确认，并给出可补充材料建议。 |
| 信息过时或矛盾的题 | 检查冲突处理和时间敏感判断 | 标注有效文档、过时文档、冲突点和应优先采用的证据规则。 |

### Retriever 层评估

Retriever 测试只评估“有没有把正确证据找回来”和“排序是否合理”，不评估生成答案。

输入为 `question`，检索结果与 `expected_documents` 对比。核心指标：

| 指标 | 用途 |
|------|------|
| `precision@k` | 前 k 条里有多少是真正相关证据，衡量结果列表是否干净。 |
| `recall@k` | 应找回的正确证据有多少出现在前 k 条，衡量是否漏证据。 |
| `MRR` | 第一个正确证据出现得有多靠前，衡量首屏可用性。 |
| `NDCG` | 支持分级相关性时衡量整体排序质量。 |
| `label_coverage` | 先验质量门，低于 100% 时不解释 precision / recall。 |

Retriever 报告必须按 `case_type`、`bucket` 和 `source_type` 拆分，避免整体均值掩盖 `gap_map`、`resume_variant`、`requirement_evidence` 等弱项。

### Generator 层评估

Generator 测试需要跳过 retriever，直接喂人工标注的正确文档，也就是“完美上下文”。该层只回答一个问题：在证据已经正确的情况下，生成器能不能给出忠实、相关、完整的答案。

评估重点：

| 指标 | 用途 |
|------|------|
| `faithfulness` | 答案是否忠于给定文档，是否出现 unsupported claim。 |
| `answer_relevance` | 答案是否真正回应用户问题，而不是泛泛总结。 |
| `must_cover_coverage` | `must_cover_points` 覆盖率。 |
| `forbidden_claim_violation` | 是否触发 `forbidden_claims`。 |
| `citation_accuracy` | 引用是否指向支持该说法的正确文档。 |

RAGAS 可以在这一层作为辅助观测工具引入，但不应先于人工 golden set，也不应在首版作为唯一质量门。首版应优先保留人工 rubric 和可复核证据链。

### E2E 层评估

E2E 测试把 retriever 和 generator 串起来，使用同一条用户问题从真实业务入口运行完整 RAG 流程。该层同时解释两类失败：

| 失败类型 | 判断方式 |
|----------|----------|
| Retriever failure | 正确文档没有进入前 k，或排序过低导致 generator 没看到关键证据。 |
| Generator failure | 正确文档已经给到，但答案仍然遗漏、跑题、乱答或引用错误。 |

E2E 报告应同时输出 retriever 指标、generator 指标和最终业务 rubric。最终结论不能只看一个总分，必须能归因到“找不到证据”还是“有证据但答不好”。

### 后续落地顺序

| 优先级 | 工作项 | 产物 |
|--------|--------|------|
| P0-1 | 建立 30-50 条人工 golden set | versioned golden schema、标注指南、样本 JSON。 |
| P0-2 | 对齐真实业务 RAG 路径 | 默认 `BGE-M3 + run_dir artifact 本地向量检索`，PgVector 仅作为可选后端。 |
| P0-3 | 固化 retriever 分层评估 | precision@k、recall@k、MRR、NDCG、label_coverage、source_type 拆分。 |
| P0-4 | 固化 generator 分层评估 | 完美文档输入、faithfulness、answer relevance、覆盖率、引用准确性。 |
| P1-1 | 固化 e2e 评估 | 同一 golden set 串联 retriever + generator，并输出失败归因。 |
| P1-2 | 针对弱项优化 RAG | source_type-aware query、chunk text 构造、metadata filter、rerank、阈值。 |
| P2 | RAGAS pilot | 在 golden set 稳定后，对 generator/e2e 做辅助观测和 judge 稳定性验证。 |

### P0-1 当前落地产物

- 版本化 schema：`rag-golden-v1`，校验入口为 `scripts/validate_golden_rag_set.py`。
- 标注指南：`docs/golden-rag-annotation-guide.md`。
- 本地样本 JSON：`fixtures/golden_rag_questions.json`，首版 30 条，覆盖 common_question、multi_document、no_answer、stale_or_conflicting 四类样本。
- 提交边界：真实 golden JSON 继续匹配 `.gitignore` 中 `/fixtures/golden_*.json`，只在本地作为评估真值使用；仓库提交 validator、测试和标注指南。

### P0-2/P0-3/P0-4 当前落地产物

- 真实业务 RAG 路径统一：`shotguncv review` 在未设置 `SHOTGUNCV_DATABASE_URL` 时默认使用 `InMemoryVectorRetriever`，基于当前 `run_dir` artifacts 构建 BGE-M3 本地向量索引；PgVector 保留为显式可选后端。
- Retriever 分层评估入口：`scripts/evaluate_rag_layers.py --layer retriever` 可直接读取 `rag-golden-v1`，输出 precision@k、recall@k、MRR、NDCG、label_coverage、case_type 拆分和 no_answer 行为观测。
- Retriever 指标口径修正：重复命中同一个 expected label 时只计一次，避免 recall@k 或 NDCG 因重复 label 超过合理上限。
- Generator 分层评估入口：`scripts/evaluate_rag_layers.py --layer generator` 读取同一份 `rag-golden-v1` 和 generator answer file，在跳过 retriever 的条件下评估 faithfulness、answer_relevance、must_cover_coverage、forbidden_claim_violation 和 citation_accuracy。

### RAG 后续优化优先级

当前真实业务 RAG 已经具备 BGE-M3 本地向量检索、人工 golden set、retriever 分层评估和 generator 分层评估入口。下一轮优化按以下顺序推进：

| 优先级 | 工作 | 为什么 |
|--------|------|--------|
| P1-1 | no-answer 阈值和 abstention gate | 先降低乱答风险，避免知识库无答案时仍把弱相关 top-k 交给 generator。 |
| P1-2 | BM25 + BGE hybrid | 解决 full-raw 大库下纯 dense retrieval 召回差、精确 label/技能/source_id 命中弱的问题。 |
| P1-3 | source_type-aware routing | 防止 `candidate_evidence` 淹没 `gap_map` / `requirement_evidence`，让不同问题类型优先检索正确证据层。 |
| P1-4 | gap_map chunk text 重构 | 让缺口、风险、missing evidence、hard gate 等负向证据更容易被 query 搜到。 |
| P1-5 | dense / BM25 / hybrid 对照评估 | 用同一份 `rag-golden-v1` 量化 hybrid 是否真的提升 recall@k、MRR、NDCG、no-answer 行为和 latency。 |
| P2-1 | rerank | 在 hybrid candidate 集合质量变好后再做二次排序，避免只是在错误候选中重排。 |
| P2-2 | generator/e2e judge | 在 retriever 和 generator 分层指标稳定后，再评估 faithfulness、answer relevance、最终答案质量和失败归因。 |
