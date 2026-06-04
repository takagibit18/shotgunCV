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
  requirementId: string;
  category: ResumeConstraintCategory;
  requirementText: string;
  evidenceRefs: string[];
  gateStatus: string;
  gateReasons: string[];
  userOverride: {
    action: string;
    note: string;
    updatedAt: string;
  } | null;
  sourceLabel: string;
};

export type ResumePreviewSection = {
  title: string;
  content: string;
  evidenceRefs: string[];
  rewriteStrategy: string;
  verificationStatus: string;
};

export type GeneratedResumePreview = {
  resumeId: string;
  displayName: string;
  targetLabel: string;
  status: string;
  isDeliverable: boolean;
  markdown: string;
  exportFileName: string;
  sections: ResumePreviewSection[];
  forbiddenItems: string[];
  toVerifyItems: string[];
  candidateEvidence: string[];
  generatedFrom: string[];
  userConfirmations: string[];
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
  generatedResumeCount: number;
  evidenceConstraintCount: number;
  preflightStatus: string;
  warningText: string;
  nextAction: string;
  detailHref: string;
  reportHref: string | null;
  uploadHref: string;
  variants: ResumeWorkspaceVariant[];
  constraints: ResumeWorkspaceConstraint[];
  generatedResumes: GeneratedResumePreview[];
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
  generatedResumeCount: number;
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
      const displayLabel = run.label || "未命名投递";
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
      const constraints = buildConstraints(
        detail.requirementMatrix,
        detail.preflightGates,
        detail.review.userEvidenceOverrides?.overrides ?? [],
      );
      const preflightStatus = summarizePreflightStatus(detail.preflightGates);
      const generatedResumes = buildGeneratedResumes({
        runLabel: displayLabel,
        generatedResumes: detail.generate.generatedResumes,
        jdProfiles: detail.analyze.jdProfiles,
        constraints,
        preflightStatus,
      });
      const artifactMode: ResumeWorkspaceRow["artifactMode"] =
        detail.requirementMatrix.length > 0 ||
        detail.preflightGates.length > 0 ||
        generatedResumes.length > 0 ||
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
        label: displayLabel,
        lastModified: run.lastModified,
        status: run.draftStatus,
        completedStageCount: run.completedStages.length,
        artifactMode,
        variantCount: variants.length,
        generatedResumeCount: generatedResumes.length,
        evidenceConstraintCount: constraints.length,
        preflightStatus,
        warningText: run.runStatus?.error_summary ?? run.runStatus?.quality_summary ?? "",
        nextAction: buildNextAction(run.draftStatus, run.completedStages.length, preflightStatus),
        detailHref: `/runs/${run.runId}`,
        reportHref: run.completedStages.includes("report") ? `/runs/${run.runId}/report` : null,
        uploadHref: "/upload",
        variants,
        constraints,
        generatedResumes,
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
      generatedResumeCount: sortedRows.reduce((sum, row) => sum + row.generatedResumeCount, 0),
      constraintCount: sortedRows.reduce((sum, row) => sum + row.evidenceConstraintCount, 0),
    },
  };
}

function buildConstraints(
  requirements: RequirementEvidence[],
  gates: PreflightGate[],
  overrides: Array<{ jd_id: string; requirement_id: string; action: string; note: string; updated_at: string }>,
): ResumeWorkspaceConstraint[] {
  const gateByJd = new Map(gates.map((gate) => [gate.jd_id, gate]));
  const overrideByRequirement = new Map(
    overrides.map((override) => [`${override.jd_id}:${override.requirement_id}`, override]),
  );
  return requirements.map((item) => {
    const gate = gateByJd.get(item.jd_id);
    const userOverride = overrideByRequirement.get(`${item.jd_id}:${item.requirement_id}`);
    return {
      jdId: item.jd_id,
      requirementId: item.requirement_id,
      category: categorizeRequirement(item),
      requirementText: item.requirement_text,
      evidenceRefs: item.evidence_refs,
      gateStatus: gate?.status ?? "legacy",
      gateReasons: gate?.reasons ?? [],
      userOverride: userOverride
        ? {
            action: formatOverrideAction(userOverride.action),
            note: userOverride.note,
            updatedAt: userOverride.updated_at,
          }
        : null,
      sourceLabel: "来源：证据矩阵 / 投递前门槛",
    };
  });
}

function buildGeneratedResumes({
  runLabel,
  generatedResumes,
  jdProfiles,
  constraints,
  preflightStatus,
}: {
  runLabel: string;
  generatedResumes: Array<{
    resume_id?: string;
    display_name?: string;
    target_jd_id?: string;
    status?: string;
    markdown?: string;
    sections?: Array<{
      title?: string;
      content?: string;
      evidence_refs?: string[];
      rewrite_strategy?: string;
      verification_status?: string;
    }>;
    forbidden_items?: string[];
    to_verify_items?: string[];
    provenance?: {
      candidate_evidence?: string[];
      generated_from?: string[];
      user_confirmations?: string[];
    };
  }>;
  jdProfiles: Array<{ jd_id: string; title: string; company: string }>;
  constraints: ResumeWorkspaceConstraint[];
  preflightStatus: string;
}): GeneratedResumePreview[] {
  return generatedResumes.map((resume, index) => {
    const targetLabel = buildJdLabel(resume.target_jd_id ?? "", jdProfiles);
    const displayName = resume.display_name || `${targetLabel || "岗位"}定制简历`;
    const status = resume.status || (preflightStatus === "pass" ? "deliverable" : "needs_review");
    const toVerifyItems = resume.to_verify_items ?? [];
    const blockedByGate = preflightStatus === "blocked" || status === "blocked";
    const isDeliverable = status === "deliverable" && preflightStatus === "pass";
    const sections = (resume.sections ?? []).map((section) => ({
      title: section.title || "未命名模块",
      content: section.content || "",
      evidenceRefs: section.evidence_refs ?? [],
      rewriteStrategy: section.rewrite_strategy || "证据内改写",
      verificationStatus: section.verification_status || "待复核",
    }));
    return {
      resumeId: resume.resume_id || `resume-${index + 1}`,
      displayName,
      targetLabel,
      status: blockedByGate ? "blocked" : status,
      isDeliverable,
      markdown: resume.markdown || buildMarkdownFromSections(sections),
      exportFileName: `${slugify(runLabel)}-${slugify(buildExportTargetName(targetLabel, displayName))}.md`,
      sections,
      forbiddenItems: resume.forbidden_items ?? constraints
        .filter((constraint) => constraint.category === "禁止编造缺口")
        .map((constraint) => constraint.requirementText),
      toVerifyItems: blockedByGate && toVerifyItems.length === 0 ? ["先补齐阻断证据，再导出投递版本。"] : toVerifyItems,
      candidateEvidence: resume.provenance?.candidate_evidence ?? [],
      generatedFrom: resume.provenance?.generated_from ?? ["候选人画像", "简历版本", "证据矩阵"],
      userConfirmations: resume.provenance?.user_confirmations ?? [],
      sourceLabel: "证据来源：候选人画像 / 生成产物",
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

function buildMarkdownFromSections(sections: ResumePreviewSection[]): string {
  return ["# 本地候选人", ...sections.map((section) => `## ${section.title}\n${section.content}`)].join("\n\n");
}

function slugify(value: string): string {
  const slug = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || "resume";
}

function buildExportTargetName(targetLabel: string, displayName: string): string {
  if (targetLabel.includes(" - ")) {
    return targetLabel.split(" - ")[0] ?? displayName;
  }
  return targetLabel || displayName;
}

function formatOverrideAction(action: string): string {
  const labels: Record<string, string> = {
    confirm_existing: "已确认现有证据",
    supplement_material: "已补充材料",
    mark_unsatisfied: "标记为不满足",
    skip_requirement: "跳过该岗位要求",
  };
  return labels[action] ?? action;
}
