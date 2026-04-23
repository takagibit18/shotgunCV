# CLI 应用

`apps/cli` 是 v1 的主交互入口，负责串联 `ingest/analyze/generate/evaluate/plan/report` 六个阶段。

该目录只承载命令行参数和流程编排，不承载领域核心逻辑。

## 当前参数约定

- 所有子命令都要求 `--run-dir`
- `ingest` 额外要求：
  - `--candidate-id`
  - `--candidate-resume`
  - `--jd-file`，可重复传入

## 阶段输出

- `ingest`：写入原始输入清单与候选人简历原文
- `analyze`：写入 `CandidateProfile` 与 `JDProfile` 列表
- `generate`：按 JD 写入 `JD-specific` 的 `ResumeVariant`
- `evaluate`：写入 `ScoreCard`、`GapMap`、`eval_summary`
- `plan`：写入 `ApplicationStrategy`
- `report`：写入 Markdown 汇总报告
