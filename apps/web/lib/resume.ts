import type { PreflightGate, RequirementEvidence } from "./types";
import { loadRunDetail, listRuns } from "./runs";

type ResumeConstraintCategory = "可安全改写" | "待核实模拟补强" | "禁止编造缺口";

export type ResumeWorkspaceVariant = {
  variantId: string;
  variantDisplayName: string;
  summary: string;
  targetJdLabels: string[];
  safeRewriteItems: string[];
  simulatedSupplementItems: string[];
  forbiddenGapItems: string[];
  sourceLabel: string;
};

export type ResumeWorkspaceConstraint = {
  jdId: string;
  category: ResumeConstraintCategory;
  requirementText: string;
  evidenceRefs: string[];
  gateStatus: string;
  gateReasons: string[];
  sourceLabel: string;
};

export type ResumeWorkspaceRow = {
  runId: string;
  label: string;
  lastModified: string;
  status: string;
  completedStageCount: number;
  artifactMode: "v0.5.7" | "legacy";
  variantCount: number;
  evidenceConstraintCount: number;
  preflightStatus: string;
  warningText: string;
  nextAction: string;
  detailHref: string;
  reportHref: string | null;
  uploadHref: string;
  variants: ResumeWorkspaceVariant[];
  constraints: ResumeWorkspaceConstraint[];
  sourceLabel: string;
};

export type ResumeWorkspaceSummary = {
  totalRuns: number;
  draftRuns: number;
  activeRuns: number;
  failedRuns: number;
  doneRuns: number;
  warningRuns: number;
  variantCount: number;
  constraintCount: number;
};

export type ResumeWorkspace = {
  rows: ResumeWorkspaceRow[];
  summary: ResumeWorkspaceSummary;
};

export async function loadResumeWorkspace(): Promise<ResumeWorkspace> {
  const runs = await listRuns();
  const rows = await Promise.all(
    runs.map(async (run) => {
      const detail = await loadRunDetail(run.runId);
      const variants = detail.generate.variants.map((variant) => ({
        variantId: variant.variant_id,
        variantDisplayName: variant.variantDisplayName,
        summary: variant.summary,
        targetJdLabels: variant.target_jd_ids.map((jdId) => buildJdLabel(jdId, detail.analyze.jdProfiles)),
        safeRewriteItems: variant.safe_rewrites ?? [],
        simulatedSupplementItems: variant.simulated_supplements ?? [],
        forbiddenGapItems: variant.forbidden_gaps ?? [],
        sourceLabel: "来源：简历版本",
      }));
      const constraints = buildConstraints(detail.requirementMatrix, detail.preflightGates);
      const preflightStatus = summarizePreflightStatus(detail.preflightGates);
      const artifactMode: ResumeWorkspaceRow["artifactMode"] =
        detail.requirementMatrix.length > 0 ||
        detail.preflightGates.length > 0 ||
        variants.some(
          (variant) =>
            variant.safeRewriteItems.length > 0 ||
            variant.simulatedSupplementItems.length > 0 ||
            variant.forbiddenGapItems.length > 0,
        )
          ? "v0.5.7"
          : "legacy";

      return {
        runId: run.runId,
        label: run.label || run.runId,
        lastModified: run.lastModified,
        status: run.draftStatus,
        completedStageCount: run.completedStages.length,
        artifactMode,
        variantCount: variants.length,
        evidenceConstraintCount: constraints.length,
        preflightStatus,
        warningText: run.runStatus?.error_summary ?? run.runStatus?.quality_summary ?? "",
        nextAction: buildNextAction(run.draftStatus, run.completedStages.length, preflightStatus),
        detailHref: `/runs/${run.runId}`,
        reportHref: run.completedStages.includes("report") ? `/runs/${run.runId}/report` : null,
        uploadHref: "/upload",
        variants,
        constraints,
        sourceLabel: "来源：投递策略 / 运行状态",
      };
    }),
  );

  const sortedRows = rows.sort(
    (left, right) =>
      right.variantCount - left.variantCount ||
      right.evidenceConstraintCount - left.evidenceConstraintCount ||
      right.lastModified.localeCompare(left.lastModified),
  );

  return {
    rows: sortedRows,
    summary: {
      totalRuns: sortedRows.length,
      draftRuns: sortedRows.filter((row) => row.status === "draft").length,
      activeRuns: sortedRows.filter((row) => row.status === "running" || row.status === "queued").length,
      failedRuns: sortedRows.filter((row) => row.status === "failed").length,
      doneRuns: sortedRows.filter((row) => row.status === "done").length,
      warningRuns: sortedRows.filter((row) => row.warningText).length,
      variantCount: sortedRows.reduce((sum, row) => sum + row.variantCount, 0),
      constraintCount: sortedRows.reduce((sum, row) => sum + row.evidenceConstraintCount, 0),
    },
  };
}

function buildConstraints(
  requirements: RequirementEvidence[],
  gates: PreflightGate[],
): ResumeWorkspaceConstraint[] {
  const gateByJd = new Map(gates.map((gate) => [gate.jd_id, gate]));
  return requirements.map((item) => {
    const gate = gateByJd.get(item.jd_id);
    return {
      jdId: item.jd_id,
      category: categorizeRequirement(item),
      requirementText: item.requirement_text,
      evidenceRefs: item.evidence_refs,
      gateStatus: gate?.status ?? "legacy",
      gateReasons: gate?.reasons ?? [],
      sourceLabel: "来源：证据矩阵 / 投递前门槛",
    };
  });
}

function categorizeRequirement(item: RequirementEvidence): ResumeConstraintCategory {
  if (item.evidence_status === "simulatable" || item.fabrication_policy === "simulate_allowed") {
    return "待核实模拟补强";
  }
  if (
    item.evidence_status === "missing" ||
    item.evidence_status === "mismatch" ||
    item.evidence_status === "forbidden_to_fabricate"
  ) {
    return "禁止编造缺口";
  }
  return "可安全改写";
}

function summarizePreflightStatus(gates: PreflightGate[]): string {
  if (gates.some((gate) => gate.status === "blocked")) {
    return "blocked";
  }
  if (gates.some((gate) => gate.status === "needs_review")) {
    return "needs_review";
  }
  if (gates.some((gate) => gate.status === "pass")) {
    return "pass";
  }
  return "legacy";
}

function buildNextAction(status: string, completedStageCount: number, preflightStatus: string): string {
  if (status === "draft") {
    return "进入详情页运行本地流程";
  }
  if (status === "failed") {
    return "处理失败后重试或续跑";
  }
  if (status === "running" || status === "queued") {
    return "等待本地流程完成";
  }
  if (preflightStatus === "blocked" || preflightStatus === "needs_review") {
    return "先补证据再投递";
  }
  if (completedStageCount >= 6) {
    return "查看报告或评估矩阵";
  }
  return "继续运行后续阶段";
}

function buildJdLabel(jdId: string, jdProfiles: Array<{ jd_id: string; title: string; company: string }>): string {
  const jd = jdProfiles.find((candidate) => candidate.jd_id === jdId);
  if (!jd) {
    return jdId;
  }
  return [jd.company, jd.title].filter(Boolean).join(" - ") || jdId;
}
