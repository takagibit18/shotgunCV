"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import type { RunSummary } from "../lib/runs";
import { Icon } from "./AppShell";

type RunListFilterState = {
  query: string;
  status: string;
  stage: string;
  provider: string;
};

type RunSortKey = "recent" | "progress" | "status" | "label";

const STAGE_LABELS: Record<string, string> = {
  ingest: "导入",
  analyze: "分析",
  generate: "生成",
  evaluate: "评估",
  plan: "计划",
  report: "报告",
};

const STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  queued: "排队中",
  running: "运行中",
  done: "已完成",
  failed: "失败",
  "ingest-ready": "导入就绪",
};

const PAGE_SIZE = 10;

export function RunQueue({ runs }: { runs: RunSummary[] }) {
  const [filters, setFilters] = useState<RunListFilterState>({
    query: "",
    status: "all",
    stage: "all",
    provider: "all",
  });
  const [sortKey, setSortKey] = useState<RunSortKey>("recent");
  const [page, setPage] = useState(1);

  const providerOptions = useMemo(
    () =>
      Array.from(
        new Set(
          runs.flatMap((run) => [run.analyzerProvider, run.generatorProvider, run.judgeProvider, run.plannerProvider]),
        ),
      )
        .filter((provider) => provider && provider !== "unknown")
        .sort(),
    [runs],
  );

  const visibleRuns = useMemo(() => {
    const query = filters.query.trim().toLowerCase();
    return runs
      .filter((run) => {
        const queryText = [
          run.runId,
          run.label,
          run.draftStatus,
          run.generatorProvider,
          run.judgeProvider,
          run.runStatus?.error_summary ?? "",
          run.runStatus?.quality_summary ?? "",
        ]
          .join(" ")
          .toLowerCase();
        const matchesQuery = !query || queryText.includes(query);
        const matchesStatus = filters.status === "all" || run.draftStatus === filters.status;
        const matchesStage = filters.stage === "all" || run.completedStages.some((stage) => stage === filters.stage);
        const providers = [run.analyzerProvider, run.generatorProvider, run.judgeProvider, run.plannerProvider];
        const matchesProvider = filters.provider === "all" || providers.includes(filters.provider);
        return matchesQuery && matchesStatus && matchesStage && matchesProvider;
      })
      .sort((left, right) => compareRuns(left, right, sortKey));
  }, [filters, runs, sortKey]);
  const pageCount = Math.max(1, Math.ceil(visibleRuns.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const paginatedRuns = visibleRuns.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  const onlyDrafts = runs.length > 0 && runs.every((run) => run.draftStatus === "draft");

  useEffect(() => {
    setPage(1);
  }, [filters, sortKey]);

  return (
    <section className="section section-flush queue-section">
      <div className="section-heading queue-heading">
        <div>
          <p className="eyebrow">运行队列</p>
          <h2>本地 run 工作队列</h2>
          <p className="section-copy">按状态、阶段和 provider 快速定位需要处理的批次。</p>
        </div>
        <span className="status-chip">本机运行管理</span>
      </div>

      <div className="queue-controls" aria-label="运行队列筛选">
        <label className="control-field queue-search">
          <span>搜索</span>
          <input
            value={filters.query}
            placeholder="搜索 run、标签、provider"
            aria-label="搜索 run、标签、provider"
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
          <span>Provider 筛选</span>
          <select
            value={filters.provider}
            aria-label="Provider 筛选"
            onChange={(event) => setFilters((current) => ({ ...current, provider: event.currentTarget.value }))}
          >
            <option value="all">全部 provider</option>
            {providerOptions.map((provider) => (
              <option key={provider} value={provider}>
                {provider}
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
      </div>

      {runs.length === 0 ? (
        <div className="empty-state">
          <h3>暂无 run</h3>
          <p>先创建一个草稿 run，或把已有 run 目录放入当前 runs 根目录。</p>
          <Link href="/upload" className="primary-link">
            创建草稿 run
          </Link>
        </div>
      ) : onlyDrafts ? (
        <div className="notice-strip warning">
          <strong>当前只有草稿。</strong>
          <span>确认输入后进入详情页运行 pipeline，或在本地执行草稿中的命令。</span>
        </div>
      ) : null}

      {runs.length > 0 && visibleRuns.length === 0 ? (
        <div className="empty-state">
          <h3>没有匹配筛选结果</h3>
          <p>清空搜索词或放宽状态、阶段、provider 条件。</p>
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
            <span role="columnheader">Run</span>
            <span role="columnheader">状态</span>
            <span role="columnheader">阶段进度</span>
            <span role="columnheader">Provider</span>
            <span role="columnheader">风险与动作</span>
            <span role="columnheader">操作</span>
          </div>
          {paginatedRuns.map((run) => (
            <article key={run.runId} className="run-row" role="row">
              <div className="run-primary" role="cell">
                <Link href={`/runs/${run.runId}`} className="run-title-link">
                  <strong>{run.label || "未命名运行"}</strong>
                </Link>
                <span className="mono">{run.runId}</span>
                <span className="muted">{formatDateTime(run.lastModified)}</span>
              </div>
              <div className="run-status-cell" role="cell">
                <span className={buildStatusClassName(run.draftStatus)}>{STATUS_LABELS[run.draftStatus] ?? run.draftStatus}</span>
                {run.runStatus?.quality_summary ? <span className="status-chip warning">质量警告</span> : null}
                {run.runStatus?.error_summary ? <span className="status-chip danger">失败摘要</span> : null}
              </div>
              <div className="run-progress" role="cell">
                <div className="progress-meta">
                  <span>阶段完成</span>
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
              <div className="provider-stack" role="cell">
                <span>
                  生成 <strong>{run.generatorProvider}</strong>
                </span>
                <span>
                  评审 <strong>{run.judgeProvider}</strong>
                </span>
              </div>
              <div className="run-action-cell" role="cell">
                <p className={run.runStatus?.error_summary ? "risk-line" : "muted"}>
                  {run.runStatus?.error_summary ?? run.runStatus?.quality_summary ?? "暂无阻断风险"}
                </p>
                <span className={run.runStatus?.error_summary ? "status-chip danger" : "status-chip success"}>
                  {run.runStatus?.error_summary ? "需处理" : "健康"}
                </span>
              </div>
              <div className="row-actions" role="cell">
                <Link href={`/runs/${run.runId}`} className="secondary-link">
                  详情
                </Link>
                {run.completedStages.includes("report") ? (
                  <Link href={`/runs/${run.runId}/report`} className="secondary-link">
                    报告
                  </Link>
                ) : (
                  <span className="secondary-link" aria-disabled="true">
                    报告
                  </span>
                )}
              </div>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
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

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toISOString().replace("T", " ").slice(0, 16);
}
