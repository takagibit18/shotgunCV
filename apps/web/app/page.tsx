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
      <section className="workspace-hero">
        <div>
          <p className="eyebrow">{"\u53ea\u8bfb AI \u51b3\u7b56\u89c6\u56fe"}</p>
          <h1>{"ShotgunCV \u8fd0\u884c\u5de5\u4f5c\u53f0"}</h1>
          <p className="hero-copy">
            {
              "\u6d4f\u89c8\u672c\u5730 runs \u76ee\u5f55\u4e2d\u7684\u9636\u6bb5\u4ea7\u7269\u3001\u8bc4\u4f30\u7ed3\u679c\u4e0e\u6295\u9012\u7b56\u7565\uff0c\u4fdd\u6301\u53ea\u8bfb\uff0c\u4e0d\u89e6\u53d1\u4efb\u4f55 pipeline \u5199\u5165\u3002"
            }
          </p>
          <p className="sr-only">{"ShotgunCV \u8fd0\u884c\u67e5\u770b\u5668"}</p>
        </div>
        <div className="hero-metrics" aria-label="\u8fd0\u884c\u603b\u89c8">
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
          <Link href="/upload" className="primary-link">
            {"Create draft run"}
          </Link>
        </div>
      </section>

      <section className="section section-flush">
        <div className="section-heading">
          <div>
            <p className="eyebrow">{"运行队列"}</p>
            <h2>{"\u8fd0\u884c\u5217\u8868"}</h2>
          </div>
          <span className="status-chip">{"\u53ea\u8bfb\u6a21\u5f0f"}</span>
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
