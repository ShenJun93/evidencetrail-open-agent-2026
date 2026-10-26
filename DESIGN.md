---
version: alpha
name: EvidenceTrail
description: A local evidence investigation desk built around source-bound conclusions.
colors:
  primary: "#365ecf"
  background: "#f4f7fb"
  surface: "#ffffff"
  ink: "#172b45"
  muted: "#5d6b80"
  success: "#0e7975"
  warning: "#815212"
  danger: "#ae343d"
typography:
  sans:
    fontFamily: '"Segoe UI", Aptos, system-ui, sans-serif'
  display:
    fontFamily: 'Bahnschrift, "Segoe UI", sans-serif'
  mono:
    fontFamily: 'Consolas, ui-monospace, monospace'
rounded:
  DEFAULT: "10px"
  sm: "6px"
  lg: "16px"
spacing:
  section-gap: "24px"
  page-max: "1440px"
components:
  button: {min-height: "44px"}
  input: {min-height: "44px"}
  panel: {border-width: "1px"}
---

# EvidenceTrail Design System

## Overview

### Creative North Star

An investigator's desk: a strong index on the left, a conclusion on the working sheet, and a visible trail back to the source. The signature is a connected source-to-claim trace, with large quantities and quiet technical metadata.

### Product context and register

Analysts and judges inspect how declared sources change a conclusion. The existing English research interface serves the local demo; there is no inferred geographic market or new translation promise. This is a product surface for desktop investigation with phone access to all actions. It follows the bounded research behavior in `evidencetrail/case_investigator.py`, `case_workbench.py`, and `why_counterfactual.py`.

WHY, timeline and proof use one navigation and typography system. Precise timestamps, limitations and provenance outrank visual simplification. Avoid marketing heroes, fake certainty indicators, decorative dashboards and operational-alert styling.

### Token ownership/runtime mapping

Model B: `demo/ui.css` owns runtime tokens; this document mirrors accepted values. `colors.primary/background/surface/ink/muted/success/warning/danger` map directly to `--accent/--paper/--surface/--ink/--muted/--teal/--warning/--danger`. Typography maps to `--font-body/--font-display/--font-mono`; radius and spacing are implemented by shared control/panel rules. Existing sibling `--bg/--hair/--line/--blue/--olive/--red/--green` are semantic aliases in that file. Change documented values and CSS together; browser checks verify all three routes load the shared owner.

## Colors

Cool paper surrounds white working surfaces. Navy provides headings and the index rail; cobalt identifies actions and selected navigation. Teal identifies source traces, never independent source authentication. Amber marks research limits and abstention; red identifies correctable errors. The product supports a light theme; forced colors use system colors. No dark-mode toggle is advertised.

## Typography

Segoe UI/Aptos is the local body stack, Bahnschrift the local display stack, Consolas the identifier/time stack. No fonts are downloaded. Body is 15px/1.55, controls at least 13px. Quantities use tabular numerals and display type; identifiers and exact ISO times wrap without hiding precision. The current UI remains English (`lang=en`).

## Layout

Desktop has a 216px index rail and a fluid document up to 1440px. Main panels use a two-column investigation grid; the conclusion precedes experiments, timeline and next evidence. At 1000px the rail becomes a horizontal header; at 760px panels and source entry collapse to a single column. The document owns vertical scroll; long source forms have no fixed-height clipping. Spacing uses 8/12/16/24/32px intervals.

## Elevation & Depth

Hierarchy uses borders and tonal surfaces, with a small panel shadow. The persistent desktop index is the only dark surface. No blur or decorative gradients. No overlays are required for core tasks.

## Shapes

Controls use 6px corners, standard panels 10px, the conclusion surface 16px. Source trace connectors use a small circle and vertical line. Borders remain visible at normal and high contrast.

## Components

### Foundational visual states

Hover darkens action borders; focus-visible uses a 3px cobalt outline with offset. Disabled controls retain shape and use an unavailable cursor. Busy status uses the existing live region and disabled submission; errors have text and field associations. Empty/abstaining conclusions explain the next check. Scrollbars have globally owned colors and remain system-operable in forced colors.

### Buttons and actions

One cobalt primary action per local action group. Secondary actions use white surfaces and navy labels. Targets are at least 44px tall. Buttons do not change labels or dimensions during loading.

### Navigation and data display

Route links carry `aria-current=page`. In-page links target named investigation sections. Mobile navigation wraps without hiding links. Claims show quantity, source ID and clock basis; no statistical confidence visualization. Tables retain their column relationships inside labeled overflow regions.

### Forms and overlays

Use existing native controls: the operating system owns select and date popups. Exact instants remain typed text with explicit timezone guidance, never datetime-local conversion. Label wrapping associates fields. Textareas autogrow with resize disabled. Inline preview preserves the adopted case until explicit reviewed adoption. See UX-CONTRACT.md for validation and draft recovery.

### Iconography

The brand mark and section numbers are decorative CSS/text, hidden from accessibility when appropriate. Actions always have visible words; no external icon library.

### Motion

Only brief hover feedback and existing requested scroll-to-section movement. Reduced motion disables smooth scrolling and transitions. No decorative entrance animation.

### Content and data visualization

Plain English actions name what happens: create, preview, add, download, test. Raw evidence IDs remain available for audit. All factual proof counts and caveats are retained. Chart colors on the existing timeline remain evidence categories, not confidence scores.

## Do's and Don'ts

- Do lead with the selected conclusion and its source.
- Do preserve complete timestamps and visible research limits.
- Don't turn a declared hash into an authentication badge.
- Don't introduce external assets, fake metrics or model calls for presentation.
