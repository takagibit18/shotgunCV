"use client";

import React, { useEffect, useState } from "react";

import type { DependencyReport } from "../../lib/python-env";


type InstallState = {
  packageName: "fitz" | "pytesseract";
  message: string;
} | null;


export function DependencyPanel() {
  const [report, setReport] = useState<DependencyReport | null>(null);
  const [error, setError] = useState("");
  const [installState, setInstallState] = useState<InstallState>(null);

  async function loadReport() {
    setError("");
    const response = await fetch("/api/settings/dependencies");
    if (!response.ok) {
      setError("依赖健康检查失败。");
      return;
    }
    setReport((await response.json()) as DependencyReport);
  }

  async function installPackage(packageName: "fitz" | "pytesseract") {
    setInstallState({ packageName, message: "正在安装..." });
    const response = await fetch("/api/settings/dependencies", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ package: packageName }),
    });
    const payload = (await response.json()) as { success?: boolean; output?: string; error?: string };
    if (!response.ok || !payload.success) {
      setInstallState({ packageName, message: payload.output || payload.error || "安装失败。" });
      return;
    }
    setInstallState(null);
    await loadReport();
  }

  useEffect(() => {
    void loadReport();
  }, []);

  return (
    <section className="section settings-panel dependency-panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">运行环境依赖</p>
          <h2>Python 依赖健康检查</h2>
          <p className="section-copy">只展示可用性，不展示密钥内容。扫描件 PDF 依赖 PyMuPDF、OCR 或视觉兜底。</p>
        </div>
      </div>
      {error ? <p className="local-config-message error">{error}</p> : null}
      {!report ? <p className="muted">正在检查本地运行环境...</p> : <DependencyRows report={report} installState={installState} onInstall={installPackage} />}
    </section>
  );
}


function DependencyRows({
  report,
  installState,
  onInstall,
}: {
  report: DependencyReport;
  installState: InstallState;
  onInstall: (packageName: "fitz" | "pytesseract") => void;
}) {
  const rows = [
    { label: "Python", status: report.python.found ? "pass" : "fail", detail: report.python.path ?? "未找到" },
    { label: "shotguncv", status: report.shotguncv.importable ? "pass" : "fail", detail: report.shotguncv.importable ? "可导入" : "不可导入" },
    {
      label: "PyMuPDF/fitz",
      status: report.fitz.installed ? "pass" : "fail",
      detail: report.fitz.detail,
      packageName: "fitz" as const,
      action: "安装 PyMuPDF",
    },
    {
      label: "pytesseract",
      status: report.pytesseract.installed ? (report.tesseractExe.found ? "pass" : "warn") : "fail",
      detail: report.pytesseract.detail,
      packageName: "pytesseract" as const,
      action: "安装 pytesseract",
    },
    { label: "Tesseract", status: report.tesseractExe.found ? "pass" : "fail", detail: report.tesseractExe.detail },
    { label: "OpenAI Key", status: report.openaiKey.configured ? "pass" : "warn", detail: report.openaiKey.configured ? "已配置" : "未配置" },
  ];

  return (
    <div className="dependency-grid">
      {rows.map((row) => {
        const installing = installState?.packageName === row.packageName;
        return (
          <article className="dependency-row" key={row.label}>
            <span className={buildStatusClassName(row.status)}>{formatStatus(row.status)}</span>
            <div>
              <strong>{row.label}</strong>
              <p>{truncateDetail(row.detail)}</p>
              {installing && installState ? <p className="muted">{installState.message}</p> : null}
            </div>
            {row.packageName && row.status === "fail" ? (
              <button className="secondary-button" type="button" disabled={Boolean(installState)} onClick={() => onInstall(row.packageName)}>
                {installing ? "正在安装..." : row.action}
              </button>
            ) : null}
          </article>
        );
      })}
    </div>
  );
}


function buildStatusClassName(status: string): string {
  if (status === "pass") {
    return "status-chip success";
  }
  if (status === "fail") {
    return "status-chip danger";
  }
  return "status-chip warning";
}


function formatStatus(status: string): string {
  if (status === "pass") {
    return "可用";
  }
  if (status === "fail") {
    return "缺失";
  }
  return "需检查";
}


function truncateDetail(detail: string): string {
  return detail.length > 180 ? `${detail.slice(0, 179)}...` : detail;
}
