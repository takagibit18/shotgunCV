"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import type { EvaluationResult } from "../../lib/evaluations";
import {
  DEFAULT_EVALUATION_FILTERS,
  filterEvaluationResults,
  sortEvaluationResults,
  type EvaluationFilterState,
  type EvaluationSortKey,
} from "../../lib/evaluation-filters";

const PAGE_SIZE = 10;

export function EvaluationQueue({ results }: { results: EvaluationResult[] }) {
  const [filters, setFilters] = useState<EvaluationFilterState>(DEFAULT_EVALUATION_FILTERS);
  const [sortKey, setSortKey] = useState<EvaluationSortKey>("recent");
  const [page, setPage] = useState(1);

  const providerOptions = useMemo(
    () => Array.from(new Set(results.map((item) => item.provider).filter((provider) => provider !== "unknown"))).sort(),
    [results],
  );
  const decisionOptions = useMemo(
    () => Array.from(new Set(results.map((item) => item.applyDecision).filter(Boolean))).sort(),
    [results],
  );
  const visibleResults = useMemo(
    () => sortEvaluationResults(filterEvaluationResults(results, filters), sortKey),
    [filters, results, sortKey],
  );
  const pageCount = Math.max(1, Math.ceil(visibleResults.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const paginatedResults = visibleResults.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  useEffect(() => {
    setPage(1);
  }, [filters, sortKey]);

  return (
    <section className="section section-flush evaluation-section">
      <div className="section-heading queue-heading">
        <div>
          <p className="eyebrow">评估结果</p>
          <h2>岗位评估队列</h2>
          <p className="section-copy">按 JD 聚合 scorecard、gate、证据、风险和投递建议，优先处理高风险或需复核岗位。</p>
        </div>
        <span className="status-chip info">{visibleResults.length}/{results.length} 条结果</span>
      </div>

      <div className="evaluation-controls" aria-label="评估结果筛选">
        <label className="control-field evaluation-search">
          <span>搜索</span>
          <input
            value={filters.query}
            placeholder="搜索 JD、run、证据、风险、建议"
            aria-label="搜索 JD、run、证据、风险、建议"
            onChange={(event) => setFilters((current) => ({ ...current, query: event.currentTarget.value }))}
          />
        </label>
        <label className="control-field">
          <span>Gate</span>
          <select
            value={filters.gate}
            aria-label="Gate 筛选"
            onChange={(event) => setFilters((current) => ({ ...current, gate: event.currentTarget.value }))}
          >
            <option value="all">全部 gate</option>
            <option value="pass">通过</option>
            <option value="needs_review">需复核</option>
            <option value="blocked">阻断</option>
            <option value="legacy">历史产物</option>
          </select>
        </label>
        <label className="control-field">
          <span>风险</span>
          <select
            value={filters.risk}
            aria-label="风险筛选"
            onChange={(event) => setFilters((current) => ({ ...current, risk: event.currentTarget.value }))}
          >
            <option value="all">全部风险</option>
            <option value="high">高风险</option>
            <option value="medium">中风险</option>
            <option value="low">低风险</option>
            <option value="unknown">未知</option>
          </select>
        </label>
        <label className="control-field">
          <span>分数</span>
          <select
            value={filters.score}
            aria-label="分数筛选"
            onChange={(event) => setFilters((current) => ({ ...current, score: event.currentTarget.value }))}
          >
            <option value="all">全部分数</option>
            <option value="high">高分</option>
            <option value="medium">中分</option>
            <option value="low">低分</option>
            <option value="unknown">未知</option>
          </select>
        </label>
        <label className="control-field">
          <span>Provider</span>
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
          <span>建议</span>
          <select
            value={filters.decision}
            aria-label="投递建议筛选"
            onChange={(event) => setFilters((current) => ({ ...current, decision: event.currentTarget.value }))}
          >
            <option value="all">全部建议</option>
            {decisionOptions.map((decision) => (
              <option key={decision} value={decision}>
                {decision}
              </option>
            ))}
          </select>
        </label>
        <label className="control-field">
          <span>排序</span>
          <select
            value={sortKey}
            aria-label="评估结果排序"
            onChange={(event) => setSortKey(event.currentTarget.value as EvaluationSortKey)}
          >
            <option value="recent">最近更新</option>
            <option value="score">最终分</option>
            <option value="risk">风险分</option>
            <option value="priority">优先级</option>
            <option value="title">岗位标题</option>
          </select>
        </label>
        <button className="secondary-link evaluation-reset" type="button" onClick={() => setFilters(DEFAULT_EVALUATION_FILTERS)}>
          重置
        </button>
      </div>

      {results.length === 0 ? (
        <div className="empty-state">
          <h3>暂无评估结果</h3>
          <p>等待 run 完成 evaluate 阶段后，这里会按 JD 聚合评分、gate、风险和投递建议。</p>
          <Link href="/" className="primary-link">
            返回运行队列
          </Link>
        </div>
      ) : null}

      {results.length > 0 && visibleResults.length === 0 ? (
        <div className="empty-state">
          <h3>没有匹配的评估结果</h3>
          <p>清空搜索词或放宽 gate、风险、分数、provider 与投递建议筛选。</p>
        </div>
      ) : null}

      {visibleResults.length > PAGE_SIZE ? (
        <PaginationSummary
          currentPage={currentPage}
          pageCount={pageCount}
          totalCount={visibleResults.length}
          onPrevious={() => setPage((current) => Math.max(1, current - 1))}
          onNext={() => setPage((current) => Math.min(pageCount, current + 1))}
        />
      ) : null}

      {visibleResults.length > 0 ? (
        <div className="evaluation-table" role="table" aria-label="岗位评估队列">
          <div className="evaluation-table-head" role="row">
            <span role="columnheader">岗位/JD</span>
            <span role="columnheader">Gate 与建议</span>
            <span role="columnheader">评分矩阵</span>
            <span role="columnheader">证据与风险</span>
            <span role="columnheader">操作</span>
          </div>
          {paginatedResults.map((item) => (
            <article key={`${item.runId}-${item.jdId}-${item.variantId}`} className="evaluation-row" role="row">
              <div className="evaluation-primary" role="cell">
                <Link href={item.detailHref} className="run-title-link">
                  <strong>{item.title}</strong>
                </Link>
                <span className="mono">{item.jdId}</span>
                <span className="muted">{item.runLabel}</span>
                <span className="muted">{formatDateTime(item.lastModified)}</span>
              </div>
              <div className="evaluation-status-cell" role="cell">
                <span className={buildGateClassName(item.gateStatus)}>{formatGateStatus(item.gateStatus)}</span>
                <span className="status-chip">{item.applyDecision}</span>
                <span className="pill">{item.artifactMode}</span>
                {item.gateReasons.length > 0 ? <p className="risk-line">{item.gateReasons.join(" / ")}</p> : null}
              </div>
              <div className="evaluation-score-cell" role="cell">
                <ScoreMetric label="最终分" value={item.finalScore} />
                <ScoreMetric label="真实匹配" value={item.verifiedFitScore} />
                <ScoreMetric label="改写潜力" value={item.rewritePotentialScore} />
                <ScoreMetric label="风险分" value={item.riskScore} tone="risk" />
              </div>
              <div className="evaluation-evidence-cell" role="cell">
                <p>{firstText(item.evidenceRefs, item.topReasons, "暂无证据引用")}</p>
                <p className={item.riskFlags.length > 0 ? "risk-line" : "muted"}>
                  {firstText(item.riskFlags, item.requirementSummaries, "暂无显著风险")}
                </p>
                <small className="muted">来源：scorecard / gate / evidence / strategy</small>
              </div>
              <div className="row-actions" role="cell">
                <Link href={item.detailHref} className="secondary-link">
                  详情
                </Link>
                <Link href={item.reportHref} className="secondary-link">
                  报告
                </Link>
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
    <div className="pagination-bar" aria-label="评估结果分页">
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

function ScoreMetric({ label, value, tone }: { label: string; value: number | null; tone?: "risk" }) {
  const percent = value === null ? "--" : `${Math.round(value * 100)}%`;
  return (
    <span className={tone === "risk" ? "score-pill risk" : "score-pill"}>
      <span>{label}</span>
      <strong>{percent}</strong>
    </span>
  );
}

function firstText(primary: string[], fallback: string[], emptyText: string): string {
  return primary[0] ?? fallback[0] ?? emptyText;
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toISOString().replace("T", " ").slice(0, 16);
}

function formatGateStatus(status: string): string {
  const labels: Record<string, string> = {
    pass: "通过",
    blocked: "阻断",
    needs_review: "需复核",
    legacy: "历史产物",
  };
  return labels[status] ?? status;
}

function buildGateClassName(status: string): string {
  if (status === "blocked") {
    return "status-chip danger";
  }
  if (status === "needs_review") {
    return "status-chip warning";
  }
  if (status === "pass") {
    return "status-chip success";
  }
  return "status-chip";
}
