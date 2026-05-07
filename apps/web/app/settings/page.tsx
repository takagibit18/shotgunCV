import React from "react";
import Link from "next/link";

import { loadSettingsOverview, type SettingsCheck, type SettingsOverview } from "../../lib/settings";
import { AppShell, Icon } from "../AppShell";

export default async function SettingsPage() {
  const overview = await loadSettingsOverview();

  return (
    <AppShell active="settings" eyebrow="设置 / 环境检查" freshnessText={overview.runsDirReadable ? "本地可读" : "需要检查"}>
      <main className="app-shell operational-shell">
        <Link href="/" className="backlink">
          返回运行队列
        </Link>

        <section className="page-header detail-header">
          <div>
            <p className="eyebrow">v0.6.3 设置</p>
            <h1 className="page-title">本地设置与环境检查</h1>
            <p className="hero-copy">
              汇总本地 runs 边界、provider 快照和关键 artifacts 健康度。此页面只读取本地元数据，不保存设置、不执行 pipeline，也不显示完整密钥或 CV/JD 原文。
            </p>
          </div>
          <div className="rail-card purple">
            <div className="metric-title">
              <Icon name="settings" />
              <h3>只读排障边界</h3>
            </div>
            <p className="muted">
              provider 与模型以最新可解析 run_config.json 为准；密钥仅显示环境变量名，OpenAI-compatible endpoint 仅显示 host。
            </p>
          </div>
        </section>

        <section className="status-strip" aria-label="设置总览">
          <article className={overview.runsDirReadable ? "status-strip-item success" : "status-strip-item danger"}>
            <span>runs 目录</span>
            <strong>{overview.runsDirReadable ? "可读" : "不可读"}</strong>
          </article>
          <article className="status-strip-item info">
            <span>run 数量</span>
            <strong>{overview.runCount}</strong>
          </article>
          <article className={overview.configIssueCount > 0 ? "status-strip-item warning" : "status-strip-item success"}>
            <span>配置缺失或异常</span>
            <strong>{overview.configIssueCount}</strong>
          </article>
          <article className={overview.artifactIssueCount > 0 ? "status-strip-item warning" : "status-strip-item success"}>
            <span>artifact 解析异常</span>
            <strong>{overview.artifactIssueCount}</strong>
          </article>
        </section>

        <section className="settings-grid" aria-label="本地设置摘要">
          <section className="section settings-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">运行边界</p>
                <h2>本地路径</h2>
                <p className="section-copy">Web 读取本地 run_dir artifacts，不重新实现 pipeline 业务逻辑。</p>
              </div>
            </div>
            <dl className="settings-list">
              <SummaryRow label="runs 来源" value={overview.runsDirSource === "env" ? "SHOTGUNCV_RUNS_DIR" : "默认路径"} />
              <SummaryRow label="脱敏路径" value={overview.displayRunsDir} />
              <SummaryRow label="配置快照" value={`${overview.configSnapshotCount} 个可解析`} />
              <SummaryRow label="unknown provider" value={`${overview.unknownProviderCount} 项`} />
            </dl>
          </section>

          <section className="section settings-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Provider</p>
                <h2>最新配置快照</h2>
                <p className="section-copy">来自最近修改且可解析的 run_config.json。</p>
              </div>
            </div>
            {overview.latestConfig ? <LatestConfig overview={overview} /> : <EmptyConfig />}
          </section>
        </section>

        <section className="section section-flush settings-check-section">
          <div className="section-heading queue-heading">
            <div>
              <p className="eyebrow">环境检查</p>
              <h2>本地依赖与 artifacts</h2>
              <p className="section-copy">失败项不会导致页面崩溃，只给出可操作解释。</p>
            </div>
            <span className="status-chip info">{overview.checks.length} 项检查</span>
          </div>
          <div className="settings-check-list">
            {overview.checks.map((check) => (
              <CheckRow key={check.label} check={check} />
            ))}
          </div>
          {overview.runCount === 0 && overview.runsDirReadable ? (
            <div className="empty-state settings-empty">
              <h3>暂无 run</h3>
              <p>当前 runs 目录可读，但还没有本地 run。可以先从上传页创建草稿，再用 CLI 执行 pipeline。</p>
              <Link href="/upload" className="primary-link">
                创建草稿 run
              </Link>
            </div>
          ) : null}
        </section>
      </main>
    </AppShell>
  );
}

function LatestConfig({ overview }: { overview: SettingsOverview }) {
  const config = overview.latestConfig;
  if (!config) {
    return null;
  }
  return (
    <div className="settings-config">
      <dl className="settings-list">
        <SummaryRow label="run" value={config.runId} />
        <SummaryRow label="标签" value={config.label || "未命名"} />
        <SummaryRow label="base URL host" value={config.baseUrlHost} />
        <SummaryRow label="API key env" value={config.apiKeyEnv} />
        <SummaryRow label=".env 文件" value={config.envFile || "未指定"} />
      </dl>
      <div className="provider-grid">
        {config.providers.map((provider) => (
          <article key={provider.role} className="provider-card">
            <span>{formatRole(provider.role)}</span>
            <strong>{provider.provider}</strong>
            <small>{provider.model}</small>
          </article>
        ))}
      </div>
      <dl className="settings-list compact">
        <SummaryRow label="OCR provider" value={config.inputExtraction.ocrProvider} />
        <SummaryRow label="Vision provider" value={config.inputExtraction.visionProvider} />
        <SummaryRow label="Vision model" value={config.inputExtraction.visionModel || "未指定"} />
        <SummaryRow label="OCR languages" value={config.inputExtraction.ocrLanguages || "未指定"} />
      </dl>
    </div>
  );
}

function EmptyConfig() {
  return (
    <div className="empty-state settings-empty">
      <h3>暂无可解析配置</h3>
      <p>未找到可读取的 config/run_config.json；设置页仍会显示 runs 目录与基础环境检查。</p>
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function CheckRow({ check }: { check: SettingsCheck }) {
  return (
    <article className="settings-check-row">
      <span className={buildCheckClassName(check.status)}>{formatCheckStatus(check.status)}</span>
      <div>
        <strong>{check.label}</strong>
        <p>{check.detail}</p>
      </div>
    </article>
  );
}

function formatRole(role: string): string {
  const labels: Record<string, string> = {
    analyzer: "Analyzer",
    generator: "Generator",
    judge: "Judge",
    planner: "Planner",
  };
  return labels[role] ?? role;
}

function buildCheckClassName(status: SettingsCheck["status"]): string {
  if (status === "pass") {
    return "status-chip success";
  }
  if (status === "fail") {
    return "status-chip danger";
  }
  return "status-chip warning";
}

function formatCheckStatus(status: SettingsCheck["status"]): string {
  if (status === "pass") {
    return "通过";
  }
  if (status === "fail") {
    return "失败";
  }
  return "需检查";
}
