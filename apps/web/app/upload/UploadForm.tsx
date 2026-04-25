"use client";

import React, { useState } from "react";


type DraftSuccess = {
  runId: string;
  status: "draft";
  uploadManifestPath: string;
  nextCommand: string;
};

type DraftError = {
  error: string;
  code: string;
};


export function UploadForm() {
  const [result, setResult] = useState<DraftSuccess | null>(null);
  const [error, setError] = useState<DraftError | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResult(null);
    setError(null);
    setIsSubmitting(true);
    const form = event.currentTarget;
    const response = await fetch("/api/runs/drafts", {
      method: "POST",
      body: new FormData(form),
    });
    const payload = (await response.json()) as DraftSuccess | DraftError;
    setIsSubmitting(false);
    if (!response.ok) {
      setError(payload as DraftError);
      return;
    }
    setResult(payload as DraftSuccess);
    form.reset();
  }

  return (
    <div className="upload-workspace">
      <form className="upload-form" onSubmit={handleSubmit}>
        <label>
          <span>{"Candidate ID"}</span>
          <input name="candidateId" required placeholder="cand-001" />
        </label>
        <label>
          <span>{"Label"}</span>
          <input name="label" placeholder="April upload" />
        </label>
        <label>
          <span>{"CV / 补充材料"}</span>
          <input name="cvFiles" type="file" multiple required accept=".txt,.md,.pdf,.png,.jpg,.jpeg" />
        </label>
        <label>
          <span>{"JD 文件"}</span>
          <input name="jdFiles" type="file" multiple required accept=".txt,.md,.pdf,.png,.jpg,.jpeg" />
        </label>
        <button className="primary-link" type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Creating draft" : "Create draft run"}
        </button>
      </form>

      {error ? (
        <div className="upload-result error" role="alert">
          <strong>{error.code}</strong>
          <p>{error.error}</p>
        </div>
      ) : null}

      {result ? (
        <div className="upload-result" role="status">
          <h3>{result.runId}</h3>
          <p>
            {"Draft manifest: "}
            <span className="mono">{result.uploadManifestPath}</span>
          </p>
          <pre className="command-block">{result.nextCommand}</pre>
        </div>
      ) : null}
    </div>
  );
}
