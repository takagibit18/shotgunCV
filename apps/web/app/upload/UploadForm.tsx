"use client";

import React, { useState, useEffect, useRef } from "react";

import { CvTextSidecarPanel } from "../CvTextSidecarPanel";
import { ACTIVE_CANDIDATE_KEY, CANDIDATE_EVENT } from "../CandidateSelector";
import type { CandidateSummary } from "../../lib/candidates";
import type { CvIssue } from "../../lib/upload-drafts";

type DraftSuccess = {
  runId: string;
  status: "draft";
  uploadManifestPath: string;
  nextCommand: string;
  cvIssues?: CvIssue[];
  needsManualText: boolean;
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

type StoredCandidate = {
  candidateId: string;
  displayName: string;
};

type UploadCandidate = CandidateSummary & {
  isLocalOnly?: boolean;
};

type CandidateResponse = {
  candidates: CandidateSummary[];
};

const ACCEPTED_INPUT_TYPES = ".txt,.md,.pdf,.png,.jpg,.jpeg";

export function UploadForm() {
  const [result, setResult] = useState<DraftSuccess | null>(null);
  const [error, setError] = useState<DraftError | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeCandidate, setActiveCandidate] = useState<UploadCandidate | null>(null);
  const candidateOptionsRef = useRef<CandidateSummary[]>([]);
  const [cvFiles, setCvFiles] = useState<JdFileEntry[]>([]);
  const [nextCvFileId, setNextCvFileId] = useState(1);
  const [jdMode, setJdMode] = useState<"files" | "text">("files");
  const [jdFiles, setJdFiles] = useState<JdFileEntry[]>([]);
  const [nextFileId, setNextFileId] = useState(1);
  const [jdTexts, setJdTexts] = useState<JdTextEntry[]>([{ id: 1, displayName: "", value: "" }]);
  const [nextTextId, setNextTextId] = useState(2);
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);
  const reusableCvFiles = activeCandidate?.cvFiles ?? [];
  const totalCvCount = reusableCvFiles.length + cvFiles.length;

  useEffect(() => {
    let cancelled = false;
    fetch("/api/candidates", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error("候选人列表读取失败");
        }
        return (await response.json()) as CandidateResponse;
      })
      .then((payload) => {
        if (cancelled) {
          return;
        }
        candidateOptionsRef.current = payload.candidates;
        setActiveCandidate(resolveActiveCandidate(payload.candidates, readStoredCandidate()));
      })
      .catch(() => {
        if (!cancelled) {
          setActiveCandidate(resolveActiveCandidate([], readStoredCandidate()));
        }
      });

    function handleCandidateChange(event: Event) {
      const detail = (event as CustomEvent<StoredCandidate>).detail;
      setActiveCandidate(resolveActiveCandidate(candidateOptionsRef.current, detail));
    }

    window.addEventListener(CANDIDATE_EVENT, handleCandidateChange);
    return () => {
      cancelled = true;
      window.removeEventListener(CANDIDATE_EVENT, handleCandidateChange);
    };
  }, []);

  function handleCvTextSaved(savedOriginalNames: string[]) {
    setResult((current) => {
      if (!current) {
        return current;
      }
      const saved = new Set(savedOriginalNames);
      const cvIssues = (current.cvIssues ?? []).filter((issue) => !saved.has(issue.originalName));
      return { ...current, cvIssues, needsManualText: cvIssues.length > 0 };
    });
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResult(null);
    setError(null);
    setIsSubmitting(true);

    const form = event.currentTarget;
    const formData = new FormData(form);
    formData.delete("cvFiles");
    formData.delete("candidateId");
    formData.delete("candidateDisplayName");
    formData.delete("existingCvRefs");
    formData.delete("jdFiles");
    formData.delete("jdFileDisplayNames");
    formData.delete("jdTexts");
    formData.delete("jdTextDisplayNames");
    cvFiles.forEach((entry) => {
      formData.append("cvFiles", entry.file);
    });
    if (activeCandidate) {
      formData.append("candidateId", activeCandidate.candidateId);
      formData.append("candidateDisplayName", activeCandidate.displayName);
      if (activeCandidate.cvFiles.length > 0) {
        formData.append(
          "existingCvRefs",
          JSON.stringify(
            activeCandidate.cvFiles.map((file) => ({
              sourceRunId: file.sourceRunId,
              storedRelativePath: file.storedRelativePath,
            })),
          ),
        );
      }
    }
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
        <li>2 岗位输入</li>
        <li>3 草稿确认</li>
      </ol>
      <form className="upload-form" onSubmit={handleSubmit}>
        <section className="upload-panel">
          <div className="upload-panel-heading">
            <div>
              <p className="eyebrow">{"简历材料"}</p>
              <h3>{"候选人材料"}</h3>
            </div>
          </div>
          <div className="candidate-prefill-panel">
            <span className="avatar-mark compact">{activeCandidate?.initials ?? "候"}</span>
            <div>
              <strong>{activeCandidate ? activeCandidate.displayName : "未选择候选人"}</strong>
              <p>
                {reusableCvFiles.length > 0
                  ? `已预填 ${reusableCvFiles.length} 份历史简历，可继续上传补充材料。`
                  : "当前候选人暂无可复用简历，请上传第一份简历。"}
              </p>
              {reusableCvFiles.length > 0 ? (
                <ul>
                  {reusableCvFiles.map((file) => (
                    <li key={`${file.sourceRunId}:${file.storedRelativePath}`}>{file.originalName}</li>
                  ))}
                </ul>
              ) : null}
            </div>
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
              required={totalCvCount === 0}
              accept={ACCEPTED_INPUT_TYPES}
              onChange={(event) => {
                if (event.currentTarget.files) {
                  appendCvFiles(event.currentTarget.files);
                  event.currentTarget.value = "";
                }
              }}
            />
            <div>
              <strong>{"将简历文件拖拽到此区域"}</strong>
              <p>{"拖拽到此处，或点击按钮选择文件；支持 PDF、Markdown、文本和图片文件。"}</p>
            </div>
            <label className="primary-link" htmlFor="cvFiles">
              {"选择本地简历文件（可多选）"}
            </label>
          </div>
          {cvFiles.length > 0 ? (
            <ul className="upload-file-list" aria-label="已选择简历文件">
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
            <p className="upload-empty-hint">{"尚未选择简历或补充材料"}</p>
          )}
        </section>

        <section className="upload-panel">
          <div className="upload-panel-heading">
            <div>
              <p className="eyebrow">{"岗位描述"}</p>
              <h3>{"岗位信息"}</h3>
            </div>
            <div className="upload-segment" aria-label="岗位输入方式">
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
                <strong>{"将岗位文件拖拽到此区域"}</strong>
                <p>{"拖拽到此处，或点击按钮选择文件；支持截图图片、PDF、Markdown 和文本文件。"}</p>
                <p>{"每个岗位都需要填写非空的公司/岗位显示名。"}</p>
              </div>
              <label className="primary-link" htmlFor="jdFiles">
                {"选择本地岗位文件（可多选）"}
              </label>
            </div>
          ) : (
            <div className="jd-text-stack">
              {jdTexts.map((entry, index) => (
                <div className="jd-text-entry" key={entry.id}>
                  <label className="field-label">
                    <span>{`岗位文本 ${index + 1}`}</span>
                    <input
                      name="jdTextDisplayNames"
                      value={entry.displayName}
                      placeholder="公司/岗位显示名，例如：某公司 - 产品经理"
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
                {"添加岗位文本"}
              </button>
            </div>
          )}

          {jdFiles.length > 0 ? (
            <ul className="upload-file-list" aria-label="已选择岗位文件">
              {jdFiles.map((entry, index) => (
                <li key={entry.id}>
                  <div className="upload-file-item">
                    <FileThumbnail file={entry.file} onClick={setLightboxUrl} />
                    <input
                      name="jdFileDisplayNames"
                      value={entry.displayName}
                      placeholder="公司/岗位显示名，例如：某公司 - 产品经理"
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
            <p className="upload-empty-hint">{"尚未选择岗位文件"}</p>
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
              <span className="confirmation-label">{"简历文件"}</span>
              <span className="confirmation-value">
                <strong>{totalCvCount > 0 ? `${totalCvCount} 个` : "待选择"}</strong>
                <span className="confirmation-hint">
                  {reusableCvFiles.length > 0 ? ` · 含 ${reusableCvFiles.length} 份历史简历` : " · 必须至少 1 个"}
                </span>
              </span>
            </div>
            <div className="confirmation-row">
              <span className="confirmation-label">{"岗位输入"}</span>
              <span className="confirmation-value">
                <strong>{jdMode === "files" ? `${jdFiles.length} 个文件` : `${jdTexts.filter((entry) => entry.value.trim()).length} 条文本`}</strong>
                <span className="confirmation-hint">{" · 每个岗位需要显示名"}</span>
              </span>
            </div>
          </div>
        </section>

        <button className="primary-link" type="submit" disabled={isSubmitting}>
          {isSubmitting ? "正在创建草稿" : "创建投递草稿"}
        </button>
      </form>

      {error ? (
        <div className="upload-result error" role="alert">
          <p className="eyebrow">{"创建未完成"}</p>
          <strong>{"请检查输入后重试"}</strong>
          <p>{error.error}</p>
        </div>
      ) : null}

      {result ? (
        <div className="upload-result" role="status">
          <h3>草稿已创建</h3>
          <p>草稿已创建，点击下方按钮进入详情页运行。</p>
          <div className="row-actions">
            <a className="primary-link" href={`/runs/${result.runId}`}>
              {"进入详情页"}
            </a>
            <a className="secondary-link" href="/runs">
              {"返回运行队列"}
            </a>
          </div>
          <details className="advanced-command">
            <summary>高级 / 本地执行命令</summary>
            <pre className="command-block">{result.nextCommand}</pre>
          </details>
        </div>
      ) : null}

      {result?.needsManualText && result.cvIssues ? (
        <CvTextSidecarPanel runId={result.runId} cvIssues={result.cvIssues} onSaved={handleCvTextSaved} />
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

function readStoredCandidate(): StoredCandidate | null {
  const value = localStorage.getItem(ACTIVE_CANDIDATE_KEY);
  if (!value) {
    return null;
  }
  try {
    const parsed = JSON.parse(value) as Partial<StoredCandidate>;
    if (typeof parsed.candidateId === "string" && typeof parsed.displayName === "string") {
      return { candidateId: parsed.candidateId, displayName: parsed.displayName };
    }
  } catch {
    return null;
  }
  return null;
}

function resolveActiveCandidate(candidates: CandidateSummary[], stored: StoredCandidate | null): UploadCandidate | null {
  if (stored) {
    const matched = candidates.find((candidate) => candidate.candidateId === stored.candidateId);
    if (matched) {
      return matched;
    }
    return {
      candidateId: stored.candidateId,
      displayName: stored.displayName,
      initials: buildInitials(stored.displayName),
      latestRunId: "",
      latestLabel: "",
      updatedAt: new Date().toISOString(),
      runCount: 0,
      cvFiles: [],
      isLocalOnly: true,
    };
  }
  return candidates[0] ?? null;
}

function buildInitials(displayName: string): string {
  const trimmed = displayName.trim();
  const asciiWords = trimmed.match(/[A-Za-z0-9]+/g);
  if (asciiWords && asciiWords.length > 0) {
    return asciiWords
      .slice(0, 2)
      .map((word) => word[0])
      .join("")
      .toUpperCase();
  }
  return trimmed.slice(0, 2) || "候";
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
