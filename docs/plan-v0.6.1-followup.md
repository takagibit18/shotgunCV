# ShotgunCV v0.6.1+ 后续优化规划

## Summary

v0.6.0 已经完成 Web 体验的主要重构：统一 `AppShell`、冷白 SaaS 工作台视觉系统、首页运行队列、运行详情页、上传页与报告页。v0.6.1 起的目标是把这套工作台从“主流程可展示”推进到“关键业务页面完整、截图级稳定、可持续扩展”。

后续优化继续限定在本地单用户 Web 工作台范围内。Python pipeline 仍是唯一业务真源，Web 优先读取既有 `run_dir` artifacts，不引入数据库、远程队列、多用户权限、CRM 或自动投递。

## Version Roadmap

### v0.6.1 稳定化与视觉 QA 基线

目标：先补齐 v0.6.0 未完成的浏览器级验证与截图级细节，建立后续页面扩展的质量基线。

关键变化：
- 跑通本地 `dev server` 与 Browser IAB 或等价浏览器验证流程，形成桌面和移动端截图 QA 清单。
- 修复 AppShell 导航可达性，避免“评估结果、设置”等入口长期只显示 disabled 状态而没有规划说明。
- 检查首页、运行详情、上传页和报告页的移动端溢出、表格密度、长文本截断、按钮尺寸和焦点状态。
- 补齐截图级 UI 细节：空态、加载态、筛选控件紧凑度、状态 chip 对齐、表格列宽与小圆角一致性。

验收标准：
- `npm test` 与 `tsc --noEmit` 通过。
- 至少覆盖首页、运行详情、上传页、报告页的桌面与移动端截图 QA。
- 页面中英文混排不出现明显截断、重叠或横向不可控溢出。

### v0.6.2 评估结果独立列表页

目标：新增 `/evaluations`，把分散在 run detail 中的 JD 评估结果聚合为可筛选、可排序、可回溯的独立工作队列。

关键变化：
- 从所有 run 中读取 `scorecards.json`、`ranking_explanations.json`、`preflight_gates.json`、`requirement_matrix.json` 与 `application_strategies.json`。
- 以“岗位/JD”为行粒度展示 run、JD 标题、gate 状态、真实匹配分、改写潜力分、风险分、投递建议和证据摘要。
- 支持按状态、gate、风险、provider、分数区间、关键词筛选，并支持按更新时间、最终分、风险分、优先级排序。
- 每一行提供跳转到 run detail 对应评估区域和报告页的入口。
- 兼容 legacy run：缺少 v0.5.7 三分制或 gate artifact 时降级展示历史 `overall_score` 与 scorecard 字段。

验收标准：
- 空 runs、只有草稿、legacy artifact、完整 v0.5.7 artifact 均有稳定展示。
- 筛选和排序行为有单元测试覆盖。
- 长 JD 标题、长风险说明、空证据引用均不破坏布局。

### v0.6.3 设置真实页面与模板页清理

目标：新增 `/settings`，把本地运行边界、路径、provider 配置和环境检查集中展示，降低用户理解和排障成本；同时移除模板 Settings 页和模板导航残留，让 v0.6.3 的设置入口成为真实可用页面。

关键变化：
- 删除默认模板库 Settings 页面内容，避免用户进入无业务含义的占位页。
- 更新 AppShell 导航，使设置入口指向真实 `/settings` 页面，并保持与现有本地单用户工作台视觉体系一致。
- 展示当前 runs 根目录、Web 读取路径、Python CLI 调用边界和本地单用户模式说明。
- 展示 provider 配置摘要：analyzer、generator、judge、planner、OpenAI-compatible base URL host、OCR/vision 配置。
- 提供环境检查区：runs 目录是否可读、关键 artifacts 是否可解析、`shotguncv` CLI 是否可用、OCR/vision 依赖是否配置。
- 设置页不保存 API key，不在页面输出完整密钥、完整 CV/JD 原文或敏感路径。
- 设置页只读取本地元数据和 run artifacts，不执行 pipeline，不修改 `.env`，不写入 provider 配置。
- 若未来需要可编辑设置，必须作为单独小版本明确持久化文件、权限边界和脱敏策略。

验收标准：
- `/settings` 不再显示 Next.js 或模板库占位内容，导航中设置入口可达。
- 缺少 runs 目录、空目录、配置不完整、provider unknown 时均显示可操作解释。
- 环境检查失败不导致页面崩溃。
- 敏感配置只展示摘要，不泄露 API key。

### v0.6.3.x Web 端本地配置闭环

目标：在 v0.6.3 只读设置页稳定后，新增 Web 端本地模型配置闭环，让用户可以在浏览器里完成 API key、OpenAI-compatible endpoint 和模型配置的本地保存、校验与回退；该能力仍限定在开源、本地单用户、不部署的项目边界内。

关键变化：
- 将入口放在 `/settings` 的独立配置区或子页面中，命名为“本地模型配置”，避免使用“上传 API key”这类容易暗示远端传输的文案。
- 以项目根目录 `.env` 作为首选持久化目标，继续由 `.gitignore` 排除；Web 不把密钥写入 `run_config.json`、run artifacts、日志或浏览器 localStorage。
- 支持配置 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`、`SHOTGUNCV_GENERATOR_MODEL`、`SHOTGUNCV_JUDGE_MODEL`、`SHOTGUNCV_VISION_MODEL`，并保留 `OPENAI_API_KEY_ENV` 的高级用法。
- 保存前展示将要写入的字段摘要，API key 输入框默认掩码，仅显示已配置/未配置和末尾少量字符；不回显完整密钥。
- 提供连接检查或最小模型探测动作，但检查结果只写入 UI 状态，不落盘保存完整响应、prompt、CV/JD 原文或密钥。
- 提供清空、覆盖、恢复到 `.env.example` 默认结构的操作，并说明这些操作只影响本地项目配置。

验收标准：
- 首次打开时能识别 `.env` 不存在、缺少 key、base URL 非法、模型为空等状态，并给出可操作提示。
- 保存后 CLI pipeline 能继续通过现有 `.env` 读取逻辑获得配置，Web 不引入第二套 provider 真源。
- API key 不进入客户端持久存储、run artifacts、测试快照或日志摘要。
- 配置写入失败、权限不足、`.env` 格式异常时，页面不崩溃，并提供明确恢复路径。

### v0.6.4 简历优化完整业务页

目标：新增 `/resume`，把当前“上传/草稿流程”扩展为完整的简历优化工作台；`/upload` 继续保留为创建草稿入口。

关键变化：
- 页面聚合候选人材料、草稿 run、生成版本、证据约束、改写建议、投递前检查和下一步动作。
- 展示 `resume_variants.json` 中的版本摘要、目标 JD、可安全改写项、待核实模拟补强项和禁止编造缺口。
- 将 `requirement_matrix.json` 与 `preflight_gates.json` 作为证据约束来源，明确哪些内容可改写、哪些内容必须补证据、哪些内容不能写。
- 支持从草稿 run 进入运行详情，从完成 run 进入报告或评估矩阵。
- 不在 Web 端重新实现 pipeline 生成逻辑；Web 只读取 artifacts 并组织工作流。

验收标准：
- 草稿、运行中、失败、完成、有 warning、legacy run 都能进入稳定状态。
- 证据约束、改写建议和投递前检查都有清晰来源标签。
- 页面测试覆盖空态、legacy artifact、v0.5.7 artifact 和长文本场景。

### v0.6.5 数据密度与趋势细节

目标：补齐趋势线、分页控件和数据密度细节，让工作台能承载更多 run 和更多 JD。

关键变化：
- 首页和评估列表增加轻量趋势线，展示 run 数、完成率、warning/failed 数量、平均分或风险分变化。
- 为运行队列和评估列表增加分页或虚拟化前的最小分页控件。
- 补齐表格列显示策略：固定主列、长文本截断、hover/展开详情、移动端卡片化降级。
- 统一所有列表的空态、加载态、错误态、无匹配筛选态和 legacy 降级提示。
- 将浏览器截图 QA 纳入每个新增页面的验收标准。

验收标准：
- 100+ run 或多 JD run 场景下页面仍可扫描。
- 分页、筛选、排序组合行为稳定。
- 桌面与移动端截图中无明显重叠、错位或不可读文本。

### v0.6.6 上传页交互优化与 SaaS 痕迹清理

目标：打磨上传草稿页的 UX 细节（CV-JD 视觉一致性、截图缩略图预览、按钮可读性与对齐），删除 AppShell 和 RunQueue 中未实装的 SaaS 占位元素，使界面语言对齐项目"开源工具、用户自带 API key、全本地化"的定位。

关键变化：
- CV 上传区改为与 JD 一致的 dropzone + `.upload-file-list` 结构：隐藏原生 `<input>`，使用 styled label 作为触发器，增加拖拽支持（`onDragOver`/`onDrop`），移除冗余的 4 列 `.metadata-table`。
- JD 文件列表中为图片文件（PNG/JPG）生成客户端缩略图预览（`URL.createObjectURL`），点击缩略图弹出 lightbox 查看原图；非图片文件保持纯文本文件名展示。
- 确保"选择本地 JD 文件"按钮文字在 `.primary-link` 蓝紫渐变背景上对比度足够（`color: #fff`），与"创建草稿 run"按钮视觉对齐。
- 删除 `AppShell.tsx` 命令栏中未实装的铃铛和书本图标按钮（仅删除渲染调用，保留 Icon 组件定义）。
- 删除 `RunQueue.tsx` 中无功能的"更多筛选条件" filter-button。
- 删除后验证命令栏右区仅保留 freshness-pill + avatar compact，排版在各断点下自然美观。

验收标准：
- CV 和 JD 上传区使用一致的 dropzone + file-list 视觉结构，均支持拖拽。
- 图片文件（PNG/JPG）在 JD 文件列表中显示缩略图，点击可查看大图；非图片文件展示文件名。
- "选择本地 JD 文件"按钮文字清晰可读，与"创建草稿 run"按钮视觉协调。
- AppShell 命令栏不再出现铃铛和书本占位图标，RunQueue 筛选栏不再出现无功能筛选按钮。
- 删除 SaaS 占位后，命令栏和筛选栏在各断点（1180px / 980px / 720px）下排版正常，无错位或空白异常。
- `npm test` 与 `tsc --noEmit` 通过。

## Public Interfaces

后续版本默认新增或稳定以下 Web 路由：

- `/evaluations`：独立评估结果列表页。
- `/settings`：本地配置与环境检查页面。
- `/resume`：简历优化完整业务工作台。
- `/upload`：继续保留为草稿创建入口。

后续页面优先读取既有 run artifacts：

- `run_status.json`
- `logs/run_events.jsonl`
- `ingest/manifest.json`
- `analyze/requirement_matrix.json`
- `analyze/preflight_gates.json`
- `evaluate/scorecards.json`
- `evaluate/ranking_explanations.json`
- `plan/application_strategies.json`
- `generate/resume_variants.json`
- `report/summary.md`

## Test Plan

- 文档变更验收：确认本文档存在，标题、版本拆分、边界、路由、artifact 来源和验收标准完整；`docs/README.md` 能链接到本文档。
- 每个后续版本实现时都需要运行 `npm test` 与 `tsc --noEmit`。
- 新页面测试应覆盖导航可达、空态、legacy artifact 兼容、筛选排序、长文本不溢出、中文/英文混排可读。
- 浏览器截图级 QA 至少覆盖桌面和移动端，重点检查 AppShell、表格、右栏、详情展开、状态 chip、分页和趋势线。

## Assumptions

- v0.6.1 优先补 QA 与稳定性，不急于新增业务页面。
- Web 继续作为本地单用户工作台，pipeline artifacts 仍是唯一业务来源。
- 后续页面可以增加 UI-only 状态，但不能引入第二套业务判断、自动投递、远程队列、CRM 或多用户权限。
- API key、完整 CV/JD 原文和敏感路径不应出现在设置页或日志摘要中。
