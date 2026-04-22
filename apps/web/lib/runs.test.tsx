import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";

import HomePage from "../app/page";
import RunPage from "../app/runs/[runId]/page";
import ReportPage from "../app/runs/[runId]/report/page";
import { loadRunDetail, listRuns, loadRunReport } from "./runs";


describe("run viewer data loading", () => {
  afterEach(() => {
    delete process.env.SHOTGUNCV_RUNS_DIR;
  });

  it("lists runs with completed stages and provider labels", async () => {
    const runsDir = await createTempRunsDir();
    await createIncompleteRun(runsDir, "demo");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const runs = await listRuns();

    expect(runs).toHaveLength(1);
    expect(runs[0]).toMatchObject({
      runId: "demo",
      completedStages: ["ingest", "analyze"],
      generatorProvider: "deterministic",
      judgeProvider: "deterministic",
      label: "demo-run",
    });
  });

  it("loads incomplete run detail without crashing and marks missing stages", async () => {
    const runsDir = await createTempRunsDir();
    await createIncompleteRun(runsDir, "demo");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const detail = await loadRunDetail("demo");

    expect(detail.runId).toBe("demo");
    expect(detail.generate.isComplete).toBe(false);
    expect(detail.evaluate.isComplete).toBe(false);
    expect(detail.plan.isComplete).toBe(false);
    expect(detail.analyze.candidate?.candidate_id).toBe("cand-001");
  });

  it("loads completed run detail with score and strategy summaries", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-full");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const detail = await loadRunDetail("demo-full");

    expect(detail.generate.isComplete).toBe(true);
    expect(detail.evaluate.isComplete).toBe(true);
    expect(detail.plan.isComplete).toBe(true);
    expect(detail.evaluate.topVariants[0]).toMatchObject({
      jdId: "jd-001",
      variantId: "variant-jd-jd-001",
      overallScore: 0.81,
      gapCount: 1,
      topReasons: ["Strong evidence binding", "Good keyword coverage"],
    });
    expect(detail.plan.strategies[0]).toMatchObject({
      jd_id: "jd-001",
      apply_decision: "apply",
      watchouts: ["No large-scale benchmark ownership"],
    });
  });

  it("marks evaluate stage complete for legacy runs without ranking explanations", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-legacy", { includeExplanations: false });
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const detail = await loadRunDetail("demo-legacy");

    expect(detail.evaluate.isComplete).toBe(true);
    expect(detail.evaluate.topVariants[0]).toMatchObject({
      jdId: "jd-001",
      variantId: "variant-jd-jd-001",
      topReasons: ["Strong evidence binding", "Good keyword coverage"],
    });
    expect(detail.evaluate.explanations).toEqual([]);
  });

  it("loads report markdown for complete run and returns null when report missing", async () => {
    const runsDir = await createTempRunsDir();
    await createIncompleteRun(runsDir, "demo");
    await createCompleteRun(runsDir, "demo-full");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const missingReport = await loadRunReport("demo");
    const existingReport = await loadRunReport("demo-full");

    expect(missingReport).toBeNull();
    expect(existingReport?.markdown).toContain("# ShotgunCV v0.2.0 Explainable Ranking Summary");
  });
});


describe("run viewer pages", () => {
  afterEach(() => {
    delete process.env.SHOTGUNCV_RUNS_DIR;
  });

  it("renders the run index page", async () => {
    const runsDir = await createTempRunsDir();
    await createIncompleteRun(runsDir, "demo");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await HomePage());

    expect(html).toContain("ShotgunCV Run Viewer");
    expect(html).toContain("demo");
    expect(html).toContain("ingest");
  });

  it("renders run detail page with incomplete-stage messaging", async () => {
    const runsDir = await createTempRunsDir();
    await createIncompleteRun(runsDir, "demo");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId: "demo" }) }));

    expect(html).toContain("Generate");
    expect(html).toContain("阶段未完成");
  });

  it("renders explanation empty state for legacy evaluate artifacts", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-legacy", { includeExplanations: false });
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId: "demo-legacy" }) }));

    expect(html).toContain("Ranking Explanations");
    expect(html).toContain("Legacy artifacts are still readable.");
  });

  it("renders report page markdown for complete run", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-full");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await ReportPage({ params: Promise.resolve({ runId: "demo-full" }) }));

    expect(html).toContain("ShotgunCV v0.2.0 Explainable Ranking Summary");
    expect(html).toContain("LLM Product Engineer");
  });
});


async function createTempRunsDir(): Promise<string> {
  return mkdtemp(path.join(tmpdir(), "shotguncv-runs-"));
}


async function createIncompleteRun(runsDir: string, runId: string): Promise<void> {
  const runDir = path.join(runsDir, runId)
  await mkdir(path.join(runDir, "config"), { recursive: true });
  await mkdir(path.join(runDir, "ingest"), { recursive: true });
  await mkdir(path.join(runDir, "analyze"), { recursive: true });

  await writeJson(path.join(runDir, "config", "run_config.json"), {
    generator: { provider: "deterministic", model: "" },
    judge: { provider: "deterministic", model: "" },
    openai: { base_url: null, api_key_env: "OPENAI_API_KEY" },
    run_metadata: { label: "demo-run" },
  });
  await writeJson(path.join(runDir, "ingest", "manifest.json"), {
    candidate_id: "cand-001",
    jd_inputs: [{ source_type: "file", source_value: "fixtures/jds/sample_batch.txt" }],
  });
  await writeJson(path.join(runDir, "analyze", "candidate_profile.json"), {
    candidate_id: "cand-001",
    base_resume_path: "fixtures/candidates/base_resume.md",
    experiences: ["围绕 LLM 辅助工作流构建过内部工具"],
    projects: [],
    skills: ["LLM workflows"],
    industry_tags: ["AI tooling"],
    strengths: ["围绕 LLM 辅助工作流构建过内部工具"],
    constraints: ["No explicit production ML platform ownership yet"],
    preferences: ["Product-oriented AI roles"],
  });
  await writeJson(path.join(runDir, "analyze", "jd_profiles.json"), [
    {
      jd_id: "jd-001",
      title: "LLM Product Engineer",
      company: "Example AI",
      cluster: "ai-product",
      responsibilities: ["Build evaluation pipelines"],
      requirements: ["Python"],
      keywords: ["evaluation", "python"],
      seniority: "mid",
      bonuses: [],
      risk_signals: ["Prompt quality will be probed"],
      source_type: "file",
      source_value: "fixtures/jds/sample_batch.txt",
    },
  ]);
}


async function createCompleteRun(
  runsDir: string,
  runId: string,
  options?: { includeExplanations?: boolean },
): Promise<void> {
  const includeExplanations = options?.includeExplanations ?? true;
  const runDir = path.join(runsDir, runId)
  await createIncompleteRun(runsDir, runId);
  await mkdir(path.join(runDir, "generate"), { recursive: true });
  await mkdir(path.join(runDir, "evaluate"), { recursive: true });
  await mkdir(path.join(runDir, "plan"), { recursive: true });
  await mkdir(path.join(runDir, "report"), { recursive: true });

  await writeJson(path.join(runDir, "generate", "resume_variants.json"), [
    {
      variant_id: "variant-cluster-ai-product",
      variant_type: "cluster",
      cluster: "ai-product",
      target_jd_ids: ["jd-001", "jd-002"],
      summary: "Cluster summary",
      emphasized_strengths: ["LLM workflow delivery"],
      stretch_points: ["metrics"],
      source_resume_path: "fixtures/candidates/base_resume.md",
    },
    {
      variant_id: "variant-jd-jd-001",
      variant_type: "jd-specific",
      cluster: "ai-product",
      target_jd_ids: ["jd-001"],
      summary: "JD summary 1",
      emphasized_strengths: ["evaluation"],
      stretch_points: ["metrics"],
      source_resume_path: "fixtures/candidates/base_resume.md",
    },
  ]);
  await writeJson(path.join(runDir, "evaluate", "scorecards.json"), [
    {
      jd_id: "jd-001",
      variant_id: "variant-jd-jd-001",
      fit_score: 0.82,
      ats_score: 0.79,
      evidence_score: 0.76,
      stretch_score: 0.68,
      gap_risk_score: 0.42,
      rewrite_cost_score: 0.25,
      overall_score: 0.81,
      ranking_version: "v0.2.0-explainable-ranking",
      judge_rationale: "Strong fit with manageable catch-up.",
    },
  ]);
  if (includeExplanations) {
    await writeJson(path.join(runDir, "evaluate", "ranking_explanations.json"), [
      {
        jd_id: "jd-001",
        variant_id: "variant-jd-jd-001",
        ranking_version: "v0.2.0-explainable-ranking",
        dimension_reasons: {
          fit: "keyword coverage and evidence binding are strong",
          ats: "python and evaluation keywords are present",
          evidence: "resume bullets support emphasized strengths",
          stretch: "stretch claims remain bounded",
          gap_risk: "large-scale benchmark ownership is missing",
          rewrite_cost: "jd-specific variant needs moderate tailoring",
          overall: "Strong fit with bounded catch-up risk.",
        },
        positive_signals: ["Strong evidence binding", "Good keyword coverage"],
        risk_flags: ["No large-scale benchmark ownership"],
        evidence_refs: ["Built internal tooling for LLM workflows"],
        decision_summary: "Strong fit with bounded catch-up risk.",
      },
    ]);
  }
  await writeJson(path.join(runDir, "evaluate", "gap_maps.json"), [
    {
      jd_id: "jd-001",
      candidate_id: "cand-001",
      items: [
        {
          area: "Evaluation design",
          current_state: "Has prototype exposure",
          target_state: "Can discuss offline ranking metrics",
          priority: "high",
          catch_up_concepts: ["precision@k", "evaluation rubric"],
          weak_points: ["No large-scale benchmark ownership"],
        },
      ],
    },
  ]);
  await writeJson(path.join(runDir, "evaluate", "eval_summary.json"), [
    {
      jd_id: "jd-001",
      title: "LLM Product Engineer",
      top_variant_id: "variant-jd-jd-001",
      gap_count: 1,
      top_reasons: ["Strong evidence binding", "Good keyword coverage"],
    },
  ]);
  await writeJson(path.join(runDir, "plan", "application_strategies.json"), [
    {
      jd_id: "jd-001",
      recommended_variant_id: "variant-jd-jd-001",
      priority_rank: 1,
      apply_decision: "apply",
      reason_summary: "Strong fit with bounded catch-up risk.",
      needs_jd_specific_variant: true,
      decision_drivers: ["Strong evidence binding", "Good keyword coverage"],
      watchouts: ["No large-scale benchmark ownership"],
      recommended_actions: ["Review offline evaluation metrics before interviews."],
      catch_up_notes: ["Review offline evaluation metrics before interviews."],
    },
  ]);
  await writeFile(
    path.join(runDir, "report", "summary.md"),
    "# ShotgunCV v0.2.0 Explainable Ranking Summary\n\n## Ranked Application Strategy\n\n### 1. LLM Product Engineer @ Example AI\n\n- Top Evidence: Built internal tooling for LLM workflows\n",
    "utf-8",
  );
}


async function writeJson(filePath: string, payload: unknown): Promise<void> {
  await writeFile(filePath, JSON.stringify(payload, null, 2), "utf-8");
}
