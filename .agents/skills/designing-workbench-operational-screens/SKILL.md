---
name: designing-workbench-operational-screens
description: Use when designing ShotgunCV dashboards, operational workspaces, run viewers, detail pages, monitoring pages, or workflow-heavy product screens.
---

# Designing Workbench Operational Screens

## Overview

ShotgunCV is a local single-user workbench. Its UI should be dense, calm, and task-first: scan run status, compare JD/candidate evidence, inspect artifacts, and take repeated actions without marketing-style decoration.

## Workspace Structure

| Layer | Purpose | UI pattern |
| --- | --- | --- |
| Global context | Where am I and what run/workbench is active? | Sidebar, breadcrumb, compact command bar. |
| Primary status | What changed and what needs attention? | Summary strip, risk/gate chips, progress, alert. |
| Work queue | What should I inspect next? | Table, dense list, or repeated item cards. |
| Detail | Why is this item in this state? | Split view, tabs, evidence panel, artifact sections. |
| Action rail | What can I do now? | Button group, menu, retry/continue controls. |

## Visual Direction

- Use cold white backgrounds, compact typography, restrained color, clear borders, small radii, and predictable spacing.
- Use cards only for repeated items, modals, or framed tools. Do not put cards inside cards.
- Avoid oversized hero sections in workbench routes, decorative gradients, empty marketing composition, and equal-weight widget walls.
- A product-facing homepage may have a clear first-run CTA, but it must still point quickly into upload, queue, evidence, or run actions.
- Keep metrics close to thresholds, interpretation, and next actions.
- Preserve information density while keeping row height, wrapping, and tap targets accessible.

## ShotgunCV Fit

- Dashboard should surface run health, recent activity, pending gates, high-risk JD, and the create-run path.
- Run Viewer should prioritize pipeline status, artifact availability, ranking changes, and review tasks.
- Detail pages should put JD evidence, resume evidence, score rationale, and generated output in comparable regions.
- Reports should show decisions and risks before narrative explanation.
- Empty states should tell the next valid UI action or pipeline command, and name missing artifacts.

## Responsive Rules

- Desktop: use split panes for list/detail and evidence/result comparison.
- Tablet: keep context and primary actions visible, collapse secondary filters.
- Mobile: stack sections by task priority, not by implementation order.
- Long Chinese text, mixed English identifiers, and long JD titles must wrap without shifting controls unpredictably.

## Common Mistakes

- Dashboard full of equal-weight widgets.
- Metrics without thresholds or action.
- Navigation labels based on internal package names instead of user workflow.
- Hiding errors in logs while showing a green run status.
- Using visual novelty where repeat users need speed.
- Reintroducing CRM, team, template-library, or auto-apply concepts outside the agreed scope.

## Checklist

- [ ] Can a user identify current run status within 5 seconds?
- [ ] Are critical risks and missing artifacts visible without scrolling deeply?
- [ ] Are repeated actions reachable from the work queue?
- [ ] Does the detail view explain why the status exists?
- [ ] Does the layout remain useful when data volume grows?
- [ ] Does the route preserve the local single-user and artifact-first boundary?

## References

- Atlassian Design System: https://atlassian.design/design-system/
- Atlassian Design System overview: https://atlassian.design/get-started/about-atlassian-design-system
