---
name: designing-ai-trustworthy-interfaces
description: Use when designing AI product interfaces that show generated output, recommendations, scoring, ranking, summaries, or model-assisted decisions.
---

# Designing AI Trustworthy Interfaces

## Overview

AI UI must help users calibrate trust. The interface should show what the system did, why it matters, what is uncertain, and what the user can do next.

Use this for `ShotgunCV` screens that display generated resumes, scorecards, ranking explanations, gap maps, strategy suggestions, or LLM-generated summaries.

## Core Rules

| Rule | UI requirement |
| --- | --- |
| Show capability boundaries | State what this AI result can and cannot support in the current workflow. |
| Expose evidence | Link every important conclusion to source JD, resume evidence, score dimension, or run artifact. |
| Mark uncertainty | Use confidence, coverage, or evidence strength labels only when backed by data. |
| Separate fact from suggestion | Keep parsed facts, inferred gaps, and suggested actions visually distinct. |
| Provide next action | Every AI result should support accept, inspect evidence, revise, retry, or dismiss. |

## Layout Pattern

For each AI output panel:

1. Result: concise answer, score, recommendation, or generated draft.
2. Basis: cited evidence, source fields, dimensions, or changed inputs.
3. Limits: missing evidence, model caveat, unsupported claim, or `gap`.
4. Action: inspect, edit, regenerate, compare, export, or mark as not useful.

## ShotgunCV Fit

- Ranking pages should show score, reason, risk, and traceable evidence together.
- Resume generation pages should distinguish "source-backed rewrite" from "stretch phrasing".
- Strategy pages should expose why a JD is high-value, low-fit, risky, or worth manual review.
- Reports should avoid absolute claims unless the evaluation artifact directly supports them.

## Anti-Patterns

- One large AI answer with no source links.
- "Magic" confidence badges with no definition.
- Hiding gaps below the fold while showing only positive recommendations.
- Making generated text look final before review.
- Using decorative AI styling that competes with evidence.

## Checklist

- [ ] Does the screen show the AI output source or basis?
- [ ] Are unsupported claims labeled as gaps, risks, or assumptions?
- [ ] Can the user inspect or correct the result?
- [ ] Are high-impact actions gated by review?
- [ ] Is uncertainty presented in plain language?

## References

- Microsoft HAX Toolkit: https://www.microsoft.com/en-us/haxtoolkit/
- Microsoft Guidelines for Human-AI Interaction: https://www.microsoft.com/en-us/research/publication/guidelines-for-human-ai-interaction/
- Google PAIR Explainability + Trust: https://pair.withgoogle.com/guidebook-v2/chapter/explainability-trust/
