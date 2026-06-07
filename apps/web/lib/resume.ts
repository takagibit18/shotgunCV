import type {
  CandidateProfile,
  CustomizedResumeDocument,
  PreflightGate,
  RequirementEvidence,
  ResumeBasics,
  ResumeEntry,
  ResumeProvenance,
} from "./types";
import { loadRunDetail, listRuns, type ResumeFieldStatus, type UserResumeEdit } from "./runs";
import { sanitizeUserFacingText } from "./user-facing";

type ResumeConstraintCategory = "可安全改写" | "待核实模拟补强" | "禁止编造缺口";
type LegacyResumeProvenance = {
  candidate_evidence?: string[];
  generated_from?: string[];
  user_confirmations?: string[];
};

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
  systemDocument: CustomizedResumeDocument;
  previewDocument: CustomizedResumeDocument;
  fieldStatuses: Record<string, ResumeFieldStatus>;
  hasUserEdits: boolean;
  markdown: string;
  exportFileName: string;
  sections: ResumePreviewSection[];
  forbiddenItems: string[];
  toVerifyItems: string[];
  candidateEvidence: string[];
  generatedFrom: string[];
  userConfirmations: string[];
  fieldSources: Record<string, string[]>;
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
        summary: sanitizeUserFacingText(variant.summary),
        targetJdLabels: variant.target_jd_ids.map((jdId) => buildJdLabel(jdId, detail.analyze.jdProfiles)),
        safeRewriteItems: sanitizeUserFacingList(variant.safe_rewrites ?? []),
        simulatedSupplementItems: sanitizeUserFacingList(variant.simulated_supplements ?? []),
        forbiddenGapItems: sanitizeUserFacingList(variant.forbidden_gaps ?? []),
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
        candidate: detail.analyze.candidate,
        generatedResumes: detail.generate.generatedResumes,
        jdProfiles: detail.analyze.jdProfiles,
        constraints,
        preflightStatus,
        edits: detail.review.userResumeEdits?.edits ?? [],
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
      requirementText: sanitizeUserFacingText(item.requirement_text),
      evidenceRefs: sanitizeUserFacingList(item.evidence_refs),
      gateStatus: gate?.status ?? "legacy",
      gateReasons: gate?.reasons ?? [],
      userOverride: userOverride
        ? {
            action: formatOverrideAction(userOverride.action),
            note: sanitizeUserFacingText(userOverride.note),
            updatedAt: userOverride.updated_at,
          }
        : null,
      sourceLabel: "来源：证据矩阵 / 投递前门槛",
    };
  });
}

function buildGeneratedResumes({
  runLabel,
  candidate,
  generatedResumes,
  jdProfiles,
  constraints,
  preflightStatus,
  edits,
}: {
  runLabel: string;
  generatedResumes: Array<{
    resume_id?: string;
    display_name?: string;
    target_jd_id?: string;
    target_variant_id?: string;
    status?: string;
    document?: CustomizedResumeDocument;
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
    provenance?: ResumeProvenance | {
      candidate_evidence?: string[];
      generated_from?: string[];
      user_confirmations?: string[];
    };
  }>;
  candidate: CandidateProfile | null;
  jdProfiles: Array<{ jd_id: string; title: string; company: string }>;
  constraints: ResumeWorkspaceConstraint[];
  preflightStatus: string;
  edits: UserResumeEdit[];
}): GeneratedResumePreview[] {
  return generatedResumes.map((resume, index) => {
    const targetLabel = buildJdLabel(resume.target_jd_id ?? "", jdProfiles);
    const displayName = resume.display_name || `${targetLabel || "岗位"}定制简历`;
    const status = resume.status || (preflightStatus === "pass" ? "deliverable" : "needs_review");
    const blockedByGate = preflightStatus === "blocked" || status === "blocked";
    const isDeliverable = status === "deliverable" && preflightStatus === "pass";
    const resumeId = resume.resume_id || `resume-${index + 1}`;
    const systemDocument = normalizeResumeDocument(resume, candidate);
    const edit = edits.find((item) => item.resume_id === resumeId) ?? null;
    const previewDocument = mergeResumeDocument(systemDocument, edit?.document_patch);
    const structuredProvenance = isStructuredProvenance(resume.provenance) ? resume.provenance : null;
    const legacyProvenance = isLegacyProvenance(resume.provenance) ? resume.provenance : null;
    const fieldSources = sanitizeFieldSources(structuredProvenance?.field_sources ?? {});
    const sections = buildSectionsFromDocument(previewDocument, fieldSources);
    const toVerifyItems = structuredProvenance?.to_verify_fields ?? resume.to_verify_items ?? [];
    const forbiddenItems =
      structuredProvenance?.forbidden_fields ??
      resume.forbidden_items ??
      constraints
        .filter((constraint) => constraint.category === "禁止编造缺口")
        .map((constraint) => constraint.requirementText);
    return {
      resumeId,
      displayName,
      targetLabel,
      status: blockedByGate ? "blocked" : status,
      isDeliverable,
      systemDocument,
      previewDocument,
      fieldStatuses: edit?.field_statuses ?? {},
      hasUserEdits: Boolean(edit),
      markdown: buildMarkdownFromDocument(previewDocument),
      exportFileName: `${slugify(runLabel)}-${slugify(buildExportTargetName(targetLabel, displayName))}.md`,
      sections,
      forbiddenItems,
      toVerifyItems: blockedByGate && toVerifyItems.length === 0 ? ["先补齐阻断证据，再导出投递版本。"] : toVerifyItems,
      candidateEvidence: sanitizeUserFacingList(Object.values(structuredProvenance?.field_sources ?? {}).flat()),
      generatedFrom: legacyProvenance?.generated_from ?? ["候选人画像", "简历版本", "证据矩阵"],
      userConfirmations: sanitizeUserFacingList(legacyProvenance?.user_confirmations ?? []),
      fieldSources,
      sourceLabel: "证据来源：候选人画像 / 生成产物",
    };
  });
}

function normalizeResumeDocument(
  resume: {
    document?: CustomizedResumeDocument;
    markdown?: string;
    sections?: Array<{ title?: string; content?: string }>;
  },
  candidate: CandidateProfile | null,
): CustomizedResumeDocument {
  if (resume.document) {
    return {
      basics: normalizeBasics(resume.document.basics, candidate),
      summary: resume.document.summary ?? "",
      skills: resume.document.skills ?? [],
      experiences: normalizeEntries(resume.document.experiences ?? [], "exp"),
      projects: normalizeEntries(resume.document.projects ?? [], "proj"),
      education: normalizeEntries(resume.document.education ?? [], "edu"),
      certifications: resume.document.certifications ?? [],
    };
  }
  const sectionMap = new Map(
    (resume.sections ?? []).map((section) => [(section.title ?? "").trim(), section.content ?? ""]),
  );
  return {
    basics: normalizeBasics({ full_name: candidate?.candidate_id ?? "本地候选人" }, candidate),
    summary: sectionMap.get("摘要") || firstNonEmpty(candidate?.strengths) || "",
    skills: splitListText(sectionMap.get("技能") || "").concat(candidate?.skills ?? []).filter(Boolean).slice(0, 10),
    experiences: buildEntryFallback("exp", "Relevant Experience", splitListText(sectionMap.get("经历") || "").concat(candidate?.experiences ?? [])),
    projects: buildEntryFallback("proj", "Relevant Project", splitListText(sectionMap.get("项目") || "").concat(candidate?.projects ?? [])),
    education: [],
    certifications: [],
  };
}

function normalizeBasics(basics: Partial<ResumeBasics> | undefined, candidate: CandidateProfile | null): ResumeBasics {
  return {
    full_name: basics?.full_name || candidate?.candidate_id || "本地候选人",
    headline: basics?.headline ?? "",
    location: basics?.location ?? "",
    email: basics?.email ?? "",
    phone: basics?.phone ?? "",
    links: basics?.links ?? [],
  };
}

function normalizeEntries(entries: ResumeEntry[], prefix: string): ResumeEntry[] {
  return entries.map((entry, index) => ({
    id: entry.id || `${prefix}-${String(index + 1).padStart(3, "0")}`,
    title: entry.title || "未命名条目",
    organization: entry.organization ?? "",
    period: entry.period ?? "",
    bullets: entry.bullets ?? [],
  }));
}

function mergeResumeDocument(
  systemDocument: CustomizedResumeDocument,
  documentPatch: Partial<CustomizedResumeDocument> | undefined,
): CustomizedResumeDocument {
  if (!documentPatch) {
    return systemDocument;
  }
  return {
    basics: { ...systemDocument.basics, ...(documentPatch.basics ?? {}) },
    summary: documentPatch.summary ?? systemDocument.summary,
    skills: documentPatch.skills ?? systemDocument.skills,
    experiences: documentPatch.experiences ?? systemDocument.experiences,
    projects: documentPatch.projects ?? systemDocument.projects,
    education: documentPatch.education ?? systemDocument.education,
    certifications: documentPatch.certifications ?? systemDocument.certifications,
  };
}

function buildSectionsFromDocument(
  document: CustomizedResumeDocument,
  fieldSources: Record<string, string[]>,
): ResumePreviewSection[] {
  return [
    {
      title: "摘要",
      content: document.summary,
      evidenceRefs: fieldSources["document.summary"] ?? [],
      rewriteStrategy: "JSON 字段渲染",
      verificationStatus: "merged",
    },
    {
      title: "技能",
      content: document.skills.join("、"),
      evidenceRefs: document.skills.flatMap((_, index) => fieldSources[`document.skills.${index}`] ?? []),
      rewriteStrategy: "JSON 字段渲染",
      verificationStatus: "merged",
    },
    ...document.experiences.map((entry, index) => ({
      title: entry.title || `经历 ${index + 1}`,
      content: entry.bullets.join("\n"),
      evidenceRefs: entry.bullets.flatMap(
        (_, bulletIndex) => fieldSources[`document.experiences.${index}.bullets.${bulletIndex}`] ?? [],
      ),
      rewriteStrategy: "JSON 字段渲染",
      verificationStatus: "merged",
    })),
  ];
}

function buildMarkdownFromDocument(document: CustomizedResumeDocument): string {
  const lines = [
    `# ${document.basics.full_name}`,
    document.basics.headline ? `\n${document.basics.headline}` : "",
    document.summary ? `\n## 摘要\n${document.summary}` : "",
    document.skills.length ? `\n## 技能\n${document.skills.map((skill) => `- ${skill}`).join("\n")}` : "",
    ...document.experiences.map((entry) => buildMarkdownEntrySection("经历", entry)),
    ...document.projects.map((entry) => buildMarkdownEntrySection("项目", entry)),
    ...document.education.map((entry) => buildMarkdownEntrySection("教育", entry)),
    document.certifications.length
      ? `\n## 证书\n${document.certifications.map((item) => `- ${item}`).join("\n")}`
      : "",
  ];
  return lines.filter((line) => line.trim()).join("\n\n");
}

function buildMarkdownEntrySection(sectionTitle: string, entry: ResumeEntry): string {
  const heading = [entry.title, entry.organization, entry.period].filter(Boolean).join(" · ");
  const bullets = entry.bullets.map((bullet) => `- ${bullet}`).join("\n");
  return `\n## ${sectionTitle}：${heading || "未命名条目"}\n${bullets}`;
}

function buildEntryFallback(prefix: string, title: string, bullets: string[]): ResumeEntry[] {
  const clean = bullets.map((item) => item.trim()).filter(Boolean);
  if (clean.length === 0) {
    return [];
  }
  return [{ id: `${prefix}-001`, title, organization: "", period: "", bullets: clean.slice(0, 5) }];
}

function splitListText(value: string): string[] {
  return value
    .split(/\r?\n|,|，|、/)
    .map((item) => item.replace(/^[-*]\s*/, "").trim())
    .filter(Boolean);
}

function firstNonEmpty(items: string[] | undefined): string {
  return items?.find((item) => item.trim()) ?? "";
}

function isStructuredProvenance(value: unknown): value is ResumeProvenance {
  return Boolean(value && typeof value === "object" && "field_sources" in value);
}

function isLegacyProvenance(value: unknown): value is LegacyResumeProvenance {
  return Boolean(value && typeof value === "object" && !("field_sources" in value));
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

function sanitizeUserFacingList(values: string[]): string[] {
  return values.map(sanitizeUserFacingText).filter(Boolean);
}

function sanitizeFieldSources(value: Record<string, string[]>): Record<string, string[]> {
  return Object.fromEntries(Object.entries(value).map(([key, items]) => [key, sanitizeUserFacingList(items)]));
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
