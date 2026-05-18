import React from "react";
import Link from "next/link";

import { loadEvaluationResults } from "../../lib/evaluations";
import { AppShell, Icon, MetricCard } from "../AppShell";
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
        <section className="page-header evaluation-page-header">
          <div className="page-kicker-row">
            <Link href="/runs" className="backlink icon-link">
              <Icon name="chevron-left" />
              返回运行队列
            </Link>
            <span className="breadcrumb-text">评估结果 / 队列</span>
          </div>
          <div>
            <h1 className="page-title">评估结果列表</h1>
            <p className="hero-copy">按岗位聚合已固化的评分、门槛、证据和投递建议，优先处理风险与复核项。</p>
          </div>
        </section>

        <section className="metric-card-grid evaluation-metric-grid" aria-label="评估结果总览">
          <MetricCard icon="stats" label="总评估" value={total} helper="已完成评估的岗位行" tone="blue" />
          <MetricCard
            icon="alert-triangle"
            label="需复核门槛"
            value={blockedOrReview}
            helper="阻断或需人工复核"
            tone={blockedOrReview > 0 ? "orange" : "green"}
          />
          <MetricCard
            icon="shield-alert"
            label="高风险岗位"
            value={highRisk}
            helper="risk_score ≥ 70%"
            tone={highRisk > 0 ? "red" : "green"}
          />
          <MetricCard icon="clock" label="历史产物" value={legacy} helper="缺少新版门槛字段" tone="purple" />
        </section>

        <div className="eval-summary-strip" aria-label="趋势与评估边界">
          <span className="eval-summary-item">
            <Icon name="stats" />
            平均最终分 <strong>{averageScore}</strong>
          </span>
          <span className="eval-summary-item">
            <Icon name="shield-alert" />
            平均风险分 <strong>{averageRisk}</strong>
          </span>
          <span className="eval-summary-hint">
            评估基于已固化评分快照，不包含实时策略变更。
          </span>
        </div>

        <EvaluationQueue results={results} />
      </main>
    </AppShell>
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
