import React from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";

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
    <main className="app-shell">
      <Link href={`/runs/${resolvedParams.runId}`} className="backlink">
        {"返回运行详情"}
      </Link>

      <section className="workspace-hero editorial-hero">
        <div>
          <p className="eyebrow">{"运行报告 · 投递复盘"}</p>
          <h1 className="page-title">{resolvedParams.runId}</h1>
          <p className="hero-copy">{"先呈现投递结论、关键证据和面试前补强点，再保留原始 Markdown 报告用于追溯。"}</p>
        </div>
        <span className="status-chip dark-product-surface">{"Markdown 原文"}</span>
      </section>

      <section className="section report-summary">
        <div className="section-heading">
          <div>
            <p className="eyebrow">{"结构化摘要"}</p>
            <h2>{"投递决策摘要"}</h2>
          </div>
          <span className="status-chip">{"保留原文 Markdown"}</span>
        </div>
        <div className="report-summary-grid">
          <SummaryCard title="推荐结论" items={reportSummary.recommendations} />
          <SummaryCard title="关键证据" items={reportSummary.evidence} />
          <SummaryCard title="面试前突击内容" items={reportSummary.interviewPrep} />
        </div>
      </section>

      <section className="section report-shell">
        {report ? (
          <div className="markdown">
            <ReactMarkdown>{report.markdown}</ReactMarkdown>
          </div>
        ) : (
          <div className="empty">{"阶段未完成"}</div>
        )}
      </section>
    </main>
  );
}


function SummaryCard({ title, items }: { title: string; items: string[] }) {
  return (
    <article className="report-summary-card">
      <h3>{title}</h3>
      <ul>
        {items.length > 0 ? items.map((item) => <li key={item}>{item}</li>) : <li>{"当前运行尚未提供可结构化展示的内容。"}</li>}
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
    recommendations: uniqueText([
      topVariant
        ? `优先投递 ${topVariant.title}，综合得分 ${Math.round(topVariant.overallScore * 100)}%。`
        : "",
      topStrategy ? `投递决策：${topStrategy.apply_decision}。${topStrategy.reason_summary}` : "",
    ]),
    evidence: uniqueText([
      ...(topExplanation?.evidence_refs ?? []),
      ...(topExplanation?.positive_signals ?? []),
      ...(topStrategy?.decision_drivers ?? []),
      ...(topVariant?.topReasons ?? []),
    ]),
    interviewPrep: uniqueText([
      ...(topStrategy?.catch_up_notes ?? []),
      ...(topStrategy?.interview_prep_points ?? []),
      ...(topStrategy?.recommended_actions ?? []),
      ...(topGapMap?.items.flatMap((item) => [...item.catch_up_concepts, ...item.weak_points]) ?? []),
      ...(topExplanation?.risk_flags ?? []),
    ]),
  };
}


function uniqueText(items: string[]): string[] {
  return Array.from(new Set(items.map((item) => item.trim()).filter(Boolean)));
}
