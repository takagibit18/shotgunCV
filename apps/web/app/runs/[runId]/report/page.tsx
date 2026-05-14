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
            <p className="eyebrow">运行报告 · 投递复盘</p>
            <h1 className="page-title">{resolvedParams.runId}</h1>
            <p className="hero-copy">先读投递结论、证据和面试/改进重点；原始 Markdown 保留为可追溯来源。</p>
          </div>
        </section>

        <section className="metric-card-grid report-action-grid" aria-label="报告导航与来源摘要">
          <MetricCard
            icon="document"
            label="报告目录"
            value="决策摘要 / 原始 Markdown"
            helper="结构化结论优先，原文用于追溯"
            tone="blue"
          />
          <MetricCard
            icon="briefcase"
            label="推荐 JD"
            value={reportSummary.topTitle}
            helper="来自 scorecard 与 strategy 快照"
            tone="green"
          />
          <MetricCard
            icon="layers"
            label="引用 / 来源依据"
            value={reportSummary.sourceBasis}
            helper="每条摘要保留来源标签"
            tone="purple"
          />
        </section>

        <section className="section report-summary report-decision-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">结构化摘要</p>
            <h2>投递决策摘要</h2>
            <p className="section-copy">Web 只整理已生成 artifact 的展示顺序，不重新解释评分、Gate 或投递建议。</p>
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
                原始 Markdown 报告
              </span>
              <small>traceable source content</small>
            </summary>
            {report ? (
              <div className="markdown">
                <ReactMarkdown>{report.markdown}</ReactMarkdown>
              </div>
            ) : (
              <div className="empty">阶段未完成</div>
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
              <small>{"来源：" + item.source}</small>
            </li>
          ))
        ) : (
          <li>{"当前运行尚未提供可结构化展示的内容。"}</li>
        )}
        {hiddenCount > 0 ? (
          <li className="report-more-item">
            <span>另有 {hiddenCount} 条来源内容保留在原始 Markdown 与 artifact 中。</span>
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

  return {
    topTitle: topVariant?.title ?? topStrategy?.jd_id ?? "暂无推荐岗位",
    sourceBasis: uniqueItems([
      topVariant ? { text: "scorecard", source: "scorecard" } : null,
      topStrategy ? { text: "strategy", source: "strategy" } : null,
      topExplanation ? { text: "evidence", source: "ranking_explanations" } : null,
      topGapMap ? { text: "gap_map", source: "gap_map" } : null,
    ])
      .map((item) => item.text)
      .join(" / ") || "暂无来源",
    recommendations: uniqueItems([
      topVariant
        ? { text: `优先投递 ${topVariant.title}，综合得分 ${Math.round(topVariant.overallScore * 100)}%。`, source: "scorecard" }
        : null,
      topStrategy ? { text: `投递决策：${topStrategy.apply_decision}。${topStrategy.reason_summary}`, source: "strategy" } : null,
    ]),
    evidence: uniqueItems([
      ...(topExplanation?.evidence_refs.map((text) => ({ text, source: "ranking_explanations.evidence_refs" })) ?? []),
      ...(topExplanation?.positive_signals.map((text) => ({ text, source: "ranking_explanations.positive_signals" })) ?? []),
      ...(topStrategy?.decision_drivers.map((text) => ({ text, source: "strategy.decision_drivers" })) ?? []),
      ...(topVariant?.topReasons.map((text) => ({ text, source: "eval_summary.top_reasons" })) ?? []),
    ]),
    interviewPrep: uniqueItems([
      ...(topStrategy?.catch_up_notes.map((text) => ({ text, source: "strategy.catch_up_notes" })) ?? []),
      ...(topStrategy?.interview_prep_points.map((text) => ({ text, source: "strategy.interview_prep_points" })) ?? []),
      ...(topStrategy?.recommended_actions.map((text) => ({ text, source: "strategy.recommended_actions" })) ?? []),
      ...(topGapMap?.items.flatMap((item) => [
        ...item.catch_up_concepts.map((text) => ({ text, source: "gap_map.catch_up_concepts" })),
        ...item.weak_points.map((text) => ({ text, source: "gap_map.weak_points" })),
      ]) ?? []),
      ...(topExplanation?.risk_flags.map((text) => ({ text, source: "ranking_explanations.risk_flags" })) ?? []),
    ]),
  };
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
    results.push({ text, source: item.source });
  });
  return results;
}
