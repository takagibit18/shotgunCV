"use client";

import React, { useMemo, useState } from "react";

import type { CvIssue } from "../lib/upload-drafts";


type Props = {
  runId: string;
  cvIssues: CvIssue[];
  onSaved?: (savedOriginalNames: string[]) => void;
};


export function CvTextSidecarPanel({ runId, cvIssues, onSaved }: Props) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState("");
  const savableEntries = useMemo(
    () => cvIssues.filter((issue) => (values[issue.originalName] ?? "").trim()),
    [cvIssues, values],
  );

  async function saveCvText() {
    setIsSaving(true);
    setMessage("");
    const formData = new FormData();
    savableEntries.forEach((issue) => {
      formData.append("cvTextOriginalName", issue.originalName);
      formData.append("cvText", values[issue.originalName].trim());
    });
    const response = await fetch(`/api/runs/${runId}/draft`, {
      method: "PATCH",
      body: formData,
    });
    setIsSaving(false);
    if (!response.ok) {
      const payload = (await response.json()) as { error?: string; code?: string };
      setMessage(payload.error ?? payload.code ?? "保存简历文本失败。");
      return;
    }
    setMessage("简历文本已保存，将作为补充材料参与分析。");
    onSaved?.(savableEntries.map((issue) => issue.originalName));
  }

  if (cvIssues.length === 0) {
    return null;
  }

  return (
    <section className="cv-sidecar-panel">
      <div>
        <p className="eyebrow">扫描件简历</p>
        <h3>补充简历文本</h3>
        <p>
          检测到扫描件简历，文本可能无法自动提取。请在下方粘贴简历的纯文本内容，确保分析结果准确。
          你也可以先跳过，系统会继续尝试本地依赖或视觉兜底。
        </p>
      </div>
      <div className="cv-sidecar-fields">
        {cvIssues.map((issue) => (
          <label className="field-label" key={issue.originalName}>
            <span>{issue.originalName}</span>
            <textarea
              rows={10}
              value={values[issue.originalName] ?? ""}
              placeholder="粘贴该 PDF 对应的简历纯文本"
              onChange={(event) =>
                setValues((current) => ({ ...current, [issue.originalName]: event.currentTarget.value }))
              }
            />
          </label>
        ))}
      </div>
      <div className="row-actions">
        <button className="primary-link" type="button" disabled={isSaving || savableEntries.length === 0} onClick={saveCvText}>
          {isSaving ? "正在保存" : "保存简历文本"}
        </button>
        {message ? <p className="muted">{message}</p> : null}
      </div>
    </section>
  );
}
