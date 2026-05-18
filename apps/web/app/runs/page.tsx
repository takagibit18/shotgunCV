import React from "react";

import { listRuns } from "../../lib/runs";
import { AppShell } from "../AppShell";
import { RunQueue } from "../RunQueue";

export default async function RunsPage() {
  const runs = await listRuns();

  return (
    <AppShell active="queue" eyebrow="投递管理">
      <main className="app-shell operational-shell">
        <section className="page-header">
          <div>
            <p className="eyebrow">投递管理</p>
            <h1 className="page-title">运行队列</h1>
            <p className="hero-copy">集中查看每个投递的状态、进度和下一步动作。</p>
          </div>
        </section>

        <RunQueue runs={runs} />
      </main>
    </AppShell>
  );
}
