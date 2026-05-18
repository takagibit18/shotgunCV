---
name: designing-ai-feedback-control
description: Use when designing ShotgunCV AI feedback, correction, override, retry, reset, preference, or human-in-the-loop controls.
---

# Designing AI Feedback Control

## Overview

ShotgunCV feedback controls should keep the user in charge of local artifacts and repeated job-application decisions. Feedback improves the current run workflow first; it should not imply model training, remote sync, or hidden automation.

## Feedback Model

| Feedback type | Best UI |
| --- | --- |
| Fast quality signal | Useful/not useful, approve/reject, compact reason menu. |
| Correction | Inline edit, field-level correction, replacement text, evidence override note. |
| Workflow decision | Accept recommendation, skip, defer, compare alternatives. |
| Local preference | Remember locally, stop suggesting this, reset preference. |
| Failure report | Wrong source, missing evidence, hallucinated claim, unsupported rewrite, unsafe suggestion. |

## Control Rules

1. Say what feedback affects: this view, this run, future local runs, or nothing persisted yet.
2. Keep manual fallback available for resume edits, JD prioritization, and final delivery decisions.
3. Put undo, revert, and compare near generated edits.
4. Let users retry with changed inputs or selected artifacts instead of only "regenerate".
5. Make opt-out and reset discoverable for persistent local preferences.
6. Never overwrite user edits or `run_dir` artifacts without an explicit confirmation path.

## ShotgunCV Fit

- Generated resume variants need accept, edit, revert, compare, and mark unsupported.
- Scorecards need dimension-level correction notes, not only global thumbs.
- Ranking explanations need "evidence is wrong/missing" feedback.
- Strategy plans need defer/skip decisions so users can keep the pipeline moving.
- Run actions need clear separation between UI-only state, local status writeback, and Python pipeline execution.

## Copy Rules

- Use Chinese action text such as "仅更新当前视图", "写入当前 run", "保留人工处理", and "重试并保留原稿".
- Avoid vague thanks-only feedback. Tell the user what changed.
- Avoid implying model training unless the implementation actually trains or tunes.
- Avoid user personas, team roles, or account language that conflicts with the single-user local boundary.

## Common Mistakes

- Asking for feedback after the user has already left the task.
- Treating all negative feedback as the same signal.
- Letting regenerate overwrite user edits without confirmation.
- Hiding the non-AI path after introducing automation.
- Saving preferences in browser storage, logs, or artifacts without saying so.

## Checklist

- [ ] Is there a clear way to correct wrong AI output?
- [ ] Does the UI say what the feedback affects?
- [ ] Can the user undo or reset AI-applied changes?
- [ ] Is manual review preserved for high-impact decisions?
- [ ] Are feedback options mutually exclusive enough to be useful?
- [ ] Does persistence stay local, masked, and explicit?

## References

- Google PAIR Feedback + Control: https://pair.withgoogle.com/guidebook-v2/chapters/feedback-controls/
- Google PAIR Patterns: https://pair.withgoogle.com/guidebook-v2/patterns
- Microsoft HAX Design Patterns: https://www.microsoft.com/en-us/haxtoolkit/?p=108
