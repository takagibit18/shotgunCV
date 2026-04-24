---
name: designing-saas-operational-workspaces
description: Use when designing SaaS dashboards, operational workspaces, run viewers, detail pages, monitoring pages, or workflow-heavy product screens.
---

# Designing SaaS Operational Workspaces

## Overview

Operational SaaS UI should be dense, calm, and task-first. It should help users scan status, compare entities, inspect evidence, and take repeated actions without marketing-style decoration.

## Workspace Structure

| Layer | Purpose | UI pattern |
| --- | --- | --- |
| Global context | Where am I and what run/workspace is active? | Header, breadcrumb, run selector. |
| Primary status | What changed and what needs attention? | Compact summary strip, alerts, progress. |
| Work queue | What should I inspect next? | Table, list, grouped cards only for repeated items. |
| Detail | Why is this item in this state? | Split view, drawer, tabs, evidence panel. |
| Action rail | What can I do now? | Button group, menu, keyboard-safe controls. |

## Visual Direction

- Prefer compact typography, restrained color, clear borders, and predictable spacing.
- Use cards only for repeated items, modals, or framed tools.
- Avoid oversized hero sections, decorative gradients, and empty marketing composition.
- Keep charts and metrics close to their interpretation and next action.
- Preserve information density while keeping row height and tap targets accessible.

## ShotgunCV Fit

- Run Viewer should prioritize pipeline status, artifact availability, ranking changes, and review tasks.
- Detail pages should put JD evidence, candidate evidence, score rationale, and generated output in comparable regions.
- Reports should show decisions and risks before narrative explanation.
- Empty states should tell the next valid pipeline command or missing artifact.

## Responsive Rules

- Desktop: use split panes for list/detail and evidence/result comparison.
- Tablet: keep context and primary actions visible, collapse secondary filters.
- Mobile: stack sections by task priority, not by implementation order.

## Common Mistakes

- Dashboard full of equal-weight widgets.
- Metrics without thresholds or action.
- Navigation labels based on internal package names instead of user workflow.
- Hiding errors in logs while showing a green run status.
- Using visual novelty where repeat users need speed.

## Checklist

- [ ] Can a user identify current run status within 5 seconds?
- [ ] Are critical risks and missing artifacts visible without scrolling deeply?
- [ ] Are repeated actions reachable from the work queue?
- [ ] Does the detail view explain why the status exists?
- [ ] Does the layout remain useful when data volume grows?

## References

- Atlassian Design System: https://atlassian.design/design-system/
- Atlassian Design System overview: https://atlassian.design/get-started/about-atlassian-design-system
- SaaSUI dashboard patterns: https://www.saasui.design/pattern/dashboard
