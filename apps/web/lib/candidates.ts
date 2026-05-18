import { access, readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";

import type { UploadManifest } from "./types";
import { getRunsDir } from "./runs";

type CandidateCvFile = {
  originalName: string;
  sourceRunId: string;
  storedRelativePath: string;
  sizeBytes: number;
  contentType: string;
  uploadedAt: string;
};

type CandidateSummary = {
  candidateId: string;
  displayName: string;
  initials: string;
  latestRunId: string;
  latestLabel: string;
  updatedAt: string;
  runCount: number;
  cvFiles: CandidateCvFile[];
};

type CandidateAwareManifest = UploadManifest & {
  candidateDisplayName?: string;
};

type RunManifestRecord = {
  runId: string;
  updatedAt: string;
  manifest: CandidateAwareManifest;
};

export async function listCandidates(): Promise<CandidateSummary[]> {
  const runsDir = getRunsDir();
  const entries = await readdir(runsDir, { withFileTypes: true }).catch(() => []);
  const manifests = (
    await Promise.all(
      entries
        .filter((entry) => entry.isDirectory())
        .map(async (entry): Promise<RunManifestRecord | null> => {
          const runDir = path.join(runsDir, entry.name);
          const manifest = await readManifest(path.join(runDir, "ingest", "upload_manifest.json"));
          if (!manifest?.candidateId) {
            return null;
          }
          const metadata = await stat(runDir).catch(() => null);
          return {
            runId: entry.name,
            updatedAt: metadata?.mtime.toISOString() ?? manifest.createdAt,
            manifest,
          };
        }),
    )
  )
    .filter((record): record is RunManifestRecord => record !== null)
    .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));

  const grouped = new Map<string, CandidateSummary>();
  const seenCvFiles = new Map<string, Set<string>>();

  for (const record of manifests) {
    const candidateId = record.manifest.candidateId;
    const displayName = record.manifest.candidateDisplayName?.trim() || candidateId;
    const existing = grouped.get(candidateId);
    if (existing) {
      existing.runCount += 1;
    } else {
      grouped.set(candidateId, {
        candidateId,
        displayName,
        initials: buildInitials(displayName),
        latestRunId: record.runId,
        latestLabel: record.manifest.label,
        updatedAt: record.updatedAt,
        runCount: 1,
        cvFiles: [],
      });
      seenCvFiles.set(candidateId, new Set());
    }

    const candidate = grouped.get(candidateId);
    const seen = seenCvFiles.get(candidateId);
    if (!candidate || !seen) {
      continue;
    }

    for (const file of record.manifest.files.filter((item) => item.role === "cv")) {
      const signature = `${file.originalName}\0${file.sizeBytes}\0${file.contentType}`;
      if (seen.has(signature)) {
        continue;
      }
      const sourcePath = resolveRunFilePath(path.join(runsDir, record.runId), file.storedRelativePath);
      if (!sourcePath || !(await pathExists(sourcePath))) {
        continue;
      }
      seen.add(signature);
      candidate.cvFiles.push({
        originalName: file.originalName,
        sourceRunId: record.runId,
        storedRelativePath: file.storedRelativePath,
        sizeBytes: file.sizeBytes,
        contentType: file.contentType,
        uploadedAt: file.uploadedAt,
      });
    }
  }

  return Array.from(grouped.values()).sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
}

export function buildCandidateDisplayName(candidateId: string, candidateDisplayName?: string): string {
  return candidateDisplayName?.trim() || candidateId;
}

function buildInitials(displayName: string): string {
  const trimmed = displayName.trim();
  if (!trimmed) {
    return "候";
  }
  const asciiWords = trimmed.match(/[A-Za-z0-9]+/g);
  if (asciiWords && asciiWords.length > 0) {
    return asciiWords
      .slice(0, 2)
      .map((word) => word[0])
      .join("")
      .toUpperCase();
  }
  return trimmed.slice(0, 2);
}

async function readManifest(filePath: string): Promise<CandidateAwareManifest | null> {
  try {
    return JSON.parse(await readFile(filePath, "utf-8")) as CandidateAwareManifest;
  } catch {
    return null;
  }
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

async function pathExists(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

export type { CandidateCvFile, CandidateSummary, CandidateAwareManifest };
