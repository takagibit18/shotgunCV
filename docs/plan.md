# ShotgunCV v0.5.0-v0.5.7 落地规划

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

### v0.5.6 观测性收盘与质量门槛

目标：补齐 v0.5 收盘版本的运行可信度，让一次本地 run 不只显示“跑完”，还能够解释输入规模、实际模型、agent/tool 执行、token 消耗、fallback 与质量风险。

关键变化：

- 修正 `input_scale` 统计口径，区分 CLI 参数源数量与 ingest 后实际解析出的文件数量，例如 `cli_jd_sources: 1`、`resolved_jd_files: 2`。
- 日志记录最终生效模型 `resolved_model`，不再只记录 `run_config.json` 中可能为空的 `configured_model`。
- 扩展结构化日志事件，覆盖 token、耗时、解析状态、fallback、tool call、agent reasoning summary 和质量门槛检查。
- 增加 analyze 质量门槛，避免 JD profile 空字段、CV 抽取低质量、规则高分但证据弱的 run 静默产出普通 `done` 报告。
- Web 详情页展示 `done_with_warnings` 或等价质量警告状态，并展示 resolved model、token usage、tool call 次数、fallback 次数和质量摘要。
- 日志采用三层等级：`normal`、`debug`、`trace`；默认 `normal`，`trace` 仅用于本机私有调试且必须脱敏。

验收标准：

- CLI `--jd` 传目录且目录内有多个 JD 文件时，日志同时保留 CLI source 数量和 resolved file 数量。
- model 配置为空但运行时解析出默认模型时，日志能显示 `configured_model: ""` 与非空 `resolved_model`。
- LLM 调用日志记录 token usage；provider 未返回 token 时写 `null`，不伪造数值。
- fallback、tool call 和质量门槛检查均能在 `run_events.jsonl` 中定位到 stage、operation、原因和结果。
- JD 原文非空但 analyze 后 `title/responsibilities/requirements` 为空时，run 至少进入 warning 状态，不能静默展示为完全可信的普通完成。
- 日志不记录完整 chain-of-thought；只记录可审计 reasoning summary、decision inputs 和 tool execution summary。

### v0.5.7 打分算法优化

目标：将评估机制从“关键词规则分 + LLM final”升级为“岗位要求分级 + CV 证据追溯 + 生成前门禁 + 双分制/三分展示”。学历、专业、证书、工作许可、硬年限等可追溯硬门槛拥有最高优先级；硬门槛缺失或不匹配时按 JD 跳过后续生成和 LLM judge，节约成本并避免生成阶段编造硬事实。

关键变化：
- analyze 阶段新增岗位要求分级：`hard_gate` 覆盖学历、专业、证书、工作许可、明确硬年限、语言硬要求；`high_priority` 覆盖核心技术、框架、业务域；`medium_priority` 覆盖经历、项目、场景；`nice_to_have` 只作为加分项。
- 新增 CV 证据矩阵：`verified`、`inferred`、`missing`、`mismatch`、`simulatable`、`forbidden_to_fabricate`，并为每条要求记录 evidence refs 与 fabrication policy。
- 在 analyze 后、generate 前新增 per-JD preflight gate：`hard_gate mismatch` 进入 `blocked`，`hard_gate missing` 进入 `needs_review`，该 JD 跳过 generate/evaluate/LLM judge/plan，同批其他 JD 正常继续。
- 评分改为三类主分：`verified_fit_score` 只看 CV 可追溯证据；`rewrite_potential_score` 只反映可补强空间；`risk_score` 由硬门槛、证据缺口、模拟补强、背调风险共同决定。
- `final_overall_score` 默认公式为 `verified_fit_score * 0.65 + rewrite_potential_score * 0.20 + (1 - risk_score) * 0.15`；blocked/needs_review JD 使用 `final_decision_source = preflight-gate`，不计算普通 final。
- generate 阶段读取 preflight/evidence matrix，严禁编造学历、专业、证书、公司、工作年限、论文、奖项等硬事实；经历/项目类中优先级要求可生成“待核实模拟补强”，但必须标注，且不能计入真实匹配分。
- Web 详情页展示硬门槛状态、blocked/needs_review 原因、跳过的 JD、真实匹配分、改写潜力分和风险分，避免单一综合分误导。
- CV PDF 解析质量增强：PDF 先走 `pypdf` 文本抽取；文本为空、有效字符过少或乱码比例高时，用 PyMuPDF 渲染页面，再复用本地 OCR/vision fallback。PDF OCR/vision 结果继续落入 `ingest/manifest.json` 的既有字段，不新增 manifest schema。
- CV profile 结构化增强：deterministic analyze 不再只依赖 bullet 行，增加章节/段落解析，覆盖教育、工作经历、项目、技能、证书、语言等信息；OpenAI analyze prompt 要求完整保留可追溯硬事实，支撑 v0.5.7 hard gate 判断。

验收标准：
- 学历、专业、证书等要求能被识别为 `hard_gate`；经历、项目类要求能被识别为 `medium_priority`。
- CV 明确满足、缺失、明确不符分别生成 `verified/missing/mismatch`；medium priority 缺失时可标记为 `simulatable`。
- hard gate mismatch 时该 JD 进入 `blocked`，hard gate missing 时进入 `needs_review`，并跳过 generate/evaluate/LLM judge；多 JD run 中只跳过不合格 JD。
- 关键词命中很高但 hard gate 缺失时，不允许出现高普通 `final_overall_score`；模拟补强只提高 `rewrite_potential_score`，不提高 `verified_fit_score`。
- 生成产物区分 `safe_rewrites`、`simulated_supplements`、`forbidden_gaps`，且硬事实缺失时不生成伪造内容。
- PDF CV 包含学历、专业、证书等硬事实时，解析后的 candidate profile 应能让 requirement matrix 判定为 `verified`；缺失硬事实时仍进入 `needs_review`，不能由解析器默认补齐。
- 旧 run 缺少 v0.5.7 产物时，Web 和 pipeline 仍按历史 scorecard 兼容展示。

## Public Interfaces

计划新增或稳定以下接口与文件契约：

- `run_dir/config/run_config.json`：唯一执行配置快照，由草稿创建或 CLI ingest 初始化，后续阶段只读。
- `run_dir/ingest/upload_manifest.json`：Web 上传元数据清单，不包含解析正文。
- `run_dir/ingest/manifest.json`：Python ingest 生成的唯一业务输入清单，包含抽取后的可执行输入。
- `run_dir/run_status.json`：最小运行状态文件，承载 `draft/queued/running/done/failed` 状态。
- `run_dir/logs/*.jsonl`：阶段级结构化日志和最小审计记录。
- Web API：保留草稿创建接口，新增 run 触发、状态读取、重试/继续执行相关接口。
- CLI：继续以 `shotguncv run/ingest/analyze/generate/evaluate/plan/report --run-dir` 为执行入口。

v0.5.7 计划新增以下评分与门禁产物：

- `run_dir/analyze/requirement_matrix.json`：每个 JD 的 requirement tier、requirement text、evidence status、evidence refs、fabrication policy 和 risk weight。
- `run_dir/analyze/preflight_gates.json`：每个 JD 的 gate status：`pass | blocked | needs_review`，以及原因、跳过阶段和用户可操作建议。
- `run_dir/evaluate/scorecards.json`：在旧字段基础上新增 `verified_fit_score`、`rewrite_potential_score`、`risk_score`、`gate_status`、`gate_reasons`；blocked/needs_review JD 使用 `final_decision_source = preflight-gate`。
- `run_dir/generate/resume_variants.json`：在旧字段基础上新增 `safe_rewrites`、`simulated_supplements`、`forbidden_gaps`，用于区分可安全改写、待核实模拟补强和严禁编造的缺口。
- `pyproject.toml`：v0.5.7 CV PDF 解析增强新增 `PyMuPDF>=1.24`，用于低质量/扫描 PDF 的页面渲染；本地 OCR 和 vision fallback 沿用既有配置。

v0.5.6 计划扩展以下日志和状态契约：

- `run_dir/logs/run_events.jsonl` 新增事件：`input_resolved`、`input_extracted`、`model_resolved`、`llm_call_started`、`llm_call_finished`、`llm_call_failed`、`tool_call_started`、`tool_call_finished`、`tool_call_failed`、`agent_reasoning_summary`、`quality_gate_checked`、`fallback_used`。
- `input_resolved` 记录 `cli_cv_sources`、`cli_jd_sources`、`resolved_cv_files`、`resolved_jd_files`、`jd_text_blocks`。
- `input_extracted` 记录单文件抽取 provider、status、text chars、fallback 来源和 warning。
- `model_resolved` 记录 `provider`、`configured_model`、`resolved_model`、`base_url_host`，不得记录 API key。
- `llm_call_*` 记录 operation、provider、model、duration、prompt tokens、completion tokens、total tokens、parse status 和 error summary。
- `tool_call_*` 记录 tool 名称、输入类型、耗时、状态和输出摘要。
- `agent_reasoning_summary` 只记录可审计决策摘要，不记录完整 chain-of-thought。
- `quality_gate_checked` 记录 `jd_profile_completeness`、`cv_text_quality`、`score_consistency` 等质量门槛结果。
- `fallback_used` 记录 fallback 来源、目标 provider、原因和影响阶段。
- 日志等级为 `normal | debug | trace`：`normal` 记录阶段、耗时、状态、resolved model、token usage、fallback 和质量警告；`debug` 追加 prompt 摘要、输出结构摘要、字段完整性和 tool output 摘要；`trace` 允许本机调试记录完整 request/response，但必须脱敏 API key、路径隐私和候选人敏感信息。
- `run_dir/run_status.json` 计划扩展 `quality_status: ok | warning | failed` 与 `quality_summary`；`last_action` 保持现有语义。

## Test Plan

- Python 单元测试：覆盖 ingest 多输入合并、PDF/图片抽取状态、不可解析输入、阶段产物检测、失败摘要生成。
- Python 集成测试：使用 deterministic config 跑完整 `shotguncv run`，断言所有阶段产物、状态文件和日志存在。
- Web 单元测试：覆盖 draft API、run status 读取、输入来源展示、失败状态展示。
- Web 集成测试：模拟上传文件创建草稿，触发 CLI，轮询到 `done/failed`，再读取详情页和报告页。
- 回归测试：固定 fixtures 下重复运行应产生稳定排序、稳定阶段状态和稳定报告关键字段。
- v0.5.6 日志测试：CLI `--jd` 传目录且目录内有 2 个 JD 文件时，断言日志同时记录 `cli_jd_sources: 1` 和 `resolved_jd_files: 2`。
- v0.5.6 模型测试：配置 model 为空但运行时解析出默认模型时，断言日志记录 `configured_model: ""` 和非空 `resolved_model`。
- v0.5.6 token 测试：LLM 调用完成后记录 `prompt_tokens`、`completion_tokens`、`total_tokens`；provider 不返回 token 时记录 `null`。
- v0.5.6 fallback 测试：fallback 发生时写入 `fallback_used`，并能定位 stage、operation、reason。
- v0.5.6 质量门槛测试：JD 原文非空但 analyze 后 `responsibilities/requirements/title` 为空时写入 `quality_gate_checked`，CV 文本控制字符比例过高时写入 `cv_text_quality` warning，规则分高但 evidence/profile 质量低时写入 `score_consistency` warning。
- v0.5.6 Web 测试：run detail 显示 resolved model、token usage、tool call 次数、fallback 次数；`done` 且有质量 warning 时展示 `Done with warnings` 或等价提示；旧 run 缺少新增事件时仍兼容展示。

- v0.5.7 analyze 测试：学历/专业/证书要求识别为 `hard_gate`，经历/项目类要求识别为 `medium_priority`，CV 明确满足、缺失、明确不符分别生成 `verified/missing/mismatch`。
- v0.5.7 preflight gate 测试：hard gate mismatch 进入 `blocked`，hard gate missing 进入 `needs_review`，并按 JD 跳过 generate/evaluate/LLM judge；多 JD run 中只跳过不合格 JD。
- v0.5.7 scoring 测试：hard gate 缺失时不允许高普通 final；模拟补强只提高 `rewrite_potential_score`，不提高 `verified_fit_score`；hard gate 缺失、不匹配、模拟补强过多时 `risk_score` 上升。
- v0.5.7 generate safety 测试：学历、专业、证书、工作年限缺失时不生成伪造内容；medium priority 项目经历可生成待核实补强并明确标注。
- v0.5.7 Web 测试：blocked/needs_review JD 显示原因和跳过阶段，分数矩阵展示 verified/rewrite/risk 三分，旧 run 缺少 v0.5.7 产物时仍兼容展示。
- v0.5.7 PDF 解析测试：文本型 PDF 仍用 `pypdf`；低质量/扫描 PDF 渲染后走 OCR；OCR 空且 vision disabled 时记录 `unparseable`；vision enabled 时可回退到 vision。
- v0.5.7 CV profile 测试：无 bullet 的 PDF/文本简历段落能抽出 experiences、skills、education/certificate 证据，并能支撑 hard gate `verified` 判断。

## Assumptions

- v0.5 仍是本地单用户模式，不引入远程队列、多用户权限或数据库。
- Web 触发 Python CLI 允许使用本机环境中的 `shotguncv` 命令。
- `run_dir` 是跨 Web/CLI 的唯一状态边界。
- PDF/OCR/vision 的外部依赖缺失时，系统应给出可操作错误，而不是静默失败。
- 本轮只落地 `docs/plan.md`，不实施代码、测试或其他文档变更。
- v0.5.6 是 v0.5 收盘优化版本，只增强可观测性、质量门槛和文档边界，不新增远程队列、多用户、自动投递或 CRM 能力。
- 默认日志等级为 `normal`；`debug` 和 `trace` 只影响日志详细度，不改变 pipeline 业务产物。
- `trace` 仅用于本机私有调试，并要求脱敏。
- v0.5.7 仍保持本地单用户、`run_dir` 唯一状态边界；不实现用户交互式补材料流程，只提示需要补充哪些硬门槛证据。
- 硬门槛缺失默认不继续消耗生成和 LLM judge 成本，状态为 `needs_review`；硬门槛明确不符默认 `blocked`。
- 中优先级经历/项目可生成待核实模拟补强，但必须标注，且不计入真实匹配分。
