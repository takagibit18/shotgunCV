"use client";

import React, { type FormEvent, useMemo, useState } from "react";

import { Icon, type IconName } from "../AppShell";
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
  icon: IconName;
}> = [
  { key: "openaiModel", label: "共享模型", placeholder: "留空时使用默认模型", icon: "model" },
  { key: "generatorModel", label: "生成模型", placeholder: "可留空继承共享模型", icon: "model" },
  { key: "judgeModel", label: "评审模型", placeholder: "可留空继承共享模型", icon: "shield-check" },
  { key: "visionModel", label: "视觉兜底模型", placeholder: "图片兜底模型，可留空", icon: "image-upload" },
];

export function LocalConfigPanel({ initialConfig }: LocalConfigPanelProps) {
  const [config, setConfig] = useState(initialConfig);
  const [values, setValues] = useState<LocalConfigValues>(initialConfig.values);
  const [advancedValues, setAdvancedValues] = useState<
    Pick<LocalConfigValues, "openaiBaseUrl" | "openaiModel" | "generatorModel" | "judgeModel" | "visionModel" | "openaiApiKeyEnv">
  >({
    openaiBaseUrl: "",
    openaiModel: "",
    generatorModel: "",
    judgeModel: "",
    visionModel: "",
    openaiApiKeyEnv: "",
  });
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
    const payload: Partial<LocalConfigValues> = Object.fromEntries(
      Object.entries(advancedValues).filter(([, value]) => value.trim().length > 0),
    ) as Partial<LocalConfigValues>;
    if (clearApiKey) {
      payload.openaiApiKey = "";
    } else if (values.openaiApiKey.trim()) {
      payload.openaiApiKey = values.openaiApiKey.trim();
    }
    await submitConfig("/api/settings/local-config", "PUT", payload);
  }

  async function handleRestore() {
    setStatus({ kind: "saving", message: "正在恢复默认本地配置结构..." });
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
      setAdvancedValues({
        openaiBaseUrl: "",
        openaiModel: "",
        generatorModel: "",
        judgeModel: "",
        visionModel: "",
        openaiApiKeyEnv: "",
      });
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

  function updateAdvancedValue(key: keyof typeof advancedValues, value: string) {
    setAdvancedValues((current) => ({ ...current, [key]: value }));
  }

  return (
    <section className="section section-flush settings-local-config">
      <div className="section-heading queue-heading">
        <div>
          <p className="eyebrow">本地模型配置</p>
          <h2>密钥与模型运行参数</h2>
          <p className="section-copy">
            仅写入项目根目录的本地配置文件；网页不保存到浏览器存储、不写入运行产物，也不发起远端模型检查。
          </p>
        </div>
        <span className={config.apiKey.configured ? "status-chip success icon-chip" : "status-chip warning icon-chip"}>
          <Icon name={config.apiKey.configured ? "eye-off" : "key"} />
          {apiKeyLabel}
        </span>
      </div>

      <form className="local-config-form" onSubmit={handleSubmit}>
        <div className="local-config-status-grid" aria-label="本地配置状态">
          <StatusCell icon="file" label="配置文件" value={config.envExists ? "已存在" : "未创建"} tone={config.envExists ? "success" : "warning"} />
          <StatusCell icon="edit" label="可写状态" value={config.envWritable ? "可写" : "需检查"} tone={config.envWritable ? "success" : "warning"} />
          <StatusCell icon="link" label="服务地址" value={config.baseUrlHost ? "已配置" : "未配置"} tone="info" />
          <StatusCell
            icon="key"
            label="密钥状态"
            value={apiKeyLabel}
            tone={config.apiKey.configured ? "success" : "warning"}
          />
        </div>

        <label className="control-field local-config-field-with-icon">
          <FieldLabel icon="key" text="模型服务密钥" trailingIcon="eye-off" />
          <input
            type="password"
            value={values.openaiApiKey}
            placeholder={config.apiKey.configured ? "留空保持当前密钥" : "输入本地模型服务密钥"}
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
          清空当前密钥
        </label>

        <div className="local-config-grid">
          <label className="control-field local-config-field-with-icon">
            <FieldLabel icon="link" text="模型服务地址" />
            <input
              value={advancedValues.openaiBaseUrl}
              placeholder={config.values.openaiBaseUrl ? "已配置，留空保持当前地址" : "留空使用默认服务地址"}
              onChange={(event) => updateAdvancedValue("openaiBaseUrl", event.target.value)}
            />
          </label>
          <label className="control-field local-config-field-with-icon">
            <FieldLabel icon="key" text="密钥来源名称" />
            <input
              value={advancedValues.openaiApiKeyEnv}
              placeholder="留空使用默认密钥来源"
              onChange={(event) => updateAdvancedValue("openaiApiKeyEnv", event.target.value.toUpperCase())}
            />
          </label>
        </div>

        <div className="local-config-grid">
          {MODEL_FIELDS.map((field) => (
            <label key={field.key} className="control-field local-config-field-with-icon">
              <FieldLabel icon={field.icon} text={field.label} />
              <input
                value={advancedValues[field.key]}
                placeholder={values[field.key] ? "已配置，留空保持当前模型" : field.placeholder}
                onChange={(event) => updateAdvancedValue(field.key, event.target.value)}
              />
            </label>
          ))}
        </div>

        {status.message ? <p className={`local-config-message ${status.kind}`}>{status.message}</p> : null}

        <div className="local-config-actions">
          <button className="primary-link icon-link" type="submit" disabled={status.kind === "saving" || !config.envExists}>
            <Icon name="save" />
            保存本地配置
          </button>
          <button className="secondary-button icon-link" type="button" onClick={handleRestore} disabled={status.kind === "saving" || !config.restoreAvailable}>
            <Icon name="reset" />
            恢复默认结构
          </button>
        </div>
      </form>
    </section>
  );
}

function FieldLabel({ icon, text, trailingIcon }: { icon: IconName; text: string; trailingIcon?: IconName }) {
  return (
    <span className="field-label-row">
      <span>
        <Icon name={icon} />
        {text}
      </span>
      {trailingIcon ? (
        <span className="field-label-trailing" title="完整密钥保持隐藏">
          <Icon name={trailingIcon} />
        </span>
      ) : null}
    </span>
  );
}

function StatusCell({
  icon,
  label,
  value,
  tone,
}: {
  icon: IconName;
  label: string;
  value: string;
  tone: "info" | "success" | "warning";
}) {
  return (
    <div className={`status-strip-item ${tone}`}>
      <span>
        <Icon name={icon} />
        {label}
      </span>
      <strong>{value}</strong>
    </div>
  );
}

function buildErrorMessage(code: string | undefined, fallback: string | undefined): string {
  const messages: Record<string, string> = {
    env_not_found: "本地配置文件不存在，请先恢复默认结构。",
    env_unreadable: "本地配置文件不可读，请检查本地权限。",
    env_unwritable: "本地配置文件不可写，请检查本地权限。",
    invalid_base_url: "模型服务地址必须是合法的网址。",
    invalid_key_env: "密钥来源名称格式不正确。",
    write_failed: "写入本地配置失败，请检查本地权限。",
  };
  return (code && messages[code]) || fallback || "本地配置保存失败。";
}
