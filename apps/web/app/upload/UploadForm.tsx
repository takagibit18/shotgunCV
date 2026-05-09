"use client";

import React, { useState, useEffect } from "react";

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
  const [cvFiles, setCvFiles] = useState<JdFileEntry[]>([]);
  const [nextCvFileId, setNextCvFileId] = useState(1);
  const [jdMode, setJdMode] = useState<"files" | "text">("files");
  const [jdFiles, setJdFiles] = useState<JdFileEntry[]>([]);
  const [nextFileId, setNextFileId] = useState(1);
  const [jdTexts, setJdTexts] = useState<JdTextEntry[]>([{ id: 1, displayName: "", value: "" }]);
  const [nextTextId, setNextTextId] = useState(2);
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResult(null);
    setError(null);
    setIsSubmitting(true);

    const form = event.currentTarget;
    const formData = new FormData(form);
    formData.delete("cvFiles");
    formData.delete("jdFiles");
    formData.delete("jdFileDisplayNames");
    formData.delete("jdTexts");
    formData.delete("jdTextDisplayNames");
    cvFiles.forEach((entry) => {
      formData.append("cvFiles", entry.file);
    });
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
    setCvFiles([]);
    setNextCvFileId(1);
    setJdFiles([]);
    setNextFileId(1);
    setJdTexts([{ id: 1, displayName: "", value: "" }]);
    setNextTextId(2);
  }

  function appendCvFiles(files: FileList | File[]) {
    const incoming = Array.from(files);
    if (incoming.length === 0) {
      return;
    }
    setCvFiles((current) => [
      ...current,
      ...incoming.map((file, index) => ({
        id: nextCvFileId + index,
        file,
        displayName: "",
      })),
    ]);
    setNextCvFileId((current) => current + incoming.length);
  }

  function removeCvFile(index: number) {
    setCvFiles((current) => current.filter((_, itemIndex) => itemIndex !== index));
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
      <ol className="stepper" aria-label="草稿创建步骤">
        <li>1 候选人材料</li>
        <li>2 JD 输入</li>
        <li>3 草稿确认</li>
      </ol>
      <form className="upload-form" onSubmit={handleSubmit}>
        <section className="upload-panel">
          <div className="upload-panel-heading">
            <div>
              <p className="eyebrow">{"CV"}</p>
              <h3>{"候选人材料"}</h3>
            </div>
            <span className="status-chip">{"自动生成 Candidate ID"}</span>
          </div>
          <div
            className="jd-dropzone"
            onDragOver={(event) => {
              event.preventDefault();
            }}
            onDrop={(event) => {
              event.preventDefault();
              appendCvFiles(event.dataTransfer.files);
            }}
          >
            <input
              id="cvFiles"
              name="cvFiles"
              type="file"
              multiple
              required={cvFiles.length === 0}
              accept={ACCEPTED_INPUT_TYPES}
              onChange={(event) => {
                if (event.currentTarget.files) {
                  appendCvFiles(event.currentTarget.files);
                  event.currentTarget.value = "";
                }
              }}
            />
            <div>
              <strong>{"将 CV 文件拖拽到此区域"}</strong>
              <p>{"拖拽到此处，或点击按钮选择文件；支持 PDF、Markdown、文本和图片文件。"}</p>
            </div>
            <label className="primary-link" htmlFor="cvFiles">
              {"选择本地 CV 文件（可多选）"}
            </label>
          </div>
          {cvFiles.length > 0 ? (
            <ul className="upload-file-list" aria-label="已选择 CV 文件">
              {cvFiles.map((entry, index) => (
                <li key={entry.id}>
                  <div>
                    <span>{entry.file.name}</span>
                  </div>
                  <button type="button" onClick={() => removeCvFile(index)}>
                    {"移除"}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="upload-empty-hint">{"尚未选择 CV 或补充材料"}</p>
          )}
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
                <div className="jd-text-entry" key={entry.id}>
                  <label className="field-label">
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
                  </label>
                  <button type="button" className="inline-action" onClick={() => removeJdTextEntry(entry.id)}>
                    {"删除"}
                  </button>
                </div>
              ))}
              <button type="button" className="primary-link" onClick={addJdTextEntry}>
                {"添加 JD 文本"}
              </button>
            </div>
          )}

          {jdFiles.length > 0 ? (
            <ul className="upload-file-list" aria-label="已选择 JD 文件">
              {jdFiles.map((entry, index) => (
                <li key={entry.id}>
                  <div className="upload-file-item">
                    <FileThumbnail file={entry.file} onClick={setLightboxUrl} />
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
          ) : (
            <p className="upload-empty-hint">{"尚未选择 JD 文件"}</p>
          )}
        </section>

        <section className="upload-panel confirmation-panel">
          <div className="upload-panel-heading">
            <div>
              <p className="eyebrow">{"3 草稿确认"}</p>
              <h3>{"确认后落盘"}</h3>
            </div>
          </div>
          <div className="confirmation-summary" aria-label="草稿确认字段">
            <div className="confirmation-row">
              <span className="confirmation-label">{"CV 文件"}</span>
              <span className="confirmation-value">
                <strong>{cvFiles.length > 0 ? `${cvFiles.length} 个` : "待选择"}</strong>
                <span className="confirmation-hint">{" · 必须至少 1 个"}</span>
              </span>
            </div>
            <div className="confirmation-row">
              <span className="confirmation-label">{"JD 输入"}</span>
              <span className="confirmation-value">
                <strong>{jdMode === "files" ? `${jdFiles.length} 个文件` : `${jdTexts.filter((entry) => entry.value.trim()).length} 条文本`}</strong>
                <span className="confirmation-hint">{" · 每个 JD 需要显示名"}</span>
              </span>
            </div>
          </div>
        </section>

        <button className="primary-link" type="submit" disabled={isSubmitting}>
          {isSubmitting ? "正在创建草稿" : "创建草稿 run"}
        </button>
      </form>

      {error ? (
        <div className="upload-result error" role="alert">
          <p className="eyebrow">{"页面级错误摘要"}</p>
          <strong>{error.code}</strong>
          <p>{error.error}</p>
        </div>
      ) : null}

      {result ? (
        <div className="upload-result" role="status">
          <h3>{result.runId}</h3>
          <div className="row-actions">
            <a className="primary-link" href={`/runs/${result.runId}`}>
              {"打开草稿详情"}
            </a>
            <a className="secondary-link" href="/">
              {"返回运行队列"}
            </a>
          </div>
          <p>
            {"草稿 manifest："}
            <span className="mono">{result.uploadManifestPath}</span>
          </p>
          <pre className="command-block">{result.nextCommand}</pre>
        </div>
      ) : null}

      {lightboxUrl ? (
        <div className="lightbox-overlay" onClick={() => setLightboxUrl(null)}>
          <button className="lightbox-close" type="button" onClick={() => setLightboxUrl(null)} aria-label="关闭预览">
            {"X"}
          </button>
          <img src={lightboxUrl} alt="预览" onClick={(event) => event.stopPropagation()} />
        </div>
      ) : null}
    </div>
  );
}

const IMAGE_EXTENSIONS = /\.(png|jpg|jpeg|gif|webp|bmp)$/i;

function isImageFile(file: File): boolean {
  return file.type.startsWith("image/") || IMAGE_EXTENSIONS.test(file.name);
}

function FileThumbnail({ file, onClick }: { file: File; onClick: (url: string) => void }) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    if (isImageFile(file)) {
      const url = URL.createObjectURL(file);
      setPreviewUrl(url);
      return () => {
        URL.revokeObjectURL(url);
      };
    }
    return;
  }, [file]);

  if (!previewUrl) {
    return <span className="upload-file-name">{file.name}</span>;
  }

  return (
    <img
      src={previewUrl}
      alt={file.name}
      className="upload-thumbnail"
      onClick={(event) => {
        event.stopPropagation();
        onClick(previewUrl);
      }}
    />
  );
}
