# 文档与工程约束

## 目标

本规范用于消除语言混杂，降低文档和实现阶段的理解偏差。

## 统一语言规则

- Markdown 文档统一使用中文主文本。
- 代码注释统一使用英文。
- Git 提交信息统一使用英文。

## 术语书写规则

- 文档中使用“中文主述 + 英文标识保留”格式。
- 示例：评分卡（`ScoreCard`）、候选人画像（`CandidateProfile`）。
- 代码中的类名、函数名、字段名保持英文，不做中文化。

## 提交前自检清单

- 所有新建或修改的 `.md` 文件是否为中文主文本。
- 是否出现中文代码注释；若出现需改为英文。
- 本次提交信息是否为英文。
- 核心对象命名是否与系统文档一致：
  - `JDProfile`
  - `CandidateProfile`
  - `ResumeVariant`
  - `ScoreCard`
  - `GapMap`
  - `ApplicationStrategy`

## 适用范围

本规范适用于仓库自维护内容（根目录、`docs/`、`apps/`、`packages/`、`examples/`、`fixtures/` 下的 Markdown 文档）。
