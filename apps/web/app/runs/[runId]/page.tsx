import React from "react";
import Link from "next/link";

import { loadRunDetail } from "../../../lib/runs";
import type { ApplicationStrategy, RankingExplanation, ScoreCard } from "../../../lib/types";
import { ScoreRing } from "./ScoreRing";


type PageProps = {
  params: Promise<{ runId: string }>;
};

type DimensionItem = {
  key: string;
  label: string;
  value?: number;
  tone?: "default" | "risk";
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
              <article key={variant.variant_id} id={buildVariantAnchorId(variant.variant_id)} className="detail-card">
                <h3>{variant.variantDisplayName}</h3>
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
          <div className="score-matrix">
            <div className="matrix-header">
              <div>
                <p className="eyebrow">{"决策矩阵"}</p>
                <h3>{"岗位优先级矩阵"}</h3>
              </div>
              <p className="muted">{"综合得分、证据覆盖和风险压力共同决定投递顺序。点击岗位标题可跳转到对应定制简历。"}</p>
            </div>
            {detail.evaluate.topVariants
              .slice()
              .sort((left, right) => right.overallScore - left.overallScore)
              .map((item) => (
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
                  strategy={detail.plan.strategies.find((strategy) => strategy.jd_id === item.jdId)}
                />
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
  strategy?: ApplicationStrategy;
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
  strategy,
}: ScoreMatrixRowProps) {
  const score = toPercent(scorecard?.final_overall_score ?? scorecard?.overall_score ?? overallScore);
  const dimensions: DimensionItem[] = [
    { key: "fit", label: "岗位匹配", value: scorecard?.fit_score },
    { key: "ats", label: "关键词", value: scorecard?.ats_score },
    { key: "evidence", label: "证据覆盖", value: scorecard?.evidence_score },
    { key: "stretch", label: "拉伸可控", value: scorecard?.stretch_score },
    { key: "risk", label: "风险压力", value: scorecard?.gap_risk_score, tone: "risk" },
    { key: "cost", label: "改写成本", value: scorecard?.rewrite_cost_score },
  ];
  const riskScore = toPercent(scorecard?.gap_risk_score ?? 0);
  const signals = explanation?.positive_signals.length ? explanation.positive_signals : topReasons;
  const risks = explanation?.risk_flags ?? [];
  const evidenceRefs = explanation?.evidence_refs ?? [];
  const evidenceCount = evidenceRefs.length;

  return (
    <article className="matrix-row">
      <ScoreRing score={score} />
      <div className="matrix-main">
        <div className="matrix-titleline">
          <div>
            <a className="matrix-title-link" href={`#${buildVariantAnchorId(variantId)}`} title="打开对应定制简历">
              <h4>{title}</h4>
            </a>
            <p className="muted">
              {variantDisplayName}
              {" · "}
              <span className="mono">{variantId}</span>
            </p>
          </div>
          <div className="matrix-actions">
            <span className="decision-badge">{"综合评分"}</span>
            <details className="matrix-action-detail">
              <summary>{"适配度分析"}</summary>
              <div className="matrix-action-panel">
                <h5>{"适配度分析"}</h5>
                <p>{explanation?.dimension_reasons.overall ?? "当前运行未生成评估解释文件，旧版产物仍可继续阅读，评分矩阵会使用 scorecards 降级展示。"}</p>
                <p>
                  {"风险标记："}
                  {risks.join(" / ") || "无明显风险标记"}
                </p>
              </div>
            </details>
            <details className="matrix-action-detail">
              <summary>{"投递建议"}</summary>
              <div className="matrix-action-panel">
                <h5>{"投递建议"}</h5>
                <p>
                  {"投递决策："}
                  {strategy?.apply_decision ?? "暂无投递决策"}
                </p>
                <p>
                  {"决策驱动："}
                  {strategy?.decision_drivers.join(" / ") || "暂无决策驱动"}
                </p>
                <p>
                  {"建议动作："}
                  {strategy?.recommended_actions.join(" / ") || "暂无建议动作"}
                </p>
              </div>
            </details>
          </div>
        </div>
        <DimensionBars dimensions={dimensions} />
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
        <div className="matrix-expansion">
          <div className="matrix-expansion-card">
            <h5>{"证据引用展开"}</h5>
            <ul>
              {(evidenceRefs.length ? evidenceRefs : signals).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
          <div className="matrix-expansion-card">
            <h5>{"风险解释展开"}</h5>
            <ul>
              {(risks.length ? risks : ["当前岗位未记录显著风险，建议继续核对岗位要求与证据覆盖。"]).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </article>
  );
}


function DimensionBars({ dimensions }: { dimensions: DimensionItem[] }) {
  return (
    <div className="dimension-grid" aria-label="维度矩阵">
      <span className="dimension-caption">{"维度矩阵"}</span>
      {dimensions.map((dimension) => {
        const percent = dimension.value === undefined ? 0 : toPercent(dimension.value);
        return (
          <div key={dimension.key} className="dimension-cell">
            <div className="dimension-label">
              <span>{dimension.label}</span>
              <strong>{dimension.value === undefined ? "--" : `${percent}%`}</strong>
            </div>
            <div className={dimension.tone === "risk" ? "score-bar risk-bar" : "score-bar"}>
              <span style={{ width: `${percent}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}


function toPercent(value: number): number {
  return Math.round(Math.max(0, Math.min(1, value)) * 100);
}


function buildVariantAnchorId(variantId: string): string {
  return `variant-${variantId}`;
}
