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
    await handleResponse(response, "Run action queued.");
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
    await handleResponse(response, "Run deleted.");
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
    await handleResponse(response, "Draft updated.");
  }

  async function handleResponse(response: Response, success: string) {
    setIsBusy(false);
    if (!response.ok) {
      const payload = (await response.json()) as { error?: string; code?: string };
      setMessage(payload.error ?? payload.code ?? "Request failed.");
      return;
    }
    setMessage(success);
    if (typeof window !== "undefined") {
      window.location.reload();
    }
  }

  return (
    <div className="run-action-stack">
      <div className="pill-row compact">
        <button className="primary-link" type="button" disabled={!canRun || isBusy} onClick={() => runAction("run")}>
          {"Run"}
        </button>
        <button className="secondary-link" type="button" disabled={!canRetry || isBusy} onClick={() => runAction("retry_full")}>
          {"Retry full"}
        </button>
        <button className="secondary-link" type="button" disabled={!canRetry || isBusy} onClick={() => runAction("resume_failed")}>
          {"Resume failed"}
        </button>
        <button className="secondary-link danger" type="button" disabled={!canDelete || isBusy} onClick={deleteCurrentRun}>
          {"Delete"}
        </button>
      </div>
      {message ? <p className="muted">{message}</p> : null}

      {canEditDraft ? (
        <form className="draft-edit-form" onSubmit={patchDraft}>
          <div className="detail-grid">
            <label className="field-label">
              <span>{"Candidate ID"}</span>
              <input name="candidateId" defaultValue={draft.candidateId} />
            </label>
            <label className="field-label">
              <span>{"Label"}</span>
              <input name="label" defaultValue={draft.label} />
            </label>
          </div>
          <label className="field-label">
            <span>{"Replace all CV files"}</span>
            <input name="cvFiles" type="file" multiple accept=".txt,.md,.pdf,.png,.jpg,.jpeg" />
          </label>
          <div className="jd-text-stack">
            {draft.files
              .filter((file) => file.role === "jd")
              .map((file, index) => (
                <label className="field-label" key={file.storedRelativePath}>
                  <span>{`JD display name ${index + 1}`}</span>
                  <input name="jdFileDisplayNames" defaultValue={file.displayName ?? ""} />
                </label>
              ))}
          </div>
          <label className="field-label">
            <span>{"Append JD file"}</span>
            <input name="jdFiles" type="file" multiple accept=".txt,.md,.pdf,.png,.jpg,.jpeg" />
          </label>
          <label className="field-label">
            <span>{"New JD display name"}</span>
            <input name="jdFileDisplayNames" placeholder="Company - Role" />
          </label>
          <label className="field-label">
            <span>{"Append pasted JD"}</span>
            <input name="jdTextDisplayNames" placeholder="Company - Role" />
            <textarea name="jdTexts" rows={5} placeholder="Paste JD text" />
          </label>
          <button className="primary-link" type="submit" disabled={isBusy}>
            {"Update draft"}
          </button>
        </form>
      ) : null}
    </div>
  );
}
