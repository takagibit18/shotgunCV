import { access, readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";

import type {
  ApplicationStrategy,
  CandidateProfile,
  EvalSummaryItem,
  GapMap,
  JDProfile,
  PreflightGate,
  RankingExplanation,
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

type ManifestInputItem = {
  role?: "cv" | "jd";
  source_origin?: string;
  display_name?: string;
  original_name?: string;
  relative_path?: string;
  size_bytes?: number;
  source_value?: string;
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
  observability: ObservabilitySummary;
};

type RunReport = {
  runId: string;
  markdown: string;
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
    observability,
  };
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
    if (runStatus?.status === "failed" && runStatus.error_stage === stage) {
      return { stage, status: "failed" };
    }
    if (runStatus?.status === "running" && runStatus.current_stage === stage) {
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


export type { ObservabilitySummary, RunDetail, RunReport, RunSummary };


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
