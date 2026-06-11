"use client";

import React, { useEffect, useRef, useState } from "react";

import type { RunDraftStatus, RunStatusFile, StageName } from "../../../lib/types";

type RunStatusSnapshot = {
  draftStatus: RunDraftStatus;
  runStatus: RunStatusFile | null;
  completedStages: StageName[];
  hasResults: boolean;
  hasReport: boolean;
  reviewItemCount: number;
};

type Props = {
  runId: string;
  initialStatus: RunDraftStatus;
  initialStage: StageName | null;
  initialCompletedStages: StageName[];
};

const ACTIVE_STATUSES = new Set(["queued", "running", "partial_running"]);
const TERMINAL_STATUSES = new Set(["done", "failed", "partial_failed"]);
const POLL_INTERVAL_MS = 3500;
const MAX_CONSECUTIVE_FAILURES = 3;

export function RunStatusPoller({ runId, initialStatus, initialStage, initialCompletedStages }: Props) {
  if (!ACTIVE_STATUSES.has(initialStatus)) {
    return null;
  }
  return (
    <ActiveRunStatusPoller
      runId={runId}
      initialStatus={initialStatus}
      initialStage={initialStage}
      initialCompletedStages={initialCompletedStages}
    />
  );
}

function ActiveRunStatusPoller({ runId, initialStatus, initialStage, initialCompletedStages }: Props) {
  const [pollError, setPollError] = useState("");
  const lastSignatureRef = useRef(buildSignature(initialStatus, initialStage, initialCompletedStages));

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    let failureCount = 0;

    async function poll() {
      try {
        const response = await fetch(`/api/runs/${runId}`, { cache: "no-store" });
        if (!response.ok) {
          throw new Error("status request failed");
        }
        const snapshot = (await response.json()) as RunStatusSnapshot;
        if (cancelled) {
          return;
        }
        failureCount = 0;
        setPollError("");
        const nextStatus = snapshot.runStatus?.status ?? snapshot.draftStatus;
        const nextStage = snapshot.runStatus?.current_stage ?? null;
        const nextSignature = buildSignature(nextStatus, nextStage, snapshot.completedStages);
        const changed = nextSignature !== lastSignatureRef.current;
        if (changed || TERMINAL_STATUSES.has(nextStatus) || snapshot.hasResults || snapshot.hasReport) {
          lastSignatureRef.current = nextSignature;
          window.location.reload();
        }
        if (ACTIVE_STATUSES.has(nextStatus)) {
          timer = window.setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch {
        if (cancelled) {
          return;
        }
        failureCount += 1;
        if (failureCount >= MAX_CONSECUTIVE_FAILURES) {
          setPollError("暂时无法读取最新进度。可以稍后重试，或手动刷新当前页面。");
        }
        timer = window.setTimeout(poll, POLL_INTERVAL_MS * Math.min(failureCount + 1, 3));
      }
    }

    timer = window.setTimeout(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
    };
  }, [runId]);

  return (
    <div className="run-poller-status" role="status" aria-live="polite">
      <span>页面会自动读取本地进度，阶段变化或完成后会更新结果。</span>
      {pollError ? <strong>{pollError}</strong> : null}
    </div>
  );
}

function buildSignature(status: string, stage: StageName | null, completedStages: StageName[]) {
  return [status, stage ?? "none", completedStages.join(",")].join("|");
}
