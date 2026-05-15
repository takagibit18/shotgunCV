import React from "react";
import Link from "next/link";

import { loadLocalConfig } from "../../lib/local-config";
import { loadSettingsOverview, type SettingsCheck, type SettingsOverview } from "../../lib/settings";
import { AppShell, Icon, MetricCard } from "../AppShell";
import { LocalConfigPanel } from "./LocalConfigPanel";

export default async function SettingsPage() {
  const overview = await loadSettingsOverview();
  const localConfig = await loadLocalConfig();

  return (
    <AppShell active="settings" eyebrow="设置">
      <main className="app-shell operational-shell">
        <section className="page-header settings-page-header">
          <div className="page-kicker-row">
            <Link href="/" className="backlink icon-link">
              <Icon name="chevron-left" />
              返回运行队列
            </Link>
            <span className="breadcrumb-text">设置 / 本地环境</span>
          </div>
          <div>
            <h1 className="page-title">本地设置与环境检查</h1>
            <p className="hero-copy">环境健康、`.env` 边界和模型参数只反映本地状态；网页不写入本地流程产物。</p>
          </div>
        </section>

        <section className="metric-card-grid settings-metric-grid" aria-label="环境健康">
          <MetricCard
            icon="folder"
            label="运行目录"
            value={overview.runsDirReadable ? "可读" : "不可读"}
            helper={overview.displayRunsDir}
            tone={overview.runsDirReadable ? "green" : "red"}
          />
          <MetricCard icon="play" label="运行数量" value={overview.runCount} helper="本地运行目录" tone="blue" />
          <MetricCard
            icon="alert-triangle"
            label="配置缺失或异常"
            value={overview.configIssueCount}
            helper="缺失或无法解析的运行配置"
            tone={overview.configIssueCount > 0 ? "orange" : "green"}
          />
          <MetricCard
            icon="shield-alert"
            label="产物解析异常"
            value={overview.artifactIssueCount}
            helper="已存在的本地 JSON 产物"
            tone={overview.artifactIssueCount > 0 ? "orange" : "green"}
          />
        </section>

        <LocalConfigPanel initialConfig={localConfig} />

        <section className="settings-grid" aria-label="本地设置摘要">
          <section className="section settings-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">.env 边界</p>
                <h2>本地路径</h2>
                <p className="section-copy">网页读取本地运行目录产物；路径已脱敏，不展示完整本机目录。</p>
              </div>
            </div>
            <dl className="settings-list">
              <SummaryRow label="运行目录来源" value={overview.runsDirSource === "env" ? "环境变量" : "默认路径"} />
              <SummaryRow label="脱敏路径" value={overview.displayRunsDir} />
              <SummaryRow label="配置快照" value={`${overview.configSnapshotCount} 个可解析`} />
              <SummaryRow label="未知模型提供商" value={`${overview.unknownProviderCount} 项`} />
            </dl>
          </section>

          <section className="section settings-panel">
            <div className="section-heading">
              <div>
              <p className="eyebrow">模型提供商</p>
                <h2>最新配置快照</h2>
                <p className="section-copy">来自最近修改且可解析的运行配置，只展示模型提供商与模型摘要。</p>
              </div>
            </div>
            {overview.latestConfig ? <LatestConfig overview={overview} /> : <EmptyConfig />}
          </section>
        </section>

        <section className="section section-flush settings-check-section">
          <div className="section-heading queue-heading">
            <div>
                <p className="eyebrow">环境健康</p>
          <h2>本地依赖与产物</h2>
                <p className="section-copy">失败项保持可读并指向下一步检查，不阻断页面。</p>
            </div>
          </div>
          <div className="settings-check-list">
            {overview.checks.map((check) => (
              <CheckRow key={check.label} check={check} />
            ))}
          </div>
          {overview.runCount === 0 && overview.runsDirReadable ? (
            <div className="empty-state settings-empty">
          <h3>暂无运行批次</h3>
          <p>当前运行目录可读，但还没有本地运行。可以先从上传页创建草稿，再进入详情页启动本地流程。</p>
              <Link href="/upload" className="primary-link">
            创建投递草稿
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
        <SummaryRow label="运行批次" value={config.runId} />
        <SummaryRow label="标签" value={config.label || "未命名"} />
        <SummaryRow label="服务地址主机" value={config.baseUrlHost} />
        <SummaryRow label="密钥环境变量" value={config.apiKeyEnv} />
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
        <SummaryRow label="文字识别提供商" value={config.inputExtraction.ocrProvider} />
        <SummaryRow label="视觉兜底提供商" value={config.inputExtraction.visionProvider} />
        <SummaryRow label="视觉兜底模型" value={config.inputExtraction.visionModel || "未指定"} />
      </dl>
    </div>
  );
}

function EmptyConfig() {
  return (
    <div className="empty-state settings-empty">
      <h3>暂无可解析配置</h3>
      <p>未找到可读取的运行配置；设置页仍会显示运行目录与基础环境检查。</p>
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
    analyzer: "分析器",
    generator: "生成器",
    judge: "评审器",
    planner: "规划器",
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
