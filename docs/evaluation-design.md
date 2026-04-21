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
