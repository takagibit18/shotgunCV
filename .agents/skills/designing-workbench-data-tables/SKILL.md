---
name: designing-workbench-data-tables
description: Use when designing ShotgunCV tables, ranking lists, filters, sorting, bulk actions, comparison views, or data-dense review queues.
---

# Designing Workbench Data Tables

## Overview

ShotgunCV tables are decision surfaces, not storage dumps. They should make JD triage, run comparison, evidence review, filtering, and next actions faster than opening every run one by one.

## Table Anatomy

| Area | Requirement |
| --- | --- |
| Header | Title, count, freshness, artifact mode, primary action. |
| Filter bar | Search, high-value facets, current sort, reset. |
| Columns | Stable run/JD identifiers, gate/status, score metrics, evidence/risk, action. |
| Rows | Consistent height, clear selected/hover/focus states, predictable wrapping. |
| Bulk area | Selection count, batch action, destructive confirmation only when real bulk actions exist. |
| Empty/error states | Explain cause and next valid action, including missing artifact or narrow filters. |

## Ranking And Review Rules

- Put the user decision column near score, gate, and risk, not detached at the far edge.
- Show score breakdown access inline through popover, drawer, expandable row, or detail link.
- Use badges for categorical state, not for long explanations.
- Keep filter chips removable and visible.
- Preserve current filters and sort when returning from a detail page.
- Avoid repeating `scorecard / gate / evidence / strategy` source prose in every row; use column labels, tooltips, or one page-level note.

## ShotgunCV Fit

- JD ranking tables need fit score, gap risk, evidence coverage, generated variant status, and strategy status.
- Evaluation queues need unresolved gaps, severe risks, gate status, and manual-review flags.
- Candidate/JD comparisons need stable identifiers and source traceability.
- Report tables need exportable, deterministic ordering.
- Legacy or partial artifacts need clear degraded display, not broken rows.

## States To Design

- Loading skeleton with stable table dimensions.
- No data because the run has not reached this pipeline stage.
- No results because filters are too narrow.
- Partial artifact because generation or evaluation failed.
- Legacy artifact using older score fields.
- File-read or parse error.

## Common Mistakes

- Too many columns with no priority.
- Filters that disappear after navigation.
- Sort controls that do not reveal current sort direction.
- Color-only status encoding.
- Long text in cells that changes row height unpredictably.
- Treating a local workbench as a remote admin table with owners, permissions, or account state.

## Checklist

- [ ] Is each column tied to a real decision?
- [ ] Can users recover from over-filtering?
- [ ] Are selected rows and bulk actions obvious only when supported?
- [ ] Do score, gate, risk, and explanation stay connected?
- [ ] Are loading, empty, partial, legacy, and error states designed?
- [ ] Does the table work with Chinese text and mixed technical identifiers?

## References

- Atlassian Design System components and patterns: https://atlassian.design/design-system/
- Material Design Accessibility: https://m1.material.io/usability/accessibility.html
