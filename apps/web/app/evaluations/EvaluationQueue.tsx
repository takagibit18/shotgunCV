"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { Icon, type IconName } from "../AppShell";
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

  const riskInPage =
    results.length > 0 &&
    (paginatedResults.some((item) => item.gateStatus === "blocked" || item.gateStatus === "needs_review") ||
      paginatedResults.some((item) => (item.riskScore ?? 0) >= 0.7));

  useEffect(() => {
    setPage(1);
  }, [filters, sortKey]);

  return (
    <section className="section section-flush evaluation-section">
      <h3 className="eval-filter-heading">
        <Icon name="filter" />
        筛选与排序
      </h3>

      <div className="evaluation-controls" aria-label="评估结果筛选">
        <label className="control-field evaluation-search">
          <FilterLabel icon="search" text="搜索" />
          <input
            value={filters.query}
            placeholder="搜索岗位、证据、风险、建议"
            aria-label="搜索岗位、证据、风险、建议"
            onChange={(event) => setFilters((current) => ({ ...current, query: event.currentTarget.value }))}
          />
        </label>
        <label className="control-field">
          <FilterLabel icon="shield-check" text="门槛" />
          <select
            value={filters.gate}
            aria-label="门槛筛选"
            onChange={(event) => setFilters((current) => ({ ...current, gate: event.currentTarget.value }))}
          >
            <option value="all">全部门槛</option>
            <option value="pass">通过</option>
            <option value="needs_review">需复核</option>
            <option value="blocked">阻断</option>
            <option value="legacy">历史结果</option>
          </select>
        </label>
        <label className="control-field">
          <FilterLabel icon="shield-alert" text="风险" />
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
          <FilterLabel icon="stats" text="分数" />
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
          <FilterLabel icon="briefcase" text="投递建议" />
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
          <FilterLabel icon="filter" text="排序" />
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
        <button className="secondary-link evaluation-reset icon-link" type="button" onClick={() => setFilters(DEFAULT_EVALUATION_FILTERS)}>
          <Icon name="reset" />
          重置
        </button>
      </div>

      {results.length === 0 ? (
        <div className="empty-state">
          <h3>暂无评估结果</h3>
          <p>等待投递完成评估后，这里会按岗位聚合匹配度、风险和投递建议。</p>
          <Link href="/runs" className="primary-link">
            返回运行队列
          </Link>
        </div>
      ) : null}

      {results.length > 0 && visibleResults.length === 0 ? (
        <div className="empty-state">
          <h3>没有匹配的评估结果</h3>
          <p>
          当前筛选：{filters.gate !== "all" ? `门槛=${formatGateStatus(filters.gate)} ` : ""}
            {filters.risk !== "all" ? `风险=${filters.risk} ` : ""}
            {filters.score !== "all" ? `分数=${filters.score} ` : ""}
            {filters.decision !== "all" ? `建议=${filters.decision} ` : ""}
            {filters.query ? `搜索="${filters.query}" ` : ""}
          </p>
          <button className="secondary-button" type="button" onClick={() => setFilters(DEFAULT_EVALUATION_FILTERS)}>
            重置筛选
          </button>
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

      {riskInPage ? (
        <div className="eval-risk-banner" role="alert">
          <Icon name="shield-alert" />
          当前页面存在高风险或需复核的岗位，建议优先处理。
        </div>
      ) : null}

      {visibleResults.length > 0 ? (
        <div className="evaluation-table" role="table" aria-label="岗位评估队列">
          <div className="evaluation-table-head" role="row">
            <span role="columnheader">岗位</span>
            <span role="columnheader">投递判断</span>
            <span role="columnheader">匹配与风险</span>
            <span role="columnheader">证据与风险</span>
            <span role="columnheader">操作</span>
          </div>
          {paginatedResults.map((item) => (
            <article key={`${item.runId}-${item.jdId}-${item.variantId}`} className="evaluation-row" role="row">
              <div className="evaluation-primary" role="cell">
                <Link href={item.detailHref} className="run-title-link">
                  <strong>{item.title}</strong>
                </Link>
                <span className="muted">{formatDisplayName(item.runLabel)}</span>
                <span className="muted">最近更新 {formatDateTime(item.lastModified)}</span>
              </div>
              <div className="evaluation-status-cell" role="cell">
                <span className={buildGateClassName(item.gateStatus)}>{formatGateStatus(item.gateStatus)}</span>
                <span className="decision-pill">
                  <Icon name="briefcase" />
                  投递建议：{formatDecision(item.applyDecision)}
                </span>
                {item.artifactMode === "legacy" ? <span className="pill">历史结果</span> : null}
                {item.gateReasons.length > 0 ? <p className="risk-line">{summarizeList(item.gateReasons)}</p> : null}
              </div>
              <div className="evaluation-score-cell" role="cell">
                <ScoreMetric label="综合" value={item.finalScore} />
                <ScoreMetric label="匹配" value={item.verifiedFitScore} />
                <ScoreMetric label="补强" value={item.rewritePotentialScore} />
                <ScoreMetric label="风险" value={item.riskScore} tone="risk" />
              </div>
              <div className="evaluation-evidence-cell" role="cell">
                <p>{firstText(item.evidenceRefs, item.topReasons, "暂无证据引用")}</p>
                <p className={item.riskFlags.length > 0 ? "risk-line" : "muted"}>
                  {firstText(item.riskFlags, item.requirementSummaries, "暂无显著风险")}
                </p>
              </div>
              <div className="row-actions" role="cell">
                <Link href={item.detailHref} className="secondary-link icon-link">
                  <Icon name="eye" />
                  查看
                </Link>
                <Link href={item.reportHref} className="secondary-link icon-link">
                  <Icon name="document" />
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

function formatDisplayName(value: string): string {
  if (!value || /^[a-z0-9][a-z0-9._-]*$/i.test(value)) {
    return "未命名投递";
  }
  return value;
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
        <button className="secondary-button icon-link" type="button" disabled={currentPage <= 1} onClick={onPrevious}>
          <Icon name="chevron-left" />
          上一页
        </button>
        <button className="secondary-button icon-link" type="button" disabled={currentPage >= pageCount} onClick={onNext}>
          下一页
          <Icon name="chevron-right" />
        </button>
      </div>
    </div>
  );
}

function FilterLabel({ icon, text }: { icon: IconName; text: string }) {
  return (
    <span className="field-label-row">
      <span>
        <Icon name={icon} />
        {text}
      </span>
    </span>
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

function summarizeList(values: string[]): string {
  const [first, ...rest] = values;
  if (!first) {
    return "";
  }
  return rest.length > 0 ? `${first}（另 ${rest.length} 条）` : first;
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
    legacy: "历史结果",
  };
  return labels[status] ?? status;
}

function formatDecision(value: string): string {
  const labels: Record<string, string> = {
    apply: "建议投递",
    manual_review: "人工复核",
    hold: "暂缓",
    skip: "跳过",
    review: "复核",
  };
  return labels[value] ?? value;
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
