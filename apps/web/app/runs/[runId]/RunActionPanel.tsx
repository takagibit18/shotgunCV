"use client";

import React, { useEffect, useState } from "react";

import { CvTextSidecarPanel } from "../../CvTextSidecarPanel";
import type { DependencyReport } from "../../../lib/python-env";
import type { RunDraftStatus, UploadManifest } from "../../../lib/types";
import type { CvIssue } from "../../../lib/upload-drafts";

type ActionPhase = "idle" | "submitting" | "accepted" | "refreshing" | "error";

type Props = {
  runId: string;
  draftStatus: RunDraftStatus;
  draft: UploadManifest | null;
};

type WebUploadManifest = UploadManifest & {
  cvIssues?: CvIssue[];
  needsManualText?: boolean;
};


export function RunActionPanel({ runId, draftStatus, draft }: Props) {
  const [message, setMessage] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const [actionPhase, setActionPhase] = useState<ActionPhase>("idle");
  const [activeActionLabel, setActiveActionLabel] = useState("");
  const canEditDraft = draftStatus === "draft" && draft !== null;
  const canDelete = draftStatus === "draft" || draftStatus === "failed";
  const canRun = draftStatus === "draft";
  const canRetry = draftStatus === "failed";
  const webDraft = draft as WebUploadManifest | null;
  const cvIssues = webDraft?.cvIssues ?? [];
  const [dependencyReport, setDependencyReport] = useState<DependencyReport | null>(null);

  useEffect(() => {
    if (draftStatus !== "draft") {
      return;
    }
    let cancelled = false;
    fetch("/api/settings/dependencies")
      .then((response) => (response.ok ? response.json() : null))
      .then((payload: DependencyReport | null) => {
        if (!cancelled) {
          setDependencyReport(payload);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [draftStatus]);

  async function runAction(action: "run" | "retry_full" | "resume_failed", label: string) {
    setIsBusy(true);
    setMessage(String());
    setActionPhase("submitting");
    setActiveActionLabel(label);
    try {
      const response = await fetch(`/api/runs/${runId}/actions`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action }),
      });
      await handleRunActionResponse(response);
    } catch {
      setIsBusy(false);
      setActionPhase("error");
      setMessage("提交失败，请检查本地运行环境后重试。");
    }
  }

  async function deleteCurrentRun() {
    setIsBusy(true);
    setMessage(String());
    const response = await fetch(`/api/runs/${runId}`, { method: "DELETE" });
    if (response.ok) {
      if (typeof window !== "undefined") {
        window.location.href = "/runs";
      }
      return;
    }
    await handleResponse(response, "运行已删除。");
  }

  async function patchDraft(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsBusy(true);
    setMessage(String());
    const form = event.currentTarget;
    const formData = new FormData(form);
    formData.delete("cvFiles");
    formData.delete("jdFiles");
    appendSelectedFiles(formData, "cvFiles", form.elements.namedItem("cvFiles"));
    appendSelectedFiles(formData, "jdFiles", form.elements.namedItem("jdFiles"));
    const response = await fetch(`/api/runs/${runId}/draft`, {
      method: "PATCH",
      body: formData,
    });
    await handleResponse(response, "草稿已更新。");
  }

  async function handleRunActionResponse(response: Response) {
    if (!response.ok) {
      const payload = (await response.json()) as { error?: string; code?: string };
      setIsBusy(false);
      setActionPhase("error");
      setMessage(payload.error ?? payload.code ?? "请求失败，请检查本地运行环境后重试。");
      return;
    }
    setActionPhase("accepted");
    setMessage("已提交本地运行，正在等待状态回写。");
    if (typeof window !== "undefined") {
      window.setTimeout(() => setActionPhase("refreshing"), 900);
      window.setTimeout(() => window.location.reload(), 2200);
    }
  }

  async function handleResponse(response: Response, success: string, options: { delayedReload?: boolean } = {}) {
    setIsBusy(false);
    if (!response.ok) {
      const payload = (await response.json()) as { error?: string; code?: string };
      setMessage(payload.error ?? payload.code ?? "请求失败，请检查本地运行环境后重试。");
      return;
    }
    setMessage(success);
    if (typeof window !== "undefined") {
      window.setTimeout(() => window.location.reload(), options.delayedReload ? 1800 : 0);
    }
  }

  return (
    <div className="run-action-stack">
      <div className="pill-row compact">
        {canRun ? (
          <button className="primary-link" type="button" disabled={isBusy} onClick={() => runAction("run", "开始评估")}>
            {"开始评估"}
          </button>
        ) : null}
        {canRetry ? (
          <>
            <button className="primary-link" type="button" disabled={isBusy} onClick={() => runAction("retry_full", "重新评估")}>
              {"重新评估"}
            </button>
            <button className="secondary-link" type="button" disabled={isBusy} onClick={() => runAction("resume_failed", "从失败处继续")}>
              {"从失败处继续"}
            </button>
          </>
        ) : null}
        {canDelete ? (
          <button className="secondary-link danger" type="button" disabled={isBusy} onClick={deleteCurrentRun}>
            {"删除"}
          </button>
        ) : null}
      </div>
      {actionPhase !== "idle" ? <RunActionProgress phase={actionPhase} actionLabel={activeActionLabel} /> : null}
      {draftStatus === "draft" && dependencyReport && dependencyReport.overall !== "healthy" ? (
        <div className="notice-strip warning">
          <strong>环境不完整</strong>
          <span>PDF 解析依赖未安装或本地执行依赖不可用，扫描件 PDF 可能解析失败。</span>
          <a className="secondary-link" href="/settings">
            查看设置
          </a>
        </div>
      ) : null}
      {message ? <p className="muted">{message}</p> : null}
      {draftStatus === "draft" && cvIssues.length > 0 ? <CvTextSidecarPanel runId={runId} cvIssues={cvIssues} /> : null}

      {canEditDraft ? (
        <form className="draft-edit-form" onSubmit={patchDraft}>
          <div className="detail-grid">
            <label className="field-label">
              <span>{"投递名称"}</span>
              <input name="label" defaultValue={draft.label} />
            </label>
          </div>
          <label className="field-label">
            <span>{"可选：替换简历文件"}</span>
            <input name="cvFiles" type="file" multiple accept=".txt,.md,.pdf,.png,.jpg,.jpeg" />
            <small>{"不选择文件会保留当前简历；只有选择新文件才会替换全部简历输入。"}</small>
          </label>
          <div className="jd-text-stack">
            {draft.files
              .filter((file) => file.role === "jd")
              .map((file, index) => (
                <label className="field-label" key={file.storedRelativePath}>
                  <span>{`岗位显示名 ${index + 1}`}</span>
                  <input name="jdFileDisplayNames" defaultValue={file.displayName ?? ""} />
                </label>
              ))}
          </div>
          <label className="field-label">
            <span>{"追加岗位文件"}</span>
            <input name="jdFiles" type="file" multiple accept=".txt,.md,.pdf,.png,.jpg,.jpeg" />
            <small>{"不选择文件不会改变现有岗位；这里只用于追加新的 JD 文件。"}</small>
          </label>
          <label className="field-label">
            <span>{"新岗位显示名"}</span>
            <input name="jdFileDisplayNames" placeholder="例如：公司名称 - 岗位名称" />
          </label>
          <label className="field-label">
            <span>{"追加粘贴岗位"}</span>
            <input name="jdTextDisplayNames" placeholder="例如：公司名称 - 岗位名称" />
            <textarea name="jdTexts" rows={5} placeholder="粘贴岗位描述文本" />
            <small>{"留空会跳过，不会覆盖已上传的岗位内容。"}</small>
          </label>
          <button className="primary-link" type="submit" disabled={isBusy}>
            {"更新草稿"}
          </button>
        </form>
      ) : null}
    </div>
  );
}

function appendSelectedFiles(formData: FormData, fieldName: string, field: Element | RadioNodeList | null) {
  if (!(field instanceof HTMLInputElement) || field.type !== "file" || !field.files) {
    return;
  }
  Array.from(field.files).forEach((file) => {
    if (file.size > 0 || file.name.trim()) {
      formData.append(fieldName, file);
    }
  });
}

function RunActionProgress({ phase, actionLabel }: { phase: ActionPhase; actionLabel: string }) {
  const currentStep = phase === "submitting" ? 1 : phase === "accepted" ? 2 : phase === "refreshing" ? 3 : 0;
  const title = phase === "error" ? "提交未完成" : `${actionLabel || "评估任务"}处理中`;
  const helper =
    phase === "submitting"
      ? "正在把任务提交给本地执行器。"
      : phase === "accepted"
        ? "任务已接收，等待运行状态写入。"
        : phase === "refreshing"
          ? "正在刷新页面读取最新进度。"
          : "请根据提示修正后重试。";

  return (
    <div className={`run-action-progress ${phase}`} role="status" aria-live="polite">
      <div className="progress-meta">
        <strong>{title}</strong>
        <span>{helper}</span>
      </div>
      <div className="action-progress-track" aria-hidden="true">
        <span style={{ width: `${Math.max(currentStep, 1) * 33.333}%` }} />
      </div>
      <div className="action-progress-steps" aria-label="运行提交进度">
        {["提交指令", "等待回写", "刷新状态"].map((step, index) => (
          <span key={step} className={currentStep >= index + 1 ? "active" : ""}>
            {step}
          </span>
        ))}
      </div>
    </div>
  );
}
