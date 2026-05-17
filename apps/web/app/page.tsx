import React from "react";
import Link from "next/link";

import { listRuns, type RunSummary } from "../lib/runs";
import { AppShell, Icon } from "./AppShell";
import { HomeOnboardingGuide } from "./HomeOnboardingGuide";
import { RunQueue } from "./RunQueue";

const STAGE_TOTAL = 6;

export default async function HomePage() {
  const runs = await listRuns();
  const totalRuns = runs.length;
  const activeRuns = runs.filter((run) => run.draftStatus === "running" || run.draftStatus === "queued").length;
  const draftRuns = runs.filter((run) => run.draftStatus === "draft" || run.draftStatus === "ingest-ready").length;
  const warningRuns = runs.filter((run) => run.runStatus?.quality_summary || run.runStatus?.error_summary).length;
  const doneRuns = runs.filter((run) => run.draftStatus === "done").length;
  const completionRate = totalRuns === 0 ? 0 : Math.round((doneRuns / totalRuns) * 100);
  const stageCoverage =
    totalRuns === 0
      ? 0
      : Math.round((runs.reduce((sum, run) => sum + run.completedStages.length, 0) / (totalRuns * STAGE_TOTAL)) * 100);
  const recentRuns = runs.slice(0, 4);
  const primaryInsight = buildPrimaryInsight(runs);

  return (
    <AppShell active="dashboard" eyebrow="AI Resume Ops 工作台">
      <main className="app-shell operational-shell v08-home">
        <section className="creative-hero" aria-labelledby="home-hero-title">
          <div className="hero-announcement">
            <Icon name="sparkle" />
            v0.8 本地投递工作台重构
          </div>
          <div className="hero-copy-block">
            <h1 id="home-hero-title">从岗位输入到证据化简历策略，一屏掌控</h1>
            <p>
              ShotgunCV Web 保持本地优先：只展示 run 产物、评分证据、风险提示和下一步动作，不暴露原始 CV/JD 正文，只聚焦当前 pipeline 工作流。
            </p>
          </div>
          <div className="hero-actions">
            <Link href="/upload" className="primary-link hero-primary-action">
              创建草稿 run
            </Link>
            <Link href="/resume" className="secondary-link hero-secondary-action">
              查看简历优化
            </Link>
          </div>
          <div className="hero-proof-strip" aria-label="工作台状态摘要">
            <HeroProof label="Run 批次" value={totalRuns} helper="本地 runs 目录" />
            <HeroProof label="完成率" value={`${completionRate}%`} helper={`${doneRuns} 个已出报告`} />
            <HeroProof label="阶段覆盖" value={`${stageCoverage}%`} helper="ingest 到 report" />
          </div>
          <ProductPreview
            totalRuns={totalRuns}
            activeRuns={activeRuns}
            warningRuns={warningRuns}
            draftRuns={draftRuns}
            recentRuns={recentRuns}
          />
        </section>

        <HomeOnboardingGuide totalRuns={totalRuns} draftRuns={draftRuns} activeRuns={activeRuns} />

        <div className="workspace-grid v08-workspace">
          <div className="workspace-main">
            <section className="metric-card-grid" aria-label="运行总览">
              <MetricTile value={totalRuns} label="运行批次" tone="info" helper="所有本地 run" />
              <MetricTile value={activeRuns} label="进行中" tone="success" helper="queued / running" />
              <MetricTile value={warningRuns} label="警告/失败" tone="warning" helper="需复核项" />
              <MetricTile value={doneRuns} label="已完成" tone="purple" helper="report 已生成" />
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
                  <p className="eyebrow">最近动态</p>
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
                          阶段 {buildStageSummary(run.completedStages.length)} /{" "}
                          {STATUS_LABELS[run.draftStatus] ?? run.draftStatus}
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

            {primaryInsight ? (
              <section className="rail-card purple">
                <div className="section-heading">
                  <div>
                    <p className="eyebrow">AI 洞察</p>
                    <h3>下一步建议</h3>
                  </div>
                </div>
                <div className="recommendation-list">
                  <div className={primaryInsight.tone}>
                    <Icon name="sparkle" />
                    <div>
                      <strong>{primaryInsight.title}</strong>
                      <p>{primaryInsight.reason}</p>
                    </div>
                  </div>
                </div>
              </section>
            ) : null}
          </aside>
        </div>
      </main>
    </AppShell>
  );
}

function ProductPreview({
  totalRuns,
  activeRuns,
  warningRuns,
  draftRuns,
  recentRuns,
}: {
  totalRuns: number;
  activeRuns: number;
  warningRuns: number;
  draftRuns: number;
  recentRuns: RunSummary[];
}) {
  const previewRows = recentRuns.length > 0 ? recentRuns.slice(0, 3) : buildPreviewFallbackRows();

  return (
    <div className="product-preview-frame" aria-label="ShotgunCV 工作台预览">
      <div className="preview-browser-bar">
        <span className="preview-dot red" />
        <span className="preview-dot yellow" />
        <span className="preview-dot green" />
        <strong>shotguncv.local / runs</strong>
      </div>
      <div className="preview-grid">
        <div className="preview-panel preview-overview">
          <span className="preview-label">Pipeline health</span>
          <strong>{totalRuns === 0 ? "等待首个 run" : `${totalRuns} 个 run 已接入`}</strong>
          <div className="preview-stage-line" aria-hidden="true">
            {["ingest", "analyze", "generate", "evaluate", "plan", "report"].map((stage, index) => (
              <span key={stage} className={index < Math.max(1, Math.min(6, totalRuns + activeRuns)) ? "active" : ""} />
            ))}
          </div>
          <div className="preview-stat-grid">
            <PreviewStat label="草稿" value={draftRuns} tone="neutral" />
            <PreviewStat label="运行中" value={activeRuns} tone="good" />
            <PreviewStat label="风险" value={warningRuns} tone={warningRuns > 0 ? "warn" : "good"} />
          </div>
        </div>

        <div className="preview-panel preview-queue">
          <div className="preview-row header">
            <span>Run</span>
            <span>状态</span>
            <span>动作</span>
          </div>
          {previewRows.map((run) => (
            <div className="preview-row" key={run.runId}>
              <span>
                <strong>{run.label || run.runId}</strong>
                <small>{truncateText(run.runId, 22)}</small>
              </span>
              <span className={buildStatusClassName(run.draftStatus)}>
                {STATUS_LABELS[run.draftStatus] ?? run.draftStatus}
              </span>
              <span className="preview-action">检查证据</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function HomeMetric({
  label,
  value,
  helper,
}: {
  label: string;
  value: number | string;
  helper: string;
}) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{helper}</small>
    </div>
  );
}

function HeroProof({ label, value, helper }: { label: string; value: number | string; helper: string }) {
  return <HomeMetric label={label} value={value} helper={helper} />;
}

function PreviewStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "good" | "warn" | "neutral";
}) {
  return (
    <span className={`preview-stat ${tone}`}>
      <small>{label}</small>
      <strong>{value}</strong>
    </span>
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
  tone,
  helper,
}: {
  value: number;
  label: string;
  tone: "info" | "success" | "warning" | "purple";
  helper: string;
}) {
  return (
    <div className="metric-tile">
      <span className={`metric-icon ${tone === "info" ? "" : tone}`}>
        <Icon name={tone === "warning" ? "bell" : tone === "purple" ? "check-square" : "list"} />
      </span>
      <span className="metric-body">
        <span className="metric-label">{label}</span>
        <span className="metric-value">{value}</span>
        <span className="metric-helper">{helper}</span>
      </span>
    </div>
  );
}

function truncateText(text: string, maxLen: number): string {
  if (text.length <= maxLen) {
    return text;
  }
  return text.slice(0, maxLen - 1) + "...";
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
      title: `${failedRuns.length} 个 run 运行失败`,
      reason: "查看详情中的错误摘要和日志事件，修复输入或配置后再重跑 pipeline。",
      tone: "recommendation-item priority",
    };
  }
  if (warningRuns.length > warningRuns.filter((run) => run.draftStatus === "failed").length) {
    return {
      title: `${warningRuns.length} 个 run 有质量警告`,
      reason: "优先复查质量警告、缺失证据和风险项，确认是否需要补充输入或调整模型配置。",
      tone: "recommendation-item watch",
    };
  }
  if (runningRuns.length > 0) {
    return {
      title: `${runningRuns.length} 个 run 正在执行`,
      reason: "关注阶段进度，完成后进入评估结果和报告页面复核证据链。",
      tone: "recommendation-item safe",
    };
  }
  if (runs.length === 0) {
    return {
      title: "尚无运行数据",
      reason: "从创建草稿 run 开始，Web 会记录元数据并给出后续本地命令。",
      tone: "recommendation-item safe",
    };
  }
  return null;
}

function buildPreviewFallbackRows(): RunSummary[] {
  return [
    {
      runId: "draft-preview",
      label: "创建草稿后显示在这里",
      draftStatus: "draft",
      completedStages: [],
      lastModified: new Date("2026-05-17T08:00:00.000Z").toISOString(),
      analyzerProvider: "deterministic",
      generatorProvider: "openai",
      judgeProvider: "openai",
      plannerProvider: "openai",
      runStatus: null,
      stageStatuses: [],
      timeline: [],
      draft: null,
    },
  ];
}

function buildStageSummary(completedCount: number): string {
  if (completedCount >= STAGE_TOTAL) {
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

function buildStatusClassName(status: string): string {
  if (status === "failed") {
    return "status-chip danger";
  }
  if (status === "done") {
    return "status-chip success";
  }
  if (status === "running" || status === "queued") {
    return "status-chip info";
  }
  return "status-chip";
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toISOString().slice(11, 16);
}
