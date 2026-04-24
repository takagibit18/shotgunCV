---
name: designing-ai-feedback-control
description: Use when designing AI feedback, correction, override, retry, reset, preference, or human-in-the-loop controls.
---

# Designing AI Feedback Control

## Overview

AI products need user control because outputs are probabilistic and user goals change. Feedback controls should improve the user's current workflow first, and model or product learning second.

## Feedback Model

| Feedback type | Best UI |
| --- | --- |
| Fast quality signal | Helpful/not helpful, approve/reject, thumbs, compact reason menu. |
| Correction | Inline edit, field-level correction, replacement text, evidence override. |
| Workflow decision | Accept recommendation, skip, defer, compare alternatives. |
| Learning preference | Remember preference, stop suggesting this, reset personalization. |
| Failure report | Wrong source, missing evidence, hallucinated claim, unsafe suggestion. |

## Control Rules

1. Explain what feedback affects: this result, this run, future runs, or nothing yet.
2. Provide a manual fallback for high-stakes actions.
3. Keep undo and revert near generated edits.
4. Let users retry with changed inputs instead of only "regenerate".
5. Make opt-out and reset discoverable for persistent preferences.

## ShotgunCV Fit

- Generated resume variants need accept, edit, revert, compare, and mark unsupported.
- Scorecards need dimension-level correction notes, not only global thumbs.
- Ranking explanations need "evidence is wrong/missing" feedback.
- Strategy plans need defer/skip decisions so users can keep the pipeline moving.

## Copy Rules

- Say "This updates the current run" or "This only changes this view" when relevant.
- Avoid vague thanks-only feedback. Tell the user what changed.
- Avoid implying model training unless the implementation actually trains or tunes.

## Common Mistakes

- Asking for feedback after the user has already left the task.
- Treating all negative feedback as the same signal.
- Letting regenerate overwrite user edits without confirmation.
- Hiding the non-AI path after introducing automation.

## Checklist

- [ ] Is there a clear way to correct wrong AI output?
- [ ] Does the UI say what the feedback affects?
- [ ] Can the user undo or reset AI-applied changes?
- [ ] Is manual review preserved for high-impact decisions?
- [ ] Are feedback options mutually exclusive enough to be useful?

## References

- Google PAIR Feedback + Control: https://pair.withgoogle.com/guidebook-v2/chapters/feedback-controls/
- Google PAIR Patterns: https://pair.withgoogle.com/guidebook-v2/patterns
- Microsoft HAX Design Patterns: https://www.microsoft.com/en-us/haxtoolkit/?p=108
