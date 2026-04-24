import React from "react";
import Link from "next/link";

import { loadRunDetail } from "../../../lib/runs";
import type { RankingExplanation, ScoreCard } from "../../../lib/types";


type PageProps = {
  params: Promise<{ runId: string }>;
};

const STAGE_LABELS: Record<string, string> = {
  ingest: "导入",
  analyze: "分析",
  generate: "生成",
  evaluate: "评估",
  plan: "计划",
  report: "报告",
};


export default async function RunPage({ params }: PageProps) {
  const resolvedParams = await params;
  const detail = await loadRunDetail(resolvedParams.runId);

  return (
    <main className="app-shell">
      <Link href="/" className="backlink">
        {"返回运行列表"}
      </Link>

      <section className="workspace-hero">
        <div>
          <p className="eyebrow">{detail.label || "运行详情"}</p>
          <h1 className="page-title">{detail.runId}</h1>
          <p className="hero-copy">
            {"从阶段产物到评分矩阵的只读视图，用于快速判断岗位优先级、简历版本收益和风险压力。"}
          </p>
          <div className="pill-row">
            <span className="pill">{"分析器："}{detail.analyzerProvider}</span>
            <span className="pill">{"生成器："}{detail.generatorProvider}</span>
            <span className="pill">{"评审器："}{detail.judgeProvider}</span>
            <span className="pill">{"规划器："}{detail.plannerProvider}</span>
            {detail.completedStages.map((stage) => (
              <span key={stage} className="pill">
                {STAGE_LABELS[stage] ?? stage}
              </span>
            ))}
          </div>
        </div>
        <div className="run-control-panel">
          <div className="metric-tile">
            <span className="metric-value">
              {detail.completedStages.length}
              {"/6"}
            </span>
            <span className="metric-label">{"阶段完成"}</span>
          </div>
          <Link href={`/runs/${detail.runId}/report`} className="primary-link">
            {"打开报告"}
          </Link>
        </div>
      </section>

      <section className="section">
        <SectionHeading eyebrow="阶段分析" title="分析阶段" />
        {detail.analyze.isComplete && detail.analyze.candidate ? (
          <div className="detail-grid">
            <article className="detail-card">
              <h3>{"候选人"}</h3>
              <p className="mono">{detail.analyze.candidate.candidate_id}</p>
              <p>{detail.analyze.candidate.strengths.join(" / ")}</p>
            </article>
            <article className="detail-card">
              <h3>{"岗位画像"}</h3>
              <p>
                {"共 "}
                {detail.analyze.jdProfiles.length}
                {" 条岗位描述"}
              </p>
              <ul>
                {detail.analyze.jdProfiles.map((jd) => (
                  <li key={jd.jd_id}>
                    {jd.title} @ {jd.company}
                  </li>
                ))}
              </ul>
            </article>
          </div>
        ) : (
          <div className="empty">{"阶段未完成"}</div>
        )}
      </section>

      <section className="section">
        <SectionHeading eyebrow="阶段生成" title="生成阶段" />
        {detail.generate.isComplete ? (
          <div className="detail-grid">
            {detail.generate.variants.map((variant) => (
              <article key={variant.variant_id} className="detail-card">
                <h3>{variant.variantDisplayName}</h3>
                <p className="pill">{variant.variantTypeDisplay}</p>
                <p className="mono">{variant.variant_id}</p>
                <p>{variant.summary}</p>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty">{"阶段未完成"}</div>
        )}
      </section>

      <section className="section">
        <SectionHeading eyebrow="阶段评估" title="评估阶段" action="岗位优先级矩阵" />
        {detail.evaluate.isComplete ? (
          <>
            <div className="score-matrix">
              <div className="matrix-header">
                <div>
                  <p className="eyebrow">{"决策矩阵"}</p>
                  <h3>{"岗位优先级矩阵"}</h3>
                </div>
                <p className="muted">{"综合得分、证据覆盖和风险压力共同决定投递顺序。"}</p>
              </div>
              {detail.evaluate.topVariants.map((item) => (
                <ScoreMatrixRow
                  key={`${item.jdId}-${item.variantId}`}
                  title={item.title}
                  variantDisplayName={item.variantDisplayName}
                  variantId={item.variantId}
                  overallScore={item.overallScore}
                  gapCount={item.gapCount}
                  topReasons={item.topReasons}
                  scorecard={detail.evaluate.scorecards.find(
                    (scorecard) => scorecard.jd_id === item.jdId && scorecard.variant_id === item.variantId,
                  )}
                  explanation={detail.evaluate.explanations.find(
                    (explanation) => explanation.jd_id === item.jdId && explanation.variant_id === item.variantId,
                  )}
                />
              ))}
            </div>

            <div className="detail-grid">
              {detail.evaluate.explanations.map((explanation) => (
                <article key={`${explanation.jd_id}-${explanation.variant_id}-explanation`} className="detail-card">
                  <h3>{buildVariantDisplayName(explanation.variant_id)}</h3>
                  <p className="mono">{explanation.variant_id}</p>
                  <p>
                    {"评估解释："}
                    {explanation.dimension_reasons.overall}
                  </p>
                  <p>
                    {"风险标记："}
                    {explanation.risk_flags.join(" / ") || "无风险标记"}
                  </p>
                </article>
              ))}
              {detail.evaluate.explanations.length === 0 ? (
                <article className="detail-card">
                  <h3>{"评估解释"}</h3>
                  <p>
                    {"当前运行未生成评估解释文件，旧版产物仍可继续阅读，评分矩阵会使用 scorecards 降级展示。"}
                  </p>
                </article>
              ) : null}
            </div>
          </>
        ) : (
          <div className="empty">{"阶段未完成"}</div>
        )}
      </section>

      <section className="section">
        <SectionHeading eyebrow="阶段计划" title="计划阶段" />
        {detail.plan.isComplete ? (
          <div className="detail-grid">
            {detail.plan.strategies.map((strategy) => (
              <article key={`${strategy.jd_id}-${strategy.recommended_variant_id}`} className="detail-card">
                <h3>{strategy.jd_id}</h3>
                <p>{"优先级："}{strategy.priority_rank}</p>
                <p>{"投递决策："}{strategy.apply_decision}</p>
                <p>{"决策驱动："}{strategy.decision_drivers.join(" / ")}</p>
                <p>{"风险提醒："}{strategy.watchouts.join(" / ")}</p>
                <p>{"建议动作："}{strategy.recommended_actions.join(" / ")}</p>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty">{"阶段未完成"}</div>
        )}
      </section>
    </main>
  );
}


function SectionHeading({ eyebrow, title, action }: { eyebrow: string; title: string; action?: string }) {
  return (
    <div className="section-heading">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
      </div>
      {action ? <span className="status-chip">{action}</span> : null}
    </div>
  );
}


type ScoreMatrixRowProps = {
  title: string;
  variantDisplayName: string;
  variantId: string;
  overallScore: number;
  gapCount: number;
  topReasons: string[];
  scorecard?: ScoreCard;
  explanation?: RankingExplanation;
};


function ScoreMatrixRow({
  title,
  variantDisplayName,
  variantId,
  overallScore,
  gapCount,
  topReasons,
  scorecard,
  explanation,
}: ScoreMatrixRowProps) {
  const score = toPercent(scorecard?.final_overall_score ?? scorecard?.overall_score ?? overallScore);
  const dimensions = [
    ["Fit", "岗位匹配", scorecard?.fit_score],
    ["ATS", "关键词", scorecard?.ats_score],
    ["Evidence", "证据覆盖", scorecard?.evidence_score],
    ["Stretch", "拉伸可控", scorecard?.stretch_score],
    ["Risk", "风险压力", scorecard ? 1 - scorecard.gap_risk_score : undefined],
    ["Cost", "改写成本", scorecard ? 1 - scorecard.rewrite_cost_score : undefined],
  ] as const;
  const riskScore = toPercent(scorecard?.gap_risk_score ?? 0);
  const signals = explanation?.positive_signals.length ? explanation.positive_signals : topReasons;
  const risks = explanation?.risk_flags ?? [];
  const evidenceCount = explanation?.evidence_refs.length ?? 0;

  return (
    <article className="matrix-row">
      <div className="score-ring" style={{ "--score": `${score}%` } as React.CSSProperties}>
        <span>{score}</span>
        <small>{"%"}</small>
      </div>
      <div className="matrix-main">
        <div className="matrix-titleline">
          <div>
            <h4>{title}</h4>
            <p className="muted">
              {variantDisplayName}
              {" · "}
              <span className="mono">{variantId}</span>
            </p>
          </div>
          <span className="decision-badge">{"综合得分"}</span>
        </div>
        <div className="dimension-grid" aria-label="维度矩阵">
          <span className="dimension-caption">{"维度矩阵"}</span>
          {dimensions.map(([key, label, value]) => (
            <div key={key} className="dimension-cell">
              <div className="dimension-label">
                <span>{label}</span>
                <strong>{value === undefined ? "--" : `${toPercent(value)}%`}</strong>
              </div>
              <div className="score-bar">
                <span style={{ width: value === undefined ? "0%" : `${toPercent(value)}%` }} />
              </div>
            </div>
          ))}
        </div>
        <div className="signal-grid">
          <div>
            <span className="mini-label">{"证据覆盖"}</span>
            <strong>{evidenceCount || "待检查"}</strong>
          </div>
          <div>
            <span className="mini-label">{"风险压力"}</span>
            <strong>{riskScore}{"%"}</strong>
          </div>
          <div>
            <span className="mini-label">{"Gap"}</span>
            <strong>{gapCount}</strong>
          </div>
        </div>
        <p className="reason-line">{signals.join(" / ") || "未记录主要原因"}</p>
        <p className="risk-line">{risks.join(" / ") || "无明显风险标记"}</p>
      </div>
    </article>
  );
}


function toPercent(value: number): number {
  return Math.round(Math.max(0, Math.min(1, value)) * 100);
}


function buildVariantDisplayName(variantId: string): string {
  if (variantId.startsWith("variant-jd-")) {
    const jdId = variantId.replace("variant-jd-", "");
    return `岗位定制版本（${jdId}）`;
  }
  if (variantId.startsWith("variant-cluster-")) {
    const cluster = variantId.replace("variant-cluster-", "");
    return `岗位簇版本（${cluster}）`;
  }
  return `简历版本（${variantId}）`;
}
