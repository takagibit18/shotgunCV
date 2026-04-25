# ShotgunCV 系统设计

## v0.4.0 Web 上传草稿边界

Web 从只读 viewer 扩展为本地单用户上传入口，但仍不成为第二套业务执行入口。`/upload` 只负责把 CV/JD 原始文件保存到 `runs/<runId>/input_files/`，并写入 `ingest/upload_manifest.json` 与 `config/run_config.json`。

`ingest/upload_manifest.json` 是 Web 草稿清单，只记录上传元数据、相对路径和下一步 CLI 命令；它不包含 `candidate_resume_text`，也不包含 `jd_inputs[].content`。真正的 `ingest/manifest.json` 仍由 Python CLI 生成，后续解析、OCR、vision fallback、评分、排序和报告继续以 Python pipeline 为唯一业务真源。

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
