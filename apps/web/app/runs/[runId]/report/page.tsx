import React from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";

import { AppShell } from "../../../AppShell";
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
      <Link href={`/runs/${resolvedParams.runId}`} className="backlink">
        {"返回运行详情"}
      </Link>

      <section className="page-header detail-header">
        <div>
          <p className="eyebrow">{"运行报告 · 投递复盘"}</p>
          <h1 className="page-title">{resolvedParams.runId}</h1>
          <p className="hero-copy">{"先呈现投递结论、关键证据和面试前补强点，再保留原始 Markdown 报告用于追溯。"}</p>
        </div>
        <span className="status-chip info">{"Markdown 原文"}</span>
      </section>

      <section className="status-strip" aria-label="报告目录">
        <article className="status-strip-item info">
          <span>报告目录</span>
          <strong>摘要 / 原文 / 追溯</strong>
        </article>
        <article className="status-strip-item success">
          <span>当前推荐岗位</span>
          <strong>{reportSummary.topTitle}</strong>
        </article>
        <article className="status-strip-item">
          <span>引用来源</span>
          <strong>strategy / scorecard / gap_map</strong>
        </article>
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
    </AppShell>
  );
}


type SummaryItem = {
  text: string;
  source: string;
};

function SummaryCard({ title, items }: { title: string; items: SummaryItem[] }) {
  return (
    <article className="report-summary-card">
      <h3>{title}</h3>
      <ul>
        {items.length > 0 ? (
          items.map((item) => (
            <li key={`${item.source}-${item.text}`}>
              <span>{item.text}</span>
              <small>{"来源：" + item.source}</small>
            </li>
          ))
        ) : (
          <li>{"当前运行尚未提供可结构化展示的内容。"}</li>
        )}
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
