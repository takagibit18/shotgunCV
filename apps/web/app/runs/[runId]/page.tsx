import React from "react";
import Link from "next/link";

import { AppShell, Icon, MetricCard } from "../../AppShell";
import { STAGE_LABELS, STATUS_LABELS } from "../../../lib/labels";
import { loadRunDetail, type JdInputPreview } from "../../../lib/runs";
import { RunActionPanel } from "./RunActionPanel";
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
  const displayTitle = detail.label || topResult?.title || "岗位评估详情";
  const displayStatus = buildDisplayStatus(detail);
  const riskCount = countHighRiskScores(detail);
  const reviewCount = countReviewItems(detail);
  const topScore = topResult ? `${Math.round(topResult.overallScore * 100)}%` : "--";
  const canShowActions = detail.draftStatus === "draft" || detail.draftStatus === "failed";

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
              <strong>{buildPrimaryConclusion(topResult, reviewCount, riskCount)}</strong>
              <small>{displayStatus}</small>
            </div>
            <Link href={`/runs/${detail.runId}/report`} className="primary-link icon-link">
              <Icon name="document" />
              查看报告
            </Link>
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

        <JdPreviewSection runId={detail.runId} previews={detail.jdInputPreviews} />
        <GateReviewSection detail={detail} />

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
              {sortedResults.map((item) => (
                <ScoreMatrixRow
                  key={`${item.jdId}-${item.variantId}`}
                  title={item.title}
                  variantDisplayName={item.variantDisplayName}
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
  const currentStage = detail.runStatus?.current_stage ?? null;
  const stageLabel = currentStage ? STAGE_LABELS[currentStage] ?? currentStage : "";

  if (status === "running" || status === "queued") {
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

  if (status === "failed") {
    return (
      <section className="section run-state-panel failed" role="alert">
        <div>
          <p className="eyebrow">运行失败</p>
          <h2>评估未完成</h2>
          <p className="section-copy">
            {stageLabel ? `失败阶段：${stageLabel}。` : "失败阶段：未知。"}
            {detail.runStatus?.error_summary ? `原因：${detail.runStatus.error_summary}` : "请查看本地运行日志确认原因。"}
          </p>
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


function buildRunningText(stage: string | null): string {
  if (stage === "generate" || stage === "plan" || stage === "report") {
    return "生成中...";
  }
  if (stage === "evaluate" || stage === "analyze") {
    return "分析中...";
  }
  return "思考中...";
}


function JdPreviewSection({ runId, previews }: { runId: string; previews: JdInputPreview[] }) {
  if (previews.length === 0) {
    return null;
  }
  return (
    <section className="section evaluation-focus-section jd-context-section">
      <div className="section-heading">
        <div>
          <p className="eyebrow">岗位输入</p>
          <h2>JD 详情</h2>
          <p className="section-copy">截图可点击放大；文本 JD 可展开查看原始岗位描述。</p>
        </div>
      </div>
      <div className="jd-preview-grid">
        {previews.map((preview, index) => (
          <JdPreviewCard key={`${preview.originalName}-${index}`} runId={runId} preview={preview} index={index} />
        ))}
      </div>
    </section>
  );
}


function JdPreviewCard({ runId, preview, index }: { runId: string; preview: JdInputPreview; index: number }) {
  if (preview.kind === "image" && preview.imageDataUrl) {
    return (
      <article className="jd-preview-card image">
        <div className="jd-preview-card-heading">
          <span className="semantic-icon blue" aria-hidden="true">
            <Icon name="image-upload" />
          </span>
          <div>
            <h3>{preview.label}</h3>
            <p>{preview.note ?? "点击截图可放大查看"}</p>
          </div>
        </div>
        <Link href={`/runs/${runId}/jd-preview/${index}`} className="jd-image-preview-link" aria-label={`打开 ${preview.label} 图片预览`}>
            <img src={preview.imageDataUrl} alt={`${preview.label} 截图预览`} />
            <span>打开大图预览</span>
        </Link>
      </article>
    );
  }

  if (preview.kind === "text" && preview.text) {
    return (
      <article className="jd-preview-card text">
        <div className="jd-preview-card-heading">
          <span className="semantic-icon green" aria-hidden="true">
            <Icon name="file" />
          </span>
          <div>
            <h3>{preview.label}</h3>
            <p>岗位文本已读取，可展开核对细节。</p>
          </div>
        </div>
        <details className="jd-text-preview">
          <summary className="secondary-link icon-link">
            <Icon name="eye" />
            查看 JD 详情
          </summary>
          <pre>{preview.text}</pre>
        </details>
      </article>
    );
  }

  return (
    <article className="jd-preview-card metadata">
      <div className="jd-preview-card-heading">
        <span className="semantic-icon orange" aria-hidden="true">
          <Icon name="alert-triangle" />
        </span>
        <div>
          <h3>{preview.label}</h3>
          <p>{preview.note ?? "当前岗位输入暂无可直接展示的文本或截图。"}</p>
        </div>
      </div>
    </article>
  );
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


function buildDisplayStatus(detail: RunDetail): string {
  if (detail.draftStatus === "done" && detail.runStatus?.quality_status === "warning") {
    return "完成，建议复核提醒项";
  }
  return STATUS_LABELS[detail.draftStatus] ?? detail.draftStatus;
}


function buildPrimaryConclusion(
  topResult: RunDetail["evaluate"]["topVariants"][number] | undefined,
  reviewCount: number,
  riskCount: number,
): string {
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
  return value.replace(/\b[a-z]+(?:_[a-z0-9]+)+\b/g, (token) => labels[token] ?? token.replace(/_/g, " "));
}
