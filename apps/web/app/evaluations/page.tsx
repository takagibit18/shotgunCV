import React from "react";
import Link from "next/link";

import { loadEvaluationResults } from "../../lib/evaluations";
import { AppShell } from "../AppShell";
import { EvaluationQueue } from "./EvaluationQueue";

export default async function EvaluationPage() {
  const results = await loadEvaluationResults();
  const total = results.length;
  const blockedOrReview = results.filter((item) => item.gateStatus === "blocked" || item.gateStatus === "needs_review").length;
  const highRisk = results.filter((item) => (item.riskScore ?? 0) >= 0.7).length;
  const legacy = results.filter((item) => item.artifactMode === "legacy").length;
  const averageScore = averagePercent(results.map((item) => item.finalScore));
  const averageRisk = averagePercent(results.map((item) => item.riskScore));

  return (
    <AppShell active="evaluation" eyebrow="评估结果">
      <main className="app-shell operational-shell">
        <Link href="/" className="backlink">
          返回运行队列
        </Link>

        <section className="page-header">
          <div>
            <h1 className="page-title">评估结果列表</h1>
          </div>
        </section>

        <section className="status-strip" aria-label="评估结果总览">
          <article className="status-strip-item info">
            <span>评估结果</span>
            <strong>{total}</strong>
          </article>
          <article className={blockedOrReview > 0 ? "status-strip-item warning" : "status-strip-item success"}>
            <span>需处理 gate</span>
            <strong>{blockedOrReview}</strong>
          </article>
          <article className={highRisk > 0 ? "status-strip-item danger" : "status-strip-item success"}>
            <span>高风险岗位</span>
            <strong>{highRisk}</strong>
          </article>
          <article className="status-strip-item">
            <span>历史产物</span>
            <strong>{legacy}</strong>
          </article>
        </section>

        <section className="trend-strip" aria-label="趋势概览">
          <div>
            <p className="eyebrow">趋势概览</p>
            <h2>评分与风险密度</h2>
          </div>
          <TrendMetric label="JD 数" value={total} />
          <TrendMetric label="平均最终分" value={averageScore} />
          <TrendMetric label="平均风险分" value={averageRisk} tone={highRisk > 0 ? "warning" : "success"} />
        </section>

        <EvaluationQueue results={results} />
      </main>
    </AppShell>
  );
}

function TrendMetric({ label, value, tone }: { label: string; value: string | number; tone?: "warning" | "success" }) {
  return (
    <div className={tone ? `trend-metric ${tone}` : "trend-metric"}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function averagePercent(values: Array<number | null>): string {
  const numericValues = values.filter((value): value is number => typeof value === "number");
  if (numericValues.length === 0) {
    return "--";
  }
  const average = numericValues.reduce((sum, value) => sum + value, 0) / numericValues.length;
  return `${Math.round(average * 100)}%`;
}
