"use client";

import React, { useMemo, useState } from "react";
import Link from "next/link";

import type { ResumeWorkspaceRow } from "../../lib/resume";
import { Icon } from "../AppShell";
import {
  buildConstraintClassName,
  buildStatusChip,
  formatFilterStatus,
  formatGateStatus,
  formatStatus,
} from "./resume-utils";

type FilterState = {
  query: string;
  status: string;
  source: string;
  sort: string;
};

const DEFAULT_FILTERS: FilterState = {
  query: "",
  status: "all",
  source: "all",
  sort: "recent",
};

export function ResumeWorkspace({ rows }: { rows: ResumeWorkspaceRow[] }) {
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);

  const filtered = useMemo(() => {
    let result = rows;

    if (filters.query.trim()) {
      const q = filters.query.trim().toLowerCase();
      result = result.filter(
        (row) =>
          row.label.toLowerCase().includes(q) ||
          row.runId.toLowerCase().includes(q) ||
          row.variants.some(
            (v) =>
              v.variantDisplayName.toLowerCase().includes(q) ||
              v.summary.toLowerCase().includes(q) ||
              v.targetJdLabels.some((l) => l.toLowerCase().includes(q)),
          ),
      );
    }

    if (filters.status !== "all") {
      result = result.filter((row) => row.status === filters.status);
    }

    if (filters.source !== "all") {
      result = result.filter((row) => row.artifactMode === filters.source);
    }

    switch (filters.sort) {
      case "versions_desc":
        result = [...result].sort((a, b) => b.variantCount - a.variantCount);
        break;
      case "constraints_desc":
        result = [...result].sort((a, b) => b.evidenceConstraintCount - a.evidenceConstraintCount);
        break;
      default:
        break;
    }

    return result;
  }, [rows, filters]);

  if (rows.length === 0) {
    return (
      <section className="empty-state">
        <h3>暂无简历优化 run</h3>
        <p>先创建草稿 run，完成 pipeline 后这里会展示版本摘要、证据约束和投递前检查。</p>
        <Link href="/upload" className="primary-link">
          创建草稿 run
        </Link>
      </section>
    );
  }

  return (
    <>
      <div className="resume-controls" aria-label="简历优化筛选">
        <label className="control-field resume-search">
          <span>搜索</span>
          <input
            value={filters.query}
            placeholder="搜索版本名、run、摘要"
            aria-label="搜索版本名、run、摘要"
            onChange={(e) => setFilters((c) => ({ ...c, query: e.currentTarget.value }))}
          />
        </label>
        <label className="control-field">
          <span>状态</span>
          <select
            value={filters.status}
            aria-label="状态筛选"
            onChange={(e) => setFilters((c) => ({ ...c, status: e.currentTarget.value }))}
          >
            <option value="all">全部状态</option>
            <option value="done">已完成</option>
            <option value="running">运行中</option>
            <option value="queued">排队中</option>
            <option value="draft">草稿</option>
            <option value="failed">失败</option>
          </select>
        </label>
        <label className="control-field">
          <span>来源</span>
          <select
            value={filters.source}
            aria-label="来源筛选"
            onChange={(e) => setFilters((c) => ({ ...c, source: e.currentTarget.value }))}
          >
            <option value="all">全部来源</option>
            <option value="v0.5.7">v0.5.7</option>
            <option value="legacy">legacy</option>
          </select>
        </label>
        <label className="control-field">
          <span>排序</span>
          <select
            value={filters.sort}
            aria-label="排序方式"
            onChange={(e) => setFilters((c) => ({ ...c, sort: e.currentTarget.value }))}
          >
            <option value="recent">最近更新</option>
            <option value="versions_desc">版本数降序</option>
            <option value="constraints_desc">约束数降序</option>
          </select>
        </label>
        <button
          className="secondary-link resume-reset"
          type="button"
          onClick={() => setFilters(DEFAULT_FILTERS)}
        >
          重置
        </button>
      </div>

      {filtered.length === 0 ? (
        <div className="empty-state">
          <h3>没有匹配的筛选结果</h3>
          <p>
            当前筛选：
            {filters.status !== "all" ? `状态=${formatFilterStatus(filters.status)} ` : ""}
            {filters.source !== "all" ? `来源=${filters.source} ` : ""}
            {filters.query ? `搜索="${filters.query}" ` : ""}
          </p>
          <button
            className="secondary-button"
            type="button"
            onClick={() => setFilters(DEFAULT_FILTERS)}
          >
            重置筛选
          </button>
        </div>
      ) : (
        <section className="resume-workspace" aria-label="简历优化 run 列表">
          {filtered.map((row) => (
            <ResumeWorkspaceCard key={row.runId} row={row} />
          ))}
        </section>
      )}
    </>
  );
}

function ResumeWorkspaceCard({ row }: { row: ResumeWorkspaceRow }) {
  const firstVariant = row.variants[0];
  const visibleConstraints = row.constraints.slice(0, 3);
  const isEmpty = !firstVariant && row.constraints.length === 0;

  return (
    <article className="resume-card">
      <div className="resume-card-header">
        <div className="resume-card-title-group">
          <div className="resume-card-eyebrow">
            <span className={buildStatusChip(row.status)}>{formatStatus(row.status)}</span>
            {row.artifactMode === "legacy" ? (
              <span className="pill legacy-tag">legacy</span>
            ) : null}
          </div>
          <h2>{row.label}</h2>
          <span className="mono">{row.runId}</span>
        </div>
        <div className="row-actions resume-card-header-actions">
          <Link href={row.detailHref} className="secondary-link">
            详情
          </Link>
          {row.reportHref ? (
            <Link href={row.reportHref} className="secondary-link">
              报告
            </Link>
          ) : (
            <Link href={row.uploadHref} className="secondary-link">
              创建草稿
            </Link>
          )}
        </div>
      </div>

      {isEmpty ? (
        <p className="muted">当前 artifact 未提供该类条目。</p>
      ) : (
        <div className="resume-card-grid">
          <div className="resume-info-block">
            <div className="resume-info-title">
              <Icon name="document" />
              <h3>版本摘要</h3>
            </div>
            {firstVariant ? (
              <>
                <strong>{firstVariant.variantDisplayName}</strong>
                <span className="mono">{firstVariant.variantId}</span>
                <p className="muted">{firstVariant.summary}</p>
                <small className="muted">{firstVariant.sourceLabel}</small>
                <div className="pill-row compact">
                  {firstVariant.targetJdLabels.map((label) => (
                    <span key={label} className="pill">
                      {label}
                    </span>
                  ))}
                </div>
              </>
            ) : (
              <p className="muted">当前 artifact 未提供该类条目。</p>
            )}
          </div>

          <div className="resume-info-block">
            <div className="resume-info-title">
              <Icon name="sparkle" />
              <h3>改写边界</h3>
            </div>
            {firstVariant ? (
              <>
                <BoundarySection
                  title="可安全改写"
                  items={firstVariant.safeRewriteItems}
                />
                <BoundarySection
                  title="待核实模拟补强"
                  items={firstVariant.simulatedSupplementItems}
                />
                <BoundarySection
                  title="禁止编造缺口"
                  items={firstVariant.forbiddenGapItems}
                />
              </>
            ) : (
              <p className="muted">当前 artifact 未提供该类条目。</p>
            )}
          </div>

          <div className="resume-info-block">
            <div className="resume-info-title">
              <Icon name="check-square" />
              <h3>证据约束</h3>
            </div>
            {visibleConstraints.length > 0 ? (
              <div className="resume-constraint-list">
                {visibleConstraints.map((c) => (
                  <div key={`${c.jdId}-${c.requirementText}`} className="resume-constraint-item">
                    <span className={buildConstraintClassName(c.category)}>{c.category}</span>
                    <p>{c.requirementText}</p>
                    <small className="muted">{c.sourceLabel}</small>
                  </div>
                ))}
              </div>
            ) : (
              <p className="muted">当前 artifact 未提供该类条目。</p>
            )}
          </div>

          <div className="resume-info-block">
            <div className="resume-info-title">
              <Icon name="bell" />
              <h3>投递前检查</h3>
            </div>
            <dl className="settings-list compact">
              <div>
                <dt>Gate</dt>
                <dd>{formatGateStatus(row.preflightStatus)}</dd>
              </div>
              <div>
                <dt>下一步</dt>
                <dd>{row.nextAction}</dd>
              </div>
              <div>
                <dt>来源</dt>
                <dd>{row.sourceLabel}</dd>
              </div>
            </dl>
            {row.warningText ? (
              <p className="risk-line">{row.warningText}</p>
            ) : (
              <p className="muted">暂无阻断风险。</p>
            )}
          </div>
        </div>
      )}

      <div className="resume-card-mobile-actions">
        <Link href={row.detailHref} className="secondary-link">
          详情
        </Link>
        {row.reportHref ? (
          <Link href={row.reportHref} className="secondary-link">
            报告
          </Link>
        ) : (
          <Link href={row.uploadHref} className="secondary-link">
            创建草稿
          </Link>
        )}
      </div>
    </article>
  );
}

function BoundarySection({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="resume-boundary-group">
      <strong>{title}</strong>
      {items.length > 0 ? (
        <ul>
          {items.map((item, i) => (
            <li key={`${i}-${item.slice(0, 20)}`}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">当前 artifact 未提供该类条目。</p>
      )}
    </div>
  );
}
