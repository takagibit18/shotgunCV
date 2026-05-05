import React from "react";
import Link from "next/link";

import { listRuns } from "../lib/runs";


const STAGE_LABELS: Record<string, string> = {
  ingest: "\u5bfc\u5165",
  analyze: "\u5206\u6790",
  generate: "\u751f\u6210",
  evaluate: "\u8bc4\u4f30",
  plan: "\u8ba1\u5212",
  report: "\u62a5\u544a",
};


export default async function HomePage() {
  const runs = await listRuns();
  const totalRuns = runs.length;
  const completedStageCount = runs.reduce((sum, run) => sum + run.completedStages.length, 0);
  const latestRun = runs[0];

  return (
    <main className="app-shell">
      <section className="workspace-hero editorial-hero">
        <div>
          <p className="eyebrow">{"v0.5.8 本地 AI 简历运营工作台"}</p>
          <h1>{"ShotgunCV 投递运行台"}</h1>
          <p className="hero-copy">
            {
              "面向本地单用户的 AI Resume Ops 工作台，集中查看 runs 目录中的阶段产物、评分证据、风险提示和下一步投递动作。"
            }
          </p>
          <p className="sr-only">{"ShotgunCV \u8fd0\u884c\u67e5\u770b\u5668"}</p>
        </div>
        <div className="hero-metrics dark-product-surface" aria-label="\u8fd0\u884c\u603b\u89c8">
          <div className="metric-tile">
            <span className="metric-value">{totalRuns}</span>
            <span className="metric-label">{"\u8fd0\u884c\u6279\u6b21"}</span>
          </div>
          <div className="metric-tile">
            <span className="metric-value">{completedStageCount}</span>
            <span className="metric-label">{"\u5df2\u5b8c\u6210\u9636\u6bb5"}</span>
          </div>
          <div className="metric-tile">
            <span className="metric-value">{latestRun ? latestRun.completedStages.length : 0}</span>
            <span className="metric-label">{"\u6700\u65b0\u8fdb\u5ea6"}</span>
          </div>
          <Link href="/upload" className="primary-link coral-cta">
            {"创建草稿 run"}
          </Link>
        </div>
      </section>

      <section className="section section-flush">
        <div className="section-heading">
          <div>
            <p className="eyebrow">{"运行队列"}</p>
            <h2>{"运行列表"}</h2>
          </div>
          <span className="status-chip">{"本机运行管理"}</span>
        </div>

        <div className="run-table" role="list">
        {runs.map((run) => (
          <Link key={run.runId} href={`/runs/${run.runId}`} className="run-row" role="listitem">
            <div className="run-primary">
              <p className="eyebrow">{run.label || "\u672a\u547d\u540d\u8fd0\u884c"}</p>
              <h3>{run.runId}</h3>
              <p className="muted mono">{run.lastModified}</p>
            </div>
            <div className="run-progress">
              <div className="progress-meta">
                <span>{"\u9636\u6bb5\u5b8c\u6210\u5ea6"}</span>
                <strong>
                  {run.completedStages.length}
                  {"/6"}
                </strong>
              </div>
              <div className="stage-track" aria-hidden="true">
                {Object.keys(STAGE_LABELS).map((stage) => (
                  <span
                    key={stage}
                    className={run.completedStages.some((completedStage) => completedStage === stage) ? "stage-dot active" : "stage-dot"}
                  />
                ))}
              </div>
              <div className="pill-row compact">
              {run.completedStages.map((stage) => (
                <span key={stage} className="pill">
                  {STAGE_LABELS[stage] ?? stage}
                </span>
              ))}
              </div>
            </div>
            <div className="provider-stack">
              <span>
                {"状态 "}
                <strong>{run.draftStatus}</strong>
              </span>
              <span>
                {"\u751f\u6210 "}
                <strong>{run.generatorProvider}</strong>
              </span>
              <span>
                {"\u8bc4\u5ba1 "}
                <strong>{run.judgeProvider}</strong>
              </span>
            </div>
          </Link>
        ))}
        </div>
      </section>
    </main>
  );
}
