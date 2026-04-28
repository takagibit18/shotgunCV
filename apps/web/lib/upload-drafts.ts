import { mkdir, open, stat, writeFile } from "node:fs/promises";
import path from "node:path";

import type { UploadManifest, UploadedInputFile } from "./types";
import { getRunsDir } from "./runs";


type DraftFile = File;

type CreateRunDraftInput = {
  candidateId: string;
  label?: string;
  cvFiles: DraftFile[];
  jdFiles: DraftFile[];
  now?: Date;
};

type CreateRunDraftResult = {
  runId: string;
  status: "draft";
  uploadManifestPath: string;
  nextCommand: string;
};

type DraftErrorCode =
  | "missing_candidate_id"
  | "missing_cv"
  | "missing_jd"
  | "empty_file"
  | "file_too_large"
  | "unsupported_file_type"
  | "unsafe_filename"
  | "run_exists"
  | "write_failed";

const MAX_FILE_BYTES = 10 * 1024 * 1024;
const SUPPORTED_EXTENSIONS = new Set([".txt", ".md", ".pdf", ".png", ".jpg", ".jpeg"]);
const UPLOAD_MANIFEST_PATH = "ingest/upload_manifest.json";


export class DraftCreationError extends Error {
  code: DraftErrorCode;

  constructor(code: DraftErrorCode, message: string) {
    super(message);
    this.name = "DraftCreationError";
    this.code = code;
  }
}


export async function createRunDraft(input: CreateRunDraftInput): Promise<CreateRunDraftResult> {
  const candidateId = input.candidateId.trim();
  if (!candidateId) {
    throw new DraftCreationError("missing_candidate_id", "Candidate id is required.");
  }
  if (input.cvFiles.length === 0) {
    throw new DraftCreationError("missing_cv", "At least one CV file is required.");
  }
  if (input.jdFiles.length === 0) {
    throw new DraftCreationError("missing_jd", "At least one JD file is required.");
  }
  [...input.cvFiles, ...input.jdFiles].forEach((file) => {
    validateUploadFile(file);
    sanitizeFileName(file.name);
  });

  const now = input.now ?? new Date();
  const label = input.label?.trim() ?? "";
  const runId = buildRunId(label || candidateId, now);
  const runsDir = getRunsDir();
  const runDir = path.join(runsDir, runId);
  assertInside(runsDir, runDir);
  await reserveRunDirectory(runDir);

  try {
    const uploadedAt = now.toISOString();
    const files: UploadedInputFile[] = [
      ...(await writeRoleFiles(runDir, "cv", input.cvFiles, uploadedAt)),
      ...(await writeRoleFiles(runDir, "jd", input.jdFiles, uploadedAt)),
    ];
    const nextCommand = buildNextCommand(runId, candidateId);
    const manifest: UploadManifest = {
      schemaVersion: "v0.5.1-upload-manifest",
      candidateId,
      label,
      createdAt: uploadedAt,
      files,
      nextCommand,
    };
    await writeDefaultRunConfig(runDir, label);
    await writeFile(path.join(runDir, UPLOAD_MANIFEST_PATH), JSON.stringify(manifest, null, 2), "utf-8");
    return {
      runId,
      status: "draft",
      uploadManifestPath: UPLOAD_MANIFEST_PATH,
      nextCommand,
    };
  } catch (error) {
    if (error instanceof DraftCreationError) {
      throw error;
    }
    throw new DraftCreationError("write_failed", error instanceof Error ? error.message : "Failed to create draft run.");
  }
}


function buildRunId(label: string, now: Date): string {
  const slug = label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
  const stamp = now.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "").replace("T", "-");
  return `${slug || "run"}-${stamp}`;
}


async function reserveRunDirectory(runDir: string): Promise<void> {
  try {
    await stat(runDir);
    throw new DraftCreationError("run_exists", "Run already exists.");
  } catch (error) {
    if (error instanceof DraftCreationError) {
      throw error;
    }
  }
  await mkdir(path.join(runDir, "ingest"), { recursive: true });
  await mkdir(path.join(runDir, "config"), { recursive: true });
}


async function writeRoleFiles(
  runDir: string,
  role: "cv" | "jd",
  files: DraftFile[],
  uploadedAt: string,
): Promise<UploadedInputFile[]> {
  const outputDir = path.join(runDir, "input_files", role);
  await mkdir(outputDir, { recursive: true });

  const records: UploadedInputFile[] = [];
  for (const file of files) {
    const safeName = sanitizeFileName(file.name);
    const bytes = Buffer.from(await file.arrayBuffer());
    const outputPath = path.join(outputDir, safeName);
    assertInside(outputDir, outputPath);
    await writeFile(outputPath, bytes);
    records.push({
      role,
      originalName: file.name,
      storedRelativePath: path.posix.join("input_files", role, safeName),
      sizeBytes: file.size,
      contentType: file.type || "application/octet-stream",
      uploadedAt,
    });
  }
  return records;
}


function validateUploadFile(file: DraftFile): void {
  if (file.size === 0) {
    throw new DraftCreationError("empty_file", `File ${file.name} is empty.`);
  }
  if (file.size > MAX_FILE_BYTES) {
    throw new DraftCreationError("file_too_large", `File ${file.name} exceeds the 10MB limit.`);
  }
  const extension = path.extname(file.name).toLowerCase();
  if (!SUPPORTED_EXTENSIONS.has(extension)) {
    throw new DraftCreationError("unsupported_file_type", `Unsupported file type: ${extension || "none"}.`);
  }
}


function sanitizeFileName(name: string): string {
  const normalized = name.replaceAll("\\", "/");
  if (normalized.includes("/") || normalized.includes("..")) {
    throw new DraftCreationError("unsafe_filename", "Uploaded filenames must not contain paths.");
  }
  const safeName = normalized.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "");
  if (!safeName) {
    throw new DraftCreationError("unsafe_filename", "Uploaded filename is invalid.");
  }
  return safeName;
}


function assertInside(parent: string, child: string): void {
  const relative = path.relative(path.resolve(parent), path.resolve(child));
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new DraftCreationError("unsafe_filename", "Resolved path escapes the configured runs directory.");
  }
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


async function writeDefaultRunConfig(runDir: string, label: string): Promise<void> {
  const config = {
    analyzer: { provider: "openai", model: "" },
    generator: { provider: "openai", model: "" },
    judge: { provider: "openai", model: "" },
    planner: { provider: "openai", model: "" },
    openai: { base_url: null, api_key_env: "OPENAI_API_KEY", env_file: ".env" },
    input_extraction: {
      ocr_provider: "local_ocr",
      vision_provider: "openai_vision",
      vision_model: "",
      ocr_languages: "eng+chi_sim",
    },
    run_metadata: { label },
  };
  const handle = await open(path.join(runDir, "config", "run_config.json"), "wx");
  await handle.writeFile(JSON.stringify(config, null, 2), "utf-8");
  await handle.close();
}


export type { CreateRunDraftInput, CreateRunDraftResult };
