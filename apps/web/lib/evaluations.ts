import type { ApplicationStrategy, PreflightGate, RankingExplanation, RequirementEvidence, ScoreCard } from "./types";
import { loadRunDetail, listRuns } from "./runs";

export {
  DEFAULT_EVALUATION_FILTERS,
  filterEvaluationResults,
  sortEvaluationResults,
  type EvaluationFilterState,
  type EvaluationSortKey,
} from "./evaluation-filters";

export type EvaluationResult = {
  runId: string;
  runLabel: string;
  lastModified: string;
  jdId: string;
  title: string;
  variantId: string;
  variantDisplayName: string;
  gateStatus: string;
  gateReasons: string[];
  finalScore: number | null;
  verifiedFitScore: number | null;
  rewritePotentialScore: number | null;
  riskScore: number | null;
  applyDecision: string;
  priorityRank: number | null;
  provider: string;
  model: string;
  artifactMode: "v0.5.7" | "legacy";
  topReasons: string[];
  evidenceRefs: string[];
  riskFlags: string[];
  requirementSummaries: string[];
  strategySummary: string;
  detailHref: string;
  reportHref: string;
};

export async function loadEvaluationResults(): Promise<EvaluationResult[]> {
  const runs = await listRuns();
  const evaluableRuns = runs.filter((run) => run.completedStages.includes("evaluate"));
  const nestedResults = await Promise.all(
    evaluableRuns.map(async (run) => {
      const detail = await loadRunDetail(run.runId);
      return detail.evaluate.topVariants.map((item) => {
        const scorecard = detail.evaluate.scorecards.find(
          (candidate) => candidate.jd_id === item.jdId && candidate.variant_id === item.variantId,
        );
        const explanation = detail.evaluate.explanations.find(
          (candidate) => candidate.jd_id === item.jdId && candidate.variant_id === item.variantId,
        );
        const gate = detail.preflightGates.find((candidate) => candidate.jd_id === item.jdId);
        const requirements = detail.requirementMatrix.filter((candidate) => candidate.jd_id === item.jdId);
        const strategy = detail.plan.strategies.find((candidate) => candidate.jd_id === item.jdId);
        return buildEvaluationResult({
          runId: run.runId,
          runLabel: run.label || run.runId,
          lastModified: run.lastModified,
          jdId: item.jdId,
          title: item.title || item.jdId,
          variantId: item.variantId,
          variantDisplayName: item.variantDisplayName,
          topReasons: item.topReasons,
          scorecard,
          explanation,
          gate,
          requirements,
          strategy,
        });
      });
    }),
  );
  return nestedResults.flat().sort((left, right) => right.lastModified.localeCompare(left.lastModified));
}

function buildEvaluationResult({
  runId,
  runLabel,
  lastModified,
  jdId,
  title,
  variantId,
  variantDisplayName,
  topReasons,
  scorecard,
  explanation,
  gate,
  requirements,
  strategy,
}: {
  runId: string;
  runLabel: string;
  lastModified: string;
  jdId: string;
  title: string;
  variantId: string;
  variantDisplayName: string;
  topReasons: string[];
  scorecard?: ScoreCard;
  explanation?: RankingExplanation;
  gate?: PreflightGate;
  requirements: RequirementEvidence[];
  strategy?: ApplicationStrategy;
}): EvaluationResult {
  const hasV057Artifacts =
    scorecard?.verified_fit_score !== undefined ||
    scorecard?.rewrite_potential_score !== undefined ||
    scorecard?.risk_score !== undefined ||
    Boolean(scorecard?.gate_status) ||
    Boolean(gate);
  const gateStatus = scorecard?.gate_status ?? gate?.status ?? "legacy";
  const requirementSummaries = requirements.slice(0, 3).map((item) =>
    [formatRequirementTier(item.tier), formatEvidenceStatus(item.evidence_status), item.requirement_text]
      .filter(Boolean)
      .join(" / "),
  );

  return {
    runId,
    runLabel,
    lastModified,
    jdId,
    title,
    variantId,
    variantDisplayName,
    gateStatus,
    gateReasons: uniqueStrings([...(scorecard?.gate_reasons ?? []), ...(gate?.reasons ?? [])]),
    finalScore: normalizeScore(scorecard?.final_overall_score ?? scorecard?.overall_score ?? null),
    verifiedFitScore: normalizeScore(scorecard?.verified_fit_score),
    rewritePotentialScore: normalizeScore(scorecard?.rewrite_potential_score),
    riskScore: normalizeScore(scorecard?.risk_score ?? scorecard?.gap_risk_score ?? null),
    applyDecision: strategy?.apply_decision ?? "review",
    priorityRank: typeof strategy?.priority_rank === "number" ? strategy.priority_rank : null,
    provider: scorecard?.provider ?? "unknown",
    model: scorecard?.model ?? "",
    artifactMode: hasV057Artifacts ? "v0.5.7" : "legacy",
    topReasons: uniqueStrings(topReasons),
    evidenceRefs: uniqueStrings([...(explanation?.evidence_refs ?? []), ...requirements.flatMap((item) => item.evidence_refs)]),
    riskFlags: uniqueStrings([...(explanation?.risk_flags ?? []), ...(strategy?.watchouts ?? []), ...(scorecard?.guardrail_flags ?? [])]),
    requirementSummaries,
    strategySummary: strategy?.reason_summary ?? explanation?.decision_summary ?? scorecard?.judge_rationale ?? "",
    detailHref: `/runs/${runId}#evaluation-${jdId}`,
    reportHref: `/runs/${runId}/report`,
  };
}

function normalizeScore(value: number | null | undefined): number | null {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return null;
  }
  return Math.max(0, Math.min(1, value));
}

function uniqueStrings(values: string[]): string[] {
  const seen = new Set<string>();
  const results: string[] = [];
  values.forEach((value) => {
    const normalized = value.trim();
    if (!normalized || seen.has(normalized)) {
      return;
    }
    seen.add(normalized);
    results.push(normalized);
  });
  return results;
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
