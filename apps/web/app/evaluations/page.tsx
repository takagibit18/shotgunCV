import React from "react";
import Link from "next/link";

import { loadEvaluationResults } from "../../lib/evaluations";
import { AppShell, Icon } from "../AppShell";
import { EvaluationQueue } from "./EvaluationQueue";

export default async function EvaluationPage() {
  const results = await loadEvaluationResults();
  const total = results.length;
  const blockedOrReview = results.filter((item) => item.gateStatus === "blocked" || item.gateStatus === "needs_review").length;
  const highRisk = results.filter((item) => (item.riskScore ?? 0) >= 0.7).length;
  const legacy = results.filter((item) => item.artifactMode === "legacy").length;
  const averageScore = averagePercent(results.map((item) => item.finalScore));
  const averageRisk = averagePercent(results.map((item) => item.riskScore));
  const freshnessText = formatFreshness(results[0]?.lastModified);

  return (
    <AppShell active="evaluation" eyebrow="评估结果 / 岗位队列" freshnessText={freshnessText}>
      <main className="app-shell operational-shell">
        <Link href="/" className="backlink">
          返回运行队列
        </Link>

        <section className="page-header detail-header">
          <div>
            <p className="eyebrow">v0.6.2 评估结果</p>
            <h1 className="page-title">独立评估结果列表</h1>
            <p className="hero-copy">
              将所有 run 的 JD 评估结果聚合成可筛选、可排序、可回溯的工作队列。每条结果都保留 scorecard、gate、证据、风险和投递建议来源。
            </p>
          </div>
          <div className="rail-card purple">
            <div className="metric-title">
              <Icon name="sparkle" />
              <h3>可信评估边界</h3>
            </div>
            <p className="muted">
              本页只读取本地 artifacts，不重新判断业务结论；缺少 v0.5.7 gate 或三分制产物时按历史 scorecard 降级展示。
            </p>
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

function formatFreshness(value?: string): string {
  if (!value) {
    return "暂无评估";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "本地数据";
  }
  return date.toISOString().slice(11, 16);
}
