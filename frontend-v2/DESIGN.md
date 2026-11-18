---
name: MARCUS
description: From a journal PDF to checked chemical structures for COCONUT, drawn as a survey sheet.
colors:
  paper: "#F4F3EA"
  surface: "#FFFFFF"
  sunken: "#ECEBE1"
  ink: "#1C211D"
  text-2: "#3F443D"
  muted: "#5E625B"
  line: "#B9BCB2"
  hair: "#D9DACF"
  tick: "#9FA398"
  hatch: "#E6E5DC"
  control-border: "#7E8279"
  green: "#1E4D33"
  accepted: "#2D7A46"
  orange: "#FA3600"
  orange-ink: "#B82800"
  charcoal: "#1C211D"
  on-green: "#FFFFFF"
  on-orange: "#141414"
  on-charcoal: "#F4F3EA"
  selection: "#DCEBDF"
typography:
  display:
    fontFamily: "Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "clamp(36px, 4vw + 18px, 76px)"
    fontWeight: 700
    lineHeight: 0.92
    letterSpacing: "-0.035em"
  headline:
    fontFamily: "Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "30px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "22px"
    fontWeight: 700
    lineHeight: 1.2
  body:
    fontFamily: "Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.6
  body-sm:
    fontFamily: "Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Geist Mono, ui-monospace, SFMono-Regular, Menlo, monospace"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "0.06em"
  label-control:
    fontFamily: "Geist Mono, ui-monospace, SFMono-Regular, Menlo, monospace"
    fontSize: "13px"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "0.06em"
  data:
    fontFamily: "Geist Mono, ui-monospace, SFMono-Regular, Menlo, monospace"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
  wordmark:
    fontFamily: "Gmarket Sans, Geist, sans-serif"
    fontSize: "28px"
    fontWeight: 300
    lineHeight: 1
    letterSpacing: "0.06em"
rounded:
  none: "0"
  control: "2px"
  key: "3px"
  pill: "999px"
  round: "50%"
spacing:
  rule: "1px"
  xs: "6px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  xxl: "64px"
components:
  button-glass-orange:
    textColor: "{colors.on-orange}"
    typography: "{typography.label-control}"
    rounded: "{rounded.pill}"
    padding: "12px 20px"
  button-glass-green:
    textColor: "{colors.on-green}"
    typography: "{typography.label-control}"
    rounded: "{rounded.pill}"
    padding: "12px 20px"
  button-glass-clear:
    textColor: "{colors.ink}"
    typography: "{typography.label-control}"
    rounded: "{rounded.pill}"
    padding: "12px 20px"
  button-glass-sm:
    rounded: "{rounded.pill}"
    padding: "8px 14px"
  button-glass-disabled:
    backgroundColor: "{colors.hair}"
    textColor: "{colors.muted}"
    rounded: "{rounded.pill}"
  nav-cell:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "12px 14px 26px"
    width: "150px"
  nav-cell-hover:
    backgroundColor: "{colors.sunken}"
  nav-cell-tool:
    backgroundColor: "{colors.green}"
    textColor: "{colors.on-green}"
    width: "170px"
  nav-cell-tool-hover:
    backgroundColor: "{colors.ink}"
  segment:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "7px 12px"
  segment-pressed:
    backgroundColor: "{colors.green}"
    textColor: "{colors.on-green}"
  select:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 10px"
    height: "40px"
  structure-card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.none}"
    padding: "14px"
  specimen-head:
    backgroundColor: "{colors.charcoal}"
    textColor: "{colors.on-charcoal}"
    typography: "{typography.label}"
    padding: "6px 10px"
  badge-to-check:
    backgroundColor: "{colors.orange}"
    textColor: "{colors.on-orange}"
    typography: "{typography.label}"
    padding: "1px 6px"
  tag-failed:
    backgroundColor: "{colors.charcoal}"
    textColor: "{colors.on-charcoal}"
    typography: "{typography.label}"
    padding: "1px 6px"
  stamp-sm:
    textColor: "{colors.accepted}"
    rounded: "{rounded.round}"
    size: "66px"
  stamp-lg:
    textColor: "{colors.accepted}"
    rounded: "{rounded.round}"
    size: "128px"
  toast:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "10px 16px"
  toast-error:
    backgroundColor: "{colors.charcoal}"
    textColor: "{colors.on-charcoal}"
---

# Design System: MARCUS

## Overview

**Creative North Star: "The Survey Sheet"**

Every screen is a drawing sheet laid flat on a warm paper ground: a hairline frame, ruled cells, "+" corner marks, ruler ticks every 8px, and mono captions that read like a plate's title block. Structures sit in surface-white cells inside that grid, and the curation states are marked on the sheet the way a surveyor marks a field sheet: a round stamp for accepted, a cross-out for rejected, a hatched ground for failed, an orange fill or outline for what still needs a person's eyes.

The density is a working document, not a brochure. Cells share 1px rules instead of floating as cards; type is either a heavy uppercase Geist heading in forest green or a small uppercase Geist Mono readout. The only objects that rise off the sheet are the liquid-glass pill buttons, which sit on light grounds and carry the actions. Light mode only.

The world is evidence-first: page numbers, bounding boxes, engine names and counts are printed as readouts, never decorated. Copy is minimal; a state is its exact word.

**Key Characteristics:**
- Warm paper ground (#F4F3EA) with white structure cells, ruled by 1px hairlines.
- Forest green leads; orange asks for attention; charcoal marks rejected and failed.
- Geist 700 uppercase headings, Geist Mono uppercase labels and readouts; two weights per family.
- Square cells and sheets; round only for things that act (pills) or mark (stamps, dots).
- Flat sheet; glass pills, menus, toasts and dialogs are the only lifted objects.

## Colors

A muted field palette: warm paper and graphite rules, one deep forest green that leads, one signal orange that asks, charcoal for what was struck or failed.

### Primary
- **Forest Green** (green): the h1, links, the "Open the tool" nav cell, pressed segments, selected-card rings, the focus outline, caret and accent colour, and the green glass pill for committing work (Accept, Send to COCONUT).
- **Accepted Green** (accepted): the word "Accepted", the accepted stamp ring and the accepted count dot. Text in this colour sits on paper or surface only.

### Secondary
- **Signal Orange** (orange): the colour of "needs your eyes". The To check badge fill, the 2px inside edge of a card to check, the dashed outline of a structure being read, bounding boxes on the example page, and the orange glass pill for the first action on a screen (Upload a PDF). Shapes and fills only, never small text.
- **Orange Ink** (orange-ink): small orange text, such as the [01] index tags and "DECIMER and MolNexTR differ" notes.

### Tertiary
- **Charcoal** (charcoal): the specimen-label header bar, the Failed tag, the rejected stamp ring and the diagonal strike, and the error toast.

### Neutral
- **Survey Paper** (paper): the page ground and the ground of every sheet cell that is not a structure.
- **Plate White** (surface): structure cells, specimen tables, inputs, toasts, the example page.
- **Sunken Paper** (sunken): hover ground for nav cells and segments, the review preview band, the keys bar.
- **Field Ink** (ink): body text and headings below the h1; also the hover colour of links.
- **Graphite Text** (text-2): secondary paragraphs and field labels.
- **Pencil Muted** (muted): mono captions, counts, placeholders, struck SMILES, the footer.
- **Frame Line** (line): sheet frames, cell rules and the 1px gaps between cells. Never a control edge.
- **Inner Hair** (hair): rules inside a specimen table, the glass-bed grid, the disabled pill.
- **Ruler Tick** (tick): ruler ticks and the waiting mark in an empty structure cell.
- **Hatch Stripe** (hatch): the darker stripe of the failed ground (135deg, 6px stripes with paper).
- **Control Edge** (control-border): every control's border: inputs, selects, checkboxes, segmented sets, switches, the solid clear pill.
- **Selection Mint** (selection): text selection.
- **On-colours** (on-green, on-orange, on-charcoal): text set on the green, orange and charcoal fills.

### Named Rules
**The Orange Asks Rule.** Orange means a person is needed: to check, being read, or the one first action. It never decorates, never marks success, and never sets small text (use orange-ink).

**The Word and Shape Rule.** A state is always its exact word plus a shape: Accepted with the round stamp, To check with the orange fill, Reading with the dashed orange outline, Rejected in charcoal with the cross-out, Failed with the charcoal tag on the hatched ground, Not read yet in muted. Colour alone never carries a state.

**The Green on Paper Rule.** Accepted-green text sits on paper or surface only, never on sunken (4.4:1 there). A band that carries the Accepted count uses paper.

**The Control Edge Rule.** Every control edge is control-border (3.3:1 or more on every ground). The frame line (about 1.7:1) draws sheets and cells, never something you click or type into.

## Typography

**Display Font:** Geist (with ui-sans-serif, system-ui)
**Body Font:** Geist (with ui-sans-serif, system-ui)
**Label/Mono Font:** Geist Mono (with ui-monospace, SFMono-Regular, Menlo)
**Wordmark:** Gmarket Sans Light, subset to the letters of MARCUS, wordmark only.

**Character:** A blunt engineering grotesque for headings and prose, paired with a monospace that prints every label, readout, button and SMILES string like a title block. Self-hosted from @fontsource 5.3.0, Latin only.

### Hierarchy
- **Display** (Geist 700, clamp(36px, 4vw + 18px, 76px), line-height 0.92, -0.035em, uppercase, forest green): the one h1 per page, max about 14ch.
- **Headline** (Geist 700, 30px, line-height 1, -0.02em, uppercase): section and card headings; 26px under 900px.
- **Title** (Geist 700, 22px, line-height 1.2): names of things, such as a paper's file name or "Example paper"; sentence case and file case kept.
- **Body** (Geist 400, 16px, line-height 1.6): prose, lead text capped at about 40ch.
- **Body small** (Geist 400, 14px, line-height 1.5, text-2): card lines and notes, capped at about 42ch.
- **Label** (Geist Mono 400, 11px, 0.05 to 0.08em, uppercase, muted): captions, readouts, specimen row heads, state words, footer.
- **Control label** (Geist Mono 500, 13px, 0.06em, uppercase; 12px in small pills, segments and nav cells): every button and nav cell.
- **Data** (Geist Mono 400, 12px, line-height 1.5): SMILES and other machine strings, wrapping anywhere, never uppercased.

### Named Rules
**The Two Weights Rule.** Geist ships 400 and 700, Geist Mono 400 and 500, with font-synthesis-weight off. No other weights.

**The Uppercase in CSS Rule.** Headings, labels and buttons are uppercased by CSS; the source text stays in sentence case. Machine strings (SMILES, file names) keep their case.

**The Mono Speaks for the Machine Rule.** Anything the tool measures, counts or names (pages, bboxes, engines, counts, keys) is set in Geist Mono; prose a person reads is Geist.

## Layout

The app sits in one framed sheet: max width 1440px, 8px outer padding, a 1px line frame filling the window height. Inside, everything is rows of ruled cells. Cells share edges by sitting in a grid with a 1px gap over a line-coloured background, or by each cell ruling its own right and bottom edge, so the rules are always exactly 1px and never double.

The header is a row of cells: the mark on the left, then fixed nav cells (150px; the green tool cell 170px) with their text set top-left and generous bottom padding. Section insets are 24px horizontally (16px on phones); cell padding sits between 14px and 24px. Small gaps step 6 / 8 / 12 / 16 / 24px; the ruler tick unit is 8px and the glass-bed grid 16px.

The review grid is auto-fill columns of at least 300px structure cells. Breakpoints observed: 560px (phone; nav becomes 2 columns), 720px (lead stacks), 900px (three cards stack), 960px (nav drops to its own ruled row of 4), 1024px (the tool's minimum width; below it the tool shows a desktop-only note), 1200px and 1280px (lead and workspace column changes). Only the landing page is built for phones.

## Elevation & Depth

The sheet is flat. Depth comes from tone (paper, white cells, sunken bands, the hatched failed ground) and from hairlines, not shadows. The example page on the landing lies flat with only a 1px hair underline. Shadows belong to the few objects that float above the sheet, all in one green-black ambient family (rgba(15, 30, 22, 0.35)): glass pills, toasts and menus, and dialogs (the structure editor and the COCONUT submission).

### Shadow Vocabulary
- **Glass lift** (`0 10px 24px -8px rgba(15, 30, 22, 0.35)` plus the pill's inner highlights): glass pill buttons; also toasts and the card's floating menu.
- **Menu lift** (`0 12px 28px -10px rgba(15, 30, 22, 0.35)`): workspace disclosures such as Export.
- **Dialog lift** (`0 24px 64px -24px rgba(15, 30, 22, 0.45)`): the editor and COCONUT dialogs.
- **Solid pill fallback** (`0 6px 16px -8px rgba(15, 30, 22, 0.35)`): glass pills under reduced transparency or without backdrop-filter.

### Named Rules
**The Flat Sheet Rule.** Nothing printed on the sheet casts a shadow. Only objects that act or float (pills, menus, toasts, dialogs) lift.

**The Light Ground Rule.** Glass pills sit on light grounds only: paper, surface, sunken, or the glass bed. Never on charcoal or on a picture (the clear tint drops to 2.3:1 there).

## Shapes

Rectangles with square corners for everything that holds content: the frame, cells, structure cards, specimen tables, toasts, segmented controls. Small radii only on form controls (2px on selects and inputs, 3px on key caps). Round forms are reserved: the 999px pill for actions, the 50% circle for stamps, count dots and switch knobs. The drawing-sheet primitives repeat everywhere: the "+" corner mark, horizontal and vertical ruler ticks (1px every 8px, 7px deep), the 16px glass-bed grid behind button clusters, the 135deg hatch, and the 2px charcoal diagonal strike across a rejected structure.

## Components

### Buttons
Liquid glass on paper: tactile pills that are the only shiny thing on a matte sheet.
- **Shape:** full pill (999px), Geist Mono 500 uppercase, 13px at 12px 20px; small variant 12px at 8px 14px.
- **Orange glass:** gradient rgba(255,118,72,.95) to rgba(250,54,0,.9), on-orange text: the first action (Upload a PDF).
- **Green glass:** gradient rgba(46,110,74,.95) to rgba(30,77,51,.92), on-green text: commit actions (Accept, Send to COCONUT).
- **Clear glass:** white 70% to 25% gradient, ink text: everything else (Reject, Compare, More, Export, Copy).
- **Material:** backdrop-filter blur(3px) saturate(1.8) with the #marcus-glass SVG refraction where supported; inner top highlight and a soft bottom shade.
- **Hover / Focus:** scale(1.03) over 160ms cubic-bezier(0.16, 1, 0.3, 1) when motion is allowed; 2px forest-green outline at 2px offset. Disabled is a flat hair pill with muted text.
- **Fallbacks:** solid orange, green, or white with a control-border ring under reduced transparency or without backdrop-filter; a ButtonBorder edge in forced colours.
- **Text links as buttons:** small Geist Mono 500 uppercase in green with an underline that appears on hover (Copy, Select all shown).

### Segmented filters
- **Style:** a control-border box of square surface segments divided by control-border rules, Geist Mono 500 12px uppercase, muted tabular counts.
- **State:** hover sunken; pressed fills forest green with on-green text and counts.

### Structure cards
- **Corner Style:** square.
- **Background:** surface; failed cards on the hatched ground.
- **Border:** each card rules its right and bottom edge in line; to check adds a 2px orange inside edge, selected a 3px green inside ring, both stack.
- **Internal Padding:** 14px, 8px between rows: tag row (checkbox, [nn] · page, state), drawing, SMILES row with Copy, engine readout, pill row.
- **Rejected:** drawing at 55% opacity under the charcoal diagonal strike, SMILES struck through in muted, charcoal stamp drawn above the strike.

### Inputs / Fields
- **Style:** surface ground, 1px control-border edge, 2px radius, 40px tall, 15px Geist; labels in mono over text-2.
- **Switch:** 38 by 22px pill with a control-border edge and a round knob.
- **Focus:** the global 2px forest-green outline at 2px offset.
- **Disabled:** 55% opacity, not-allowed cursor.

### Navigation
- **Style:** header row of ruled cells; Geist Mono 12px uppercase, ink on paper, text set top-left.
- **States:** hover sunken; the tool cell is solid forest green and turns ink on hover; focus outline drawn inside the cell (-4px offset).
- **Mobile:** below 960px the nav is its own ruled row of four cells; below 560px two columns.

### Specimen label
A data table drawn like a herbarium label: a charcoal header bar with on-charcoal mono caption, then rows on surface ruled by hair, mono uppercase row heads in muted, values in ink. A failed specimen lies on the hatched ground.

### Stamp
A round 2px ring rotated -12deg with Geist Mono 500 uppercase text: 66px / 10px on cards, 128px / 17px large. Accepted in accepted green, rejected in charcoal. When a decision is made it lands from scale 1.4 to rest in 160ms; no motion under reduced motion.

### Toasts
Square surface slips with a line border and the glass-lift shadow, mono 12px uppercase, sliding up 8px over 200ms from the bottom right. Errors invert to charcoal.

## Do's and Don'ts

### Do:
- **Do** rule cells with exactly 1px of line, by a 1px grid gap over a line background or by right and bottom edges, never by doubled borders.
- **Do** pair every state with its word and shape (stamp, orange fill, dashed outline, strike, hatch); colour alone never decides.
- **Do** set small orange text in orange-ink and keep orange itself for fills, outlines and markers.
- **Do** put accepted-green text on paper or surface only.
- **Do** give every control a control-border (#7E8279) edge.
- **Do** set headings, labels and buttons uppercase through CSS and keep source text in sentence case.
- **Do** place glass pills on paper, surface, sunken or the glass bed, with their solid fallbacks intact.
- **Do** keep every size, tint and rotation in a stylesheet class: no inline style attributes in pre-rendered components and no innerHTML (strict CSP).
- **Do** use the one easing, cubic-bezier(0.16, 1, 0.3, 1), at 160 to 220ms, and drop motion under prefers-reduced-motion.

### Don't:
- **Don't** add a dark mode; the system is light only.
- **Don't** use orange for anything that does not need a person's attention.
- **Don't** put accepted-green text on sunken.
- **Don't** draw a control edge in line or hair.
- **Don't** put glass pills on charcoal or over a picture.
- **Don't** cast shadows from things printed on the sheet: cells, cards, tables, the example page.
- **Don't** load a weight outside Geist 400/700 and Geist Mono 400/500, or use Gmarket Sans for anything but the wordmark.
- **Don't** round content containers; radius is for pills, stamps, dots and small control corners.
