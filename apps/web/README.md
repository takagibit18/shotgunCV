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
