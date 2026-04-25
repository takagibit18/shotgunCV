# Web Viewer

`apps/web` 是 ShotgunCV 的只读 Web Viewer，用于浏览本地 `runs/` 目录中的结构化产物。

当前范围：

- 展示 run 列表、阶段完成情况与 provider 配置
- 展示单个 run 的 Analyze / Generate / Evaluate / Plan 摘要
- 渲染 `report/summary.md`

明确不做：

- 不触发 pipeline
- 不写入 `runs/`
- 不承载表单、登录或多用户能力

## 启动

```bash
npm install
set SHOTGUNCV_RUNS_DIR=../../runs
npm run dev
```

## v0.4.0 上传草稿

`apps/web` 新增本地单用户上传入口：`/upload`。该入口只创建 run 草稿，不触发 pipeline，不解析正文，也不写入 `ingest/manifest.json`。

草稿落盘结构：

- `runs/<runId>/input_files/cv/`
- `runs/<runId>/input_files/jd/`
- `runs/<runId>/ingest/upload_manifest.json`
- `runs/<runId>/config/run_config.json`

`upload_manifest.json` 只保存上传元数据、相对路径和下一步 CLI 命令。真正的输入解析、OCR、vision fallback、评分和报告生成仍由 Python CLI 执行。
