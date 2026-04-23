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

  return (
    <main>
      <section className="hero">
        <p className="eyebrow">{"\u53ea\u8bfb\u67e5\u770b\u5668"}</p>
        <h1>{"ShotgunCV \u8fd0\u884c\u67e5\u770b\u5668"}</h1>
        <p>
          {
            "\u6d4f\u89c8\u672c\u5730 runs \u76ee\u5f55\u4e2d\u7684\u9636\u6bb5\u4ea7\u7269\u3001\u8bc4\u4f30\u7ed3\u679c\u4e0e\u6295\u9012\u7b56\u7565\uff0c\u4e0d\u89e6\u53d1\u4efb\u4f55 pipeline \u5199\u5165\u3002"
          }
        </p>
      </section>

      <section className="grid">
        {runs.map((run) => (
          <Link key={run.runId} href={`/runs/${run.runId}`} className="card">
            <p className="eyebrow">{run.label || "\u672a\u547d\u540d\u8fd0\u884c"}</p>
            <h2>{run.runId}</h2>
            <p className="muted mono">{run.lastModified}</p>
            <div className="pill-row">
              <span className="pill">
                {"\u751f\u6210\u5668\uff1a"}
                {run.generatorProvider}
              </span>
              <span className="pill">
                {"\u8bc4\u5ba1\u5668\uff1a"}
                {run.judgeProvider}
              </span>
            </div>
            <div className="pill-row" style={{ marginTop: 14 }}>
              {run.completedStages.map((stage) => (
                <span key={stage} className="pill">
                  {STAGE_LABELS[stage] ?? stage}
                </span>
              ))}
            </div>
          </Link>
        ))}
      </section>
    </main>
  );
}
