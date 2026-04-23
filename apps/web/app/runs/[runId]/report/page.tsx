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
        {"\u8fd4\u56de\u8fd0\u884c\u8be6\u60c5"}
      </Link>

      <section className="hero">
        <p className="eyebrow">{"\u8fd0\u884c\u62a5\u544a"}</p>
        <h1 className="page-title">{resolvedParams.runId}</h1>
      </section>

      <section className="section">
        {report ? (
          <div className="markdown">
            <ReactMarkdown>{report.markdown}</ReactMarkdown>
          </div>
        ) : (
          <div className="empty">{"\u9636\u6bb5\u672a\u5b8c\u6210"}</div>
        )}
      </section>
    </main>
  );
}
