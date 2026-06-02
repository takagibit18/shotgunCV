# 真实 CV 候选人样本与 Golden Set 重构记录

日期：2026-06-02

分支：`codex/real-cv-golden-rebuild`

## 背景

原 golden set 使用的候选人材料主要来自 `fixtures/candidates/base_resume.md`，内容过于简略，导致 RAG 评测很容易变成对低质量候选人样本和旧 artifact 的拟合。用户提供真实 CV JSON 后，本轮目标是先整合高信息密度候选人样本，再基于新 baseline artifact 重构 golden set 的问题、答案和 expected documents。

## 本轮改动

- 新增候选人样本：`fixtures/candidates/real_cv_agent_engineer.md`。
- 更新 fixture 说明：`fixtures/README.md`。
- 使用真实 CV 样本重跑 deterministic baseline：
  - run：`baseline/real-cv-golden-rebuild-20260602`
  - CV：`fixtures/candidates/real_cv_agent_engineer.md`
  - JD corpus：`baseline/jd_corpus_supplement_20260520`
  - config：`baseline/deterministic-run-config.json`
- 重写本地 golden set：
  - 文件：`fixtures/golden_rag_questions.json`
  - dataset：`rag-golden-v2-20260602-real-cv`
  - 样本数：30
  - 状态：`real-cv-rebuilt-pending-human-review`

## Golden Set 结构

case type 分布：

| 类型 | 数量 |
| --- | ---: |
| common_question | 20 |
| multi_document | 3 |
| stale_or_conflicting | 2 |
| no_answer | 5 |

golden layer 分布：

| 分层 | 数量 |
| --- | ---: |
| core_high_info | 18 |
| ocr_regression | 4 |
| low_info_stress | 3 |
| non_target_negative | 5 |

## 校验结果

命令：

```powershell
.\.venv\Scripts\python.exe scripts\validate_golden_rag_set.py fixtures\golden_rag_questions.json --run-dir baseline\real-cv-golden-rebuild-20260602
```

结果：通过。

## BM25 Retriever 指标

| 范围 | 样本数 | MRR | P@1 | R@10 | Weighted R@10 | All Primary Hit | All Expected Hit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| overall | 30 | 0.913 | 0.840 | 0.940 | 0.950 | 1.000 | 0.880 |
| core_high_info | 18 | 0.917 | 0.833 | 0.972 | 0.981 | 1.000 | 0.944 |
| ocr_regression | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| low_info_stress | 3 | 0.778 | 0.667 | 0.667 | 0.690 | 1.000 | 0.333 |
| non_target_negative | 5 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

说明：

- `non_target_negative` 是 no-answer 样本，`expected_documents=[]`，因此 retriever 命中类指标为 0 属于预期；这层应主要用于 generator/no-answer gate 观测。
- `core_high_info` 的 MRR 从前一轮低位显著恢复，核心原因是候选人样本从极简 `base_resume.md` 换成了真实高信息密度 CV，query、answer 和 expected labels 均重新绑定到新 artifact。
- `low_info_stress` 的 all_expected 较低，主要因为该层包含 gap/ranking/candidate-profile 等混合 scope 文档，primary 能命中，但 supporting 文档排序和共同召回仍不稳定；该层不应进入主 headline。

## 后续人工审核重点

- 检查 30 条问题是否符合真实用户问法，而不是过度贴合 BM25 关键词。
- 复核 `jd-019:gap-map`、`jd-024:ranking`、`candidate-profile` 这类 mixed-scope expected documents 是否适合作为 retriever 主评测标签。
- 针对 no-answer 层补跑 generator/no-answer gate，确认不会把 Docker、Java token、通用 AI 经验误答成 Kubernetes、Java 微服务、金融风控或医疗影像经验。

## 2026-06-02 扩展到 60 条 Golden Set

本轮为了测试 RAG 健壮性，将 `fixtures/golden_rag_questions.json` 从 30 条扩展到 60 条，并把 validator 的样本数量上限从 50 调整为 60。

新增覆盖类别：

| 类别 | 新增数量 | 目的 |
| --- | ---: | --- |
| 精确事实型问题 | 4 | 检查数字、项目名、学校/GPA 等硬事实能否精确召回。 |
| 概念解释型问题 | 4 | 检查 Evidence Gate、no-answer gate、Pydantic、fan-out 等概念是否能回到项目上下文。 |
| 多证据综合型问题 | 2 | 检查 framework + 项目、RAG + eval 两条证据链能否合并。 |
| 同义表达问题 | 3 | 检查“搜出来准不准”“AI-native builder”“demo”等表达能否映射到正式 artifact。 |
| 模糊口语问题 | 4 | 检查“工具别乱跑”“模型别瞎写格式”等口语问题是否能召回结构化证据。 |
| no-answer / 相似概念干扰 | 7 | 检查 pgvector vs Milvus/Qdrant 运维、FastAPI vs 资深架构师、RAG eval vs 模型训练等边界。 |
| 跨章节问题 | 3 | 检查教育、候选人 profile、项目、传播/文档化能力能否合并解释。 |
| OCR / 低信息压力 | 3 | 检查 OCR 框架枚举、低信息 JD、公平性边界。 |

扩展后分布：

| 维度 | 分布 |
| --- | --- |
| case_type | common_question 36；multi_document 10；stale_or_conflicting 5；no_answer 9 |
| golden_layer | core_high_info 38；ocr_regression 7；low_info_stress 6；non_target_negative 9 |
| retriever labels | 32 |

校验命令：

```powershell
.\.venv\Scripts\python.exe scripts\validate_golden_rag_set.py fixtures\golden_rag_questions.json --run-dir baseline\real-cv-golden-rebuild-20260602
```

结果：通过，`sample_count=60`。

BM25 retriever 指标：

| 范围 | 样本数 | MRR | P@1 | R@10 | Weighted R@10 | All Primary Hit | All Expected Hit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| overall | 60 | 0.657 | 0.549 | 0.794 | 0.802 | 0.824 | 0.706 |
| core_high_info | 38 | 0.600 | 0.474 | 0.789 | 0.807 | 0.842 | 0.737 |
| ocr_regression | 7 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| low_info_stress | 6 | 0.621 | 0.500 | 0.583 | 0.540 | 0.500 | 0.167 |
| non_target_negative | 9 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

按新增 robustness category 切片：

| 类别 | Answerable 数 | MRR | P@1 | R@10 | Primary Hit |
| --- | ---: | ---: | ---: | ---: | ---: |
| precise_fact | 4 | 0.536 | 0.250 | 1.000 | 1.000 |
| concept_explanation | 4 | 0.373 | 0.250 | 1.000 | 1.000 |
| multi_evidence | 2 | 0.000 | 0.000 | 0.000 | 0.000 |
| synonym_expression | 3 | 0.108 | 0.000 | 0.500 | 0.667 |
| fuzzy_colloquial | 4 | 0.208 | 0.000 | 0.500 | 0.500 |
| cross_section | 3 | 0.500 | 0.333 | 0.333 | 0.667 |
| similar_concept_interference | 3 | 0.750 | 0.667 | 0.667 | 0.333 |
| ocr_regression | 2 | 1.000 | 1.000 | 1.000 | 1.000 |
| low_info_stress | 1 | 0.143 | 0.000 | 0.500 | 0.000 |

观察：

- 60 条后主指标下降是预期结果：新增样本减少了关键词直给，增加了口语、同义、跨章节、多证据综合和相似概念干扰。
- 精确事实和概念解释的 `R@10=1.0`，说明证据通常能进候选集，但 `P@1/MRR` 不高，主要问题是排序。
- 多证据综合、同义表达、模糊口语、跨章节是当前最明显短板，后续应优先考虑 query rewrite、multi-hop retrieval 或 evidence aggregation，而不是只继续调 BM25。
- OCR 层仍然满分，说明当前 OCR regression 样本更像关键词定位题；如果要测 OCR 鲁棒性，需要补更少关键词、更口语化的 OCR 问题。
- no-answer 层不参与 answerable retriever 命中，仍应通过 generator/no-answer gate 单独观测。

## 2026-06-02 OCR 样本加固

前一轮 `ocr_regression` 层 MRR/P@1/R@10 全为 1.0，原因不是 OCR/RAG 已经满分，而是 OCR 样本几乎都是关键词直连题：query 中直接写出 `Python`、`RAG`、`Function Calling`、`GitHub Actions`、`LangGraph` 等词，BM25 可以直接定位到对应 `jd-025-req-*`。

本轮在 60 条总量不变的前提下，重写 7 条 OCR 层样本，覆盖：

| 类型 | 示例 |
| --- | --- |
| 弱关键词岗位方向判断 | “这个图片岗位是不是更像开发者工具和 AI 工作流方向？” |
| 跨 OCR requirement 综合 | “工程基础和 agent 调试分别要求什么？” |
| OCR 噪声识别 | “哪些内容因为 OCR 质量不能高置信引用？” |
| 相似框架干扰 | “提到 Dify/n8n 时能确认哪些？” |
| 低信息 OCR 判定 | “宽泛技能枚举是否应进入 core headline？” |
| 跨句/截断综合 | “个人 demo / 开源实践 / 工具项目要求能否对上？” |
| 口语化调试问题 | “agent 不稳定、工具失败、检索不准时会不会拆问题？” |

加固后校验通过：

```powershell
.\.venv\Scripts\python.exe scripts\validate_golden_rag_set.py fixtures\golden_rag_questions.json --run-dir baseline\real-cv-golden-rebuild-20260602
```

加固后 BM25 指标：

| 范围 | MRR | P@1 | R@10 | Weighted R@10 | All Primary Hit | All Expected Hit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| overall | 0.590 | 0.471 | 0.745 | 0.753 | 0.784 | 0.627 |
| core_high_info | 0.600 | 0.474 | 0.789 | 0.807 | 0.842 | 0.737 |
| ocr_regression | 0.512 | 0.429 | 0.643 | 0.643 | 0.714 | 0.429 |

结论：

- OCR 层从 1.000 回落到 0.512，说明新样本不再只是关键词 smoke test，已经开始测 OCR 噪声、弱表达、跨 requirement 和相似概念干扰。
- core 指标保持不变，说明本轮只加固 OCR 压力层，没有污染 headline core。
- 当前 OCR 层的新短板是排序与多证据共同命中：primary hit 还有 0.714，但 all expected hit 只有 0.429，后续需要 query rewrite 或 OCR artifact 层的结构化 alias/normalization。
