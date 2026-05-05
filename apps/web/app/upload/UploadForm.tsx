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

type JdTextEntry = {
  id: number;
  displayName: string;
  value: string;
};

type JdFileEntry = {
  id: number;
  file: File;
  displayName: string;
};

const ACCEPTED_INPUT_TYPES = ".txt,.md,.pdf,.png,.jpg,.jpeg";

export function UploadForm() {
  const [result, setResult] = useState<DraftSuccess | null>(null);
  const [error, setError] = useState<DraftError | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [jdMode, setJdMode] = useState<"files" | "text">("files");
  const [jdFiles, setJdFiles] = useState<JdFileEntry[]>([]);
  const [nextFileId, setNextFileId] = useState(1);
  const [jdTexts, setJdTexts] = useState<JdTextEntry[]>([{ id: 1, displayName: "", value: "" }]);
  const [nextTextId, setNextTextId] = useState(2);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResult(null);
    setError(null);
    setIsSubmitting(true);

    const form = event.currentTarget;
    const formData = new FormData(form);
    formData.delete("jdFiles");
    formData.delete("jdFileDisplayNames");
    formData.delete("jdTexts");
    formData.delete("jdTextDisplayNames");
    jdFiles.forEach((entry) => {
      formData.append("jdFiles", entry.file);
      formData.append("jdFileDisplayNames", entry.displayName);
    });
    jdTexts.forEach((entry) => {
      formData.append("jdTextDisplayNames", entry.displayName);
      formData.append("jdTexts", entry.value);
    });

    const response = await fetch("/api/runs/drafts", {
      method: "POST",
      body: formData,
    });
    const payload = (await response.json()) as DraftSuccess | DraftError;
    setIsSubmitting(false);
    if (!response.ok) {
      setError(payload as DraftError);
      return;
    }
    setResult(payload as DraftSuccess);
    form.reset();
    setJdFiles([]);
    setNextFileId(1);
    setJdTexts([{ id: 1, displayName: "", value: "" }]);
    setNextTextId(2);
  }

  function appendJdFiles(files: FileList | File[]) {
    const incoming = Array.from(files);
    if (incoming.length === 0) {
      return;
    }
    setJdFiles((current) => [
      ...current,
      ...incoming.map((file, index) => ({
        id: nextFileId + index,
        file,
        displayName: "",
      })),
    ]);
    setNextFileId((current) => current + incoming.length);
  }

  function removeJdFile(index: number) {
    setJdFiles((current) => current.filter((_, itemIndex) => itemIndex !== index));
  }

  function updateJdFileDisplayName(id: number, displayName: string) {
    setJdFiles((current) => current.map((entry) => (entry.id === id ? { ...entry, displayName } : entry)));
  }

  function addJdTextEntry() {
    setJdTexts((current) => [...current, { id: nextTextId, displayName: "", value: "" }]);
    setNextTextId((current) => current + 1);
  }

  function updateJdTextEntry(id: number, value: string) {
    setJdTexts((current) => current.map((entry) => (entry.id === id ? { ...entry, value } : entry)));
  }

  function updateJdTextDisplayName(id: number, displayName: string) {
    setJdTexts((current) => current.map((entry) => (entry.id === id ? { ...entry, displayName } : entry)));
  }

  function removeJdTextEntry(id: number) {
    setJdTexts((current) => {
      const next = current.filter((entry) => entry.id !== id);
      return next.length > 0 ? next : [{ id: 1, displayName: "", value: "" }];
    });
  }

  return (
    <div className="upload-workspace">
      <form className="upload-form" onSubmit={handleSubmit}>
        <section className="upload-panel">
          <div className="upload-panel-heading">
            <div>
              <p className="eyebrow">{"CV"}</p>
              <h3>{"候选人材料"}</h3>
            </div>
            <span className="status-chip">{"自动生成 Candidate ID"}</span>
          </div>
          <label className="field-label">
            <span>{"CV / 补充材料"}</span>
            <input name="cvFiles" type="file" multiple required accept={ACCEPTED_INPUT_TYPES} />
          </label>
        </section>

        <section className="upload-panel">
          <div className="upload-panel-heading">
            <div>
              <p className="eyebrow">{"JD"}</p>
              <h3>{"岗位信息"}</h3>
            </div>
            <div className="upload-segment" aria-label="JD 输入方式">
              <button type="button" className={jdMode === "files" ? "active" : ""} onClick={() => setJdMode("files")}>
                {"本地文件"}
              </button>
              <button type="button" className={jdMode === "text" ? "active" : ""} onClick={() => setJdMode("text")}>
                {"粘贴文本"}
              </button>
            </div>
          </div>

          {jdMode === "files" ? (
            <div
              className="jd-dropzone"
              onDragOver={(event) => {
                event.preventDefault();
              }}
              onDrop={(event) => {
                event.preventDefault();
                appendJdFiles(event.dataTransfer.files);
              }}
            >
              <input
                id="jdFiles"
                name="jdFiles"
                type="file"
                multiple
                accept={ACCEPTED_INPUT_TYPES}
                onChange={(event) => {
                  if (event.currentTarget.files) {
                    appendJdFiles(event.currentTarget.files);
                    event.currentTarget.value = "";
                  }
                }}
              />
              <div>
                <strong>{"将 JD 文件拖拽到此区域"}</strong>
                <p>{"拖拽到此处，或点击按钮选择文件；支持截图图片、PDF、Markdown 和文本文件。"}</p>
                <p>{"每个 JD 都需要填写非空的公司/岗位显示名。"}</p>
              </div>
              <label className="primary-link" htmlFor="jdFiles">
                {"选择本地 JD 文件（可多选）"}
              </label>
            </div>
          ) : (
            <div className="jd-text-stack">
              {jdTexts.map((entry, index) => (
                <label className="field-label" key={entry.id}>
                  <span>{`JD 文本 ${index + 1}`}</span>
                  <input
                    name="jdTextDisplayNames"
                    value={entry.displayName}
                    placeholder="公司/岗位显示名，例如 OpenAI - Product Manager"
                    onChange={(event) => updateJdTextDisplayName(entry.id, event.currentTarget.value)}
                  />
                  <textarea
                    name="jdTexts"
                    value={entry.value}
                    rows={6}
                    placeholder="粘贴岗位标题、公司、职责和要求"
                    onChange={(event) => updateJdTextEntry(entry.id, event.currentTarget.value)}
                  />
                  <button type="button" className="secondary-link" onClick={() => removeJdTextEntry(entry.id)}>
                    {"删除"}
                  </button>
                </label>
              ))}
              <button type="button" className="secondary-link" onClick={addJdTextEntry}>
                {"添加 JD 文本"}
              </button>
            </div>
          )}

          {jdFiles.length > 0 ? (
            <ul className="upload-file-list" aria-label="已选择 JD 文件">
              {jdFiles.map((entry, index) => (
                <li key={entry.id}>
                  <div>
                    <span>{entry.file.name}</span>
                    <input
                      name="jdFileDisplayNames"
                      value={entry.displayName}
                      placeholder="公司/岗位显示名，例如 OpenAI - Product Manager"
                      onChange={(event) => updateJdFileDisplayName(entry.id, event.currentTarget.value)}
                    />
                  </div>
                  <button type="button" onClick={() => removeJdFile(index)}>
                    {"移除"}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </section>

        <button className="primary-link coral-cta" type="submit" disabled={isSubmitting}>
          {isSubmitting ? "正在创建草稿" : "创建草稿 run"}
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
            {"草稿 manifest："}
            <span className="mono">{result.uploadManifestPath}</span>
          </p>
          <pre className="command-block">{result.nextCommand}</pre>
        </div>
      ) : null}
    </div>
  );
}
