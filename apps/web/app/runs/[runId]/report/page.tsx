import React from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";

import { loadRunReport } from "../../../../lib/runs";


type PageProps = {
  params: Promise<{ runId: string }>;
};


export default async function ReportPage({ params }: PageProps) {
  const resolvedParams = await params;
  const report = await loadRunReport(resolvedParams.runId);

  return (
    <main>
      <Link href={`/runs/${resolvedParams.runId}`} className="backlink">
        ← Back to run detail
      </Link>

      <section className="hero">
        <p className="eyebrow">Run Report</p>
        <h1 className="page-title">{resolvedParams.runId}</h1>
      </section>

      <section className="section">
        {report ? (
          <div className="markdown">
            <ReactMarkdown>{report.markdown}</ReactMarkdown>
          </div>
        ) : (
          <div className="empty">阶段未完成</div>
        )}
      </section>
    </main>
  );
}
