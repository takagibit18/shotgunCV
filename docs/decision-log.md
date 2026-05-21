# ShotgunCV 决策日志

## v0.4.0 Web 上传只创建本地 run 草稿

Web 允许写入本地 `runs/`，但写入边界限制为创建上传草稿：保存原始 CV/JD 文件、写入 `ingest/upload_manifest.json` 和 `config/run_config.json`。Web 不执行 pipeline、不解析正文、不生成 `ingest/manifest.json`。

原因：这样可以让用户从 Web 开始录入数据，同时继续保持 Python pipeline 是唯一业务真源。后续的文本提取、OCR、vision fallback、评分、排序和报告仍通过 CLI 显式执行，避免 Web 与 CLI 产生两套输入解释逻辑。

## 已生效决策

### 采用 Pipeline-first，而非 Agent-first

核心价值是批量比较和排序决策，不是聊天交互体验。流水线结构天然支持可复现产物和阶段化验证。

### 采用 Python 核心，保留 TypeScript 扩展位

Python 更适合批处理、规则评估与模型编排。当前继续以 Python pipeline 作为唯一业务真源，并新增 `apps/web` 只读查看层与 `packages/ts-shared` 共享契约。

### 采用混合生成策略

先按岗位簇生成共享版本，再对高潜力 JD 做定制化版本，以控制海投场景下的生成成本与收益。

### v1 即内建评估系统

规则评估与结构化判分同时存在，任何排序都必须可追溯到评分卡（`ScoreCard`）字段。

### v1 采用 CLI-first

CLI 是最低摩擦交付路径，优先确保批处理链路、结构化产物和回归验证闭环。

### 引入 run 级配置快照

provider 选择与模型参数在 `ingest` 阶段快照到 `run_dir/config/run_config.json`，后续阶段统一读取，避免运行过程中的隐式环境漂移。

### OpenAI 仅补生成与 judge 文本

OpenAI 首期只接入 `generate` 与 `evaluate` 中的文本生成部分；规则评分和排序公式继续保留为主导逻辑，保证可解释性与回放稳定性。

### Web 采用只读 Viewer，而非第二套执行入口

本阶段 Web 的目标是查看本地产物，而不是发起或编排 pipeline。这样可以保持单一真源，降低跨入口状态不一致风险。

### 语言与提交规范生效

- Markdown 文档统一中文。
- 代码注释统一英文。
- Git 提交信息统一英文。
## v0.5.3 Web 运行管理入口

Web 从只读查看器扩展为本机运行管理入口，但执行边界仍保持 Pipeline-first：Web 只能通过 `shotguncv` CLI 触发 run、retry 和 resume，不能调用 Python 内部业务函数。运行状态落在 `run_dir/run_status.json`，阶段完成度仍以阶段产物文件判断。

原因：v0.5.3 需要让草稿、失败和续跑在 Web 内可操作，但不能引入第二套 pipeline 编排逻辑。把状态写回 `run_dir` 可以让 CLI、Web 和本地调试共享同一个可回放边界，同时避免数据库、队列和多用户权限的复杂度。

## v0.5.4-v0.5.5 结构化日志与回归基线

运行观测采用 run-local JSONL，而不是集中式监控。`logs/run_events.jsonl` 足够还原本地单用户 run 的阶段顺序、耗时和失败原因，同时不会把 CV/JD 原文写入日志。

原因：当前阶段最重要的是可诊断和可回放，不是运维平台化。结构化日志加 targeted 回归测试可以稳定 v0.5 能力边界，并继续保持 Web 只作为本机触发与观察层。

## v0.6.4-v0.6.5 Web artifact 工作台与数据密度

`/resume` 被定义为简历优化工作台，但它只编排和展示既有 run artifacts：简历版本、证据约束、preflight gate、策略建议和状态摘要。它不成为第二套生成器，不写入 `resume_variants.json`，也不把完整 CV/JD 原文展示到页面中。

首页运行队列和评估列表的数据密度增强限定为 Web 展示层：轻量趋势摘要、客户端分页、长文本可读性和移动端降级。原因是 v0.6.5 的目标是让本地工作台可承载更多 run/JD，而不是改变评分、排序或 pipeline 合约。

## Indeed MCP 岗位导入暂缓到基础 RAG/Agent 能力之后

Indeed MCP 岗位导入与预期产品方向一致：它可以作为 JD 信息输入阶段的外部岗位来源，把搜索到的 Indeed Job Detail 标准化为当前 run draft 已支持的文本 JD，再交给 Python pipeline 处理。

该能力暂不进入当前优先级。原因是当前项目更需要先稳定 RAG、数据库投影、LangGraph 复盘 Agent、检索观测事件和质量基线；同时 Indeed 官方 MCP 仍标注 beta，且当前文档约束为 only available for Claude Connector。后续若要实现，应先做只读技术 spike 验证直接 MCP client 是否可达；若不可达，再评估 Claude MCP connector bridge 或 Indeed 官方 API/Partner 路线。

边界：不做自动投递、不做招聘网站抓取、不做浏览器自动化登录；Indeed 只作为可选 JD 导入源，不能改变 `run_dir` 与 Python pipeline 的业务真源地位。
