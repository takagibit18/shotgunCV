# Golden Set 分层设计 - 2026-06-02

## 目标

当前 golden set 不能再把高质量 JD、低信息 JD、OCR 污染样本和非目标域负样本混成一个平均数。分层目标是让主指标公平衡量 RAG 能力，同时保留真实市场中的模糊 JD、图片 OCR、无答案问题作为独立压力观测。

`case_type` 和 `golden_layer` 是两条正交轴：

- `case_type` 描述问题形态：单证据、多文档、无答案、过时或冲突。
- `golden_layer` 描述样本质量和评测用途：是否进入主指标、压力集还是回归集。

## 分层枚举

| golden_layer | 用途 | 是否进入主 RAG 指标 |
|---|---|---|
| `core_high_info` | 高信息密度、可稳定复核的主评测样本 | 是 |
| `low_info_stress` | 真实招聘市场中宽泛、模糊、低信息 JD 的鲁棒性压力样本 | 否，单独报告 |
| `ocr_regression` | 图片/OCR/切分质量回归样本，用于观测采集和清洗链路 | 否，单独报告 |
| `non_target_negative` | 非目标域、能力不存在、应拒答或低置信回答的负样本 | 否，单独报告 |

## Core 准入规则

样本进入 `core_high_info` 必须同时满足：

- raw JD 来自可读文本或高质量 PDF，或图片经过人工重采集后文本质量稳定。
- JD 有可区分候选人的真实招聘约束，不只是学历、宽泛技能词或平台 UI 文案。
- `expected_documents` 使用细粒度 artifact，例如 `requirement_evidence`、`gap_map`、`ranking_explanation`、`candidate_evidence`。
- 不使用 `jd-xxx` 这种 JD-level expected label 兜底。
- 引用的 requirement artifact 通过质量门：非 label-only、非 mojibake、非 OCR 断字、非路径型 evidence、refs 去重。
- 在当前 clean baseline run 中 label coverage 为 100%，否则不得解释 MRR/recall。

## 非 Core 层规则

`low_info_stress` 用来保留现实中的低信息 JD，例如只给学历、Remote、宽泛 AI/LLM/Python/AWS 技能的岗位。它可以帮助判断系统面对弱约束输入时是否保守，但不应拉低或抬高主 RAG 指标。

`ocr_regression` 用来保留图片采集链路问题。图片原始内容可能有价值，但只要当前 OCR 产物存在中文断字、空格污染、符号噪声、requirement matrix 为 0 或极少，就不能进入 core。修复路径是重采集文本或引入更可靠的 vision extraction，再晋级。

`non_target_negative` 用来测试拒答、低置信和非目标域隔离。它的主要指标不是 MRR，而是 no-answer gate、abstention、unsupported claim 和误召回泄漏。

## 指标解释口径

报告必须同时输出整体指标和 `golden_layer` 拆分指标。

主决策只看 `core_high_info`：

- `MRR`
- `P@1`
- `R@k`
- `weighted R@k`
- `all_primary_hit`
- `all_expected_hit`

压力层只做 guardrail：

- `low_info_stress`：观察宽泛问题是否过度自信、是否误把弱相关证据排太前。
- `ocr_regression`：观察 OCR 修复前后 label coverage、zero-hit 和 artifact 质量门变化。
- `non_target_negative`：观察 no-answer gate、abstention rate 和 generator 是否编造。

如果整体指标和 core 指标方向相反，以 core 指标为主；如果 core 提升但压力层明显劣化，需要记录为风险，不直接阻塞主链路迭代。

## 当前语料建议

保留为 `core_high_info` 的优先候选：

- `量化派AI Native 全栈工程师如LLM  Agent AI应用开发.pdf`
- `JD10_RAG_Backend_Engineer_high.txt`
- `JD8_AI_Agent_Platform_Engineer_high.txt`
- `JD9_LLM_Evaluation_Engineer_high.txt`
- `JD14_Technical_Support_AI_Platform_medium.txt`
- `JD7_Cummins_AI_Agent_Intern.txt`
- `JD4_AMD_AI_Agent.txt`
- `JD1_YOIT_AI_Evaluation_Specialist.txt`

默认放入 `ocr_regression`：

- `Minimax.png`
- `sharpa.png`
- `wave.png`
- `深圳.png`
- `清华实习.png`
- `百图.png`

默认放入 `low_info_stress`：

- `AI_engineer.png`
- `JD2_拼多多_服务研发.txt`
- `JD3_君和律所_AI产品实习.txt`
- `JD5_Voice_Coach.txt`

默认放入 `non_target_negative`：

- `JD15_HR_Recruiting_Coordinator_low.txt`
- `JD16_Legal_Assistant_Contracts_low.txt`
- `JD17_Sales_Account_Executive_SaaS_low.txt`
- `JD18_Finance_Operations_Analyst_low.txt`
- `JD19_Marketing_Content_Manager_low.txt`
- 明确询问候选人不存在能力的 no-answer 样本

## 落地状态

- `scripts/validate_golden_rag_set.py` 要求每条样本声明 `metadata.golden_layer`，并拒绝未知层。
- `scripts/evaluate_rag_layers.py` 在 retriever 和 generator 报告中输出 `golden_layer_metrics`。
- `fixtures/golden_rag_questions.json` 仍然是本地 ignored artifact；realign 前必须先完成 layer 标注。

## 2026-06-02 初始观测

使用当前 clean baseline：

`baseline/runs-formal-20260601/baseline-formal-r3-full-raw-library-clean-20260601`

输出：

`baseline/golden-layering-20260602/bm25-layered.json`

本地 golden 分层分布：

| golden_layer | 样本数 |
|---|---:|
| `core_high_info` | 9 |
| `low_info_stress` | 5 |
| `non_target_negative` | 10 |
| `ocr_regression` | 6 |

BM25 retriever 分层指标：

| golden_layer | answerable queries | MRR | P@1 | R@10 | weighted R@10 | all primary hit | all expected hit |
|---|---:|---:|---:|---:|---:|---:|---:|
| `core_high_info` | 9 | 0.553 | 0.333 | 0.889 | 0.889 | 0.889 | 0.778 |
| `low_info_stress` | 5 | 0.450 | 0.200 | 0.900 | 0.867 | 0.800 | 0.800 |
| `non_target_negative` | 5 | 0.174 | 0.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| `ocr_regression` | 6 | 0.625 | 0.333 | 0.917 | 0.905 | 0.833 | 0.833 |

整体 BM25 MRR 为 0.474，`core_high_info` MRR 为 0.553。后续解释主链路质量时应优先引用 core 指标；非目标层的 answerable 子集 MRR 很低，但它本身不是主 RAG 排序能力样本，应和 no-answer gate 一起解释。

## 后续流程

1. 先重跑 clean baseline，确保 artifacts 通过 requirement/evidence 质量门。
2. 对 golden 样本先标注 `golden_layer`，再做 expected document realign。
3. realign 后先跑 validator 的 artifact audit，再跑 retriever layer。
4. 记录整体指标和 `core_high_info` 指标；主结论只引用 core。
5. OCR 样本必须等重采集或 vision extraction 质量达标后，才能从 `ocr_regression` 晋级 core。
