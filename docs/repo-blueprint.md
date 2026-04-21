# ShotgunCV 仓库蓝图

## 定位与目标

仓库结构围绕“可扩展流水线 + 可复现评估”设计，确保 v1 的 CLI 路径可落地，同时为后续 Web 和多 Provider 接入保留演进空间。

## 核心流程

目录协同直接对应流水线阶段与质量闭环：

- `apps/cli/` 负责运行入口与阶段编排。
- `packages/py-core/` 负责对象、规则、排序与流水线原语。
- `packages/py-agents/` 负责编排与判分提示词。
- `packages/py-evals/` 负责规则校验与回归验证。
- `fixtures/` 与 `tests/` 负责可重复验证。

## 数据对象与接口

目录与接口边界：

- `apps/cli/`
  - 对外暴露命令：`shotguncv ingest/analyze/generate/evaluate/plan/report`
  - 不承载核心领域逻辑
  - 负责统一 `run_dir` 参数与阶段调度
- `packages/py-core/`
  - 对外提供对象：`JDProfile`、`CandidateProfile`、`ResumeVariant`、`ScoreCard`、`GapMap`、`ApplicationStrategy`
  - 提供阶段间的结构化读写契约
- `packages/py-agents/`
  - 对外提供 generator/judge provider 协议与 deterministic stub 实现
- `packages/py-evals/`
  - 对外提供评估与回归入口
  - 输出评估摘要供 `report` 阶段消费

## 评估与质量门禁

- 所有策略或评分改动必须在 `fixtures/` 上可回放。
- `tests/` 至少覆盖对象契约、阶段链路与排序回归。
- `docs/` 文档必须和实现对象命名一致。
- 文档、注释、提交语言规范以 `docs/conventions.md` 与 `agent.md` 为准。
- `examples/` 应提供最小 CLI 运行示例，覆盖从 `ingest` 到 `report` 的串行路径。

## 非目标与边界

- `apps/web/` 当前仅为占位目录，不纳入 v1 功能交付。
- `packages/ts-shared/` 当前仅保留契约扩展位。
- v1 不引入与主流程无关的目录层级或服务拆分。
