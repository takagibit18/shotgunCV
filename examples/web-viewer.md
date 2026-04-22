# Web Viewer 示例

Web Viewer 是只读界面，用于浏览 `runs/` 目录中的结构化产物，不会触发新的 pipeline 运行。

## 启动方式

```bash
cd ./apps/web
npm install
set SHOTGUNCV_RUNS_DIR=../../runs
npm run dev
```

默认情况下，若未设置 `SHOTGUNCV_RUNS_DIR`，应用会读取仓库根目录下的 `runs/`。

## 页面说明

- `/`：run 列表页，显示阶段完成情况、provider 和标签
- `/runs/<runId>`：run 概览页，展示 Analyze / Generate / Evaluate / Plan 四块摘要
- `/runs/<runId>/report`：Markdown 报告页；如果报告不存在，会显示“阶段未完成”
