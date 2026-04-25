export type CandidateProfile = {
  candidate_id: string;
  base_resume_path: string;
  experiences: string[];
  projects: string[];
  skills: string[];
  industry_tags: string[];
  strengths: string[];
  constraints: string[];
  preferences: string[];
  core_claims: string[];
  verified_evidence: string[];
  missing_evidence_areas: string[];
  preferred_role_tracks: string[];
};

export type JDProfile = {
  jd_id: string;
  title: string;
  company: string;
  cluster: string;
  responsibilities: string[];
  requirements: string[];
  keywords: string[];
  seniority: string;
  bonuses: string[];
  risk_signals: string[];
  source_type: string;
  source_value: string;
  must_have_requirements: string[];
  nice_to_have_requirements: string[];
  hidden_signals: string[];
  interview_focus_areas: string[];
  role_level_confidence: number;
};

export type ResumeVariant = {
  variant_id: string;
  variant_type: string;
  cluster: string;
  target_jd_ids: string[];
  summary: string;
  emphasized_strengths: string[];
  stretch_points: string[];
  source_resume_path: string;
};

export type ScoreCard = {
  jd_id: string;
  variant_id: string;
  fit_score: number;
  ats_score: number;
  evidence_score: number;
  stretch_score: number;
  gap_risk_score: number;
  rewrite_cost_score: number;
  overall_score: number;
  ranking_version: string;
  judge_rationale: string;
  llm_role_fit_score: number;
  llm_evidence_score: number;
  llm_persuasion_score: number;
  llm_risk_score: number;
  llm_overall_score: number;
  final_overall_score: number;
  final_decision_source: string;
  guardrail_flags: string[];
  provider: string;
  model: string;
};

export type LLMAssessment = {
  jd_id: string;
  variant_id: string;
  role_fit: number;
  evidence_quality: number;
  persuasiveness: number;
  interview_pressure_risk: number;
  application_worthiness: string;
  must_fix_issues: string[];
  evidence_citations: string[];
  rewrite_opportunities: string[];
  decision_rationale: string;
  provider: string;
  model: string;
};

export type RankingExplanation = {
  jd_id: string;
  variant_id: string;
  ranking_version: string;
  dimension_reasons: Record<string, string>;
  positive_signals: string[];
  risk_flags: string[];
  evidence_refs: string[];
  decision_summary: string;
};

export type GapItem = {
  area: string;
  current_state: string;
  target_state: string;
  priority: string;
  catch_up_concepts: string[];
  weak_points: string[];
};

export type GapMap = {
  jd_id: string;
  candidate_id: string;
  items: GapItem[];
};

export type ApplicationStrategy = {
  jd_id: string;
  recommended_variant_id: string;
  priority_rank: number;
  apply_decision: string;
  reason_summary: string;
  needs_jd_specific_variant: boolean;
  decision_drivers: string[];
  watchouts: string[];
  recommended_actions: string[];
  catch_up_notes: string[];
  decision_confidence: number;
  interview_prep_points: string[];
  resume_revision_tasks: string[];
};

export type ProviderConfig = {
  provider: "deterministic" | "openai" | "openai-compatible";
  model: string;
};

export type OpenAIConfig = {
  base_url: string | null;
  api_key_env: string;
  env_file?: string;
};

export type RunMetadata = {
  label: string;
};

export type RunConfig = {
  analyzer: ProviderConfig;
  generator: ProviderConfig;
  judge: ProviderConfig;
  planner: ProviderConfig;
  openai: OpenAIConfig;
  run_metadata: RunMetadata;
};

export type EvalSummaryItem = {
  jd_id: string;
  title: string;
  top_variant_id: string;
  gap_count: number;
  top_reasons: string[];
};

export type RunDraftStatus = "draft" | "ingest-ready" | "running" | "complete";

export type UploadedInputFile = {
  role: "cv" | "jd";
  originalName: string;
  storedRelativePath: string;
  sizeBytes: number;
  contentType: string;
  uploadedAt: string;
};

export type UploadManifest = {
  schemaVersion: "v0.4.0-upload-draft";
  candidateId: string;
  label: string;
  createdAt: string;
  files: UploadedInputFile[];
  nextCommand: string;
};
