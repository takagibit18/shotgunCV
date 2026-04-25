# ShotgunCV

`ShotgunCV` 是一个面向海投场景的 `Pipeline-first` AI Resume Ops 系统，围绕批量岗位输入执行解析、生成、评分、排序与投递策略输出。

当前版本：`v0.2.0`，重点增强 Explainable Ranking 闭环。

主流程：

`multiple JD inputs -> analysis -> resume variants -> scoring -> ranking -> strategy`

## 仓库重点

- `docs/`：产品、系统、评估与仓库决策文档。
- `apps/cli/`：v1 首要交互入口。
- `apps/web/`：只读 Run Viewer。
- `packages/py-core/`：领域模型与流水线原语。
- `packages/py-evals/`：规则评估与 LLM 判分能力。
- `packages/py-agents/`：编排与提示词资产。
- `packages/ts-shared/`：Web 只读解析所用的 TypeScript 共享契约。

## 最小闭环运行

### 1. 一键运行

当前仓库已提供基于 `fixtures/` 的 deterministic 最小闭环，推荐用 `run` 一次完成全流程：

```bash
python -m pip install -e .
python -m shotguncv_cli.main run --run-dir ./runs/demo --candidate-id cand-001 --cv ./fixtures/candidates/base_resume.md --jd ./fixtures/jds/sample_batch.txt
```

`--cv` 与 `--jd` 都可以重复传入，也可以指向文件或目录。当前输入模块支持：

- `.txt` / `.md` / `.markdown`
- 文本型 `.pdf`
- 图片文件（`.png` / `.jpg` / `.jpeg` / `.webp` 等）+ 同名 `.txt` 或 `.md` sidecar

图片和扫描 PDF 不做 OCR。若图片没有同名文本 sidecar，或 PDF 无法提取文本，系统会给出明确错误提示。

### 2. 分阶段 Deterministic 回放

如果需要调试某个阶段，也可以继续按阶段执行。旧参数仍然兼容：

```bash
python -m pip install -e .
python -m shotguncv_cli.main ingest --run-dir ./runs/demo --candidate-id cand-001 --candidate-resume ./fixtures/candidates/base_resume.md --jd-file ./fixtures/jds/sample_batch.txt
python -m shotguncv_cli.main analyze --run-dir ./runs/demo
python -m shotguncv_cli.main generate --run-dir ./runs/demo
python -m shotguncv_cli.main evaluate --run-dir ./runs/demo
python -m shotguncv_cli.main plan --run-dir ./runs/demo
python -m shotguncv_cli.main report --run-dir ./runs/demo
```

补充说明：

- 若不传 `--config`，`ingest` 会自动写入 deterministic `run config`
- 快照路径固定为 `run_dir/config/run_config.json`

### 3. OpenAI 配置运行

若需要在 `generate/evaluate` 阶段启用 OpenAI 格式模型（含兼容端点），按下面步骤：

```bash
cp ./.env.example ./.env
python -m shotguncv_cli.main run --run-dir ./runs/openai-demo --candidate-id cand-001 --cv ./fixtures/candidates/base_resume.md --jd ./fixtures/jds/sample_batch.txt
```

在 `.env` 中至少填写：

```bash
OPENAI_API_KEY=your-real-key
```

说明：

- provider 选择只由 `run_dir/config/run_config.json` 决定，默认保持 deterministic
- 项目 `.env` 只负责为已选中的 OpenAI / OpenAI-compatible provider 注入 model/base_url/api key
- 模型密钥只从项目 `.env` 读取，不读取系统环境变量
- 可通过 `SHOTGUNCV_GENERATOR_MODEL` / `SHOTGUNCV_JUDGE_MODEL` 指定模型
- 若模型都留空，则默认 `gpt-5.4-mini`
- 兼容 OpenAI 格式端点：设置 `OPENAI_BASE_URL`

`run_dir` 默认会生成如下结构化产物：

- `config/run_config.json`
- `ingest/manifest.json`
- `analyze/candidate_profile.json`
- `analyze/jd_profiles.json`
- `generate/resume_variants.json`
- `evaluate/scorecards.json`
- `evaluate/gap_maps.json`
- `evaluate/ranking_explanations.json`
- `evaluate/eval_summary.json`
- `plan/application_strategies.json`
- `report/summary.md`

## Web Viewer

仓库现已提供只读 Web Viewer，用于浏览本地 `runs/` 目录中的产物：

```bash
cd ./apps/web
npm install
set SHOTGUNCV_RUNS_DIR=../../runs
npm run dev
```

Web 只消费结构化产物，不发起运行，也不写回 `runs/`。

## v1 已定边界

- 仅面向海投工作流。
- 输入优先支持文本、Markdown、文本型 PDF，以及带文本 sidecar 的图片。
- 候选人画像来源于主简历与补充资料。
- 生成策略采用岗位簇版本 + 高价值 JD 定制版本。
- 从第一天内建评估系统。
- Python pipeline 仍是唯一业务真源，Web 仅做只读查看。

## v1 明确不做

- 自动投递行为。
- 招聘网站账号与页面自动化。
- OCR、视觉模型解析和截图自动识别。
- 泛化求职助手能力。

## Conventions

- Markdown 文档统一使用中文主文本。
- 代码注释统一使用英文。
- Git 提交信息统一使用英文。
