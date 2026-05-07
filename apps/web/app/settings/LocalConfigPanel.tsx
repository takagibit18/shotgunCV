"use client";

import React, { type FormEvent, useMemo, useState } from "react";

import type { LocalConfigState, LocalConfigValues } from "../../lib/local-config";

type LocalConfigPanelProps = {
  initialConfig: LocalConfigState;
};

type SaveStatus = {
  kind: "idle" | "saving" | "success" | "error";
  message: string;
};

const MODEL_FIELDS: Array<{
  key: keyof Pick<LocalConfigValues, "openaiModel" | "generatorModel" | "judgeModel" | "visionModel">;
  label: string;
  placeholder: string;
}> = [
  { key: "openaiModel", label: "共享模型", placeholder: "留空时使用 CLI 默认模型" },
  { key: "generatorModel", label: "Generator 模型", placeholder: "可留空继承共享模型" },
  { key: "judgeModel", label: "Judge 模型", placeholder: "可留空继承共享模型" },
  { key: "visionModel", label: "Vision 模型", placeholder: "图片兜底模型，可留空" },
];

export function LocalConfigPanel({ initialConfig }: LocalConfigPanelProps) {
  const [config, setConfig] = useState(initialConfig);
  const [values, setValues] = useState<LocalConfigValues>(initialConfig.values);
  const [clearApiKey, setClearApiKey] = useState(false);
  const [status, setStatus] = useState<SaveStatus>({ kind: "idle", message: "" });

  const apiKeyLabel = useMemo(() => {
    if (!config.apiKey.configured) {
      return "未配置";
    }
    return `已配置 · ****${config.apiKey.suffix}`;
  }, [config.apiKey]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus({ kind: "saving", message: "正在保存本地配置..." });
    const payload: Partial<LocalConfigValues> = {
      openaiBaseUrl: values.openaiBaseUrl,
      openaiModel: values.openaiModel,
      generatorModel: values.generatorModel,
      judgeModel: values.judgeModel,
      visionModel: values.visionModel,
      openaiApiKeyEnv: values.openaiApiKeyEnv,
    };
    if (clearApiKey) {
      payload.openaiApiKey = "";
    } else if (values.openaiApiKey.trim()) {
      payload.openaiApiKey = values.openaiApiKey.trim();
    }
    await submitConfig("/api/settings/local-config", "PUT", payload);
  }

  async function handleRestore() {
    setStatus({ kind: "saving", message: "正在恢复默认 .env 结构..." });
    await submitConfig("/api/settings/local-config", "POST");
  }

  async function submitConfig(url: string, method: "PUT" | "POST", payload?: Partial<LocalConfigValues>) {
    try {
      const response = await fetch(url, {
        method,
        headers: payload ? { "Content-Type": "application/json" } : undefined,
        body: payload ? JSON.stringify(payload) : undefined,
      });
      const body = await response.json();
      if (!response.ok) {
        setStatus({ kind: "error", message: buildErrorMessage(body?.code, body?.error) });
        return;
      }
      setConfig(body as LocalConfigState);
      setValues((body as LocalConfigState).values);
      setClearApiKey(false);
      setStatus({ kind: "success", message: "本地配置已保存。" });
    } catch {
      setStatus({ kind: "error", message: "无法保存本地配置，请检查 Web 进程是否仍在运行。" });
    }
  }

  function updateValue(key: keyof LocalConfigValues, value: string) {
    setValues((current) => ({ ...current, [key]: value }));
    if (key === "openaiApiKey" && value.trim()) {
      setClearApiKey(false);
    }
  }

  return (
    <section className="section section-flush settings-local-config">
      <div className="section-heading queue-heading">
        <div>
          <p className="eyebrow">本地模型配置</p>
          <h2>API key 与模型运行参数</h2>
          <p className="section-copy">
            仅写入项目根目录 .env；Web 不保存到浏览器存储、不写入 run_config.json，也不发起远端模型检查。
          </p>
        </div>
        <span className={config.apiKey.configured ? "status-chip success" : "status-chip warning"}>{apiKeyLabel}</span>
      </div>

      <form className="local-config-form" onSubmit={handleSubmit}>
        <div className="local-config-status-grid" aria-label="本地配置状态">
          <StatusCell label=".env 文件" value={config.envExists ? "已存在" : "未创建"} tone={config.envExists ? "success" : "warning"} />
          <StatusCell label="可写状态" value={config.envWritable ? "可写" : "需检查"} tone={config.envWritable ? "success" : "warning"} />
          <StatusCell label="base URL host" value={config.baseUrlHost} tone="info" />
        </div>

        <label className="control-field">
          API key
          <input
            type="password"
            value={values.openaiApiKey}
            placeholder={config.apiKey.configured ? "留空保持当前密钥" : "输入本地 API key"}
            autoComplete="off"
            onChange={(event) => updateValue("openaiApiKey", event.target.value)}
            disabled={clearApiKey}
          />
        </label>
        <label className="local-config-checkbox">
          <input
            type="checkbox"
            checked={clearApiKey}
            onChange={(event) => {
              setClearApiKey(event.target.checked);
              if (event.target.checked) {
                updateValue("openaiApiKey", "");
              }
            }}
          />
          清空当前 API key
        </label>

        <div className="local-config-grid">
          <label className="control-field">
            OPENAI_BASE_URL
            <input
              value={values.openaiBaseUrl}
              placeholder="留空使用 https://api.openai.com/v1"
              onChange={(event) => updateValue("openaiBaseUrl", event.target.value)}
            />
          </label>
          <label className="control-field">
            OPENAI_API_KEY_ENV
            <input
              value={values.openaiApiKeyEnv}
              placeholder="留空使用 OPENAI_API_KEY"
              onChange={(event) => updateValue("openaiApiKeyEnv", event.target.value.toUpperCase())}
            />
          </label>
        </div>

        <div className="local-config-grid">
          {MODEL_FIELDS.map((field) => (
            <label key={field.key} className="control-field">
              {field.label}
              <input
                value={values[field.key]}
                placeholder={field.placeholder}
                onChange={(event) => updateValue(field.key, event.target.value)}
              />
            </label>
          ))}
        </div>

        {status.message ? <p className={`local-config-message ${status.kind}`}>{status.message}</p> : null}

        <div className="local-config-actions">
          <button className="primary-link" type="submit" disabled={status.kind === "saving" || !config.envExists}>
            保存本地配置
          </button>
          <button className="secondary-button" type="button" onClick={handleRestore} disabled={status.kind === "saving" || !config.restoreAvailable}>
            恢复默认结构
          </button>
        </div>
      </form>
    </section>
  );
}

function StatusCell({ label, value, tone }: { label: string; value: string; tone: "info" | "success" | "warning" }) {
  return (
    <div className={`status-strip-item ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function buildErrorMessage(code: string | undefined, fallback: string | undefined): string {
  const messages: Record<string, string> = {
    env_not_found: ".env 文件不存在，请先恢复默认结构。",
    env_unreadable: ".env 文件不可读，请检查本地权限。",
    env_unwritable: ".env 文件不可写，请检查本地权限。",
    invalid_base_url: "OPENAI_BASE_URL 必须是合法的 HTTP(S) URL。",
    invalid_key_env: "OPENAI_API_KEY_ENV 必须是合法环境变量名。",
    write_failed: "写入 .env 失败，请检查本地权限。",
  };
  return (code && messages[code]) || fallback || "本地配置保存失败。";
}
