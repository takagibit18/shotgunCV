import React from "react";
import Link from "next/link";

import { loadResumeWorkspace, type ResumeWorkspaceRow } from "../../lib/resume";
import { AppShell, Icon } from "../AppShell";

export default async function ResumePage() {
  const workspace = await loadResumeWorkspace();
  const freshnessText = formatFreshness(workspace.rows[0]?.lastModified);

  return (
    <AppShell active="resume" eyebrow="简历优化 / Artifact 工作台" freshnessText={freshnessText}>
      <main className="app-shell operational-shell">
        <section className="page-header with-actions">
          <div>
            <p className="eyebrow">v0.6.4 简历优化</p>
            <h1 className="page-title">简历优化工作台</h1>
            <p className="hero-copy">
              聚合本地 run 的简历版本、证据约束、投递前检查和下一步动作；本页只读取 artifacts，不生成或改写 pipeline 产物。
            </p>
          </div>
          <Link href="/upload" className="primary-link">
            创建草稿 run
          </Link>
        </section>

        <section className="status-strip" aria-label="简历优化总览">
          <article className="status-strip-item info">
            <span>Run 批次</span>
            <strong>{workspace.summary.totalRuns}</strong>
          </article>
          <article className="status-strip-item success">
            <span>简历版本</span>
            <strong>{workspace.summary.variantCount}</strong>
          </article>
          <article className={workspace.summary.warningRuns > 0 ? "status-strip-item warning" : "status-strip-item success"}>
            <span>Warning/Failed</span>
            <strong>{workspace.summary.warningRuns + workspace.summary.failedRuns}</strong>
          </article>
          <article className="status-strip-item">
            <span>证据约束</span>
            <strong>{workspace.summary.constraintCount}</strong>
          </article>
        </section>

        {workspace.rows.length === 0 ? (
          <section className="empty-state">
            <h3>暂无简历优化 run</h3>
            <p>先创建草稿 run，完成 pipeline 后这里会展示版本摘要、证据约束和投递前检查。</p>
            <Link href="/upload" className="primary-link">
              创建草稿 run
            </Link>
          </section>
        ) : (
          <section className="resume-workspace" aria-label="简历优化 run 列表">
            {workspace.rows.map((row) => (
              <ResumeWorkspaceCard key={row.runId} row={row} />
            ))}
          </section>
        )}
      </main>
    </AppShell>
  );
}

function ResumeWorkspaceCard({ row }: { row: ResumeWorkspaceRow }) {
  const firstVariant = row.variants[0];
  const visibleConstraints = row.constraints.slice(0, 3);
  return (
    <article className="section resume-card">
      <div className="resume-card-header">
        <div>
          <p className="eyebrow">{formatStatus(row.status)} · {row.artifactMode}</p>
          <h2>{row.label}</h2>
          <p className="mono">{row.runId}</p>
        </div>
        <div className="row-actions">
          <Link href={row.detailHref} className="secondary-link">
            详情
          </Link>
          {row.reportHref ? (
            <Link href={row.reportHref} className="secondary-link">
              报告
            </Link>
          ) : (
            <Link href={row.uploadHref} className="secondary-link">
              创建草稿
            </Link>
          )}
        </div>
      </div>

      <div className="resume-card-grid">
        <section className="resume-panel">
          <div className="metric-title">
            <Icon name="document" />
            <h3>版本摘要</h3>
          </div>
          {firstVariant ? (
            <>
              <strong>{firstVariant.variantDisplayName}</strong>
              <span className="mono">{firstVariant.variantId}</span>
              <p>{firstVariant.summary}</p>
              <small className="muted">{firstVariant.sourceLabel}</small>
              <div className="pill-row compact">
                {firstVariant.targetJdLabels.map((label) => (
                  <span key={label} className="pill">
                    {label}
                  </span>
                ))}
              </div>
            </>
          ) : (
            <p className="muted">当前 run 尚未生成 `resume_variants.json`，进入详情页运行后续阶段。</p>
          )}
        </section>

        <section className="resume-panel">
          <h3>改写边界</h3>
          <BoundaryList title="可安全改写" items={firstVariant?.safeRewriteItems ?? []} />
          <BoundaryList title="待核实模拟补强" items={firstVariant?.simulatedSupplementItems ?? []} />
          <BoundaryList title="禁止编造缺口" items={firstVariant?.forbiddenGapItems ?? []} />
          <small className="muted">来源：variant</small>
        </section>

        <section className="resume-panel">
          <h3>证据约束</h3>
          {visibleConstraints.length > 0 ? (
            <div className="resume-constraint-list">
              {visibleConstraints.map((constraint) => (
                <div key={`${constraint.jdId}-${constraint.requirementText}`} className="resume-constraint-item">
                  <span className={buildConstraintClassName(constraint.category)}>{constraint.category}</span>
                  <p>{constraint.requirementText}</p>
                  <small className="muted">{constraint.sourceLabel}</small>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">旧版产物缺少 requirement matrix 或 preflight gate，按 legacy 状态降级展示。</p>
          )}
        </section>

        <section className="resume-panel">
          <h3>投递前检查</h3>
          <dl className="settings-list compact">
            <div>
              <dt>Gate</dt>
              <dd>{formatGateStatus(row.preflightStatus)}</dd>
            </div>
            <div>
              <dt>下一步</dt>
              <dd>{row.nextAction}</dd>
            </div>
            <div>
              <dt>来源</dt>
              <dd>{row.sourceLabel}</dd>
            </div>
          </dl>
          {row.warningText ? <p className="risk-line">{row.warningText}</p> : <p className="muted">暂无阻断风险。</p>}
        </section>
      </div>
    </article>
  );
}

function BoundaryList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="resume-boundary-group">
      <strong>{title}</strong>
      {items.length > 0 ? (
        <ul>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">当前 artifact 未提供该类条目。</p>
      )}
    </div>
  );
}

function formatFreshness(value?: string): string {
  if (!value) {
    return "暂无数据";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "本地数据";
  }
  return date.toISOString().slice(11, 16);
}

function formatStatus(status: string): string {
  const labels: Record<string, string> = {
    draft: "草稿",
    queued: "排队中",
    running: "运行中",
    done: "已完成",
    failed: "失败",
    "ingest-ready": "导入就绪",
  };
  return labels[status] ?? status;
}

function formatGateStatus(status: string): string {
  const labels: Record<string, string> = {
    pass: "通过",
    blocked: "阻断",
    needs_review: "需复核",
    legacy: "历史产物",
  };
  return labels[status] ?? status;
}

function buildConstraintClassName(category: string): string {
  if (category === "禁止编造缺口") {
    return "status-chip danger";
  }
  if (category === "待核实模拟补强") {
    return "status-chip warning";
  }
  return "status-chip success";
}
