import React from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";

import { AppShell, Icon, MetricCard } from "../../../AppShell";
import { loadRunDetail, loadRunReport } from "../../../../lib/runs";


type PageProps = {
  params: Promise<{ runId: string }>;
};


export default async function ReportPage({ params }: PageProps) {
  const resolvedParams = await params;
  const [report, detail] = await Promise.all([
    loadRunReport(resolvedParams.runId),
    loadRunDetail(resolvedParams.runId),
  ]);
  const reportSummary = buildReportSummary(detail);
  const reportTitle = detail.label || reportSummary.topTitle || "评估报告";

  return (
    <AppShell active="evaluation" eyebrow="评估结果 / 报告" freshnessText="本地数据">
      <main className="app-shell operational-shell">
        <section className="page-header report-page-header">
          <div className="page-kicker-row">
            <Link href={`/runs/${resolvedParams.runId}`} className="backlink icon-link">
              <Icon name="chevron-left" />
              返回运行详情
            </Link>
            <span className="breadcrumb-text">评估结果 / 报告</span>
          </div>
          <div>
            <p className="eyebrow">评估报告 · 投递复盘</p>
            <h1 className="page-title">{reportTitle}</h1>
            <p className="hero-copy">先读投递结论、关键证据和面试准备；系统字段已转换为可读判断。</p>
          </div>
        </section>

        <section className="metric-card-grid report-action-grid" aria-label="报告导航与来源摘要">
          <MetricCard
            icon="document"
            label="报告目录"
            value="决策摘要 / 原始报告"
            helper="结构化结论优先，原文用于追溯"
            tone="blue"
          />
          <MetricCard
            icon="briefcase"
            label="推荐岗位"
            value={reportSummary.topTitle}
            helper="来自评分与投递策略快照"
            tone="green"
          />
          <MetricCard
            icon="layers"
            label="依据完整度"
            value={reportSummary.sourceBasis}
            helper="来自评分、证据和投递建议"
            tone="purple"
          />
        </section>

        <section className="section report-summary report-decision-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">结构化摘要</p>
            <h2>投递决策摘要</h2>
            <p className="section-copy">网页只整理已生成产物的展示顺序，不重新解释评分、门槛或投递建议。</p>
          </div>
        </div>
        <div className="report-summary-grid">
          <SummaryCard icon="shield-check" title="推荐结论" items={reportSummary.recommendations} />
          <SummaryCard icon="link" title="关键证据" items={reportSummary.evidence} />
          <SummaryCard icon="edit" title="面试前突击内容 / 改进重点" items={reportSummary.interviewPrep} />
        </div>
      </section>

        <section className="section report-shell report-source-panel">
          <details className="source-details">
            <summary>
              <span>
                <Icon name="file" />
                原始报告
              </span>
              <small>可追溯来源内容</small>
            </summary>
            {report ? (
              <div className="markdown">
                <ReactMarkdown>{sanitizeReportMarkdown(report.markdown)}</ReactMarkdown>
              </div>
            ) : (
              <div className="empty">报告尚未生成。</div>
            )}
          </details>
        </section>
      </main>
    </AppShell>
  );
}


type SummaryItem = {
  text: string;
  source: string;
};

function SummaryCard({ icon, title, items }: { icon: Parameters<typeof Icon>[0]["name"]; title: string; items: SummaryItem[] }) {
  const visibleItems = items.slice(0, 5);
  const hiddenCount = Math.max(0, items.length - visibleItems.length);
  return (
    <article className="report-summary-card">
      <h3>
        <span className="semantic-icon blue" aria-hidden="true">
          <Icon name={icon} />
        </span>
        {title}
      </h3>
      <ul>
        {visibleItems.length > 0 ? (
          visibleItems.map((item) => (
            <li key={`${item.source}-${item.text}`}>
              <span>{item.text}</span>
            </li>
          ))
        ) : (
          <li>{"当前运行尚未提供可结构化展示的内容。"}</li>
        )}
        {hiddenCount > 0 ? (
          <li className="report-more-item">
          <span>另有 {hiddenCount} 条来源内容保留在原始报告与本地产物中。</span>
          </li>
        ) : null}
      </ul>
    </article>
  );
}


type DetailForReport = Awaited<ReturnType<typeof loadRunDetail>>;


function buildReportSummary(detail: DetailForReport) {
  const topVariant = detail.evaluate.topVariants
    .slice()
    .sort((left, right) => right.overallScore - left.overallScore)[0];
  const topStrategy = topVariant
    ? detail.plan.strategies.find((strategy) => strategy.jd_id === topVariant.jdId)
    : detail.plan.strategies[0];
  const topExplanation = topVariant
    ? detail.evaluate.explanations.find(
        (explanation) => explanation.jd_id === topVariant.jdId && explanation.variant_id === topVariant.variantId,
      )
    : detail.evaluate.explanations[0];
  const topGapMap = topVariant
    ? detail.evaluate.gapMaps.find((gapMap) => gapMap.jd_id === topVariant.jdId)
    : detail.evaluate.gapMaps[0];
  const gapItems = Array.isArray(topGapMap?.items) ? topGapMap.items : [];
  const strategyReason = topStrategy?.reason_summary ? `。${formatUserText(topStrategy.reason_summary)}` : "";

  return {
    topTitle: topVariant?.title ?? "暂无推荐岗位",
    sourceBasis: uniqueItems([
      topVariant ? { text: "评分快照", source: "评分产物" } : null,
      topStrategy ? { text: "投递策略", source: "策略产物" } : null,
      topExplanation ? { text: "证据解释", source: "证据产物" } : null,
      topGapMap ? { text: "差距分析", source: "差距产物" } : null,
    ])
      .map((item) => item.text)
      .join(" / ") || "暂无依据",
    recommendations: uniqueItems([
      topVariant
        ? { text: `优先投递 ${topVariant.title}，综合得分 ${Math.round(topVariant.overallScore * 100)}%。`, source: "评分产物" }
        : null,
      topStrategy ? { text: `投递建议：${formatDecision(topStrategy.apply_decision)}${strategyReason}`, source: "策略产物" } : null,
    ]),
    evidence: uniqueItems([
      ...toSummaryItems(topExplanation?.evidence_refs, "证据引用"),
      ...toSummaryItems(topExplanation?.positive_signals, "正向信号"),
      ...toSummaryItems(topStrategy?.decision_drivers, "决策依据"),
      ...toSummaryItems(topVariant?.topReasons, "评估摘要"),
    ]),
    interviewPrep: uniqueItems([
      ...toSummaryItems(topStrategy?.catch_up_notes, "补强建议"),
      ...toSummaryItems(topStrategy?.interview_prep_points, "面试准备"),
      ...toSummaryItems(topStrategy?.recommended_actions, "推荐动作"),
      ...gapItems.flatMap((item) => [
        ...toSummaryItems(item.catch_up_concepts, "补强概念"),
        ...toSummaryItems(item.weak_points, "薄弱点"),
      ]),
      ...toSummaryItems(topExplanation?.risk_flags, "风险标记"),
    ]),
  };
}


function toSummaryItems(value: unknown, source: string): SummaryItem[] {
  return Array.isArray(value)
    ? value
        .filter((text): text is string => typeof text === "string" && text.trim().length > 0)
        .map((text) => ({ text: formatUserText(text), source }))
    : [];
}


function uniqueItems(items: Array<SummaryItem | null>): SummaryItem[] {
  const seen = new Set<string>();
  const results: SummaryItem[] = [];
  items.forEach((item) => {
    const text = item?.text.trim();
    if (!item || !text || seen.has(text)) {
      return;
    }
    seen.add(text);
    results.push({ text: formatUserText(text), source: item.source });
  });
  return results;
}


function sanitizeReportMarkdown(markdown: string): string {
  return markdown.replace(/\b[a-z]+(?:_[a-z0-9]+)+\b/g, (token) => formatUserText(token));
}


function formatDecision(value: string): string {
  const labels: Record<string, string> = {
    apply: "建议投递",
    manual_review: "人工复核",
    hold: "暂缓",
    skip: "跳过",
    review: "复核后决定",
  };
  return labels[value] ?? formatUserText(value);
}


function formatUserText(value: string): string {
  const labels: Record<string, string> = {
    hard_gate_missing: "硬性要求缺少证据",
    needs_review: "需要复核",
    manual_review: "人工复核",
    final_overall_score: "综合得分",
    risk_score: "风险",
    gate_status: "门槛状态",
    apply_decision: "投递建议",
  };
  return value.replace(/\b[a-z]+(?:_[a-z0-9]+)+\b/g, (token) => labels[token] ?? token.replace(/_/g, " "));
}
