# ShotgunCV v0.6 Web Experience Plan

## Summary

v0.6 focuses on the Web surface only. The goal is to move `apps/web` from a usable local run viewer to a calm, scannable, explainable local AI Resume Ops workspace.

The backend boundary remains unchanged: Python pipeline is still the only business source of truth, and Web continues to read and trigger local `run_dir` artifacts without introducing a database, remote queue, CRM, multi-user permissions, or automatic application submission.

## Experience Gaps

- The current implementation mixes a beige editorial visual language with a blue SaaS mockup direction. A data-dense operational workspace needs the latter: neutral structure, clear borders, restrained color, and compact typography.
- The home page reads like a landing page. It needs to behave like a run queue with search, filters, sorting, status summaries, and obvious next actions.
- The run detail page has most information, but the decision path is too vertical. Status, trust, next action, quality warnings, gates, scores, evidence, and risks need to appear in a stable order.
- Diagnostics such as timeline and input sources are important, but they should not compete with the decision surface.
- The report page needs traceable structured summaries before the Markdown body, including source labels for strategy, scorecard, evidence, and gap data.
- Upload should behave like a task flow: candidate material, JD input, then draft confirmation.

## Implementation Direction

- Replace the beige/editorial theme with a light operational SaaS system: cool neutral backgrounds, white panels, blue accent, semantic status colors, small radii, low shadows, and compact sans-serif typography.
- Keep cards only for repeated items and framed tools. Use tables, strips, grids, and inline expandable regions for dense review surfaces.
- Make the home page a queue-first workspace:
  - compact app header with runs root, refresh affordance, and draft creation;
  - summary strip for total runs, active runs, warnings/failures, and completed stages;
  - searchable/filterable/sortable run queue;
  - row-level status, stage progress, provider, warning/error, last modified time, and detail/report actions.
- Make run detail answer three questions in the first viewport: current status, whether the output is trustworthy, and what the next valid action is.
- Keep the scoring matrix as the primary decision surface. Prefer verified fit, rewrite potential, risk pressure, gate status, evidence references, and application advice over generic score decoration.
- Move timeline and input source tables into diagnostics sections that remain complete and readable.
- Add report references and a compact report outline before rendering raw Markdown.
- Convert upload into a three-step workspace with file metadata, validation state, and clear success actions.

## Public Interfaces

- No changes to pipeline artifacts or `run_dir` contracts.
- Web continues to read:
  - `run_status.json`
  - `logs/run_events.jsonl`
  - `ingest/manifest.json`
  - `analyze/requirement_matrix.json`
  - `analyze/preflight_gates.json`
  - `evaluate/scorecards.json`
  - `evaluate/ranking_explanations.json`
  - `plan/application_strategies.json`
  - `report/summary.md`
- Web may add local UI-only state for filtering, sorting, display severity, and decision status.

## Test Plan

- Unit tests cover run queue rendering, filtering controls, status badges, quality warning display, legacy artifact compatibility, score matrix fallbacks, report summaries, and upload page structure.
- Responsive QA checks desktop, tablet, and mobile layouts for overflow, priority ordering, and readable Chinese/English mixed content.
- Accessibility QA checks labels for filters, buttons, expanders, focus-visible states, non-color-only status, and reduced-motion behavior.

## Assumptions

- v0.6 does not change Python pipeline behavior.
- `apps/web` remains a local single-user Next.js app.
- The existing HTML mockup is a directional reference, not a pixel-perfect implementation target.
