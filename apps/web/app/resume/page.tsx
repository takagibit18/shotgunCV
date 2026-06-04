import React from "react";
import Link from "next/link";

import { loadResumeWorkspace } from "../../lib/resume";
import { AppShell } from "../AppShell";
import { ResumeWorkspace } from "./ResumeWorkspace";

export default async function ResumePage() {
  const workspace = await loadResumeWorkspace();

  return (
    <AppShell active="resume" eyebrow="简历优化">
      <main className="app-shell operational-shell">
        <section className="page-header with-actions">
          <div>
            <h1 className="page-title">简历优化</h1>
          </div>
          <Link href="/upload" className="primary-link">
            创建投递草稿
          </Link>
        </section>

        <section className="status-strip" aria-label="简历优化总览">
          <article className="status-strip-item info">
            <span>运行批次</span>
            <strong>{workspace.summary.totalRuns}</strong>
          </article>
          <article className="status-strip-item success">
            <span>可预览简历</span>
            <strong>{workspace.summary.generatedResumeCount}</strong>
          </article>
          <article
            className={
              workspace.summary.warningRuns > 0
                ? "status-strip-item warning"
                : "status-strip-item success"
            }
          >
            <span>警告/失败</span>
            <strong>
              {workspace.summary.warningRuns + workspace.summary.failedRuns}
            </strong>
          </article>
          <article className="status-strip-item">
            <span>证据约束</span>
            <strong>{workspace.summary.constraintCount}</strong>
          </article>
        </section>

        <ResumeWorkspace rows={workspace.rows} />
      </main>
    </AppShell>
  );
}
