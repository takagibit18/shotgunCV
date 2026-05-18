"use client";

import React, { useState } from "react";

import type { RunDraftStatus, UploadManifest } from "../../../lib/types";


type Props = {
  runId: string;
  draftStatus: RunDraftStatus;
  draft: UploadManifest | null;
};


export function RunActionPanel({ runId, draftStatus, draft }: Props) {
  const [message, setMessage] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const canEditDraft = draftStatus === "draft" && draft !== null;
  const canDelete = draftStatus === "draft" || draftStatus === "failed";
  const canRun = draftStatus === "draft";
  const canRetry = draftStatus === "failed";

  async function runAction(action: "run" | "retry_full" | "resume_failed") {
    setIsBusy(true);
    setMessage("");
    const response = await fetch(`/api/runs/${runId}/actions`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action }),
    });
    await handleResponse(response, "已提交本地运行，请稍候。页面会自动刷新显示最新状态。", { delayedReload: true });
  }

  async function deleteCurrentRun() {
    setIsBusy(true);
    setMessage("");
    const response = await fetch(`/api/runs/${runId}`, { method: "DELETE" });
    if (response.ok) {
      if (typeof window !== "undefined") {
        window.location.href = "/";
      }
      return;
    }
    await handleResponse(response, "运行已删除。");
  }

  async function patchDraft(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsBusy(true);
    setMessage("");
    const formData = new FormData(event.currentTarget);
    const response = await fetch(`/api/runs/${runId}/draft`, {
      method: "PATCH",
      body: formData,
    });
    await handleResponse(response, "草稿已更新。");
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
        <button className="primary-link" type="button" disabled={!canRun || isBusy} onClick={() => runAction("run")}>
          {"开始评估"}
        </button>
        <button className="secondary-link" type="button" disabled={!canRetry || isBusy} onClick={() => runAction("retry_full")}>
          {"重新评估"}
        </button>
        <button className="secondary-link" type="button" disabled={!canRetry || isBusy} onClick={() => runAction("resume_failed")}>
          {"从失败处继续"}
        </button>
        <button className="secondary-link danger" type="button" disabled={!canDelete || isBusy} onClick={deleteCurrentRun}>
          {"删除"}
        </button>
      </div>
      {message ? <p className="muted">{message}</p> : null}

      {canEditDraft ? (
        <form className="draft-edit-form" onSubmit={patchDraft}>
          <div className="detail-grid">
            <label className="field-label">
              <span>{"候选人备注"}</span>
              <input name="candidateId" defaultValue={draft.candidateId} />
            </label>
            <label className="field-label">
              <span>{"投递名称"}</span>
              <input name="label" defaultValue={draft.label} />
            </label>
          </div>
          <label className="field-label">
            <span>{"替换全部简历文件"}</span>
            <input name="cvFiles" type="file" multiple accept=".txt,.md,.pdf,.png,.jpg,.jpeg" />
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
          </label>
          <label className="field-label">
            <span>{"新岗位显示名"}</span>
            <input name="jdFileDisplayNames" placeholder="例如：公司名称 - 岗位名称" />
          </label>
          <label className="field-label">
            <span>{"追加粘贴岗位"}</span>
            <input name="jdTextDisplayNames" placeholder="例如：公司名称 - 岗位名称" />
            <textarea name="jdTexts" rows={5} placeholder="粘贴岗位描述文本" />
          </label>
          <button className="primary-link" type="submit" disabled={isBusy}>
            {"更新草稿"}
          </button>
        </form>
      ) : null}
    </div>
  );
}
