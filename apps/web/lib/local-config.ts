import { constants } from "node:fs";
import { access, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

type LocalConfigErrorCode =
  | "env_not_found"
  | "env_unreadable"
  | "env_unwritable"
  | "invalid_base_url"
  | "invalid_key_env"
  | "write_failed";

type LocalConfigPaths = {
  projectRoot?: string;
};

type ApiKeySummary = {
  configured: boolean;
  suffix: string;
};

type LocalConfigValues = {
  openaiApiKey: string;
  openaiBaseUrl: string;
  openaiModel: string;
  generatorModel: string;
  judgeModel: string;
  visionModel: string;
  openaiApiKeyEnv: string;
};

type LocalConfigState = {
  envExists: boolean;
  envReadable: boolean;
  envWritable: boolean;
  restoreAvailable: boolean;
  apiKey: ApiKeySummary;
  baseUrlHost: string;
  values: LocalConfigValues;
};

type LocalConfigPatch = Partial<LocalConfigValues>;

type ParsedLine = {
  raw: string;
  key: string | null;
  value: string;
};

const FIELD_TO_ENV_KEY: Record<keyof LocalConfigValues, string> = {
  openaiApiKey: "OPENAI_API_KEY",
  openaiBaseUrl: "OPENAI_BASE_URL",
  openaiModel: "OPENAI_MODEL",
  generatorModel: "SHOTGUNCV_GENERATOR_MODEL",
  judgeModel: "SHOTGUNCV_JUDGE_MODEL",
  visionModel: "SHOTGUNCV_VISION_MODEL",
  openaiApiKeyEnv: "OPENAI_API_KEY_ENV",
};

const ORDERED_FIELDS = Object.keys(FIELD_TO_ENV_KEY) as Array<keyof LocalConfigValues>;

class LocalConfigError extends Error {
  code: LocalConfigErrorCode;
  status: number;

  constructor(code: LocalConfigErrorCode, message: string, status = 400) {
    super(message);
    this.name = "LocalConfigError";
    this.code = code;
    this.status = status;
  }
}

async function loadLocalConfig(paths: LocalConfigPaths = {}): Promise<LocalConfigState> {
  const resolved = resolveConfigPaths(paths);
  const envExists = await pathExists(resolved.envPath);
  const restoreAvailable = await pathReadable(resolved.envExamplePath);
  if (!envExists) {
    return buildState(resolved, "", {
      envExists: false,
      envReadable: false,
      envWritable: false,
      restoreAvailable,
    });
  }

  let envText = "";
  try {
    envText = await readFile(resolved.envPath, "utf-8");
  } catch {
    return buildState(resolved, "", {
      envExists: true,
      envReadable: false,
      envWritable: await pathWritable(resolved.envPath),
      restoreAvailable,
    });
  }

  return buildState(resolved, envText, {
    envExists: true,
    envReadable: true,
    envWritable: await pathWritable(resolved.envPath),
    restoreAvailable,
  });
}

async function saveLocalConfig(patch: LocalConfigPatch, paths: LocalConfigPaths = {}): Promise<LocalConfigState> {
  validatePatch(patch);
  const resolved = resolveConfigPaths(paths);
  if (!(await pathExists(resolved.envPath))) {
    throw new LocalConfigError("env_not_found", "Project .env file does not exist.", 404);
  }
  if (!(await pathReadable(resolved.envPath))) {
    throw new LocalConfigError("env_unreadable", "Project .env file cannot be read.", 500);
  }
  if (!(await pathWritable(resolved.envPath))) {
    throw new LocalConfigError("env_unwritable", "Project .env file cannot be written.", 500);
  }

  const current = await readFile(resolved.envPath, "utf-8");
  const next = updateEnvText(current, patch);
  try {
    await writeFile(resolved.envPath, next, "utf-8");
  } catch {
    throw new LocalConfigError("write_failed", "Failed to write project .env file.", 500);
  }
  return loadLocalConfig(paths);
}

async function resetLocalConfig(paths: LocalConfigPaths = {}): Promise<LocalConfigState> {
  const resolved = resolveConfigPaths(paths);
  if (!(await pathReadable(resolved.envExamplePath))) {
    throw new LocalConfigError("env_not_found", "Project .env.example file does not exist.", 404);
  }
  const template = await readFile(resolved.envExamplePath, "utf-8");
  try {
    await writeFile(resolved.envPath, template, "utf-8");
  } catch {
    throw new LocalConfigError("write_failed", "Failed to restore project .env file.", 500);
  }
  return loadLocalConfig(paths);
}

function updateEnvText(envText: string, patch: LocalConfigPatch): string {
  const parsed = parseEnvLines(envText);
  const updatedKeys = new Set<string>();
  const patchByEnvKey = new Map<string, string>();
  for (const field of ORDERED_FIELDS) {
    if (Object.prototype.hasOwnProperty.call(patch, field)) {
      patchByEnvKey.set(FIELD_TO_ENV_KEY[field], patch[field] ?? "");
    }
  }

  const lines = parsed.map((line) => {
    if (!line.key || !patchByEnvKey.has(line.key)) {
      return line.raw;
    }
    updatedKeys.add(line.key);
    return `${line.key}=${formatEnvValue(patchByEnvKey.get(line.key) ?? "")}`;
  });

  for (const field of ORDERED_FIELDS) {
    const envKey = FIELD_TO_ENV_KEY[field];
    if (patchByEnvKey.has(envKey) && !updatedKeys.has(envKey)) {
      lines.push(`${envKey}=${formatEnvValue(patchByEnvKey.get(envKey) ?? "")}`);
    }
  }

  return `${lines.join("\n").replace(/\n*$/, "")}\n`;
}

function buildState(
  resolved: { envPath: string; envExamplePath: string },
  envText: string,
  flags: Pick<LocalConfigState, "envExists" | "envReadable" | "envWritable" | "restoreAvailable">,
): LocalConfigState {
  const values = readValues(envText);
  const apiKey = values.openaiApiKey.trim();
  return {
    ...flags,
    apiKey: {
      configured: apiKey.length > 0,
      suffix: apiKey ? apiKey.slice(-4) : "",
    },
    baseUrlHost: baseUrlHost(values.openaiBaseUrl),
    values: {
      ...values,
      openaiApiKey: "",
    },
  };
}

function readValues(envText: string): LocalConfigValues {
  const byKey = new Map<string, string>();
  for (const line of parseEnvLines(envText)) {
    if (line.key) {
      byKey.set(line.key, line.value);
    }
  }
  return {
    openaiApiKey: byKey.get("OPENAI_API_KEY") ?? "",
    openaiBaseUrl: byKey.get("OPENAI_BASE_URL") ?? "",
    openaiModel: byKey.get("OPENAI_MODEL") ?? "",
    generatorModel: byKey.get("SHOTGUNCV_GENERATOR_MODEL") ?? "",
    judgeModel: byKey.get("SHOTGUNCV_JUDGE_MODEL") ?? "",
    visionModel: byKey.get("SHOTGUNCV_VISION_MODEL") ?? "",
    openaiApiKeyEnv: byKey.get("OPENAI_API_KEY_ENV") ?? "",
  };
}

function parseEnvLines(envText: string): ParsedLine[] {
  return envText.split(/\r?\n/).map((raw) => {
    const trimmed = raw.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      return { raw, key: null, value: "" };
    }
    const candidate = trimmed.startsWith("export ") ? trimmed.slice(7).trim() : trimmed;
    const separator = candidate.indexOf("=");
    if (separator < 0) {
      return { raw, key: null, value: "" };
    }
    const key = candidate.slice(0, separator).trim();
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
      return { raw, key: null, value: "" };
    }
    return { raw, key, value: unquoteEnvValue(candidate.slice(separator + 1).trim()) };
  });
}

function validatePatch(patch: LocalConfigPatch): void {
  if (patch.openaiBaseUrl?.trim()) {
    try {
      const parsed = new URL(patch.openaiBaseUrl.trim());
      if (!["http:", "https:"].includes(parsed.protocol)) {
        throw new Error("unsupported protocol");
      }
    } catch {
      throw new LocalConfigError("invalid_base_url", "OPENAI_BASE_URL must be a valid HTTP(S) URL.");
    }
  }
  if (patch.openaiApiKeyEnv?.trim() && !/^[A-Z_][A-Z0-9_]*$/.test(patch.openaiApiKeyEnv.trim())) {
    throw new LocalConfigError("invalid_key_env", "OPENAI_API_KEY_ENV must be an environment variable name.");
  }
}

function resolveConfigPaths(paths: LocalConfigPaths): { envPath: string; envExamplePath: string } {
  const projectRoot = path.resolve(
    paths.projectRoot ?? process.env.SHOTGUNCV_WEB_PROJECT_ROOT ?? path.resolve(process.cwd(), "..", ".."),
  );
  return {
    envPath: path.join(projectRoot, ".env"),
    envExamplePath: path.join(projectRoot, ".env.example"),
  };
}

async function pathExists(filePath: string): Promise<boolean> {
  try {
    await access(filePath, constants.F_OK);
    return true;
  } catch {
    return false;
  }
}

async function pathReadable(filePath: string): Promise<boolean> {
  try {
    await access(filePath, constants.R_OK);
    return true;
  } catch {
    return false;
  }
}

async function pathWritable(filePath: string): Promise<boolean> {
  try {
    await access(filePath, constants.W_OK);
    return true;
  } catch {
    return false;
  }
}

function unquoteEnvValue(value: string): string {
  if (value.length >= 2 && value[0] === value[value.length - 1] && ["'", '"'].includes(value[0])) {
    return value.slice(1, -1);
  }
  return value;
}

function formatEnvValue(value: string): string {
  if (!value || /^[^\s#"'`]+$/.test(value)) {
    return value;
  }
  return JSON.stringify(value);
}

function baseUrlHost(value: string): string {
  if (!value.trim()) {
    return "默认 OpenAI endpoint";
  }
  try {
    return new URL(value).host;
  } catch {
    return "自定义 endpoint";
  }
}

export {
  LocalConfigError,
  loadLocalConfig,
  resetLocalConfig,
  saveLocalConfig,
};
export type { LocalConfigErrorCode, LocalConfigPatch, LocalConfigState, LocalConfigValues };
