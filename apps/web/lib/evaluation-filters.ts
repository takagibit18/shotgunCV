import type { EvaluationResult } from "./evaluations";

export type EvaluationFilterState = {
  query: string;
  gate: string;
  risk: string;
  provider: string;
  decision: string;
  score: string;
};

export type EvaluationSortKey = "recent" | "score" | "risk" | "priority" | "title";

export const DEFAULT_EVALUATION_FILTERS: EvaluationFilterState = {
  query: "",
  gate: "all",
  risk: "all",
  provider: "all",
  decision: "all",
  score: "all",
};

export function filterEvaluationResults(
  results: EvaluationResult[],
  filters: EvaluationFilterState,
): EvaluationResult[] {
  const query = filters.query.trim().toLowerCase();
  return results.filter((item) => {
    const queryText = [
      item.runId,
      item.runLabel,
      item.jdId,
      item.title,
      item.variantId,
      item.variantDisplayName,
      item.provider,
      item.applyDecision,
      item.strategySummary,
      ...item.topReasons,
      ...item.evidenceRefs,
      ...item.riskFlags,
      ...item.gateReasons,
      ...item.requirementSummaries,
    ]
      .join(" ")
      .toLowerCase();
    return (
      (!query || queryText.includes(query)) &&
      (filters.gate === "all" || item.gateStatus === filters.gate) &&
      (filters.provider === "all" || item.provider === filters.provider) &&
      (filters.decision === "all" || item.applyDecision === filters.decision) &&
      (filters.risk === "all" || riskBucket(item.riskScore) === filters.risk) &&
      (filters.score === "all" || scoreBucket(item.finalScore) === filters.score)
    );
  });
}

export function sortEvaluationResults(
  results: EvaluationResult[],
  sortKey: EvaluationSortKey,
): EvaluationResult[] {
  return results.slice().sort((left, right) => compareEvaluationResults(left, right, sortKey));
}

function compareEvaluationResults(left: EvaluationResult, right: EvaluationResult, sortKey: EvaluationSortKey): number {
  if (sortKey === "score") {
    return compareNumbers(right.finalScore, left.finalScore) || right.lastModified.localeCompare(left.lastModified);
  }
  if (sortKey === "risk") {
    return compareNumbers(right.riskScore, left.riskScore) || right.lastModified.localeCompare(left.lastModified);
  }
  if (sortKey === "priority") {
    return compareNumbers(left.priorityRank, right.priorityRank) || compareNumbers(right.finalScore, left.finalScore);
  }
  if (sortKey === "title") {
    return left.title.localeCompare(right.title, "zh-Hans-CN") || left.runId.localeCompare(right.runId);
  }
  return right.lastModified.localeCompare(left.lastModified);
}

function compareNumbers(left: number | null, right: number | null): number {
  if (left === null && right === null) {
    return 0;
  }
  if (left === null) {
    return 1;
  }
  if (right === null) {
    return -1;
  }
  return left - right;
}

function riskBucket(value: number | null): string {
  if (value === null) {
    return "unknown";
  }
  if (value >= 0.7) {
    return "high";
  }
  if (value >= 0.4) {
    return "medium";
  }
  return "low";
}

function scoreBucket(value: number | null): string {
  if (value === null) {
    return "unknown";
  }
  if (value >= 0.75) {
    return "high";
  }
  if (value >= 0.5) {
    return "medium";
  }
  return "low";
}
