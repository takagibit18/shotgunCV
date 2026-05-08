import React from "react";

import { getRunsDir, listRuns } from "../lib/runs";
import { AppShell, Icon } from "./AppShell";
import { RunQueue } from "./RunQueue";

export default async function HomePage() {
  const runs = await listRuns();
  const totalRuns = runs.length;
  const completedStageCount = runs.reduce((sum, run) => sum + run.completedStages.length, 0);
  const activeRuns = runs.filter((run) => run.draftStatus === "running" || run.draftStatus === "queued").length;
  const warningRuns = runs.filter((run) => run.runStatus?.quality_summary || run.runStatus?.error_summary).length;
  const doneRuns = runs.filter((run) => run.draftStatus === "done").length;
  const completionRate = totalRuns === 0 ? 0 : Math.round((doneRuns / totalRuns) * 100);
  const runsDir = getRunsDir();
  const recentRuns = runs.slice(0, 4);
  const freshnessText = formatFreshness(runs[0]?.lastModified);
  const insightText =
    runs.length === 0
      ? "暂无历史 run，可先创建草稿并运行 pipeline。"
      : warningRuns > 0
        ? `当前有 ${warningRuns} 个批次包含质量或失败提示，建议优先查看风险解释与证据覆盖。`
        : `近 ${Math.min(runs.length, 7)} 个批次未发现阻断摘要，可继续检查评分证据后投递。`;

  return (
    <AppShell active="dashboard" freshnessText={freshnessText}>
      <main className="app-shell operational-shell">
        <section className="page-header">
          <div>
            <p className="eyebrow">AI Resume Ops 工作台</p>
            <h1>运行队列与投递决策</h1>
            <p className="hero-copy">
              面向本地用户的 pipeline-first 工作台，集中查看阶段产物、质量警告、评分证据、风险解释和下一步动作。
            </p>
          </div>
        </section>

        <div className="workspace-grid">
          <div className="workspace-main">
            <section className="metric-card-grid" aria-label="运行总览">
              <MetricTile value={totalRuns} label="运行批次" delta={buildDeltaText(totalRuns)} tone="info" />
              <MetricTile value={activeRuns} label="进行中" delta={activeRuns > 0 ? "需关注" : "无排队"} tone="success" />
              <MetricTile value={warningRuns} label="警告/失败" delta={warningRuns > 0 ? "优先处理" : "暂无阻断"} tone="warning" />
              <MetricTile value={completedStageCount} label="已完成阶段" delta={`${doneRuns} 个完成 run`} tone="purple" />
            </section>

            <section className="trend-strip" aria-label="趋势概览">
              <div>
                <p className="eyebrow">趋势概览</p>
                <h2>批次容量与健康度</h2>
              </div>
              <TrendMetric label="Run 数" value={totalRuns} />
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
                <span className="status-chip info">查看全部</span>
              </div>
              <div className="activity-list">
                {recentRuns.length > 0 ? (
                  recentRuns.map((run) => (
                    <div className="activity-item" key={run.runId}>
                      <span className={buildActivityDotClassName(run.draftStatus)} />
                      <span className="activity-meta">
                        <strong>{run.label || run.runId}</strong>
                        <small>
                          阶段 {buildStageSummary(run.completedStages.length)} · {STATUS_LABELS[run.draftStatus] ?? run.draftStatus}
                        </small>
                      </span>
                      <span className="muted">{formatTime(run.lastModified)}</span>
                    </div>
                  ))
                ) : (
                  <p className="muted">暂无 run 活动。</p>
                )}
              </div>
            </section>

            <section className="rail-card purple">
              <div className="metric-title">
                <Icon name="sparkle" />
                <h3>AI 洞察</h3>
              </div>
              <p className="muted">{insightText}</p>
              <div className="insight-list">
                <div className="insight-item">
                  <Icon name="check-square" />
                  <span>建议优先审查岗位匹配、风险解释、证据引用等维度，以提升投递把握。</span>
                </div>
              </div>
            </section>
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

const STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  queued: "排队中",
  running: "运行中",
  done: "已完成",
  failed: "失败",
  "ingest-ready": "导入就绪",
};

function MetricTile({
  value,
  label,
  delta,
  tone,
}: {
  value: number;
  label: string;
  delta: string;
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
        <span className="metric-delta">较昨日 {delta}</span>
      </span>
    </div>
  );
}

function buildDeltaText(totalRuns: number): string {
  return totalRuns > 0 ? `+${Math.min(totalRuns, 2)}` : "持平";
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

function formatFreshness(value?: string): string {
  if (!value) {
    return "暂无数据";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "本地数据";
  }
  return formatTime(value) || "本地数据";
}
