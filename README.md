# ShotgunCV

`ShotgunCV` 是一个面向海投场景的 `Pipeline-first` AI Resume Ops 系统，围绕批量岗位输入执行解析、生成、评分、排序与投递策略输出。

主流程：

`multiple JD inputs -> analysis -> resume variants -> scoring -> ranking -> strategy`

## 仓库重点

- `docs/`：产品、系统、评估与仓库决策文档。
- `apps/cli/`：v1 首要交互入口。
- `packages/py-core/`：领域模型与流水线原语。
- `packages/py-evals/`：规则评估与 LLM 判分能力。
- `packages/py-agents/`：编排与提示词资产。

## 最小闭环运行

当前仓库已提供基于 `fixtures/` 的 deterministic v1 最小闭环，可按阶段执行：

```bash
python -m pip install -e .
python -m shotguncv_cli.main ingest --run-dir ./runs/demo --candidate-id cand-001 --candidate-resume ./fixtures/candidates/base_resume.md --jd-file ./fixtures/jds/sample_batch.txt
python -m shotguncv_cli.main analyze --run-dir ./runs/demo
python -m shotguncv_cli.main generate --run-dir ./runs/demo
python -m shotguncv_cli.main evaluate --run-dir ./runs/demo
python -m shotguncv_cli.main plan --run-dir ./runs/demo
python -m shotguncv_cli.main report --run-dir ./runs/demo
```

`run_dir` 默认会生成如下结构化产物：

- `ingest/manifest.json`
- `analyze/candidate_profile.json`
- `analyze/jd_profiles.json`
- `generate/resume_variants.json`
- `evaluate/scorecards.json`
- `evaluate/gap_maps.json`
- `evaluate/eval_summary.json`
- `plan/application_strategies.json`
- `report/summary.md`

## v1 已定边界

- 仅面向海投工作流。
- 输入优先支持文本与 URL。
- 候选人画像来源于主简历与补充资料。
- 生成策略采用岗位簇版本 + 高价值 JD 定制版本。
- 从第一天内建评估系统。

## v1 明确不做

- 自动投递行为。
- 招聘网站账号与页面自动化。
- 截图/OCR 作为一等输入路径。
- 泛化求职助手能力。

## Conventions

- Markdown 文档统一使用中文主文本。
- 代码注释统一使用英文。
- Git 提交信息统一使用英文。
