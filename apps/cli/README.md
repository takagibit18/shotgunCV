# CLI 应用

`apps/cli` 是 v1 的主交互入口，负责串联 `ingest/analyze/generate/evaluate/plan/report` 六个阶段。

该目录只承载命令行参数和流程编排，不承载领域核心逻辑。
