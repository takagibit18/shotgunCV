"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { STAGE_LABELS, STATUS_LABELS } from "../lib/labels";
import type { RunSummary } from "../lib/runs";
import { Icon } from "./AppShell";

type RunListFilterState = {
  query: string;
  status: string;
  stage: string;
};

type RunSortKey = "recent" | "progress" | "status" | "label";

const PAGE_SIZE = 10;

export function RunQueue({ runs }: { runs: RunSummary[] }) {
  const [filters, setFilters] = useState<RunListFilterState>({
    query: "",
    status: "all",
    stage: "all",
  });
  const [sortKey, setSortKey] = useState<RunSortKey>("recent");
  const [page, setPage] = useState(1);
  const [deletingRunId, setDeletingRunId] = useState("");
  const [deleteMessage, setDeleteMessage] = useState("");

  const visibleRuns = useMemo(() => {
    const query = filters.query.trim().toLowerCase();
    return runs
      .filter((run) => {
        const queryText = [
          run.runId,
          run.label,
          run.draftStatus,
          run.runStatus?.error_summary ?? "",
          run.runStatus?.quality_summary ?? "",
        ]
          .join(" ")
          .toLowerCase();
        const matchesQuery = !query || queryText.includes(query);
        const matchesStatus = filters.status === "all" || run.draftStatus === filters.status;
        const matchesStage = filters.stage === "all" || run.completedStages.some((stage) => stage === filters.stage);
        return matchesQuery && matchesStatus && matchesStage;
      })
      .sort((left, right) => compareRuns(left, right, sortKey));
  }, [filters, runs, sortKey]);
  const pageCount = Math.max(1, Math.ceil(visibleRuns.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const paginatedRuns = visibleRuns.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  const onlyDrafts = runs.length > 0 && runs.every((run) => run.draftStatus === "draft");
  const activeCount = runs.filter((run) => run.draftStatus === "running" || run.draftStatus === "queued").length;
  const attentionCount = runs.filter((run) => run.draftStatus === "failed" || run.runStatus?.error_summary).length;
  const reportCount = runs.filter((run) => run.completedStages.includes("report")).length;

  function handleReset() {
    setFilters({ query: "", status: "all", stage: "all" });
    setSortKey("recent");
  }

  async function deleteRunFromQueue(run: RunSummary) {
    if (!canDeleteRun(run)) {
      return;
    }
    const confirmed = typeof window === "undefined" || window.confirm(`确认删除“${run.label || "未命名投递"}”？`);
    if (!confirmed) {
      return;
    }
    setDeletingRunId(run.runId);
    setDeleteMessage(String());
    try {
      const response = await fetch(`/api/runs/${run.runId}`, { method: "DELETE" });
      if (!response.ok) {
        const payload = (await response.json()) as { error?: string; code?: string };
        setDeleteMessage(payload.error ?? payload.code ?? "删除失败，请稍后重试。");
        return;
      }
      if (typeof window !== "undefined") {
        window.location.reload();
      }
    } catch {
      setDeleteMessage("删除失败，请检查本地服务后重试。");
    } finally {
      setDeletingRunId("");
    }
  }

  useEffect(() => {
    setPage(1);
  }, [filters, sortKey]);

  return (
    <section className="section section-flush queue-section">
      <div className="eval-summary-strip queue-summary-strip" aria-label="运行队列总览">
        <span className="eval-summary-item">
          <Icon name="list" />
          全部投递 <strong>{runs.length}</strong>
        </span>
        <span className="eval-summary-item">
          <Icon name="play" />
          进行中 <strong>{activeCount}</strong>
        </span>
        <span className="eval-summary-item">
          <Icon name="alert-triangle" />
          需要处理 <strong>{attentionCount}</strong>
        </span>
        <span className="eval-summary-item">
          <Icon name="document" />
          可查看报告 <strong>{reportCount}</strong>
        </span>
      </div>
      {deleteMessage ? <p className="queue-delete-message" role="alert">{deleteMessage}</p> : null}

      <div className="queue-controls" aria-label="运行队列筛选">
        <label className="control-field queue-search">
          <span>搜索</span>
          <input
            value={filters.query}
            placeholder="搜索投递名称、状态、风险"
            aria-label="搜索投递名称、状态、风险"
            onChange={(event) => setFilters((current) => ({ ...current, query: event.currentTarget.value }))}
          />
        </label>
        <label className="control-field">
          <span>状态筛选</span>
          <select
            value={filters.status}
            aria-label="状态筛选"
            onChange={(event) => setFilters((current) => ({ ...current, status: event.currentTarget.value }))}
          >
            <option value="all">全部状态</option>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="control-field">
          <span>阶段筛选</span>
          <select
            value={filters.stage}
            aria-label="阶段筛选"
            onChange={(event) => setFilters((current) => ({ ...current, stage: event.currentTarget.value }))}
          >
            <option value="all">全部阶段</option>
            {Object.entries(STAGE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="control-field">
          <span>排序</span>
          <select
            value={sortKey}
            aria-label="排序"
            onChange={(event) => setSortKey(event.currentTarget.value as RunSortKey)}
          >
            <option value="recent">最近修改</option>
            <option value="progress">阶段进度</option>
            <option value="status">状态优先</option>
            <option value="label">标签名称</option>
          </select>
        </label>
        <button className="secondary-button queue-reset" type="button" onClick={handleReset}>
          重置
        </button>
      </div>

      {runs.length === 0 ? (
        <div className="empty-state">
          <h3>暂无投递</h3>
          <p>先创建一个投递草稿，或把已有运行目录放入当前本地数据目录。</p>
          <Link href="/upload" className="primary-link">
            创建投递草稿
          </Link>
        </div>
      ) : onlyDrafts ? (
        <div className="notice-strip warning">
          <strong>当前只有草稿。</strong>
          <span>确认输入后进入详情页启动本地流程，或在高级模式下使用草稿命令。</span>
        </div>
      ) : null}

      {runs.length > 0 && visibleRuns.length === 0 ? (
        <div className="empty-state">
          <h3>没有匹配筛选结果</h3>
          <p>清空搜索词或放宽状态、阶段条件。</p>
        </div>
      ) : null}

      {visibleRuns.length > PAGE_SIZE ? (
        <PaginationSummary
          currentPage={currentPage}
          pageCount={pageCount}
          totalCount={visibleRuns.length}
          onPrevious={() => setPage((current) => Math.max(1, current - 1))}
          onNext={() => setPage((current) => Math.min(pageCount, current + 1))}
        />
      ) : null}

      {visibleRuns.length > 0 ? (
        <div className="run-table" role="table" aria-label="运行队列">
          <div className="run-table-head" role="row">
            <span role="columnheader">投递</span>
            <span role="columnheader">状态</span>
            <span role="columnheader">进度</span>
            <span role="columnheader">需要关注</span>
            <span role="columnheader">操作</span>
          </div>
          {paginatedRuns.map((run) => (
            <article key={run.runId} className="run-row" role="row">
              <div className="run-primary" role="cell">
                <Link href={`/runs/${run.runId}`} className="run-title-link">
                  <strong title={run.label || ""}>{run.label || "未命名投递"}</strong>
                </Link>
                <span className="muted">最近更新 {formatDateTime(run.lastModified)}</span>
              </div>
              <div className="run-status-cell" role="cell">
                <span className={buildStatusClassName(run.draftStatus)}>{STATUS_LABELS[run.draftStatus] ?? run.draftStatus}</span>
                {run.runStatus?.quality_summary ? <span className="status-chip warning">有提醒</span> : null}
                {run.runStatus?.error_summary ? <span className="status-chip danger">失败</span> : null}
              </div>
              <div className="run-progress" role="cell">
                <div className="progress-meta">
                  <span>已完成</span>
                  <strong>{run.completedStages.length}/6</strong>
                </div>
                <div className="stage-track" aria-label={`阶段完成 ${run.completedStages.length}/6`}>
                  {Object.keys(STAGE_LABELS).map((stage) => (
                    <span
                      key={stage}
                      className={run.completedStages.some((completedStage) => completedStage === stage) ? "stage-dot active" : "stage-dot"}
                      title={STAGE_LABELS[stage]}
                    />
                  ))}
                </div>
                <div className="pill-row compact">
                  {run.completedStages.length > 0 ? (
                    run.completedStages.map((stage) => (
                      <span key={stage} className="pill">
                        {STAGE_LABELS[stage] ?? stage}
                      </span>
                    ))
                  ) : (
                    <span className="pill">等待导入</span>
                  )}
                </div>
              </div>
              <div className="run-action-cell" role="cell">
                <p
                  className={run.runStatus?.error_summary ? "risk-line" : "muted"}
                  title={run.runStatus?.error_summary ?? run.runStatus?.quality_summary ?? ""}
                >
                  {truncateText(run.runStatus?.error_summary ?? run.runStatus?.quality_summary ?? getNextStepText(run), 34)}
                </p>
                <span className={run.runStatus?.error_summary ? "status-chip danger" : "status-chip success"}>
                  {run.runStatus?.error_summary ? "需处理" : "可继续"}
                </span>
              </div>
              <div className="row-actions" role="cell">
                <Link href={`/runs/${run.runId}`} className="secondary-link icon-link">
                  <Icon name="eye" />
                  {getPrimaryActionText(run)}
                </Link>
                {run.completedStages.includes("report") ? (
                  <Link href={`/runs/${run.runId}/report`} className="secondary-link icon-link">
                    <Icon name="document" />
                    报告
                  </Link>
                ) : null}
                <button
                  className="secondary-link danger icon-link row-delete-button"
                  type="button"
                  disabled={!canDeleteRun(run) || deletingRunId === run.runId}
                  title={canDeleteRun(run) ? "删除该投递" : "仅草稿或失败的投递可删除"}
                  onClick={() => deleteRunFromQueue(run)}
                >
                  <Icon name="delete" />
                  {deletingRunId === run.runId ? "删除中" : "删除"}
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function canDeleteRun(run: RunSummary): boolean {
  return run.draftStatus === "draft" || run.draftStatus === "failed";
}

function PaginationSummary({
  currentPage,
  pageCount,
  totalCount,
  onPrevious,
  onNext,
}: {
  currentPage: number;
  pageCount: number;
  totalCount: number;
  onPrevious: () => void;
  onNext: () => void;
}) {
  return (
    <div className="pagination-bar" aria-label="运行队列分页">
      <span>
        第 {currentPage} / {pageCount} 页 · 每页 {PAGE_SIZE} 条 · 共 {totalCount} 条
      </span>
      <div className="row-actions">
        <button className="secondary-button" type="button" disabled={currentPage <= 1} onClick={onPrevious}>
          上一页
        </button>
        <button className="secondary-button" type="button" disabled={currentPage >= pageCount} onClick={onNext}>
          下一页
        </button>
      </div>
    </div>
  );
}

function getNextStepText(run: RunSummary): string {
  if (run.draftStatus === "draft") {
    return "确认输入后启动评估流程";
  }
  if (run.draftStatus === "failed") {
    return "查看失败原因并重新处理";
  }
  if (run.draftStatus === "running" || run.draftStatus === "queued") {
    return "流程正在推进，查看最新进度";
  }
  if (run.completedStages.includes("report")) {
    return "报告已就绪，可进入结果复核";
  }
  return "继续查看当前进度";
}

function getPrimaryActionText(run: RunSummary): string {
  if (run.draftStatus === "draft") {
    return "启动";
  }
  if (run.draftStatus === "failed") {
    return "处理";
  }
  return "查看";
}

function compareRuns(left: RunSummary, right: RunSummary, sortKey: RunSortKey): number {
  if (sortKey === "progress") {
    return right.completedStages.length - left.completedStages.length || right.lastModified.localeCompare(left.lastModified);
  }
  if (sortKey === "status") {
    return statusWeight(right.draftStatus) - statusWeight(left.draftStatus) || right.lastModified.localeCompare(left.lastModified);
  }
  if (sortKey === "label") {
    return (left.label || left.runId).localeCompare(right.label || right.runId, "zh-Hans-CN");
  }
  return right.lastModified.localeCompare(left.lastModified);
}

function statusWeight(status: string): number {
  const weights: Record<string, number> = {
    failed: 5,
    running: 4,
    queued: 3,
    draft: 2,
    done: 1,
    "ingest-ready": 0,
  };
  return weights[status] ?? 0;
}

function buildStatusClassName(status: string): string {
  if (status === "failed") {
    return "status-chip danger";
  }
  if (status === "done") {
    return "status-chip success";
  }
  if (status === "running" || status === "queued") {
    return "status-chip info";
  }
  return "status-chip";
}

function truncateText(text: string, maxLen: number): string {
  if (text.length <= maxLen) {
    return text;
  }
  return text.slice(0, maxLen - 1) + "…";
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toISOString().replace("T", " ").slice(0, 16);
}
