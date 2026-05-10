import React from "react";
import Link from "next/link";

import { AppShell } from "../../AppShell";
import { loadRunDetail } from "../../../lib/runs";
import { RunActionPanel } from "./RunActionPanel";
import { ScoreMatrixRow } from "./ScoreMatrixRow";


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
    <AppShell active="evaluation" eyebrow="运行详情">
      <main className="app-shell operational-shell">
      <Link href="/" className="backlink">
        {"返回运行列表"}
      </Link>

      <div>
        <div>
      <section className="page-header detail-header">
        <div>
          <p className="eyebrow">{detail.label || "未命名运行"}</p>
          <h1 className="page-title">{detail.runId}</h1>
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


function formatBytes(sizeBytes: number): string {
  if (!Number.isFinite(sizeBytes) || sizeBytes <= 0) {
    return "--";
  }
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`;
  }
  return `${(sizeBytes / 1024).toFixed(1)} KB`;
}
