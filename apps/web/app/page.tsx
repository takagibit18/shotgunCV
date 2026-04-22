import React from "react";
import Link from "next/link";

import { listRuns } from "../lib/runs";


export default async function HomePage() {
  const runs = await listRuns();

  return (
    <main>
      <section className="hero">
        <p className="eyebrow">Read-Only Viewer</p>
        <h1>ShotgunCV Run Viewer</h1>
        <p>浏览本地 runs 目录中的阶段产物、评分结果与投递策略，不触发任何 pipeline 写入。</p>
      </section>

      <section className="grid">
        {runs.map((run) => (
          <Link key={run.runId} href={`/runs/${run.runId}`} className="card">
            <p className="eyebrow">{run.label || "untitled run"}</p>
            <h2>{run.runId}</h2>
            <p className="muted mono">{run.lastModified}</p>
            <div className="pill-row">
              <span className="pill">generator: {run.generatorProvider}</span>
              <span className="pill">judge: {run.judgeProvider}</span>
            </div>
            <div className="pill-row" style={{ marginTop: 14 }}>
              {run.completedStages.map((stage) => (
                <span key={stage} className="pill">
                  {stage}
                </span>
              ))}
            </div>
          </Link>
        ))}
      </section>
    </main>
  );
}
