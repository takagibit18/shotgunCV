import React from "react";
import Link from "next/link";

import { AppShell } from "../AppShell";
import { getRunsDir } from "../../lib/runs";
import { UploadForm } from "./UploadForm";


export default function UploadPage() {
  return (
    <AppShell active="resume" eyebrow="简历优化 / 创建草稿" freshnessText="本地数据">
      <main className="app-shell operational-shell">
      <Link href="/" className="backlink">
        {"返回运行列表"}
      </Link>

      <section className="page-header detail-header">
        <div>
          <p className="eyebrow">{"三步创建草稿"}</p>
          <h1 className="page-title">{"创建投递草稿"}</h1>
          <p className="hero-copy">
            {"将 CV、补充材料和 JD 输入整理为可复现的 run 草稿。Web 只负责落盘和元数据，不解析正文，也不直接承载业务判断。"}
          </p>
        </div>
        <span className="status-chip info">{"仅创建草稿"}</span>
      </section>

      <section className="section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">{"Draft workflow"}</p>
            <h2>{"新建 run 草稿"}</h2>
          </div>
          <span className="status-chip">{"本地单用户"}</span>
        </div>
        <UploadForm />
        <div className="detail-card upload-note">
          <h3>{"落盘边界"}</h3>
          <p className="mono">{getRunsDir()}</p>
          <p>{"草稿会写入 input_files/、ingest/upload_manifest.json 和 config/run_config.json。后续请使用页面返回的 shotguncv run 命令执行 pipeline。"}</p>
        </div>
      </section>
      </main>
    </AppShell>
  );
}
