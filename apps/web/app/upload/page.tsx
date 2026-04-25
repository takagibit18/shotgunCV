import React from "react";
import Link from "next/link";

import { getRunsDir } from "../../lib/runs";
import { UploadForm } from "./UploadForm";


export default function UploadPage() {
  return (
    <main className="app-shell">
      <Link href="/" className="backlink">
        {"返回运行列表"}
      </Link>

      <section className="workspace-hero">
        <div>
          <p className="eyebrow">{"本地上传"}</p>
          <h1 className="page-title">{"Create draft run"}</h1>
          <p className="hero-copy">
            {"上传的 CV 和 JD 文件只会落盘到本机 runs 目录；Web 仅创建草稿，不解析正文，也不触发 pipeline。"}
          </p>
        </div>
        <span className="status-chip">{"Draft only"}</span>
      </section>

      <section className="section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">{"上传输入"}</p>
            <h2>{"新建 run 草稿"}</h2>
          </div>
          <span className="status-chip">{"Local single-user"}</span>
        </div>
        <UploadForm />
        <div className="detail-card upload-note">
          <h3>{"落盘边界"}</h3>
          <p className="mono">{getRunsDir()}</p>
          <p>{"草稿会写入 input_files/、ingest/upload_manifest.json 和 config/run_config.json。后续请使用页面返回的 shotguncv run 命令执行 pipeline。"}</p>
        </div>
      </section>
    </main>
  );
}
