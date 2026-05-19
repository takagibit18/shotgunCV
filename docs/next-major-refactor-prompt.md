# ShotgunCV Next Major Refactor Prompt

You are working in the `shotgunCV` repository. Design and implement the next major refactor as a database-backed RAG and agent workflow expansion of the existing product, while preserving the current pipeline-first architecture.

## Goal

Extend ShotgunCV from a local artifact-only Resume Ops pipeline into a structured career-memory and JD-decision system that combines:

- PostgreSQL-backed persistence for runs, candidates, JD inputs, artifacts, scorecards, application strategies, and user feedback.
- Vector retrieval for JD similarity, candidate evidence recall, project-material recall, and interview-preparation context.
- LangChain-based RAG components for document loading, chunking, retrieval, reranking hooks, and structured generation wrappers.
- A new LangGraph-based review/reflection agent for post-run application review, interview preparation, and feedback-driven improvement.

The refactor must make the system more production-relevant without turning it into an automatic application bot or a generic job-search crawler.

## Current Architecture To Preserve

ShotgunCV is currently a Python-first, pipeline-first, local single-user system. The durable business pipeline remains:

```text
ingest -> analyze -> generate -> evaluate -> plan -> report
```

The current `run_dir` artifact contract remains valid:

- `config/run_config.json`
- `ingest/manifest.json`
- `analyze/candidate_profile.json`
- `analyze/jd_profiles.json`
- `analyze/requirement_matrix.json`
- `analyze/preflight_gates.json`
- `generate/resume_variants.json`
- `evaluate/scorecards.json`
- `evaluate/gap_maps.json`
- `evaluate/ranking_explanations.json`
- `evaluate/eval_summary.json`
- `plan/application_strategies.json`
- `report/summary.md`
- `logs/run_events.jsonl`

The Python pipeline remains the source of truth for business execution. The web app remains a local workbench and must not duplicate pipeline business logic.

## Target Modules

### 1. Database Projection Layer

Add a database projection layer that can index existing `run_dir` artifacts into PostgreSQL.

Required entities:

- `candidates`
- `candidate_sources`
- `jd_inputs`
- `companies`
- `runs`
- `run_artifacts`
- `resume_variants`
- `requirement_evidence`
- `preflight_gates`
- `scorecards`
- `gap_maps`
- `ranking_explanations`
- `application_strategies`
- `application_feedback`
- `retrieval_chunks`

The first implementation should treat PostgreSQL as a read/query projection of existing artifacts, not as a replacement for `run_dir`.

Required task:

```text
shotguncv index --runs-dir ./runs
```

This command must read existing run artifacts, normalize them, and upsert them into the database idempotently.

### 2. Vector Retrieval Layer

Add vector retrieval for:

- JD similarity search.
- Candidate experience and project evidence recall.
- Resume-variant evidence recall.
- Interview-preparation question context.
- Historical feedback recall.

Preferred first implementation:

- PostgreSQL + pgvector.

Acceptable abstraction:

- Implement a retriever interface that can later support Qdrant, but do not introduce Qdrant as the default unless there is a clear need.

Chunk sources:

- Candidate resume facts.
- Candidate project materials.
- JD descriptions.
- Requirement evidence.
- Gap maps.
- Application feedback.
- Interview prep notes.

Each chunk must keep metadata for:

- source type
- source id
- candidate id
- JD id when applicable
- run id when applicable
- artifact path when applicable
- provenance summary

### 3. LangChain RAG Components

Use LangChain where it reduces custom glue code around RAG.

Allowed LangChain scope:

- Document loaders or custom `Document` construction from artifacts.
- Text splitting.
- Retriever wrappers.
- Prompt templates for RAG-backed generation.
- Structured-output wrappers where they improve schema reliability.

Do not replace the existing pipeline orchestration with LangChain chains. The existing pipeline stage functions remain explicit Python functions.

### 4. LangChain Provider Refactor

Refactor selected prompt/provider code to reduce ad hoc prompt assembly and repeated JSON parsing.

Target areas:

- Analyze provider prompt construction.
- Generate provider summary generation.
- Judge assessment JSON output.
- Planner strategy generation.

Constraints:

- Keep deterministic providers working.
- Keep OpenAI-compatible provider support.
- Keep strict Chinese-output validation where it already exists.
- Keep fallback behavior explicit and logged.
- Do not hide model calls behind opaque abstractions that make run logs less useful.

### 5. LangGraph Review Agent

Add a new LangGraph-based post-run review agent. This is not the main pipeline executor.

The agent should run after an existing run has produced artifacts.

Primary use cases:

- Explain why a JD was ranked high, low, blocked, or marked `needs_review`.
- Retrieve related candidate evidence and prior JD feedback.
- Generate interview-preparation questions and reference answers.
- Suggest safe resume-revision tasks based only on verified or clearly marked simulatable evidence.
- Summarize what the candidate should improve before applying to similar roles.

Suggested graph nodes:

```text
load_run_context
retrieve_relevant_evidence
inspect_score_and_gates
generate_interview_questions
generate_reference_answers
generate_revision_tasks
validate_against_fabrication_policy
write_review_artifact
```

Suggested output artifact:

```text
run_dir/review/post_run_review.json
run_dir/review/interview_prep.md
```

The review agent may also write a database record linked to the run, but the run-local artifact should remain available for offline review.

## Task Boundaries

### In Scope

- Add database schema and migration tooling.
- Add artifact-to-database indexing.
- Add pgvector-backed retrieval.
- Add LangChain RAG utilities.
- Refactor part of the provider/prompt layer to use cleaner prompt and structured-output utilities.
- Add a LangGraph post-run review agent.
- Add CLI commands for indexing, retrieval smoke tests, and post-run review.
- Add targeted tests for indexing idempotency, retrieval metadata, provider fallback, and review-agent artifact output.
- Update docs in English or Chinese as appropriate for the repository convention; existing Chinese docs may stay Chinese.

### Out of Scope

- No automatic job application submission.
- No browser automation for job boards.
- No company data scraping.
- No company website crawling.
- No LinkedIn, Boss, Lagou, Greenhouse, Lever, or ATS scraping.
- No account login automation.
- No CRM workflow beyond local feedback records.
- No remote multi-user SaaS mode.
- No replacement of `run_dir` artifacts as the execution source of truth in the first refactor.
- No Web rewrite that bypasses the Python pipeline.

## Hard Constraints

1. **Absolutely do not implement company data crawling or scraping.**
   Company information may only come from user-provided JD text, manually entered notes, or local artifacts already present in the run.

2. **Do not make PostgreSQL the business execution source of truth in the first version.**
   It is a query/projection layer. The pipeline still writes and reads `run_dir` artifacts.

3. **Do not expose raw CV/JD text unnecessarily in the Web UI.**
   Prefer summaries, provenance labels, evidence snippets, and artifact references.

4. **Do not fabricate candidate facts.**
   Hard facts such as education, degree, major, certificate, employer, years of experience, publications, awards, and work authorization must remain evidence-bound.

5. **Do not let RAG override scoring gates.**
   Retrieval can supply evidence and explanations, but ranking still flows through `ScoreCard`, `PreflightGate`, and the existing scoring contracts.

6. **Do not hide failures.**
   Provider failures, parsing failures, retrieval misses, and review-agent validation failures must be logged and surfaced in artifacts.

7. **Do not degrade deterministic local runs.**
   Existing deterministic fixture tests should continue to pass without requiring a live model, database, or vector extension unless the specific test opts into those dependencies.

## Suggested Implementation Order

1. Add database configuration and schema.
2. Add an idempotent artifact indexer.
3. Add pgvector chunk storage and retrieval.
4. Add retrieval smoke tests over fixture runs.
5. Refactor provider prompt construction incrementally.
6. Add LangGraph post-run review agent.
7. Add review artifacts and Web read-only display.
8. Document setup, boundaries, and non-goals.

## Acceptance Criteria

- Existing pipeline commands still work without PostgreSQL when database features are not invoked.
- `shotguncv index --runs-dir ./runs` can index existing runs idempotently.
- A retrieval smoke test can find similar JDs and candidate evidence with metadata-preserving results.
- Provider refactor keeps deterministic and OpenAI-compatible paths working.
- The LangGraph review agent can generate post-run review artifacts from an existing run without rerunning the whole pipeline.
- Review-agent outputs cite artifact-backed evidence and respect fabrication policy.
- Documentation clearly states that company data crawling, job-board automation, and automatic application submission are out of scope.
