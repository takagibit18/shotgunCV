import React from "react";
import type { ApplicationStrategy, RankingExplanation, ScoreCard } from "../../../lib/types";


export type ScoreMatrixRowProps = {
  jdId: string;
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

type DimensionItem = {
  key: string;
  label: string;
  value?: number;
  tone?: "default" | "evidence" | "rewrite" | "risk";
};


export function ScoreMatrixRow({
  jdId,
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
    { key: "verified", label: "真实匹配", value: scorecard?.verified_fit_score, tone: "evidence" },
    { key: "rewritePotential", label: "改写潜力", value: scorecard?.rewrite_potential_score, tone: "rewrite" },
    { key: "risk", label: "风险压力", value: scorecard?.risk_score ?? scorecard?.gap_risk_score, tone: "risk" },
    { key: "fit", label: "岗位匹配", value: scorecard?.fit_score },
    { key: "ats", label: "关键词", value: scorecard?.ats_score },
    { key: "evidence", label: "证据覆盖", value: scorecard?.evidence_score },
  ];
  const riskScore = toPercent(scorecard?.risk_score ?? scorecard?.gap_risk_score ?? 0);
  const positiveSignals = toStringArray(explanation?.positive_signals);
  const signals = positiveSignals.length ? positiveSignals : topReasons;
  const risks = toStringArray(explanation?.risk_flags);
  const evidenceRefs = toStringArray(explanation?.evidence_refs);
  const evidenceCount = evidenceRefs.length;
  const primaryRisk = risks[0] ?? null;
  const decisionDrivers = toStringArray(strategy?.decision_drivers);
  const recommendedActions = toStringArray(strategy?.recommended_actions);
  const suggestedAction = recommendedActions[0] ?? null;
  const overallReason =
    explanation?.dimension_reasons && typeof explanation.dimension_reasons.overall === "string"
      ? explanation.dimension_reasons.overall
      : "";

  return (
    <article className="matrix-row" id={`evaluation-${jdId}`}>
      <div className="matrix-main matrix-single-panel">
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
          <div className="matrix-score-area">
            <span className="matrix-decision-score">
              <span className="decision-label">决策分</span>
              <strong>{score}%</strong>
            </span>
            {scorecard?.gate_status ? (
              <span className={buildGateClassName(scorecard.gate_status)}>{formatGateStatus(scorecard.gate_status)}</span>
            ) : null}
          </div>
        </div>

        <div className="matrix-action-strip">
          <div className="action-strip-col">
            <h5>适配度</h5>
            <p>{overallReason.slice(0, 120) || "当前运行未生成评估解释文件，评分矩阵使用评分快照降级展示。"}</p>
          </div>
          <div className="action-strip-col">
            <h5>风险提示</h5>
            {primaryRisk ? (
              <>
                <p className="risk-line">{primaryRisk}</p>
                {suggestedAction ? <p className="muted">{suggestedAction}</p> : null}
              </>
            ) : (
              <p className="muted">无明显风险</p>
            )}
          </div>
          <div className="action-strip-col">
            <h5>投递建议</h5>
            <p>{strategy?.apply_decision ?? "暂无投递决策"}</p>
          </div>
        </div>

        <DimensionBars dimensions={dimensions} />
        <div className="matrix-status-bar">
          <span>
            <span className="mini-label">证据引用</span>
            <strong>{evidenceCount || "--"}</strong>
          </span>
          <span>
            <span className="mini-label">风险压力</span>
            <strong>{riskScore}%</strong>
          </span>
          <span>
            <span className="mini-label">缺口</span>
            <strong>{gapCount}</strong>
          </span>
          <span className="reason-line">{signals[0] ?? "未记录主要原因"}</span>
        </div>

        <div className="matrix-expansion">
          <div className="matrix-expansion-card">
            <h5>证据引用</h5>
            <ul>
              {(evidenceRefs.length ? evidenceRefs.slice(0, 3) : signals.slice(0, 3)).map((item, i) => (
                <li key={`${i}-${item.slice(0, 20)}`}>{item}</li>
              ))}
            </ul>
          </div>
          <div className="matrix-expansion-card">
            <h5>风险解释</h5>
            <ul>
              {(risks.length ? risks.slice(0, 3) : ["当前岗位未记录显著风险。"]).map((item, i) => (
                <li key={`${i}-${item.slice(0, 20)}`}>{item}</li>
              ))}
            </ul>
          </div>
          {decisionDrivers.length ? (
            <div className="matrix-action-strip">
              <div className="action-strip-col">
                <h5>决策驱动</h5>
                <p>{decisionDrivers.slice(0, 3).join(" / ")}</p>
              </div>
              <div className="action-strip-col">
                <h5>建议动作</h5>
                <p>{recommendedActions.slice(0, 3).join(" / ") || "--"}</p>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </article>
  );
}


function toStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0) : [];
}


function DimensionBars({ dimensions }: { dimensions: DimensionItem[] }) {
  return (
    <div className="dimension-grid" aria-label="维度矩阵">
      {dimensions.map((dimension) => {
        const percent = dimension.value === undefined ? 0 : toPercent(dimension.value);
        return (
          <div key={dimension.key} className="dimension-cell">
            <div className="dimension-label">
              <span>{dimension.label}</span>
              <strong>{dimension.value === undefined ? "--" : `${percent}%`}</strong>
            </div>
            <div className={buildScoreBarClassName(dimension.tone)}>
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


function buildGateClassName(status: string): string {
  if (status === "blocked") {
    return "status-chip danger";
  }
  if (status === "needs_review") {
    return "status-chip warning";
  }
  if (status === "pass") {
    return "status-chip success";
  }
  return "status-chip";
}


function formatGateStatus(status: string): string {
  const labels: Record<string, string> = {
    pass: "通过",
    blocked: "阻断",
    needs_review: "需复核",
  };
  return labels[status] ?? status;
}


function buildScoreBarClassName(tone?: DimensionItem["tone"]): string {
  return ["score-bar", tone === "risk" ? "risk-bar" : "", tone === "rewrite" ? "rewrite-bar" : "", tone === "evidence" ? "evidence-bar" : ""]
    .filter(Boolean)
    .join(" ");
}
