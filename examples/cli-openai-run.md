# CLI OpenAI 配置运行示例

以下示例演示如何通过项目 `.env` + `run_config` 在 `generate/evaluate` 阶段启用 OpenAI 格式模型：

```bash
cp ./.env.example ./.env
python -m pip install -e .
python -m shotguncv_cli.main ingest --run-dir ./runs/openai-demo --candidate-id cand-001 --candidate-resume ./fixtures/candidates/base_resume.md --jd-file ./fixtures/jds/sample_batch.txt
python -m shotguncv_cli.main analyze --run-dir ./runs/openai-demo
python -m shotguncv_cli.main generate --run-dir ./runs/openai-demo
python -m shotguncv_cli.main evaluate --run-dir ./runs/openai-demo
python -m shotguncv_cli.main plan --run-dir ./runs/openai-demo
python -m shotguncv_cli.main report --run-dir ./runs/openai-demo
```

关键说明：

- 之后各阶段统一从 `run_dir/config/run_config.json` 读取默认配置，但会被项目 `.env` 统一覆盖
- 模型密钥只从项目 `.env` 读取，不读取系统环境变量
- `SHOTGUNCV_GENERATOR_PROVIDER` 和 `SHOTGUNCV_JUDGE_PROVIDER` 可直接覆盖 provider
- `OPENAI_MODEL` 可在 `.env` 自行填写；若留空则默认 `gpt-5.4-mini`
- 支持 OpenAI 兼容接口：可在 `.env` 里设置 `OPENAI_BASE_URL`
- 若 `.env` 中缺少 `OPENAI_API_KEY`，`generate` 或 `evaluate` 会直接失败，不会静默回退到 deterministic
