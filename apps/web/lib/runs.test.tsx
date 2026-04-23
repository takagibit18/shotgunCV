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
      variantDisplayName: "岗位定制版本（jd-001）",
      overallScore: 0.81,
      gapCount: 1,
      topReasons: ["证据绑定强", "关键词覆盖好"],
    });
    expect(detail.plan.strategies[0]).toMatchObject({
      jd_id: "jd-001",
      apply_decision: "apply",
      watchouts: ["缺少大规模 benchmark 经验"],
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
      topReasons: ["证据绑定强", "关键词覆盖好"],
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
    expect(existingReport?.markdown).toContain("# ShotgunCV v0.3.0 LLM Eval Summary");
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

    expect(html).toContain("ShotgunCV 运行查看器");
    expect(html).toContain("demo");
    expect(html).toContain("导入");
  });

  it("renders run detail page with incomplete-stage messaging", async () => {
    const runsDir = await createTempRunsDir();
    await createIncompleteRun(runsDir, "demo");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId: "demo" }) }));

    expect(html).toContain("生成阶段");
    expect(html).toContain("阶段未完成");
  });

  it("renders chinese variant alias as title while keeping raw id in body", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-full");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId: "demo-full" }) }));

    expect(html).toContain("岗位定制版本（jd-001）");
    expect(html).toContain("variant-jd-jd-001");
  });

  it("renders explanation empty state for legacy evaluate artifacts", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-legacy", { includeExplanations: false });
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId: "demo-legacy" }) }));

    expect(html).toContain("评估解释");
    expect(html).toContain("旧版产物");
  });

  it("renders report page markdown for complete run", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-full");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await ReportPage({ params: Promise.resolve({ runId: "demo-full" }) }));

    expect(html).toContain("ShotgunCV v0.3.0 LLM Eval Summary");
    expect(html).toContain("LLM Product Engineer");
  });
});


async function createTempRunsDir(): Promise<string> {
  return mkdtemp(path.join(tmpdir(), "shotguncv-runs-"));
}


async function createIncompleteRun(runsDir: string, runId: string): Promise<void> {
  const runDir = path.join(runsDir, runId);
  await mkdir(path.join(runDir, "config"), { recursive: true });
  await mkdir(path.join(runDir, "ingest"), { recursive: true });
  await mkdir(path.join(runDir, "analyze"), { recursive: true });

  await writeJson(path.join(runDir, "config", "run_config.json"), {
    analyzer: { provider: "deterministic", model: "" },
    generator: { provider: "deterministic", model: "" },
    judge: { provider: "deterministic", model: "" },
    planner: { provider: "deterministic", model: "" },
    openai: { base_url: null, api_key_env: "OPENAI_API_KEY", env_file: ".env" },
    run_metadata: { label: "demo-run" },
  });
  await writeJson(path.join(runDir, "ingest", "manifest.json"), {
    candidate_id: "cand-001",
    jd_inputs: [{ source_type: "file", source_value: "fixtures/jds/sample_batch.txt" }],
  });
  await writeJson(path.join(runDir, "analyze", "candidate_profile.json"), {
    candidate_id: "cand-001",
    base_resume_path: "fixtures/candidates/base_resume.md",
    experiences: ["围绕 LLM 辅助工作流搭建过内部工具"],
    projects: [],
    skills: ["LLM workflows"],
    industry_tags: ["AI tooling"],
    strengths: ["围绕 LLM 辅助工作流搭建过内部工具"],
    constraints: ["No explicit production ML platform ownership yet"],
    preferences: ["Product-oriented AI roles"],
    core_claims: ["围绕 LLM 辅助工作流搭建过内部工具"],
    verified_evidence: ["围绕 LLM 辅助工作流搭建过内部工具"],
    missing_evidence_areas: ["缺少大规模 benchmark 经验"],
    preferred_role_tracks: ["LLM Product Engineer"],
  });
  await writeJson(path.join(runDir, "analyze", "jd_profiles.json"), [
    {
      jd_id: "jd-001",
      title: "LLM Product Engineer",
      company: "Example AI",
      cluster: "product-engineer",
      responsibilities: ["Build evaluation pipelines"],
      requirements: ["Python"],
      keywords: ["evaluation", "python"],
      seniority: "mid",
      bonuses: [],
      risk_signals: ["Prompt quality will be probed"],
      source_type: "file",
      source_value: "fixtures/jds/sample_batch.txt",
      must_have_requirements: ["Python"],
      nice_to_have_requirements: [],
      hidden_signals: [],
      interview_focus_areas: ["evaluation"],
      role_level_confidence: 0.72,
    },
  ]);
}


async function createCompleteRun(
  runsDir: string,
  runId: string,
  options?: { includeExplanations?: boolean },
): Promise<void> {
  const includeExplanations = options?.includeExplanations ?? true;
  const runDir = path.join(runsDir, runId);
  await createIncompleteRun(runsDir, runId);
  await mkdir(path.join(runDir, "generate"), { recursive: true });
  await mkdir(path.join(runDir, "evaluate"), { recursive: true });
  await mkdir(path.join(runDir, "plan"), { recursive: true });
  await mkdir(path.join(runDir, "report"), { recursive: true });

  await writeJson(path.join(runDir, "generate", "resume_variants.json"), [
    {
      variant_id: "variant-jd-jd-001",
      variant_type: "jd-specific",
      cluster: "product-engineer",
      target_jd_ids: ["jd-001"],
      summary: "岗位定制摘要",
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
      ranking_version: "v0.3.0-llm-eval",
      judge_rationale: "匹配度较强，补齐少量短板即可。",
      llm_role_fit_score: 0.81,
      llm_evidence_score: 0.78,
      llm_persuasion_score: 0.75,
      llm_risk_score: 0.31,
      llm_overall_score: 0.78,
      final_overall_score: 0.81,
      final_decision_source: "llm-primary",
      guardrail_flags: [],
      provider: "openai",
      model: "gpt-5.4-mini",
    },
  ]);
  if (includeExplanations) {
    await writeJson(path.join(runDir, "evaluate", "ranking_explanations.json"), [
      {
        jd_id: "jd-001",
        variant_id: "variant-jd-jd-001",
        ranking_version: "v0.3.0-llm-eval",
        dimension_reasons: {
          fit: "关键词覆盖与证据绑定较强",
          ats: "Python 与 evaluation 命中",
          evidence: "简历条目支持核心优势",
          stretch: "延展项可控",
          gap_risk: "缺少大规模 benchmark 经验",
          rewrite_cost: "岗位定制版本改动成本中等",
          overall: "匹配度较高，补齐少量短板即可。",
        },
        positive_signals: ["证据绑定强", "关键词覆盖好"],
        risk_flags: ["缺少大规模 benchmark 经验"],
        evidence_refs: ["围绕 LLM 辅助工作流搭建过内部工具"],
        decision_summary: "匹配度较高，补齐少量短板即可。",
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
          weak_points: ["缺少大规模 benchmark 经验"],
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
      top_reasons: ["证据绑定强", "关键词覆盖好"],
    },
  ]);
  await writeJson(path.join(runDir, "plan", "application_strategies.json"), [
    {
      jd_id: "jd-001",
      recommended_variant_id: "variant-jd-jd-001",
      priority_rank: 1,
      apply_decision: "apply",
      reason_summary: "匹配度较高，补齐少量短板即可。",
      needs_jd_specific_variant: true,
      decision_drivers: ["证据绑定强", "关键词覆盖好"],
      watchouts: ["缺少大规模 benchmark 经验"],
      recommended_actions: ["面试前复习离线评估指标。"],
      catch_up_notes: ["面试前复习离线评估指标。"],
      decision_confidence: 0.81,
      interview_prep_points: ["evaluation"],
      resume_revision_tasks: [],
    },
  ]);
  await writeFile(
    path.join(runDir, "report", "summary.md"),
    "# ShotgunCV v0.3.0 LLM Eval Summary\n\n## Ranked Application Strategy\n\n### 1. LLM Product Engineer @ Example AI\n\n- Top Evidence: 围绕 LLM 辅助工作流搭建过内部工具\n",
    "utf-8",
  );
}


async function writeJson(filePath: string, payload: unknown): Promise<void> {
  await writeFile(filePath, JSON.stringify(payload, null, 2), "utf-8");
}
