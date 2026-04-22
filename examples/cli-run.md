# CLI 最小闭环示例

以下示例基于仓库内固定样本，从 `ingest` 运行到 `report`：

```bash
python -m pip install -e .
python -m shotguncv_cli.main ingest --run-dir ./runs/demo --candidate-id cand-001 --candidate-resume ./fixtures/candidates/base_resume.md --jd-file ./fixtures/jds/sample_batch.txt
python -m shotguncv_cli.main analyze --run-dir ./runs/demo
python -m shotguncv_cli.main generate --run-dir ./runs/demo
python -m shotguncv_cli.main evaluate --run-dir ./runs/demo
python -m shotguncv_cli.main plan --run-dir ./runs/demo
python -m shotguncv_cli.main report --run-dir ./runs/demo
```

生成后的关键文件：

- `runs/demo/ingest/manifest.json`
- `runs/demo/analyze/candidate_profile.json`
- `runs/demo/analyze/jd_profiles.json`
- `runs/demo/generate/resume_variants.json`
- `runs/demo/evaluate/scorecards.json`
- `runs/demo/evaluate/gap_maps.json`
- `runs/demo/evaluate/eval_summary.json`
- `runs/demo/plan/application_strategies.json`
- `runs/demo/report/summary.md`

该示例默认使用 deterministic generator/judge stub，不依赖外部模型或网络。

补充说明：

- 若不传 `--config`，`ingest` 会自动写入 deterministic `run config`
- 快照路径固定为 `runs/demo/config/run_config.json`
