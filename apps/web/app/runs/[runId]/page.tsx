import React from "react";
import Link from "next/link";

import { loadRunDetail } from "../../../lib/runs";


type PageProps = {
  params: Promise<{ runId: string }>;
};


export default async function RunPage({ params }: PageProps) {
  const resolvedParams = await params;
  const detail = await loadRunDetail(resolvedParams.runId);

  return (
    <main>
      <Link href="/" className="backlink">
        ← Back to runs
      </Link>

      <section className="hero">
        <p className="eyebrow">{detail.label || "run detail"}</p>
        <h1 className="page-title">{detail.runId}</h1>
        <div className="pill-row" style={{ marginTop: 18 }}>
          <span className="pill">generator: {detail.generatorProvider}</span>
          <span className="pill">judge: {detail.judgeProvider}</span>
          {detail.completedStages.map((stage) => (
            <span key={stage} className="pill">
              {stage}
            </span>
          ))}
        </div>
        <p style={{ marginTop: 18 }}>
          <Link href={`/runs/${detail.runId}/report`} className="backlink">
            Open report →
          </Link>
        </p>
      </section>

      <section className="section">
        <h2>Analyze</h2>
        {detail.analyze.isComplete && detail.analyze.candidate ? (
          <div className="detail-grid">
            <article className="detail-card">
              <h3>Candidate</h3>
              <p className="mono">{detail.analyze.candidate.candidate_id}</p>
              <p>{detail.analyze.candidate.strengths.join(" / ")}</p>
            </article>
            <article className="detail-card">
              <h3>JD Profiles</h3>
              <p>{detail.analyze.jdProfiles.length} parsed job descriptions</p>
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
          <div className="empty">阶段未完成</div>
        )}
      </section>

      <section className="section">
        <h2>Generate</h2>
        {detail.generate.isComplete ? (
          <div className="detail-grid">
            {detail.generate.variants.map((variant) => (
              <article key={variant.variant_id} className="detail-card">
                <h3>{variant.variant_id}</h3>
                <p className="pill">{variant.variant_type}</p>
                <p>{variant.summary}</p>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty">阶段未完成</div>
        )}
      </section>

      <section className="section">
        <h2>Evaluate</h2>
        {detail.evaluate.isComplete ? (
          <div className="detail-grid">
            {detail.evaluate.topVariants.map((item) => (
              <article key={`${item.jdId}-${item.variantId}`} className="detail-card">
                <h3>{item.title}</h3>
                <p className="mono">{item.variantId}</p>
                <p>overall score: {item.overallScore.toFixed(2)}</p>
                <p>gap count: {item.gapCount}</p>
                <p>top reasons: {item.topReasons.join(" / ") || "No top reasons captured"}</p>
              </article>
            ))}
            {detail.evaluate.explanations.map((explanation) => (
              <article key={`${explanation.jd_id}-${explanation.variant_id}-explanation`} className="detail-card">
                <h3>{explanation.variant_id}</h3>
                <p>overall: {explanation.dimension_reasons.overall}</p>
                <p>risk flags: {explanation.risk_flags.join(" / ") || "No risk flags"}</p>
              </article>
            ))}
            {detail.evaluate.explanations.length === 0 ? (
              <article className="detail-card">
                <h3>Ranking Explanations</h3>
                <p>No ranking explanations found for this run. Legacy artifacts are still readable.</p>
              </article>
            ) : null}
          </div>
        ) : (
          <div className="empty">阶段未完成</div>
        )}
      </section>

      <section className="section">
        <h2>Plan</h2>
        {detail.plan.isComplete ? (
          <div className="detail-grid">
            {detail.plan.strategies.map((strategy) => (
              <article key={`${strategy.jd_id}-${strategy.recommended_variant_id}`} className="detail-card">
                <h3>{strategy.jd_id}</h3>
                <p>priority: {strategy.priority_rank}</p>
                <p>decision: {strategy.apply_decision}</p>
                <p>drivers: {strategy.decision_drivers.join(" / ")}</p>
                <p>watchouts: {strategy.watchouts.join(" / ")}</p>
                <p>recommended actions: {strategy.recommended_actions.join(" / ")}</p>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty">阶段未完成</div>
        )}
      </section>
    </main>
  );
}
