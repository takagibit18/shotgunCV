"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";

import type { CandidateCvFile, CandidateSummary } from "../lib/candidates";

type CandidateResponse = {
  candidates: CandidateSummary[];
};

type ActiveCandidate = CandidateSummary & {
  isLocalOnly?: boolean;
};

type StoredCandidate = {
  candidateId: string;
  displayName: string;
};

const ACTIVE_CANDIDATE_KEY = "shotguncv.activeCandidate";
const CANDIDATE_EVENT = "shotguncv:candidate-change";

export function CandidateSelector() {
  const [candidates, setCandidates] = useState<CandidateSummary[]>([]);
  const [activeCandidate, setActiveCandidate] = useState<ActiveCandidate | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [isAdding, setIsAdding] = useState(false);
  const [newDisplayName, setNewDisplayName] = useState("");
  const [loadState, setLoadState] = useState<"idle" | "loading" | "error">("idle");
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    setLoadState("loading");
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
        setCandidates(payload.candidates);
        const stored = readStoredCandidate();
        const matched = stored
          ? payload.candidates.find((candidate) => candidate.candidateId === stored.candidateId)
          : null;
        if (matched) {
          setActiveCandidate(matched);
        } else if (stored) {
          setActiveCandidate(buildLocalCandidate(stored));
        } else {
          setActiveCandidate(payload.candidates[0] ?? null);
        }
        setLoadState("idle");
      })
      .catch(() => {
        if (!cancelled) {
          setLoadState("error");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
        setIsAdding(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsOpen(false);
        setIsAdding(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  function selectCandidate(candidate: ActiveCandidate) {
    setActiveCandidate(candidate);
    setIsOpen(false);
    setIsAdding(false);
    persistCandidate(candidate);
  }

  function addCandidate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const displayName = newDisplayName.trim();
    if (!displayName) {
      return;
    }
    const candidate = buildLocalCandidate({
      candidateId: buildCandidateId(displayName),
      displayName,
    });
    setNewDisplayName("");
    selectCandidate(candidate);
  }

  const currentLabel = activeCandidate?.displayName ?? "未选择候选人";
  const currentHint = activeCandidate
    ? activeCandidate.cvFiles.length > 0
      ? `${activeCandidate.cvFiles.length} 份简历可复用`
      : "新候选人，需上传简历"
    : loadState === "loading"
      ? "正在读取历史候选人"
      : "新建草稿时可选择";

  return (
    <div className="candidate-selector" ref={rootRef}>
      <button
        type="button"
        className="sidebar-user candidate-trigger"
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        onClick={() => setIsOpen((current) => !current)}
      >
        <span className="avatar-mark">{activeCandidate?.initials ?? "候"}</span>
        <span className="candidate-trigger-copy">
          <strong>{currentLabel}</strong>
          <small>{currentHint}</small>
        </span>
        <span className="candidate-trigger-chevron" aria-hidden="true">
          ›
        </span>
      </button>

      {isOpen ? (
        <div className="candidate-popover" role="dialog" aria-label="候选人选择">
          <div className="candidate-popover-heading">
            <span>候选人档案</span>
            <small>{candidates.length > 0 ? "选择后将预填新草稿简历" : "暂无历史候选人"}</small>
          </div>

          {loadState === "error" ? <p className="candidate-popover-error">候选人列表暂时无法读取。</p> : null}

          {candidates.length > 0 ? (
            <div className="candidate-list" role="listbox" aria-label="历史候选人">
              {candidates.map((candidate) => (
                <button
                  key={candidate.candidateId}
                  type="button"
                  className={[
                    "candidate-option",
                    activeCandidate?.candidateId === candidate.candidateId ? "active" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  onClick={() => selectCandidate(candidate)}
                >
                  <span className="avatar-mark compact">{candidate.initials}</span>
                  <span>
                    <strong>{candidate.displayName}</strong>
                    <small>{`${candidate.cvFiles.length} 份简历 · ${candidate.runCount} 次投递`}</small>
                  </span>
                  {activeCandidate?.candidateId === candidate.candidateId ? (
                    <span className="candidate-option-check" aria-hidden="true">
                      ✓
                    </span>
                  ) : null}
                </button>
              ))}
            </div>
          ) : (
            <p className="candidate-empty">创建第一个草稿后，这里会出现可复用的候选人简历。</p>
          )}

          <div className="candidate-add-block">
            {isAdding ? (
              <form onSubmit={addCandidate}>
                <label>
                  <span>候选人名称</span>
                  <input
                    value={newDisplayName}
                    placeholder="例如：李华"
                    onChange={(event) => setNewDisplayName(event.currentTarget.value)}
                    autoFocus
                  />
                </label>
                <div className="candidate-add-actions">
                  <button type="submit">添加</button>
                  <button type="button" onClick={() => setIsAdding(false)}>
                    取消
                  </button>
                </div>
              </form>
            ) : (
              <button type="button" className="candidate-add-button" onClick={() => setIsAdding(true)}>
                <span aria-hidden="true">＋</span>
                添加候选人
              </button>
            )}
          </div>

          <Link href="/upload" className="candidate-upload-link" onClick={() => setIsOpen(false)}>
            用当前候选人创建草稿
          </Link>
        </div>
      ) : null}
    </div>
  );
}

function persistCandidate(candidate: ActiveCandidate) {
  const payload: StoredCandidate = {
    candidateId: candidate.candidateId,
    displayName: candidate.displayName,
  };
  localStorage.setItem(ACTIVE_CANDIDATE_KEY, JSON.stringify(payload));
  window.dispatchEvent(new CustomEvent(CANDIDATE_EVENT, { detail: payload }));
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

function buildLocalCandidate(candidate: StoredCandidate): ActiveCandidate {
  return {
    candidateId: candidate.candidateId,
    displayName: candidate.displayName,
    initials: buildInitials(candidate.displayName),
    latestRunId: "",
    latestLabel: "",
    updatedAt: new Date().toISOString(),
    runCount: 0,
    cvFiles: [] satisfies CandidateCvFile[],
    isLocalOnly: true,
  };
}

function buildCandidateId(displayName: string): string {
  const slug = displayName
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 32);
  return `cand-${slug || Date.now().toString(36)}`;
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

export { ACTIVE_CANDIDATE_KEY, CANDIDATE_EVENT };
