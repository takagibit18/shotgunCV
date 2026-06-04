import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { EventEmitter } from "node:events";
import { tmpdir } from "node:os";
import path from "node:path";

import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";

import HomePage from "../app/page";
import EvaluationPage from "../app/evaluations/page";
import ResumePage from "../app/resume/page";
import RunsPage from "../app/runs/page";
import JdImagePreviewPage from "../app/runs/[runId]/jd-preview/[index]/page";
import RunPage from "../app/runs/[runId]/page";
import ReportPage from "../app/runs/[runId]/report/page";
import {
  GET as getLocalConfigRoute,
  POST as resetLocalConfigRoute,
  PUT as putLocalConfigRoute,
} from "../app/api/settings/local-config/route";
import {
  POST as postEvidenceOverrideRoute,
} from "../app/api/runs/[runId]/evidence-overrides/route";
import {
  GET as getDependencyRoute,
  POST as postDependencyRoute,
} from "../app/api/settings/dependencies/route";
import SettingsPage from "../app/settings/page";
import UploadPage from "../app/upload/page";
import { filterEvaluationResults, loadEvaluationResults, sortEvaluationResults } from "./evaluations";
import {
  LocalConfigError,
  loadLocalConfig,
  resetLocalConfig,
  saveLocalConfig,
} from "./local-config";
import { loadResumeWorkspace } from "./resume";
import { loadRunDetail, listRuns, loadRunReport } from "./runs";
import { deleteRun, patchRunDraft, startRunAction } from "./run-actions";
import { checkPythonDependencies } from "./python-env";
import { listCandidates } from "./candidates";
import { loadSettingsOverview } from "./settings";
import { createRunDraft, DraftCreationError } from "./upload-drafts";


describe("run viewer data loading", () => {
  afterEach(() => {
    delete process.env.SHOTGUNCV_RUNS_DIR;
    delete process.env.OPENAI_API_KEY;
    delete process.env.SHOTGUNCV_WEB_PROJECT_ROOT;
    delete process.env.SHOTGUNCV_PYTHON;
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

  it("loads legacy artifact-only run detail without config", async () => {
    const runsDir = await createTempRunsDir();
    const runDir = path.join(runsDir, "artifact-only");
    await mkdir(path.join(runDir, "report"), { recursive: true });
    await writeFile(path.join(runDir, "report", "summary.md"), "# Legacy report\n", "utf-8");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const detail = await loadRunDetail("artifact-only");
    const html = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId: "artifact-only" }) }));

    expect(detail.runId).toBe("artifact-only");
    expect(detail.analyzerProvider).toBe("unknown");
    expect(detail.completedStages).toEqual(["report"]);
    expect(html).toContain("评估详情");
    expect(html).toContain("评估结果尚未生成");
    expect(html).toContain("结果已就绪");
  });

  it("renders legacy partial run with downstream artifacts but no config or analyze output", async () => {
    const runsDir = await createTempRunsDir();
    const runId = "legacy-partial";
    const runDir = path.join(runsDir, runId);
    await mkdir(path.join(runDir, "generate"), { recursive: true });
    await mkdir(path.join(runDir, "evaluate"), { recursive: true });
    await mkdir(path.join(runDir, "plan"), { recursive: true });
    await mkdir(path.join(runDir, "report"), { recursive: true });
    await writeJson(path.join(runDir, "generate", "resume_variants.json"), [
      {
        variant_id: "variant-jd-jd-001",
        variant_type: "jd-specific",
        cluster: "legacy",
        target_jd_ids: ["jd-001"],
        summary: "legacy variant",
        emphasized_strengths: [],
        stretch_points: [],
        source_resume_path: "legacy.md",
      },
    ]);
    await writeJson(path.join(runDir, "evaluate", "scorecards.json"), [
      {
        jd_id: "jd-001",
        variant_id: "variant-jd-jd-001",
        fit_score: 0.7,
        ats_score: 0.7,
        evidence_score: 0.7,
        stretch_score: 0.5,
        gap_risk_score: 0.4,
        rewrite_cost_score: 0.2,
        overall_score: 0.7,
        ranking_version: "legacy",
        judge_rationale: "legacy",
        llm_role_fit_score: 0,
        llm_evidence_score: 0,
        llm_persuasion_score: 0,
        llm_risk_score: 0,
        llm_overall_score: 0,
        final_overall_score: 0.7,
        final_decision_source: "legacy",
        guardrail_flags: [],
        provider: "unknown",
        model: "",
      },
    ]);
    await writeJson(path.join(runDir, "evaluate", "gap_maps.json"), [{ jd_id: "jd-001", candidate_id: "cand", items: [] }]);
    await writeJson(path.join(runDir, "evaluate", "eval_summary.json"), [
      { jd_id: "jd-001", title: "Legacy role", top_variant_id: "variant-jd-jd-001", gap_count: 0, top_reasons: [] },
    ]);
    await writeJson(path.join(runDir, "plan", "application_strategies.json"), []);
    await writeFile(path.join(runDir, "report", "summary.md"), "# Legacy report\n", "utf-8");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId }) }));

    expect(html).toContain("Legacy role");
    expect(html).toContain("匹配、证据与风险");
    expect(html).toContain("结果已就绪");
  });

  it("renders run detail when one optional artifact contains malformed json", async () => {
    const runsDir = await createTempRunsDir();
    await createIncompleteRun(runsDir, "malformed-artifact");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;
    await writeFile(
      path.join(runsDir, "malformed-artifact", "analyze", "candidate_profile.json"),
      '{"candidate_id": "broken"',
      "utf-8",
    );

    const detail = await loadRunDetail("malformed-artifact");
    const html = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId: "malformed-artifact" }) }));

    expect(detail.analyze.candidate).toBeNull();
    expect(html).toContain("评估结果尚未生成");
    expect(html).not.toContain("阶段状态");
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

  it("loads and renders post-run review artifacts without raw source text", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-full");
    const runDir = path.join(runsDir, "demo-full");
    await mkdir(path.join(runDir, "review"), { recursive: true });
    await writeJson(path.join(runDir, "review", "post_run_review.json"), {
      schema_version: "post-run-review-v1",
      run_id: "demo-full",
      candidate_id: "cand-001",
      jd_ids: ["jd-001"],
      evidence_citations: [
        {
          source_type: "candidate_evidence",
          artifact_path: "analyze/candidate_profile.json",
          provenance_summary: "候选人画像证据",
          text: "围绕 LLM 辅助工作流搭建过内部工具",
        },
      ],
      interview_questions: [{ jd_id: "jd-001", question: "请说明项目证据。" }],
      revision_tasks: [{ jd_id: "jd-001", task: "补强指标表达。" }],
      retrieval: { result_count: 1, misses: [] },
      validation: { fabrication_policy: "passed", warnings: [] },
    });
    await writeFile(path.join(runDir, "review", "interview_prep.md"), "# 面试准备\n\n- 证据\n", "utf-8");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const detail = await loadRunDetail("demo-full");
    const html = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId: "demo-full" }) }));

    expect(detail.review.postRunReview?.schema_version).toBe("post-run-review-v1");
    expect(detail.review.interviewPrepMarkdown).toContain("面试准备");
    expect(html).toContain("面试准备");
    expect(html).toContain("候选人画像证据");
    expect(html).not.toContain("input_files");
  });

  it("loads v0.5.7 gate and three-score artifacts", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-v057", { includeV057Artifacts: true });
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const detail = await loadRunDetail("demo-v057");

    expect(detail.preflightGates[0]).toMatchObject({
      jd_id: "jd-001",
      status: "pass",
    });
    expect(detail.requirementMatrix[0]).toMatchObject({
      tier: "hard_gate",
      evidence_status: "verified",
      fabrication_policy: "never_fabricate",
    });
    expect(detail.evaluate.scorecards[0]).toMatchObject({
      verified_fit_score: 0.74,
      rewrite_potential_score: 0.83,
      risk_score: 0.22,
      gate_status: "pass",
    });
  });

  it("uses uploaded JD display names as readable fallbacks for empty analyzed titles", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-display-name");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;
    const manifestPath = path.join(runsDir, "demo-display-name", "ingest", "manifest.json");
    const jdProfilesPath = path.join(runsDir, "demo-display-name", "analyze", "jd_profiles.json");
    const evalSummaryPath = path.join(runsDir, "demo-display-name", "evaluate", "eval_summary.json");
    const manifest = JSON.parse(await readFile(manifestPath, "utf-8"));
    manifest.jd_inputs[0].display_name = "Example AI - Staff Product Manager";
    await writeFile(manifestPath, JSON.stringify(manifest, null, 2), "utf-8");
    const jdProfiles = JSON.parse(await readFile(jdProfilesPath, "utf-8"));
    jdProfiles[0].title = "";
    jdProfiles[0].company = "";
    await writeFile(jdProfilesPath, JSON.stringify(jdProfiles, null, 2), "utf-8");
    const evalSummary = JSON.parse(await readFile(evalSummaryPath, "utf-8"));
    evalSummary[0].title = "";
    await writeFile(evalSummaryPath, JSON.stringify(evalSummary, null, 2), "utf-8");

    const detail = await loadRunDetail("demo-display-name");

    expect(detail.evaluate.topVariants[0].title).toBe("Example AI - Staff Product Manager");
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

  it("renders report with core and guardrail summaries visible by default", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-v057", { includeV057Artifacts: true });
    await makeRunRisky(runsDir, "demo-v057");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await ReportPage({ params: Promise.resolve({ runId: "demo-v057" }) }));

    expect(html).toContain("核心结论");
    expect(html).toContain("风险边界");
    expect(html).toContain("硬性要求缺少证据");
    expect(html).toContain("风险水平");
    expect(html).not.toContain("Core");
    expect(html).not.toContain("Guardrail");
    expect(html).not.toContain("hard_gate_missing");
    expect(html).not.toContain("risk score");
  });

  it("creates a draft run with uploaded files and a metadata-only manifest", async () => {
    const runsDir = await createTempRunsDir();
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const result = await createRunDraft({
      candidateId: "cand-001",
      label: "April upload",
      cvFiles: [new File(["resume text"], "resume.md", { type: "text/markdown" })],
      jdFiles: [new File(["jd text"], "jd.txt", { type: "text/plain" })],
      jdFileDisplayNames: ["Example - Applied AI Engineer"],
      now: new Date("2026-04-25T08:30:00.000Z"),
    });

    expect(result).toMatchObject({
      runId: "april-upload-20260425-083000",
      status: "draft",
      uploadManifestPath: "ingest/upload_manifest.json",
    });
    expect(result.nextCommand).toContain("shotguncv run");
    expect(result.nextCommand).toContain("--cv");
    expect(result.nextCommand).toContain("--jd");

    const manifest = JSON.parse(
      await readFile(path.join(runsDir, result.runId, "ingest", "upload_manifest.json"), "utf-8"),
    );
    expect(manifest).toMatchObject({
      schemaVersion: "v0.5.1-upload-manifest",
      candidateId: "cand-001",
      label: "April upload",
      nextCommand: result.nextCommand,
    });
    expect(manifest.files).toEqual([
      expect.objectContaining({
        role: "cv",
        originalName: "resume.md",
        storedRelativePath: "input_files/cv/resume.md",
        sizeBytes: 11,
      }),
      expect.objectContaining({
        role: "jd",
        originalName: "jd.txt",
        displayName: "Example - Applied AI Engineer",
        storedRelativePath: "input_files/jd/jd.txt",
        sizeBytes: 7,
      }),
    ]);
    expect(JSON.stringify(manifest)).not.toContain("resume text");
    expect(JSON.stringify(manifest)).not.toContain("jd text");
    const config = JSON.parse(await readFile(path.join(runsDir, result.runId, "config", "run_config.json"), "utf-8"));
    expect(config.input_extraction).toMatchObject({
      ocr_provider: "local_ocr",
      vision_provider: "openai_vision",
      vision_model: "",
      ocr_languages: "eng+chi_sim",
    });
    expect(await readFile(path.join(runsDir, result.runId, "input_files", "cv", "resume.md"), "utf-8")).toBe(
      "resume text",
    );
    expect(await readFile(path.join(runsDir, result.runId, "input_files", "jd", "jd.txt"), "utf-8")).toBe("jd text");
  });

  it("creates a draft run with an automatic timestamp candidate id", async () => {
    const runsDir = await createTempRunsDir();
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const result = await createRunDraft({
      cvFiles: [new File(["resume text"], "resume.md", { type: "text/markdown" })],
      jdFiles: [new File(["jd text"], "jd.txt", { type: "text/plain" })],
      jdFileDisplayNames: ["Example - Applied AI Engineer"],
      now: new Date("2026-04-25T08:30:00.123Z"),
    });

    const manifest = JSON.parse(
      await readFile(path.join(runsDir, result.runId, "ingest", "upload_manifest.json"), "utf-8"),
    );
    expect(manifest.candidateId).toBe("cand-20260425-083000123");
    expect(result.nextCommand).toContain("--candidate-id cand-20260425-083000123");
  });

  it("lists registered candidates from upload manifests", async () => {
    const runsDir = await createTempRunsDir();
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const first = await createRunDraft({
      candidateId: "cand-lihua",
      candidateDisplayName: "李华",
      label: "first role",
      cvFiles: [new File(["resume text"], "resume.md", { type: "text/markdown" })],
      jdFiles: [new File(["jd text"], "jd.txt", { type: "text/plain" })],
      jdFileDisplayNames: ["Example - Applied AI Engineer"],
      now: new Date("2026-04-25T08:30:00.000Z"),
    });
    await createRunDraft({
      candidateId: "cand-lihua",
      candidateDisplayName: "李华",
      label: "second role",
      cvFiles: [new File(["resume text"], "resume.md", { type: "text/markdown" })],
      jdFiles: [new File(["jd text"], "jd.txt", { type: "text/plain" })],
      jdFileDisplayNames: ["Example - Platform PM"],
      now: new Date("2026-04-26T08:30:00.000Z"),
    });

    const candidates = await listCandidates();

    expect(first.runId).toBe("first-role-20260425-083000");
    expect(candidates).toHaveLength(1);
    expect(candidates[0]).toMatchObject({
      candidateId: "cand-lihua",
      displayName: "李华",
      initials: "李华",
      runCount: 2,
      latestRunId: "second-role-20260426-083000",
    });
    expect(candidates[0].cvFiles).toHaveLength(1);
    expect(candidates[0].cvFiles[0]).toMatchObject({
      originalName: "resume.md",
      storedRelativePath: "input_files/cv/resume.md",
    });
  });

  it("creates a draft from selected candidate CV references", async () => {
    const runsDir = await createTempRunsDir();
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const source = await createRunDraft({
      candidateId: "cand-lihua",
      candidateDisplayName: "李华",
      label: "source role",
      cvFiles: [new File(["resume text"], "resume.md", { type: "text/markdown" })],
      jdFiles: [new File(["jd text"], "jd.txt", { type: "text/plain" })],
      jdFileDisplayNames: ["Example - Source"],
      now: new Date("2026-04-25T08:30:00.000Z"),
    });

    const result = await createRunDraft({
      candidateId: "cand-lihua",
      candidateDisplayName: "李华",
      label: "reuse role",
      cvFiles: [],
      existingCvFiles: [{ sourceRunId: source.runId, storedRelativePath: "input_files/cv/resume.md" }],
      jdFiles: [new File(["new jd"], "new-jd.txt", { type: "text/plain" })],
      jdFileDisplayNames: ["Example - Reuse"],
      now: new Date("2026-04-27T08:30:00.000Z"),
    });

    const manifest = JSON.parse(
      await readFile(path.join(runsDir, result.runId, "ingest", "upload_manifest.json"), "utf-8"),
    );

    expect(manifest).toMatchObject({
      candidateId: "cand-lihua",
      candidateDisplayName: "李华",
    });
    expect(manifest.files).toEqual([
      expect.objectContaining({
        role: "cv",
        originalName: "resume.md",
        storedRelativePath: "input_files/cv/resume.md",
        contentType: "text/markdown",
      }),
      expect.objectContaining({
        role: "jd",
        originalName: "new-jd.txt",
        displayName: "Example - Reuse",
      }),
    ]);
    expect(await readFile(path.join(runsDir, result.runId, "input_files", "cv", "resume.md"), "utf-8")).toBe(
      "resume text",
    );
  });

  it("creates separate metadata-only JD files from pasted text entries", async () => {
    const runsDir = await createTempRunsDir();
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const result = await createRunDraft({
      candidateId: "cand-001",
      cvFiles: [new File(["resume text"], "resume.md", { type: "text/markdown" })],
      jdFiles: [new File(["file jd text"], "jd-file.txt", { type: "text/plain" })],
      jdFileDisplayNames: ["Example - File JD"],
      jdTexts: [
        "Title: Applied AI Engineer\nCompany: Example\nBody:\n- Build AI workflows",
        "  ",
        "Title: Platform PM\nCompany: Example\nBody:\n- Own automation roadmap",
      ],
      jdTextDisplayNames: ["Example - Applied AI Engineer", "", "Example - Platform PM"],
      now: new Date("2026-04-25T08:30:00.000Z"),
    });

    const manifest = JSON.parse(
      await readFile(path.join(runsDir, result.runId, "ingest", "upload_manifest.json"), "utf-8"),
    );
    expect(manifest.files.filter((file: { role: string }) => file.role === "jd")).toEqual([
      expect.objectContaining({
        role: "jd",
        originalName: "jd-file.txt",
        displayName: "Example - File JD",
        storedRelativePath: "input_files/jd/jd-file.txt",
        contentType: "text/plain",
      }),
      expect.objectContaining({
        role: "jd",
        originalName: "pasted-jd-001.txt",
        displayName: "Example - Applied AI Engineer",
        storedRelativePath: "input_files/jd/pasted-jd-001.txt",
        contentType: "text/plain",
      }),
      expect.objectContaining({
        role: "jd",
        originalName: "pasted-jd-002.txt",
        displayName: "Example - Platform PM",
        storedRelativePath: "input_files/jd/pasted-jd-002.txt",
        contentType: "text/plain",
      }),
    ]);
    expect(JSON.stringify(manifest)).not.toContain("Build AI workflows");
    expect(JSON.stringify(manifest)).not.toContain("Own automation roadmap");
    expect(await readFile(path.join(runsDir, result.runId, "input_files", "jd", "pasted-jd-001.txt"), "utf-8")).toBe(
      "Title: Applied AI Engineer\nCompany: Example\nBody:\n- Build AI workflows",
    );
    expect(await readFile(path.join(runsDir, result.runId, "input_files", "jd", "pasted-jd-002.txt"), "utf-8")).toBe(
      "Title: Platform PM\nCompany: Example\nBody:\n- Own automation roadmap",
    );
  });

  it("rejects invalid draft uploads with stable error codes", async () => {
    const runsDir = await createTempRunsDir();
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    await expect(
      createRunDraft({
        candidateId: "cand-001",
        cvFiles: [],
        jdFiles: [new File(["jd text"], "jd.txt", { type: "text/plain" })],
        jdFileDisplayNames: ["Example - Applied AI Engineer"],
        now: new Date("2026-04-25T08:30:00.000Z"),
      }),
    ).rejects.toMatchObject({ code: "missing_cv" });

    await expect(
      createRunDraft({
        candidateId: "cand-001",
        cvFiles: [new File(["resume"], "../resume.md", { type: "text/markdown" })],
        jdFiles: [new File(["jd text"], "jd.txt", { type: "text/plain" })],
        jdFileDisplayNames: ["Example - Applied AI Engineer"],
        now: new Date("2026-04-25T08:30:00.000Z"),
      }),
    ).rejects.toMatchObject({ code: "unsafe_filename" });

    await expect(
      createRunDraft({
        candidateId: "cand-001",
        cvFiles: [new File(["resume"], "resume.exe", { type: "application/octet-stream" })],
        jdFiles: [new File(["jd text"], "jd.txt", { type: "text/plain" })],
        jdFileDisplayNames: ["Example - Applied AI Engineer"],
        now: new Date("2026-04-25T08:30:00.000Z"),
      }),
    ).rejects.toMatchObject({ code: "unsupported_file_type" });

    await expect(
      createRunDraft({
        candidateId: "cand-001",
        cvFiles: [new File(["resume"], "resume.md", { type: "text/markdown" })],
        jdFiles: [new File(["jd text"], "jd.txt", { type: "text/plain" })],
        jdFileDisplayNames: ["   "],
        now: new Date("2026-04-25T08:30:00.000Z"),
      }),
    ).rejects.toMatchObject({ code: "missing_jd_display_name" });

    await expect(
      createRunDraft({
        candidateId: "cand-001",
        cvFiles: [new File(["resume"], "resume.md", { type: "text/markdown" })],
        jdFiles: [],
        jdTexts: ["Title: Applied AI Engineer\nCompany: Example\nBody:\n- Build AI workflows"],
        jdTextDisplayNames: ["   "],
        now: new Date("2026-04-25T08:30:00.000Z"),
      }),
    ).rejects.toMatchObject({ code: "missing_jd_display_name" });

    await expect(
      createRunDraft({
        candidateId: "cand-001",
        cvFiles: [new File(["resume"], "resume.md", { type: "text/markdown" })],
        jdFiles: [],
        jdTexts: ["   "],
        jdTextDisplayNames: ["Example - Applied AI Engineer"],
        now: new Date("2026-04-25T08:30:00.000Z"),
      }),
    ).rejects.toMatchObject({ code: "missing_jd" });
  });

  it("includes draft runs without marking ingest complete", async () => {
    const runsDir = await createTempRunsDir();
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;
    const draft = await createRunDraft({
      candidateId: "cand-001",
      label: "Draft upload",
      cvFiles: [new File(["resume"], "resume.md", { type: "text/markdown" })],
      jdFiles: [new File(["jd"], "jd.md", { type: "text/markdown" })],
      jdFileDisplayNames: ["Example - Draft Role"],
      now: new Date("2026-04-25T08:30:00.000Z"),
    });

    const runs = await listRuns();
    const detail = await loadRunDetail(draft.runId);

    expect(runs[0]).toMatchObject({
      runId: draft.runId,
      draftStatus: "draft",
      completedStages: [],
      label: "Draft upload",
    });
    expect(detail.draft?.nextCommand).toBe(draft.nextCommand);
    expect(detail.completedStages).not.toContain("ingest");
  });

  it("loads run status file and builds stage statuses", async () => {
    const runsDir = await createTempRunsDir();
    await createIncompleteRun(runsDir, "demo");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;
    await writeJson(path.join(runsDir, "demo", "run_status.json"), {
      status: "failed",
      current_stage: "generate",
      started_at: "2026-05-03T08:00:00.000Z",
      finished_at: "2026-05-03T08:01:00.000Z",
      error_stage: "generate",
      error_summary: "simulated generate failure",
      last_action: "run",
    });

    const detail = await loadRunDetail("demo");
    const runs = await listRuns();

    expect(detail.draftStatus).toBe("failed");
    expect(detail.runStatus?.error_summary).toBe("simulated generate failure");
    expect(detail.stageStatuses).toContainEqual({ stage: "analyze", status: "complete" });
    expect(detail.stageStatuses).toContainEqual({ stage: "generate", status: "failed" });
    expect(runs[0].draftStatus).toBe("failed");
  });

  it("loads structured timeline events from logs without requiring report artifacts", async () => {
    const runsDir = await createTempRunsDir();
    await createIncompleteRun(runsDir, "timeline-run");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;
    await mkdir(path.join(runsDir, "timeline-run", "logs"), { recursive: true });
    await writeJson(path.join(runsDir, "timeline-run", "run_status.json"), {
      status: "done",
      current_stage: "report",
      started_at: "2026-05-03T08:00:00Z",
      finished_at: "2026-05-03T08:00:02Z",
      error_stage: null,
      error_summary: null,
      last_action: "run",
      quality_status: "warning",
      quality_summary: "JD profile fields are incomplete.",
    });
    await writeFile(
      path.join(runsDir, "timeline-run", "logs", "run_events.jsonl"),
      [
        JSON.stringify({
          timestamp: "2026-05-03T08:00:00Z",
          event: "run_started",
          trigger_entrypoint: "web",
          input_scale: { cv_sources: 1, jd_sources: 2 },
          model_config: { analyzer: { provider: "deterministic", model: "" } },
          cli_command_summary: ["shotguncv", "run", "--run-dir", "<run_dir>"],
        }),
        JSON.stringify({
          timestamp: "2026-05-03T08:00:01Z",
          event: "stage_started",
          stage: "analyze",
        }),
        JSON.stringify({
          timestamp: "2026-05-03T08:00:01Z",
          event: "model_resolved",
          stage: "analyze",
          role: "analyzer",
          provider: "openai",
          configured_model: "",
          resolved_model: "gpt-5.4-mini",
          base_url_host: "api.openai.com",
        }),
        JSON.stringify({
          timestamp: "2026-05-03T08:00:01Z",
          event: "llm_call_finished",
          stage: "analyze",
          operation: "analyze_resume_and_jds",
          provider: "openai",
          model: "gpt-5.4-mini",
          duration_ms: 500,
          prompt_tokens: 100,
          completion_tokens: 25,
          total_tokens: 125,
          output_parse_status: "success",
        }),
        JSON.stringify({
          timestamp: "2026-05-03T08:00:01Z",
          event: "tool_call_finished",
          stage: "ingest",
          tool: "openai_vision",
          input_type: "jd",
          duration_ms: 500,
          status: "success",
          output_summary: { text_chars: 1200 },
        }),
        JSON.stringify({
          timestamp: "2026-05-03T08:00:01Z",
          event: "fallback_used",
          stage: "analyze",
          operation: "analyze_resume_and_jds",
          from_provider: "openai",
          to_provider: "deterministic",
          reason: "invalid json",
        }),
        JSON.stringify({
          timestamp: "2026-05-03T08:00:01Z",
          event: "quality_gate_checked",
          stage: "analyze",
          gate: "jd_profile_completeness",
          status: "failed",
          checks: { empty_title_count: 1 },
          action: "warn",
        }),
        JSON.stringify({
          timestamp: "2026-05-03T08:00:02Z",
          event: "stage_failed",
          stage: "analyze",
          duration_ms: 1000,
          error_code: "RuntimeError",
          error_summary: "simulated failure",
        }),
      ].join("\n"),
      "utf-8",
    );

    const detail = await loadRunDetail("timeline-run");
    const html = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId: "timeline-run" }) }));

    expect(detail.timeline).toHaveLength(8);
    expect(detail.timeline[0]).toMatchObject({
      event: "run_started",
      trigger_entrypoint: "web",
      input_scale: { cv_sources: 1, jd_sources: 2 },
    });
    expect(detail.observability).toMatchObject({
      totalTokens: 125,
      toolCallCount: 1,
      fallbackCount: 1,
    });
    expect(detail.observability.resolvedModels[0]).toMatchObject({
      stage: "analyze",
      resolvedModel: "gpt-5.4-mini",
    });
    expect(html).not.toContain("Run timeline");
    expect(html).not.toContain("运行观测");
    expect(html).not.toContain("gpt-5.4-mini");
    expect(html).not.toContain("125");
    expect(html).toContain("完成，建议复核提醒项");
  });

  it("updates draft metadata, replaces CV files, and appends JD inputs", async () => {
    const runsDir = await createTempRunsDir();
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;
    const draft = await createRunDraft({
      candidateId: "cand-001",
      label: "Draft upload",
      cvFiles: [new File(["old resume"], "old-resume.md", { type: "text/markdown" })],
      jdFiles: [new File(["old jd"], "old-jd.md", { type: "text/markdown" })],
      jdFileDisplayNames: ["Old JD"],
      now: new Date("2026-04-25T08:30:00.000Z"),
    });

    await patchRunDraft(draft.runId, {
      candidateId: "cand-002",
      label: "Updated draft",
      cvFiles: [new File(["new resume"], "new-resume.md", { type: "text/markdown" })],
      jdFiles: [new File(["new jd"], "new-jd.md", { type: "text/markdown" })],
      jdFileDisplayNames: ["Renamed old JD", "New JD"],
      jdTexts: ["Title: Added JD\nBody:\n- Build workflows"],
      jdTextDisplayNames: ["Pasted JD"],
      now: new Date("2026-04-25T09:00:00.000Z"),
    });

    const runDir = path.join(runsDir, draft.runId);
    const manifest = JSON.parse(await readFile(path.join(runDir, "ingest", "upload_manifest.json"), "utf-8"));
    const config = JSON.parse(await readFile(path.join(runDir, "config", "run_config.json"), "utf-8"));
    const status = JSON.parse(await readFile(path.join(runDir, "run_status.json"), "utf-8"));

    expect(manifest.candidateId).toBe("cand-002");
    expect(manifest.label).toBe("Updated draft");
    expect(manifest.nextCommand).toContain("--candidate-id cand-002");
    expect(config.run_metadata.label).toBe("Updated draft");
    expect(manifest.files.filter((file: { role: string }) => file.role === "cv")).toEqual([
      expect.objectContaining({ originalName: "new-resume.md", storedRelativePath: "input_files/cv/new-resume.md" }),
    ]);
    expect(manifest.files.filter((file: { role: string }) => file.role === "jd")).toEqual([
      expect.objectContaining({ originalName: "old-jd.md", displayName: "Renamed old JD" }),
      expect.objectContaining({ originalName: "new-jd.md", displayName: "New JD" }),
      expect.objectContaining({ originalName: "pasted-jd-001.txt", displayName: "Pasted JD" }),
    ]);
    expect(await readFile(path.join(runDir, "input_files", "cv", "new-resume.md"), "utf-8")).toBe("new resume");
    expect(status).toMatchObject({ status: "draft", last_action: "draft_update" });
  });

  it("deletes draft and failed runs but rejects running runs", async () => {
    const runsDir = await createTempRunsDir();
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;
    const draft = await createRunDraft({
      candidateId: "cand-001",
      cvFiles: [new File(["resume"], "resume.md", { type: "text/markdown" })],
      jdFiles: [new File(["jd"], "jd.md", { type: "text/markdown" })],
      jdFileDisplayNames: ["Example - Draft Role"],
      now: new Date("2026-04-25T08:30:00.000Z"),
    });
    await createIncompleteRun(runsDir, "failed-run");
    await writeJson(path.join(runsDir, "failed-run", "run_status.json"), {
      status: "failed",
      current_stage: "generate",
      started_at: "2026-05-03T08:00:00.000Z",
      finished_at: "2026-05-03T08:01:00.000Z",
      error_stage: "generate",
      error_summary: "simulated failure",
      last_action: "run",
    });
    await createIncompleteRun(runsDir, "running-run");
    await writeJson(path.join(runsDir, "running-run", "run_status.json"), {
      status: "running",
      current_stage: "generate",
      started_at: "2026-05-03T08:00:00.000Z",
      finished_at: null,
      error_stage: null,
      error_summary: null,
      last_action: "run",
    });

    await deleteRun(draft.runId);
    await deleteRun("failed-run");
    await expect(deleteRun("running-run")).rejects.toMatchObject({ code: "run_busy" });

    await expect(readFile(path.join(runsDir, draft.runId, "ingest", "upload_manifest.json"), "utf-8")).rejects.toThrow();
    await expect(readFile(path.join(runsDir, "failed-run", "run_status.json"), "utf-8")).rejects.toThrow();
  });

  it("queues a local CLI run action and writes running status", async () => {
    const runsDir = await createTempRunsDir();
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;
    const draft = await createRunDraft({
      candidateId: "cand-001",
      cvFiles: [new File(["resume"], "resume.md", { type: "text/markdown" })],
      jdFiles: [new File(["jd"], "jd.md", { type: "text/markdown" })],
      jdFileDisplayNames: ["Example - Draft Role"],
      now: new Date("2026-04-25T08:30:00.000Z"),
    });
    const calls: { command: string; args: string[] }[] = [];

    const result = await startRunAction(draft.runId, "run", (command, args) => {
      calls.push({ command, args });
      return { on: () => undefined };
    });

    const status = JSON.parse(await readFile(path.join(runsDir, draft.runId, "run_status.json"), "utf-8"));
    expect(result).toMatchObject({ runId: draft.runId, status: "queued", action: "run" });
    expect(calls[0].command).toBe("shotguncv");
    expect(calls[0].args).toContain("--candidate-id");
    expect(calls[0].args).toContain("cand-001");
    expect(status).toMatchObject({ status: "running", current_stage: "ingest", last_action: "run" });
  });

  it("rejects a web run action before status changes when the CLI command is unavailable", async () => {
    const runsDir = await createTempRunsDir();
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;
    process.env.SHOTGUNCV_CLI_COMMAND = "definitely-missing-shotguncv-command";
    const draft = await createRunDraft({
      candidateId: "cand-001",
      cvFiles: [new File(["resume"], "resume.md", { type: "text/markdown" })],
      jdFiles: [new File(["jd"], "jd.md", { type: "text/markdown" })],
      jdFileDisplayNames: ["Example - Draft Role"],
      now: new Date("2026-04-25T08:30:00.000Z"),
    });

    await expect(startRunAction(draft.runId, "run")).rejects.toMatchObject({
      code: "cli_not_found",
      message:
        "CLI 命令未找到（definitely-missing-shotguncv-command），请确认已安装并在 PATH 中，或取消 SHOTGUNCV_CLI_COMMAND 环境变量以使用自动发现。",
    });

    const status = JSON.parse(await readFile(path.join(runsDir, draft.runId, "run_status.json"), "utf-8"));
    expect(status).toMatchObject({ status: "draft", current_stage: null, error_summary: null });
  });

  it("marks a web run action failed when the CLI exits with a non-zero code", async () => {
    const runsDir = await createTempRunsDir();
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;
    process.env.SHOTGUNCV_CLI_COMMAND = process.execPath;
    const draft = await createRunDraft({
      candidateId: "cand-001",
      cvFiles: [new File(["resume"], "resume.md", { type: "text/markdown" })],
      jdFiles: [new File(["jd"], "jd.md", { type: "text/markdown" })],
      jdFileDisplayNames: ["Example - Draft Role"],
      now: new Date("2026-04-25T08:30:00.000Z"),
    });
    const child = new EventEmitter() as EventEmitter & {
      stdout: EventEmitter;
      stderr: EventEmitter;
      unref: () => void;
    };
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.unref = () => undefined;

    const result = await startRunAction(draft.runId, "run", () => child);
    child.stderr.emit("data", Buffer.from("missing python package"));
    child.emit("exit", 1, null);
    await waitForRunStatus(path.join(runsDir, draft.runId, "run_status.json"), "failed");

    const status = JSON.parse(await readFile(path.join(runsDir, draft.runId, "run_status.json"), "utf-8"));
    expect(result).toMatchObject({ runId: draft.runId, status: "queued", action: "run" });
    expect(status).toMatchObject({
      status: "failed",
      current_stage: "ingest",
      error_stage: "ingest",
      last_action: "run",
    });
    expect(status.error_summary).toContain("CLI 运行失败，退出码 1");
    expect(status.error_summary).toContain("missing python package");
    const actionLog = await readFile(path.join(runsDir, draft.runId, "logs", "web_run_action.jsonl"), "utf-8");
    expect(actionLog).toContain("web_cli_start");
    expect(actionLog).toContain("web_cli_exit");
    expect(actionLog).toContain("missing python package");
  });

  it("rejects duplicate draft run ids", async () => {
    const runsDir = await createTempRunsDir();
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;
    const input = {
      candidateId: "cand-001",
      label: "Duplicate upload",
      cvFiles: [new File(["resume"], "resume.md", { type: "text/markdown" })],
      jdFiles: [new File(["jd"], "jd.md", { type: "text/markdown" })],
      jdFileDisplayNames: ["Example - Draft Role"],
      now: new Date("2026-04-25T08:30:00.000Z"),
    };

    await createRunDraft(input);

    await expect(createRunDraft(input)).rejects.toMatchObject({ code: "run_exists" });
  });

  it("detects scanned PDF and returns needsManualText in draft result", async () => {
    const runsDir = await createTempRunsDir();
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const draft = await createRunDraft({
      candidateId: "cand-001",
      cvFiles: [new File([Buffer.from("%PDF-1.4\n%%EOF")], "resume.pdf", { type: "application/pdf" })],
      jdFiles: [new File(["jd"], "jd.md", { type: "text/markdown" })],
      jdFileDisplayNames: ["Example - Draft Role"],
      now: new Date("2026-04-25T08:30:00.000Z"),
    });

    expect(draft.needsManualText).toBe(true);
    expect(draft.cvIssues).toEqual([{ originalName: "resume.pdf", quality: "empty" }]);
    const manifest = JSON.parse(await readFile(path.join(runsDir, draft.runId, "ingest", "upload_manifest.json"), "utf-8"));
    expect(manifest.needsManualText).toBe(true);
    expect(manifest.cvIssues).toEqual([{ originalName: "resume.pdf", quality: "empty" }]);
  });

  it("patches draft with cvText and writes sidecar file", async () => {
    const runsDir = await createTempRunsDir();
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;
    const draft = await createRunDraft({
      candidateId: "cand-001",
      cvFiles: [new File([Buffer.from("%PDF-1.4\n%%EOF")], "resume.pdf", { type: "application/pdf" })],
      jdFiles: [new File(["jd"], "jd.md", { type: "text/markdown" })],
      jdFileDisplayNames: ["Example - Draft Role"],
      now: new Date("2026-04-25T08:30:00.000Z"),
    });

    await patchRunDraft(draft.runId, { cvText: "候选人简历纯文本内容" });

    const sidecarPath = path.join(runsDir, draft.runId, "input_files", "cv", "resume.txt");
    expect(await readFile(sidecarPath, "utf-8")).toBe("候选人简历纯文本内容");
    const manifest = JSON.parse(await readFile(path.join(runsDir, draft.runId, "ingest", "upload_manifest.json"), "utf-8"));
    expect(manifest.files).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          role: "cv",
          originalName: "resume.txt",
          storedRelativePath: "input_files/cv/resume.txt",
          contentType: "text/plain",
        }),
      ]),
    );
  });

  it("dependency check reports fitz missing when not installed", async () => {
    process.env.SHOTGUNCV_PYTHON = process.execPath;

    const report = await checkPythonDependencies({ forceRefresh: true });

    expect(report.python.found).toBe(true);
    expect(report.python.path).toBe(process.execPath);
    expect(report.fitz.installed).toBe(false);
    expect(report.overall).toBe("blocked");
  });

  it("POST /api/settings/dependencies rejects unknown packages", async () => {
    const response = await postDependencyRoute(
      new Request("http://localhost/api/settings/dependencies", {
        method: "POST",
        body: JSON.stringify({ package: "requests" }),
      }),
    );
    const payload = await response.json();

    expect(response.status).toBe(400);
    expect(payload).toMatchObject({ code: "unsupported_package" });
  });

  it("exposes stable draft creation errors", async () => {
    const error = new DraftCreationError("missing_jd", "请至少提供一个岗位文件或岗位文本。");

    expect(error.code).toBe("missing_jd");
    expect(error.message).toBe("请至少提供一个岗位文件或岗位文本。");
  });
});


describe("run viewer pages", () => {
  afterEach(() => {
    delete process.env.SHOTGUNCV_RUNS_DIR;
  });

  it("renders the landing home page", async () => {
    const runsDir = await createTempRunsDir();
    await createIncompleteRun(runsDir, "demo");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await HomePage());

    expect(html).toContain("智能简历工作台");
    expect(html).toContain("从岗位输入到证据化简历策略，一屏掌控");
    expect(html).toContain("demo");
    expect(html).toContain("为什么用智能简历工作台");
    expect(html).toContain("准备开始你的第一轮简历工作流了吗");
    expect(html).toContain("打开运行队列");
    expect(html).toContain('href="/upload"');
    expect(html).toContain('href="/runs"');
    expect(html).not.toContain("app-sidebar");
    expect(html).not.toContain("app-commandbar");
  });

  it("renders landing navigation and keeps full queue controls on the queue page", async () => {
    const runsDir = await createTempRunsDir();
    await createIncompleteRun(runsDir, "demo");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await HomePage());
    const runsHtml = renderToStaticMarkup(await RunsPage());

    expect(html).toContain("智能简历工作台");
    expect(html).toContain("功能特色");
    expect(html).toContain("工作流");
    expect(html).toContain("使用方式");
    expect(html).toContain("常见问题");
    expect(html).toContain('href="/resume"');
    expect(html).toContain('href="#features"');
    expect(html).toContain('href="#workflow"');
    expect(html).not.toContain("模板库");
    expect(html).not.toContain("sidebar-nav-item disabled");
    expect(html).toContain("本地优先，边界清晰");
    expect(html).toContain("先把工作流跑通，再进入证据复核");
    expect(html).not.toContain("搜索投递名称、状态、风险");
    expect(runsHtml).toContain("搜索投递名称、状态、风险");
    expect(runsHtml).toContain("状态筛选");
    expect(runsHtml).toContain("阶段筛选");
    expect(runsHtml).toContain("排序");
    expect(runsHtml).toContain("集中查看每个投递的状态");
    expect(runsHtml).toContain("内部工作台");
    expect(runsHtml).toContain("优先处理");
    expect(runsHtml).toContain("可导出简历");
    expect(runsHtml).toContain("简历交付");
    expect(runsHtml).toContain("检索增强等性能强化暂缓");
    expect(runsHtml).toContain("operational-shell");
    expect(html).not.toContain("editorial-hero");
    expect(html).not.toContain("dark-product-surface");
    expect(html).not.toContain("coral-cta");
    expect(html).not.toContain("v0.5.8");
  });

  it("keeps the landing hero separate from the full run queue", async () => {
    const runsDir = await createTempRunsDir();
    for (let index = 0; index < 12; index += 1) {
      await createIncompleteRun(runsDir, `dashboard-run-${String(index + 1).padStart(2, "0")}`);
    }
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await HomePage());

    expect(html).toContain("从岗位输入到证据化简历策略，一屏掌控");
    expect(html).toContain('href="/runs"');
    expect(html).toContain("landing-workflow-card");
    expect(html).toContain("aria-label=\"下一步\"");
    expect(html).toContain("aria-label=\"查看第 2 步\"");
    expect(html).not.toContain("搜索投递名称、状态、风险");
    expect(html).not.toContain("状态筛选");
    expect(html).not.toContain("第 1 / 2 页");
    expect(html).not.toContain("每页 10 条");
  });

  it("renders the draft upload entry point on the run index page", async () => {
    const runsDir = await createTempRunsDir();
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await HomePage());

    expect(html).toContain("/upload");
    expect(html).toContain("创建投递草稿");
    expect(html).toContain("等待首个任务");
    expect(html).toContain("整理输入");
  });

  it("renders run pagination on the dedicated queue page", async () => {
    const runsDir = await createTempRunsDir();
    for (let index = 0; index < 12; index += 1) {
      await createIncompleteRun(runsDir, `dense-run-${String(index + 1).padStart(2, "0")}`);
    }
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const dashboardHtml = renderToStaticMarkup(await HomePage());
    const html = renderToStaticMarkup(await RunsPage());

    expect(dashboardHtml).toContain("流程健康度");
    expect(dashboardHtml).not.toContain("Workflow Health");
    expect(html).toContain("内部工作台");
    expect(html).toContain("优先处理");
    expect(html).toContain("待处理投递");
    expect(dashboardHtml).toContain("完成率");
    expect(dashboardHtml).toContain("打开运行队列");
    expect(html).toContain("运行队列");
    expect(html).toContain("全部投递");
    expect(html).toContain("进行中");
    expect(html).toContain("删除");
    expect(html).toContain("第 1 / 2 页");
    expect(html).toContain("每页 10 条");
    expect(html).toContain("共 12 条");
  });

  it("renders v0.6 polished Chinese workspace copy without mojibake or temporary version labels", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-v060", { includeV057Artifacts: true });
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const homeHtml = renderToStaticMarkup(await HomePage());
    const runsHtml = renderToStaticMarkup(await RunsPage());
    const uploadHtml = renderToStaticMarkup(UploadPage());
    const runHtml = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId: "demo-v060" }) }));
    const reportHtml = renderToStaticMarkup(await ReportPage({ params: Promise.resolve({ runId: "demo-v060" }) }));
    const combinedHtml = [homeHtml, runsHtml, uploadHtml, runHtml, reportHtml].join("\n");

    expect(combinedHtml).toContain("智能简历工作台");
    expect(combinedHtml).toContain("运行队列");
    expect(combinedHtml).toContain("返回评估结果");
    expect(combinedHtml).toContain("三步创建草稿");
    expect(combinedHtml).toContain("评估详情");
    expect(combinedHtml).toContain("AI 评估复核");
    expect(combinedHtml).toContain("投递决策摘要");
    expect(combinedHtml).toContain("匹配度");
    expect(combinedHtml).toContain("补强空间");
    expect(combinedHtml).toContain("风险");
    expect(combinedHtml).toContain("operational-shell");
    expect(combinedHtml).not.toContain("editorial-hero");
    expect(combinedHtml).not.toContain("dark-product-surface");
    expect(combinedHtml).not.toContain("coral-cta");
    expect(combinedHtml).not.toContain("v0.5.8");
    expect(combinedHtml).not.toContain("v0.6.0 决策矩阵");
    expect(combinedHtml).not.toMatch(/[杩鏂鐢绋鐘宀]/);
  });

  it("renders draft run detail as a product action page without CLI paths", async () => {
    const runsDir = await createTempRunsDir();
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;
    const draft = await createRunDraft({
      candidateId: "cand-001",
      label: "Draft upload",
      cvFiles: [new File(["resume"], "resume.md", { type: "text/markdown" })],
      jdFiles: [new File(["jd"], "jd.md", { type: "text/markdown" })],
      jdFileDisplayNames: ["Example - Draft Role"],
      now: new Date("2026-04-25T08:30:00.000Z"),
    });

    const html = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId: draft.runId }) }));

    expect(html).toContain("开始评估");
    expect(html).toContain("投递名称");
    expect(html).toContain("Example - Draft Role");
    expect(html).toContain("草稿");
    expect(html).not.toContain("JD 详情");
    expect(html).not.toContain("查看 JD 详情");
    expect(html).not.toContain("JD 原文");
    expect(html).not.toContain("shotguncv run");
    expect(html).not.toContain("input_files/cv");
    expect(html).not.toContain("输入来源");
  });

  it("renders JD text preview on the run detail page without exposing source paths", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-full");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const detail = await loadRunDetail("demo-full");
    const html = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId: "demo-full" }) }));

    expect(detail.inputSources).toEqual([
      expect.objectContaining({
        role: "cv",
        sourceOrigin: "fixture",
        originalName: "base_resume.md",
        relativePath: "fixtures/candidates/base_resume.md",
        sizeBytes: 1234,
        extractionStatus: "extracted",
      }),
      expect.objectContaining({
        role: "jd",
        sourceOrigin: "fixture",
        displayName: "Example AI - LLM Product Engineer",
        originalName: "sample_batch.txt",
        relativePath: "fixtures/jds/sample_batch.txt",
        sizeBytes: 2345,
        extractionStatus: "extracted",
      }),
    ]);
    expect(detail.jdInputPreviews[0]).toMatchObject({
      label: "Example AI - LLM Product Engineer",
      kind: "text",
      text: "jd text",
    });
    expect(html).toContain("岗位描述详情");
    expect(html).not.toContain("JD 详情");
    expect(html).toContain("岗位描述原文");
    expect(html).not.toContain("JD 原文");
    expect(html).toContain("jd text");
    expect(html).toContain("Example AI - LLM Product Engineer");
    expect(html).not.toContain("输入来源");
    expect(html).not.toContain("fixture");
    expect(html).not.toContain("base_resume.md");
    expect(html).not.toContain("fixtures/candidates/base_resume.md");
  });

  it("renders uploaded JD screenshots as enlargeable previews", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-full");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;
    const runDir = path.join(runsDir, "demo-full");
    await mkdir(path.join(runDir, "input_files", "jd"), { recursive: true });
    await writeFile(path.join(runDir, "input_files", "jd", "jd-scan.png"), Buffer.from([137, 80, 78, 71]));
    const manifestPath = path.join(runsDir, "demo-full", "ingest", "manifest.json");
    const manifest = JSON.parse(await readFile(manifestPath, "utf-8"));
    manifest.jd_inputs = [
      {
        role: "jd",
      source_origin: "upload",
      source_type: "file",
        display_name: "Example AI - Screenshot JD",
        source_value: path.join(runDir, "input_files", "jd", "jd-scan.png"),
        original_name: "jd-scan.png",
        relative_path: "input_files/jd/jd-scan.png",
      size_bytes: 3456,
        media_type: "image/png",
      text: "",
      extraction_status: "unparseable",
      extraction_provider: "local_ocr",
        extraction_error: "",
      },
    ];
    await writeFile(manifestPath, JSON.stringify(manifest, null, 2), "utf-8");

    const detail = await loadRunDetail("demo-full");
    const html = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId: "demo-full" }) }));

    expect(detail.jdInputPreviews[0]).toMatchObject({
      label: "Example AI - Screenshot JD",
      kind: "image",
      contentType: "image/png",
    });
    expect(detail.jdInputPreviews[0].imageDataUrl).toContain("data:image/png;base64,");
    expect(html).toContain("Example AI - Screenshot JD");
    expect(html).toContain("放大查看 Example AI - Screenshot JD");
    expect(html).toContain(`href="/runs/demo-full/jd-preview/0"`);
    expect(html).toContain("data:image/png;base64,");
    expect(html).not.toContain("input_files/jd/jd-scan.png");

    const previewHtml = renderToStaticMarkup(
      await JdImagePreviewPage({ params: Promise.resolve({ runId: "demo-full", index: "0" }) }),
    );
    expect(previewHtml).toContain("岗位描述图片预览");
    expect(previewHtml).not.toContain("JD 图片预览");
    expect(previewHtml).toContain("返回评估详情");
    expect(previewHtml).toContain("Example AI - Screenshot JD");
  });

  it("renders the upload page as a three-step draft workflow", () => {
    const html = renderToStaticMarkup(UploadPage());

    expect(html).toContain("创建投递草稿");
    expect(html).not.toContain("仅创建草稿");
    expect(html).toContain("三步创建草稿");
    expect(html).toContain("1 候选人材料");
    expect(html).toContain("2 岗位输入");
    expect(html).toContain("3 草稿确认");
    expect(html).not.toContain("candidateId");
    expect(html).not.toContain("name=\"label\"");
    expect(html).toContain("cvFiles");
    expect(html).toContain("jdFiles");
    expect(html).toContain("本地文件");
    expect(html).toContain("粘贴文本");
    expect(html).toContain("公司/岗位显示名");
    expect(html).toContain("选择本地简历文件（可多选）");
    expect(html).toContain("将简历文件拖拽到此区域");
    expect(html).toContain("选择本地岗位文件（可多选）");
    expect(html).toContain("数据存储位置");
  });

  it("renders run detail page with product empty evaluation messaging", async () => {
    const runsDir = await createTempRunsDir();
    await createIncompleteRun(runsDir, "demo");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId: "demo" }) }));

    expect(html).toContain("评估结果尚未生成");
    expect(html).toContain("完成本地评估后");
    expect(html).not.toContain("生成阶段");
    expect(html).not.toContain("阶段未完成");
  });

  it("hides raw variant identifiers from the evaluation detail page", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-full");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId: "demo-full" }) }));

    expect(html).toContain("岗位定制版本");
    expect(html).not.toContain("variant-jd-jd-001");
  });

  it("does not render generated artifact cards on the evaluation detail page", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-full");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId: "demo-full" }) }));

    expect(html).not.toContain('id="variant-variant-jd-jd-001"');
    expect(html).not.toContain('<p class="pill">岗位定制版本</p>');
  });

  it("renders scorecards as a v0.6 operational priority matrix", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-full");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId: "demo-full" }) }));

    expect(html).toContain("评估结果");
    expect(html).toContain("决策分");
    expect(html).toContain("匹配维度");
    expect(html).toContain("证据引用");
    expect(html).toContain("风险解释");
    expect(html).toContain("81%");
    expect(html).not.toContain("移动端改成可纵向扫描的决策卡");
  });

  it("renders v0.5.7 gate status and three-score labels", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-v057", { includeV057Artifacts: true });
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId: "demo-v057" }) }));

    expect(html).toContain("匹配度");
    expect(html).toContain("补强空间");
    expect(html).toContain("风险");
  });

  it("does not link matrix rows to raw customized resume anchors", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-full");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId: "demo-full" }) }));

    expect(html).not.toContain('href="#variant-variant-jd-jd-001"');
    expect(html).not.toContain("打开对应定制简历");
  });

  it("moves fit analysis and application advice into matrix row expanders", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-full");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId: "demo-full" }) }));

    expect(html).toContain("适配度");
    expect(html).toContain("投递建议");
    expect(html).toContain("决策驱动");
    expect(html).not.toContain("阶段计划");
    expect(html).not.toContain("评估解释：");
  });

  it("renders explanation empty state for legacy evaluate artifacts", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-legacy", { includeExplanations: false });
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId: "demo-legacy" }) }));

    expect(html).toContain("适配度");
    expect(html).toContain("当前运行未生成评估解释文件");
  });

  it("renders report page markdown with structured interview prep summary", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-full");
    await writeFile(
      path.join(runsDir, "demo-full", "report", "summary.md"),
      "# ShotgunCV v0.3.0 LLM Eval Summary\n\n- gate: hard_gate_missing\n- review: needs_review\n- Top Evidence: 围绕 LLM 辅助工作流搭建过内部工具\n",
      "utf-8",
    );
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await ReportPage({ params: Promise.resolve({ runId: "demo-full" }) }));

    expect(html).toContain("评估摘要");
    expect(html).not.toContain("ShotgunCV v0.3.0 LLM Eval Summary");
    expect(html).toContain("LLM Product Engineer");
    expect(html).toContain("推荐结论");
    expect(html).toContain("关键证据");
    expect(html).toContain("面试前突击内容");
    expect(html).toContain("决策摘要");
    expect(html).toContain("推荐岗位");
    expect(html).toContain("依据完整度");
    expect(html).toContain("原始报告");
    expect(html).toContain("report-source-panel");
    expect(html).not.toContain("来源：");
    expect(html).toContain("报告目录");
    expect(html).toContain("推荐岗位");
    expect(html).toContain("离线评估指标");
    expect(html).toContain("硬性要求缺少证据");
    expect(html).toContain("需要复核");
    expect(html).not.toContain("hard_gate_missing");
    expect(html).not.toContain("needs_review");
    expect(html).not.toContain("主要风险");
  });

  it("renders legacy report and score rows when optional summary arrays are missing", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "legacy-summary-arrays");
    const runDir = path.join(runsDir, "legacy-summary-arrays");
    await writeJson(path.join(runDir, "evaluate", "ranking_explanations.json"), [
      {
        jd_id: "jd-001",
        variant_id: "variant-jd-jd-001",
        ranking_version: "legacy",
        dimension_reasons: { overall: "旧版解释只提供总述。" },
        decision_summary: "旧版摘要",
      },
    ]);
    await writeJson(path.join(runDir, "evaluate", "gap_maps.json"), [
      {
        jd_id: "jd-001",
        candidate_id: "cand-001",
        items: [
          {
            area: "Legacy gap",
            current_state: "partial",
            target_state: "ready",
            priority: "medium",
          },
        ],
      },
    ]);
    await writeJson(path.join(runDir, "plan", "application_strategies.json"), [
      {
        jd_id: "jd-001",
        recommended_variant_id: "variant-jd-jd-001",
        priority_rank: 1,
        apply_decision: "apply",
        needs_jd_specific_variant: true,
        decision_confidence: 0.5,
        resume_revision_tasks: [],
      },
    ]);
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const runHtml = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ runId: "legacy-summary-arrays" }) }));
    const reportHtml = renderToStaticMarkup(await ReportPage({ params: Promise.resolve({ runId: "legacy-summary-arrays" }) }));

    expect(runHtml).toContain("投递建议");
    expect(reportHtml).toContain("投递决策摘要");
    expect(reportHtml).toContain("投递建议：建议投递");
    expect(`${runHtml}\n${reportHtml}`).not.toContain("undefined");
  });

  it("aggregates v0.5.7 evaluation results as JD-level review rows", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-v057", { includeV057Artifacts: true });
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const results = await loadEvaluationResults();

    expect(results).toHaveLength(1);
    expect(results[0]).toMatchObject({
      runId: "demo-v057",
      jdId: "jd-001",
      title: "LLM Product Engineer",
      variantId: "variant-jd-jd-001",
      gateStatus: "pass",
      finalScore: 0.81,
      verifiedFitScore: 0.74,
      rewritePotentialScore: 0.83,
      riskScore: 0.22,
      applyDecision: "apply",
      provider: "openai",
      reportHref: "/runs/demo-v057/report",
      detailHref: "/runs/demo-v057#evaluation-jd-001",
    });
    expect(results[0].evidenceRefs).toContain("围绕 LLM 辅助工作流搭建过内部工具");
    expect(results[0].riskFlags).toContain("缺少大规模 benchmark 经验");
  });

  it("keeps legacy evaluation rows with scorecard fallbacks", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-legacy");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const results = await loadEvaluationResults();

    expect(results).toHaveLength(1);
    expect(results[0]).toMatchObject({
      runId: "demo-legacy",
      jdId: "jd-001",
      gateStatus: "legacy",
      finalScore: 0.81,
      verifiedFitScore: null,
      rewritePotentialScore: null,
      riskScore: 0.42,
      artifactMode: "legacy",
    });
  });

  it("filters and sorts evaluation rows by gate, risk, provider, score, and query", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "safe-run", { includeV057Artifacts: true });
    await createCompleteRun(runsDir, "risky-run", { includeV057Artifacts: true });
    await makeRunRisky(runsDir, "risky-run");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const results = await loadEvaluationResults();
    const filtered = filterEvaluationResults(results, {
      query: "学历硬门槛",
      gate: "blocked",
      risk: "high",
      provider: "openai",
      decision: "manual_review",
      score: "low",
    });
    const sorted = sortEvaluationResults(results, "risk");

    expect(filtered).toHaveLength(1);
    expect(filtered[0].runId).toBe("risky-run");
    expect(sorted[0].runId).toBe("risky-run");
  });

  it("renders the evaluation results page with review table and reachable navigation", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-v057", { includeV057Artifacts: true });
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await EvaluationPage());
    const homeHtml = renderToStaticMarkup(await HomePage());

    expect(html).toContain("岗位评估队列");
    expect(html).toContain("岗位结果");
    expect(html).toContain("需复核");
    expect(html).toContain("高风险岗位");
    expect(html).toContain("历史结果");
    expect(html).toContain("投递建议");
    expect(html).toContain("LLM Product Engineer");
    expect(html).toContain("匹配");
    expect(html).toContain("补强");
    expect(html).toContain("风险");
    expect(html).toContain('href="/runs/demo-v057#evaluation-jd-001"');
    expect(html).toContain('href="/runs/demo-v057/report"');
    expect(homeHtml).toContain("评估结果");
  });

  it("renders an empty evaluation result state when no run has evaluate artifacts", async () => {
    const runsDir = await createTempRunsDir();
    await createIncompleteRun(runsDir, "draft-only");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const results = await loadEvaluationResults();
    const html = renderToStaticMarkup(await EvaluationPage());

    expect(results).toEqual([]);
    expect(html).toContain("暂无评估结果");
    expect(html).toContain("等待投递完成评估");
  });

  it("renders evaluation pagination and score trend summary for dense JD queues", async () => {
    const runsDir = await createTempRunsDir();
    for (let index = 0; index < 12; index += 1) {
      await createCompleteRun(runsDir, `eval-run-${String(index + 1).padStart(2, "0")}`, { includeV057Artifacts: true });
    }
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await EvaluationPage());

    expect(html).toContain("平均最终分");
    expect(html).toContain("平均风险分");
    expect(html).toContain("评估基于最近一次生成结果");
    expect(html).toContain("第 1 / 2 页");
    expect(html).toContain("每页 10 条");
    expect(html).toContain("共 12 条");
  });

  it("loads resume workspace rows with variant and evidence constraint sources", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "resume-v057", { includeV057Artifacts: true });
    await createIncompleteRun(runsDir, "resume-legacy");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const workspace = await loadResumeWorkspace();

    expect(workspace.rows).toHaveLength(2);
    expect(workspace.rows[0]).toMatchObject({
      runId: "resume-v057",
      status: "done",
      variantCount: 1,
      evidenceConstraintCount: 1,
      preflightStatus: "pass",
      nextAction: "查看报告或评估矩阵",
    });
    expect(workspace.rows[0].variants[0]).toMatchObject({
      variantId: "variant-jd-jd-001",
      variantDisplayName: "岗位定制版本（jd-001）",
      safeRewriteItems: ["Keep education and employer facts unchanged."],
      simulatedSupplementItems: ["待核实模拟补强：风控项目复盘"],
      forbiddenGapItems: ["Do not fabricate certificates."],
      sourceLabel: "来源：简历版本",
    });
    expect(workspace.rows[0].constraints[0]).toMatchObject({
      category: "可安全改写",
      requirementText: "本科及以上学历，计算机相关专业",
      sourceLabel: "来源：证据矩阵 / 投递前门槛",
    });
    expect(workspace.rows[1]).toMatchObject({
      runId: "resume-legacy",
      status: "running",
      artifactMode: "legacy",
    });
  });

  it("renders the resume workspace without exposing raw resume or JD text", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "resume-v057", { includeV057Artifacts: true });
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await ResumePage());

    expect(html).toContain("简历优化");
    expect(html).toContain("创建投递草稿");
    expect(html).toContain('href="/upload"');
    expect(html).toContain("岗位定制版本（jd-001）");
    expect(html).toContain("可安全改写");
    expect(html).toContain("待核实模拟补强");
    expect(html).toContain("禁止编造缺口");
    expect(html).toContain("来源：简历版本");
    expect(html).toContain("来源：证据矩阵 / 投递前门槛");
    expect(html).toContain("来源：投递策略 / 运行状态");
    expect(html).not.toContain("resume text");
    expect(html).not.toContain("jd text");
  });

  it("renders a deliverable resume preview with markdown export controls and provenance", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "resume-v010", {
      includeV057Artifacts: true,
      includeGeneratedResume: true,
    });
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const workspace = await loadResumeWorkspace();
    const html = renderToStaticMarkup(await ResumePage());

    expect(workspace.summary.generatedResumeCount).toBe(1);
    expect(workspace.rows[0].generatedResumes[0]).toMatchObject({
      displayName: "Example AI 定制简历",
      exportFileName: "demo-run-example-ai.md",
      targetLabel: "Example AI - LLM Product Engineer",
      isDeliverable: true,
    });
    expect(html).toContain("实时简历预览");
    expect(html).toContain("Example AI 定制简历");
    expect(html).toContain("一键复制 Markdown");
    expect(html).toContain("下载 Markdown");
    expect(html).toContain("候选人：本地候选人");
    expect(html).toContain("证据来源：候选人画像 / 生成产物");
    expect(html).toContain("围绕 LLM 辅助工作流搭建过内部工具");
    expect(html).not.toContain("generated_resumes.json");
    expect(html).not.toContain("target_jd_ids");
  });

  it("marks blocked generated resumes as non-deliverable and keeps them in review mode", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "resume-blocked", {
      includeV057Artifacts: true,
      includeGeneratedResume: true,
      preflightStatus: "blocked",
    });
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const html = renderToStaticMarkup(await ResumePage());

    expect(html).toContain("不可直接投递");
    expect(html).toContain("先补齐阻断证据，再导出投递版本。");
    expect(html).not.toContain('download="demo-run-example-ai.md"');
  });

  it("persists user evidence confirmations as an independent review artifact", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "resume-v011", { includeV057Artifacts: true });
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const response = await postEvidenceOverrideRoute(
      new Request("http://localhost/api/runs/resume-v011/evidence-overrides", {
        method: "POST",
        body: JSON.stringify({
          jdId: "jd-001",
          requirementId: "jd-001-req-001",
          action: "confirm_existing",
          note: "确认简历中的项目经历可用于该硬门槛。",
        }),
      }),
      { params: Promise.resolve({ runId: "resume-v011" }) },
    );
    const body = await response.json();
    const artifact = JSON.parse(
      await readFile(path.join(runsDir, "resume-v011", "review", "user_evidence_overrides.json"), "utf-8"),
    );
    const candidateProfile = await readFile(
      path.join(runsDir, "resume-v011", "analyze", "candidate_profile.json"),
      "utf-8",
    );

    expect(response.status).toBe(200);
    expect(body.savedCount).toBe(1);
    expect(artifact.overrides[0]).toMatchObject({
      jd_id: "jd-001",
      requirement_id: "jd-001-req-001",
      action: "confirm_existing",
      note: "确认简历中的项目经历可用于该硬门槛。",
      source: "user",
    });
    expect(candidateProfile).not.toContain("确认简历中的项目经历可用于该硬门槛。");
  });

  it("loads settings overview from local runs without leaking sensitive values", async () => {
    const runsDir = await createTempRunsDir();
    await createCompleteRun(runsDir, "demo-settings", { includeV057Artifacts: true });
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;
    process.env.OPENAI_API_KEY = "sk-sensitive-test-key";
    const configPath = path.join(runsDir, "demo-settings", "config", "run_config.json");
    const config = JSON.parse(await readFile(configPath, "utf-8"));
    config.openai = {
      base_url: "https://api.openai.com/v1",
      api_key_env: "OPENAI_API_KEY",
      env_file: ".env",
    };
    config.input_extraction = {
      ocr_provider: "local_ocr",
      vision_provider: "openai_vision",
      vision_model: "gpt-5.4-mini",
      ocr_languages: "eng+chi_sim",
    };
    await writeFile(configPath, JSON.stringify(config, null, 2), "utf-8");

    const overview = await loadSettingsOverview();
    const html = renderToStaticMarkup(await SettingsPage());

    expect(overview).toMatchObject({
      runsDirSource: "env",
      runCount: 1,
      configSnapshotCount: 1,
      configIssueCount: 0,
      latestConfig: {
        runId: "demo-settings",
        baseUrlHost: "api.openai.com",
        apiKeyEnv: "OPENAI_API_KEY",
      },
    });
    expect(overview.displayRunsDir).not.toContain(runsDir);
    expect(html).toContain("设置");
    expect(html).toContain("本地设置与环境检查");
    expect(html).toContain("服务地址");
    expect(html).toContain("密钥状态");
    expect(html).toContain("自定义服务");
    expect(html).not.toContain("api.openai.com");
    expect(html).not.toContain("OPENAI_API_KEY");
    expect(html).not.toContain("local_ocr");
    expect(html).not.toContain("openai_vision");
    expect(html).toContain("环境检查");
    expect(html).not.toContain(runsDir);
    expect(html).not.toContain("sk-sensitive-test-key");
    expect(html).not.toContain("resume text");
    delete process.env.OPENAI_API_KEY;
  });

  it("reports empty and missing runs directories on the settings page", async () => {
    const emptyRunsDir = await createTempRunsDir();
    process.env.SHOTGUNCV_RUNS_DIR = emptyRunsDir;

    const emptyOverview = await loadSettingsOverview();
    const emptyHtml = renderToStaticMarkup(await SettingsPage());

    expect(emptyOverview).toMatchObject({
      runCount: 0,
      configSnapshotCount: 0,
      configIssueCount: 0,
    });
    expect(emptyHtml).toContain("暂无运行批次");

    process.env.SHOTGUNCV_RUNS_DIR = path.join(emptyRunsDir, "missing-runs-root");
    const missingOverview = await loadSettingsOverview();
    const missingHtml = renderToStaticMarkup(await SettingsPage());

    expect(missingOverview.runsDirReadable).toBe(false);
    expect(missingHtml).toContain("运行目录不可读");
  });

  it("surfaces missing config, malformed json artifacts, and unknown providers in settings", async () => {
    const runsDir = await createTempRunsDir();
    const missingConfigDir = path.join(runsDir, "missing-config");
    const malformedRunDir = path.join(runsDir, "malformed-run");
    await mkdir(missingConfigDir, { recursive: true });
    await createIncompleteRun(runsDir, "unknown-provider");
    await createCompleteRun(runsDir, "malformed-run");
    const unknownConfigPath = path.join(runsDir, "unknown-provider", "config", "run_config.json");
    const unknownConfig = JSON.parse(await readFile(unknownConfigPath, "utf-8"));
    unknownConfig.analyzer.provider = "unknown";
    await writeFile(unknownConfigPath, JSON.stringify(unknownConfig, null, 2), "utf-8");
    await writeFile(path.join(malformedRunDir, "evaluate", "scorecards.json"), "{broken", "utf-8");
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;

    const overview = await loadSettingsOverview();
    const html = renderToStaticMarkup(await SettingsPage());

    expect(overview.runCount).toBe(3);
    expect(overview.configIssueCount).toBeGreaterThanOrEqual(1);
    expect(overview.artifactIssueCount).toBeGreaterThanOrEqual(1);
    expect(html).toContain("配置缺失或异常");
    expect(html).toContain("产物解析异常");
    expect(html).toContain("unknown-provider");
    expect(html).toContain("unknown");
    expect(html).not.toContain("jd text");
  });

  it("loads missing local env config as a recoverable settings state", async () => {
    const projectRoot = await createTempProjectRoot();

    const config = await loadLocalConfig({ projectRoot });

    expect(config.envExists).toBe(false);
    expect(config.envReadable).toBe(false);
    expect(config.envWritable).toBe(false);
    expect(config.restoreAvailable).toBe(true);
    expect(config.apiKey.configured).toBe(false);
    expect(config.values.openaiApiKey).toBe("");
  });

  it("updates supported env fields without leaking the API key", async () => {
    const projectRoot = await createTempProjectRoot();
    await writeFile(
      path.join(projectRoot, ".env"),
      [
        "# custom header",
        "OPENAI_API_KEY=sk-existing-secret-0000",
        "OPENAI_MODEL=old-model",
        "CUSTOM_FLAG=keep-me",
        "",
      ].join("\n"),
      "utf-8",
    );

    const saved = await saveLocalConfig(
      {
        openaiApiKey: "sk-new-secret-9999",
        openaiBaseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
        openaiModel: "qwen3.6-27b",
        generatorModel: "generator-model",
        judgeModel: "",
        visionModel: "vision-model",
        openaiApiKeyEnv: "OPENAI_API_KEY",
      },
      { projectRoot },
    );
    const envText = await readFile(path.join(projectRoot, ".env"), "utf-8");

    expect(envText).toContain("# custom header");
    expect(envText).toContain("CUSTOM_FLAG=keep-me");
    expect(envText).toContain("OPENAI_API_KEY=sk-new-secret-9999");
    expect(envText).toContain("OPENAI_MODEL=qwen3.6-27b");
    expect(saved.apiKey).toMatchObject({ configured: true, suffix: "9999" });
    expect(saved.values.openaiApiKey).toBe("");
    expect(JSON.stringify(saved)).not.toContain("sk-new-secret-9999");
  });

  it("renders local model configuration on settings without leaking the API key", async () => {
    const runsDir = await createTempRunsDir();
    const projectRoot = await createTempProjectRoot();
    await writeFile(
      path.join(projectRoot, ".env"),
      "OPENAI_API_KEY=sk-page-secret-7777\nOPENAI_BASE_URL=https://api.openai.com/v1\nOPENAI_MODEL=gpt-5.4-mini\n",
      "utf-8",
    );
    process.env.SHOTGUNCV_RUNS_DIR = runsDir;
    process.env.SHOTGUNCV_WEB_PROJECT_ROOT = projectRoot;

    const html = renderToStaticMarkup(await SettingsPage());

    expect(html).toContain("本地模型配置");
    expect(html).toContain("密钥与模型运行参数");
    expect(html).toContain("环境健康");
    expect(html).toContain("本地配置边界");
    expect(html).toContain("密钥状态");
    expect(html).toContain("local-config-field-with-icon");
    expect(html).toContain("已配置 · ****7777");
    expect(html).not.toContain("api.openai.com");
    expect(html).not.toContain("gpt-5.4-mini");
    expect(html).not.toContain("OCR 语言");
    expect(html).not.toContain("eng+chi_sim");
    expect(html).not.toContain("sk-page-secret-7777");
  });

  it("preserves an existing API key unless the clear action sends an empty value", async () => {
    const projectRoot = await createTempProjectRoot();
    await writeFile(path.join(projectRoot, ".env"), "OPENAI_API_KEY=sk-preserve-1234\nOPENAI_MODEL=old\n", "utf-8");

    await saveLocalConfig({ openaiModel: "new-model" }, { projectRoot });
    let envText = await readFile(path.join(projectRoot, ".env"), "utf-8");
    expect(envText).toContain("OPENAI_API_KEY=sk-preserve-1234");

    await saveLocalConfig({ openaiApiKey: "" }, { projectRoot });
    envText = await readFile(path.join(projectRoot, ".env"), "utf-8");
    expect(envText).toContain("OPENAI_API_KEY=");
    expect(envText).not.toContain("sk-preserve-1234");
  });

  it("rejects invalid local env config inputs with stable error codes", async () => {
    const projectRoot = await createTempProjectRoot();
    await writeFile(path.join(projectRoot, ".env"), "OPENAI_API_KEY=\n", "utf-8");

    await expect(saveLocalConfig({ openaiBaseUrl: "not a url" }, { projectRoot })).rejects.toMatchObject({
      code: "invalid_base_url",
    });
    await expect(saveLocalConfig({ openaiApiKeyEnv: "OPENAI API KEY" }, { projectRoot })).rejects.toMatchObject({
      code: "invalid_key_env",
    });
  });

  it("restores the default env structure without copying a real key", async () => {
    const projectRoot = await createTempProjectRoot();
    await writeFile(path.join(projectRoot, ".env"), "OPENAI_API_KEY=sk-real-key-5555\nCUSTOM_FLAG=remove\n", "utf-8");

    const restored = await resetLocalConfig({ projectRoot });
    const envText = await readFile(path.join(projectRoot, ".env"), "utf-8");

    expect(envText).toContain("# Project-level model runtime settings");
    expect(envText).toContain("OPENAI_API_KEY=");
    expect(envText).not.toContain("sk-real-key-5555");
    expect(envText).not.toContain("CUSTOM_FLAG=remove");
    expect(restored.apiKey.configured).toBe(false);
  });

  it("serves local config API responses without returning the full API key", async () => {
    const projectRoot = await createTempProjectRoot();
    await writeFile(path.join(projectRoot, ".env"), "OPENAI_API_KEY=sk-route-secret-8888\nOPENAI_MODEL=old\n", "utf-8");
    process.env.SHOTGUNCV_WEB_PROJECT_ROOT = projectRoot;

    const putResponse = await putLocalConfigRoute(
      new Request("http://localhost/api/settings/local-config", {
        method: "PUT",
        body: JSON.stringify({ openaiApiKey: "sk-route-secret-9999", openaiModel: "new-model" }),
      }),
    );
    const putBody = await putResponse.json();
    const getBody = await (await getLocalConfigRoute()).json();

    expect(putResponse.status).toBe(200);
    expect(putBody.apiKey).toMatchObject({ configured: true, suffix: "9999" });
    expect(getBody.values.openaiApiKey).toBe("");
    expect(getBody.values.openaiModel).toBe("new-model");
    expect(JSON.stringify(getBody)).not.toContain("sk-route-secret-9999");
    expect(JSON.stringify(getBody)).not.toContain(projectRoot);
  });

  it("restores local config through the API route", async () => {
    const projectRoot = await createTempProjectRoot();
    await writeFile(path.join(projectRoot, ".env"), "OPENAI_API_KEY=sk-route-secret-1111\nCUSTOM_FLAG=remove\n", "utf-8");
    process.env.SHOTGUNCV_WEB_PROJECT_ROOT = projectRoot;

    const response = await resetLocalConfigRoute();
    const body = await response.json();
    const envText = await readFile(path.join(projectRoot, ".env"), "utf-8");

    expect(response.status).toBe(200);
    expect(body.apiKey.configured).toBe(false);
    expect(envText).not.toContain("sk-route-secret-1111");
    expect(envText).not.toContain("CUSTOM_FLAG=remove");
  });
});


async function createTempRunsDir(): Promise<string> {
  return mkdtemp(path.join(tmpdir(), "shotguncv-runs-"));
}


async function createTempProjectRoot(): Promise<string> {
  const projectRoot = await mkdtemp(path.join(tmpdir(), "shotguncv-project-"));
  await writeFile(
    path.join(projectRoot, ".env.example"),
    [
      "# Project-level model runtime settings",
      "OPENAI_API_KEY=",
      "OPENAI_BASE_URL=",
      "OPENAI_MODEL=",
      "SHOTGUNCV_GENERATOR_MODEL=",
      "SHOTGUNCV_JUDGE_MODEL=",
      "SHOTGUNCV_VISION_MODEL=",
      "SHOTGUNCV_OCR_LANGUAGES=chi+eng",
      "OPENAI_API_KEY_ENV=",
      "",
    ].join("\n"),
    "utf-8",
  );
  return projectRoot;
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
    candidate_inputs: [
      {
        role: "cv",
        source_origin: "fixture",
        source_type: "file",
        source_value: "fixtures/candidates/base_resume.md",
        original_name: "base_resume.md",
        relative_path: "fixtures/candidates/base_resume.md",
        size_bytes: 1234,
        media_type: "text/markdown",
        text: "resume text",
        extraction_status: "extracted",
        extraction_provider: "local_text",
        extraction_error: "",
      },
    ],
    jd_inputs: [
      {
        role: "jd",
        source_origin: "fixture",
        source_type: "file",
        source_value: "fixtures/jds/sample_batch.txt",
        display_name: "Example AI - LLM Product Engineer",
        original_name: "sample_batch.txt",
        relative_path: "fixtures/jds/sample_batch.txt",
        size_bytes: 2345,
        media_type: "text/plain",
        text: "jd text",
        content: "jd text",
        extraction_status: "extracted",
        extraction_provider: "local_text",
        extraction_error: "",
      },
    ],
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
  options?: {
    includeExplanations?: boolean;
    includeV057Artifacts?: boolean;
    includeGeneratedResume?: boolean;
    preflightStatus?: "pass" | "blocked" | "needs_review";
  },
): Promise<void> {
  const includeExplanations = options?.includeExplanations ?? true;
  const preflightStatus = options?.preflightStatus ?? "pass";
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
      safe_rewrites: options?.includeV057Artifacts ? ["Keep education and employer facts unchanged."] : undefined,
      simulated_supplements: options?.includeV057Artifacts ? ["待核实模拟补强：风控项目复盘"] : undefined,
      forbidden_gaps: options?.includeV057Artifacts ? ["Do not fabricate certificates."] : undefined,
    },
  ]);
  if (options?.includeV057Artifacts) {
    await writeJson(path.join(runDir, "analyze", "requirement_matrix.json"), [
      {
        jd_id: "jd-001",
        requirement_id: "jd-001-req-001",
        tier: "hard_gate",
        requirement_text: "本科及以上学历，计算机相关专业",
        evidence_status: "verified",
        evidence_refs: ["Bachelor degree in Computer Science"],
        fabrication_policy: "never_fabricate",
        risk_weight: 1,
      },
    ]);
    await writeJson(path.join(runDir, "analyze", "preflight_gates.json"), [
      {
        jd_id: "jd-001",
        status: preflightStatus,
        reasons: preflightStatus === "pass" ? [] : ["缺少可验证硬门槛证据"],
        skipped_stages: [],
        user_action: preflightStatus === "pass" ? "" : "补充或确认硬门槛证据",
      },
    ]);
  }
  if (options?.includeGeneratedResume) {
    await writeJson(path.join(runDir, "generate", "generated_resumes.json"), [
      {
        resume_id: "resume-jd-001",
        display_name: "Example AI 定制简历",
        target_jd_id: "jd-001",
        target_variant_id: "variant-jd-jd-001",
        status: preflightStatus === "pass" ? "deliverable" : "needs_review",
        markdown: [
          "# 本地候选人",
          "",
          "## 摘要",
          "围绕 LLM 辅助工作流搭建过内部工具，能够支持评估流程建设。",
          "",
          "## 技能",
          "- LLM workflows",
          "- evaluation",
          "",
          "## 经历",
          "- 围绕 LLM 辅助工作流搭建过内部工具",
        ].join("\n"),
        sections: [
          {
            title: "摘要",
            content: "围绕 LLM 辅助工作流搭建过内部工具，能够支持评估流程建设。",
            evidence_refs: ["围绕 LLM 辅助工作流搭建过内部工具"],
            rewrite_strategy: "证据内强化表达",
            verification_status: "verified",
          },
          {
            title: "技能",
            content: "LLM workflows, evaluation",
            evidence_refs: ["LLM workflows"],
            rewrite_strategy: "关键词对齐",
            verification_status: "verified",
          },
        ],
        forbidden_items: ["Do not fabricate certificates."],
        to_verify_items: preflightStatus === "pass" ? [] : ["缺少可验证硬门槛证据"],
        provenance: {
          candidate_evidence: ["围绕 LLM 辅助工作流搭建过内部工具"],
          generated_from: ["候选人画像", "简历版本", "证据矩阵"],
          user_confirmations: [],
        },
      },
    ]);
  }
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
      verified_fit_score: options?.includeV057Artifacts ? 0.74 : undefined,
      rewrite_potential_score: options?.includeV057Artifacts ? 0.83 : undefined,
      risk_score: options?.includeV057Artifacts ? 0.22 : undefined,
      gate_status: options?.includeV057Artifacts ? "pass" : undefined,
      gate_reasons: options?.includeV057Artifacts ? [] : undefined,
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
      recommended_actions: ["投递前补齐离线评估指标表达"],
      catch_up_notes: ["面试前复习离线评估指标"],
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


async function makeRunRisky(runsDir: string, runId: string): Promise<void> {
  const runDir = path.join(runsDir, runId);
  await writeJson(path.join(runDir, "analyze", "preflight_gates.json"), [
    {
      jd_id: "jd-001",
      status: "blocked",
      reasons: ["学历硬门槛缺失"],
      skipped_stages: ["generate", "evaluate", "plan"],
      user_action: "补充学历证据后再评估",
    },
  ]);
  await writeJson(path.join(runDir, "analyze", "requirement_matrix.json"), [
    {
      jd_id: "jd-001",
      requirement_id: "jd-001-req-001",
      tier: "hard_gate",
      requirement_text: "学历硬门槛：本科及以上学历，计算机相关专业",
      evidence_status: "missing",
      evidence_refs: [],
      fabrication_policy: "never_fabricate",
      risk_weight: 1,
    },
  ]);
  await writeJson(path.join(runDir, "evaluate", "scorecards.json"), [
    {
      jd_id: "jd-001",
      variant_id: "variant-jd-jd-001",
      fit_score: 0.31,
      ats_score: 0.4,
      evidence_score: 0.2,
      stretch_score: 0.6,
      gap_risk_score: 0.88,
      rewrite_cost_score: 0.7,
      overall_score: 0.44,
      ranking_version: "v0.5.7-gated",
      judge_rationale: "学历硬门槛缺失，需要人工复核。",
      llm_role_fit_score: 0,
      llm_evidence_score: 0,
      llm_persuasion_score: 0,
      llm_risk_score: 0,
      llm_overall_score: 0,
      final_overall_score: 0.44,
      final_decision_source: "preflight-gate",
      guardrail_flags: ["hard_gate_missing"],
      provider: "openai",
      model: "gpt-5.4-mini",
      verified_fit_score: 0.31,
      rewrite_potential_score: 0.58,
      risk_score: 0.88,
      gate_status: "blocked",
      gate_reasons: ["学历硬门槛缺失"],
    },
  ]);
  await writeJson(path.join(runDir, "evaluate", "ranking_explanations.json"), [
    {
      jd_id: "jd-001",
      variant_id: "variant-jd-jd-001",
      ranking_version: "v0.5.7-gated",
      dimension_reasons: {
        overall: "学历硬门槛缺失，需要人工复核。",
      },
      positive_signals: ["项目经验可迁移"],
      risk_flags: ["学历硬门槛缺失"],
      evidence_refs: [],
      decision_summary: "先补证据，不建议直接投递。",
    },
  ]);
  await writeJson(path.join(runDir, "plan", "application_strategies.json"), [
    {
      jd_id: "jd-001",
      recommended_variant_id: "variant-jd-jd-001",
      priority_rank: 9,
      apply_decision: "manual_review",
      reason_summary: "学历硬门槛缺失，需要人工复核。",
      needs_jd_specific_variant: false,
      decision_drivers: ["先补齐硬门槛证据"],
      watchouts: ["学历硬门槛缺失"],
      recommended_actions: ["补充学历证明后重跑"],
      catch_up_notes: [],
      decision_confidence: 0.44,
      interview_prep_points: [],
      resume_revision_tasks: [],
    },
  ]);
  await writeJson(path.join(runDir, "evaluate", "eval_summary.json"), [
    {
      jd_id: "jd-001",
      title: "Risky AI Manager",
      top_variant_id: "variant-jd-jd-001",
      gap_count: 3,
      top_reasons: ["项目经验可迁移"],
    },
  ]);
}


async function writeJson(filePath: string, payload: unknown): Promise<void> {
  await writeFile(filePath, JSON.stringify(payload, null, 2), "utf-8");
}


async function waitForRunStatus(statusPath: string, expectedStatus: string): Promise<void> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const status = JSON.parse(await readFile(statusPath, "utf-8")) as { status?: string };
    if (status.status === expectedStatus) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
}
