# ShotgunCV v0.5.0-v0.5.5 落地规划

## Summary

v0.5 目标是把现有 Web 草稿入口推进到 `Draft-to-Run` 最小闭环：Web 可以触发本地 Python pipeline，并展示运行状态、阶段产物、失败摘要和输入来源，但不承载业务解析、生成、评估或排序逻辑。

核心边界保持不变：

- Python pipeline 是唯一业务真源。
- Web 只负责上传、触发、状态展示和产物读取。
- `run_config.json` 与 `ingest/manifest.json` 构成可复现执行快照。
- 所有状态、日志、审计和阶段产物落在 `run_dir`，不引入二级数据库。

## Version Plan

### v0.5.0 Draft-to-Run 最小闭环

目标：Web 草稿可以升级为可执行 run，完成 `ingest -> analyze -> generate -> evaluate -> plan -> report` 全链路。

关键变化：

- `/api/runs/drafts` 保留草稿创建语义，新增执行入口用于把草稿推进到 `queued/running/done/failed`。
- Web 执行层只调用 `shotguncv run` 或等价 Python CLI，不复制 pipeline 逻辑。
- 在 `run_dir` 写入最小状态文件，例如 `run_status.json`，包含 `status`、`current_stage`、`started_at`、`finished_at`、`error_stage`、`error_summary`。
- 状态机限定为 `draft -> queued -> running -> done/failed`。
- 任一阶段失败时，API 返回阶段名和简短错误摘要，详情仍保留在 run 目录日志中。

验收标准：

- Web 创建草稿后可以触发本地 pipeline。
- 成功运行后生成现有完整产物与 `report/summary.md`。
- 失败 run 能在详情页看到失败阶段和简短错误。
- Web 不直接调用 Python 内部函数，只调用 CLI。

### v0.5.1 输入合并与一致性强化

目标：Web 上传入口与 CLI ingest 的多目录/多文件输入模型对齐。

关键变化：

- `upload_manifest.json` 调整为与 Python ingest 输入模型一致的元数据清单，继续不保存正文解析结果。
- Web 只写上传文件清单，Python ingest 统一读取目录或 manifest 生成 `ingest/manifest.json`。
- run 详情页展示输入来源清单，区分 `upload`、`cli`、`fixture`。
- CLI 与 Web 入口使用相同的 candidate/JD 多输入语义，避免同一批文件产生不同 manifest。

验收标准：

- Web 上传多个 CV/JD 文件后，ingest 生成的 `candidate_inputs` 与 `jd_inputs` 完整保留来源。
- CLI 多目录输入与 Web 上传输入在 manifest 字段结构上保持一致。
- run 详情页能展示每个输入的角色、原始文件名、相对路径、大小和来源类型。

### v0.5.2 输入抽取并入 pipeline

目标：PDF/图片文本抽取成为 ingest 的正式能力，并对 Web 上传透明。

关键变化：

- PDF、图片 OCR、vision fallback 只在 Python ingest 层执行。
- ingest 产物保留原始来源、抽取文本、抽取状态、抽取 provider 和错误摘要。
- Web 上传支持 `.pdf/.png/.jpg/.jpeg`，但只负责文件落盘与 manifest 记录。
- 单个输入不可解析时记录为 `unparseable` 或等价状态，不阻塞其他输入；若 CV 或 JD 最终无有效文本，则 ingest 阶段失败。

验收标准：

- text/markdown/PDF/image 输入均经过统一 ingest manifest 输出。
- OCR 或 vision 失败时，错误可追溯到单个输入文件。
- Web 不包含任何 PDF/OCR/vision 解析代码。

### v0.5.3 运行管理能力

目标：补齐草稿编辑、删除、重试和阶段继续执行。

关键变化：

- 草稿阶段允许替换文件、追加 JD、更新 candidate meta。
- 支持删除仍处于 `draft/failed` 的 run；对 `running` run 禁止删除或要求先终止。
- 支持失败后重试整个 run，或从最近未完成阶段继续执行。
- 阶段继续执行基于 `run_dir` 中已存在的阶段产物判断，不依赖数据库状态。
- run 详情页展示阶段级状态和最近一次失败原因。

验收标准：

- 草稿修改后重新触发时，新的 `run_config.json` 与输入 manifest 能反映修改。
- 已完成阶段不会被误判为未完成。
- 从失败阶段重试不会破坏之前成功阶段产物，除非显式重新运行全链路。

### v0.5.4 观测性与最小审计

目标：让本地 run 可诊断、可回放、可解释。

关键变化：

- 新增结构化日志，写入 `run_dir/logs/*.jsonl`。
- 每个阶段记录 `stage_started`、`stage_finished`、`stage_failed`、耗时、错误码和错误摘要。
- 记录最小审计字段：触发入口、输入规模、模型配置摘要、CLI 命令摘要。
- Web 详情页展示 run 时间线，不引入集中式监控。

验收标准：

- 任意 run 可通过 `logs/*.jsonl` 还原阶段顺序和失败原因。
- Web 时间线与本地日志一致。
- 日志不写入原始简历/JD 全文，只记录路径、计数、摘要和错误。

### v0.5.5 稳定性与文档收敛

目标：收敛 v0.5 能力边界，建立回归基线。

关键变化：

- 增加端到端集成测试：Web 上传草稿 -> 触发 run -> 完整产物 -> Web 读取报告。
- 更新 deterministic fixtures，保证本地回归稳定。
- 同步更新 `README.md`、`docs/decision-log.md`、`docs/system-design.md`、`docs/product-requirements.md`。
- 明确文档表述：Web 不是业务真源，只是本地触发与观察层。

验收标准：

- Python 测试覆盖 CLI pipeline、输入抽取、阶段恢复和失败记录。
- Web 测试覆盖草稿创建、触发、状态展示、输入清单和失败详情。
- 文档与实际能力一致，不承诺自动投递、CRM、远程队列或多用户协作。

## Public Interfaces

计划新增或稳定以下接口与文件契约：

- `run_dir/config/run_config.json`：唯一执行配置快照，由草稿创建或 CLI ingest 初始化，后续阶段只读。
- `run_dir/ingest/upload_manifest.json`：Web 上传元数据清单，不包含解析正文。
- `run_dir/ingest/manifest.json`：Python ingest 生成的唯一业务输入清单，包含抽取后的可执行输入。
- `run_dir/run_status.json`：最小运行状态文件，承载 `draft/queued/running/done/failed` 状态。
- `run_dir/logs/*.jsonl`：阶段级结构化日志和最小审计记录。
- Web API：保留草稿创建接口，新增 run 触发、状态读取、重试/继续执行相关接口。
- CLI：继续以 `shotguncv run/ingest/analyze/generate/evaluate/plan/report --run-dir` 为执行入口。

## Test Plan

- Python 单元测试：覆盖 ingest 多输入合并、PDF/图片抽取状态、不可解析输入、阶段产物检测、失败摘要生成。
- Python 集成测试：使用 deterministic config 跑完整 `shotguncv run`，断言所有阶段产物、状态文件和日志存在。
- Web 单元测试：覆盖 draft API、run status 读取、输入来源展示、失败状态展示。
- Web 集成测试：模拟上传文件创建草稿，触发 CLI，轮询到 `done/failed`，再读取详情页和报告页。
- 回归测试：固定 fixtures 下重复运行应产生稳定排序、稳定阶段状态和稳定报告关键字段。

## Assumptions

- v0.5 仍是本地单用户模式，不引入远程队列、多用户权限或数据库。
- Web 触发 Python CLI 允许使用本机环境中的 `shotguncv` 命令。
- `run_dir` 是跨 Web/CLI 的唯一状态边界。
- PDF/OCR/vision 的外部依赖缺失时，系统应给出可操作错误，而不是静默失败。
- 本轮只落地 `docs/plan.md`，不实施代码、测试或其他文档变更。
