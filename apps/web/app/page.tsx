import React from "react";
import Link from "next/link";

import { STATUS_LABELS } from "../lib/labels";
import { listRuns, type RunSummary } from "../lib/runs";
import { AppShell, Icon } from "./AppShell";
import { RunQueue } from "./RunQueue";

export default async function HomePage() {
  const runs = await listRuns();
  const totalRuns = runs.length;
  const activeRuns = runs.filter((run) => run.draftStatus === "running" || run.draftStatus === "queued").length;
  const warningRuns = runs.filter((run) => run.runStatus?.quality_summary || run.runStatus?.error_summary).length;
  const doneRuns = runs.filter((run) => run.draftStatus === "done").length;
  const completionRate = totalRuns === 0 ? 0 : Math.round((doneRuns / totalRuns) * 100);
  const recentRuns = runs.slice(0, 4);

  return (
    <AppShell active="dashboard" eyebrow="仪表盘">
      <main className="app-shell operational-shell">
        <section className="page-header with-actions dashboard-header">
          <div>
            <h1>运行队列</h1>
          </div>
          <Link href="/upload" className="primary-link dashboard-primary-cta icon-link">
            <Icon name="play" />
            开始新投递
          </Link>
        </section>

        <div className="workspace-grid">
          <div className="workspace-main">
            <section className="metric-card-grid" aria-label="运行总览">
              <MetricTile value={totalRuns} label="运行批次" tone="info" />
              <MetricTile value={activeRuns} label="进行中" tone="success" />
              <MetricTile value={warningRuns} label="警告/失败" tone="warning" />
              <MetricTile value={doneRuns} label="已完成" tone="purple" />
            </section>

            <section className="trend-strip" aria-label="趋势概览">
              <div>
                <p className="eyebrow">趋势概览</p>
                <h2>批次容量与健康度</h2>
              </div>
              <TrendMetric label="运行数" value={totalRuns} />
              <TrendMetric label="完成率" value={`${completionRate}%`} />
              <TrendMetric label="警告/失败" value={warningRuns} tone={warningRuns > 0 ? "warning" : "success"} />
            </section>

            <RunQueue runs={runs} />
          </div>

          <aside className="insight-rail" aria-label="运行洞察">
            <section className="rail-card">
              <div className="section-heading">
                <div>
                  <h3>近期活动</h3>
                </div>
              </div>
              <div className="activity-list">
                {recentRuns.length > 0 ? (
                  recentRuns.map((run) => (
                    <div className="activity-item" key={run.runId}>
                      <span className={buildActivityDotClassName(run.draftStatus)} />
                      <span className="activity-meta">
                        <strong title={run.label || run.runId}>{truncateText(run.label || run.runId, 24)}</strong>
                        <small>
                          阶段 {buildStageSummary(run.completedStages.length)} · {STATUS_LABELS[run.draftStatus] ?? run.draftStatus}
                        </small>
                      </span>
                      <span className="muted">{formatTime(run.lastModified)}</span>
                    </div>
                  ))
                ) : (
                  <p className="muted">暂无运行活动。</p>
                )}
              </div>
            </section>

            {buildPrimaryInsight(runs) ? (
              <section className="rail-card purple">
                <div className="section-heading">
                  <div>
                    <h3>智能洞察</h3>
                  </div>
                </div>
                <div className="recommendation-list">
                  {runs.length === 0 ? (
                    <Link href="/upload" className="recommendation-item safe dashboard-first-run-card">
                      <Icon name="play" />
                      <div>
                        <strong>开始您的第一次投递</strong>
                        <p>上传简历和岗位信息，创建投递草稿后即可在详情页启动本地流程。</p>
                      </div>
                    </Link>
                  ) : (
                    <div className={buildPrimaryInsight(runs)!.tone}>
                      <Icon name="sparkle" />
                      <div>
                        <strong>{buildPrimaryInsight(runs)!.title}</strong>
                        <p>{buildPrimaryInsight(runs)!.reason}</p>
                      </div>
                    </div>
                  )}
                </div>
              </section>
            ) : null}

          </aside>
        </div>
      </main>
    </AppShell>
  );
}

function TrendMetric({ label, value, tone }: { label: string; value: number | string; tone?: "warning" | "success" }) {
  return (
    <div className={tone ? `trend-metric ${tone}` : "trend-metric"}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function MetricTile({
  value,
  label,
  tone,
}: {
  value: number;
  label: string;
  tone: "info" | "success" | "warning" | "purple";
}) {
  return (
    <div className="metric-tile">
      <span className={`metric-icon ${tone === "info" ? "" : tone}`}>
        <Icon name={tone === "warning" ? "bell" : tone === "purple" ? "check-square" : "list"} />
      </span>
      <span className="metric-body">
        <span className="metric-label">{label}</span>
        <span className="metric-value">{value}</span>
      </span>
    </div>
  );
}

function truncateText(text: string, maxLen: number): string {
  if (text.length <= maxLen) {
    return text;
  }
  return text.slice(0, maxLen - 1) + "…";
}

function buildPrimaryInsight(runs: RunSummary[]): {
  title: string;
  reason: string;
  tone: string;
} | null {
  const failedRuns = runs.filter((run) => run.draftStatus === "failed");
  const warningRuns = runs.filter((run) => run.runStatus?.quality_summary || run.runStatus?.error_summary);
  const runningRuns = runs.filter((run) => run.draftStatus === "running" || run.draftStatus === "queued");

  if (failedRuns.length > 0) {
    return {
      title: `${failedRuns.length} 个运行批次失败`,
      reason: "查看详情排查错误摘要，修复后重新运行。",
      tone: "recommendation-item priority",
    };
  }
  if (warningRuns.length > warningRuns.filter((r) => r.draftStatus === "failed").length) {
    return {
      title: `${warningRuns.length} 个运行批次有质量警告`,
      reason: "优先复查警告项，确认是否需要调整输入或模型配置。",
      tone: "recommendation-item watch",
    };
  }
  if (runningRuns.length > 0) {
    return {
      title: `${runningRuns.length} 个运行批次正在执行`,
      reason: "关注阶段进度，完成后进入评估与报告。",
      tone: "recommendation-item safe",
    };
  }
  if (runs.length === 0) {
    return {
      title: "尚无运行数据",
      reason: "创建投递草稿开始评估。",
      tone: "recommendation-item safe",
    };
  }
  return null;
}

function buildStageSummary(completedCount: number): string {
  if (completedCount >= 6) {
    return "完成";
  }
  if (completedCount > 0) {
    return "进行中";
  }
  return "待导入";
}

function buildActivityDotClassName(status: string): string {
  if (status === "failed") {
    return "activity-dot danger";
  }
  if (status === "done") {
    return "activity-dot success";
  }
  if (status === "draft" || status === "queued") {
    return "activity-dot warning";
  }
  return "activity-dot";
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toISOString().slice(11, 16);
}
