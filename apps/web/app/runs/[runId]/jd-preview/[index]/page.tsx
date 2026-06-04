import React from "react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { loadRunDetail } from "../../../../../lib/runs";
import { Icon } from "../../../../AppShell";


type PageProps = {
  params: Promise<{ runId: string; index: string }>;
};


export default async function JdImagePreviewPage({ params }: PageProps) {
  const { runId, index } = await params;
  const previewIndex = Number.parseInt(index, 10);
  if (!Number.isInteger(previewIndex) || previewIndex < 0) {
    notFound();
  }

  const detail = await loadRunDetail(runId);
  const preview = detail.jdInputPreviews[previewIndex];
  if (!preview || preview.kind !== "image" || !preview.imageDataUrl) {
    notFound();
  }

  return (
    <main className="jd-image-page">
      <header className="jd-image-toolbar">
        <Link href={`/runs/${runId}`} className="backlink icon-link">
          <Icon name="chevron-left" />
          返回评估详情
        </Link>
        <div>
          <p className="eyebrow">岗位描述图片预览</p>
          <h1>{preview.label}</h1>
        </div>
      </header>
      <section className="jd-image-canvas" aria-label={`${preview.label} 大图预览`}>
        <img src={preview.imageDataUrl} alt={`${preview.label} 岗位描述图片预览`} />
      </section>
    </main>
  );
}
