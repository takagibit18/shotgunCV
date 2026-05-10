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

### v0.7 全页面 status-chip 清理与视觉规范统一

目标：审计并清理全页面中滥用 `status-chip` 的静态装饰标签，建立"status-chip 仅用于动态状态展示"的使用规范；将确认面板重排为 2 列简洁布局。

#### v0.7.0 — 确认面板重排 + 上传页 chip 清理

关键变化：
- 确认面板由 3 列 `.metadata-table.compact-table` 改为 2 列 `.confirmation-summary` 行布局（字段名 | 状态值 · 说明），字体统一 13px。
- 删除 `upload/page.tsx` 中 "仅创建草稿"、"本地单用户" 两个静态状态 chip。
- 删除 `UploadForm.tsx` 中 "自动生成 Candidate ID"、"元数据写入" 两个静态状态 chip。
- 删除 `report/page.tsx` 中 "Markdown 原文"、"保留原文 Markdown" 两个静态状态 chip。

验收标准：
- 上传页和报告页无静态装饰 chip。
- 确认面板字体与 upload-file-list 统一（13px），2 列排版清晰。
- `npm test` 与 `tsc --noEmit` 通过。

#### v0.7.1 — 首页和运行队列 chip 清理

关键变化：
- 删除 `page.tsx` 右侧 "近期活动" 栏中 "查看全部" 静态 chip。
- 删除 `RunQueue.tsx` 标题行中 "本机运行管理" 静态 chip。

验收标准：
- 首页和运行队列页面无静态装饰 chip。
- 删除后各区域标题排版自然，无空白异常。

#### v0.7.2 — 设置页和评估页 chip 清理

关键变化：
- 删除 `settings/page.tsx` 中 "X 项检查" 计数器 chip。
- 删除 `EvaluationQueue.tsx` 中 "X/Y 条结果" 计数器 chip。

验收标准：
- 设置页和评估页无静态装饰 chip。
- 计数器信息如有需要以其他方式展示（如普通文本）。

#### v0.7.3 — Run Detail 页 chip 规范化

关键变化：
- `runs/[runId]/page.tsx` line 271: `source.role` chip 改为普通 `<span>` 文本。
- `runs/[runId]/page.tsx` line 329 和 579: gate status chip 增加颜色编码（复用 `buildGateClassName` 模式）。
- `SectionHeading` 组件：清理静态 `action` prop 调用，只保留动态状态值传参。

验收标准：
- run detail 页所有 status-chip 均为动态状态 + 带颜色编码。
- `SectionHeading` 不再渲染静态字符串 chip。

#### v0.7.4 — EvaluationQueue applyDecision 颜色编码

关键变化：
- `EvaluationQueue.tsx` line 202: applyDecision chip 新增颜色映射（强烈推荐→success, 可投递→info, 不建议→warning）。

验收标准：
- 评估列表决策列有颜色区分，正向/中性/负向决策视觉明确。

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

### v0.7.5 移除 Web 端运行时间线展示

目标：删除 run detail 页的运行时间线 section，Web 端不需要逐条展示 pipeline 内部日志。

关键变化：
- 删除 `runs/[runId]/page.tsx` 中整段 timeline section（SectionHeading + timeline-list + timeline-row 渲染）。
- 移除 `globals.css` 中 `.timeline-list`、`.timeline-row` 样式定义及响应式覆盖。
- 保留 `readTimeline()` 和 `buildObservabilitySummary()` 数据层函数，Observability 区域继续提供聚合摘要（token、fallback、quality warnings）。

验收标准：
- run detail 页面不再出现时间线区块。
- Observability 区域正常展示模型与 token、工具与质量摘要。
- `npm test` 与 `tsc --noEmit` 通过。

### v0.7.6 清理评估结果页冗余 chips

目标：精简 EvaluationQueue 行内与分数列信息重复的 applyDecision chip。

关键变化：
- 删除 `EvaluationQueue.tsx` 中 applyDecision chip 渲染及 `buildDecisionClassName` 函数。
- 保留 gateStatus chip（每个 JD 独立 gate 状态）和 artifactMode pill（数据版本标识）。

验收标准：
- 评估队列行内仅保留 gateStatus chip + artifactMode pill + 分数列。
- `npm test` 与 `tsc --noEmit` 通过。

### v0.7.7 全局页面骨架压缩与信息层级重排

目标：参考上传截图中的冷白工作台风格，把所有 Web 页面统一成“面包屑/标题/关键状态/主工作区”的紧凑骨架，删除解释性过强、重复出现的页面说明。

关键变化：
- 审计 `AppShell.tsx`、`page.tsx`、`evaluations/page.tsx`、`resume/page.tsx`、`settings/page.tsx` 与 `runs/[runId]/page.tsx` 的首屏结构，保留必要上下文，删除重复的营销式副标题和长说明。
- 统一页面标题区：面包屑或 eyebrow 只表达当前位置，`h1` 只表达当前任务，不再重复“本地 artifacts / 不重新判断业务结论 / 工作台”等已在系统边界中说明过的内容。
- 将“数据更新”保留为全局 freshness-pill；各页面内部不再重复展示更新时间，除非该时间直接用于列表排序或行级追溯。
- 左侧导航维持当前信息架构，但减少侧栏底部 AI 洞察卡片的视觉重量，避免与主页面 AI 建议、风险解释产生重复。
- 统一首屏间距：页面标题区、指标区、主卡片之间使用固定 spacing token，避免不同页面出现大段空白或卡片漂浮感。

验收标准：
- 首页、简历优化、运行队列/仪表盘、评估结果、运行详情、设置页首屏标题层级一致。
- 每个页面首屏只保留一个主要任务说明，不出现两段以上功能解释文案。
- 侧栏、标题区、freshness-pill 在 1440px、1180px、980px、720px 下不重叠。
- `npm test` 与 `tsc --noEmit` 通过；截图 QA 覆盖桌面与移动端首屏。

### v0.7.8 仪表盘与运行队列版式精简

目标：参考“运行队列与投递决策”截图，重排首页 `page.tsx` 与 `RunQueue.tsx`，让运行状态、近期活动和 AI 洞察更像工作队列，而不是多个同权重信息块。

关键变化：
- 首页顶部指标卡保留 4 个以内：运行批次、进行中、警告/失败、已完成阶段；删除与表格内容重复的次级解释。
- 趋势概览收敛为一条横向 summary strip：只展示 Run 数、完成率、警告/失败，不在首页首屏放置复杂趋势图或重复指标卡。
- 右栏“近期活动”只保留最近 4 条可行动记录，删除过长 run id 的完整展示，改为截断 + title tooltip 或详情入口。
- 右栏“AI 洞察”只展示一个当前最重要的建议：优先处理维度、原因、查看详情入口；删除泛化的说明文字。
- `RunQueue.tsx` 表格列顺序调整为：Run、状态、阶段进度、Provider、风险与动作、操作；把操作按钮靠近风险与下一步，减少视线横跳。
- 筛选栏压缩为一行：搜索、状态、阶段、Provider、排序、重置；低频筛选只在后续有真实需求时再新增。
- 长 run id、provider 列和阶段标签使用固定宽度与换行策略，避免行高被单个长字符串撑开。

验收标准：
- 首页首屏能同时看到关键指标、运行队列前两行、近期活动或 AI 洞察的至少一个卡片。
- 运行队列表格每行高度稳定，长 run id 不导致列错位或横向溢出。
- 空队列、无近期活动、无风险建议时使用紧凑空态，不占据大面积首屏。
- `npm test` 与 `tsc --noEmit` 通过；截图 QA 覆盖 100+ run 的分页场景。

### v0.7.9 评估结果列表密度与筛选区重构

目标：参考“独立评估结果列表”截图，优化 `evaluations/page.tsx` 与 `EvaluationQueue.tsx` 的信息密度，让 JD 评估结果更适合批量筛选、排序和复核。

关键变化：
- 顶部统计卡压缩为 4 个以内：评估结果、需处理 gate、高风险岗位、历史产物；右侧“可信评估边界”改为轻量提示，不再与统计卡同等视觉重量。
- 趋势区从大卡片改为紧凑 summary strip，避免与统计卡重复展示 JD 数、平均分、风险分。
- 筛选区标题改为普通小标题，不再占用独立大卡片；筛选控件按搜索、Gate、风险、分数、Provider、建议、排序排列。
- 评估表格首列聚焦 JD/Run 标识，第二列保留 gate 与建议，第三列展示分数矩阵，第四列展示证据与风险，第五列展示操作。
- 删除行内重复来源说明，例如每行都出现的 `scorecard / gate / evidence / strategy`；改为表头或页面底部一次性说明。
- 风险提示条只在当前页存在高风险或 hard gate 缺失时出现，位置放在表头与列表之间，不插入到单条行中打断扫描。
- 移动端将每条评估结果降级为紧凑卡片：标题、gate、三分、风险、详情/报告操作，隐藏次级 provider/model 文本到展开区。

验收标准：
- 一屏至少展示 3 条评估结果行，且分数、gate、风险、操作都可扫描。
- 筛选组合后没有匹配结果时，空态说明当前筛选条件并提供重置入口。
- legacy artifact 行保留 artifactMode pill，但不额外增加整段解释文字。
- `npm test` 与 `tsc --noEmit` 通过；截图 QA 覆盖长 JD 标题、长风险说明、legacy artifact。

### v0.7.10 运行详情评估矩阵首屏重排

目标：参考“岗位优先级矩阵”截图，重排 `runs/[runId]/page.tsx` 的评估阶段区域，把分数、风险、证据、建议放到同一个决策面板内，删除分散重复的解释卡片。

关键变化：
- 评估阶段首屏采用“候选 JD 概览 + 决策分 + 状态按钮 + 维度矩阵”的单一主面板，避免 score ring、状态 chip、风险说明分散在多个同级卡片里。
- 保留综合得分、真实匹配、岗位匹配、拉伸可控、改写潜力、关键词、风险压力、证据覆盖、改写成本等维度，但统一为 3 列指标矩阵，减少重复标题和多余边框。
- 将“证据引用”“风险压力”“缺口数”合并为一条横向状态带，替代多个独立小卡片。
- “主要风险”提示条只展示最高优先级风险、当前建议、下一步动作；完整风险解释移动到下方展开区。
- “适配度分析”“风险解释”“投递建议”三张卡片压缩为三栏 action panel，每栏最多 3 行摘要 + 一个主要入口；删除重复的来源/解释性长文。
- 证据引用展开与风险解释展开保持可追溯，但默认只显示前 3 条；更多内容通过展开操作查看。
- 右侧 AI 洞察栏只在评估策略存在时展示，且不重复主面板已经展示的建议。

验收标准：
- 运行详情评估阶段首屏能同时看到 JD 标题、最终决策分、gate/risk 状态、核心分数矩阵和下一步动作。
- 证据、风险、建议各自保留来源与展开入口，不因精简而丢失可追溯性。
- 多 JD 情况下，每个 JD 面板之间视觉间距一致，当前选中或重点 JD 清晰。
- `npm test` 与 `tsc --noEmit` 通过；截图 QA 覆盖 blocked、needs_review、passed、legacy 四类状态。

### v0.7.11 简历优化工作台卡片结构收敛

目标：参考“简历优化工作台”截图，优化 `resume/page.tsx` 的 run artifact 卡片，让每个简历版本的摘要、改写边界、证据约束和投递前检查更紧凑。

关键变化：
- 顶部指标卡保留 Run 批次、简历版本、Warning/Failed、证据约束四项，删除与列表重复的解释文本。
- 搜索与筛选栏压缩到一行：版本名搜索、状态、来源、Provider、排序、视图密度；不增加无实现的高级筛选。
- 每个简历版本卡片改为固定结构：标题区、版本摘要、改写边界、证据约束、投递前检查、操作区。
- 卡片内四个信息块使用统一标题、图标和行高；空数据统一显示“当前 artifact 未提供该类条目”，不再为每个缺失字段写不同解释。
- “详情”“报告”按钮保持在卡片右上角，移动端移动到卡片底部操作区。
- 对 legacy run 使用轻量标签标识，不在每张卡片重复说明 legacy 降级规则。
- 图片或长文件名在版本摘要中只作为来源摘要展示，不展开完整路径。

验收标准：
- 每张简历版本卡片高度可预测，缺失 artifact 不造成大面积空白。
- 完成、进行中、失败、legacy run 均有稳定卡片结构。
- 卡片内无嵌套卡片视觉，四个信息块边界清晰但不显得拥挤。
- `npm test` 与 `tsc --noEmit` 通过；截图 QA 覆盖至少 2 个连续版本卡片。

### v0.7.12 Web 视觉规范与冗余样式清理

目标：在 v0.7.7 到 v0.7.11 的页面重排后，清理 `globals.css` 中重复、过度装饰或已失效的样式规则，形成可继续演进的轻量视觉规范。

关键变化：
- 审计 `globals.css` 中卡片、status、table、rail、summary、filter、pagination 相关 class，删除已经没有渲染调用的样式。
- 建立小范围视觉 token 约定：页面间距、卡片边框、表格行高、chip 颜色、risk/success/warning/info 语义色、focus-visible。
- 统一所有表格和列表的空态、错误态、partial artifact 态、无匹配筛选态样式。
- 删除过度渐变、重复阴影、重复边框和大面积淡色背景；保留冷白、细边框、小圆角、紧凑控件的工作台基调。
- 为 icon button、更多菜单、保存视图、分页按钮补齐 hover、focus-visible、disabled 样式规范。
- 更新 `docs/qa-v0.6.1-visual-baseline.md` 或新增视觉 QA 小节，记录 v0.7.x 页面截图检查点。

验收标准：
- `rg "className=.*旧样式名"` 不再能找到已删除样式的使用；`globals.css` 中无明显孤立的 timeline、静态 chip 或废弃 SaaS 占位样式。
- 全页面语义色不依赖颜色单独传达状态，关键状态同时有文字标签。
- 桌面、平板、移动端无重叠、不可读按钮或不可控横向滚动。
- `npm test` 与 `tsc --noEmit` 通过；完成一轮手动截图 QA 记录。
