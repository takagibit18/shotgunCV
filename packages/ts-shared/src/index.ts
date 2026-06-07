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
  safe_rewrites?: string[];
  simulated_supplements?: string[];
  forbidden_gaps?: string[];
};

export type ResumeBasics = {
  full_name: string;
  headline?: string;
  location?: string;
  email?: string;
  phone?: string;
  links?: string[];
};

export type ResumeEntry = {
  id: string;
  title: string;
  organization?: string;
  period?: string;
  bullets: string[];
};

export type CustomizedResumeDocument = {
  basics: ResumeBasics;
  summary: string;
  skills: string[];
  experiences: ResumeEntry[];
  projects: ResumeEntry[];
  education: ResumeEntry[];
  certifications: string[];
};

export type ResumeProvenance = {
  field_sources: Record<string, string[]>;
  to_verify_fields: string[];
  forbidden_fields: string[];
};

export type GeneratedResume = {
  resume_id?: string;
  display_name?: string;
  target_jd_id?: string;
  target_variant_id?: string;
  status?: "deliverable" | "needs_review" | "blocked" | string;
  document?: CustomizedResumeDocument;
  provenance?: ResumeProvenance;
  markdown?: string;
  sections?: Array<{
    title?: string;
    content?: string;
    evidence_refs?: string[];
    rewrite_strategy?: string;
    verification_status?: string;
  }>;
  forbidden_items?: string[];
  to_verify_items?: string[];
};

export type RequirementEvidence = {
  jd_id: string;
  requirement_id: string;
  tier: "hard_gate" | "high_priority" | "medium_priority" | "nice_to_have" | string;
  requirement_text: string;
  evidence_status: "verified" | "inferred" | "missing" | "mismatch" | "simulatable" | "forbidden_to_fabricate" | string;
  evidence_refs: string[];
  fabrication_policy: "never_fabricate" | "rewrite_only" | "simulate_allowed" | string;
  risk_weight: number;
};

export type PreflightGate = {
  jd_id: string;
  status: "pass" | "blocked" | "needs_review" | string;
  reasons: string[];
  skipped_stages: string[];
  user_action: string;
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
  verified_fit_score?: number;
  rewrite_potential_score?: number;
  risk_score?: number;
  gate_status?: "pass" | "blocked" | "needs_review" | string;
  gate_reasons?: string[];
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
  input_extraction?: {
    ocr_provider: string;
    vision_provider: string;
    vision_model: string;
    ocr_languages: string;
  };
  run_metadata: RunMetadata;
};

export type EvalSummaryItem = {
  jd_id: string;
  title: string;
  top_variant_id: string;
  gap_count: number;
  top_reasons: string[];
};

export type RunDraftStatus = "draft" | "queued" | "running" | "done" | "failed" | "partial_failed" | "ingest-ready";

export type StageName = "ingest" | "analyze" | "generate" | "evaluate" | "plan" | "report";
export type TimelineStageName = StageName | "review";

export type StageStatus = {
  stage: StageName;
  status: "complete" | "running" | "failed" | "pending";
};

export type RunStatusFile = {
  status: "draft" | "queued" | "running" | "done" | "failed" | "partial_failed";
  status_kind?: "success" | "running" | "failed" | "partial_failed" | "config_error" | "model_error" | "parse_error" | string;
  current_stage: StageName | null;
  started_at: string | null;
  finished_at: string | null;
  error_stage: StageName | null;
  error_code?: string | null;
  error_summary: string | null;
  last_action: "run" | "retry_full" | "resume_failed" | "draft_update" | "delete";
  quality_status?: "ok" | "warning" | "failed";
  quality_summary?: string | null;
};

export type RunTimelineEvent = {
  timestamp: string;
  event:
    | "run_started"
    | "run_finished"
    | "stage_started"
    | "stage_finished"
    | "stage_failed"
    | "input_resolved"
    | "input_extracted"
    | "model_resolved"
    | "llm_call_started"
    | "llm_call_finished"
    | "llm_call_failed"
    | "tool_call_started"
    | "tool_call_finished"
    | "tool_call_failed"
    | "agent_reasoning_summary"
    | "quality_gate_checked"
    | "pipeline_stage_status"
    | "fallback_used"
    | "graph_node_started"
    | "graph_node_finished"
    | "retrieval_query";
  stage?: TimelineStageName;
  stage_key?: string;
  status?: string;
  duration_ms?: number;
  error_code?: string;
  error_category?: string | null;
  error_summary?: string;
  trigger_entrypoint?: string;
  input_scale?: Record<string, number>;
  model_config?: Record<string, { provider: string; model: string }>;
  cli_command_summary?: string[];
  role?: string;
  provider?: string;
  configured_model?: string;
  resolved_model?: string;
  base_url_host?: string | null;
  operation?: string;
  model?: string;
  prompt_tokens?: number | null;
  prompt_chars?: number | null;
  timeout_sec?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
  output_parse_status?: string;
  tool?: string;
  input_type?: string;
  output_summary?: Record<string, unknown>;
  gate?: string;
  checks?: Record<string, unknown>;
  action?: string;
  from_provider?: string;
  to_provider?: string;
  reason?: string;
  summary?: string;
  decision_inputs?: string[];
  graph?: string;
  graph_runtime?: string;
  node?: string;
  run_id?: string;
  jd_id?: string | null;
  jd_count?: number;
  input_summary?: Record<string, unknown>;
  query_preview?: string;
  query_chars?: number;
  retriever_type?: string;
  retrieval_scope?: string;
  filters?: Record<string, unknown>;
  limit?: number;
  hit_count?: number;
  raw_hit_count?: number;
  unique_hit_count?: number;
  miss?: boolean;
  score_distribution?: {
    min: number;
    max: number;
    mean: number;
    median: number;
  } | null;
  hit_source_refs?: Array<{
    source_type: string | null;
    source_id: string | null;
    score: number;
  }> | null;
  source_type_hit_counts?: Record<string, number> | null;
  source_type_available_counts?: Record<string, number>;
  supporting_hit_count?: number | null;
  precision?: number | null;
  hit_rate?: number | null;
  cli_cv_sources?: number;
  cli_jd_sources?: number;
  resolved_cv_files?: number;
  resolved_jd_files?: number;
  jd_text_blocks?: number;
};

export type UploadedInputFile = {
  role: "cv" | "jd";
  originalName: string;
  displayName?: string;
  storedRelativePath: string;
  sizeBytes: number;
  contentType: string;
  uploadedAt: string;
};

export type UploadManifest = {
  schemaVersion: "v0.5.1-upload-manifest";
  candidateId: string;
  label: string;
  createdAt: string;
  files: UploadedInputFile[];
  nextCommand: string;
};
