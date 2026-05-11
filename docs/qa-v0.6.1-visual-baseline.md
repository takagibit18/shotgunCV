# ShotgunCV 视觉 QA 基线

## 目标

v0.7.12 视觉规范清理后的 QA 基线，验证全页面样式一致性。检查对象包括 AppShell、首页、运行队列、运行详情、上传页、报告页、评估结果页、设置页、简历优化工作台。

本基线只验证本地 Web 工作台展示，不改变 Python pipeline、`run_dir` artifact 合约或本地单用户边界。

## 浏览器验证流程

1. 在 `apps/web` 启动本地开发服务器：`npm run dev`。
2. 打开桌面视口，建议尺寸 `1440x1000`。
3. 打开移动视口，建议尺寸 `390x844`。
4. 依次访问：
   - `/`
   - `/evaluations`
   - `/settings`
   - `/upload`
   - `/runs/<runId>`
   - `/runs/<runId>/report`
5. 若当前 runs 目录没有完整 run，至少验证空态、草稿态和 legacy artifact 降级态。

## 截图检查项

- AppShell：左侧导航不溢出，当前页面高亮明确；`评估结果` 可点击进入 `/evaluations`；`设置` 可点击进入 `/settings`。
- 设置页：runs 目录、provider 摘要、OCR/vision 配置和环境检查项可扫描，不显示完整密钥、完整 CV/JD 原文或敏感路径。
- 首页：指标卡、筛选区、运行队列表格、近期活动和 AI 洞察右栏在桌面可扫描，移动端按任务优先级堆叠。
- 评估结果页：筛选控件、JD 行、gate、真实匹配、改写潜力、风险分、证据/风险摘要和详情/报告链接不重叠。
- 运行详情页：首屏状态条、preflight gate、评分矩阵、证据展开、风险展开和运行观测区保持可读。
- 上传页：三步草稿流程、文件元数据、粘贴 JD、确认区和命令块在移动端不横向失控。
- 报告页：结构化摘要、来源标签和 Markdown 正文间距稳定，长文本可换行。

## 验收规则

- 桌面和移动端都不能出现 incoherent overlap、不可读按钮文字、失控横向滚动或正文遮挡。
- 评估、风险、建议和证据必须同时可见或可直接展开，不能只显示单一综合分。
- legacy artifact 缺少 v0.5.7 gate 或三分制字段时，页面必须标注历史产物并降级展示历史 scorecard。
- 空态必须说明下一步有效动作，而不是只显示空白页面。
- 所有状态颜色都要配合文字标签，不能只靠颜色表达。

## v0.7.12 视觉规范清理验证

- 确认 `globals.css` 中已移除所有未使用样式类（timeline-list、filter-button、decision-badge、legacy-tag、signal-grid、stage-*、matrix-header、matrix-action-panel/detail、sr-only、dimension-caption 等）。
- 全站按钮（primary-link、secondary-link、secondary-button、backlink、inline-action）均有 hover、focus-visible、disabled 状态。
- 语义色（success/warning/danger/info）统一使用 CSS 自定义属性，无硬编码色值。
- 空态（.empty-state）和占位态（.empty）样式统一，各页面空态表现一致。
- 桌面 (1440px)、平板 (1180px/980px)、移动端 (720px) 无重叠、不可读按钮或不可控横向滚动。
- `npm test` 与 `tsc --noEmit` 通过。
