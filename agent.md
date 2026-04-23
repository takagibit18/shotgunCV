# ShotgunCV Agent 协作规范

## 项目使命

`ShotgunCV` 是一个面向海投场景的 `Pipeline-first` 简历运营系统。仓库的核心目标是批量完成岗位解析、混合生成、评估打分、排序决策与投递策略输出。

## 语言与提交底层约束

- 仓库内 Markdown 文档统一使用中文主文本。
- 代码注释统一使用英文。
- Git 提交信息统一使用英文。
- 术语表达统一采用“中文主述 + 英文标识”格式，例如：评分卡（`ScoreCard`）。

## 产品边界

- 必须围绕 `ingest -> analyze -> generate -> evaluate -> rank -> report` 主流程构建。
- 目标是海投决策支持，不是单岗位简历润色。
- 评估系统是产品能力本身，不是附属工具。
- v1 不实现自动投递、招聘站点自动化、CRM 流程。
- v1 不将截图/OCR 作为主输入路径。

## 经历重述边界

- 允许在有证据前提下强化表述真实经历。
- 对“拉伸表达”必须显式标注。
- 证据不足内容必须落入 `gap` 或 `catch-up` 输出。
- 禁止虚构岗位、头衔、项目、成果或不可追溯结论。

## 仓库分层规则

- `packages/py-core/` 负责领域模型、评分排序逻辑与流水线原语。
- `packages/py-evals/` 负责评估规则、判分器与回归验证。
- `packages/py-agents/` 负责编排与提示词资产。
- `apps/cli/` 只做入口层，不承载领域核心逻辑。
- `apps/web/` 为后续扩展保留，不与核心逻辑耦合。

## 质量门禁

- 新行为必须配套测试。
- 生成或策略变更必须配套 `fixtures/evals/tests`。
- 新评分逻辑必须说明对排序与风险的影响。
- 优先输出结构化结果，避免纯自然语言结果。
- 运行产物必须可复现，避免仅控制台瞬时输出。

## ❌ Forbidden commands

- DO NOT run: npm test
- DO NOT run: pnpm test
- DO NOT run: pytest (without file scope)

## ✅ Allowed commands

- npm run test -- --run
- vitest run <file>
- pytest <file> -q

## Execution policy

- Always run the smallest possible test scope
- Never run full test suite unless explicitly requested

## 文档维护规则

- 架构或产品关键取舍变化时更新 `docs/decision-log.md`。
- 流水线阶段或对象定义变化时更新 `docs/system-design.md`。
- 评估维度或判分契约变化时更新 `docs/evaluation-design.md`。
- 新增文档前先检查 `docs/README.md` 并更新索引。
