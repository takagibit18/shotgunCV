# 项目 UI 设计 Skills

这些 skills 用于后续设计或实现 `apps/web` 的本地单用户工作台体验。它们提供可复用设计约束与检查清单，不自动触发构建，也不替代 `docs/` 中已经生效的产品边界。

## 当前设计哲学

- `apps/web` 是本地单用户工作台，不是远程 SaaS、CRM、多用户系统或自动投递平台。
- Python pipeline 和 `run_dir` artifacts 是业务真源；Web 只组织、展示、触发明确边界内的动作。
- 默认界面语言是中文；英文只用于技术标识、文件名、artifact 名或必要的 provider 字段。
- 视觉基调是冷白、紧凑、证据优先：细边框、小圆角、低阴影、语义色、稳定表格和列表密度。
- 删除过度解释、装饰性 AI 感、重复状态 chip、大面积渐变和泛化营销文案。
- 每个评分、建议、风险、生成内容都要靠近来源、缺口、人工检查或下一步动作。

## 技能索引

- `designing-ai-trustworthy-interfaces`: AI 输出、建议、评分、排序、生成结果的信任校准。
- `designing-ai-feedback-control`: AI 反馈、人工接管、撤销、重试、偏好重置。
- `designing-workbench-operational-screens`: 工作台、Run Viewer、任务流、详情页布局。
- `designing-workbench-data-tables`: 表格、筛选、排序、批量操作、空态与异常状态。
- `designing-workbench-design-system`: token、组件状态、可访问性、密度与交付约束。

## 资料来源

- Microsoft HAX Toolkit: https://www.microsoft.com/en-us/haxtoolkit/
- Microsoft Guidelines for Human-AI Interaction: https://www.microsoft.com/en-us/research/publication/guidelines-for-human-ai-interaction/
- Google People + AI Guidebook: https://pair.withgoogle.com/guidebook-v2/chapters
- Google PAIR Explainability + Trust: https://pair.withgoogle.com/guidebook-v2/chapter/explainability-trust/
- Google PAIR Feedback + Control: https://pair.withgoogle.com/guidebook-v2/chapters/feedback-controls/
- Material Design Accessibility: https://m1.material.io/usability/accessibility.html
- Atlassian Design System: https://atlassian.design/design-system/
