import React from "react";
import Link from "next/link";

import { AppShell, Icon, MetricCard } from "../../AppShell";
import { STAGE_LABELS, STATUS_LABELS } from "../../../lib/labels";
import { loadRunDetail } from "../../../lib/runs";
import { formatRunDisplayName, sanitizeUserFacingText } from "../../../lib/user-facing";
import { RunActionPanel } from "./RunActionPanel";
import { RunStatusPoller } from "./RunStatusPoller";
import { ScoreMatrixRow } from "./ScoreMatrixRow";


type PageProps = {
  params: Promise<{ runId: string }>;
};

type RunDetail = Awaited<ReturnType<typeof loadRunDetail>>;


export default async function RunPage({ params }: PageProps) {
  const resolvedParams = await params;
  const detail = await loadRunDetail(resolvedParams.runId);
  const sortedResults = detail.evaluate.topVariants.slice().sort((left, right) => right.overallScore - left.overallScore);
  const topResult = sortedResults[0];
  const displayTitle = buildDetailTitle(detail.label, topResult?.title);
  const displayStatus = buildDisplayStatus(detail);
  const riskCount = countHighRiskScores(detail);
  const reviewCount = countReviewItems(detail);
  const topScore = topResult ? `${Math.round(topResult.overallScore * 100)}%` : "--";
  const canShowActions = detail.draftStatus === "draft" || detail.draftStatus === "failed";
  const canShowReport = detail.completedStages.includes("report");

  return (
    <AppShell active="evaluation" eyebrow="评估详情">
      <main className="app-shell operational-shell evaluation-detail-shell">
        <section className="page-header detail-header evaluation-detail-hero">
          <div>
            <div className="page-kicker-row">
              <Link href="/evaluations" className="backlink icon-link">
                <Icon name="chevron-left" />
                返回评估结果
              </Link>
              <span className="breadcrumb-text">评估结果 / 详情</span>
            </div>
            <p className="eyebrow">AI 评估复核</p>
            <h1 className="page-title">{displayTitle}</h1>
            <p className="hero-copy">聚焦岗位要求、匹配结论、风险和下一步动作；工程运行细节已收起，不参与用户判断。</p>
          </div>
          <div className="evaluation-hero-card">
            <span className="semantic-icon blue" aria-hidden="true">
              <Icon name="sparkle" />
            </span>
            <div>
              <span>当前结论</span>
              <strong>{buildPrimaryConclusion(topResult, reviewCount, riskCount, detail)}</strong>
              <small>{displayStatus}</small>
            </div>
            {canShowReport ? (
              <Link href={`/runs/${detail.runId}/report`} className="primary-link icon-link">
                <Icon name="document" />
                查看报告
              </Link>
            ) : null}
          </div>
        </section>

        <section className="metric-card-grid evaluation-detail-metrics" aria-label="评估摘要">
          <MetricCard icon="stats" label="综合推荐" value={topScore} helper={topResult?.title ?? "等待评估结果"} tone="blue" />
          <MetricCard
            icon="shield-alert"
            label="风险提醒"
            value={riskCount}
            helper={riskCount > 0 ? "需要先确认风险" : "未发现高风险项"}
            tone={riskCount > 0 ? "red" : "green"}
          />
          <MetricCard
            icon="shield-check"
            label="复核事项"
            value={reviewCount}
            helper={reviewCount > 0 ? "存在阻断或需复核项" : "门槛检查通过"}
            tone={reviewCount > 0 ? "orange" : "green"}
          />
          <MetricCard
            icon="briefcase"
            label="岗位结果"
            value={sortedResults.length}
            helper="按岗位聚合后的评估结果"
            tone="purple"
          />
        </section>

        <RunExecutionState detail={detail} />
        <RunStatusPoller
          runId={detail.runId}
          initialStatus={detail.draftStatus}
          initialStage={detail.runStatus?.current_stage ?? null}
          initialCompletedStages={detail.completedStages}
        />

        {canShowActions ? (
          <section className="section evaluation-action-section">
            <div className="section-heading">
              <div>
                <p className="eyebrow">下一步</p>
                <h2>{detail.draftStatus === "draft" ? "开始评估" : "重新处理"}</h2>
                <p className="section-copy">{detail.draftStatus === "draft" ? "确认岗位和简历材料后启动本地评估。" : "失败后可重新评估或从上次中断处继续。"}</p>
              </div>
            </div>
            <RunActionPanel runId={detail.runId} draftStatus={detail.draftStatus} draft={detail.draft} />
          </section>
        ) : null}

        <GateReviewSection detail={detail} />

        <PostRunReviewSection detail={detail} />

        <section className="section evaluation-focus-section">
          <div className="section-heading">
            <div>
              <p className="eyebrow">评估结果</p>
              <h2>匹配、证据与风险</h2>
              <p className="section-copy">每个岗位都把推荐判断、证据依据和不确定项放在同一张复核卡片里。</p>
            </div>
          </div>

          {sortedResults.length > 0 ? (
            <div className="score-matrix ai-score-matrix">
              {sortedResults.map((item) => {
                const scorecard = detail.evaluate.scorecards.find(
                  (candidateScorecard) => candidateScorecard.jd_id === item.jdId && candidateScorecard.variant_id === item.variantId,
                );
                const gate = detail.preflightGates.find((candidateGate) => candidateGate.jd_id === item.jdId);
                const previewEntry = findJdPreviewEntry(detail.jdInputPreviews, item.jdId);
                return (
                  <ScoreMatrixRow
                    key={`${item.jdId}-${item.variantId}`}
                    title={item.title}
                    variantDisplayName={item.variantDisplayName}
                    overallScore={item.overallScore}
                    gapCount={item.gapCount}
                    topReasons={item.topReasons}
                    jdId={item.jdId}
                    runId={detail.runId}
                    scorecard={scorecard}
                    explanation={detail.evaluate.explanations.find(
                      (explanation) => explanation.jd_id === item.jdId && explanation.variant_id === item.variantId,
                    )}
                    strategy={detail.plan.strategies.find((strategy) => strategy.jd_id === item.jdId)}
                    gateStatus={gate?.status}
                    gateReasons={gate?.reasons}
                    jdPreview={previewEntry?.preview}
                    jdPreviewIndex={previewEntry?.index}
                  />
                );
              })}
            </div>
          ) : (
            <div className="empty-state evaluation-empty-state">
              <h3>评估结果尚未生成</h3>
              <p>完成本地评估后，这里会展示岗位匹配、风险和投递建议。</p>
            </div>
          )}
        </section>
      </main>
    </AppShell>
  );
}


function RunExecutionState({ detail }: { detail: RunDetail }) {
  const status = detail.runStatus?.status ?? detail.draftStatus;
  const statusKind = detail.runStatus?.status_kind ?? status;
  const currentStage = detail.runStatus?.current_stage ?? null;
  const displayStage = status === "failed" || status === "partial_failed" ? detail.runStatus?.error_stage ?? currentStage : currentStage;
  const stageLabel = displayStage ? STAGE_LABELS[displayStage] ?? displayStage : "";
  const errorCode = detail.runStatus?.error_code ?? "";
  const rawErrorSummary = detail.runStatus?.error_summary ?? detail.runStatus?.quality_summary ?? "";
  const errorSummary = buildUserFacingRunErrorSummary(
    rawErrorSummary,
    errorCode,
    statusKind,
  );

  if (status === "running" || status === "queued" || status === "partial_running") {
    const runningText = buildRunningText(currentStage);
    return (
      <section className="section run-state-panel running" aria-live="polite">
        <div>
          <p className="eyebrow">运行状态</p>
          <h2>
            <AnimatedRunningText text={runningText} />
          </h2>
          <p className="section-copy">{stageLabel ? `当前阶段：${stageLabel}。页面会读取本地状态更新结果。` : "任务已进入本地执行队列。"}</p>
        </div>
      </section>
    );
  }

  if (status === "partial_failed" || statusKind === "partial_failed") {
    return (
      <section className="section run-state-panel partial" role="status">
        <div>
          <p className="eyebrow">部分未完成</p>
          <h2>部分岗位或输入未完成分析</h2>
          <p className="section-copy">
            {stageLabel ? `影响阶段：${stageLabel}。` : ""}
            {errorSummary || "部分输入未能进入完整流程，请查看解析提示后重试或继续复核已成功结果。"}
          </p>
          <div className="pill-row compact">
            <Link className="secondary-link" href={`/runs/${detail.runId}`}>
              查看当前结果
            </Link>
            <Link className="secondary-link" href="/settings">
              检查模型配置
            </Link>
          </div>
        </div>
      </section>
    );
  }

  if (status === "failed") {
    const structuredAnalysisError = isStructuredAnalysisError(errorCode);
    const networkRelated = isModelNetworkError(errorCode, rawErrorSummary);
    const configRelated =
      !structuredAnalysisError && !networkRelated && (statusKind === "config_error" || statusKind === "model_error" || /^MODEL_/.test(errorCode));
    return (
      <section className="section run-state-panel failed" role="alert">
        <div>
          <p className="eyebrow">运行失败</p>
          <h2>
            {networkRelated
              ? "模型请求超时"
              : configRelated
              ? "模型服务配置失败"
              : structuredAnalysisError
                ? "结构化分析失败"
                : statusKind === "parse_error"
                  ? "输入解析失败"
                  : "评估未完成"}
          </h2>
          <p className="section-copy">
            {stageLabel ? `失败阶段：${stageLabel}。` : "失败阶段：未知。"}
            {errorSummary ? `原因：${errorSummary}` : "请查看本地运行日志确认原因。"}
          </p>
          {configRelated ? (
            <div className="notice-strip warning">
              <strong>当前任务未完成</strong>
              <span>API Key 可能无权限、不可用，或当前 provider/model 没有开通。检查配置后重新运行。</span>
              <Link className="secondary-link" href="/settings">
                检查配置
              </Link>
            </div>
          ) : null}
          {networkRelated ? (
            <div className="notice-strip warning">
              <strong>结构化分析长请求未返回</strong>
              <span>先减少 JD 数量或裁短简历；也可以切换更快的分析器模型，或提高 SHOTGUNCV_ANALYZER_TIMEOUT_SEC 后重试。</span>
            </div>
          ) : null}
        </div>
      </section>
    );
  }

  if (detail.completedStages.includes("report")) {
    return (
      <section className="section run-state-panel success">
        <div>
          <p className="eyebrow">运行状态</p>
          <h2>结果已就绪</h2>
          <p className="section-copy">评估、策略和报告产物已生成，可以进入复核。</p>
        </div>
      </section>
    );
  }

  if (status === "draft") {
    return (
      <section className="section run-state-panel idle">
        <div>
          <p className="eyebrow">运行状态</p>
          <h2>尚未开始</h2>
          <p className="section-copy">确认岗位和简历材料后，点击开始评估启动本地流程。</p>
        </div>
      </section>
    );
  }

  return null;
}


function buildUserFacingRunErrorSummary(summary: string, errorCode: string, statusKind: string): string {
  const rawSummary = summary.trim();
  if (errorCode === "STRUCTURED_ANALYSIS_INVALID" || rawSummary.includes("Structured analysis validation failed")) {
    if (rawSummary.includes("CV and JD structured outputs are missing") || rawSummary.includes("candidate_profile or jd_profiles")) {
      return "结构化分析失败：简历信息和 JD 信息都没有被模型转换成可用结构。请检查简历是否包含可识别的经历、项目和技能，JD 是否包含岗位职责和任职要求，然后修改后重试。";
    }
    if (rawSummary.includes("CV structured output")) {
      return "结构化分析失败：简历信息没有被模型转换成可用结构。请检查简历文本是否清晰，并补充经历、项目、技能或教育等可识别内容后重试。";
    }
    if (rawSummary.includes("JD structured output")) {
      return "结构化分析失败：JD 信息没有被模型转换成可用结构。请补充岗位名称、职责、硬性要求和加分项后重试。";
    }
    return "结构化分析失败：模型返回内容不符合简历/JD 分析结构。请检查简历和 JD 内容是否完整、清晰，然后重试。";
  }
  if (statusKind === "parse_error") {
    return "输入解析失败：请检查上传的简历 PDF/JD 文本是否可复制、非空且没有乱码，然后重新上传或补充可读文本。";
  }
  if (isModelNetworkError(errorCode, rawSummary)) {
    return "模型请求超时或网络连接失败：结构化分析已经开始，但模型没有稳定返回。可先只保留 1 个 JD、裁短简历，切换更快的分析器模型，或提高 SHOTGUNCV_ANALYZER_TIMEOUT_SEC 后重试。";
  }
  if (statusKind === "model_error" || errorCode.startsWith("MODEL_")) {
    return "模型服务调用失败：请检查 API Key、provider、model 权限和网络连通性，确认配置后重试。";
  }
  return sanitizeUserFacingText(rawSummary);
}


function AnimatedRunningText({ text }: { text: string }) {
  return (
    <span className="running-wave-text" aria-label={text}>
      {Array.from(text).map((char, index) => (
        <span key={`${char}-${index}`} style={{ animationDelay: `${index * 80}ms` }} aria-hidden="true">
          {char}
        </span>
      ))}
    </span>
  );
}


function findJdPreviewEntry(previews: RunDetail["jdInputPreviews"], jdId: string) {
  const explicitIndex = previews.findIndex((preview) => preview.jdId === jdId);
  if (explicitIndex >= 0) {
    return { preview: previews[explicitIndex], index: previews[explicitIndex].previewIndex ?? explicitIndex };
  }

  const match = /^jd-(\d+)$/i.exec(jdId);
  if (!match) {
    return null;
  }
  const fallbackIndex = Number.parseInt(match[1], 10) - 1;
  const preview = previews[fallbackIndex];
  return preview ? { preview, index: preview.previewIndex ?? fallbackIndex } : null;
}


function buildRunningText(stage: string | null): string {
  if (stage === "generate" || stage === "plan" || stage === "report") {
    return "生成中...";
  }
  if (stage === "evaluate" || stage === "analyze") {
    return "分析中...";
  }
  return "思考中...";
}


function buildDetailTitle(label: string, topTitle?: string): string {
  const displayLabel = formatRunDisplayName(label);
  if (displayLabel !== "未命名投递") {
    return displayLabel;
  }
  return topTitle || "岗位评估详情";
}


function GateReviewSection({ detail }: { detail: RunDetail }) {
  const gateItems = detail.preflightGates.filter((gate) => gate.status !== "pass" || gate.reasons.length > 0);
  if (gateItems.length === 0) {
    return null;
  }
  return (
    <section className="section evaluation-focus-section">
      <div className="section-heading">
        <div>
          <p className="eyebrow">复核事项</p>
          <h2>需要确认的门槛</h2>
          <p className="section-copy">只展示会影响投递判断的缺口和风险，不展开底层产物字段。</p>
        </div>
      </div>
      <div className="gate-grid review-gate-grid">
        {gateItems.map((gate) => {
          const requirements = detail.requirementMatrix.filter((item) => item.jd_id === gate.jd_id);
          return (
            <article key={gate.jd_id} className={`detail-card gate-card gate-${gate.status}`}>
              <div className="gate-card-heading">
                <h3>{findJdTitle(detail, gate.jd_id)}</h3>
                <span className={buildGateClassName(gate.status)}>{formatGateStatus(gate.status)}</span>
              </div>
              {gate.reasons.length > 0 ? <p className="risk-line">{gate.reasons.map(formatUserText).join(" / ")}</p> : null}
              {requirements.length > 0 ? (
                <ul className="requirement-list">
                  {requirements.slice(0, 4).map((item) => (
                    <li key={item.requirement_id}>
                      {formatRequirementTier(item.tier)}
                      {" · "}
                      {formatEvidenceStatus(item.evidence_status)}
                      {" · "}
                      {item.requirement_text}
                    </li>
                  ))}
                </ul>
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}


function PostRunReviewSection({ detail }: { detail: RunDetail }) {
  const review = detail.review.postRunReview;
  if (!review) {
    return null;
  }
  const citations = review.evidence_citations ?? [];
  const questions = review.interview_questions ?? [];
  const tasks = review.revision_tasks ?? [];
  return (
    <section className="section evaluation-focus-section">
      <div className="section-heading">
        <div>
          <p className="eyebrow">复盘产物</p>
          <h2>面试准备与复盘建议</h2>
          <p className="section-copy">只读取 review artifact，展示证据摘要、面试问题和安全修订任务。</p>
        </div>
      </div>
      <div className="gate-grid review-gate-grid">
        <article className="detail-card gate-card">
          <div className="gate-card-heading">
            <h3>证据依据</h3>
            <span className="status-chip success">{review.validation?.fabrication_policy ?? "reviewed"}</span>
          </div>
          <ul className="requirement-list">
            {citations.slice(0, 4).map((citation, index) => (
              <li key={`${citation.source_type ?? "source"}-${index}`}>
                {formatUserText(citation.provenance_summary || citation.artifact_path || "证据产物")}
              </li>
            ))}
          </ul>
        </article>
        <article className="detail-card gate-card">
          <div className="gate-card-heading">
            <h3>面试准备</h3>
            <span className="status-chip">{questions.length}</span>
          </div>
          <ul className="requirement-list">
            {questions.slice(0, 4).map((item, index) => (
              <li key={`${item.jd_id ?? "jd"}-${index}`}>{item.question}</li>
            ))}
          </ul>
        </article>
        <article className="detail-card gate-card">
          <div className="gate-card-heading">
            <h3>安全修订任务</h3>
            <span className="status-chip">{tasks.length}</span>
          </div>
          <ul className="requirement-list">
            {tasks.slice(0, 4).map((item, index) => (
              <li key={`${item.jd_id ?? "jd"}-${index}`}>{item.task}</li>
            ))}
          </ul>
        </article>
      </div>
    </section>
  );
}


function buildDisplayStatus(detail: RunDetail): string {
  if (detail.runStatus?.status_kind === "config_error") {
    return "配置错误";
  }
  if (isModelNetworkError(detail.runStatus?.error_code ?? "", detail.runStatus?.error_summary ?? "")) {
    return "模型请求超时";
  }
  if (isStructuredAnalysisError(detail.runStatus?.error_code ?? "")) {
    return "结构化分析失败";
  }
  if (detail.runStatus?.status_kind === "model_error") {
    return "模型服务错误";
  }
  if (detail.runStatus?.status_kind === "parse_error") {
    return "解析错误";
  }
  if (detail.draftStatus === "partial_failed" || detail.runStatus?.status_kind === "partial_failed") {
    return "部分未完成";
  }
  if (detail.draftStatus === "done" && detail.runStatus?.quality_status === "warning") {
    return "完成，建议复核提醒项";
  }
  return STATUS_LABELS[detail.draftStatus] ?? detail.draftStatus;
}


function buildPrimaryConclusion(
  topResult: RunDetail["evaluate"]["topVariants"][number] | undefined,
  reviewCount: number,
  riskCount: number,
  detail?: RunDetail,
): string {
  if (detail?.draftStatus === "failed") {
    if (isStructuredAnalysisError(detail.runStatus?.error_code ?? "")) {
      return "检查简历和 JD 内容";
    }
    if (isModelNetworkError(detail.runStatus?.error_code ?? "", detail.runStatus?.error_summary ?? "")) {
      return "调整分析器后重试";
    }
    if (detail.runStatus?.status_kind === "model_error" || detail.runStatus?.status_kind === "config_error") {
      return "检查模型配置后重试";
    }
    if (detail.runStatus?.status_kind === "parse_error") {
      return "重新上传可识别文件";
    }
    return "任务未完成";
  }
  if (detail?.draftStatus === "partial_failed" || detail?.runStatus?.status_kind === "partial_failed") {
    return "先处理未完成项";
  }
  if (!topResult) {
    return "等待评估结果";
  }
  if (reviewCount > 0) {
    return "先复核门槛，再决定投递";
  }
  if (riskCount > 0) {
    return "存在风险，建议谨慎推进";
  }
  return `优先关注 ${topResult.title}`;
}


function isStructuredAnalysisError(errorCode: string): boolean {
  return errorCode === "STRUCTURED_ANALYSIS_INVALID";
}


function isModelNetworkError(errorCode: string, summary = ""): boolean {
  const text = summary.toLowerCase();
  return errorCode === "MODEL_NETWORK_ERROR" || text.includes("timed out") || text.includes("timeout") || text.includes("network connection failed");
}


function countHighRiskScores(detail: RunDetail): number {
  return detail.evaluate.scorecards.filter((scorecard) => (scorecard.risk_score ?? scorecard.gap_risk_score ?? 0) >= 0.7).length;
}


function countReviewItems(detail: RunDetail): number {
  return detail.preflightGates.filter((gate) => gate.status === "blocked" || gate.status === "needs_review").length;
}


function findJdTitle(detail: RunDetail, jdId: string): string {
  const topVariant = detail.evaluate.topVariants.find((item) => item.jdId === jdId);
  const profile = detail.analyze.jdProfiles.find((item) => item.jd_id === jdId);
  return topVariant?.title || [profile?.company, profile?.title].filter(Boolean).join(" - ") || "目标岗位";
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


function formatRequirementTier(tier: string): string {
  const labels: Record<string, string> = {
    hard_gate: "硬性要求",
    high_priority: "高优先级",
    medium_priority: "中优先级",
    nice_to_have: "加分项",
  };
  return labels[tier] ?? formatUserText(tier);
}


function formatEvidenceStatus(status: string): string {
  const labels: Record<string, string> = {
    verified: "已有证据",
    inferred: "可推断",
    missing: "缺少证据",
    mismatch: "不匹配",
    simulatable: "可补强",
    forbidden_to_fabricate: "不能编造",
  };
  return labels[status] ?? formatUserText(status);
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
  return sanitizeUserFacingText(value.replace(/\b[a-z]+(?:_[a-z0-9]+)+\b/g, (token) => labels[token] ?? token.replace(/_/g, " ")));
}
