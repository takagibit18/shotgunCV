# CLI 最小闭环示例

以下示例基于仓库内固定样本，推荐使用 `run` 一次完成 `ingest -> analyze -> generate -> evaluate -> plan -> report`：

```bash
python -m pip install -e .
python -m shotguncv_cli.main run --run-dir ./runs/demo --candidate-id cand-001 --cv ./fixtures/candidates/base_resume.md --jd ./fixtures/jds/sample_batch.txt
```

如果需要调试单个阶段，旧的分阶段命令仍然可用：

```bash
python -m shotguncv_cli.main ingest --run-dir ./runs/demo --candidate-id cand-001 --candidate-resume ./fixtures/candidates/base_resume.md --jd-file ./fixtures/jds/sample_batch.txt
python -m shotguncv_cli.main analyze --run-dir ./runs/demo
python -m shotguncv_cli.main generate --run-dir ./runs/demo
python -m shotguncv_cli.main evaluate --run-dir ./runs/demo
python -m shotguncv_cli.main plan --run-dir ./runs/demo
python -m shotguncv_cli.main report --run-dir ./runs/demo
```

`--cv` 与 `--jd` 可重复传入，也可指向文件或目录。支持 `.txt`、`.md`、文本型 `.pdf`，以及图片输入。

图片会先走本地 Tesseract OCR；OCR 为空或失败时，默认尝试 OpenAI-compatible 视觉兜底；如果同名 `.txt` / `.md` sidecar 存在，也可以作为最后兜底。完全本地运行时可加 `--no-vision-fallback`：

```bash
python -m shotguncv_cli.main run --run-dir ./runs/image-demo --candidate-id cand-001 --cv ./private_inputs/resume.png --jd ./fixtures/jds/sample_batch.txt --no-vision-fallback
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

该示例默认使用 deterministic provider，不依赖外部模型或网络。
