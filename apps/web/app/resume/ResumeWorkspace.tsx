"use client";

import React, { useMemo, useState } from "react";
import Link from "next/link";

import type {
  GeneratedResumePreview,
  ResumeWorkspaceConstraint,
  ResumeWorkspaceRow,
} from "../../lib/resume";
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
  const [selectedRunId, setSelectedRunId] = useState(rows[0]?.runId ?? "");
  const [selectedResumeId, setSelectedResumeId] = useState(rows[0]?.generatedResumes[0]?.resumeId ?? "");

  const filtered = useMemo(() => {
    let result = rows;

    if (filters.query.trim()) {
      const q = filters.query.trim().toLowerCase();
      result = result.filter(
        (row) =>
          row.label.toLowerCase().includes(q) ||
          row.generatedResumes.some(
            (resume) =>
              resume.displayName.toLowerCase().includes(q) ||
              resume.targetLabel.toLowerCase().includes(q) ||
              resume.sections.some((section) => section.content.toLowerCase().includes(q)),
          ) ||
          row.variants.some(
            (variant) =>
              variant.variantDisplayName.toLowerCase().includes(q) ||
              variant.summary.toLowerCase().includes(q) ||
              variant.targetJdLabels.some((label) => label.toLowerCase().includes(q)),
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
      case "resumes_desc":
        result = [...result].sort((a, b) => b.generatedResumeCount - a.generatedResumeCount);
        break;
      case "constraints_desc":
        result = [...result].sort((a, b) => b.evidenceConstraintCount - a.evidenceConstraintCount);
        break;
      default:
        break;
    }

    return result;
  }, [rows, filters]);

  const selectedRow = filtered.find((row) => row.runId === selectedRunId) ?? filtered[0] ?? null;
  const selectedResume =
    selectedRow?.generatedResumes.find((resume) => resume.resumeId === selectedResumeId) ??
    selectedRow?.generatedResumes[0] ??
    null;

  if (rows.length === 0) {
    return (
      <section className="empty-state">
        <h3>暂无简历生成任务</h3>
        <p>先创建投递草稿，完成本地流程后这里会展示完整简历、证据状态和导出入口。</p>
        <Link href="/upload" className="primary-link">
          创建投递草稿
        </Link>
      </section>
    );
  }

  return (
    <section className="resume-studio" aria-label="简历生成工作台">
      <div className="resume-controls" aria-label="简历任务筛选">
        <label className="control-field resume-search">
          <span>搜索</span>
          <input
            value={filters.query}
            placeholder="搜索岗位、简历内容、版本摘要"
            aria-label="搜索岗位、简历内容、版本摘要"
            onChange={(event) => setFilters((current) => ({ ...current, query: event.currentTarget.value }))}
          />
        </label>
        <label className="control-field">
          <span>状态</span>
          <select
            value={filters.status}
            aria-label="状态筛选"
            onChange={(event) => setFilters((current) => ({ ...current, status: event.currentTarget.value }))}
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
            onChange={(event) => setFilters((current) => ({ ...current, source: event.currentTarget.value }))}
          >
            <option value="all">全部来源</option>
            <option value="v0.5.7">证据门槛产物</option>
            <option value="legacy">历史产物</option>
          </select>
        </label>
        <label className="control-field">
          <span>排序</span>
          <select
            value={filters.sort}
            aria-label="排序方式"
            onChange={(event) => setFilters((current) => ({ ...current, sort: event.currentTarget.value }))}
          >
            <option value="recent">最近更新</option>
            <option value="resumes_desc">简历数降序</option>
            <option value="constraints_desc">待处理证据降序</option>
          </select>
        </label>
        <button className="secondary-link resume-reset" type="button" onClick={() => setFilters(DEFAULT_FILTERS)}>
          重置
        </button>
      </div>

      {filtered.length === 0 ? (
        <div className="empty-state">
          <h3>没有匹配的简历任务</h3>
          <p>
            当前筛选：
            {filters.status !== "all" ? `状态=${formatFilterStatus(filters.status)} ` : ""}
            {filters.source !== "all" ? `来源=${filters.source} ` : ""}
            {filters.query ? `搜索="${filters.query}" ` : ""}
          </p>
          <button className="secondary-button" type="button" onClick={() => setFilters(DEFAULT_FILTERS)}>
            重置筛选
          </button>
        </div>
      ) : (
        <div className="resume-studio-grid">
          <aside className="resume-task-pane" aria-label="投递与证据处理">
            <div className="resume-task-list">
              {filtered.map((row) => (
                <button
                  key={row.runId}
                  type="button"
                  className={row.runId === selectedRow?.runId ? "resume-task active" : "resume-task"}
                  onClick={() => {
                    setSelectedRunId(row.runId);
                    setSelectedResumeId(row.generatedResumes[0]?.resumeId ?? "");
                  }}
                >
                  <span className={buildStatusChip(row.status)}>{formatStatus(row.status)}</span>
                  <strong>{row.label}</strong>
                  <small>{row.generatedResumeCount > 0 ? `${row.generatedResumeCount} 份简历可预览` : "等待完整简历产物"}</small>
                  <small>{row.nextAction}</small>
                </button>
              ))}
            </div>

            {selectedRow ? (
              <EvidencePanel row={selectedRow} />
            ) : null}
          </aside>

          <main className="resume-preview-pane" aria-label="实时简历预览">
            {selectedRow && selectedResume ? (
              <ResumePreview
                row={selectedRow}
                resume={selectedResume}
                selectedResumeId={selectedResume.resumeId}
                onSelectResume={setSelectedResumeId}
              />
            ) : selectedRow ? (
              <LegacyResumeState row={selectedRow} />
            ) : null}
          </main>
        </div>
      )}
    </section>
  );
}

function ResumePreview({
  row,
  resume,
  selectedResumeId,
  onSelectResume,
}: {
  row: ResumeWorkspaceRow;
  resume: GeneratedResumePreview;
  selectedResumeId: string;
  onSelectResume: (resumeId: string) => void;
}) {
  return (
    <article className="resume-live-preview">
      <div className="resume-preview-toolbar">
        <div>
          <span className="section-kicker">实时简历预览</span>
          <h2>{resume.displayName}</h2>
          <p>{resume.targetLabel}</p>
        </div>
        <div className="row-actions">
          <CopyMarkdownButton markdown={resume.markdown} />
          {resume.isDeliverable ? (
            <a
              className="primary-link"
              href={`data:text/markdown;charset=utf-8,${encodeURIComponent(resume.markdown)}`}
              download={resume.exportFileName}
            >
              下载 Markdown
            </a>
          ) : (
            <span className="status-chip danger">不可直接投递</span>
          )}
        </div>
      </div>

      {row.generatedResumes.length > 1 ? (
        <div className="resume-version-tabs" role="tablist" aria-label="简历版本">
          {row.generatedResumes.map((item) => (
            <button
              key={item.resumeId}
              type="button"
              role="tab"
              aria-selected={item.resumeId === selectedResumeId}
              className={item.resumeId === selectedResumeId ? "active" : ""}
              onClick={() => onSelectResume(item.resumeId)}
            >
              {item.displayName}
            </button>
          ))}
        </div>
      ) : null}

      {!resume.isDeliverable ? (
        <div className="resume-alert">
          <strong>先补齐阻断证据，再导出投递版本。</strong>
          <span>当前预览用于复核，不会被包装成可直接投递的普通简历。</span>
        </div>
      ) : null}

      <section className="resume-paper" aria-label="完整简历正文">
        {resume.markdown.split(/\n{2,}/).map((block, index) => (
          <p key={`${index}-${block.slice(0, 24)}`}>{block}</p>
        ))}
      </section>

      <section className="resume-provenance" aria-label="简历来源与风险">
        <div className="resume-info-title">
          <Icon name="check-square" />
          <h3>证据来源</h3>
        </div>
        <p>{resume.sourceLabel}</p>
        <p>候选人：{resume.markdown.startsWith("# ") ? resume.markdown.slice(2).split(/\r?\n/)[0] : "本地候选人"}</p>
        <TagList items={resume.generatedFrom} emptyText="当前产物未声明生成来源。" />
        <TagList items={resume.candidateEvidence} emptyText="当前产物未列出候选人证据。" />
        <RiskList title="待核实" items={resume.toVerifyItems} />
        <RiskList title="禁止编造" items={resume.forbiddenItems} />
      </section>
    </article>
  );
}

function EvidencePanel({ row }: { row: ResumeWorkspaceRow }) {
  const visibleConstraints = row.constraints.slice(0, 6);
  return (
    <section className="resume-evidence-pane" aria-label="证据确认">
      <div className="resume-info-title">
        <Icon name="bell" />
        <h3>证据确认</h3>
      </div>
      <dl className="settings-list compact">
        <div>
          <dt>门槛</dt>
          <dd>{formatGateStatus(row.preflightStatus)}</dd>
        </div>
        <div>
          <dt>下一步</dt>
          <dd>{row.nextAction}</dd>
        </div>
      </dl>
      {visibleConstraints.length > 0 ? (
        <div className="resume-constraint-list">
          {visibleConstraints.map((constraint) => (
            <EvidenceConstraint key={`${constraint.jdId}-${constraint.requirementId}`} row={row} constraint={constraint} />
          ))}
        </div>
      ) : (
        <p className="muted">当前没有待确认的证据门槛。</p>
      )}
      <div className="row-actions">
        <Link href={row.detailHref} className="secondary-link">
          查看详情
        </Link>
        {row.reportHref ? (
          <Link href={row.reportHref} className="secondary-link">
            查看报告
          </Link>
        ) : (
          <Link href={row.uploadHref} className="secondary-link">
            补充材料
          </Link>
        )}
      </div>
    </section>
  );
}

function EvidenceConstraint({ row, constraint }: { row: ResumeWorkspaceRow; constraint: ResumeWorkspaceConstraint }) {
  return (
    <div className="resume-constraint-item">
      <span className={buildConstraintClassName(constraint.category)}>{constraint.category}</span>
      <p>{constraint.requirementText}</p>
      <TagList items={constraint.evidenceRefs} emptyText="系统尚未找到可用证据。" />
      {constraint.userOverride ? (
        <small className="success-line">
          用户确认：{constraint.userOverride.action}
          {constraint.userOverride.note ? `，${constraint.userOverride.note}` : ""}
        </small>
      ) : (
        <EvidenceActionForm row={row} constraint={constraint} />
      )}
      <small className="muted">{constraint.sourceLabel}</small>
    </div>
  );
}

function EvidenceActionForm({ row, constraint }: { row: ResumeWorkspaceRow; constraint: ResumeWorkspaceConstraint }) {
  const [status, setStatus] = useState("");

  async function submit(action: string) {
    setStatus("保存中");
    const response = await fetch(`/api/runs/${encodeURIComponent(row.runId)}/evidence-overrides`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jdId: constraint.jdId,
        requirementId: constraint.requirementId,
        action,
        note: action === "supplement_material" ? "用户将在补充材料中完善该证据。" : "",
      }),
    });
    setStatus(response.ok ? "已保存，刷新后生效" : "保存失败");
  }

  return (
    <div className="resume-evidence-actions">
      <button type="button" onClick={() => void submit("confirm_existing")}>
        确认现有证据
      </button>
      <button type="button" onClick={() => void submit("supplement_material")}>
        补充材料
      </button>
      <button type="button" onClick={() => void submit("mark_unsatisfied")}>
        标记不满足
      </button>
      <button type="button" onClick={() => void submit("skip_requirement")}>
        不投该岗位
      </button>
      {status ? <small className="muted">{status}</small> : null}
    </div>
  );
}

function CopyMarkdownButton({ markdown }: { markdown: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    await navigator.clipboard?.writeText(markdown);
    setCopied(true);
  }
  return (
    <button className="secondary-link" type="button" onClick={() => void copy()}>
      {copied ? "已复制" : "一键复制 Markdown"}
    </button>
  );
}

function LegacyResumeState({ row }: { row: ResumeWorkspaceRow }) {
  const firstVariant = row.variants[0];
  return (
    <article className="resume-live-preview">
      <div className="resume-preview-toolbar">
        <div>
          <span className="section-kicker">等待完整简历产物</span>
          <h2>{row.label}</h2>
          <p>当前只有版本摘要，尚不能导出可投递简历。</p>
        </div>
        <Link href={row.detailHref} className="secondary-link">
          查看运行详情
        </Link>
      </div>
      {firstVariant ? (
        <section className="resume-paper">
          <p>{firstVariant.variantDisplayName}</p>
          <p>{firstVariant.summary}</p>
          <p>{firstVariant.sourceLabel}</p>
          <p>{row.sourceLabel}</p>
          <BoundarySection title="可安全改写" items={firstVariant.safeRewriteItems} />
          <BoundarySection title="待核实模拟补强" items={firstVariant.simulatedSupplementItems} />
          <BoundarySection title="禁止编造缺口" items={firstVariant.forbiddenGapItems} />
        </section>
      ) : (
        <p className="muted">当前本地产物未提供简历版本。</p>
      )}
    </article>
  );
}

function BoundarySection({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="resume-boundary-group">
      <strong>{title}</strong>
      {items.length > 0 ? (
        <ul>
          {items.map((item, index) => (
            <li key={`${index}-${item.slice(0, 20)}`}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">当前本地产物未提供该类条目。</p>
      )}
    </div>
  );
}

function TagList({ items, emptyText }: { items: string[]; emptyText: string }) {
  if (items.length === 0) {
    return <p className="muted">{emptyText}</p>;
  }
  return (
    <div className="pill-row compact">
      {items.map((item) => (
        <span key={item} className="pill">
          {item}
        </span>
      ))}
    </div>
  );
}

function RiskList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) {
    return null;
  }
  return (
    <div className="resume-risk-list">
      <strong>{title}</strong>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
