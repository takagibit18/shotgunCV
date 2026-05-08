# ShotgunCV 系统设计

## v0.5.1 Web 上传与输入一致性边界

Web 从只读 viewer 扩展为本地单用户上传入口，但仍不成为第二套业务执行入口。`/upload` 只负责把 CV/JD 原始文件保存到 `runs/<runId>/input_files/`，并写入 `ingest/upload_manifest.json` 与 `config/run_config.json`。

`ingest/upload_manifest.json` 是 Web 草稿清单，当前 schema 为 `v0.5.1-upload-manifest`，只记录上传元数据、相对路径和下一步 CLI 命令；它不包含 `candidate_resume_text`，也不包含 `jd_inputs[].content`。真正的 `ingest/manifest.json` 仍由 Python CLI 生成，后续解析、OCR、vision fallback、评分、排序和报告继续以 Python pipeline 为唯一业务真源。

Python ingest 会读取 Web 草稿清单并把上传元数据合并进统一业务 manifest。`candidate_inputs[]` 与 `jd_inputs[]` 共享 `role`、`source_origin`、`original_name`、`relative_path`、`size_bytes`、`source_type`、`source_value`、`media_type`、`text` 与抽取状态字段；`jd_inputs[]` 额外保留 `content` 兼容 analyzer。`source_origin` 固定用于区分 `upload`、`cli` 与 `fixture`，run 详情页只读取这些结构化产物展示输入来源，不反向解析原始文件。

## v0.5.2 输入抽取容错边界

Python ingest 是 PDF、图片 OCR、vision fallback 与文本抽取的唯一执行层。Web 上传入口继续只保存原始文件和 `ingest/upload_manifest.json`，不解析正文、不写入 `candidate_resume_text` 或 `jd_inputs[].content`。

`ingest/manifest.json` 保留所有被发现的输入项。单个文件抽取失败时，对应输入项写入 `text: ""`、`extraction_status: "unparseable"` 和 `extraction_error`，同时在 `input_warnings[]` 中记录角色、原始文件名、相对路径和错误摘要。只有当 CV 或 JD 角色没有任何可用正文时，ingest 阶段才失败。

## 定位与目标

系统采用固定批处理架构，以“多岗位输入、多版本生成、评估排序、策略输出”为主目标。设计优先保证可解释与可复现，而不是一次性生成质量。

## 核心流程

固定流水线：

1. `ingest`
2. `analyze`
3. `generate`
4. `evaluate`
5. `plan`
6. `report`

混合生成策略：

1. 对输入 JD 做岗位簇识别。
2. 先生成岗位簇共享版本。
3. 用共享版本做全量首轮评分。
4. 对高潜力 JD 生成定制版本。
5. 二轮评分后更新排序与策略输出。

## 数据对象与接口

- 岗位画像（`JDProfile`）：岗位标题、公司、职责、要求、关键词、来源。
- 候选人画像（`CandidateProfile`）：经历、项目、技能、约束、偏好。
- 简历版本（`ResumeVariant`）：版本类型、目标 JD 集合、强调点、拉伸点。
- 评分卡（`ScoreCard`）：规则分、判分分、总分和解释。
- 缺口映射（`GapMap`）：补强概念、风险点、面试注意事项。
- 策略建议（`ApplicationStrategy`）：是否投递、推荐版本、优先级、理由。

接口约束：

- CLI 子命令保持 `shotguncv ingest/analyze/generate/evaluate/plan/report`。
- 每个阶段都以 `run_dir` 作为输入输出边界。
- `ingest` 负责写入 `run_dir/config/run_config.json`，后续阶段统一读取该快照。
- 各阶段产物使用结构化文件持久化，供后续阶段消费。
- v1 最小闭环默认写入：
  - `config/run_config.json`
  - `ingest/manifest.json`
  - `analyze/candidate_profile.json`
  - `analyze/jd_profiles.json`
  - `generate/resume_variants.json`
  - `evaluate/scorecards.json`
  - `evaluate/gap_maps.json`
  - `evaluate/eval_summary.json`
  - `plan/application_strategies.json`
  - `report/summary.md`
- `generate` 与 `evaluate` 均通过 provider 接口落地，默认 deterministic，可按 `run_config` 切换到 OpenAI。
- OpenAI 仅负责生成 summary 与 judge rationale，`overall_score` 仍由规则公式决定。

## 评估与质量门禁

- 评估层必须同时包含规则评估与结构化判分。
- `ScoreCard` 是排序唯一输入，不允许绕过评估直接排序。
- 拉伸表达与证据不足内容必须体现在 `gap_map` 与策略说明中。
- 评分逻辑变更必须通过回归测试后才允许进入主分支。

## 非目标与边界

- Web Viewer 为只读界面，不触发 pipeline，也不写入 `runs/`。
- v1 不实现自动投递、浏览器自动化和 CRM。
- v1 不做截图/OCR 主链路，仅保留后续接口扩展能力。
## v0.5.3 运行管理边界

`run_dir/run_status.json` 是 Web 与 CLI 共享的最小运行状态文件，记录 `draft/queued/running/done/failed`、当前阶段、开始/结束时间、失败阶段、失败摘要和最近动作。阶段是否完成仍以 `run_dir` 中的结构化产物为准，状态文件只承载运行观测和操作反馈，不替代阶段产物判断。

Web 可以触发本机 `shotguncv` CLI，但不直接调用 Python 内部函数，也不复制 ingest/analyze/generate/evaluate/plan/report 业务逻辑。Web 的写入范围限定为草稿输入文件、`ingest/upload_manifest.json`、`config/run_config.json`、`run_status.json`，以及删除允许删除的 `draft/failed` run 目录。`running/queued` run 禁止删除。

失败后支持两种恢复路径：`retry_full` 清理 `analyze` 及之后阶段产物并重新从 ingest 执行；`resume_failed` 根据现有阶段产物定位第一个未完成阶段，只清理该阶段及后续阶段。两种路径都以 CLI 为执行入口，并在失败时把错误摘要写回 `run_status.json`。

## v0.5.4 观测与审计边界

CLI 在 `run_dir/logs/run_events.jsonl` 写入结构化 JSONL 事件：`run_started`、`run_finished`、`stage_started`、`stage_finished`、`stage_failed`。每条事件包含时间戳；阶段结束和失败事件记录耗时；失败事件记录错误类型和短摘要。日志不写入 CV/JD 原文，只记录输入数量、provider/model 摘要和脱敏后的 CLI 参数摘要。

Web 只读取 `logs/run_events.jsonl` 并渲染 run timeline，不引入集中式监控、远程队列或数据库。日志文件损坏的单行会被忽略，避免一个坏事件阻断整个 run detail 页面。

## v0.5.5 稳定性与回归边界

v0.5.5 的稳定性基线由 targeted Python/Web 测试承担：CLI 覆盖状态文件、失败记录和结构化日志；Web 覆盖草稿编辑、删除、run action、状态读取、timeline 读取和报告展示。文档表述保持本地单用户边界，不承诺自动投递、CRM、远程队列或多用户协作。

## v0.6.4 简历优化工作台边界

`/resume` 是 Web 端的简历优化 artifact 编排页，不是新的生成入口。它聚合 `generate/resume_variants.json`、`analyze/requirement_matrix.json`、`analyze/preflight_gates.json`、`plan/application_strategies.json` 与 `run_status.json`，用于展示版本摘要、证据约束、改写边界、投递前检查和下一步动作。

Web 不在 `/resume` 重新生成简历、不改写候选人材料、不调用 Python 内部业务函数，也不展示完整 CV/JD 原文。`/upload` 继续保留为创建草稿入口；完整 pipeline 仍由 CLI 或既有 run action 触发，Python pipeline 仍是唯一业务真源。

## v0.6.5 数据密度展示边界

首页运行队列和评估结果列表可以在 Web 层增加轻量趋势摘要和客户端分页，用于承载更多 run 与更多 JD。趋势指标只从现有 `run_dir` metadata、状态文件和评估 artifacts 推导，不新增持久化趋势文件，不影响排序、评分或投递策略的业务判断。
