import React from "react";
import Link from "next/link";

import { AppShell, Icon } from "../../AppShell";
import { loadRunDetail } from "../../../lib/runs";
import type { ApplicationStrategy, RankingExplanation, ScoreCard } from "../../../lib/types";
import { RunActionPanel } from "./RunActionPanel";
import { ScoreRing } from "./ScoreRing";


type PageProps = {
  params: Promise<{ runId: string }>;
};

type DimensionItem = {
  key: string;
  label: string;
  value?: number;
  tone?: "default" | "evidence" | "rewrite" | "risk";
};

const STAGE_LABELS: Record<string, string> = {
  ingest: "导入",
  analyze: "分析",
  generate: "生成",
  evaluate: "评估",
  plan: "计划",
  report: "报告",
};

const STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  queued: "排队中",
  running: "运行中",
  done: "已完成",
  failed: "失败",
  "ingest-ready": "导入就绪",
};


export default async function RunPage({ params }: PageProps) {
  const resolvedParams = await params;
  const detail = await loadRunDetail(resolvedParams.runId);
  const displayStatus =
    detail.draftStatus === "done" && detail.runStatus?.quality_status === "warning"
      ? "完成但有警告"
      : STATUS_LABELS[detail.draftStatus] ?? detail.draftStatus;
  const qualityWarningCount = detail.observability.qualityWarnings.length + (detail.runStatus?.quality_summary ? 1 : 0);
  const nextAction = buildNextAction(detail.draftStatus);

  return (
    <AppShell active="evaluation" eyebrow="评估结果 / 阶段评估" freshnessText="本地数据">
      <main className="app-shell operational-shell">
      <Link href="/" className="backlink">
        {"返回运行列表"}
      </Link>

      <div className="workspace-grid">
        <div className="workspace-main">
      <section className="page-header detail-header">
        <div>
          <p className="eyebrow">{"运行详情 · "}{detail.label || "未命名运行"}</p>
          <h1 className="page-title">{detail.runId}</h1>
          <p className="hero-copy">
            {"把阶段状态、模型观测、硬门槛审查和投递评分放在同一条工作流里，优先回答“现在能不能投、风险在哪里”。"}
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
            <span className="pill">{displayStatus}</span>
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
          <RunActionPanel runId={detail.runId} draftStatus={detail.draftStatus} draft={detail.draft} />
        </div>
      </section>

      <section className="status-strip" aria-label="运行首屏状态">
        <StatusStripItem label="当前状态" value={displayStatus} tone={detail.draftStatus === "failed" ? "danger" : "info"} />
        <StatusStripItem
          label="是否可信"
          value={qualityWarningCount > 0 ? `${qualityWarningCount} 个质量提示` : "暂无质量警告"}
          tone={qualityWarningCount > 0 ? "warning" : "success"}
        />
        <StatusStripItem label="下一步动作" value={nextAction} tone="default" />
        <StatusStripItem
          label="硬门槛"
          value={summarizeGates(detail.preflightGates.length, detail.preflightGates.filter((gate) => gate.status !== "pass").length)}
          tone={detail.preflightGates.some((gate) => gate.status !== "pass") ? "warning" : "success"}
        />
      </section>

      <section className="section">
        <SectionHeading eyebrow="Run status" title="运行状态" action={displayStatus} />
        <div className="detail-grid">
          <article className="detail-card">
            <h3>{"阶段状态"}</h3>
            <div className="pill-row">
              {detail.stageStatuses.map((item) => (
                <span key={item.stage} className={`pill stage-${item.status}`}>
                  {(STAGE_LABELS[item.stage] ?? item.stage) + " · " + item.status}
                </span>
              ))}
            </div>
          </article>
          <article className="detail-card">
            <h3>{"最近一次运行"}</h3>
            <p>
              {"动作："}
              <span className="mono">{detail.runStatus?.last_action ?? "n/a"}</span>
            </p>
            <p>
              {"当前阶段："}
              <span className="mono">{detail.runStatus?.current_stage ?? "n/a"}</span>
            </p>
            {detail.runStatus?.error_summary ? (
              <p className="risk-line">
                {(detail.runStatus.error_stage ?? "unknown") + ": " + detail.runStatus.error_summary}
              </p>
            ) : null}
            {detail.runStatus?.quality_summary ? (
              <p className="risk-line">
                {"质量提示："}
                {detail.runStatus.quality_summary}
              </p>
            ) : null}
          </article>
        </div>
      </section>

      <section className="section">
        <SectionHeading
          eyebrow="Observability"
          title="运行观测"
          action={`${detail.observability.fallbackCount} fallback`}
        />
        <div className="detail-grid">
          <article className="detail-card">
            <h3>{"模型与 token"}</h3>
            <p>
              {"总 token："}
              <span className="mono">{detail.observability.totalTokens ?? "n/a"}</span>
            </p>
            <p>
              {"Prompt / completion："}
              <span className="mono">
                {(detail.observability.promptTokens ?? "n/a") + " / " + (detail.observability.completionTokens ?? "n/a")}
              </span>
            </p>
            <ul>
              {detail.observability.resolvedModels.map((model) => (
                <li key={`${model.stage}-${model.role}-${model.resolvedModel}`}>
                  <span className="mono">{model.stage}</span>
                  {" · "}
                  {model.role}
                  {" · "}
                  {model.provider}
                  {" · "}
                  {model.resolvedModel || "n/a"}
                </li>
              ))}
            </ul>
          </article>
          <article className="detail-card">
            <h3>{"工具与质量"}</h3>
            <p>
              {"工具调用："}
              <span className="mono">{detail.observability.toolCallCount}</span>
            </p>
            <p>
              {"Fallback："}
              <span className="mono">{detail.observability.fallbackCount}</span>
            </p>
            {detail.observability.qualityWarnings.length > 0 ? (
              <ul>
                {detail.observability.qualityWarnings.map((warning) => (
                  <li key={warning} className="risk-line">{warning}</li>
                ))}
              </ul>
            ) : (
              <p>{"暂无质量警告"}</p>
            )}
          </article>
        </div>
      </section>

      {detail.draft ? (
        <section className="section">
          <SectionHeading eyebrow="Draft run" title="上传草稿" action={displayStatus} />
          <div className="detail-grid">
            <article className="detail-card">
              <h3>{"输入文件"}</h3>
              <ul>
                {detail.draft.files.map((file) => (
                  <li key={`${file.role}-${file.storedRelativePath}`}>
                    <span className="mono">{file.role}</span>
                    {" · "}
                    {file.displayName || file.originalName}
                    {" · "}
                    {file.originalName}
                    {" · "}
                    <span className="mono">{file.storedRelativePath}</span>
                  </li>
                ))}
              </ul>
            </article>
            <article className="detail-card">
              <h3>{"下一步 CLI"}</h3>
              <p>{"Web 可以创建和管理本地草稿。确认输入后可在页面运行，或在本地执行："}</p>
              <pre className="command-block">{detail.draft.nextCommand}</pre>
            </article>
          </div>
        </section>
      ) : null}

      <section className="section">
        <SectionHeading eyebrow="Input sources" title="输入来源" />
        {detail.inputSources.length > 0 ? (
          <div className="input-source-table" role="table" aria-label="输入来源清单">
            <div className="input-source-row header" role="row">
              <span role="columnheader">{"角色"}</span>
              <span role="columnheader">{"来源"}</span>
              <span role="columnheader">{"显示名"}</span>
              <span role="columnheader">{"原始文件名"}</span>
              <span role="columnheader">{"相对路径"}</span>
              <span role="columnheader">{"大小"}</span>
              <span role="columnheader">{"抽取状态"}</span>
            </div>
            {detail.inputSources.map((source) => (
              <div key={`${source.role}-${source.relativePath}-${source.originalName}`} className="input-source-row" role="row">
                <span role="cell">{source.role}</span>
                <span role="cell">{source.sourceOrigin}</span>
                <span role="cell">{source.displayName || source.originalName}</span>
                <span role="cell">{source.originalName}</span>
                <span className="mono" role="cell">{source.relativePath}</span>
                <span role="cell">{formatBytes(source.sizeBytes)}</span>
                <span role="cell">
                  {source.extractionStatus}
                  {source.extractionError ? `: ${source.extractionError}` : ""}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty">{"暂无输入来源"}</div>
        )}
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
        <SectionHeading eyebrow="Preflight gate" title="硬门槛审查" />
        {detail.preflightGates.length > 0 ? (
          <div className="gate-grid">
            {detail.preflightGates.map((gate) => {
              const requirements = detail.requirementMatrix.filter((item) => item.jd_id === gate.jd_id);
              return (
                <article key={gate.jd_id} className={`detail-card gate-card gate-${gate.status}`}>
                  <div className="gate-card-heading">
                    <h3>{gate.jd_id}</h3>
                    <span className={buildGateClassName(gate.status)}>{formatGateStatus(gate.status)}</span>
                  </div>
                  {gate.reasons.length > 0 ? <p className="risk-line">{gate.reasons.join(" / ")}</p> : null}
                  <ul className="requirement-list">
                    {requirements.slice(0, 4).map((item) => (
                      <li key={item.requirement_id}>
                        <span className="mono">{formatRequirementTier(item.tier)}</span>
                        {" · "}
                        {formatEvidenceStatus(item.evidence_status)}
                        {" · "}
                        {item.requirement_text}
                      </li>
                    ))}
                  </ul>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="empty">{"当前 run 暂无 v0.5.7 硬门槛产物，继续按历史评分产物兼容展示。"}</div>
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
        <SectionHeading eyebrow="阶段评估" title="评估阶段" />
        {detail.evaluate.isComplete ? (
          <div className="score-matrix">
            <div className="matrix-header">
              <div>
                <p className="eyebrow">{"决策矩阵"}</p>
                <h3>{"岗位优先级矩阵"}</h3>
              </div>
              <p className="muted">{"优先看真实匹配、改写潜力和风险压力，再用历史维度解释排序。点击岗位标题可跳转到对应定制简历。"}</p>
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
                  jdId={item.jdId}
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
        </div>

        <aside className="insight-rail" aria-label="评估洞察">
          <section className="rail-card purple">
            <div className="metric-title">
              <Icon name="sparkle" />
              <h3>优化后简历摘要</h3>
            </div>
            <p className="muted">基于本次评估结果，生成的优化方向与核心改进点。</p>
            <div className="insight-list">
              <div className="insight-item">
                <Icon name="check-square" />
                <span>{detail.generate.variants[0]?.summary ?? "当前 run 尚未生成可展示的简历摘要。"}</span>
              </div>
              <div className="insight-item">
                <Icon name="document" />
                <span>{qualityWarningCount > 0 ? `${qualityWarningCount} 个质量提示需要复核。` : "暂无质量警告，可继续核对证据引用。"}</span>
              </div>
            </div>
          </section>

          <section className="rail-card">
            <div className="metric-title">
              <Icon name="home" />
              <h3>投递建议</h3>
            </div>
            <p className="muted">结合优先级、风险与改写成本，给出投递策略建议。</p>
            <div className="recommendation-list">
              {detail.plan.strategies.length > 0 ? (
                detail.plan.strategies.slice(0, 3).map((strategy, index) => (
                  <div className={index === 0 ? "recommendation-item priority" : "recommendation-item watch"} key={strategy.jd_id}>
                    <Icon name="list" />
                    <span>
                      <strong>{strategy.jd_id}</strong>
                      {" · "}
                      {strategy.reason_summary || strategy.apply_decision}
                    </span>
                  </div>
                ))
              ) : (
                <div className="recommendation-item safe">
                  <Icon name="check-square" />
                  <span>{nextAction}</span>
                </div>
              )}
            </div>
          </section>
        </aside>
      </div>
      </main>
    </AppShell>
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

function StatusStripItem({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "default" | "info" | "success" | "warning" | "danger";
}) {
  return (
    <article className={`status-strip-item ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function buildNextAction(status: string): string {
  if (status === "draft") {
    return "确认输入后运行";
  }
  if (status === "failed") {
    return "查看错误并重试";
  }
  if (status === "done") {
    return "审查评分与报告";
  }
  if (status === "running" || status === "queued") {
    return "等待阶段更新";
  }
  return "检查输入来源";
}

function summarizeGates(total: number, blockedOrReview: number): string {
  if (total === 0) {
    return "暂无门槛产物";
  }
  if (blockedOrReview > 0) {
    return `${blockedOrReview}/${total} 需处理`;
  }
  return `${total}/${total} 通过`;
}


type ScoreMatrixRowProps = {
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


function ScoreMatrixRow({
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
    { key: "riskScore", label: "风险压力", value: scorecard?.risk_score, tone: "risk" },
    { key: "fit", label: "岗位匹配", value: scorecard?.fit_score },
    { key: "ats", label: "关键词", value: scorecard?.ats_score },
    { key: "evidence", label: "证据覆盖", value: scorecard?.evidence_score },
    { key: "stretch", label: "拉伸可控", value: scorecard?.stretch_score },
    { key: "risk", label: "风险压力", value: scorecard?.gap_risk_score, tone: "risk" },
    { key: "cost", label: "改写成本", value: scorecard?.rewrite_cost_score },
  ];
  const riskScore = toPercent(scorecard?.risk_score ?? scorecard?.gap_risk_score ?? 0);
  const signals = explanation?.positive_signals.length ? explanation.positive_signals : topReasons;
  const risks = explanation?.risk_flags ?? [];
  const evidenceRefs = explanation?.evidence_refs ?? [];
  const evidenceCount = evidenceRefs.length;

  return (
    <article className="matrix-row" id={`evaluation-${jdId}`}>
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
            <span className="decision-badge">{"决策分"}</span>
            {scorecard?.gate_status ? <span className={buildGateClassName(scorecard.gate_status)}>{formatGateStatus(scorecard.gate_status)}</span> : null}
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
            <span className="mini-label">{"证据引用"}</span>
            <strong>{evidenceCount || "待检查"}</strong>
          </div>
          <div>
            <span className="mini-label">{"风险压力"}</span>
            <strong>{riskScore}{"%"}</strong>
          </div>
          <div>
            <span className="mini-label">{"缺口数"}</span>
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


function formatGateStatus(status: string): string {
  const labels: Record<string, string> = {
    pass: "通过",
    blocked: "阻断",
    needs_review: "需复核",
  };
  return labels[status] ?? status;
}


function formatRequirementTier(tier: string): string {
  const labels: Record<string, string> = {
    hard_gate: "硬门槛",
    high_priority: "高优先级",
    medium_priority: "中优先级",
    nice_to_have: "加分项",
  };
  return labels[tier] ?? tier;
}


function formatEvidenceStatus(status: string): string {
  const labels: Record<string, string> = {
    verified: "已验证",
    inferred: "可推断",
    missing: "缺失",
    mismatch: "不匹配",
    simulatable: "可模拟补强",
    forbidden_to_fabricate: "禁止编造",
  };
  return labels[status] ?? status;
}


function buildScoreBarClassName(tone?: DimensionItem["tone"]): string {
  return ["score-bar", tone === "risk" ? "risk-bar" : "", tone === "rewrite" ? "rewrite-bar" : "", tone === "evidence" ? "evidence-bar" : ""]
    .filter(Boolean)
    .join(" ");
}


function formatBytes(sizeBytes: number): string {
  if (!Number.isFinite(sizeBytes) || sizeBytes <= 0) {
    return "--";
  }
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`;
  }
  return `${(sizeBytes / 1024).toFixed(1)} KB`;
}
