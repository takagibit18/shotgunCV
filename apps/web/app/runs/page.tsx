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
            <h1 className="page-title">投递进度</h1>
            <p className="hero-copy">把每个投递的状态、进度和下一步动作放在同一个工作台里。</p>
          </div>
        </section>

        <RunQueue runs={runs} />
      </main>
    </AppShell>
  );
}
