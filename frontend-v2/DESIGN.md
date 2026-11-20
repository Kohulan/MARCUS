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
  ann-organism: "#2F6A1A"
  ann-organism-tint: "#C8E4A4"
  ann-part: "#7A5600"
  ann-part-tint: "#F7E08C"
  ann-place: "#1D5DA6"
  ann-place-tint: "#CFE3FA"
  ann-name: "#A3305F"
  ann-name-tint: "#FBD7E5"
  ann-class: "#6A3CA6"
  ann-class-tint: "#D2BEF2"
  ann-systematic: "#17675F"
  ann-systematic-tint: "#9FD6CB"
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
  display-acrostic:
    fontFamily: "Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "72px"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "-0.035em"
  display-info:
    fontFamily: "Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "clamp(36px, 2.6vw + 18px, 60px)"
    fontWeight: 700
    lineHeight: 0.92
    letterSpacing: "-0.035em"
  drop-title:
    fontFamily: "Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "44px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.02em"
  empty-title:
    fontFamily: "Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "32px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.02em"
  note-title:
    fontFamily: "Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "24px"
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: "-0.02em"
  heading-sm:
    fontFamily: "Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.15
  dialog-title:
    fontFamily: "Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  prose-lg:
    fontFamily: "Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.3
  prose-md:
    fontFamily: "Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.45
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
  nav-waterline:
    textColor: "{colors.ink}"
    typography: "{typography.label-control}"
    rounded: "{rounded.pill}"
    padding: "4px"
  nav-waterline-item:
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "12px 16px"
  footer-bubble:
    textColor: "{colors.text-2}"
    rounded: "{rounded.pill}"
    padding: "4px 16px"
    height: "24px"
  drop-ring:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    size: "124px"
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
  progress-bar:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-2}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    height: "10px"
  progress-bar-fill:
    backgroundColor: "{colors.green}"
  progress-bar-small:
    height: "6px"
---

# Design System: MARCUS

## Overview

**Creative North Star: "The Survey Sheet"**

Every screen is a drawing sheet laid flat on a warm paper ground: a hairline frame, ruled cells, "+" corner marks, ruler ticks every 8px, and mono captions that read like a plate's title block. Structures sit in surface-white cells inside that grid, and the curation states are marked on the sheet the way a surveyor marks a field sheet: a round stamp for accepted, a cross-out for rejected, a hatched ground for failed, an orange fill or outline for what still needs a person's eyes.

The density is a working document, not a brochure. Cells share 1px rules instead of floating as cards; type is either a heavy uppercase Geist heading in forest green or a small uppercase Geist Mono readout. The only objects that rise off the sheet are the liquid-glass pill buttons (the header's Waterline nav among them), which sit on light grounds and carry the actions, and the footer's porcelain bubbles. The header and the footer float free of the ruled sheet: the frame is the page's own. Light mode only.

The world is evidence-first: page numbers, bounding boxes, engine names and counts are printed as readouts, never decorated. Copy is minimal; a state is its exact word.

**Key Characteristics:**
- Warm paper ground (#F4F3EA) with white structure cells, ruled by 1px hairlines.
- Forest green leads; orange asks for attention; charcoal marks rejected and failed.
- Geist 700 uppercase headings, Geist Mono uppercase labels and readouts; two weights per family.
- Square cells and sheets; round only for things that act (pills) or mark (stamps, dots).
- Flat sheet; glass pills (the Waterline nav included), porcelain footer bubbles, menus, toasts and dialogs are the only lifted objects.
- Icons are Font Awesome Free 6.7.2 (CC BY 4.0), inline SVG through one Icon component, always beside a word.

## Colors

A muted field palette: warm paper and graphite rules, one deep forest green that leads, one signal orange that asks, charcoal for what was struck or failed.

### Primary
- **Forest Green** (green): the h1 (the landing's acrostic initials), links, the nav's water drop and icons, the footer icons, pressed segments, selected-card rings, the focus outline, caret and accent colour, and the green glass pill for committing work (Accept, Send to COCONUT).
- **Accepted Green** (accepted): the word "Accepted", the accepted stamp ring and the accepted count dot. Text in this colour sits on paper or surface only.

### Secondary
- **Signal Orange** (orange): the colour of "needs your eyes". The To check badge fill, the 2px inside edge of a card to check, the dashed outline of a structure being read, the landing's drop ring while a file is dragged over it (drag-over is a moment that needs the person), and the orange glass pill for the first action on a screen (Try a sample paper on the landing, Choose a file in the tool). Shapes and fills only, never small text.
- **Orange Ink** (orange-ink): small orange text, such as the [01] index tags and "Engines differ" notes.

### Tertiary
- **Charcoal** (charcoal): the specimen-label header bar, the Failed tag, the rejected stamp ring and the diagonal strike, and the error toast.

### Neutral
- **Survey Paper** (paper): the page ground and the ground of every sheet cell that is not a structure.
- **Plate White** (surface): structure cells, specimen tables, inputs, toasts, the landing's drop ring, the example crop on About.
- **Sunken Paper** (sunken): hover ground for segments, the review preview band (About), the keys bar.
- **Field Ink** (ink): body text and headings below the h1; also the hover colour of links.
- **Graphite Text** (text-2): secondary paragraphs and field labels.
- **Pencil Muted** (muted): mono captions, counts, placeholders, struck SMILES, the workspace's thin footer, "and" and "for" in the landing's acrostic.
- **Frame Line** (line): sheet frames, cell rules and the 1px gaps between cells. Never a control edge.
- **Inner Hair** (hair): rules inside a specimen table, the glass-bed grid, the disabled pill.
- **Ruler Tick** (tick): ruler ticks and the waiting mark in an empty structure cell.
- **Hatch Stripe** (hatch): the darker stripe of the failed ground (135deg, 6px stripes with paper).
- **Control Edge** (control-border): every control's border: inputs, selects, checkboxes, segmented sets, switches, the solid clear pill.
- **Selection Mint** (selection): text selection.
- **On-colours** (on-green, on-orange, on-charcoal): text set on the green, orange and charcoal fills.

### Named Rules
**The Orange Asks Rule.** Orange means a person is needed: to check, being read, a file being dragged over the drop ring, or the one first action. It never decorates, never marks success, and never sets small text (use orange-ink).

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
- **Display acrostic** (the landing's h1 only; an owner-approved exception to Display = 700): the name spelled out, one word a line, uppercase, on the type scale: 72px, 60px below 1280px wide or 800px tall (and below 1024px), 48px below 720px, 36px / 40px below 560px; line-height 1. The initials M A R C U S are Geist 700 in forest green, the rest of each word Geist 400 in ink, "and" and "for" in muted. Screen readers get the plain name from a visually hidden copy; the drawn letters are aria-hidden. Once per page load the name assembles (1.5 s, the one curve, transform and opacity only): the six initials stand as one word, MARCUS, centred on the title, glide into the column, and each word's rest slides out from behind its initial; it ends on the layout itself, with no shift. A later visit in the same tab, and reduced motion, show the name at rest.
- **Headline** (Geist 700, 30px, line-height 1, -0.02em, uppercase): section and card headings; 26px under 900px.
- **Title** (Geist 700, 22px, line-height 1.2): names of things, such as a paper's file name or "Example paper"; sentence case and file case kept.
- **Body** (Geist 400, 16px, line-height 1.6): prose, lead text capped at about 40ch.
- **Body small** (Geist 400, 14px, line-height 1.5, text-2): card lines and notes, capped at about 42ch.
- **Label** (Geist Mono 400, 11px, 0.05 to 0.08em, uppercase, muted): captions, readouts, specimen row heads, state words, the workspace's thin footer.
- **Landing, header and footer** follow the landing-page-design skill's type scale and spacing table (tokens.css --s-25 to --s-900) and its one curve (--ease, cubic-bezier(0.22, 1, 0.36, 1); 500ms for movement, 300ms for colour and opacity; transform and opacity only): the lead sentence Geist 400 18px / 28px, the facts line, the drop hint and the footer Geist Mono 400 12px / 16px, the nav items Geist Mono 500 12px / 16px, the drop ring's words Geist 700 16px / 24px, the sample pill Geist Mono 500 14px / 20px with 12px / 24px padding.
- **Control label** (Geist Mono 500, 13px, 0.06em, uppercase; 12px in small pills, segments and the nav's items): every button and nav item.
- **Data** (Geist Mono 400, 12px, line-height 1.5): SMILES and other machine strings, wrapping anywhere, never uppercased.

Secondary steps, each kept to one kind of thing:
- **Display info** (Geist 700, clamp(36px, 2.6vw + 18px, 60px), uppercase, forest green): the h1 of About, Privacy and Disclaimer.
- **Drop title** (Geist 700, 44px, uppercase): the tool home's drop zone heading.
- **Empty title** (Geist 700, 32px, line-height 1, uppercase): a paper or image that is gone.
- **Note title** (Geist 700, 24px, line-height 1.05, uppercase): the desktop-only note and the COCONUT results heading.
- **Heading small** (Geist 700, 20px, line-height 1.15, uppercase): info-page section headings and the tool home's Images heading; the mono readout in an empty drawing takes the same size.
- **Dialog title** (Geist 700, 18px, line-height 1.2, -0.01em, uppercase): the editor, COCONUT, Compare and Keys dialogs; the info lede (Geist 400) and the example card's failure title share the size.
- **Prose large** (Geist, 17px, line-height 1.3): paper names in the tool's list (700) and the empty-list line.
- **Prose medium** (Geist 400, 15px, line-height 1.45): text in the tool: field values, notes, problems, the paper view's text, the focus-mode step arrows.

### Named Rules
**The Two Weights Rule.** Geist ships 400 and 700, Geist Mono 400 and 500, with font-synthesis-weight off. No other weights.

**The Uppercase in CSS Rule.** Headings, labels and buttons are uppercased by CSS; the source text stays in sentence case. Machine strings (SMILES, file names) keep their case.

**The Mono Speaks for the Machine Rule.** Anything the tool measures, counts or names (pages, bboxes, engines, counts, keys) is set in Geist Mono; prose a person reads is Geist.

## Layout

The app sits on one page: max width 1440px, 8px outer padding (12px at the bottom). The header (the mark and the Waterline pill) floats free above the ruled sheet, with no box or rule around it; the page below it carries the 1px line frame; the footer follows the page. Inside the frame, everything is rows of ruled cells. Cells share edges by sitting in a grid with a 1px gap over a line-coloured background, or by each cell ruling its own right and bottom edge, so the rules are always exactly 1px and never double.

The header row: the mark on the left (24px inset), the Waterline pill on the right (12px 24px around it); below 560px the pill takes its own full-width row. Section insets are 24px horizontally (16px on phones); cell padding sits between 14px and 24px. Small gaps step 6 / 8 / 12 / 16 / 24px; the ruler tick unit is 8px and the glass-bed grid 16px.

The review grid is auto-fill columns of at least 300px structure cells. Breakpoints observed: 560px (phone; the nav pill takes its own row), 600px (the About review grid is one column), 720px (phone insets), 860px (info pages stack), 1024px (the tool's minimum width: below it the tool shows a desktop-only note, the landing is one column, its drop ring says "Desktop screen needed", and the landing's sample pill moves above the ring), 1200px (the footer bubbles stop sticking and stack, centred; landing and workspace column changes) and 1280px (the acrostic steps from 72px to 60px). The landing's first screen fills the window above the footer (the name, the ring and the sample pill in view down to 1280 × 720 and 1024 × 768), and it is the whole page, with no second screen. Every page starts with a Skip to content link, out of sight until the keyboard reaches it. Only the landing and the info pages are built for phones.

## Elevation & Depth

The sheet is flat. Depth comes from tone (paper, white cells, sunken bands, the hatched failed ground) and from hairlines, not shadows. The page in the paper view lies flat with only a 1px hair underline. Shadows belong to the few objects that float above the sheet, all in one green-black ambient family (rgba(15, 30, 22, 0.35)): glass pills (the Waterline nav and its drop included), the footer's porcelain bubbles, toasts and menus, and dialogs (the structure editor, the COCONUT submission, Compare engines and Keys). Every value is a token in `tokens.css`; no stylesheet writes a shadow or scrim colour of its own (pinned in `styles.test.ts`).

### Shadow Vocabulary
- **Glass lift** (`--lift-glass`, `0 10px 24px -8px rgba(15, 30, 22, 0.35)`): glass pills (after `--glass-shine`); also toasts and the card's floating menus.
- **Glass shine** (`--glass-shine`): the pill's inner light: a top highlight, a soft white rim and a bottom shade (four insets).
- **Menu lift** (`--lift-menu`, `0 12px 28px -10px rgba(15, 30, 22, 0.35)`): workspace disclosures such as Export.
- **Dialog lift** (`--lift-dialog`, `0 24px 64px -24px rgba(15, 30, 22, 0.45)`): every dialog: the editor, COCONUT, Compare and Keys.
- **Scrim** (`--scrim`, `rgba(28, 33, 29, 0.42)`): the backdrop of every dialog. Dialogs are native `<dialog>` elements opened as modals, so the page behind is inert.
- **Solid pill fallback** (`--lift-pill-solid`, `0 6px 16px -8px rgba(15, 30, 22, 0.35)`): glass pills (and the Waterline nav) under reduced transparency or without backdrop-filter.
- **Water drop** (`--water-drop`): the Waterline nav's drop of green water: a top meniscus highlight, a soft white rim, a green bottom shade and a small 5px lift.
- **Porcelain** (`--porcelain`): the footer bubbles: a glazed white top edge, a faint ink rim and bottom shade, and a low lift (`0 8px 16px -10px rgba(15, 30, 22, 0.45)`). Opaque, unlike glass: page text scrolls underneath them.

### Named Rules
**The Flat Sheet Rule.** Nothing printed on the sheet casts a shadow. Only objects that act or float (pills, the footer bubbles, menus, toasts, dialogs) lift. The landing's drop ring is printed on the sheet: no glass, no lift.

**The Beams.** The landing alone carries a background: 14 soft sage beams (hue 132 to 158, 34% saturation, 7 to 14% alpha) rising slowly on a diagonal, drawn on a canvas at a third of its size and blurred 22px in CSS, fainter under the words (a mask). A fixed seed gives the same picture every visit; the loop stops off screen and in a hidden tab; one still frame under reduced motion; the pre-rendered page starts on plain paper. Text over it keeps AA (measured over 20 s of motion at 1440 × 900: the muted facts line at worst 4.75:1, the drop hint in text-2 8.0:1; "and" and "for" are large text).

**The Light Ground Rule.** Glass pills sit on light grounds only: paper, surface, sunken, or the glass bed. Never on charcoal or on a picture (the clear tint drops to 2.3:1 there).

## Shapes

Rectangles with square corners for everything that holds content: the frame, cells, structure cards, specimen tables, toasts, segmented controls. Small radii only on form controls (2px on selects and inputs, 3px on key caps). Round forms are reserved: the 999px pill for actions, the 50% circle for stamps, count dots and switch knobs. The drawing-sheet primitives repeat everywhere: the "+" corner mark, horizontal and vertical ruler ticks (1px every 8px, 7px deep), the 16px glass-bed grid behind button clusters, the 135deg hatch, and the 2px charcoal diagonal strike across a rejected structure.

## Components

### Buttons
Liquid glass on paper: tactile pills that are the only shiny thing on a matte sheet.
- **Shape:** full pill (999px), Geist Mono 500 uppercase, 13px at 12px 20px; small variant 12px at 8px 14px.
- **Orange glass:** gradient rgba(255,118,72,.95) to rgba(250,54,0,.9), on-orange text: the first action (Try a sample paper on the landing, Choose a file in the tool).
- **Green glass:** gradient rgba(46,110,74,.95) to rgba(30,77,51,.92), on-green text: commit actions (Accept, Send to COCONUT).
- **Clear glass:** white 70% to 25% gradient, ink text: everything else (Reject, Compare, More, Export, Copy).
- **Material:** backdrop-filter blur(3px) saturate(1.8) with the #marcus-glass SVG refraction where supported; inner top highlight and a soft bottom shade. Pills on a structure card and small pills in focus mode keep the blur only: on flat white or paper the refraction has nothing to bend.
- **Hover / Focus:** scale(1.03) over 160ms cubic-bezier(0.16, 1, 0.3, 1) when motion is allowed; 2px forest-green outline at 2px offset. Disabled is a flat hair pill with muted text.
- **Fallbacks:** solid orange, green, or white with a control-border ring under reduced transparency or without backdrop-filter; a ButtonBorder edge in forced colours.
- **Text links as buttons:** small Geist Mono 500 uppercase in green with an underline that appears on hover (Copy, Select all shown, Back to start).
- **Dialog Close:** always the small clear glass pill, in the dialog's head cell.

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

### Navigation (the Waterline)
- **Style:** one clear glass pill (white 70% to 25%, blur 3px, saturate 1.8, glass shine and glass lift; no refraction filter, no WebGL), 4px inside padding, three items in Geist Mono 500 12px / 16px uppercase ink (12px / 16px padding, 8px to the 14px icon), each with its Font Awesome icon in green: About (circle-info), GitHub (github; opens in a new tab and says so to screen readers), Open the tool (arrow-right after the label).
- **The drop:** the current page's item (aria-current="page"; none on the other pages) holds a drop of green water (a 14% to 30% green gradient with the water-drop shadow). Pointer or focus on another item slides it there by transform (500ms on the one curve; it takes the item's width at once), then a 600ms ripple settles it; it goes back to rest when pointer and focus leave. The pointer lifts a highlight on the rim. Its offset and width are custom properties set through the CSSOM (style-src 'self' allows it).
- **Keys:** Arrow Left / Right, Home and End move focus along the items; focus is the 2px green outline at 1px offset, round.
- **Fallbacks:** no slide, ripple or rim light under reduced motion (the drop jumps and only fades); solid white with a control-border ring under reduced transparency; ButtonBorder edge and a Highlight-outlined drop in forced colours.
- **Mobile:** below 560px the pill takes the full width under the mark.

### Footer (porcelain bubbles)
Every page but the review workspace: three opaque porcelain bubbles, Geist Mono 12px / 16px uppercase in text-2 with 14px green icons, 4px / 16px padding. Far left "© 2026 MARCUS" (copyright icon, "Copyright" for screen readers); middle "Built with [mug, gently rocking] by Kohulan.R at the Steinbeck Lab, Friedrich Schiller University Jena" (three links, new tab, no icons); far right "Disclaimer · Privacy" (scale-balanced, shield-halved). Each bubble is a white radial glaze (#FFFFFF to #EFEFE8) with the porcelain shadow and a soft highlight under the text. From 1200px the row sticks 12px above the window's bottom and follows the page in the flow, so at a page's end it rests under the content; below 1200px it is static and the bubbles stack, centred. Links are 24px tall targets (a 4px hit area above and below each 16px line). The review workspace keeps its thin mono line inside the page frame.

### Drop ring (landing)
The landing's drop zone is an empty benzene ring, 124px, drawn in control-border dashes on a white fill, with an upload arrow, "Drop a PDF here or browse" and "PDF up to 20 MB". One button (Enter, Space, click open the file picker). Hover and focus turn it green and grow its three double bonds into place (opacity and scale); drag-over turns it orange, grows it 6% and runs the dashes (the Reading mark); a checked PDF closes the ring in accepted green with alternating double bonds (resonance) and "Uploading <file name>…" while the tool opens and uploads it; a refused file ("That file is not a PDF", "That PDF is larger than 20 MB") is struck through in charcoal like a rejected structure. Below 1024px it shows a monitor glyph and "Desktop screen needed" and takes no file. All motion is off under reduced motion. The ring's running dashes are the landing's one linear loop (a constant speed); everything else moves on the one curve.

### Icons
Font Awesome Free 6.7.2 (CC BY 4.0, credited on the Disclaimer page), solid, regular and brands, imported by name and rendered by one Icon component as an inline `<svg viewBox><path>`: no icon font, no injected CSS. 1.05em, the text's colour (green in the nav and footer), always decorative beside a word.

### Specimen label
A data table drawn like a herbarium label: a charcoal header bar with on-charcoal mono caption, then rows on surface ruled by hair, mono uppercase row heads in muted, values in ink. A failed specimen lies on the hatched ground.

### Annotation (Paper view)
The local model's suggestion for a paper, above its text in the Paper view's middle column (the text below scrolls on its own, the annotation at most 45% of the column).
- **Start:** the small clear pill Annotate and one line in text-2 ("A model on this server suggests organism, place and compound names."); while it runs, "Annotating…" in the Reading shape (dashed orange edge), in the panel, in the status bar and in the tool home list. A failure says why in ink, with Try again.
- **Focus:** a run's start and end are said; the focus goes to the panel while it runs, then to Edit or Try again, and back to Annotate after a refused start. A focus the panel moves after a mouse click shows no ring until a key is pressed.
- **Values:** a specimen label: the charcoal head reads "Model suggestion" (or "Curated" once corrected) with the model's name in mono; one row per field that has values, the field's label as the mono row head after its family swatch. Each value found in the text is a square button on its family's tint with a 1px edge in the family's deep colour and its count in text-2 mono; the value whose occurrence the text shows fills with the family's deep colour (white text, aria-current). A value not in the text is no button: the same tint, a dashed edge and the count 0.
- **Field families:** the 11 fields are read in six colour families, grouped the way a curator checks them (what was studied, which part of it, where it came from, what the compounds are called, what kind of compounds, their systematic names). Eleven hues could not be told apart; six can, and the fields that share a family are ones a curator reads together. Each family is a tint (tokens `ann-*-tint`), a deep colour (`ann-*`) and an underline style, set once per family (`.pv-fam--*` in paper.css); marks, value chips and swatches only read them.

| Family | Fields | Tint / deep | Underline | Ink on tint | Text-2 on tint | White on deep | Deep on paper |
|---|---|---|---|---|---|---|---|
| Organism | Organism, Kingdom | #C8E4A4 / #2F6A1A (leaf green) | double | 11.8:1 | 7.2:1 | 6.6:1 | 5.9:1 |
| Organism part | Organism part | #F7E08C / #7A5600 (bark ochre) | solid | 12.5:1 | 7.6:1 | 6.7:1 | 6.0:1 |
| Place | Place, Habitat or host | #CFE3FA / #1D5DA6 (map blue) | solid | 12.5:1 | 7.6:1 | 6.6:1 | 6.0:1 |
| Compound names | Compound names, Abbreviations | #FBD7E5 / #A3305F (rose) | dotted | 12.4:1 | 7.6:1 | 6.7:1 | 6.0:1 |
| Compound class | Compound class, Compound series | #D2BEF2 / #6A3CA6 (violet) | dashed | 9.6:1 | 5.9:1 | 7.5:1 | 6.7:1 |
| Systematic names | IUPAC names, Semi-systematic names | #9FD6CB / #17675F (teal) | wavy | 10.1:1 | 6.2:1 | 6.7:1 | 6.0:1 |

  The deep colours are at least 4.1:1 on their own tint and 5.9:1 on paper and surface (underlines and edges need 3:1); every pair is pinned in styles.test.ts. Under simulated deuteranopia and protanopia (Machado 2009) three pairs come close in hue (organism and part, place and class, compound names and systematic names): each pair has different underline styles. Part and place share the solid line because ochre and blue stay apart in every common colour-vision deficiency. No tint is selection mint, and the clicked occurrence is a dark fill, so neither is mistaken for selected text. A field the client does not know takes the sunken ground with a text-2 line.
- **Marks:** every occurrence in the text is a `<mark>` on its family's tint, underlined 1.5px in the family's deep colour and line style; the occurrence a click went to is filled with the family's deep colour, white text, no underline. Colour is never alone: each mark names its field ("Organism") as a title for the pointer and an `aria-description` for screen readers (never hidden text inside the mark, which would be copied with the text), the list names every field, and a click says "value: 2 of 5, Organism". The mark itself is not focusable, so for keyboard and touch users the line style, the legend and that announcement carry the field. Where values of two fields cover the same text, the pieces stay flat (never nested): the clicked field leads, else the most specific (the shorter span; on a tie the first field), its colour, and the title names both ("Compound names, Abbreviations"). The clicked occurrence is always one mark, naming every field inside it. A click shows the first occurrence, the next click the next (around to the first), centred in the text. Marks are React text in `<mark>` elements with a family class, never HTML from the model and never a style attribute. In forced colours, marks are Mark and the clicked one Highlight; the line styles stay.
- **Legend:** before each field's name (in the list and in the correction form) a swatch, decorative (aria-hidden): a 22 × 11px block of the family's tint on a bottom border in its line style (2px; double 3px). Borders have no wavy, so the systematic family draws its wave as an underline under no-break spaces.
- **Chip hover:** the family edge thickens to 3px.
- **Corrections:** Edit opens one labelled box per field (one value a line), Save (green small pill) and Cancel; Escape cancels. Reset to model asks first.

### Progress bar
One bar for every wait in the tool (`ui/ProgressBar`, `.pb` in ui.css), never a spinner.
- **Measured:** a square track (1px control-border edge, 3.3:1 on paper; surface ground), 10px tall or 6px small, with a forest-green fill (about 10:1 on the track) and the percentage beside it: mono 12px (11px small), tabular figures so it does not jitter, text-2 (over 9:1 on paper), at least four characters wide. The figure is rounded down, so 100% means the work is done. The bar never moves back during a run (a run that starts again, a retried page, starts over).
- **Motion:** the fill is `transform: scaleX(var(--pb))` with a 500ms transition on the one curve (`--ease`); `--pb` is set through the CSSOM, never a style attribute. The printed figure counts up with the fill (requestAnimationFrame on the same curve and time), never down; a bar that appears starts on its figure. While the work goes on a slow sheen (a band of surface at 22% over the green, still 5:1 on the track) crosses the filled part every 2.4s, clipped to it; none once the work is done, and a failed or stopped run shows no bar.
- **Unmeasured:** an empty ruler (a tick every 8px in tick on surface) with a green segment, 30% of the track, sliding calmly across it every 2s (ease-in-out); no number.
- **Reduced motion:** no sheen, no slide, no easing: the fill and the figure jump, the percentage is still printed.
- **Screen readers:** `role="progressbar"` with a name, `aria-valuenow` (the figure) and `aria-valuetext` ("Reading structures, 10 of 15, 62%"); the printed figure is aria-hidden. Announcements belong to the caller and say a stage, never a count or a percent.
- **Estimates:** a figure no one measures is printed "~60%" and said "about 60%", until it is full.
- **Where:** the reading progress (below); Annotating (the panel and the status bar); Send to COCONUT ("Sent 50 of 60", 83%); Compare's Run all engines ("Running engines 1/3", engines read or failed of those it started, full for a moment, then gone). Unmeasured: uploading a file (fetch reports no upload progress), an image waiting or reading, an engine reading in Compare, Looking up in PubChem, Loading the text, Loading editor. Skeletons (a paper, an image or the list loading) stay skeletons; the review grid's Reading… badges stay badges.

### Reading progress
How far a paper's read has come, in the status bar both workspace views share and, compact, in the tool home's row of a busy paper. Beside the state badge (Reading… or Annotating…), never instead of it.
- **Bar:** the progress bar, full width, with its percentage.
- **Stages:** above the bar, one mono 12px uppercase line: Checking PDF → Reading pages 3/5 → Reading structures 10/15 → Reading the text → Finishing (Done once the paper is done). The text is read beside the pages and is ticked as soon as it is. Done stages in text-2 with a green Font Awesome check, the current one in ink at 500 with its count (`aria-current="step"`), the rest muted; the arrows are CSS content with empty alt text. A paper read without structures has no structures stage.
- **Figure:** checking 5%, pages 35%, structures 35%, the text 20% (its step ended), the last 5% when the paper is done (70% for pages when there are no structures). Failed pages and structures count as handled. Structures are measured against those the unread pages can be expected to hold, and the shown figure is the highest so far in the run (a retried page starts a new run), so the bar never moves back.
- **Nothing to measure yet:** before the PDF check counts the pages the bar is unmeasured. Before the read starts the line reads the queue estimate ("About 3 min in the queue", or Waiting); after that the estimate stands in muted mono beside the stages while it is a minute or more (the waits are in the segmentation and OCSR queues).
- **Annotating:** the model reports no progress, so an annotate run shows an estimate from the time since this page saw it start: an ease-out to 90% over the typical run (`ANNOTATE_TYPICAL_MS`, 6 s, an estimate), then a slow creep toward 95%, never past it. When the run ends the bar fills to 100% and stays a moment (600ms) before it goes; in the annotation panel the values show after that moment. A failed run shows its failure at once, never a full bar. The tool home's row shows the estimate too.
- **When:** while the paper is busy; a paper read while it is open ends on a full bar with every stage ticked; a paper opened done shows only its badge, and so does a done paper busy only reading structures again with another engine. A failed paper or a PDF that could not be read shows no bar: its failure lines say why, as before.
- **Screen readers:** the bar is named "Reading progress" and speaks "Reading structures, 10 of 15, 62%". A visually hidden polite status says the stage name when the stage changes, never a count or a percent.
- **Compact (tool home):** under the row's counts, at most 360px: a 6px bar with its percentage and one 11px mono line ("Reading pages 2/4", "Waiting"; none while annotating, the badge says it), no announcement. The row's counts come with the list (PaperSummary pages_read, structures_read, …; polled every 5 s while a paper is busy), so a row asks for no steps; an annotate run ends on its full bar for a moment, as in the status bar.

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
- **Do** keep every size, tint and rotation in a stylesheet class: no inline style attributes in pre-rendered components and no innerHTML (strict CSP). Positions that move at run time (the nav's drop, an open menu) go through the CSSOM (style.setProperty).
- **Do** open menus (a card's More and engine menus, Export) in the top layer next to their button (a manual popover placed by `ui/anchor`): on the preferred side when it fits, else flipped, shifted to stay 8px inside the window, capped in height with its own scroll, following its button on scroll and closing once the button scrolls out of its column. No scrolling column or sticky caption may cut a menu off. In the Paper view, whatever a click scrolls into a column (a card, a marker with its tag) lands below the column's sticky caption.
- **Do** draw icons with the Icon component (Font Awesome Free, named imports), next to their word.
- **Do** use the one easing, cubic-bezier(0.16, 1, 0.3, 1), at 160 to 220ms, and drop motion under prefers-reduced-motion.

### Don't:
- **Don't** add a dark mode; the system is light only.
- **Don't** use orange for anything that does not need a person's attention.
- **Don't** put accepted-green text on sunken.
- **Don't** draw a control edge in line or hair.
- **Don't** put glass pills on charcoal or over a picture.
- **Don't** cast shadows from things printed on the sheet: cells, cards, tables, the drop ring.
- **Don't** load a weight outside Geist 400/700 and Geist Mono 400/500, or use Gmarket Sans for anything but the wordmark.
- **Don't** round content containers; radius is for pills (the nav, the footer bubbles), stamps, dots and small control corners.
- **Don't** put a box or rule around the header row; the frame belongs to the page.
