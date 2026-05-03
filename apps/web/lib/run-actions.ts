import { spawn } from "node:child_process";
import { mkdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";

import { getRunsDir } from "./runs";
import type { RunConfig, RunStatusFile, UploadManifest, UploadedInputFile } from "./types";


type RunAction = "run" | "retry_full" | "resume_failed";
type SpawnRunner = (command: string, args: string[], options: { cwd: string }) => { on: (event: string, callback: (error: Error) => void) => void };

type DraftPatchInput = {
  candidateId?: string;
  label?: string;
  cvFiles?: File[];
  jdFiles?: File[];
  jdFileDisplayNames?: string[];
  jdTexts?: string[];
  jdTextDisplayNames?: string[];
  now?: Date;
};

const STAGES = ["ingest", "analyze", "generate", "evaluate", "plan", "report"] as const;
const REQUIRED_STAGE_FILES: Record<(typeof STAGES)[number], string[]> = {
  ingest: ["ingest/manifest.json"],
  analyze: ["analyze/candidate_profile.json", "analyze/jd_profiles.json"],
  generate: ["generate/resume_variants.json"],
  evaluate: ["evaluate/scorecards.json", "evaluate/gap_maps.json", "evaluate/eval_summary.json"],
  plan: ["plan/application_strategies.json"],
  report: ["report/summary.md"],
};
const MAX_FILE_BYTES = 10 * 1024 * 1024;
const SUPPORTED_EXTENSIONS = new Set([".txt", ".md", ".pdf", ".png", ".jpg", ".jpeg"]);


export class RunActionError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status = 400) {
    super(message);
    this.name = "RunActionError";
    this.code = code;
    this.status = status;
  }
}


export async function startRunAction(runId: string, action: RunAction, spawnRunner: SpawnRunner = defaultSpawnRunner) {
  const runDir = resolveRunDir(runId);
  const current = await readRunStatus(runDir);
  if (current?.status === "running" || current?.status === "queued") {
    throw new RunActionError("run_busy", "Run is already queued or running.", 409);
  }
  if (action === "resume_failed" && current?.status !== "failed") {
    throw new RunActionError("not_failed", "Only failed runs can resume from the failed stage.");
  }

  const startedAt = nowIso();
  await writeRunStatus(runDir, {
    status: "queued",
    current_stage: null,
    started_at: startedAt,
    finished_at: null,
    error_stage: null,
    error_summary: null,
    last_action: action,
  });

  const args = await buildCliArgs(runDir, action);
  await writeRunStatus(runDir, {
    status: "running",
    current_stage: action === "resume_failed" ? firstIncompleteStage(await listStageDirs(runDir)) : "ingest",
    started_at: startedAt,
    finished_at: null,
    error_stage: null,
    error_summary: null,
    last_action: action,
  });

  const child = spawnRunner(process.env.SHOTGUNCV_CLI_COMMAND ?? "shotguncv", args, { cwd: path.resolve(getRunsDir(), "..") });
  child.on("error", async (error) => {
    await writeRunStatus(runDir, {
      status: "failed",
      current_stage: null,
      started_at: startedAt,
      finished_at: nowIso(),
      error_stage: null,
      error_summary: error.message,
      last_action: action,
    });
  });

  return { runId, status: "queued", action };
}


export async function deleteRun(runId: string) {
  const runDir = resolveRunDir(runId);
  const current = await readRunStatus(runDir);
  const inferred = current?.status ?? (await inferStatus(runDir));
  if (inferred === "running" || inferred === "queued") {
    throw new RunActionError("run_busy", "Running runs cannot be deleted.", 409);
  }
  if (inferred !== "draft" && inferred !== "failed") {
    throw new RunActionError("delete_not_allowed", "Only draft or failed runs can be deleted.", 409);
  }
  await rm(runDir, { recursive: true, force: true });
  return { runId, deleted: true };
}


export async function patchRunDraft(runId: string, input: DraftPatchInput) {
  const runDir = resolveRunDir(runId);
  const current = await readRunStatus(runDir);
  const inferred = current?.status ?? (await inferStatus(runDir));
  if (inferred !== "draft") {
    throw new RunActionError("not_draft", "Only draft runs can be edited.", 409);
  }

  const manifestPath = path.join(runDir, "ingest", "upload_manifest.json");
  const manifest = JSON.parse(await readFile(manifestPath, "utf-8")) as UploadManifest;
  const now = input.now ?? new Date();
  const uploadedAt = now.toISOString();

  const candidateId = input.candidateId?.trim();
  if (candidateId) {
    manifest.candidateId = candidateId;
  }
  if (input.label !== undefined) {
    manifest.label = input.label.trim();
    await updateRunConfigLabel(runDir, manifest.label);
  }

  const jdDisplayNames = input.jdFileDisplayNames ?? [];
  let jdIndex = 0;
  manifest.files = manifest.files.map((file) => {
    if (file.role !== "jd") {
      return file;
    }
    const displayName = jdDisplayNames[jdIndex]?.trim();
    jdIndex += 1;
    return displayName ? { ...file, displayName } : file;
  });

  if (input.cvFiles && input.cvFiles.length > 0) {
    const cvDir = path.join(runDir, "input_files", "cv");
    await rm(cvDir, { recursive: true, force: true });
    await mkdir(cvDir, { recursive: true });
    manifest.files = manifest.files.filter((file) => file.role !== "cv");
    manifest.files.unshift(...(await writeRoleFiles(runDir, "cv", input.cvFiles, uploadedAt)));
  }

  const usedJdNames = new Set(
    manifest.files
      .filter((file) => file.role === "jd")
      .map((file) => path.basename(file.storedRelativePath).toLowerCase()),
  );
  if (input.jdFiles && input.jdFiles.length > 0) {
    manifest.files.push(
      ...(await writeRoleFiles(runDir, "jd", input.jdFiles, uploadedAt, usedJdNames, (input.jdFileDisplayNames ?? []).slice(jdIndex))),
    );
  }
  const textEntries = normalizeJdTextEntries(input.jdTexts ?? [], input.jdTextDisplayNames ?? []);
  if (textEntries.length > 0) {
    manifest.files.push(...(await writePastedJdTexts(runDir, textEntries, uploadedAt, usedJdNames)));
  }

  manifest.nextCommand = buildNextCommand(runId, manifest.candidateId);
  await writeFile(manifestPath, JSON.stringify(manifest, null, 2), "utf-8");
  await writeRunStatus(runDir, {
    status: "draft",
    current_stage: null,
    started_at: null,
    finished_at: null,
    error_stage: null,
    error_summary: null,
    last_action: "draft_update",
  });
  return { runId, status: "draft", draft: manifest };
}


function defaultSpawnRunner(command: string, args: string[], options: { cwd: string }) {
  return spawn(command, args, { cwd: options.cwd, detached: true, stdio: "ignore" });
}


async function buildCliArgs(runDir: string, action: RunAction): Promise<string[]> {
  const manifest = await readManifestIfExists(runDir);
  if (action === "resume_failed" && manifest === null) {
    return ["run", "--run-dir", runDir, "--resume"];
  }
  if (manifest === null) {
    throw new RunActionError("missing_upload_manifest", "Run action requires an upload manifest.");
  }
  const args = [
    "run",
    "--run-dir",
    runDir,
    "--candidate-id",
    manifest.candidateId,
    "--cv",
    path.join(runDir, "input_files", "cv"),
    "--jd",
    path.join(runDir, "input_files", "jd"),
  ];
  if (action === "retry_full") {
    args.push("--retry-full");
  }
  if (action === "resume_failed") {
    args.push("--resume");
  }
  return args;
}


async function readManifestIfExists(runDir: string): Promise<UploadManifest | null> {
  const manifestPath = path.join(runDir, "ingest", "upload_manifest.json");
  if (!(await exists(manifestPath))) {
    return null;
  }
  return JSON.parse(await readFile(manifestPath, "utf-8")) as UploadManifest;
}


async function updateRunConfigLabel(runDir: string, label: string): Promise<void> {
  const configPath = path.join(runDir, "config", "run_config.json");
  const config = JSON.parse(await readFile(configPath, "utf-8")) as RunConfig;
  config.run_metadata = { ...(config.run_metadata ?? { label: "" }), label };
  await writeFile(configPath, JSON.stringify(config, null, 2), "utf-8");
}


async function writeRoleFiles(
  runDir: string,
  role: "cv" | "jd",
  files: File[],
  uploadedAt: string,
  usedNames = new Set<string>(),
  displayNames: string[] = [],
): Promise<UploadedInputFile[]> {
  const outputDir = path.join(runDir, "input_files", role);
  await mkdir(outputDir, { recursive: true });
  const records: UploadedInputFile[] = [];
  for (const [index, file] of files.entries()) {
    validateFile(file);
    const safeName = reserveUniqueFileName(sanitizeFileName(file.name), usedNames);
    const outputPath = path.join(outputDir, safeName);
    assertInside(outputDir, outputPath);
    await writeFile(outputPath, Buffer.from(await file.arrayBuffer()));
    const record: UploadedInputFile = {
      role,
      originalName: file.name,
      storedRelativePath: path.posix.join("input_files", role, safeName),
      sizeBytes: file.size,
      contentType: file.type || "application/octet-stream",
      uploadedAt,
    };
    if (role === "jd") {
      const displayName = displayNames[index]?.trim();
      if (displayName) {
        record.displayName = displayName;
      }
    }
    records.push(record);
  }
  return records;
}


async function writePastedJdTexts(
  runDir: string,
  texts: { text: string; displayName: string }[],
  uploadedAt: string,
  usedNames: Set<string>,
): Promise<UploadedInputFile[]> {
  const outputDir = path.join(runDir, "input_files", "jd");
  await mkdir(outputDir, { recursive: true });
  const records: UploadedInputFile[] = [];
  for (const [index, entry] of texts.entries()) {
    const safeName = reserveUniqueFileName(`pasted-jd-${String(index + 1).padStart(3, "0")}.txt`, usedNames);
    const bytes = Buffer.from(entry.text, "utf-8");
    await writeFile(path.join(outputDir, safeName), bytes);
    records.push({
      role: "jd",
      originalName: safeName,
      displayName: entry.displayName,
      storedRelativePath: path.posix.join("input_files", "jd", safeName),
      sizeBytes: bytes.byteLength,
      contentType: "text/plain",
      uploadedAt,
    });
  }
  return records;
}


function normalizeJdTextEntries(texts: string[], displayNames: string[]) {
  return texts
    .map((text, index) => ({ text: text.trim(), displayName: displayNames[index]?.trim() ?? "" }))
    .filter((entry) => entry.text && entry.displayName);
}


function validateFile(file: File): void {
  if (file.size === 0) {
    throw new RunActionError("empty_file", `File ${file.name} is empty.`);
  }
  if (file.size > MAX_FILE_BYTES) {
    throw new RunActionError("file_too_large", `File ${file.name} exceeds the 10MB limit.`);
  }
  if (!SUPPORTED_EXTENSIONS.has(path.extname(file.name).toLowerCase())) {
    throw new RunActionError("unsupported_file_type", `Unsupported file type: ${path.extname(file.name) || "none"}.`);
  }
}


async function inferStatus(runDir: string): Promise<RunStatusFile["status"] | "ingest-ready"> {
  const draftExists = await exists(path.join(runDir, "ingest", "upload_manifest.json"));
  const reportExists = await exists(path.join(runDir, "report", "summary.md"));
  if (reportExists) {
    return "done";
  }
  const completed = await listStageDirs(runDir);
  if (completed.length > 0) {
    return "running";
  }
  return draftExists ? "draft" : "ingest-ready";
}


async function listStageDirs(runDir: string) {
  const completed: string[] = [];
  for (const stage of STAGES) {
    const isComplete = await Promise.all(REQUIRED_STAGE_FILES[stage].map((file) => exists(path.join(runDir, file))));
    if (isComplete.every(Boolean)) {
      completed.push(stage);
    }
  }
  return completed;
}


function firstIncompleteStage(existingStages: string[]): RunStatusFile["current_stage"] {
  return STAGES.find((stage) => !existingStages.includes(stage)) ?? "report";
}


function resolveRunDir(runId: string): string {
  if (!/^[a-zA-Z0-9._-]+$/.test(runId)) {
    throw new RunActionError("invalid_run_id", "Run id contains unsafe characters.");
  }
  const runsDir = getRunsDir();
  const runDir = path.join(runsDir, runId);
  assertInside(runsDir, runDir);
  return runDir;
}


async function readRunStatus(runDir: string): Promise<RunStatusFile | null> {
  const statusPath = path.join(runDir, "run_status.json");
  if (!(await exists(statusPath))) {
    return null;
  }
  return JSON.parse(await readFile(statusPath, "utf-8")) as RunStatusFile;
}


async function writeRunStatus(runDir: string, status: RunStatusFile): Promise<void> {
  await writeFile(path.join(runDir, "run_status.json"), JSON.stringify(status, null, 2), "utf-8");
}


async function exists(filePath: string): Promise<boolean> {
  try {
    await stat(filePath);
    return true;
  } catch {
    return false;
  }
}


function sanitizeFileName(name: string): string {
  const normalized = name.replaceAll("\\", "/");
  if (normalized.includes("/") || normalized.includes("..")) {
    throw new RunActionError("unsafe_filename", "Uploaded filenames must not contain paths.");
  }
  const safeName = normalized.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "");
  if (!safeName) {
    throw new RunActionError("unsafe_filename", "Uploaded filename is invalid.");
  }
  return safeName;
}


function reserveUniqueFileName(name: string, usedNames: Set<string>): string {
  const extension = path.extname(name);
  const base = name.slice(0, name.length - extension.length);
  let candidate = name;
  let index = 2;
  while (usedNames.has(candidate.toLowerCase())) {
    candidate = `${base}-${index}${extension}`;
    index += 1;
  }
  usedNames.add(candidate.toLowerCase());
  return candidate;
}


function buildNextCommand(runId: string, candidateId: string): string {
  return [
    "shotguncv run",
    `--run-dir ./runs/${runId}`,
    `--candidate-id ${candidateId}`,
    `--cv ./runs/${runId}/input_files/cv`,
    `--jd ./runs/${runId}/input_files/jd`,
  ].join(" ");
}


function assertInside(parent: string, child: string): void {
  const relative = path.relative(path.resolve(parent), path.resolve(child));
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new RunActionError("unsafe_path", "Resolved path escapes the configured runs directory.");
  }
}


function nowIso(): string {
  return new Date().toISOString();
}
