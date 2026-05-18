import React from "react";
import Link from "next/link";

import { AppShell } from "../AppShell";
import { getRunsDir } from "../../lib/runs";
import { UploadForm } from "./UploadForm";


export default function UploadPage() {
  return (
    <AppShell active="resume" eyebrow="简历优化 / 创建草稿" freshnessText="本地数据">
      <main className="app-shell operational-shell">
      <Link href="/runs" className="backlink">
        {"返回运行列表"}
      </Link>

      <section className="page-header detail-header">
        <div>
          <p className="eyebrow">{"三步创建草稿"}</p>
          <h1 className="page-title">{"创建投递草稿"}</h1>
          <p className="hero-copy">
            {"将简历、补充材料和岗位描述整理为可复现的投递草稿。网页只负责保存文件和基础信息，核心分析仍由本地命令行流程完成。"}
          </p>
        </div>
      </section>

      <section className="section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">{"草稿工作流"}</p>
            <h2>{"新建投递草稿"}</h2>
          </div>
        </div>
        <UploadForm />
        <div className="detail-card upload-note">
          <h3>{"数据存储位置"}</h3>
          <p className="mono">{getRunsDir()}</p>
          <p>{"草稿会保存简历文件、岗位文件、上传清单和运行配置。创建后进入详情页即可启动本地流程；需要排查时可查看高级命令。 "}</p>
        </div>
      </section>
      </main>
    </AppShell>
  );
}
