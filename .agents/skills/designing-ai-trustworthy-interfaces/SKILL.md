---
name: designing-ai-trustworthy-interfaces
description: Use when designing ShotgunCV AI output, recommendations, scoring, ranking, summaries, generated resumes, or model-assisted decisions.
---

# Designing AI Trustworthy Interfaces

## Overview

ShotgunCV AI UI must help users calibrate trust inside a local, artifact-driven workbench. The screen should show what the system concluded, which artifact supports it, what is uncertain, and what action the user can take next.

Use this for generated resumes, scorecards, ranking explanations, gap maps, strategy suggestions, LLM summaries, and report sections.

## Core Rules

| Rule | UI requirement |
| --- | --- |
| Keep artifacts visible | Tie conclusions to `scorecards.json`, `ranking_explanations.json`, `requirement_matrix.json`, `preflight_gates.json`, generated variants, or run metadata. |
| Separate evidence and advice | Parsed facts, inferred gaps, generated suggestions, and user decisions must not share one undifferentiated panel. |
| Surface uncertainty | Label missing evidence, partial artifacts, legacy artifacts, unsupported claims, and stale runs plainly. |
| Preserve local boundaries | Do not imply remote sync, model training, CRM ownership, multi-user approval, or automatic delivery. |
| Provide next action | Every AI result should lead to inspect evidence, edit, compare, retry, export, defer, or dismiss. |

## Layout Pattern

For each AI output panel:

1. Result: concise score, recommendation, generated draft, or summary.
2. Basis: source artifact, score dimension, JD/resume evidence, or changed input.
3. Limits: missing artifact, low evidence coverage, unsupported claim, legacy fallback, or model caveat.
4. Action: inspect, edit, regenerate, compare, export, mark not useful, or continue manually.

## ShotgunCV Fit

- Ranking pages should keep score, gate status, evidence coverage, risk, and action in one decision surface.
- Resume generation pages should distinguish source-backed rewrite from stretch phrasing.
- Strategy pages should expose why a JD is high-value, low-fit, risky, or worth manual review.
- Reports should avoid absolute claims unless the evaluation artifact directly supports them.
- Settings and diagnostics should show masked metadata only, not raw API keys, full CV/JD text, or unnecessary local paths.

## Copy Rules

- Default visible copy to Chinese.
- Prefer concrete source labels such as `scorecard`, `gate`, `evidence`, and `strategy` only when they are artifact names or technical identifiers.
- Avoid repeated explanatory paragraphs when a page-level boundary has already been established.
- Avoid decorative "AI magic" language; name the evidence, gap, risk, or next step.

## Anti-Patterns

- One large AI answer with no source links.
- "Confidence" badges with no definition or backing data.
- Hiding gaps below the fold while showing only positive recommendations.
- Making generated text look final before review.
- Styling AI panels as a separate glowing or decorative product language.
- Reintroducing SaaS promises such as team workflows, CRM sync, or auto-apply without product support.

## Checklist

- [ ] Does the screen show the AI output source or basis?
- [ ] Are unsupported claims labeled as gaps, risks, assumptions, or partial artifacts?
- [ ] Can the user inspect or correct the result?
- [ ] Are high-impact actions gated by review or explicit user action?
- [ ] Is uncertainty presented in plain Chinese?
- [ ] Does the UI avoid exposing raw secrets, raw CV/JD text, or unnecessary full paths?

## References

- Microsoft HAX Toolkit: https://www.microsoft.com/en-us/haxtoolkit/
- Microsoft Guidelines for Human-AI Interaction: https://www.microsoft.com/en-us/research/publication/guidelines-for-human-ai-interaction/
- Google PAIR Explainability + Trust: https://pair.withgoogle.com/guidebook-v2/chapter/explainability-trust/
