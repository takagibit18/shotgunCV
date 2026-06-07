import { spawn, spawnSync } from "node:child_process";
import { access, appendFile, mkdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";

import { getRunsDir } from "./runs";
import type { RunConfig, RunStatusFile, UploadManifest, UploadedInputFile } from "./types";


type RunAction = "run" | "retry_full" | "resume_failed";
type SpawnedRunProcess = {
  on: (event: "error", callback: (error: Error) => void) => unknown;
  stdout?: { on: (event: "data", callback: (chunk: unknown) => void) => unknown } | null;
  stderr?: { on: (event: "data", callback: (chunk: unknown) => void) => unknown } | null;
  unref?: () => void;
} & {
  on: (event: "exit", callback: (code: number | null, signal: NodeJS.Signals | null) => void) => unknown;
};
type SpawnRunner = (command: string, args: string[], options: { cwd: string; env: NodeJS.ProcessEnv }) => SpawnedRunProcess;

type CliResolution = {
  command: string;
  prefixArgs: string[];
  runtime: string;
};

type DraftPatchInput = {
  candidateId?: string;
  label?: string;
  cvFiles?: File[];
  cvText?: string;
  cvTexts?: Array<{ originalName?: string; text: string }>;
  jdFiles?: File[];
  jdFileDisplayNames?: string[];
  jdTexts?: string[];
  jdTextDisplayNames?: string[];
  now?: Date;
};

type CvIssue = {
  originalName: string;
  quality: "readable" | "scanned" | "empty";
};

type WebUploadManifest = UploadManifest & {
  cvIssues?: CvIssue[];
  needsManualText?: boolean;
};

type CvSidecarRecord = {
  record: UploadedInputFile;
  pdfOriginalName: string;
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
    throw new RunActionError("run_busy", "该运行批次已在排队或运行中。", 409);
  }
  if (action === "resume_failed" && current?.status !== "failed") {
    throw new RunActionError("not_failed", "只有失败的运行批次可以从失败阶段继续。");
  }

  const cliArgs = await buildCliArgs(runDir, action);
  let command: string;
  let finalArgs: string[];
  let cliRuntime: string;

  if (spawnRunner === defaultSpawnRunner) {
    const resolved = await resolveCli();
    command = resolved.command;
    finalArgs = [...resolved.prefixArgs, ...cliArgs];
    cliRuntime = resolved.runtime;
  } else {
    command = process.env.SHOTGUNCV_CLI_COMMAND ?? "shotguncv";
    finalArgs = cliArgs;
    cliRuntime = "test-runner";
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

  const currentStage = action === "resume_failed" ? firstIncompleteStage(await listStageDirs(runDir)) : "ingest";
  await writeRunStatus(runDir, {
    status: "running",
    current_stage: currentStage,
    started_at: startedAt,
    finished_at: null,
    error_stage: null,
    error_summary: null,
    last_action: action,
  });

  const cwd = path.resolve(getRunsDir(), "..");
  const expectedOutputs = expectedOutputPaths(runDir);
  await appendRunActionLog(runDir, {
    event: "web_cli_start",
    runId,
    action,
    candidateId: (await readManifestIfExists(runDir))?.candidateId ?? null,
    cwd,
    command,
    args: finalArgs,
    cliRuntime,
    runDir,
    cvPath: path.join(runDir, "input_files", "cv"),
    jdPath: path.join(runDir, "input_files", "jd"),
    expectedOutputPath: expectedOutputs.report,
  });

  const child = spawnRunner(command, finalArgs, { cwd, env: process.env });
  const output = createOutputBuffer();
  child.stdout?.on("data", (chunk) => output.push("stdout", chunk));
  child.stderr?.on("data", (chunk) => output.push("stderr", chunk));
  child.on("error", async (error) => {
    const outputSnapshot = output.snapshot();
    await appendRunActionLog(runDir, {
      event: "web_cli_error",
      runId,
      action,
      cwd,
      command,
      args: finalArgs,
      errorMessage: error.message,
      stdout: outputSnapshot.stdout,
      stderr: outputSnapshot.stderr,
      expectedOutputPath: expectedOutputs.report,
      expectedOutputExists: await exists(expectedOutputs.report),
    });
    await markRunFailed(runDir, startedAt, currentStage, action, `CLI 启动失败：${error.message}${formatCapturedOutput(outputSnapshot.all)}`);
  });
  child.on("exit", async (code, signal) => {
    const outputSnapshot = output.snapshot();
    const outputExists = await exists(expectedOutputs.report);
    const statusAfterExit = await readRunStatus(runDir);
    await appendRunActionLog(runDir, {
      event: "web_cli_exit",
      runId,
      action,
      cwd,
      command,
      args: finalArgs,
      exitCode: code,
      signal,
      stdout: outputSnapshot.stdout,
      stderr: outputSnapshot.stderr,
      expectedOutputPath: expectedOutputs.report,
      expectedOutputExists: outputExists,
      parsedResultSummary: summarizeRunStatus(statusAfterExit),
    });
    if (code === 0) {
      if (!outputExists) {
        await markRunFailed(
          runDir,
          startedAt,
          currentStage,
          action,
          `CLI 已退出但未生成预期报告：${expectedOutputs.report}${formatCapturedOutput(outputSnapshot.all)}`,
        );
      }
      return;
    }
    const reason = signal ? `CLI 运行失败，信号 ${signal}` : `CLI 运行失败，退出码 ${code ?? "未知"}`;
    if (statusAfterExit?.status === "failed" && statusAfterExit.error_stage) {
      await writeRunStatus(runDir, {
        ...statusAfterExit,
        status: "failed",
        current_stage: statusAfterExit.current_stage ?? statusAfterExit.error_stage,
        started_at: statusAfterExit.started_at ?? startedAt,
        finished_at: statusAfterExit.finished_at ?? nowIso(),
        error_stage: statusAfterExit.error_stage,
        error_summary: buildUserFacingFailureSummary(statusAfterExit),
        last_action: action,
      });
      return;
    }
    await markRunFailed(runDir, startedAt, currentStage, action, buildCliFailureSummary(reason, outputSnapshot.all));
  });
  child.unref?.();

  return { runId, status: "queued", action };
}


export async function deleteRun(runId: string) {
  const runDir = resolveRunDir(runId);
  const current = await readRunStatus(runDir);
  const inferred = current?.status ?? (await inferStatus(runDir));
  if (inferred === "running" || inferred === "queued") {
    throw new RunActionError("run_busy", "正在运行的批次不能删除。", 409);
  }
  if (inferred !== "draft" && inferred !== "failed") {
    throw new RunActionError("delete_not_allowed", "只能删除草稿或失败的运行批次。", 409);
  }
  await rm(runDir, { recursive: true, force: true });
  return { runId, deleted: true };
}


export async function patchRunDraft(runId: string, input: DraftPatchInput) {
  const runDir = resolveRunDir(runId);
  const current = await readRunStatus(runDir);
  const inferred = current?.status ?? (await inferStatus(runDir));
  if (inferred !== "draft") {
    throw new RunActionError("not_draft", "只能编辑草稿状态的运行批次。", 409);
  }

  const manifestPath = path.join(runDir, "ingest", "upload_manifest.json");
  const manifest = JSON.parse(await readFile(manifestPath, "utf-8")) as WebUploadManifest;
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

  const cvFiles = normalizePatchFiles(input.cvFiles);
  if (cvFiles.length > 0) {
    cvFiles.forEach(validateFile);
    const cvDir = path.join(runDir, "input_files", "cv");
    await rm(cvDir, { recursive: true, force: true });
    await mkdir(cvDir, { recursive: true });
    manifest.files = manifest.files.filter((file) => file.role !== "cv");
    manifest.files.unshift(...(await writeRoleFiles(runDir, "cv", cvFiles, uploadedAt)));
  }

  const cvTextEntries = normalizeCvTextEntries(input);
  if (cvTextEntries.length > 0) {
    const sidecars = await writeCvTextSidecars(runDir, manifest, cvTextEntries, uploadedAt);
    const sidecarRecords = sidecars.map((sidecar) => sidecar.record);
    const replacedPaths = new Set(sidecarRecords.map((record) => record.storedRelativePath));
    manifest.files = [
      ...manifest.files.filter((file) => !replacedPaths.has(file.storedRelativePath)),
      ...sidecarRecords,
    ];
    const resolvedOriginalNames = new Set(sidecars.map((sidecar) => sidecar.pdfOriginalName));
    manifest.cvIssues = (manifest.cvIssues ?? []).filter((issue) => !resolvedOriginalNames.has(issue.originalName));
    manifest.needsManualText = (manifest.cvIssues ?? []).length > 0;
  }

  const usedJdNames = new Set(
    manifest.files
      .filter((file) => file.role === "jd")
      .map((file) => path.basename(file.storedRelativePath).toLowerCase()),
  );
  const jdFiles = normalizePatchFiles(input.jdFiles);
  if (jdFiles.length > 0) {
    manifest.files.push(
      ...(await writeRoleFiles(runDir, "jd", jdFiles, uploadedAt, usedJdNames, (input.jdFileDisplayNames ?? []).slice(jdIndex))),
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


function normalizeCvTextEntries(input: DraftPatchInput): Array<{ originalName?: string; text: string }> {
  if (input.cvTexts && input.cvTexts.length > 0) {
    return input.cvTexts
      .map((entry) => ({ originalName: entry.originalName?.trim(), text: entry.text.trim() }))
      .filter((entry) => entry.text);
  }
  const cvText = input.cvText?.trim();
  return cvText ? [{ text: cvText }] : [];
}


function normalizePatchFiles(files: File[] | undefined): File[] {
  return (files ?? []).filter((file) => !(file.size === 0 && file.name.trim() === ""));
}


async function writeCvTextSidecars(
  runDir: string,
  manifest: WebUploadManifest,
  entries: Array<{ originalName?: string; text: string }>,
  uploadedAt: string,
): Promise<CvSidecarRecord[]> {
  const pdfFiles = manifest.files.filter((file) => file.role === "cv" && isPdfUpload(file));
  const usedPdfIndexes = new Set<number>();
  const records: CvSidecarRecord[] = [];
  for (const entry of entries) {
    const matchIndex = findPdfForCvText(pdfFiles, entry.originalName, usedPdfIndexes);
    if (matchIndex < 0) {
      throw new RunActionError("cv_pdf_not_found", "未找到可匹配的 PDF 简历文件。", 400);
    }
    usedPdfIndexes.add(matchIndex);
    const pdfFile = pdfFiles[matchIndex];
    const pdfRelativePath = pdfFile.storedRelativePath.replaceAll("\\", "/");
    const parsed = path.posix.parse(pdfRelativePath);
    const sidecarRelativePath = path.posix.join(parsed.dir, `${parsed.name}.txt`);
    const outputPath = path.join(runDir, sidecarRelativePath);
    assertInside(path.join(runDir, parsed.dir), outputPath);
    await writeFile(outputPath, entry.text, "utf-8");
    records.push({
      pdfOriginalName: pdfFile.originalName,
      record: {
        role: "cv",
        originalName: `${parsed.name}.txt`,
        storedRelativePath: sidecarRelativePath,
        sizeBytes: Buffer.byteLength(entry.text, "utf-8"),
        contentType: "text/plain",
        uploadedAt,
      },
    });
  }
  return records;
}


function findPdfForCvText(files: UploadedInputFile[], originalName: string | undefined, usedIndexes: Set<number>): number {
  if (originalName) {
    const target = originalName.toLowerCase();
    const explicitIndex = files.findIndex((file, index) => !usedIndexes.has(index) && file.originalName.toLowerCase() === target);
    if (explicitIndex >= 0) {
      return explicitIndex;
    }
  }
  return files.findIndex((_, index) => !usedIndexes.has(index));
}


function isPdfUpload(file: UploadedInputFile): boolean {
  return file.contentType === "application/pdf" || path.extname(file.originalName).toLowerCase() === ".pdf";
}


function defaultSpawnRunner(command: string, args: string[], options: { cwd: string; env: NodeJS.ProcessEnv }) {
  return spawn(command, args, {
    cwd: options.cwd,
    detached: true,
    env: options.env,
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
}


async function resolveCli(): Promise<CliResolution> {
  const explicitCommand = process.env.SHOTGUNCV_CLI_COMMAND;
  if (explicitCommand) {
    if (await commandAvailable(explicitCommand)) {
      return { command: explicitCommand, prefixArgs: [], runtime: "explicit" };
    }
    throw new RunActionError(
      "cli_not_found",
      `CLI 命令未找到（${explicitCommand}），请确认已安装并在 PATH 中，或取消 SHOTGUNCV_CLI_COMMAND 环境变量以使用自动发现。`,
      503,
    );
  }

  const python = await findPython();
  if (python) {
    return { command: python, prefixArgs: ["-m", "shotguncv_cli.main"], runtime: "python-module" };
  }

  if (await commandAvailable("shotguncv")) {
    return { command: "shotguncv", prefixArgs: [], runtime: "path-script" };
  }

  throw new RunActionError(
    "cli_not_found",
    "未找到可用的 shotguncv CLI 运行时。请确认 Python 环境可以导入 shotguncv_cli.main 和 PyMuPDF，或设置 SHOTGUNCV_CLI_COMMAND。",
    503,
  );
}

async function commandAvailable(command: string): Promise<boolean> {
  if (command.includes("/") || command.includes("\\") || path.isAbsolute(command)) {
    try {
      await access(command);
      return true;
    } catch {
      return false;
    }
  }
  const resolver = process.platform === "win32" ? "where.exe" : "which";
  const result = spawnSync(resolver, [command], { env: process.env, encoding: "utf-8", windowsHide: true });
  return result.status === 0;
}

async function findPython(): Promise<string | null> {
  const candidates = [
    process.env.SHOTGUNCV_PYTHON,
    path.join(path.resolve(getRunsDir(), ".."), ".venv", "Scripts", "python.exe"),
    "python",
    "python3",
  ].filter((candidate): candidate is string => Boolean(candidate));
  const seen = new Set<string>();
  for (const candidate of candidates) {
    const key = candidate.toLowerCase();
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    if (await commandAvailable(candidate) && (await pythonRuntimeAvailable(candidate))) {
      return candidate;
    }
  }
  return null;
}

async function pythonRuntimeAvailable(pythonCmd: string): Promise<boolean> {
  try {
    const result = spawnSync(pythonCmd, ["-c", "import shotguncv_cli.main; import fitz"], {
      env: process.env,
      encoding: "utf-8",
      windowsHide: true,
      timeout: 10000,
    });
    return result.status === 0;
  } catch {
    return false;
  }
}


function createOutputBuffer() {
  const stdoutChunks: string[] = [];
  const stderrChunks: string[] = [];
  function trim(chunks: string[]) {
    while (chunks.join("").length > 4000) {
      chunks.shift();
    }
  }
  return {
    push(stream: "stdout" | "stderr", chunk: unknown) {
      const target = stream === "stdout" ? stdoutChunks : stderrChunks;
      target.push(Buffer.isBuffer(chunk) ? chunk.toString("utf-8") : String(chunk));
      trim(target);
    },
    snapshot() {
      const stdout = stdoutChunks.join("").trim().slice(-4000);
      const stderr = stderrChunks.join("").trim().slice(-4000);
      return {
        stdout,
        stderr,
        all: [stdout, stderr].filter(Boolean).join("\n").slice(-4000),
      };
    },
  };
}


function formatCapturedOutput(output: string): string {
  return output ? `。输出：${output}` : "";
}


function buildCliFailureSummary(reason: string, output: string): string {
  if (!output.trim()) {
    return reason;
  }
  return `${reason}。请查看本地运行日志获取技术细节，修正输入或配置后重试。`;
}


function buildUserFacingFailureSummary(status: RunStatusFile): string {
  const rawSummary = status.error_summary ?? "";
  const code = status.error_code ?? "";
  if (code === "STRUCTURED_ANALYSIS_INVALID" || rawSummary.includes("Structured analysis validation failed")) {
    return buildStructuredAnalysisFailureSummary(rawSummary);
  }
  if (status.status_kind === "parse_error") {
    return "输入解析失败：请检查上传的简历 PDF/JD 文本是否可复制、非空且没有乱码，然后重新上传或补充可读文本。";
  }
  if (isModelNetworkFailure(code, rawSummary)) {
    return buildModelNetworkFailureSummary();
  }
  if (status.status_kind === "model_error" || code.startsWith("MODEL_")) {
    return "模型服务调用失败：请检查 API Key、provider、model 权限和网络连通性，确认配置后重试。";
  }
  return "运行失败：请根据失败阶段检查对应输入或配置，修正后重试。";
}


function buildModelNetworkFailureSummary(): string {
  return "模型请求超时或网络连接失败：结构化分析已经开始，但模型没有稳定返回。可先只保留 1 个 JD、裁短简历，切换更快的分析器模型，或提高 SHOTGUNCV_ANALYZER_TIMEOUT_SEC 后重试。";
}


function isModelNetworkFailure(code: string, rawSummary: string): boolean {
  const text = rawSummary.toLowerCase();
  return code === "MODEL_NETWORK_ERROR" || text.includes("timed out") || text.includes("timeout") || text.includes("network connection failed");
}


function buildStructuredAnalysisFailureSummary(rawSummary: string): string {
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


async function markRunFailed(
  runDir: string,
  startedAt: string,
  currentStage: RunStatusFile["current_stage"],
  action: RunAction,
  errorSummary: string,
) {
  await writeRunStatus(runDir, {
    status: "failed",
    current_stage: currentStage,
    started_at: startedAt,
    finished_at: nowIso(),
    error_stage: currentStage,
    error_summary: errorSummary,
    last_action: action,
  });
}

function expectedOutputPaths(runDir: string) {
  return {
    report: path.join(runDir, "report", "summary.md"),
  };
}

function summarizeRunStatus(status: RunStatusFile | null) {
  if (!status) {
    return null;
  }
  return {
    status: status.status,
    statusKind: status.status_kind,
    currentStage: status.current_stage,
    errorStage: status.error_stage,
    errorCode: status.error_code,
    errorSummary: status.error_summary,
    finishedAt: status.finished_at,
  };
}

async function appendRunActionLog(runDir: string, payload: Record<string, unknown>): Promise<void> {
  const logsDir = path.join(runDir, "logs");
  await mkdir(logsDir, { recursive: true });
  await appendFile(
    path.join(logsDir, "web_run_action.jsonl"),
    `${JSON.stringify({ timestamp: nowIso(), ...payload })}\n`,
    "utf-8",
  );
}


async function buildCliArgs(runDir: string, action: RunAction): Promise<string[]> {
  const manifest = await readManifestIfExists(runDir);
  if (action === "resume_failed" && manifest === null) {
    return ["run", "--run-dir", runDir, "--resume"];
  }
  if (manifest === null) {
    throw new RunActionError("missing_upload_manifest", "启动运行需要先完成草稿上传清单。");
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
    throw new RunActionError("empty_file", `文件 ${file.name} 为空。`);
  }
  if (file.size > MAX_FILE_BYTES) {
    throw new RunActionError("file_too_large", `文件 ${file.name} 超过 10MB 限制。`);
  }
  if (!SUPPORTED_EXTENSIONS.has(path.extname(file.name).toLowerCase())) {
    throw new RunActionError("unsupported_file_type", `不支持的文件类型：${path.extname(file.name) || "无扩展名"}。`);
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
    throw new RunActionError("invalid_run_id", "运行批次编号包含不安全字符。");
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
    throw new RunActionError("unsafe_filename", "上传文件名不能包含路径。");
  }
  const safeName = normalized.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "");
  if (!safeName) {
    throw new RunActionError("unsafe_filename", "上传文件名无效。");
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
    throw new RunActionError("unsafe_path", "解析后的路径超出运行目录。");
  }
}


function nowIso(): string {
  return new Date().toISOString();
}
