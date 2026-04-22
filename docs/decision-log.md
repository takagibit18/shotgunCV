# ShotgunCV 决策日志

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
