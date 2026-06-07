import { existsSync } from "node:fs";
import { access, readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";

import { getRunsDir } from "./runs";
import type { RunConfig } from "./types";

type SettingsCheckStatus = "pass" | "warning" | "fail";

type SettingsCheck = {
  label: string;
  status: SettingsCheckStatus;
  detail: string;
};

type ProviderRoleSummary = {
  role: "analyzer" | "generator" | "judge" | "planner";
  provider: string;
  model: string;
};

type InputExtractionSummary = {
  ocrProvider: string;
  visionProvider: string;
  visionModel: string;
  ocrLanguages: string;
};

type LatestConfigSummary = {
  runId: string;
  label: string;
  providers: ProviderRoleSummary[];
  baseUrlHost: string;
  apiKeyEnv: string;
  envFile: string;
  inputExtraction: InputExtractionSummary;
} | null;

type SettingsOverview = {
  runsDir: string;
  displayRunsDir: string;
  runsDirSource: "env" | "default";
  runsDirReadable: boolean;
  runCount: number;
  configSnapshotCount: number;
  configIssueCount: number;
  artifactIssueCount: number;
  unknownProviderCount: number;
  configIssueRunIds: string[];
  artifactIssueRunIds: string[];
  unknownProviderRunIds: string[];
  latestConfig: LatestConfigSummary;
  checks: SettingsCheck[];
};

type RunConfigReadResult = {
  runId: string;
  modifiedTime: number;
  config: RunConfig | null;
  issue: string | null;
};

const JSON_ARTIFACTS = [
  "run_status.json",
  "ingest/manifest.json",
  "ingest/upload_manifest.json",
  "analyze/requirement_matrix.json",
  "analyze/preflight_gates.json",
  "evaluate/scorecards.json",
  "evaluate/ranking_explanations.json",
  "plan/application_strategies.json",
  "generate/resume_variants.json",
];

export async function loadSettingsOverview(): Promise<SettingsOverview> {
  const runsDir = getRunsDir();
  const runsDirSource = process.env.SHOTGUNCV_RUNS_DIR ? "env" : "default";
  const displayRunsDir = maskPath(runsDir);

  if (!(await pathReadable(runsDir))) {
    return {
      runsDir,
      displayRunsDir,
      runsDirSource,
      runsDirReadable: false,
      runCount: 0,
      configSnapshotCount: 0,
      configIssueCount: 1,
      artifactIssueCount: 0,
      unknownProviderCount: 0,
      configIssueRunIds: [],
      artifactIssueRunIds: [],
      unknownProviderRunIds: [],
      latestConfig: null,
      checks: [
        { label: "运行目录", status: "fail", detail: "运行目录不可读，请检查 SHOTGUNCV_RUNS_DIR 或默认运行路径。" },
        { label: "运行清单", status: "warning", detail: "无法读取运行清单。" },
        { label: "配置快照", status: "warning", detail: "无法检查运行配置。" },
        { label: "shotguncv CLI", status: cliVisible() ? "pass" : "warning", detail: buildCliDetail() },
      ],
    };
  }

  const entries = await readdir(runsDir, { withFileTypes: true });
  const runEntries = entries.filter((entry) => entry.isDirectory());
  const configResults = await Promise.all(
    runEntries.map(async (entry) => readRunConfig(runsDir, entry.name)),
  );
  const artifactResults = await Promise.all(
    runEntries.map(async (entry) => ({
      runId: entry.name,
      issueCount: await countMalformedArtifacts(path.join(runsDir, entry.name)),
    })),
  );
  const parseableConfigs = configResults.filter((result) => result.config);
  const latestConfig = buildLatestConfig(parseableConfigs);
  const configIssueRunIds = configResults.filter((result) => result.issue).map((result) => result.runId);
  const artifactIssueRunIds = artifactResults.filter((result) => result.issueCount > 0).map((result) => result.runId);
  const unknownProviderRunIds = parseableConfigs
    .filter((result) => countUnknownProviders(result.config) > 0)
    .map((result) => result.runId);
  const configIssueCount = configIssueRunIds.length;
  const artifactIssueCount = artifactResults.reduce((total, result) => total + result.issueCount, 0);
  const unknownProviderCount = parseableConfigs.reduce(
    (total, result) => total + countUnknownProviders(result.config),
    0,
  );

  return {
    runsDir,
    displayRunsDir,
    runsDirSource,
    runsDirReadable: true,
    runCount: runEntries.length,
    configSnapshotCount: parseableConfigs.length,
    configIssueCount,
    artifactIssueCount,
    unknownProviderCount,
    configIssueRunIds,
    artifactIssueRunIds,
    unknownProviderRunIds,
    latestConfig,
    checks: [
      { label: "运行目录", status: "pass", detail: `当前读取 ${displayRunsDir}` },
      {
        label: "运行清单",
        status: runEntries.length > 0 ? "pass" : "warning",
        detail: runEntries.length > 0 ? `发现 ${runEntries.length} 个本地运行批次。` : "暂无运行批次，可先从上传页创建投递草稿。",
      },
      {
        label: "配置快照",
        status: configIssueCount === 0 ? "pass" : "warning",
        detail:
          configIssueCount === 0
            ? `可解析 ${parseableConfigs.length} 个运行配置。`
            : `${configIssueCount} 个投递缺少或无法解析运行配置，可在运行队列按最近更新时间定位。`,
      },
      {
        label: "关键产物",
        status: artifactIssueCount === 0 ? "pass" : "warning",
        detail:
          artifactIssueCount === 0
            ? "已存在的关键 JSON 产物均可解析。"
            : `${artifactIssueCount} 个已存在产物无法解析，可回到运行队列重新处理相关投递。`,
      },
      {
        label: "模型提供商配置",
        status: unknownProviderCount === 0 ? "pass" : "warning",
        detail:
          unknownProviderCount === 0
            ? "可解析配置未发现未知模型提供商。"
            : `${unknownProviderCount} 项模型提供商未能识别，可检查最近投递的本地配置。`,
      },
      { label: "shotguncv CLI", status: cliVisible() ? "pass" : "warning", detail: buildCliDetail() },
    ],
  };
}

async function readRunConfig(runsDir: string, runId: string): Promise<RunConfigReadResult> {
  const configPath = path.join(runsDir, runId, "config", "run_config.json");
  let modifiedTime = 0;
  try {
    modifiedTime = (await stat(path.join(runsDir, runId))).mtimeMs;
  } catch {
    modifiedTime = 0;
  }
  if (!(await pathReadable(configPath))) {
    return { runId, modifiedTime, config: null, issue: "missing_config" };
  }
  try {
    return {
      runId,
      modifiedTime,
      config: JSON.parse(await readFile(configPath, "utf-8")) as RunConfig,
      issue: null,
    };
  } catch {
    return { runId, modifiedTime, config: null, issue: "malformed_config" };
  }
}

async function countMalformedArtifacts(runDir: string): Promise<number> {
  const results = await Promise.all(
    JSON_ARTIFACTS.map(async (artifact) => {
      const artifactPath = path.join(runDir, artifact);
      if (!(await pathReadable(artifactPath))) {
        return 0;
      }
      try {
        JSON.parse(await readFile(artifactPath, "utf-8"));
        return 0;
      } catch {
        return 1;
      }
    }),
  );
  return results.reduce<number>((total, count) => total + count, 0);
}

function buildLatestConfig(results: RunConfigReadResult[]): LatestConfigSummary {
  const latest = [...results].sort((left, right) => right.modifiedTime - left.modifiedTime)[0];
  if (!latest?.config) {
    return null;
  }
  const config = latest.config;
  return {
    runId: latest.runId,
    label: config.run_metadata?.label ?? "",
    providers: [
      buildProvider("analyzer", config.analyzer),
      buildProvider("generator", config.generator),
      buildProvider("judge", config.judge),
      buildProvider("planner", config.planner),
    ],
    baseUrlHost: baseUrlHost(config.openai?.base_url),
    apiKeyEnv: config.openai?.api_key_env ?? "OPENAI_API_KEY",
    envFile: config.openai?.env_file ?? "",
    inputExtraction: {
      ocrProvider: config.input_extraction?.ocr_provider ?? "unknown",
      visionProvider: config.input_extraction?.vision_provider ?? "unknown",
      visionModel: config.input_extraction?.vision_model ?? "",
      ocrLanguages: config.input_extraction?.ocr_languages ?? "",
    },
  };
}

function buildProvider(role: ProviderRoleSummary["role"], config: RunConfig["analyzer"]): ProviderRoleSummary {
  return {
    role,
    provider: config?.provider ?? "unknown",
    model: config?.model || "未指定",
  };
}

function countUnknownProviders(config: RunConfig | null): number {
  if (!config) {
    return 0;
  }
  return [config.analyzer, config.generator, config.judge, config.planner].filter(
    (provider) => !provider?.provider || String(provider.provider) === "unknown",
  ).length;
}

async function pathReadable(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

export function maskPath(filePath: string): string {
  const parsed = path.parse(path.resolve(filePath));
  const base = path.basename(filePath) || parsed.root;
  const parent = path.basename(path.dirname(filePath));
  return parent && parent !== base ? path.join("...", parent, base) : path.join("...", base);
}

function baseUrlHost(value: string | null | undefined): string {
  if (!value) {
    return "默认 OpenAI 服务地址";
  }
  try {
    return new URL(value).host;
  } catch {
    return "自定义服务地址";
  }
}

function cliVisible(): boolean {
  const pathEntries = (process.env.PATH ?? "").split(path.delimiter).filter(Boolean);
  const extensions = process.platform === "win32" ? (process.env.PATHEXT ?? ".EXE;.CMD;.BAT").split(";") : [""];
  return pathEntries.some((entry) =>
    extensions.some((extension) => {
      const candidate = path.join(entry, `shotguncv${extension.toLowerCase()}`);
      const upperCandidate = path.join(entry, `shotguncv${extension.toUpperCase()}`);
      return existsSync(candidate) || existsSync(upperCandidate);
    }),
  );
}

function buildCliDetail(): string {
  return cliVisible()
    ? "PATH 中可见 shotguncv 命令。"
    : "PATH 中未发现 shotguncv 命令；网页仍只展示本地产物。";
}

export type { InputExtractionSummary, ProviderRoleSummary, SettingsCheck, SettingsOverview };
