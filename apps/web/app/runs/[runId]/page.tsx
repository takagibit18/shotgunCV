import React from "react";
import Link from "next/link";

import { loadRunDetail } from "../../../lib/runs";


type PageProps = {
  params: Promise<{ runId: string }>;
};

const STAGE_LABELS: Record<string, string> = {
  ingest: "\u5bfc\u5165",
  analyze: "\u5206\u6790",
  generate: "\u751f\u6210",
  evaluate: "\u8bc4\u4f30",
  plan: "\u8ba1\u5212",
  report: "\u62a5\u544a",
};


export default async function RunPage({ params }: PageProps) {
  const resolvedParams = await params;
  const detail = await loadRunDetail(resolvedParams.runId);

  return (
    <main>
      <Link href="/" className="backlink">
        {"\u8fd4\u56de\u8fd0\u884c\u5217\u8868"}
      </Link>

      <section className="hero">
        <p className="eyebrow">{detail.label || "\u8fd0\u884c\u8be6\u60c5"}</p>
        <h1 className="page-title">{detail.runId}</h1>
        <div className="pill-row" style={{ marginTop: 18 }}>
          <span className="pill">
            {"\u5206\u6790\u5668\uff1a"}
            {detail.analyzerProvider}
          </span>
          <span className="pill">
            {"\u751f\u6210\u5668\uff1a"}
            {detail.generatorProvider}
          </span>
          <span className="pill">
            {"\u8bc4\u5ba1\u5668\uff1a"}
            {detail.judgeProvider}
          </span>
          <span className="pill">
            {"\u89c4\u5212\u5668\uff1a"}
            {detail.plannerProvider}
          </span>
          {detail.completedStages.map((stage) => (
            <span key={stage} className="pill">
              {STAGE_LABELS[stage] ?? stage}
            </span>
          ))}
        </div>
        <p style={{ marginTop: 18 }}>
          <Link href={`/runs/${detail.runId}/report`} className="backlink">
            {"\u6253\u5f00\u62a5\u544a"}
          </Link>
        </p>
      </section>

      <section className="section">
        <h2>{"\u5206\u6790\u9636\u6bb5"}</h2>
        {detail.analyze.isComplete && detail.analyze.candidate ? (
          <div className="detail-grid">
            <article className="detail-card">
              <h3>{"\u5019\u9009\u4eba"}</h3>
              <p className="mono">{detail.analyze.candidate.candidate_id}</p>
              <p>{detail.analyze.candidate.strengths.join(" / ")}</p>
            </article>
            <article className="detail-card">
              <h3>{"\u5c97\u4f4d\u753b\u50cf"}</h3>
              <p>
                {"\u5171 "}
                {detail.analyze.jdProfiles.length}
                {" \u6761\u5c97\u4f4d\u63cf\u8ff0"}
              </p>
              <ul>
                {detail.analyze.jdProfiles.map((jd) => (
                  <li key={jd.jd_id}>
                    {jd.title} @ {jd.company}
                  </li>
                ))}
              </ul>
            </article>
          </div>
        ) : (
          <div className="empty">{"\u9636\u6bb5\u672a\u5b8c\u6210"}</div>
        )}
      </section>

      <section className="section">
        <h2>{"\u751f\u6210\u9636\u6bb5"}</h2>
        {detail.generate.isComplete ? (
          <div className="detail-grid">
            {detail.generate.variants.map((variant) => (
              <article key={variant.variant_id} className="detail-card">
                <h3>{variant.variantDisplayName}</h3>
                <p className="pill">{variant.variantTypeDisplay}</p>
                <p className="mono">{variant.variant_id}</p>
                <p>{variant.summary}</p>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty">{"\u9636\u6bb5\u672a\u5b8c\u6210"}</div>
        )}
      </section>

      <section className="section">
        <h2>{"\u8bc4\u4f30\u9636\u6bb5"}</h2>
        {detail.evaluate.isComplete ? (
          <div className="detail-grid">
            {detail.evaluate.topVariants.map((item) => (
              <article key={`${item.jdId}-${item.variantId}`} className="detail-card">
                <h3>{item.title}</h3>
                <p>{item.variantDisplayName}</p>
                <p className="mono">{item.variantId}</p>
                <p>
                  {"\u6700\u7ec8\u5f97\u5206\uff1a"}
                  {item.overallScore.toFixed(2)}
                </p>
                <p>
                  {"\u5dee\u8ddd\u6570\u91cf\uff1a"}
                  {item.gapCount}
                </p>
                <p>
                  {"\u4e3b\u8981\u539f\u56e0\uff1a"}
                  {item.topReasons.join(" / ") || "\u672a\u8bb0\u5f55\u4e3b\u8981\u539f\u56e0"}
                </p>
              </article>
            ))}
            {detail.evaluate.explanations.map((explanation) => (
              <article key={`${explanation.jd_id}-${explanation.variant_id}-explanation`} className="detail-card">
                <h3>{buildVariantDisplayName(explanation.variant_id)}</h3>
                <p className="mono">{explanation.variant_id}</p>
                <p>
                  {"\u603b\u4f53\u8bf4\u660e\uff1a"}
                  {explanation.dimension_reasons.overall}
                </p>
                <p>
                  {"\u98ce\u9669\u6807\u8bb0\uff1a"}
                  {explanation.risk_flags.join(" / ") || "\u65e0\u98ce\u9669\u6807\u8bb0"}
                </p>
              </article>
            ))}
            {detail.evaluate.explanations.length === 0 ? (
              <article className="detail-card">
                <h3>{"\u8bc4\u4f30\u89e3\u91ca"}</h3>
                <p>
                  {"\u5f53\u524d\u8fd0\u884c\u672a\u751f\u6210\u8bc4\u4f30\u89e3\u91ca\u6587\u4ef6\uff0c\u4ecd\u53ef\u7ee7\u7eed\u9605\u8bfb\u65e7\u7248\u4ea7\u7269\u3002"}
                </p>
              </article>
            ) : null}
          </div>
        ) : (
          <div className="empty">{"\u9636\u6bb5\u672a\u5b8c\u6210"}</div>
        )}
      </section>

      <section className="section">
        <h2>{"\u8ba1\u5212\u9636\u6bb5"}</h2>
        {detail.plan.isComplete ? (
          <div className="detail-grid">
            {detail.plan.strategies.map((strategy) => (
              <article key={`${strategy.jd_id}-${strategy.recommended_variant_id}`} className="detail-card">
                <h3>{strategy.jd_id}</h3>
                <p>
                  {"\u4f18\u5148\u7ea7\uff1a"}
                  {strategy.priority_rank}
                </p>
                <p>
                  {"\u6295\u9012\u51b3\u7b56\uff1a"}
                  {strategy.apply_decision}
                </p>
                <p>
                  {"\u51b3\u7b56\u9a71\u52a8\uff1a"}
                  {strategy.decision_drivers.join(" / ")}
                </p>
                <p>
                  {"\u98ce\u9669\u63d0\u9192\uff1a"}
                  {strategy.watchouts.join(" / ")}
                </p>
                <p>
                  {"\u5efa\u8bae\u52a8\u4f5c\uff1a"}
                  {strategy.recommended_actions.join(" / ")}
                </p>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty">{"\u9636\u6bb5\u672a\u5b8c\u6210"}</div>
        )}
      </section>
    </main>
  );
}


function buildVariantDisplayName(variantId: string): string {
  if (variantId.startsWith("variant-jd-")) {
    const jdId = variantId.replace("variant-jd-", "");
    return `\u5c97\u4f4d\u5b9a\u5236\u7248\u672c\uff08${jdId}\uff09`;
  }
  if (variantId.startsWith("variant-cluster-")) {
    const cluster = variantId.replace("variant-cluster-", "");
    return `\u5c97\u4f4d\u7c07\u7248\u672c\uff08${cluster}\uff09`;
  }
  return `\u7b80\u5386\u7248\u672c\uff08${variantId}\uff09`;
}
