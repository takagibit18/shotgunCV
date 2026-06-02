# 欣禹行

Agent 开发工程师｜北京朝阳｜离职

- 邮箱：huali6641@gmail.com
- 电话：15061235115
- 个人网站：seanhomepage.top
- GitHub：takagibit18
- 外语：雅思 7.0，CET6
- 自媒体：Sean 的构建日志，技术内容累计播放 400w+

## 教育经历

### 中央民族大学（985）｜计算机科学与技术｜本科

2023/09 - 2027/06，GPA 3.6

## 技术能力

- Python 工程化：使用 Python 异步编程、类型约束与结构化脚本组织实现 CLI 工具、测试用例与实验脚本；熟悉 Pydantic 结构化数据建模。
- Agent / LLM 应用：围绕大模型推理、结构化输出、Tool Calling 与 LangGraph 构建多阶段 Agent 应用；熟悉 ReAct 编排、工具安全分级、上下文预算管理、Agent / eval harness 设计。
- AI-native 开发工作流：长期深度使用 Claude Code、Codex 等 AI-native 开发工具重构个人研发工作流，能将模型能力沉淀为可复用的代码生成、评测、调试与文档化流程。
- RAG / 检索评测：使用 BM25、稠密向量检索（BGE-M3）、混合检索、pgvector、PostgreSQL 构建 RAG 检索链路；建立黄金集与分层评估闭环，跟踪 MRR、NDCG、Recall、Precision、Faithfulness 等指标。
- 质量门与评测闭环：实现 no-answer abstention gate、Evidence Gate A/B 测试框架、retriever / generator 分层评估和可复盘指标记录。
- 服务化与工程化：使用 FastAPI、Docker Compose、GitHub Actions、Redis 实现服务化接口、CI/CD 集成与会话缓存；通过 JSONL event log 与 run 状态文件建立可观测链路。

## 项目经历

### MergeWarden（Code Review Agent）

2026/03 - 2026/06｜GitHub: https://github.com/takagibit18/MergeWarden

面向开发团队的自动化 PR Review Agent。系统接收本地仓库、PR patch 与错误日志，输出结构化 Review 报告；项目累计约 9.5K 行 Python，覆盖 Agent 编排、工具系统、安全执行、评测与 CI 集成模块。

- 基于 ReAct 范式实现 Agent 编排：Context Preparation -> Model Analysis -> Tool Execution -> Result Processing -> Continue / Terminate。
- 建立全链路可观测事件日志：每轮 agent run 输出结构化 JSONL event log，记录模型决策、工具调用、证据来源与终止原因。
- 通过 5 轮定向评测与修复，将 Hit Rate 从 25% 提升至 75%，负样本 False Positive Rate 从 16.67% 降至 0%。
- 实现动态上下文管理：根据 diff 行号从仓库快照中按需加载上下文，预加载内容从 75,466 字符降至 3,691 字符，下降 95.1%。
- 采用优先级截断与 LLM 摘要实现双层上下文压缩，控制上下文预算。
- 通过 Pydantic 强校验结构化输出，解析成功后才进入后续业务逻辑；解析失败抛出异常而非静默吞错。
- 将最终输出格式封装为工具 schema，避免模型自由输出 JSON 文本，将类型非法率降低到 0%。
- 通过路径沙箱与分级门控限制工具执行边界；Execute 工具支持安全工具并发执行、去重缓存和反馈滑动窗口，减少重复工具调用。

### ShotgunCV（批量简历优化 Agent）

2026/04 - 2026/06｜GitHub: https://github.com/takagibit18/shotgunCV

面向批量岗位投递场景的 AI 简历运营 Agent。系统围绕 Ingest -> Analyze -> Generate -> Evaluate -> Plan -> Report 六阶段流水线，实现 JD 批量解析、简历变体生成、评分卡排序与投递策略输出。

- 设计确定性流水线编排：将岗位解析、候选素材检索、简历生成、质量评估与投递建议拆成可观测阶段，避免端到端黑盒生成。
- 每轮产出可追踪的评分卡与策略报告，支持后续人工审阅、指标对比和回归定位。
- 构建 RAG 检索增强与结构化评估：结合候选人经历库与岗位要求进行证据检索，基于匹配度、覆盖率、真实性与风险项评估生成质量。
- 建立 golden set 与分层评估体系，覆盖 retriever、generator、no-answer abstention、Evidence Gate 等评测场景。
- 使用 LangGraph 并行 fan-out 架构，基于 JD 维度并行执行分析与生成任务；27 JD 场景加速 5.96x，串行 1975-2169ms 降至并行 327-362ms。
- 在工作量增长 3.4x 时，整体耗时仅增长 1.9x。
- 设计小批量 bypass（JD <= 3）降低 review 耗时 19.4%。
- 通过 compiled graph 模块级缓存消除重复编译，提升多轮批处理稳定性。

## 候选人定位

- 适合方向：Agent 工程、LLM 应用开发、RAG/检索评测、AI-native 工具链、简历/招聘/生产力类 AI 产品。
- 强证据：LangGraph/ReAct 编排、Tool Calling、Pydantic 结构化输出、FastAPI 服务化、RAG 指标评估、pgvector/PostgreSQL、CI/CD、Docker Compose、Redis、JSONL 可观测日志。
- 需要谨慎表述：没有明确全职生产级大规模平台 owner 经历；没有 Kubernetes 生产集群运维、金融风控建模、医疗影像算法、海外销售或 Java 微服务专家证据。
