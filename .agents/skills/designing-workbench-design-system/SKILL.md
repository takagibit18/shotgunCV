---
name: designing-workbench-design-system
description: Use when defining ShotgunCV frontend UI foundations, design tokens, component states, accessibility rules, layout density, or implementation handoff constraints.
---

# Designing Workbench Design System

## Overview

ShotgunCV's design system preserves repeatable decisions for a local, Chinese-first, artifact-driven workbench: tokens, components, states, accessibility, content tone, and density. It should constrain the UI enough that new screens feel like the same operational product.

## Foundations

| Foundation | Rule |
| --- | --- |
| Color | Use cold neutrals for structure, semantic colors for status/risk, and restrained accents for focus. |
| Typography | Use compact hierarchy; avoid viewport-scaled font sizes and oversized headings inside workbench panels. |
| Spacing | Use predictable steps; keep dense pages readable through grouping, not whitespace excess. |
| Radius | Default to small radii for operational UI. |
| Elevation | Use borders and subtle shadows for layers, not decorative depth. |
| Motion | Use motion to preserve orientation, never to delay repeated work. |
| Language | Default visible copy to Chinese; keep English only for technical identifiers and artifact names. |

## Component State Contract

Every reusable component should define:

- Default, hover, focus-visible, active, disabled.
- Loading, empty, error, partial, legacy, and success where applicable.
- Keyboard behavior and accessible name.
- Text overflow and wrapping strategy for Chinese plus English identifiers.
- Mobile behavior.
- Data freshness, artifact provenance, or masked metadata when showing generated or evaluated content.

## ShotgunCV Fit

- Tokens should support pipeline status, gate status, risk severity, evidence strength, artifact mode, and review state.
- Components should work for Chinese primary text with English identifiers.
- Generated content blocks should include source/evidence slots by default.
- Run artifact views should share status, empty, partial, legacy, and error components.
- Settings controls must protect API keys, raw CV/JD text, and unnecessary full local paths.

## Handoff Rules

- Document tokens before creating one-off styles.
- Prefer existing design-system primitives over bespoke CSS for common controls.
- Keep icon buttons accessible with labels or tooltips.
- Verify color contrast and keyboard paths for every task-critical control.
- Avoid building separate visual languages for AI panels and normal workbench panels.
- Remove dead SaaS placeholders, decorative gradients, repeated shadows, and duplicated chip systems.

## Common Mistakes

- Treating the design system as a component gallery only.
- Letting every feature define its own status colors.
- Using gradients or decorative effects as product identity.
- Designing only the happy path.
- Ignoring Chinese text expansion and mixed-language labels.
- Reusing generic SaaS language that implies accounts, teams, remote queues, CRM, or auto-delivery.

## Checklist

- [ ] Are semantic tokens defined before screen-specific colors?
- [ ] Do shared components cover loading, empty, error, partial, and legacy states?
- [ ] Can UI text wrap without breaking controls?
- [ ] Are focus-visible and keyboard paths specified?
- [ ] Does AI UI reuse the same product foundations?
- [ ] Does the design keep the local single-user artifact boundary visible but not repetitive?

## References

- Atlassian Design System: https://atlassian.design/design-system/
- Material Design Accessibility: https://m1.material.io/usability/accessibility.html
- Google People + AI Guidebook: https://pair.withgoogle.com/guidebook-v2/chapters
