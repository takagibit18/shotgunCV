---
name: designing-saas-design-systems
description: Use when defining frontend UI foundations, design tokens, component states, accessibility rules, layout density, or implementation handoff constraints for SaaS products.
---

# Designing SaaS Design Systems

## Overview

A SaaS design system should preserve repeatable decisions: tokens, components, states, accessibility, content tone, and density. It should constrain product UI enough to stay coherent as screens multiply.

## Foundations

| Foundation | Rule |
| --- | --- |
| Color | Use neutrals for structure, semantic colors for status, one restrained accent for focus. |
| Typography | Use compact hierarchy; avoid viewport-scaled font sizes. |
| Spacing | Use predictable steps; keep dense pages readable through grouping, not whitespace excess. |
| Radius | Default to small radii for operational UI unless existing system differs. |
| Elevation | Use borders and subtle shadows for layers, not decorative depth. |
| Motion | Use motion to preserve orientation, never to delay repeated work. |

## Component State Contract

Every reusable component should define:

- Default, hover, focus-visible, active, disabled.
- Loading, empty, error, partial, and success where applicable.
- Keyboard behavior and accessible name.
- Text overflow strategy.
- Mobile behavior.
- Data freshness or provenance when showing generated or evaluated content.

## ShotgunCV Fit

- Tokens should support pipeline status, risk severity, evidence strength, and review state.
- Components should work for Chinese primary text with English identifiers.
- Generated content blocks should include source/evidence slots by default.
- Run artifact views should share status, empty, and error components.

## Handoff Rules

- Document tokens before creating one-off styles.
- Prefer design-system primitives over bespoke CSS for common controls.
- Keep icon buttons accessible with labels or tooltips.
- Verify color contrast and keyboard paths for every task-critical control.
- Avoid building separate visual languages for AI panels and normal SaaS panels.

## Common Mistakes

- Treating the design system as a component gallery only.
- Letting every feature define its own status colors.
- Using gradients or decorative effects as product identity.
- Designing only the happy path.
- Ignoring Chinese text expansion and mixed-language labels.

## Checklist

- [ ] Are semantic tokens defined before screen-specific colors?
- [ ] Do shared components cover loading, empty, error, and partial states?
- [ ] Can UI text wrap without breaking controls?
- [ ] Are focus-visible and keyboard paths specified?
- [ ] Does AI UI reuse the same product foundations?

## References

- Atlassian Design System: https://atlassian.design/design-system/
- Material Design Accessibility: https://m1.material.io/usability/accessibility.html
- Google People + AI Guidebook: https://pair.withgoogle.com/guidebook-v2/chapters
