---
name: Nabd
description: Kubernetes recovery with a closed formulary
colors:
  dispensary-mint: "#e9f6ee"
  mint-deep: "#d3ebda"
  label-white: "#ffffff"
  pharmacy-ink: "#0f2e1c"
  ink-soft: "#395845"
  dispensary-green: "#3fa565"
  green-light: "#a8dfba"
  green-deep: "#1c6b3c"
  countersign-orange: "#a83f0c"
  orange-paper: "#fdeee4"
  alarm-red: "#b3261e"
typography:
  display:
    fontFamily: "Atkinson Hyperlegible Next Variable, Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "clamp(2.5rem, 1.5rem + 4.2vw, 5.1rem)"
    fontWeight: 780
    lineHeight: 1.02
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Atkinson Hyperlegible Next Variable, Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "clamp(1.9rem, 1.3rem + 2.1vw, 3.1rem)"
    fontWeight: 740
    lineHeight: 1.06
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Atkinson Hyperlegible Next Variable, Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "1.2rem"
    fontWeight: 720
    lineHeight: 1.25
  body:
    fontFamily: "Atkinson Hyperlegible Next Variable, Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "0.72rem"
    fontWeight: 600
    letterSpacing: "0.08em"
  wordmark-ar:
    fontFamily: "Marhey Variable, Marhey, sans-serif"
    fontWeight: 700
rounded:
  tag: "5px"
  control: "8px"
  card: "14px"
  panel: "18px"
  pill: "999px"
spacing:
  gutter: "clamp(1.1rem, 4vw, 3rem)"
  section: "clamp(4.5rem, 9vw, 7.5rem)"
components:
  button-primary:
    backgroundColor: "{colors.pharmacy-ink}"
    textColor: "{colors.label-white}"
    rounded: "{rounded.pill}"
    padding: "0.95rem 1.45rem"
  button-primary-hover:
    backgroundColor: "{colors.green-deep}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.pharmacy-ink}"
    rounded: "{rounded.pill}"
    padding: "0.95rem 1.45rem"
  chip:
    backgroundColor: "{colors.label-white}"
    textColor: "{colors.pharmacy-ink}"
    rounded: "{rounded.pill}"
    padding: "0.6rem 0.9rem"
  chip-selected:
    backgroundColor: "{colors.pharmacy-ink}"
    textColor: "{colors.label-white}"
  label-header:
    backgroundColor: "{colors.dispensary-green}"
    textColor: "{colors.pharmacy-ink}"
    typography: "{typography.label}"
  class-tag-auto:
    backgroundColor: "{colors.mint-deep}"
    textColor: "{colors.green-deep}"
    rounded: "{rounded.tag}"
  class-tag-countersign:
    backgroundColor: "{colors.orange-paper}"
    textColor: "{colors.countersign-orange}"
    rounded: "{rounded.tag}"
---

# Design System: Nabd

## Overview

**Creative North Star: "The Closed Formulary"**

Nabd is presented as a pharmacist who may only dispense what is on a short, fixed list. The whole system is a bright dispensary: a mint ground, white label stock, pharmacy-green ink, and exactly one warning colour for the moments a human must sign. Safety is the product, so the guardrails are shown as the main event (the formulary strip, the countersign box, the "refer to a human" stamp), never as fine print.

It is simple on purpose. Few elements, generous air, one idea per section, and one signature moment: a dispensing label that prints line by line as the agent works. Monospace appears only where real labels and terminals would use it.

**Key Characteristics:**
- Light, mint dispensary ground; white label surfaces with soft depth
- One legibility-first humanist sans for everything readable
- Fixed-width type only on labels, code, and the terminal
- Orange is reserved for countersignature and referral, nothing else
- The printed label is the signature component

## Colors

A restrained clinical palette: mint and white carry the page, deep pharmacy green carries the text, and one orange carries every human decision.

### Primary
- **Dispensary Green** (dispensary-green): the cross in the mark, the label header band, ready pods, completed steps.
- **Deep Pharmacy Green** (green-deep): hover on primary buttons, "automatic" class tags, success text and the dispensed stamp.

### Secondary
- **Countersign Orange** (countersign-orange): anything that needs a human: the countersign box, "countersign" class tags, the refer-to-a-human stamp. On its paper tint (orange-paper) for tags.

### Neutral
- **Dispensary Mint** (dispensary-mint): the page ground.
- **Deep Mint** (mint-deep): quiet tags and secondary fills.
- **Label White** (label-white): labels, panels, the leaflet.
- **Pharmacy Ink** (pharmacy-ink): body text, primary buttons, the terminal ground.
- **Soft Ink** (ink-soft): secondary text and captions.
- **Light Green** (green-light): selection, the closing call-to-action field, terminal accents.
- **Alarm Red** (alarm-red): failing health checks and crashing pods only.

### Named Rules
**The One Signature Colour Rule.** Orange means "a human decides". It never decorates, never marks errors (that is alarm red), and never appears where no human action is involved.

**The Mint Ground Rule.** The page ground is always mint, never white; white is reserved for things you could hold: labels, panels, the leaflet.

## Typography

**Display Font:** Atkinson Hyperlegible Next (with system-ui)
**Body Font:** Atkinson Hyperlegible Next (with system-ui)
**Label/Mono Font:** JetBrains Mono (with ui-monospace)
**Arabic word mark:** Marhey

**Character:** a typeface built for legibility, the same promise a medicine label makes, set heavy and tight for headlines and open for reading. The rounded Arabic نبض softens the mark.

### Hierarchy
- **Display** (780, clamp up to 5.1rem, 1.02): page headlines only.
- **Headline** (740, clamp up to 3.1rem, 1.06): section headings.
- **Title** (720, 1.2rem, 1.25): step names, leaflet entries, panel headings.
- **Body** (400, 1.0625rem, 1.55): all reading text, measure kept under about 36em in ledes.
- **Label** (600, 0.72rem, 0.08em tracking, uppercase): label terms, class tags, table headers, terminal bars.

### Named Rules
**The Real Mono Rule.** Monospace is for things that are code or printed labels: action names, kubectl, the terminal, label rows. Never for headings or decoration.

## Layout

A single centred column up to 1180px with a fluid gutter. The landing page alternates dense and quiet passages: hero with the live label, a hairline formulary strip, an eight-step grid, the white leaflet panel, results table, limits, and a mint-green closing field. The demo is a vertical sequence of four stage panels under a sticky stepper; each stage appears only after the previous one, and inside a stage the status sits beside the terminal on wide screens and stacks below 900px. Sections are separated by the section spacing token; headings carry more space above than below.

## Elevation & Depth

Mostly flat on the mint ground; white surfaces lift with one soft, offset shadow so they read as paper on a counter. No coloured glows, no hard offset shadows.

### Shadow Vocabulary
- **Label lift** (`box-shadow: 0 1px 0 rgb(15 46 28 / 0.06), 0 22px 44px -22px rgb(15 46 28 / 0.38)`): labels, the leaflet, stage panels.

## Shapes

Friendly, rounded and consistent: pills for every action and tag-like control, 14px for labels and the terminal, 18 to 20px for large panels, 5px for class tags. The countersign line is a dashed tear-off rule, the one place a dashed border appears.

## Components

### Buttons
- **Shape:** full pill (999px).
- **Primary:** pharmacy ink with white text, 700 weight; hover shifts to deep pharmacy green; 1px press on active.
- **Ghost:** transparent with a 2px ink border; hover fills with label white.

### Chips
- **Style:** white pill with a hairline border; selected chips invert to ink with white text.

### Dispensing label (signature)
- **Header:** dispensary-green band with the dispensary name and Rx number in the label face.
- **Rows:** term and value in two columns that stack when the label is narrower than 27rem; each row prints in with a short clip reveal.
- **Countersign:** dashed tear-off line; turns orange with Approve and Decline when a medium-risk action needs a human; resolves to a rotated stamp.
- **Outcome stamp:** "Dispensed · healthy" in deep green or "Refer to a human" in orange.

### Navigation
- **Style:** mark, Latin name and Arabic word mark on the left; four text links on the right with a 2px green underline on hover and on the current page.

### Demo terminal
- **Style:** pharmacy-ink ground, light green chrome, mono 0.8rem; tables keep their columns and scroll sideways, prose wraps.

## Do's and Don'ts

### Do:
- **Do** keep the page ground mint and put real content on white label surfaces.
- **Do** reserve orange for countersignature and referral only.
- **Do** show the guardrails (formulary, countersign, referral) as visible parts of the interface.
- **Do** label anything simulated as simulated, and show only numbers that come from benchmark output.

### Don't:
- **Don't** use monospace for headings or decoration.
- **Don't** add eyebrow labels above headings or gradient text.
- **Don't** use coloured glows or hard offset shadows for depth.
- **Don't** use emoji or Unicode glyphs as icons; draw icons as SVG in one stroke weight.
