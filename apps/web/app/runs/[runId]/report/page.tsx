import React from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";

import { AppShell, Icon, MetricCard } from "../../../AppShell";
import { loadRunDetail, loadRunReport } from "../../../../lib/runs";
import { formatDecisionLabel, sanitizeUserFacingText } from "../../../../lib/user-facing";


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
        <div className="report-summary-grid">
          <article className="report-summary-card">
            <h3>
              <span className="semantic-icon blue" aria-hidden="true">
                <Icon name="stats" />
              </span>
              核心结论
            </h3>
            <ul>
              {reportSummary.coreSignals.map((item) => (
                <li key={item}>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </article>
          <article className="report-summary-card">
            <h3>
              <span className="semantic-icon blue" aria-hidden="true">
                <Icon name="shield-alert" />
              </span>
              风险边界
            </h3>
            <ul>
              {reportSummary.guardrailSignals.map((item) => (
                <li key={item}>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </article>
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
  const topScorecard = topVariant
    ? detail.evaluate.scorecards.find((scorecard) => scorecard.jd_id === topVariant.jdId && scorecard.variant_id === topVariant.variantId)
    : detail.evaluate.scorecards[0];
  const gapItems = Array.isArray(topGapMap?.items) ? topGapMap.items : [];
  const strategyReason = topStrategy?.reason_summary ? `。${formatUserText(topStrategy.reason_summary)}` : "";
  const finalScore = topScorecard?.final_overall_score ?? topScorecard?.overall_score ?? topVariant?.overallScore;
  const riskScore = topScorecard?.risk_score ?? topScorecard?.gap_risk_score;
  const guardrailFlags = toRawStringArray(topScorecard?.guardrail_flags);
  const gateReasons = toRawStringArray(topScorecard?.gate_reasons);

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
    coreSignals: [
      `综合得分：${formatOptionalPercent(finalScore)}`,
      `风险水平：${formatOptionalPercent(riskScore)}`,
      `决策依据：${formatUserText(topScorecard?.final_decision_source || "未提供")}`,
    ],
    guardrailSignals: [
      `门槛状态：${formatUserText(topScorecard?.gate_status || "未提供")}`,
      ...(guardrailFlags.length ? guardrailFlags.map((flag) => `风险标记：${formatUserText(flag)}`) : ["风险标记：无"]),
      ...gateReasons.map((reason) => `门槛原因：${formatUserText(reason)}`),
    ],
  };
}


function toRawStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0) : [];
}


function formatOptionalPercent(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? `${Math.round(value * 100)}%` : "未提供";
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
  return markdown
    .replace(/^- Candidate:.*$/gim, "")
    .replace(/^- Run directory:.*$/gim, "")
    .replace(/来源：/g, "依据：")
    .replace(/ShotgunCV v[\d.]+ LLM Eval Summary/g, "评估摘要")
    .replace(/Ranked Application Strategy/g, "投递策略排序")
    .replace(/Top Evidence/g, "关键证据")
    .replace(/Apply decision:/g, "投递建议：")
    .replace(/Why worth \/ not worth:/g, "判断依据：")
    .replace(/Evidence that holds:/g, "关键证据：")
    .replace(/Interview danger points:/g, "面试风险点：")
    .replace(/If only revise 3 resume items:/g, "优先修改项：")
    .replace(new RegExp(["Final", "score:"].join(" "), "g"), "最终得分：")
    .replace(/Evidence mapping is limited\./g, "证据映射有限。")
    .replace(/confidence/g, "置信度")
    .replace(/via/g, "依据")
    .replace(/[A-Z]:\\[^\s`，。；;）)]+/gi, "本地文件")
    .replace(/\b(?:input_files|fixtures|runs|analyze|generate|evaluate|plan|report|review|config)[\\/][^\s`，。；;）)]+/gi, "本地产物")
    .replace(/\b[a-z]+(?:_[a-z0-9]+)+\b/g, (token) => formatUserText(token))
    .replace(/\b[a-z]+(?:-[a-z0-9]+)+\b/g, (token) => formatUserText(token));
}


function formatDecision(value: string): string {
  return formatDecisionLabel(value);
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
    blocked: "已阻断",
    "preflight-gate": "前置检查",
    "llm-primary": "主模型判断",
  };
  if (labels[value]) {
    return labels[value];
  }
  return sanitizeUserFacingText(value.replace(/\b[a-z]+(?:_[a-z0-9]+)+\b/g, (token) => labels[token] ?? token.replace(/_/g, " ")));
}
