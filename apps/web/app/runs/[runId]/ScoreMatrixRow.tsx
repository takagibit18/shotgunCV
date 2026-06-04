"use client";

// Visual spec: apps/web/public/design-ref/score-matrix-row-v2.png.
import React, { type ReactNode, useId, useState } from "react";
import Link from "next/link";

import type { JdInputPreview } from "../../../lib/runs";
import type { ApplicationStrategy, RankingExplanation, ScoreCard } from "../../../lib/types";


export type ScoreMatrixRowProps = {
  jdId: string;
  runId: string;
  title: string;
  variantDisplayName: string;
  overallScore: number;
  gapCount: number;
  topReasons: string[];
  scorecard?: ScoreCard;
  explanation?: RankingExplanation;
  strategy?: ApplicationStrategy;
  gateStatus?: string;
  gateReasons?: string[];
  jdPreview?: JdInputPreview;
  jdPreviewIndex?: number;
};

type DimensionItem = {
  key: string;
  label: string;
  value?: number;
  tone?: "default" | "evidence" | "rewrite" | "risk";
};

type ScoreTier = "excellent" | "good" | "caution" | "blocked";

type DecisionKind = "strong" | "apply" | "review" | "hold" | "skip";

type DetailTone = "analysis" | "evidence" | "risk" | "decision" | "action" | "interview" | "rewrite";

type DetailIconName = "target" | "file-text" | "shield-alert" | "route" | "list-check" | "user-check" | "edit-3";


export function ScoreMatrixRow({
  jdId,
  runId,
  title,
  variantDisplayName,
  overallScore,
  gapCount,
  topReasons,
  scorecard,
  explanation,
  strategy,
  gateStatus,
  gateReasons,
  jdPreview,
  jdPreviewIndex,
}: ScoreMatrixRowProps) {
  const scoreDetailsId = useId();
  const jdPanelId = useId();
  const fitDetailsId = useId();
  const [scoreExpanded, setScoreExpanded] = useState(false);
  const [jdPanelOpen, setJdPanelOpen] = useState(false);
  const [recommendationExpanded, setRecommendationExpanded] = useState(false);
  const [fitDetailsOpen, setFitDetailsOpen] = useState(false);

  const hasScorecard = Boolean(scorecard);
  const score = hasScorecard ? toPercent(scorecard?.final_overall_score ?? scorecard?.overall_score ?? overallScore) : null;
  const effectiveGateStatus = scorecard?.gate_status ?? gateStatus ?? "";
  const effectiveGateReasons = toStringArray(scorecard?.gate_reasons).length
    ? toStringArray(scorecard?.gate_reasons)
    : toStringArray(gateReasons);
  const scoreTier = buildScoreTier(score, effectiveGateStatus);
  const dimensions: DimensionItem[] = [
    { key: "verified", label: "匹配度", value: scorecard?.verified_fit_score, tone: "evidence" },
    { key: "rewritePotential", label: "补强空间", value: scorecard?.rewrite_potential_score, tone: "rewrite" },
    { key: "risk", label: "风险", value: scorecard?.risk_score ?? scorecard?.gap_risk_score, tone: "risk" },
    { key: "fit", label: "岗位适配", value: scorecard?.fit_score },
    { key: "ats", label: "关键词", value: scorecard?.ats_score },
    { key: "evidence", label: "证据覆盖", value: scorecard?.evidence_score },
  ];
  const riskScore = hasScorecard ? toPercent(scorecard?.risk_score ?? scorecard?.gap_risk_score ?? 0) : null;
  const positiveSignals = toStringArray(explanation?.positive_signals);
  const signals = positiveSignals.length ? positiveSignals : topReasons;
  const risks = toStringArray(explanation?.risk_flags);
  const evidenceRefs = toStringArray(explanation?.evidence_refs);
  const evidenceCount = evidenceRefs.length;
  const decisionDrivers = toStringArray(strategy?.decision_drivers);
  const recommendedActions = toStringArray(strategy?.recommended_actions);
  const interviewPrepPoints = toStringArray(strategy?.interview_prep_points);
  const resumeRevisionTasks = toStringArray(strategy?.resume_revision_tasks);
  const overallReason =
    explanation?.dimension_reasons && typeof explanation.dimension_reasons.overall === "string"
      ? explanation.dimension_reasons.overall
      : "";
  const fallbackReason = "当前运行未生成评估解释文件，评分矩阵使用评分快照降级展示。";
  const recommendation = buildRecommendationMeta(strategy, scoreTier, effectiveGateStatus, effectiveGateReasons);
  const hasPreviewContent = Boolean(
    jdPreview && ((jdPreview.kind === "image" && jdPreview.imageDataUrl) || (jdPreview.kind === "text" && jdPreview.text)),
  );
  const canExpandScores = hasScorecard;
  const shouldShowReadMore = recommendation.reason.length > 90;
  const scoreDetailsClassName = scoreExpanded ? "matrix-score-details open" : "matrix-score-details";
  const bottomDetailsClassName = fitDetailsOpen ? "matrix-bottom-details open" : "matrix-bottom-details";
  const scoreRingStyle = { "--score-percent": `${score ?? 0}%` } as React.CSSProperties;

  return (
    <article className={`matrix-row matrix-row-v2 matrix-tier-${scoreTier}`} id={`evaluation-${jdId}`}>
      <div className="matrix-main matrix-single-panel">
        <div className="matrix-titleline matrix-titleline-v2">
          <div className="matrix-title-preview-zone">
            <div className="matrix-title-stack">
              <div className="matrix-title-link matrix-title-with-jd">
                <h4>{title}</h4>
              </div>
              <p className="muted">{formatVariantDisplayName(variantDisplayName)}</p>
            </div>
            {jdPreview ? (
              <JdVisiblePreview
                panelId={jdPanelId}
                preview={jdPreview}
                runId={runId}
                previewIndex={jdPreviewIndex}
                canPreview={hasPreviewContent}
                expanded={jdPanelOpen}
                onToggle={() => setJdPanelOpen((current) => !current)}
              />
            ) : null}
          </div>

          <button
            type="button"
            className={`matrix-score-area score-badge score-card-v2 score-tier-${scoreTier}`}
            style={scoreRingStyle}
            aria-expanded={canExpandScores ? scoreExpanded : undefined}
            aria-controls={canExpandScores ? scoreDetailsId : undefined}
            disabled={!canExpandScores}
            onClick={() => {
              if (canExpandScores) {
                setScoreExpanded((current) => !current);
              }
            }}
          >
            <span className="score-badge-main">
              <span className="score-ring">
                <span className="score-ring-center">
                  <span className="decision-label">决策分</span>
                  <strong>{score === null ? "--" : `${score}%`}</strong>
                  {effectiveGateStatus ? (
                    <span className={buildGateClassName(effectiveGateStatus)}>{formatGateStatus(effectiveGateStatus)}</span>
                  ) : null}
                </span>
              </span>
              <InlineIcon name="chevron-down" className="score-chevron" />
            </span>
            <span className="compact-risk-indicator">
              <span>
                风险 <strong>{riskScore === null ? "--" : `${riskScore}%`}</strong>
              </span>
              <span className="risk-mini-bar" aria-hidden="true">
                <span style={{ width: `${riskScore ?? 0}%` }} />
              </span>
            </span>
          </button>
        </div>

        {jdPreview && jdPreview.kind === "text" ? (
          <JdInlinePreview
            panelId={jdPanelId}
            open={jdPanelOpen && hasPreviewContent}
            preview={jdPreview}
            runId={runId}
            previewIndex={jdPreviewIndex}
            onClose={() => setJdPanelOpen(false)}
          />
        ) : null}

        <RecommendationPanel
          meta={recommendation}
          scoreTier={scoreTier}
          expanded={recommendationExpanded}
          canExpand={shouldShowReadMore}
          onToggle={() => setRecommendationExpanded((current) => !current)}
        />

        <div
          id={scoreDetailsId}
          className={scoreDetailsClassName}
          aria-hidden={!scoreExpanded}
        >
          <div className="matrix-score-details-inner">
            <DimensionBars dimensions={dimensions} />
            <div className="matrix-status-bar">
              <span>
                <span className="mini-label">证据引用</span>
                <strong>{evidenceCount || "--"}</strong>
              </span>
              <span>
                <span className="mini-label">风险压力</span>
                <strong>{riskScore === null ? "--" : `${riskScore}%`}</strong>
              </span>
              <span>
                <span className="mini-label">缺口</span>
                <strong>{gapCount}</strong>
              </span>
              <span className="reason-line">{signals[0] ?? "未记录主要原因"}</span>
            </div>
          </div>
        </div>

        <div className="matrix-bottom-accordion">
          <button
            type="button"
            className="matrix-bottom-summary"
            aria-expanded={fitDetailsOpen}
            aria-controls={fitDetailsId}
            onClick={() => setFitDetailsOpen((current) => !current)}
          >
            <span className="cta-icon" aria-hidden="true">
              <DecisionIcon kind="apply" />
            </span>
            <span className="cta-copy">
              <strong>查看匹配详情与建议动作</strong>
              <small>证据引用 / 风险解释 / 简历修改建议 / 面试准备</small>
            </span>
            <InlineIcon name="arrow-right" className="accordion-chevron" />
          </button>
          <div
            id={fitDetailsId}
            className={bottomDetailsClassName}
            aria-hidden={!fitDetailsOpen}
          >
            <div className="matrix-bottom-details-inner">
              <DetailBlock title="适配度分析" className="wide" icon="target" tone="analysis" meta={score === null ? "待评分" : `${score}%`}>
                <p className="matrix-detail-summary">{toPreviewText(overallReason || fallbackReason, 150)}</p>
              </DetailBlock>
              <DetailBlock title="证据引用" icon="file-text" tone="evidence" meta={`${evidenceCount || 0} 条`}>
                <IconList items={evidenceRefs.length ? evidenceRefs.slice(0, 3) : signals.slice(0, 3)} emptyText="暂无证据引用记录。" />
              </DetailBlock>
              <DetailBlock title="风险解释" icon="shield-alert" tone="risk" meta={riskScore === null ? "待评估" : `${riskScore}%`}>
                <IconList items={risks.length ? risks.slice(0, 3) : ["当前岗位未记录显著风险。"]} />
              </DetailBlock>
              <DetailBlock title="决策驱动" icon="route" tone="decision" meta={`${decisionDrivers.length || 0} 项`}>
                <IconList items={decisionDrivers.slice(0, 3)} emptyText="暂无决策驱动记录。" />
              </DetailBlock>
              <DetailBlock title="建议动作" icon="list-check" tone="action" meta={`${recommendedActions.length || 0} 项`}>
                <NumberedList items={recommendedActions.slice(0, 3)} emptyText="暂无建议动作。" />
              </DetailBlock>
              {interviewPrepPoints.length ? (
                <DetailBlock title="面试准备要点" icon="user-check" tone="interview" meta={`${interviewPrepPoints.length} 项`}>
                  <IconList items={interviewPrepPoints.slice(0, 3)} />
                </DetailBlock>
              ) : null}
              {resumeRevisionTasks.length ? (
                <DetailBlock title="简历修改建议" icon="edit-3" tone="rewrite" meta={`${resumeRevisionTasks.length} 项`}>
                  <Checklist items={resumeRevisionTasks.slice(0, 3)} />
                </DetailBlock>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}


function RecommendationPanel({
  meta,
  scoreTier,
  expanded,
  canExpand,
  onToggle,
}: {
  meta: ReturnType<typeof buildRecommendationMeta>;
  scoreTier: ScoreTier;
  expanded: boolean;
  canExpand: boolean;
  onToggle: () => void;
}) {
  const reasonClassName = expanded ? "recommendation-reason expanded" : "recommendation-reason";
  return (
    <section className={`recommendation-panel recommendation-${meta.kind} recommendation-tier-${scoreTier}`} aria-label="投递建议">
      <span className="recommendation-icon" aria-hidden="true">
        <DecisionIcon kind={meta.kind} />
      </span>
      <div className="recommendation-copy">
        <p className="recommendation-kicker">投递建议</p>
        <h5>{meta.label}</h5>
        <p className={reasonClassName}>
          {meta.reason}
        </p>
        {canExpand ? (
          <button type="button" className="inline-read-more" onClick={onToggle}>
            {expanded ? "收起" : "展开全部"}
          </button>
        ) : null}
      </div>
    </section>
  );
}


function JdVisiblePreview({
  panelId,
  preview,
  runId,
  previewIndex,
  canPreview,
  expanded,
  onToggle,
}: {
  panelId: string;
  preview: JdInputPreview;
  runId: string;
  previewIndex?: number;
  canPreview: boolean;
  expanded: boolean;
  onToggle: () => void;
}) {
  const title = preview.label || preview.originalName || "岗位描述详情";
  const imageHref = typeof previewIndex === "number" ? `/runs/${runId}/jd-preview/${previewIndex}` : "";

  if (preview.kind === "image" && preview.imageDataUrl) {
    return (
      <div className="jd-visible-preview image" aria-label={`${title} 岗位描述缩略预览`}>
        <img src={preview.imageDataUrl} alt={`${title} 岗位描述缩略预览`} />
        {imageHref ? (
          <Link href={imageHref} className="jd-preview-enlarge" aria-label={`放大查看 ${title}`}>
            <InlineIcon name="external" />
          </Link>
        ) : null}
      </div>
    );
  }

  if (preview.kind === "text" && preview.text) {
    return (
      <button
        type="button"
        className="jd-visible-preview text"
        aria-label={`查看 ${title} 的岗位描述原文`}
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={onToggle}
      >
        <span className="jd-preview-label">岗位描述原文</span>
        <span className="jd-preview-excerpt">{preview.text.slice(0, 120)}</span>
        <span className="jd-preview-enlarge" aria-hidden="true">
          <InlineIcon name="external" />
        </span>
      </button>
    );
  }

  return (
    <div className="jd-visible-preview metadata" aria-label={`${title} 暂无可预览岗位描述`}>
      <span className="jd-preview-label">暂无预览</span>
      <span className="jd-preview-excerpt">{preview.note ?? "当前岗位输入暂无可直接展示的文本或截图。"}</span>
      <button type="button" className="jd-preview-enlarge" disabled={!canPreview} aria-label="暂无可预览岗位描述">
        <InlineIcon name="external" />
      </button>
    </div>
  );
}


function JdInlinePreview({
  panelId,
  open,
  preview,
  runId,
  previewIndex,
  onClose,
}: {
  panelId: string;
  open: boolean;
  preview: JdInputPreview;
  runId: string;
  previewIndex?: number;
  onClose: () => void;
}) {
  const previewClassName = open ? "jd-inline-preview open" : "jd-inline-preview";
  const title = preview.label || preview.originalName || "岗位描述详情";
  const imageHref = typeof previewIndex === "number" ? `/runs/${runId}/jd-preview/${previewIndex}` : "";
  return (
    <div
      id={panelId}
      className={previewClassName}
      role="dialog"
      aria-label={`${title} 岗位描述详情`}
      aria-hidden={!open}
    >
      <div className="jd-inline-preview-inner">
        <div className="jd-inline-preview-heading">
          <div>
            <p className="eyebrow">岗位描述详情</p>
            <h5>{title}</h5>
          </div>
          <button type="button" className="jd-inline-close" aria-label="关闭岗位描述详情" onClick={onClose}>
            <InlineIcon name="close" />
          </button>
        </div>
        {preview.kind === "image" && preview.imageDataUrl ? (
          imageHref ? (
            <Link href={imageHref} className="jd-inline-image-link" aria-label={`打开 ${title} 大图预览`}>
              <img src={preview.imageDataUrl} alt={`${title} 岗位描述截图预览`} />
              <span>点击放大</span>
            </Link>
          ) : (
            <div className="jd-inline-image-link">
              <img src={preview.imageDataUrl} alt={`${title} 岗位描述截图预览`} />
            </div>
          )
        ) : null}
        {preview.kind === "text" && preview.text ? <pre className="jd-inline-text">{preview.text}</pre> : null}
      </div>
    </div>
  );
}


function DetailBlock({
  title,
  children,
  className = "",
  icon,
  tone = "analysis",
  meta,
}: {
  title: string;
  children: ReactNode;
  className?: string;
  icon: DetailIconName;
  tone?: DetailTone;
  meta?: string;
}) {
  return (
    <section className={["matrix-detail-block", `tone-${tone}`, className].filter(Boolean).join(" ")}>
      <div className="matrix-detail-heading">
        <span className="matrix-detail-icon" aria-hidden="true">
          <InlineIcon name={icon} />
        </span>
        <h5>{title}</h5>
        {meta ? <span className="matrix-detail-meta">{meta}</span> : null}
      </div>
      {children}
    </section>
  );
}


function IconList({ items, emptyText = "" }: { items: string[]; emptyText?: string }) {
  if (!items.length) {
    return emptyText ? <p className="muted">{emptyText}</p> : null;
  }
  return (
    <ul className="matrix-icon-list">
      {items.map((item, index) => (
        <li key={`${index}-${item.slice(0, 20)}`}>
          <span aria-hidden="true" />
          {formatUserText(item)}
        </li>
      ))}
    </ul>
  );
}


function NumberedList({ items, emptyText = "" }: { items: string[]; emptyText?: string }) {
  if (!items.length) {
    return emptyText ? <p className="muted">{emptyText}</p> : null;
  }
  return (
    <ol className="matrix-number-list">
      {items.map((item, index) => (
        <li key={`${index}-${item.slice(0, 20)}`}>
          <span aria-hidden="true">{index + 1}</span>
          {formatUserText(item)}
        </li>
      ))}
    </ol>
  );
}


function Checklist({ items }: { items: string[] }) {
  return (
    <ul className="matrix-check-list">
      {items.map((item, index) => (
        <li key={`${index}-${item.slice(0, 20)}`}>
          <span aria-hidden="true">✓</span>
          {formatUserText(item)}
        </li>
      ))}
    </ul>
  );
}


function DimensionBars({ dimensions }: { dimensions: DimensionItem[] }) {
  return (
    <div className="dimension-grid" aria-label="匹配维度">
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


function toStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0) : [];
}


function toPercent(value: number): number {
  return Math.round(Math.max(0, Math.min(1, value)) * 100);
}


function buildScoreTier(score: number | null, gateStatus: string): ScoreTier {
  if (gateStatus === "blocked" || score === null || score < 40) {
    return "blocked";
  }
  if (score >= 85) {
    return "excellent";
  }
  if (score >= 65) {
    return "good";
  }
  return "caution";
}


function buildRecommendationMeta(
  strategy: ApplicationStrategy | undefined,
  scoreTier: ScoreTier,
  gateStatus: string,
  gateReasons: string[],
): { kind: DecisionKind; label: string; reason: string } {
  if (!strategy) {
    const label = gateStatus === "blocked" ? "暂缓" : "需要复核";
    const reason = gateReasons.length
      ? `门槛提示：${gateReasons.map(formatUserText).join(" / ")}`
      : "当前岗位尚未生成投递策略，请先完成评估或复核门槛状态。";
    return { kind: gateStatus === "blocked" ? "hold" : "review", label, reason };
  }

  const decision = normalizeDecision(strategy.apply_decision);
  if (decision === "apply" && scoreTier === "excellent") {
    return {
      kind: "strong",
      label: "强烈建议投递",
      reason: strategy.reason_summary || "评分和证据覆盖均处于高优先级区间，建议优先处理。",
    };
  }
  return {
    kind: decision,
    label: formatDecision(decision),
    reason: strategy.reason_summary || "策略产物未提供详细原因，请结合证据引用和风险解释复核。",
  };
}


function normalizeDecision(value: string): DecisionKind {
  if (value === "apply" || value === "recommended" || value === "strong_apply") {
    return "apply";
  }
  if (value === "hold" || value === "pause" || value === "defer") {
    return "hold";
  }
  if (value === "skip" || value === "blocked") {
    return "skip";
  }
  return "review";
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
    blocked: "暂不建议投递",
    needs_review: "需要复核",
  };
  return labels[status] ?? formatUserText(status);
}


function formatDecision(value: DecisionKind): string {
  const labels: Record<DecisionKind, string> = {
    strong: "强烈建议投递",
    apply: "建议投递",
    review: "需要复核",
    hold: "暂缓",
    skip: "跳过",
  };
  return labels[value];
}


function formatVariantDisplayName(value: string): string {
  if (!value) {
    return "推荐简历版本";
  }
  return value.replace(/（[^）]+）/g, "").replace(/\([^)]+\)/g, "") || "推荐简历版本";
}


function formatUserText(value: string): string {
  const labels: Record<string, string> = {
    hard_gate_missing: "硬性要求缺少证据",
    needs_review: "需要复核",
    manual_review: "人工复核",
    apply: "建议投递",
    hold: "暂缓",
    skip: "跳过",
    review: "复核",
  };
  return value.replace(/\b[a-z]+(?:_[a-z0-9]+)+\b/g, (token) => labels[token] ?? token.replace(/_/g, " "));
}


function toPreviewText(value: string, maxLength: number): string {
  const normalized = formatUserText(value).replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength).replace(/[，。；、\s]+$/u, "")}...`;
}


function buildScoreBarClassName(tone?: DimensionItem["tone"]): string {
  return ["score-bar", tone === "risk" ? "risk-bar" : "", tone === "rewrite" ? "rewrite-bar" : "", tone === "evidence" ? "evidence-bar" : ""]
    .filter(Boolean)
    .join(" ");
}


function InlineIcon({ name, className = "" }: { name: "search-document" | "chevron-down" | "close" | "external" | "arrow-right" | DetailIconName; className?: string }) {
  const paths: Record<typeof name, ReactNode> = {
    "search-document": (
      <>
        <path d="M7 3.5h6.2L18 8.3V20a1.5 1.5 0 0 1-1.5 1.5H7A1.5 1.5 0 0 1 5.5 20V5A1.5 1.5 0 0 1 7 3.5Z" />
        <path d="M13 3.8V9h5" />
        <circle cx="10.4" cy="14.2" r="2.3" />
        <path d="m12.1 15.9 2 2" />
      </>
    ),
    "chevron-down": <path d="m6 9 6 6 6-6" />,
    target: (
      <>
        <circle cx="12" cy="12" r="7.5" />
        <circle cx="12" cy="12" r="3.2" />
        <path d="M12 2.5v3M21.5 12h-3M12 21.5v-3M2.5 12h3" />
      </>
    ),
    "file-text": (
      <>
        <path d="M7 3.5h6.2L18 8.3V20a1.5 1.5 0 0 1-1.5 1.5H7A1.5 1.5 0 0 1 5.5 20V5A1.5 1.5 0 0 1 7 3.5Z" />
        <path d="M13 3.8V9h5M8.5 12.5h7M8.5 16h5" />
      </>
    ),
    "shield-alert": (
      <>
        <path d="M12 3.5 19 6v5.5c0 4.4-2.8 7.9-7 9-4.2-1.1-7-4.6-7-9V6l7-2.5Z" />
        <path d="M12 8.5v5M12 16.8h.01" />
      </>
    ),
    route: (
      <>
        <circle cx="6" cy="6" r="2.5" />
        <circle cx="18" cy="18" r="2.5" />
        <path d="M8.5 6h3.8a3.2 3.2 0 0 1 0 6.4h-.6a3.2 3.2 0 0 0 0 6.4H15.5" />
      </>
    ),
    "list-check": (
      <>
        <path d="m5 7 1.5 1.5L9.5 5.5M5 13l1.5 1.5 3-3M12.5 7h6M12.5 13h6M5 19h13.5" />
      </>
    ),
    "user-check": (
      <>
        <circle cx="10" cy="7.5" r="3.5" />
        <path d="M3.8 20a6.2 6.2 0 0 1 11.7-2.9" />
        <path d="m16.2 19 2 2 3.5-4" />
      </>
    ),
    "edit-3": (
      <>
        <path d="M4.5 19.5h4l10-10a2.1 2.1 0 0 0-3-3l-10 10-1 3Z" />
        <path d="m14 8 3 3M12 19.5h8" />
      </>
    ),
    external: (
      <>
        <path d="M14 5h5v5" />
        <path d="m10 14 9-9" />
        <path d="M19 14v4.5A1.5 1.5 0 0 1 17.5 20h-12A1.5 1.5 0 0 1 4 18.5v-12A1.5 1.5 0 0 1 5.5 5H10" />
      </>
    ),
    "arrow-right": (
      <>
        <path d="M5 12h14" />
        <path d="m13 6 6 6-6 6" />
      </>
    ),
    close: (
      <>
        <path d="m7 7 10 10" />
        <path d="m17 7-10 10" />
      </>
    ),
  };
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={className}>
      {paths[name]}
    </svg>
  );
}


function DecisionIcon({ kind }: { kind: DecisionKind }) {
  if (kind === "strong") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12.5 3.5c2.8 1 5.1 3.3 6.2 6.1l-4.4 4.4-4.3-4.3 4.4-4.4Z" />
        <path d="M9.6 10 5.8 11.3 4 15l4.2-.8" />
        <path d="m14 14.4-.8 4.2 3.7-1.8 1.3-3.8" />
        <path d="M7.5 16.5 5 19" />
        <circle cx="15" cy="8.8" r="1.2" />
      </svg>
    );
  }
  if (kind === "apply") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="8.5" />
        <path d="m8.2 12.3 2.4 2.4 5.2-5.5" />
      </svg>
    );
  }
  if (kind === "hold") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="8.5" />
        <path d="M9.5 8.5v7M14.5 8.5v7" />
      </svg>
    );
  }
  if (kind === "skip") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="8.5" />
        <path d="m6.2 17.8 11.6-11.6" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 3.5 21 20H3L12 3.5Z" />
      <path d="M12 9v5" />
      <path d="M12 17.5h.01" />
    </svg>
  );
}
