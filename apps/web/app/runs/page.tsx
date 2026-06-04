import React from "react";
import Link from "next/link";

import { STATUS_LABELS } from "../../lib/labels";
import { listRuns, type RunSummary } from "../../lib/runs";
import { AppShell, Icon, MetricCard } from "../AppShell";
import { RunQueue } from "../RunQueue";

const STAGE_TOTAL = 6;

export default async function RunsPage() {
  const runs = await listRuns();
  const totalRuns = runs.length;
  const activeRuns = runs.filter((run) => run.draftStatus === "running" || run.draftStatus === "queued").length;
  const draftRuns = runs.filter((run) => run.draftStatus === "draft" || run.draftStatus === "ingest-ready").length;
  const failedRuns = runs.filter((run) => run.draftStatus === "failed" || run.runStatus?.error_summary).length;
  const warningRuns = runs.filter((run) => run.runStatus?.quality_summary).length;
  const resumeReadyRuns = runs.filter((run) => run.completedStages.includes("generate")).length;
  const reportReadyRuns = runs.filter((run) => run.completedStages.includes("report")).length;
  const averageProgress =
    totalRuns === 0
      ? 0
      : Math.round((runs.reduce((sum, run) => sum + run.completedStages.length, 0) / (totalRuns * STAGE_TOTAL)) * 100);
  const priorityRuns = buildPriorityRuns(runs).slice(0, 4);
  const latestRun = runs[0];

  return (
    <AppShell active="queue" eyebrow="投递管理" freshnessText="本地任务数据">
      <main className="app-shell operational-shell">
        <section className="page-header with-actions">
          <div>
            <p className="eyebrow">内部工作台</p>
            <h1 className="page-title">运行队列</h1>
            <p className="hero-copy">
              这里是进入产品后的真实工作台：集中查看每个投递的状态，处理简历生成进度、失败风险和下一步动作。首页继续承担展示与引导职责。
            </p>
          </div>
          <div className="row-actions">
            <Link href="/upload" className="primary-link icon-link dashboard-primary-cta">
              <Icon name="image-upload" />
              开始新投递
            </Link>
            <Link href="/resume" className="secondary-link icon-link">
              <Icon name="document" />
              简历交付
            </Link>
          </div>
        </section>

        <section className="metric-card-grid" aria-label="工作台关键指标">
          <MetricCard icon="alert-triangle" label="待处理投递" value={failedRuns + warningRuns + draftRuns} helper="失败、提醒与草稿优先进入队列" tone="orange" />
          <MetricCard icon="play" label="运行中" value={activeRuns} helper="本地流程正在推进或排队" tone="blue" />
          <MetricCard icon="document" label="可导出简历" value={resumeReadyRuns} helper="已生成简历变体，后续补齐导出闭环" tone="green" />
          <MetricCard icon="stats" label="全部投递" value={totalRuns} helper={`平均阶段完成度 ${averageProgress}%`} tone="neutral" />
        </section>

        <section className="workspace-grid dashboard-workbench-grid">
          <div className="workspace-main">
            <section className="section dashboard-priority-panel" aria-labelledby="priority-title">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">优先处理</p>
                  <h2 id="priority-title">下一步动作</h2>
                  <p className="section-copy">先处理失败、质量提醒和未启动草稿，再复核已生成结果。</p>
                </div>
                <Link href={latestRun ? `/runs/${latestRun.runId}` : "/upload"} className="secondary-link icon-link">
                  <Icon name={latestRun ? "eye" : "image-upload"} />
                  {latestRun ? "继续处理" : "创建投递草稿"}
                </Link>
              </div>

              {priorityRuns.length > 0 ? (
                <div className="dashboard-priority-list">
                  {priorityRuns.map((run) => (
                    <article className="dashboard-priority-row" key={run.runId}>
                      <div>
                        <strong>{run.label || run.runId}</strong>
                        <span>{getRunActionHint(run)}</span>
                      </div>
                      <span className={buildStatusClassName(run)}>{STATUS_LABELS[run.draftStatus] ?? run.draftStatus}</span>
                      <Link href={`/runs/${run.runId}`} className="secondary-link icon-link">
                        <Icon name="chevron-right" />
                        处理
                      </Link>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="empty-state compact">
                  <h3>暂无投递</h3>
                  <p>创建投递草稿后，工作台会把下一步动作、风险和简历交付状态集中到这里。</p>
                  <Link href="/upload" className="primary-link">
                    创建投递草稿
                  </Link>
                </div>
              )}
            </section>

            <RunQueue runs={runs} />
          </div>

          <aside className="insight-rail" aria-label="工作台侧栏">
            <section className="rail-card dashboard-rail-card">
              <div className="rail-card-heading">
                <span className="semantic-icon green">
                  <Icon name="document" />
                </span>
                <div>
                  <h3>简历交付</h3>
                  <p className="muted">真实生成与导出闭环是后续版本的主线。</p>
                </div>
              </div>
              <div className="dashboard-rail-stats">
                <span>
                  <strong>{resumeReadyRuns}</strong>
                  已生成
                </span>
                <span>
                  <strong>{reportReadyRuns}</strong>
                  有报告
                </span>
              </div>
              <Link href="/resume" className="secondary-link icon-link">
                <Icon name="document" />
                查看简历工作台
              </Link>
            </section>

            <section className="rail-card dashboard-rail-card">
              <div className="rail-card-heading">
                <span className="semantic-icon orange">
                  <Icon name="shield-alert" />
                </span>
                <div>
                  <h3>风险复核</h3>
                  <p className="muted">先稳住产物可信度，检索增强等性能强化暂缓。</p>
                </div>
              </div>
              <div className="dashboard-check-list">
                <span>失败任务：{failedRuns}</span>
                <span>质量提醒：{warningRuns}</span>
                <span>待启动草稿：{draftRuns}</span>
              </div>
            </section>

            <section className="rail-card dashboard-rail-card purple">
              <div className="rail-card-heading">
                <span className="semantic-icon purple">
                  <Icon name="sparkle" />
                </span>
                <div>
                  <h3>v0.9 工作台</h3>
                  <p className="muted">展示页保持对外叙事，内部页面承接真实处理、复核和交付动作。</p>
                </div>
              </div>
            </section>
          </aside>
        </section>
      </main>
    </AppShell>
  );
}

function buildPriorityRuns(runs: RunSummary[]): RunSummary[] {
  return [...runs].sort((left, right) => getPriorityWeight(right) - getPriorityWeight(left) || right.lastModified.localeCompare(left.lastModified));
}

function getPriorityWeight(run: RunSummary): number {
  if (run.draftStatus === "failed" || run.runStatus?.error_summary) {
    return 5;
  }
  if (run.runStatus?.quality_summary) {
    return 4;
  }
  if (run.draftStatus === "draft" || run.draftStatus === "ingest-ready") {
    return 3;
  }
  if (run.draftStatus === "running" || run.draftStatus === "queued") {
    return 2;
  }
  return run.completedStages.includes("generate") ? 1 : 0;
}

function getRunActionHint(run: RunSummary): string {
  if (run.runStatus?.error_summary) {
    return run.runStatus.error_summary;
  }
  if (run.runStatus?.quality_summary) {
    return run.runStatus.quality_summary;
  }
  if (run.draftStatus === "draft" || run.draftStatus === "ingest-ready") {
    return "确认输入后启动本地流程";
  }
  if (run.draftStatus === "running" || run.draftStatus === "queued") {
    return "查看最新阶段进度";
  }
  if (run.completedStages.includes("generate")) {
    return "复核已生成简历变体";
  }
  return `最近更新 ${formatDate(run.lastModified)}`;
}

function buildStatusClassName(run: RunSummary): string {
  if (run.draftStatus === "failed" || run.runStatus?.error_summary) {
    return "status-chip danger";
  }
  if (run.runStatus?.quality_summary) {
    return "status-chip warning";
  }
  if (run.draftStatus === "running" || run.draftStatus === "queued") {
    return "status-chip info";
  }
  if (run.draftStatus === "done") {
    return "status-chip success";
  }
  return "status-chip";
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toISOString().slice(0, 10);
}
