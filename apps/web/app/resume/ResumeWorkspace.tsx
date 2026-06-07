"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import type { ResumeWorkspaceConstraint, ResumeWorkspaceRow } from "../../lib/resume";
import type { CustomizedResumeDocument, ResumeEntry } from "../../lib/types";
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

type ResumePreviewModel = ResumeWorkspaceRow["generatedResumes"][number];

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

  const generatedRows = rows.filter((row) => row.generatedResumeCount > 0);
  if (generatedRows.length === 0) {
    const reviewRow =
      rows.find((row) => row.evidenceConstraintCount > 0 && (row.preflightStatus === "blocked" || row.preflightStatus === "needs_review")) ??
      rows.find((row) => row.status === "failed") ??
      rows[0];
    return (
      <section className="resume-studio empty-resume-studio" aria-label="简历生成状态">
        <div className="empty-state">
          <h3>暂无可预览或导出的简历</h3>
          <p>已有投递任务，但还没有完整简历产物。先处理证据门槛或重新运行失败任务，生成完成后这里会出现预览、复制和导出入口。</p>
          <div className="row-actions">
            <Link href={reviewRow?.detailHref ?? "/runs"} className="primary-link">
              处理当前任务
            </Link>
            <Link href="/runs" className="secondary-link">
              查看运行队列
            </Link>
            <Link href="/upload" className="secondary-link">
              补充材料
            </Link>
          </div>
        </div>
        {reviewRow ? <EvidencePanel row={reviewRow} /> : null}
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
  resume: ResumePreviewModel;
  selectedResumeId: string;
  onSelectResume: (resumeId: string) => void;
}) {
  const [draftDocument, setDraftDocument] = useState<CustomizedResumeDocument>(resume.previewDocument);
  const [fieldStatuses, setFieldStatuses] = useState(resume.fieldStatuses);

  useEffect(() => {
    setDraftDocument(resume.previewDocument);
    setFieldStatuses(resume.fieldStatuses);
  }, [resume.resumeId, resume.previewDocument, resume.fieldStatuses]);

  const draftMarkdown = useMemo(() => buildMarkdownFromDraft(draftDocument), [draftDocument]);

  async function persist(nextDocument: CustomizedResumeDocument, nextStatuses = fieldStatuses) {
    await fetch(`/api/runs/${encodeURIComponent(row.runId)}/resume-edits`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        resumeId: resume.resumeId,
        documentPatch: nextDocument,
        fieldStatuses: nextStatuses,
      }),
    });
  }

  function updateDocument(nextDocument: CustomizedResumeDocument, persistNow = false) {
    setDraftDocument(nextDocument);
    if (persistNow) {
      void persist(nextDocument);
    }
  }

  function setFieldStatus(path: string, status: "confirmed" | "to_verify") {
    const nextStatuses = { ...fieldStatuses, [path]: status };
    setFieldStatuses(nextStatuses);
    void persist(draftDocument, nextStatuses);
  }

  function restoreSystemVersion() {
    setDraftDocument(resume.systemDocument);
    setFieldStatuses({});
    void fetch(`/api/runs/${encodeURIComponent(row.runId)}/resume-edits`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resumeId: resume.resumeId, reset: true }),
    });
  }

  return (
    <article className="resume-live-preview">
      <div className="resume-preview-toolbar">
        <div>
          <span className="section-kicker">实时简历预览</span>
          <h2>{resume.displayName}</h2>
          <p>{resume.targetLabel}</p>
        </div>
        <div className="row-actions">
          <CopyMarkdownButton markdown={draftMarkdown} />
          <button className="secondary-link" type="button" onClick={restoreSystemVersion}>
            <Icon name="reset" />
            重置为系统生成版本
          </button>
          {resume.isDeliverable ? (
            <>
              <button className="primary-link" type="button" data-export-kind="pdf" onClick={() => window.print()}>
                <Icon name="document" />
                导出 PDF
              </button>
              <a
                className="secondary-link"
                href={`data:text/markdown;charset=utf-8,${encodeURIComponent(draftMarkdown)}`}
                download={resume.exportFileName}
                data-export-kind="markdown"
              >
                <Icon name="save" />
                导出 Markdown
              </a>
            </>
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

      <div className="resume-json-workspace">
        <ResumeFieldEditor
          document={draftDocument}
          systemDocument={resume.systemDocument}
          fieldStatuses={fieldStatuses}
          onChange={updateDocument}
          onBlur={() => void persist(draftDocument)}
          onSetFieldStatus={setFieldStatus}
        />
        <ResumePaper document={draftDocument} fieldStatuses={fieldStatuses} resume={resume} />
      </div>

      <section className="resume-provenance" aria-label="简历来源与风险">
        <div className="resume-info-title">
          <Icon name="check-square" />
          <h3>证据来源</h3>
        </div>
        <p>{resume.sourceLabel}</p>
        <p>候选人：{draftDocument.basics.full_name}</p>
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
        <section className="resume-legacy-panel">
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
  const uniqueItems = Array.from(new Set(items.map((item) => item.trim()).filter(Boolean)));
  if (uniqueItems.length === 0) {
    return <p className="muted">{emptyText}</p>;
  }
  return (
    <div className="pill-row compact">
      {uniqueItems.map((item, index) => (
        <span key={`${index}-${item}`} className="pill">
          {item}
        </span>
      ))}
    </div>
  );
}

function RiskList({ title, items }: { title: string; items: string[] }) {
  const uniqueItems = Array.from(new Set(items.map((item) => item.trim()).filter(Boolean)));
  if (uniqueItems.length === 0) {
    return null;
  }
  return (
    <div className="resume-risk-list">
      <strong>{title}</strong>
      <ul>
        {uniqueItems.map((item, index) => (
          <li key={`${index}-${item}`}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function ResumeFieldEditor({
  document,
  systemDocument,
  fieldStatuses,
  onChange,
  onBlur,
  onSetFieldStatus,
}: {
  document: CustomizedResumeDocument;
  systemDocument: CustomizedResumeDocument;
  fieldStatuses: Record<string, "confirmed" | "to_verify">;
  onChange: (document: CustomizedResumeDocument, persistNow?: boolean) => void;
  onBlur: () => void;
  onSetFieldStatus: (path: string, status: "confirmed" | "to_verify") => void;
}) {
  function patch(next: Partial<CustomizedResumeDocument>, persistNow = false) {
    onChange({ ...document, ...next }, persistNow);
  }

  function updateBasics(field: keyof CustomizedResumeDocument["basics"], value: string) {
    patch({ basics: { ...document.basics, [field]: value } });
  }

  function updateEntry(
    collection: "experiences" | "projects" | "education",
    index: number,
    nextEntry: ResumeEntry,
  ) {
    const next = [...document[collection]];
    next[index] = nextEntry;
    patch({ [collection]: next } as Partial<CustomizedResumeDocument>, true);
  }

  function removeEntry(collection: "experiences" | "projects" | "education", index: number) {
    patch({ [collection]: document[collection].filter((_, itemIndex) => itemIndex !== index) } as Partial<CustomizedResumeDocument>, true);
  }

  function addEntry(collection: "experiences" | "projects" | "education", title: string) {
    const nextEntry: ResumeEntry = {
      id: `${collection}-${Date.now()}`,
      title,
      organization: "",
      period: "",
      bullets: [""],
    };
    patch({ [collection]: [...document[collection], nextEntry] } as Partial<CustomizedResumeDocument>, true);
  }

  return (
    <aside className="resume-field-editor" aria-label="字段编辑器">
      <div className="resume-editor-heading">
        <span className="section-kicker">字段编辑器</span>
        <strong>{document.basics.full_name}</strong>
      </div>

      <FieldText
        label="姓名"
        path="document.basics.full_name"
        value={document.basics.full_name}
        status={fieldStatuses["document.basics.full_name"]}
        onChange={(value) => updateBasics("full_name", value)}
        onBlur={onBlur}
        onSetFieldStatus={onSetFieldStatus}
        onRestore={() => updateBasics("full_name", systemDocument.basics.full_name)}
      />
      <FieldText
        label="标题"
        path="document.basics.headline"
        value={document.basics.headline ?? ""}
        status={fieldStatuses["document.basics.headline"]}
        onChange={(value) => updateBasics("headline", value)}
        onBlur={onBlur}
        onSetFieldStatus={onSetFieldStatus}
        onRestore={() => updateBasics("headline", systemDocument.basics.headline ?? "")}
      />
      <FieldTextArea
        label="摘要"
        path="document.summary"
        value={document.summary}
        status={fieldStatuses["document.summary"]}
        onChange={(value) => patch({ summary: value })}
        onBlur={onBlur}
        onSetFieldStatus={onSetFieldStatus}
        onRestore={() => patch({ summary: systemDocument.summary }, true)}
      />

      <ArrayFieldEditor
        label="技能"
        items={document.skills}
        basePath="document.skills"
        fieldStatuses={fieldStatuses}
        onSetFieldStatus={onSetFieldStatus}
        onChange={(items) => patch({ skills: items }, true)}
      />
      <EntryFieldEditor
        label="经历"
        collection="experiences"
        entries={document.experiences}
        fieldStatuses={fieldStatuses}
        onSetFieldStatus={onSetFieldStatus}
        onChange={updateEntry}
        onRemove={removeEntry}
        onAdd={() => addEntry("experiences", "Relevant Experience")}
      />
      <EntryFieldEditor
        label="项目"
        collection="projects"
        entries={document.projects}
        fieldStatuses={fieldStatuses}
        onSetFieldStatus={onSetFieldStatus}
        onChange={updateEntry}
        onRemove={removeEntry}
        onAdd={() => addEntry("projects", "Relevant Project")}
      />
      <EntryFieldEditor
        label="教育"
        collection="education"
        entries={document.education}
        fieldStatuses={fieldStatuses}
        onSetFieldStatus={onSetFieldStatus}
        onChange={updateEntry}
        onRemove={removeEntry}
        onAdd={() => addEntry("education", "Education")}
      />
      <ArrayFieldEditor
        label="证书"
        items={document.certifications}
        basePath="document.certifications"
        fieldStatuses={fieldStatuses}
        onSetFieldStatus={onSetFieldStatus}
        onChange={(items) => patch({ certifications: items }, true)}
      />
    </aside>
  );
}

function FieldText({
  label,
  path,
  value,
  status,
  onChange,
  onBlur,
  onSetFieldStatus,
  onRestore,
}: {
  label: string;
  path: string;
  value: string;
  status?: "confirmed" | "to_verify";
  onChange: (value: string) => void;
  onBlur: () => void;
  onSetFieldStatus: (path: string, status: "confirmed" | "to_verify") => void;
  onRestore: () => void;
}) {
  return (
    <label className="resume-edit-field">
      <FieldLabel label={label} path={path} status={status} onSetFieldStatus={onSetFieldStatus} onRestore={onRestore} />
      <input value={value} onChange={(event) => onChange(event.currentTarget.value)} onBlur={onBlur} />
    </label>
  );
}

function FieldTextArea(props: Parameters<typeof FieldText>[0]) {
  return (
    <label className="resume-edit-field">
      <FieldLabel
        label={props.label}
        path={props.path}
        status={props.status}
        onSetFieldStatus={props.onSetFieldStatus}
        onRestore={props.onRestore}
      />
      <textarea
        value={props.value}
        rows={4}
        onChange={(event) => props.onChange(event.currentTarget.value)}
        onBlur={props.onBlur}
      />
    </label>
  );
}

function FieldLabel({
  label,
  path,
  status,
  onSetFieldStatus,
  onRestore,
}: {
  label: string;
  path: string;
  status?: "confirmed" | "to_verify";
  onSetFieldStatus: (path: string, status: "confirmed" | "to_verify") => void;
  onRestore: () => void;
}) {
  return (
    <span className="resume-field-label">
      <span>{label}</span>
      {status ? <StatusText status={status} /> : null}
      <button type="button" title="标记已确认" onClick={() => onSetFieldStatus(path, "confirmed")}>
        <Icon name="check-square" />
      </button>
      <button type="button" title="标记待核实" onClick={() => onSetFieldStatus(path, "to_verify")}>
        <Icon name="alert-triangle" />
      </button>
      <button type="button" title="恢复系统版本" onClick={onRestore}>
        <Icon name="reset" />
      </button>
    </span>
  );
}

function ArrayFieldEditor({
  label,
  items,
  basePath,
  fieldStatuses,
  onSetFieldStatus,
  onChange,
}: {
  label: string;
  items: string[];
  basePath: string;
  fieldStatuses: Record<string, "confirmed" | "to_verify">;
  onSetFieldStatus: (path: string, status: "confirmed" | "to_verify") => void;
  onChange: (items: string[]) => void;
}) {
  return (
    <div className="resume-edit-group">
      <div className="resume-edit-group-title">
        <strong>{label}</strong>
        <button type="button" onClick={() => onChange([...items, ""])}>
          添加
        </button>
      </div>
      {items.map((item, index) => {
        const path = `${basePath}.${index}`;
        return (
          <label className="resume-array-field" key={`${path}-${index}`}>
            <FieldLabel
              label={`${label} ${index + 1}`}
              path={path}
              status={fieldStatuses[path]}
              onSetFieldStatus={onSetFieldStatus}
              onRestore={() => onChange(items.filter((_, itemIndex) => itemIndex !== index))}
            />
            <input
              value={item}
              onChange={(event) => onChange(items.map((current, itemIndex) => (itemIndex === index ? event.currentTarget.value : current)))}
            />
          </label>
        );
      })}
    </div>
  );
}

function EntryFieldEditor({
  label,
  collection,
  entries,
  fieldStatuses,
  onSetFieldStatus,
  onChange,
  onRemove,
  onAdd,
}: {
  label: string;
  collection: "experiences" | "projects" | "education";
  entries: ResumeEntry[];
  fieldStatuses: Record<string, "confirmed" | "to_verify">;
  onSetFieldStatus: (path: string, status: "confirmed" | "to_verify") => void;
  onChange: (collection: "experiences" | "projects" | "education", index: number, entry: ResumeEntry) => void;
  onRemove: (collection: "experiences" | "projects" | "education", index: number) => void;
  onAdd: () => void;
}) {
  return (
    <div className="resume-edit-group">
      <div className="resume-edit-group-title">
        <strong>{label}</strong>
        <button type="button" onClick={onAdd}>
          添加
        </button>
      </div>
      {entries.map((entry, entryIndex) => (
        <div className="resume-entry-editor" key={entry.id || `${collection}-${entryIndex}`}>
          <input
            aria-label={`${label}标题`}
            value={entry.title}
            onChange={(event) => onChange(collection, entryIndex, { ...entry, title: event.currentTarget.value })}
          />
          <input
            aria-label={`${label}组织`}
            value={entry.organization ?? ""}
            onChange={(event) => onChange(collection, entryIndex, { ...entry, organization: event.currentTarget.value })}
          />
          <input
            aria-label={`${label}时间`}
            value={entry.period ?? ""}
            onChange={(event) => onChange(collection, entryIndex, { ...entry, period: event.currentTarget.value })}
          />
          <ArrayFieldEditor
            label={`${label} bullet`}
            items={entry.bullets}
            basePath={`document.${collection}.${entryIndex}.bullets`}
            fieldStatuses={fieldStatuses}
            onSetFieldStatus={onSetFieldStatus}
            onChange={(bullets) => onChange(collection, entryIndex, { ...entry, bullets })}
          />
          <button type="button" className="resume-remove-button" onClick={() => onRemove(collection, entryIndex)}>
            删除{label}
          </button>
        </div>
      ))}
    </div>
  );
}

function ResumePaper({
  document,
  fieldStatuses,
  resume,
}: {
  document: CustomizedResumeDocument;
  fieldStatuses: Record<string, "confirmed" | "to_verify">;
  resume: ResumePreviewModel;
}) {
  return (
    <section className="resume-paper" aria-label="完整简历正文">
      <header className="resume-paper-header">
        <h1>{document.basics.full_name}</h1>
        {document.basics.headline ? <p>{document.basics.headline}</p> : null}
        <small>{[document.basics.location, document.basics.email, document.basics.phone].filter(Boolean).join(" · ")}</small>
      </header>
      <PaperSection title="摘要" status={fieldStatuses["document.summary"]}>
        <p>{document.summary}</p>
      </PaperSection>
      <PaperSection title="技能">
        <div className="resume-paper-skill-list">
          {document.skills.map((skill, index) => (
            <span key={`${skill}-${index}`}>
              {skill}
              <StatusText status={fieldStatuses[`document.skills.${index}`]} />
            </span>
          ))}
        </div>
      </PaperSection>
      <EntryPaperSection title="经历" collection="experiences" entries={document.experiences} fieldStatuses={fieldStatuses} />
      <EntryPaperSection title="项目" collection="projects" entries={document.projects} fieldStatuses={fieldStatuses} />
      <EntryPaperSection title="教育" collection="education" entries={document.education} fieldStatuses={fieldStatuses} />
      {document.certifications.length > 0 ? (
        <PaperSection title="证书">
          <ul>
            {document.certifications.map((item, index) => (
              <li key={`${item}-${index}`}>{item}</li>
            ))}
          </ul>
        </PaperSection>
      ) : null}
      <footer className="resume-paper-footer">
        <span>{resume.sourceLabel}</span>
        <span>{resume.status === "blocked" ? "复核版" : "JSON 画布导出版"}</span>
      </footer>
    </section>
  );
}

function PaperSection({
  title,
  status,
  children,
}: {
  title: string;
  status?: "confirmed" | "to_verify";
  children: React.ReactNode;
}) {
  return (
    <section className="resume-paper-section">
      <h2>
        {title}
        <StatusText status={status} />
      </h2>
      {children}
    </section>
  );
}

function EntryPaperSection({
  title,
  collection,
  entries,
  fieldStatuses,
}: {
  title: string;
  collection: "experiences" | "projects" | "education";
  entries: ResumeEntry[];
  fieldStatuses: Record<string, "confirmed" | "to_verify">;
}) {
  if (entries.length === 0) {
    return null;
  }
  return (
    <PaperSection title={title}>
      {entries.map((entry, entryIndex) => (
        <article className="resume-paper-entry" key={entry.id || `${collection}-${entryIndex}`}>
          <h3>{[entry.title, entry.organization, entry.period].filter(Boolean).join(" · ")}</h3>
          <ul>
            {entry.bullets.map((bullet, bulletIndex) => (
              <li key={`${entry.id}-${bulletIndex}`}>
                {bullet}
                <StatusText status={fieldStatuses[`document.${collection}.${entryIndex}.bullets.${bulletIndex}`]} />
              </li>
            ))}
          </ul>
        </article>
      ))}
    </PaperSection>
  );
}

function StatusText({ status }: { status?: "confirmed" | "to_verify" }) {
  if (status === "confirmed") {
    return <small className="resume-field-status confirmed">已确认</small>;
  }
  if (status === "to_verify") {
    return <small className="resume-field-status verify">待核实</small>;
  }
  return null;
}

function buildMarkdownFromDraft(document: CustomizedResumeDocument): string {
  const chunks = [
    `# ${document.basics.full_name}`,
    document.basics.headline ?? "",
    document.summary ? `## 摘要\n${document.summary}` : "",
    document.skills.length ? `## 技能\n${document.skills.map((skill) => `- ${skill}`).join("\n")}` : "",
    ...document.experiences.map((entry) => buildMarkdownEntry("经历", entry)),
    ...document.projects.map((entry) => buildMarkdownEntry("项目", entry)),
    ...document.education.map((entry) => buildMarkdownEntry("教育", entry)),
    document.certifications.length ? `## 证书\n${document.certifications.map((item) => `- ${item}`).join("\n")}` : "",
  ];
  return chunks.filter((chunk): chunk is string => Boolean(chunk.trim())).join("\n\n");
}

function buildMarkdownEntry(title: string, entry: ResumeEntry): string {
  const heading = [entry.title, entry.organization, entry.period].filter(Boolean).join(" · ");
  return `## ${title}：${heading || "未命名条目"}\n${entry.bullets.map((bullet) => `- ${bullet}`).join("\n")}`;
}
