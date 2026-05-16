# ShotgunCV v0.8 — Web UX Hardening & User-Facing Polish

## Goal

Transform the web workbench from a developer-internal tool into a **user-facing local workbench**. Fix the broken web-based run execution, remove developer-facing English jargon from all visible UI, and add a prominent entry point so users can start a new run from anywhere — especially the dashboard.

## Context

The web app (Next.js 15, `apps/web/`) is a local single-user workbench that reads/writes to the `runs/` directory. It has no database, no remote server, no multi-user auth. The Python CLI (`shotguncv`) is the sole business-logic engine; the web UI reads its artifacts and provides a visual workbench layer.

The current web UI was built rapidly (v0.6–v0.7.14) with a developer-first mindset: table columns are labeled "Run", "Provider", "JD"; section headers say "Draft workflow"; placeholder text references internal variable names like `runId`, `candidateId`, `jdId`. These need to become user-readable Chinese labels.

## Task Breakdown

All work happens on a **new branch created from `codex-v0.7.14-frontend-cleanup`** (the current branch). Name it `feat/v0.8-web-ux`.

Decompose into these sub-versions, each committed separately:

---

### v0.8.0 — Fix Web-Based Run Execution

**Problem:** User created draft `cand-20260515-080516463-20260515-080516` via the web UI (`/upload` → POST `/api/runs/drafts`), navigated to the run detail page, clicked "Run", and it failed. The web cannot execute pipeline runs.

**Root cause analysis (do this first):**

1. Read `apps/web/lib/run-actions.ts` — the `startRunAction()` function spawns a child process running `shotguncv` CLI (or whatever `SHOTGUNCV_CLI_COMMAND` points to). It uses `spawn(command, args, { detached: true, stdio: "ignore" })` — errors are silently dropped.

2. Check whether `shotguncv` CLI is actually installed and available in the shell environment where the Next.js dev server runs. Read `pyproject.toml` to understand the Python package entry points.

3. Trace the full flow:
   - User creates draft → `createRunDraft()` in `upload-drafts.ts` → writes files to `runs/<runId>/`
   - User clicks "Run" → POST to `/api/runs/[runId]/actions` → `startRunAction()` → `spawn("shotguncv", [...])` 
   - The subprocess runs detached, stdio ignored — no feedback loop

**Required fixes:**

- **Capture and surface errors**: The `defaultSpawnRunner` must capture stderr/stdout. When the spawn fails (command not found, Python env missing, non-zero exit), write the error into `run_status.json` so the UI can show it. Do NOT use `stdio: "ignore"` — pipe stderr at minimum.
- **Pre-flight check before spawn**: Before spawning, verify the CLI command resolves (e.g., `which`/`where` check on the command). If not found, return a clear error to the UI: "CLI 命令未找到，请确认 shotguncv 已安装并在 PATH 中" — do not silently write "running" status and then fail.
- **Environment passthrough**: Ensure the spawned process inherits `process.env` so it sees `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `PATH` including Python, etc.
- **Handle the `error` event properly**: The current code only listens for `child.on("error", ...)` which catches spawn failures. It does NOT handle the `exit` event (non-zero exit code). Add an `exit` handler that checks the exit code and updates `run_status.json` to `failed` with the exit code in `error_summary`.
- **Update the RunActionPanel component** (`apps/web/app/runs/[runId]/RunActionPanel.tsx`): After a run action is triggered, poll or show clearer feedback. Currently the UI likely says "queued" or "running" but never updates to "failed" when the spawn itself fails.

**Files to change:**
- `apps/web/lib/run-actions.ts` — capture stderr, add exit handler, add pre-flight CLI check, inherit env
- `apps/web/app/runs/[runId]/RunActionPanel.tsx` — improve error display when run fails at spawn level

**Acceptance criteria:**
- Creating a draft via web UI and clicking "Run" either (a) successfully starts the pipeline and updates status, or (b) shows a clear, Chinese-language error message explaining exactly what's missing (CLI not found, Python not configured, etc.)
- The `run_status.json` reflects the real state: never stuck at "running" when the subprocess failed to spawn
- `npm test` and `npx tsc --noEmit` pass

---

### v0.8.1 — Replace Developer-Facing English Labels in UI (Pages)

**Problem:** Multiple pages display raw English variable names, internal identifiers, and developer jargon as visible UI text. Users see "Run", "Provider", "Draft workflow", "CV", "JD", etc. as labels, headers, and placeholders.

**Audit all user-visible English text across these files and replace with Chinese:**

| File | Current English | Replace With |
|------|----------------|--------------|
| `AppShell.tsx:73-76` | "AI Resume Ops" / "工作台" | "智能简历工作台" / "" |
| `AppShell.tsx:103-107` | "AI 洞察" / "基于历史数据的智能建议" | Keep Chinese, just remove English brand |
| `AppShell.tsx:112-115` | "Nemo Zhang" / "产品负责人" | Remove hardcoded persona; replace with generic "本地用户" / "单用户工作台" |
| `page.tsx:17` | `eyebrow="仪表盘"` | Keep |
| `RunQueue.tsx:217-222` | Table headers: "Run", "状态", "阶段进度", "Provider", "风险与动作", "操作" | "运行批次", "状态", "阶段进度", "模型提供商", "风险与动作", "操作" |
| `RunQueue.tsx:110` | Placeholder: "搜索 run、标签、provider" | "搜索运行批次、标签、模型" |
| `RunQueue.tsx:150` | Label: "Provider 筛选" | "模型筛选" |
| `RunQueue.tsx:156` | Option: "全部 provider" | "全部模型" |
| `RunQueue.tsx:265-266` | Labels: "生成", "评审" | Keep Chinese |
| `RunQueue.tsx:186` | "先创建一个草稿 run" | "先创建一个投递草稿" |
| `RunQueue.tsx:187` | "创建草稿 run" | "创建投递草稿" |
| `upload/page.tsx:30` | Eyebrow: "Draft workflow" | "草稿工作流" |
| `upload/page.tsx:37` | "草稿会写入 input_files/..." | Keep Chinese but fix path references to be more readable |
| `runs/[runId]/page.tsx` | Provider pills: "分析器：", "生成器：", "评审器：", "规划器：" | Already Chinese — keep |
| All pages | Any `<p className="eyebrow">` with English | Translate to Chinese |
| All pages | Any placeholder text with English variable names (`runId`, `jdId`, `candidateId`, `provider`) | Replace with Chinese descriptions |

**Key principle:** If a string is visible in the browser (label, header, placeholder, button text, table header, empty state message) it MUST be in Chinese. English is only acceptable inside `<code>` / `.mono` elements showing file paths or technical identifiers that users need for CLI commands.

**Files to change:**
- `apps/web/app/AppShell.tsx`
- `apps/web/app/page.tsx`
- `apps/web/app/RunQueue.tsx`
- `apps/web/app/upload/page.tsx`
- `apps/web/app/upload/UploadForm.tsx`
- `apps/web/app/runs/[runId]/page.tsx`
- `apps/web/app/runs/[runId]/RunActionPanel.tsx`
- `apps/web/app/evaluations/page.tsx`
- `apps/web/app/evaluations/EvaluationQueue.tsx`
- `apps/web/app/resume/page.tsx`
- `apps/web/app/resume/ResumeWorkspace.tsx`
- `apps/web/app/settings/page.tsx`
- `apps/web/app/settings/LocalConfigPanel.tsx`
- `apps/web/app/runs/[runId]/report/page.tsx`

**Acceptance criteria:**
- Every page visually inspected: no raw English labels, headers, or placeholders visible in the rendered UI (excluding `<code>` / `.mono` elements)
- `npm test` and `npx tsc --noEmit` pass
- Screenshot QA on desktop (1440×1000) and mobile (390×844) for: dashboard, upload, run detail, evaluations, settings, resume, report

---

### v0.8.2 — Dashboard Prominent CTA Button

**Problem:** The dashboard (`/`) has no visible "Start" or "Create New" button. The only way to create a draft is via the empty state inside RunQueue (which only appears when there are 0 runs) or by navigating through the sidebar to "简历优化" → upload page. A user landing on the dashboard should see an immediate, prominent call-to-action.

**Required changes to `apps/web/app/page.tsx`:**

1. Add a prominent CTA button in the `page-header` section (alongside the `<h1>运行队列</h1>` title):
   ```
   <div className="page-header">
     <div>
       <h1>运行队列</h1>
     </div>
     <Link href="/upload" className="primary-link" style={/* prominent sizing */}>
       <Icon name="play" /> 开始新投递
     </Link>
   </div>
   ```
   
2. The button should:
   - Use the existing `.primary-link` class with slightly larger padding/font to stand out
   - Include a `play` icon (already exists in AppShell Icon component)
   - Be positioned at the top-right of the page header, visually distinct from the title
   - Be responsive: on mobile, stack below or beside the title without breaking layout

3. Also add a secondary CTA card in the `insight-rail` (right sidebar) when there are few or no runs:
   - Replace or augment the "尚无运行数据" AI insight with a clickable card that says "开始您的第一次投递" → links to `/upload`

4. Add a floating or fixed "quick action" button that stays visible as the user scrolls the dashboard? No — keep it simple. Just the page-header button and the insight-rail card.

**Files to change:**
- `apps/web/app/page.tsx` — add CTA button to page-header, update insight rail
- `apps/web/app/globals.css` — if needed, add a `.page-header` flex layout rule to accommodate the button

**Acceptance criteria:**
- Dashboard shows a prominent "开始新投递" button in the page header, visible on first paint
- Clicking it navigates to `/upload`
- Button is responsive: visible and clickable on 1440px, 1180px, 980px, and 390px widths
- The insight rail also shows a "开始您的第一次投递" card when there are 0 runs
- `npm test` and `npx tsc --noEmit` pass

---

### v0.8.3 — Cross-Page UX Polish Pass

**Problem:** After v0.8.0–v0.8.2, do a final sweep to catch remaining developer-facing artifacts and UX rough edges.

**Checklist:**

1. **Upload page flow clarity:**
   - After draft creation, the success panel shows a CLI command block (`shotguncv run --run-dir ...`). This is developer-facing. Replace with a user-friendly message: "草稿已创建，点击下方按钮进入详情页运行" and hide the raw CLI command behind a collapsible "高级 / CLI 命令" expander.
   - The "落盘边界" card at the bottom of the upload page shows a raw filesystem path. Keep it but label it more clearly: "数据存储位置" instead of "落盘边界".

2. **Empty states:**
   - Audit all empty states across pages. Each must: (a) explain what the page does in Chinese, (b) provide a clear next action button, (c) never show raw English error messages or variable names.

3. **Navigation labels:**
   - Sidebar item "简历优化" currently links to `/resume`. Consider whether it should link to `/upload` instead (the upload page eyebrow already says "简历优化 / 创建草稿"). Or keep `/resume` but ensure the workflow from dashboard → upload is clear.

4. **Status labels consistency:**
   - Verify `STATUS_LABELS` in `page.tsx`, `RunQueue.tsx`, and `runs/[runId]/page.tsx` are identical. There are currently 3 separate copies of this mapping. Consolidate into one shared constant in `lib/labels.ts` and import everywhere.

5. **Page titles and metadata:**
   - Check `apps/web/app/layout.tsx` for `<title>` and `<meta>` tags — ensure they're Chinese.

**Files to change:**
- `apps/web/app/upload/page.tsx` — hide CLI command behind expander
- `apps/web/app/upload/UploadForm.tsx` — update success panel
- `apps/web/app/layout.tsx` — check metadata
- `apps/web/lib/labels.ts` — NEW file: shared STATUS_LABELS and STAGE_LABELS
- `apps/web/app/page.tsx` — import shared labels
- `apps/web/app/RunQueue.tsx` — import shared labels
- `apps/web/app/runs/[runId]/page.tsx` — import shared labels
- Any other files with duplicate label mappings

**Acceptance criteria:**
- No duplicate `STATUS_LABELS` or `STAGE_LABELS` definitions across the codebase
- Upload success panel does not prominently display raw CLI commands
- All empty states have Chinese explanations and clear next actions
- `npm test` and `npx tsc --noEmit` pass

---

## Execution Rules

1. **Create branch:** `git checkout -b feat/v0.8-web-ux` from `codex-v0.7.14-frontend-cleanup`
2. **Work sequentially:** v0.8.0 → v0.8.1 → v0.8.2 → v0.8.3. Do NOT mix changes across sub-versions.
3. **Commit each sub-version separately** with a descriptive message following the repo's convention (e.g., `feat: fix web-based run execution with error capture and pre-flight checks for v0.8.0`)
4. **After each commit**, verify `npm test` and `npx tsc --noEmit` pass. If they fail, fix before moving to the next sub-version.
5. **DO NOT run `npm install`** — the project dependencies are already installed. Any dependency change requires explicit user approval.

## Boundary Constraints

- **Command timeout:** Every shell command (git, npm, npx) MUST specify an explicit timeout (max 120s for npm/tsc, 30s for git). No unbounded commands.
- **NO `npm install` / `npm ci` / `npm update`** — strictly prohibited. The lock file and `node_modules` are already in the correct state.
- **No destructive git operations** (force push, hard reset, checkout --) unless explicitly requested.
- **Do NOT modify Python pipeline code** (`packages/py-core/`, `packages/py-agents/`, `apps/cli/`). This is a web-only change set.
- **Do NOT change the artifact schema** in `packages/ts-shared/src/index.ts` unless required to fix the run execution bug.
- **Read before edit** — every file modification must be preceded by reading the current file content.

## Acceptance Criteria (Final Gate)

Before marking v0.8 complete, verify ALL of the following:

1. [ ] `git log --oneline` on `feat/v0.8-web-ux` shows exactly 4 commits (v0.8.0, v0.8.1, v0.8.2, v0.8.3)
2. [ ] `npm test` passes — no regressions
3. [ ] `npx tsc --noEmit` passes — no type errors
4. [ ] Dashboard (`/`) — shows "开始新投递" CTA button, no English labels visible
5. [ ] Upload (`/upload`) — creates draft successfully, success panel is user-friendly
6. [ ] Run detail (`/runs/[runId]`) — run action shows clear error when CLI is missing (not silent failure)
7. [ ] All pages — no raw English variable names visible in rendered UI (tables, headers, placeholders, empty states)
8. [ ] No duplicate label constant definitions across files
9. [ ] `npm install` was NEVER executed during this work
