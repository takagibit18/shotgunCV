# 固定样本目录

该目录存放用于解析、生成、评分与排序回归测试的固定候选人与 JD 样本。

## 当前样本

- `candidates/base_resume.md`：候选人主简历最小样例
- `jds/sample_batch.txt`：两条 JD 的批量输入样例，供 CLI 和阶段链路测试复用

补充：

- 项目根目录提供 `.env.example`，用于 OpenAI 格式模型调用配置示例
