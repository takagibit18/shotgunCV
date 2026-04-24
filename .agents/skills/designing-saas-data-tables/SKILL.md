---
name: designing-saas-data-tables
description: Use when designing SaaS tables, ranking lists, filters, sorting, bulk actions, comparison views, or data-dense review queues.
---

# Designing SaaS Data Tables

## Overview

Tables are decision surfaces, not storage dumps. A SaaS table should make comparison, triage, filtering, and bulk action faster than reading each item one by one.

## Table Anatomy

| Area | Requirement |
| --- | --- |
| Header | Title, count, freshness, primary action. |
| Filter bar | Search, saved filters, high-value facets, reset. |
| Columns | Stable identifiers, status, decision metrics, owner/action. |
| Rows | Consistent height, clear selected/hover/focus states. |
| Bulk area | Selection count, batch action, destructive confirmation. |
| Empty/error states | Explain cause and next valid action. |

## Ranking And Review Rules

- Put the user decision column near the score, not at the far edge.
- Show score breakdown access inline through popover, drawer, or expandable row.
- Use badges for categorical state, not for long explanations.
- Keep filter chips removable and visible.
- Preserve current filters and sort when returning from a detail page.

## ShotgunCV Fit

- JD ranking tables need fit score, gap risk, evidence coverage, generated variant status, and strategy status.
- Candidate/JD comparisons need stable identifiers and source traceability.
- Eval review queues need unresolved gaps, severe risks, and manual-review flags.
- Report tables need exportable, deterministic ordering.

## States To Design

- Loading skeleton with stable table dimensions.
- No data because run has not reached this pipeline stage.
- No results because filters are too narrow.
- Partial artifact because generation or evaluation failed.
- Permission or file-read error.

## Common Mistakes

- Too many columns with no priority.
- Filters that disappear after navigation.
- Sort controls that do not reveal current sort direction.
- Color-only status encoding.
- Long text in cells that changes row height unpredictably.

## Checklist

- [ ] Is each column tied to a real decision?
- [ ] Can users recover from over-filtering?
- [ ] Are selected rows and bulk actions obvious?
- [ ] Do score and explanation stay connected?
- [ ] Are loading, empty, partial, and error states designed?

## References

- SaaSUI table patterns: https://www.saasui.design/
- Atlassian Design System components and patterns: https://atlassian.design/design-system/
- Material Design Accessibility: https://m1.material.io/usability/accessibility.html
