import { access, mkdir, readdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";

import type {
  ApplicationStrategy,
  CandidateProfile,
  CustomizedResumeDocument,
  EvalSummaryItem,
  GapMap,
  JDProfile,
  PreflightGate,
  RankingExplanation,
  ResumeProvenance,
  RequirementEvidence,
  ResumeVariant,
  RunConfig,
  RunDraftStatus,
  RunStatusFile,
  RunTimelineEvent,
  ScoreCard,
  StageStatus,
  UploadManifest,
} from "./types";


type StageName = "ingest" | "analyze" | "generate" | "evaluate" | "plan" | "report";

type RunSummary = {
  runId: string;
  lastModified: string;
  completedStages: StageName[];
  analyzerProvider: string;
  generatorProvider: string;
  judgeProvider: string;
  plannerProvider: string;
  label: string;
  draftStatus: RunDraftStatus;
  runStatus: RunStatusFile | null;
  stageStatuses: StageStatus[];
  timeline: RunTimelineEvent[];
  draft: UploadManifest | null;
};

type EvaluateTopVariant = {
  jdId: string;
  title: string;
  variantId: string;
  variantDisplayName: string;
  overallScore: number;
  gapCount: number;
  topReasons: string[];
};

type DisplayVariant = ResumeVariant & {
  variantDisplayName: string;
  variantTypeDisplay: string;
};

type GeneratedResumeSection = {
  title?: string;
  content?: string;
  evidence_refs?: string[];
  rewrite_strategy?: string;
  verification_status?: string;
};

type GeneratedResume = {
  resume_id?: string;
  display_name?: string;
  target_jd_id?: string;
  target_variant_id?: string;
  status?: "deliverable" | "needs_review" | "blocked" | string;
  document?: CustomizedResumeDocument;
  markdown?: string;
  sections?: GeneratedResumeSection[];
  forbidden_items?: string[];
  to_verify_items?: string[];
  provenance?: ResumeProvenance | {
    candidate_evidence?: string[];
    generated_from?: string[];
    user_confirmations?: string[];
  };
};

type UserEvidenceOverrideAction =
  | "confirm_existing"
  | "supplement_material"
  | "mark_unsatisfied"
  | "skip_requirement";

type UserEvidenceOverride = {
  jd_id: string;
  requirement_id: string;
  action: UserEvidenceOverrideAction;
  note: string;
  source: "user";
  updated_at: string;
};

type UserEvidenceOverridesArtifact = {
  schema_version: string;
  run_id: string;
  overrides: UserEvidenceOverride[];
};

type ResumeFieldStatus = "confirmed" | "to_verify";

type UserResumeEdit = {
  resume_id: string;
  document_patch: Partial<CustomizedResumeDocument>;
  field_statuses: Record<string, ResumeFieldStatus>;
  source: "user";
  updated_at: string;
};

type UserResumeEditsArtifact = {
  schema_version: string;
  run_id: string;
  edits: UserResumeEdit[];
};

type InputSourceDisplay = {
  role: "cv" | "jd";
  sourceOrigin: string;
  displayName: string;
  originalName: string;
  relativePath: string;
  sizeBytes: number;
  extractionStatus: string;
  extractionError: string;
};

type JdInputPreview = {
  jdId?: string;
  previewIndex?: number;
  label: string;
  kind: "image" | "text" | "metadata";
  originalName: string;
  contentType: string;
  imageDataUrl?: string;
  text?: string;
  note?: string;
};

type ObservabilitySummary = {
  resolvedModels: {
    stage: string;
    role: string;
    provider: string;
    configuredModel: string;
    resolvedModel: string;
    baseUrlHost: string;
  }[];
  promptTokens: number | null;
  completionTokens: number | null;
  totalTokens: number | null;
  toolCallCount: number;
  fallbackCount: number;
  qualityWarnings: string[];
};

type PostRunReview = {
  schema_version: string;
  run_id: string;
  candidate_id: string;
  jd_ids: string[];
  evidence_citations: {
    source_type?: string;
    source_id?: string;
    candidate_id?: string;
    jd_id?: string | null;
    run_id?: string;
    artifact_path?: string;
    provenance_summary?: string;
    text?: string;
    score?: number;
  }[];
  interview_questions: { jd_id?: string; question: string }[];
  revision_tasks: { jd_id?: string; task: string }[];
  retrieval?: { result_count?: number; misses?: string[] };
  validation?: { fabrication_policy?: string; warnings?: string[] };
};

type ManifestInputItem = {
  role?: "cv" | "jd";
  source_origin?: string;
  source_type?: string;
  display_name?: string;
  original_name?: string;
  relative_path?: string;
  size_bytes?: number;
  source_value?: string;
  media_type?: string;
  text?: string;
  content?: string;
  extraction_status?: string;
  extraction_error?: string;
};

type IngestManifest = {
  candidate_inputs?: ManifestInputItem[];
  jd_inputs?: ManifestInputItem[];
};

type RunDetail = {
  runId: string;
  label: string;
  analyzerProvider: string;
  generatorProvider: string;
  judgeProvider: string;
  plannerProvider: string;
  completedStages: StageName[];
  analyze: {
    isComplete: boolean;
    candidate: CandidateProfile | null;
    jdProfiles: JDProfile[];
  };
  requirementMatrix: RequirementEvidence[];
  preflightGates: PreflightGate[];
  generate: {
    isComplete: boolean;
    variants: DisplayVariant[];
    generatedResumes: GeneratedResume[];
  };
  evaluate: {
    isComplete: boolean;
    topVariants: EvaluateTopVariant[];
    scorecards: ScoreCard[];
    gapMaps: GapMap[];
    explanations: RankingExplanation[];
  };
  plan: {
    isComplete: boolean;
    strategies: ApplicationStrategy[];
  };
  draft: UploadManifest | null;
  draftStatus: RunDraftStatus;
  runStatus: RunStatusFile | null;
  stageStatuses: StageStatus[];
  timeline: RunTimelineEvent[];
  inputSources: InputSourceDisplay[];
  jdInputPreviews: JdInputPreview[];
  observability: ObservabilitySummary;
  review: {
    postRunReview: PostRunReview | null;
    interviewPrepMarkdown: string;
    userEvidenceOverrides: UserEvidenceOverridesArtifact | null;
    userResumeEdits: UserResumeEditsArtifact | null;
  };
};

type RunReport = {
  runId: string;
  markdown: string;
};

type RunStatusSnapshot = {
  runId: string;
  draftStatus: RunDraftStatus;
  runStatus: RunStatusFile | null;
  completedStages: StageName[];
  stageStatuses: StageStatus[];
  hasResults: boolean;
  hasReport: boolean;
  reviewItemCount: number;
};

const REQUIRED_STAGE_FILES: Record<StageName, string[]> = {
  ingest: ["ingest/manifest.json"],
  analyze: ["analyze/candidate_profile.json", "analyze/jd_profiles.json"],
  generate: ["generate/resume_variants.json"],
  evaluate: ["evaluate/scorecards.json", "evaluate/gap_maps.json", "evaluate/eval_summary.json"],
  plan: ["plan/application_strategies.json"],
  report: ["report/summary.md"],
};


export async function listRuns(): Promise<RunSummary[]> {
  const runsDir = getRunsDir();
  const entries = await readdir(runsDir, { withFileTypes: true });
  const runs = await Promise.all(
    entries
      .filter((entry) => entry.isDirectory())
      .map(async (entry) => {
        const runId = entry.name;
        const runDir = path.join(runsDir, runId);
        const metadata = await stat(runDir);
        const config = await readJsonIfExists<RunConfig>(path.join(runDir, "config", "run_config.json"));
        const draft = await readJsonIfExists<UploadManifest>(path.join(runDir, "ingest", "upload_manifest.json"));
        const runStatus = await readJsonIfExists<RunStatusFile>(path.join(runDir, "run_status.json"));
        const completedStages = await getCompletedStages(runDir);
        const timeline = await readTimeline(runDir);
        return {
          runId,
          lastModified: metadata.mtime.toISOString(),
          completedStages,
          analyzerProvider: config?.analyzer?.provider ?? "unknown",
          generatorProvider: config?.generator?.provider ?? "unknown",
          judgeProvider: config?.judge?.provider ?? "unknown",
          plannerProvider: config?.planner?.provider ?? "unknown",
          label: config?.run_metadata.label || draft?.label || "",
          draftStatus: buildDraftStatus(draft, completedStages, runStatus),
          runStatus,
          stageStatuses: buildStageStatuses(completedStages, runStatus),
          timeline,
          draft,
        };
      }),
  );
  return runs.sort((left, right) => right.lastModified.localeCompare(left.lastModified));
}


function buildDraftStatus(
  draft: UploadManifest | null,
  completedStages: StageName[],
  runStatus: RunStatusFile | null = null,
): RunDraftStatus {
  if (runStatus?.status) {
    return runStatus.status;
  }
  if (completedStages.includes("report")) {
    return "done";
  }
  if (completedStages.length > 0) {
    return "running";
  }
  return draft ? "draft" : "ingest-ready";
}


export async function loadRunDetail(runId: string): Promise<RunDetail> {
  const runDir = path.join(getRunsDir(), runId);
  const config = await readJsonIfExists<RunConfig>(path.join(runDir, "config", "run_config.json"));
  const completedStages = await getCompletedStages(runDir);
  const draft = await readJsonIfExists<UploadManifest>(path.join(runDir, "ingest", "upload_manifest.json"));
  const runStatus = await readJsonIfExists<RunStatusFile>(path.join(runDir, "run_status.json"));
  const timeline = await readTimeline(runDir);
  const observability = buildObservabilitySummary(timeline, runStatus);
  const ingestManifest = await readJsonIfExists<IngestManifest>(path.join(runDir, "ingest", "manifest.json"));
  const candidate = await readJsonIfExists<CandidateProfile>(path.join(runDir, "analyze", "candidate_profile.json"));
  const jdProfiles = (await readJsonIfExists<JDProfile[]>(path.join(runDir, "analyze", "jd_profiles.json"))) ?? [];
  const requirementMatrix =
    (await readJsonIfExists<RequirementEvidence[]>(path.join(runDir, "analyze", "requirement_matrix.json"))) ?? [];
  const preflightGates =
    (await readJsonIfExists<PreflightGate[]>(path.join(runDir, "analyze", "preflight_gates.json"))) ?? [];
  const variants = (await readJsonIfExists<ResumeVariant[]>(path.join(runDir, "generate", "resume_variants.json"))) ?? [];
  const generatedResumes =
    (await readJsonIfExists<GeneratedResume[]>(path.join(runDir, "generate", "generated_resumes.json"))) ?? [];
  const displayVariants: DisplayVariant[] = variants.map((variant) => ({
    ...variant,
    variantDisplayName: buildVariantDisplayName(variant.variant_id),
    variantTypeDisplay: buildVariantTypeDisplay(variant.variant_type),
  }));
  const scorecards = (await readJsonIfExists<ScoreCard[]>(path.join(runDir, "evaluate", "scorecards.json"))) ?? [];
  const gapMaps = (await readJsonIfExists<GapMap[]>(path.join(runDir, "evaluate", "gap_maps.json"))) ?? [];
  const explanations =
    (await readJsonIfExists<RankingExplanation[]>(path.join(runDir, "evaluate", "ranking_explanations.json"))) ?? [];
  const evalSummary = (await readJsonIfExists<EvalSummaryItem[]>(path.join(runDir, "evaluate", "eval_summary.json"))) ?? [];
  const strategies =
    (await readJsonIfExists<ApplicationStrategy[]>(path.join(runDir, "plan", "application_strategies.json"))) ?? [];
  const postRunReview = await readJsonIfExists<PostRunReview>(path.join(runDir, "review", "post_run_review.json"));
  const userEvidenceOverrides = await readJsonIfExists<UserEvidenceOverridesArtifact>(
    path.join(runDir, "review", "user_evidence_overrides.json"),
  );
  const userResumeEdits = await readJsonIfExists<UserResumeEditsArtifact>(
    path.join(runDir, "review", "user_resume_edits.json"),
  );
  const interviewPrepMarkdown = await readTextIfExists(path.join(runDir, "review", "interview_prep.md"));

  const gapCounts = new Map(gapMaps.map((gapMap) => [gapMap.jd_id, gapMap.items.length]));
  const jdIndex = new Map(jdProfiles.map((jd) => [jd.jd_id, jd]));
  const jdDisplayNameIndex = buildJdDisplayNameIndex(ingestManifest);
  const topVariants = evalSummary.map((item) => {
    const scorecard = scorecards.find(
      (candidateScorecard) =>
        candidateScorecard.jd_id === item.jd_id && candidateScorecard.variant_id === item.top_variant_id,
    );
    const jd = jdIndex.get(item.jd_id);
    return {
      jdId: item.jd_id,
      title: item.title || jd?.title || jdDisplayNameIndex.get(item.jd_id) || item.jd_id,
      variantId: item.top_variant_id,
      variantDisplayName: buildVariantDisplayName(item.top_variant_id),
      overallScore: scorecard?.final_overall_score ?? scorecard?.overall_score ?? 0,
      gapCount: item.gap_count ?? gapCounts.get(item.jd_id) ?? 0,
      topReasons: item.top_reasons ?? [],
    };
  });

  return {
    runId,
    label: config?.run_metadata?.label ?? draft?.label ?? "",
    analyzerProvider: config?.analyzer?.provider ?? "unknown",
    generatorProvider: config?.generator?.provider ?? "unknown",
    judgeProvider: config?.judge?.provider ?? "unknown",
    plannerProvider: config?.planner?.provider ?? "unknown",
    completedStages,
    analyze: {
      isComplete: completedStages.includes("analyze"),
      candidate,
      jdProfiles,
    },
    requirementMatrix,
    preflightGates,
    generate: {
      isComplete: completedStages.includes("generate"),
      variants: displayVariants,
      generatedResumes,
    },
    evaluate: {
      isComplete: completedStages.includes("evaluate"),
      topVariants,
      scorecards,
      gapMaps,
      explanations,
    },
    plan: {
      isComplete: completedStages.includes("plan"),
      strategies,
    },
    draft,
    draftStatus: buildDraftStatus(draft, completedStages, runStatus),
    runStatus,
    stageStatuses: buildStageStatuses(completedStages, runStatus),
    timeline,
    inputSources: buildInputSources(ingestManifest, draft),
    jdInputPreviews: await buildJdInputPreviews(runDir, ingestManifest, draft, jdProfiles),
    observability,
    review: {
      postRunReview,
      interviewPrepMarkdown,
      userEvidenceOverrides,
      userResumeEdits,
    },
  };
}

export async function loadRunStatusSnapshot(runId: string): Promise<RunStatusSnapshot> {
  const runDir = path.join(getRunsDir(), runId);
  const completedStages = await getCompletedStages(runDir);
  const draft = await readJsonIfExists<UploadManifest>(path.join(runDir, "ingest", "upload_manifest.json"));
  const runStatus = await readJsonIfExists<RunStatusFile>(path.join(runDir, "run_status.json"));
  const preflightGates =
    (await readJsonIfExists<PreflightGate[]>(path.join(runDir, "analyze", "preflight_gates.json"))) ?? [];
  const evalSummary = await readJsonIfExists<EvalSummaryItem[]>(path.join(runDir, "evaluate", "eval_summary.json"));
  return {
    runId,
    draftStatus: buildDraftStatus(draft, completedStages, runStatus),
    runStatus,
    completedStages,
    stageStatuses: buildStageStatuses(completedStages, runStatus),
    hasResults: (evalSummary ?? []).length > 0,
    hasReport: completedStages.includes("report"),
    reviewItemCount: preflightGates.filter((gate) => gate.status === "blocked" || gate.status === "needs_review").length,
  };
}


export async function saveUserEvidenceOverride(
  runId: string,
  input: {
    jdId: string;
    requirementId: string;
    action: UserEvidenceOverrideAction;
    note?: string;
  },
): Promise<UserEvidenceOverridesArtifact> {
  if (!/^[a-zA-Z0-9._-]+$/.test(runId)) {
    throw new Error("运行批次标识无效。");
  }
  const runDir = path.join(getRunsDir(), runId);
  const resolvedRunDir = path.resolve(runDir);
  const runsRoot = path.resolve(getRunsDir());
  const relativeRunDir = path.relative(runsRoot, resolvedRunDir);
  if (relativeRunDir.startsWith("..") || path.isAbsolute(relativeRunDir)) {
    throw new Error("运行批次路径无效。");
  }
  if (!(await pathExists(runDir))) {
    throw new Error("运行批次不存在。");
  }

  const reviewDir = path.join(runDir, "review");
  const artifactPath = path.join(reviewDir, "user_evidence_overrides.json");
  const existing =
    (await readJsonIfExists<UserEvidenceOverridesArtifact>(artifactPath)) ?? {
      schema_version: "v0.11",
      run_id: runId,
      overrides: [],
    };
  const override: UserEvidenceOverride = {
    jd_id: input.jdId.trim(),
    requirement_id: input.requirementId.trim(),
    action: input.action,
    note: (input.note ?? "").trim(),
    source: "user",
    updated_at: new Date().toISOString(),
  };
  const next: UserEvidenceOverridesArtifact = {
    schema_version: existing.schema_version || "v0.11",
    run_id: runId,
    overrides: [
      ...existing.overrides.filter(
        (item) => item.jd_id !== override.jd_id || item.requirement_id !== override.requirement_id,
      ),
      override,
    ],
  };
  await mkdir(reviewDir, { recursive: true });
  await writeFile(artifactPath, `${JSON.stringify(next, null, 2)}\n`, "utf-8");
  return next;
}


export async function saveUserResumeEdit(
  runId: string,
  input: {
    resumeId: string;
    documentPatch?: Partial<CustomizedResumeDocument>;
    fieldStatuses?: Record<string, ResumeFieldStatus>;
    reset?: boolean;
  },
): Promise<UserResumeEditsArtifact> {
  if (!/^[a-zA-Z0-9._-]+$/.test(runId)) {
    throw new Error("运行批次标识无效。");
  }
  const resumeId = input.resumeId.trim();
  if (!resumeId) {
    throw new Error("简历版本标识不能为空。");
  }
  const runDir = path.join(getRunsDir(), runId);
  const resolvedRunDir = path.resolve(runDir);
  const runsRoot = path.resolve(getRunsDir());
  const relativeRunDir = path.relative(runsRoot, resolvedRunDir);
  if (relativeRunDir.startsWith("..") || path.isAbsolute(relativeRunDir)) {
    throw new Error("运行批次路径无效。");
  }
  if (!(await pathExists(runDir))) {
    throw new Error("运行批次不存在。");
  }

  const reviewDir = path.join(runDir, "review");
  const artifactPath = path.join(reviewDir, "user_resume_edits.json");
  const existing =
    (await readJsonIfExists<UserResumeEditsArtifact>(artifactPath)) ?? {
      schema_version: "resume-edits-v1",
      run_id: runId,
      edits: [],
    };
  const remaining = existing.edits.filter((item) => item.resume_id !== resumeId);
  const next: UserResumeEditsArtifact = input.reset
    ? {
        schema_version: existing.schema_version || "resume-edits-v1",
        run_id: runId,
        edits: remaining,
      }
    : {
        schema_version: existing.schema_version || "resume-edits-v1",
        run_id: runId,
        edits: [
          ...remaining,
          {
            resume_id: resumeId,
            document_patch: input.documentPatch ?? {},
            field_statuses: input.fieldStatuses ?? {},
            source: "user",
            updated_at: new Date().toISOString(),
          },
        ],
      };
  await mkdir(reviewDir, { recursive: true });
  await writeFile(artifactPath, `${JSON.stringify(next, null, 2)}\n`, "utf-8");
  return next;
}


export async function loadRunReport(runId: string): Promise<RunReport | null> {
  const reportPath = path.join(getRunsDir(), runId, "report", "summary.md");
  if (!(await pathExists(reportPath))) {
    return null;
  }
  return {
    runId,
    markdown: await readFile(reportPath, "utf-8"),
  };
}


export function getRunsDir(): string {
  return process.env.SHOTGUNCV_RUNS_DIR ?? path.resolve(process.cwd(), "..", "..", "runs");
}


async function getCompletedStages(runDir: string): Promise<StageName[]> {
  const stages = await Promise.all(
    (Object.entries(REQUIRED_STAGE_FILES) as [StageName, string[]][]).map(async ([stage, files]) => {
      const isComplete = await Promise.all(files.map((file) => pathExists(path.join(runDir, file))));
      return isComplete.every(Boolean) ? stage : null;
    }),
  );
  return stages.filter((stage): stage is StageName => stage !== null);
}


function buildStageStatuses(completedStages: StageName[], runStatus: RunStatusFile | null): StageStatus[] {
  return (Object.keys(REQUIRED_STAGE_FILES) as StageName[]).map((stage) => {
    if ((runStatus?.status === "failed" || runStatus?.status === "partial_failed") && runStatus.error_stage === stage) {
      return { stage, status: "failed" };
    }
    if ((runStatus?.status === "running" || runStatus?.status === "partial_running") && runStatus.current_stage === stage) {
      return { stage, status: "running" };
    }
    if (completedStages.includes(stage)) {
      return { stage, status: "complete" };
    }
    return { stage, status: "pending" };
  });
}


async function readTimeline(runDir: string): Promise<RunTimelineEvent[]> {
  const pathToLog = path.join(runDir, "logs", "run_events.jsonl");
  if (!(await pathExists(pathToLog))) {
    return [];
  }
  const lines = (await readFile(pathToLog, "utf-8")).split(/\r?\n/).filter((line) => line.trim());
  const events: RunTimelineEvent[] = [];
  for (const line of lines) {
    try {
      const event = JSON.parse(line) as RunTimelineEvent;
      if (typeof event.timestamp === "string" && typeof event.event === "string") {
        events.push(event);
      }
    } catch {
      // Ignore malformed legacy log lines so one bad event cannot break a run page.
    }
  }
  return events;
}


function buildObservabilitySummary(
  timeline: RunTimelineEvent[],
  runStatus: RunStatusFile | null,
): ObservabilitySummary {
  const resolvedModels = timeline
    .filter((event) => event.event === "model_resolved")
    .map((event) => ({
      stage: event.stage ?? "",
      role: event.role ?? "",
      provider: event.provider ?? "",
      configuredModel: event.configured_model ?? "",
      resolvedModel: event.resolved_model ?? "",
      baseUrlHost: event.base_url_host ?? "",
    }));

  const tokenEvents = timeline.filter((event) => event.event === "llm_call_finished");
  const promptTokens = sumOptional(tokenEvents.map((event) => event.prompt_tokens));
  const completionTokens = sumOptional(tokenEvents.map((event) => event.completion_tokens));
  const totalTokens = sumOptional(tokenEvents.map((event) => event.total_tokens));
  const qualityWarnings = timeline
    .filter((event) => event.event === "quality_gate_checked" && event.status && event.status !== "ok")
    .map((event) => `${event.gate ?? "quality"}: ${event.status}`);
  if (runStatus?.quality_summary) {
    qualityWarnings.unshift(runStatus.quality_summary);
  }

  return {
    resolvedModels,
    promptTokens,
    completionTokens,
    totalTokens,
    toolCallCount: timeline.filter((event) => event.event.startsWith("tool_call_")).length,
    fallbackCount: timeline.filter((event) => event.event === "fallback_used").length,
    qualityWarnings,
  };
}


function sumOptional(values: Array<number | null | undefined>): number | null {
  const numericValues = values.filter((value): value is number => typeof value === "number");
  if (numericValues.length === 0) {
    return null;
  }
  return numericValues.reduce((total, value) => total + value, 0);
}


async function readJsonOrThrow<T>(filePath: string): Promise<T> {
  return JSON.parse(await readFile(filePath, "utf-8")) as T;
}


async function readJsonIfExists<T>(filePath: string): Promise<T | null> {
  if (!(await pathExists(filePath))) {
    return null;
  }
  try {
    return await readJsonOrThrow<T>(filePath);
  } catch {
    return null;
  }
}


async function pathExists(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}


export type {
  GeneratedResume,
  GeneratedResumeSection,
  JdInputPreview,
  ObservabilitySummary,
  PostRunReview,
  RunDetail,
  RunReport,
  RunStatusSnapshot,
  RunSummary,
  UserEvidenceOverride,
  UserEvidenceOverrideAction,
  UserEvidenceOverridesArtifact,
  ResumeFieldStatus,
  UserResumeEdit,
  UserResumeEditsArtifact,
};


function buildInputSources(ingestManifest: IngestManifest | null, draft: UploadManifest | null): InputSourceDisplay[] {
  const manifestInputs = [
    ...(ingestManifest?.candidate_inputs ?? []),
    ...(ingestManifest?.jd_inputs ?? []),
  ];
  if (manifestInputs.length > 0) {
    return manifestInputs.map((item) => ({
      role: item.role ?? "cv",
      sourceOrigin: item.source_origin ?? "cli",
      displayName: item.display_name ?? "",
      originalName: item.original_name ?? path.basename(item.source_value ?? ""),
      relativePath: item.relative_path ?? item.source_value ?? "",
      sizeBytes: item.size_bytes ?? 0,
      extractionStatus: item.extraction_status ?? "unknown",
      extractionError: item.extraction_error ?? "",
    }));
  }
  return (draft?.files ?? []).map((file) => ({
    role: file.role,
    sourceOrigin: "upload",
    displayName: file.displayName ?? "",
    originalName: file.originalName,
    relativePath: file.storedRelativePath,
    sizeBytes: file.sizeBytes,
    extractionStatus: "draft",
    extractionError: "",
  }));
}


async function buildJdInputPreviews(
  runDir: string,
  ingestManifest: IngestManifest | null,
  draft: UploadManifest | null,
  jdProfiles: JDProfile[],
): Promise<JdInputPreview[]> {
  const manifestInputs = ingestManifest?.jd_inputs ?? [];
  const resolveJdId = buildJdPreviewJdResolver(jdProfiles);
  if (manifestInputs.length > 0) {
    return Promise.all(
      manifestInputs.map((item, index) =>
        buildJdPreview({
          runDir,
          jdId: resolveJdId(
            {
              sourceValue: item.source_value,
              relativePath: item.relative_path,
              originalName: item.original_name,
            },
            index,
          ),
          previewIndex: index,
          label: item.display_name || item.original_name || `岗位 ${index + 1}`,
          originalName: item.original_name ?? item.display_name ?? `岗位 ${index + 1}`,
          contentType: item.media_type ?? inferContentType(item.original_name ?? item.relative_path ?? item.source_value ?? ""),
          relativePath: item.relative_path,
          sourceValue: item.source_value,
          inlineText: item.text || item.content || "",
          extractionError: item.extraction_error,
        }),
      ),
    );
  }

  return Promise.all(
    (draft?.files ?? [])
      .filter((file) => file.role === "jd")
      .map((file, index) =>
        buildJdPreview({
          runDir,
          jdId: resolveJdId(
            {
              sourceValue: file.storedRelativePath,
              relativePath: file.storedRelativePath,
              originalName: file.originalName,
            },
            index,
          ),
          previewIndex: index,
          label: file.displayName || file.originalName || `岗位 ${index + 1}`,
          originalName: file.originalName || `岗位 ${index + 1}`,
          contentType: file.contentType || inferContentType(file.originalName),
          relativePath: file.storedRelativePath,
          sourceValue: file.storedRelativePath,
          inlineText: "",
          extractionError: "",
        }),
      ),
  );
}


function buildJdPreviewJdResolver(jdProfiles: JDProfile[]) {
  const bySource = new Map<string, string>();
  const byBasename = new Map<string, string>();
  jdProfiles.forEach((profile) => {
    const sourceKey = normalizeSourceKey(profile.source_value);
    if (sourceKey) {
      bySource.set(sourceKey, profile.jd_id);
    }
    const basename = getSourceBasename(profile.source_value);
    if (basename) {
      byBasename.set(basename, profile.jd_id);
    }
  });

  return (
    item: {
      sourceValue?: string;
      relativePath?: string;
      originalName?: string;
    },
    index: number,
  ): string | undefined => {
    const sourceCandidates = [item.sourceValue, item.relativePath, item.originalName];
    for (const candidate of sourceCandidates) {
      const sourceKey = normalizeSourceKey(candidate);
      if (sourceKey && bySource.has(sourceKey)) {
        return bySource.get(sourceKey);
      }
      const basename = getSourceBasename(candidate);
      if (basename && byBasename.has(basename)) {
        return byBasename.get(basename);
      }
    }
    return jdProfiles[index]?.jd_id;
  };
}


function normalizeSourceKey(value: string | undefined): string {
  return (value ?? "").replace(/\\/g, "/").trim().toLowerCase();
}


function getSourceBasename(value: string | undefined): string {
  const sourceKey = normalizeSourceKey(value);
  if (!sourceKey) {
    return "";
  }
  return sourceKey.split("/").pop() ?? "";
}


async function buildJdPreview({
  runDir,
  jdId,
  previewIndex,
  label,
  originalName,
  contentType,
  relativePath,
  sourceValue,
  inlineText,
  extractionError,
}: {
  runDir: string;
  jdId?: string;
  previewIndex: number;
  label: string;
  originalName: string;
  contentType: string;
  relativePath?: string;
  sourceValue?: string;
  inlineText: string;
  extractionError?: string;
}): Promise<JdInputPreview> {
  const candidatePath = resolveRunFilePath(runDir, relativePath || sourceValue || "");
  if (isImageInput(contentType, originalName)) {
    const bytes = candidatePath ? await readFileIfExists(candidatePath) : null;
    return {
      jdId,
      previewIndex,
      label,
      kind: bytes ? "image" : "metadata",
      originalName,
      contentType: contentType || inferContentType(originalName),
      imageDataUrl: bytes ? `data:${contentType || inferContentType(originalName)};base64,${bytes.toString("base64")}` : undefined,
      note: bytes ? "点击截图可放大查看" : extractionError || "岗位截图尚未生成可预览文件。",
    };
  }

  const fileText = candidatePath && isTextInput(contentType, originalName) ? await readTextIfExists(candidatePath) : "";
  const text = truncatePreviewText(inlineText || fileText);
  if (text) {
    return {
      jdId,
      previewIndex,
      label,
      kind: "text",
      originalName,
      contentType: contentType || inferContentType(originalName),
      text,
    };
  }

  return {
    jdId,
    previewIndex,
    label,
    kind: "metadata",
    originalName,
    contentType: contentType || inferContentType(originalName),
    note: extractionError || "当前岗位输入暂无可直接展示的文本或截图。",
  };
}


function resolveRunFilePath(runDir: string, filePath: string): string | null {
  const trimmed = filePath.trim();
  if (!trimmed) {
    return null;
  }
  const resolved = path.resolve(path.isAbsolute(trimmed) ? trimmed : path.join(runDir, trimmed));
  const relative = path.relative(path.resolve(runDir), resolved);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    return null;
  }
  return resolved;
}


async function readFileIfExists(filePath: string): Promise<Buffer | null> {
  try {
    return await readFile(filePath);
  } catch {
    return null;
  }
}


async function readTextIfExists(filePath: string): Promise<string> {
  try {
    return await readFile(filePath, "utf-8");
  } catch {
    return "";
  }
}


function inferContentType(fileName: string): string {
  const extension = path.extname(fileName).toLowerCase();
  const contentTypes: Record<string, string> = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".txt": "text/plain",
    ".md": "text/markdown",
  };
  return contentTypes[extension] ?? "application/octet-stream";
}


function isImageInput(contentType: string, fileName: string): boolean {
  return contentType.startsWith("image/") || [".jpg", ".jpeg", ".png", ".webp"].includes(path.extname(fileName).toLowerCase());
}


function isTextInput(contentType: string, fileName: string): boolean {
  return contentType.startsWith("text/") || [".txt", ".md"].includes(path.extname(fileName).toLowerCase());
}


function truncatePreviewText(text: string): string {
  const trimmed = text.trim();
  if (trimmed.length <= 12000) {
    return trimmed;
  }
  return `${trimmed.slice(0, 12000)}\n\n[内容较长，已截取前 12000 个字符用于页面预览。]`;
}


function buildJdDisplayNameIndex(ingestManifest: IngestManifest | null): Map<string, string> {
  const index = new Map<string, string>();
  (ingestManifest?.jd_inputs ?? []).forEach((item, itemIndex) => {
    const displayName = item.display_name?.trim();
    if (displayName) {
      index.set(`jd-${String(itemIndex + 1).padStart(3, "0")}`, displayName);
    }
  });
  return index;
}


function buildVariantTypeDisplay(variantType: string): string {
  if (variantType === "cluster") {
    return "岗位簇版本";
  }
  if (variantType === "jd-specific") {
    return "岗位定制版本";
  }
  return variantType;
}


function buildVariantDisplayName(variantId: string): string {
  if (variantId.startsWith("variant-jd-")) {
    const jdId = variantId.replace("variant-jd-", "");
    return `岗位定制版本（${jdId}）`;
  }
  if (variantId.startsWith("variant-cluster-")) {
    const cluster = variantId.replace("variant-cluster-", "");
    return `岗位簇版本（${cluster}）`;
  }
  return `简历版本（${variantId}）`;
}
