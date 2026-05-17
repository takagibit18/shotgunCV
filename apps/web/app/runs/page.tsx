import React from "react";

import { listRuns } from "../../lib/runs";
import { AppShell } from "../AppShell";
import { RunQueue } from "../RunQueue";

export default async function RunsPage() {
  const runs = await listRuns();

  return (
    <AppShell active="queue" eyebrow="运行队列">
      <main className="app-shell operational-shell">
        <section className="page-header">
          <div>
            <p className="eyebrow">运行队列</p>
            <h1 className="page-title">本地运行工作队列</h1>
            <p className="hero-copy">集中处理所有 run 的搜索、筛选、排序、分页、详情跳转和报告入口。</p>
          </div>
        </section>

        <RunQueue runs={runs} />
      </main>
    </AppShell>
  );
}
