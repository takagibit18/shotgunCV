import { spawnSync } from "node:child_process";
import path from "node:path";

import { getRunsDir } from "./runs";


type DependencyReport = {
  python: { found: boolean; path: string | null };
  shotguncv: { importable: boolean };
  fitz: { installed: boolean; detail: string };
  pytesseract: { installed: boolean; detail: string };
  tesseractExe: { found: boolean; detail: string };
  openaiKey: { configured: boolean };
  overall: "healthy" | "degraded" | "blocked";
};

type CheckOptions = {
  forceRefresh?: boolean;
};

type InstallPackageName = "fitz" | "pytesseract";

let cachedReport: { value: DependencyReport; expiresAt: number } | null = null;
const CACHE_MS = 60_000;


export async function checkPythonDependencies(options: CheckOptions = {}): Promise<DependencyReport> {
  if (!options.forceRefresh && cachedReport && cachedReport.expiresAt > Date.now()) {
    return cachedReport.value;
  }
  const pythonPath = resolvePythonPath();
  const report = buildDependencyReport(pythonPath);
  cachedReport = { value: report, expiresAt: Date.now() + CACHE_MS };
  return report;
}


export async function installPythonDependency(packageName: InstallPackageName): Promise<{ success: boolean; output: string }> {
  const pythonPath = resolvePythonPath();
  if (!pythonPath) {
    return { success: false, output: "未找到 Python 运行时。" };
  }
  const pipPackage = packageName === "fitz" ? "PyMuPDF" : "pytesseract";
  const args = ["-m", "pip", "install", pipPackage];
  if (!isVenvPython(pythonPath)) {
    args.push("--user");
  }
  const result = spawnSync(pythonPath, args, {
    cwd: path.resolve(getRunsDir(), ".."),
    env: process.env,
    encoding: "utf-8",
    timeout: 120_000,
    windowsHide: true,
  });
  cachedReport = null;
  const output = [result.stdout, result.stderr, result.error?.message].filter(Boolean).join("\n").trim();
  return { success: result.status === 0, output };
}


function buildDependencyReport(pythonPath: string | null): DependencyReport {
  const shotguncv = pythonPath ? importCheck(pythonPath, "shotguncv_cli.main") : { ok: false, detail: "未找到 Python。" };
  const fitz = pythonPath ? importCheck(pythonPath, "fitz") : { ok: false, detail: "未找到 Python。" };
  const pytesseract = pythonPath ? importCheck(pythonPath, "pytesseract") : { ok: false, detail: "未找到 Python。" };
  const tesseractExe = executableCheck(process.platform === "win32" ? "where.exe" : "which", ["tesseract"]);
  const openaiKey = Boolean(process.env.OPENAI_API_KEY?.trim());
  const overall = !shotguncv.ok ? "blocked" : fitz.ok || openaiKey ? "healthy" : "degraded";

  return {
    python: { found: Boolean(pythonPath), path: pythonPath },
    shotguncv: { importable: shotguncv.ok },
    fitz: { installed: fitz.ok, detail: fitz.detail },
    pytesseract: { installed: pytesseract.ok, detail: pytesseract.detail },
    tesseractExe: { found: tesseractExe.ok, detail: tesseractExe.detail },
    openaiKey: { configured: openaiKey },
    overall,
  };
}


function resolvePythonPath(): string | null {
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
    const resolved = resolveExecutable(candidate);
    if (resolved) {
      return resolved;
    }
  }
  return null;
}


function resolveExecutable(command: string): string | null {
  if (command.includes("/") || command.includes("\\") || path.isAbsolute(command)) {
    return executableCheck(command, ["--version"]).ok ? command : null;
  }
  const result = executableCheck(process.platform === "win32" ? "where.exe" : "which", [command]);
  if (!result.ok) {
    return null;
  }
  return result.detail.split(/\r?\n/)[0]?.trim() || command;
}


function importCheck(pythonPath: string, moduleName: string): { ok: boolean; detail: string } {
  const result = spawnSync(pythonPath, ["-c", `import ${moduleName}; print("ok")`], {
    cwd: path.resolve(getRunsDir(), ".."),
    env: process.env,
    encoding: "utf-8",
    timeout: 10_000,
    windowsHide: true,
  });
  const detail = [result.stdout, result.stderr, result.error?.message].filter(Boolean).join("\n").trim();
  return { ok: result.status === 0, detail: detail || (result.status === 0 ? "ok" : "导入失败") };
}


function executableCheck(command: string, args: string[]): { ok: boolean; detail: string } {
  const result = spawnSync(command, args, {
    env: process.env,
    encoding: "utf-8",
    timeout: 10_000,
    windowsHide: true,
  });
  const detail = [result.stdout, result.stderr, result.error?.message].filter(Boolean).join("\n").trim();
  if (result.status !== 0) {
    return { ok: false, detail: "未找到" };
  }
  return { ok: result.status === 0, detail: detail || (result.status === 0 ? "ok" : "未找到") };
}


function isVenvPython(pythonPath: string): boolean {
  const normalized = pythonPath.replaceAll("\\", "/").toLowerCase();
  return normalized.includes("/.venv/") || Boolean(process.env.VIRTUAL_ENV);
}


export type { DependencyReport, InstallPackageName };
