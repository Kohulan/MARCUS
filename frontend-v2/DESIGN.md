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
  display-acrostic:
    fontFamily: "Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "clamp(34px, min(5.3vw, 8.8vh), 84px)"
    fontWeight: 400
    lineHeight: 0.96
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
    padding: "10px 18px"
  footer-bubble:
    textColor: "{colors.text-2}"
    rounded: "{rounded.pill}"
    padding: "3px 14px"
    height: "30px"
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
- **Display acrostic** (the landing's h1 only; an owner-approved exception to Display = 700): the name spelled out, one word a line, uppercase, clamp(34px, min(5.3vw, 8.8vh), 84px), line-height 0.96. The initials M A R C U S are Geist 700 in forest green, the rest of each word Geist 400 in ink, "and" and "for" in muted. Screen readers get the plain name from a visually hidden copy; the drawn letters are aria-hidden.
- **Headline** (Geist 700, 30px, line-height 1, -0.02em, uppercase): section and card headings; 26px under 900px.
- **Title** (Geist 700, 22px, line-height 1.2): names of things, such as a paper's file name or "Example paper"; sentence case and file case kept.
- **Body** (Geist 400, 16px, line-height 1.6): prose, lead text capped at about 40ch.
- **Body small** (Geist 400, 14px, line-height 1.5, text-2): card lines and notes, capped at about 42ch.
- **Label** (Geist Mono 400, 11px, 0.05 to 0.08em, uppercase, muted): captions, readouts, specimen row heads, state words, footer.
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

The header row: the mark on the left (24px inset), the Waterline pill on the right (10px 24px around it); below 560px the pill takes its own full-width row. Section insets are 24px horizontally (16px on phones); cell padding sits between 14px and 24px. Small gaps step 6 / 8 / 12 / 16 / 24px; the ruler tick unit is 8px and the glass-bed grid 16px.

The review grid is auto-fill columns of at least 300px structure cells. Breakpoints observed: 560px (phone; the nav pill takes its own row), 600px (the About review grid is one column), 720px (phone insets), 860px (info pages stack), 1024px (the tool's minimum width: below it the tool shows a desktop-only note, the landing is one column, its drop ring says "Desktop screen needed", and the footer bubbles stop sticking and stack, centred), 1200px and 1280px (landing and workspace column changes). The landing is one screen: at 1440 × 900 and 1280 × 720 it does not scroll. Only the landing and the info pages are built for phones.

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
- **Style:** one clear glass pill (white 70% to 25%, blur 3px, saturate 1.8, glass shine and glass lift; no refraction filter, no WebGL), 4px inside padding, three items in Geist Mono 500 12px uppercase ink, each with its Font Awesome icon in green: About (circle-info), GitHub (github; opens in a new tab and says so to screen readers), Open the tool (arrow-right after the label).
- **The drop:** the current page's item (aria-current="page"; none on the other pages) holds a drop of green water (a 14% to 30% green gradient with the water-drop shadow). Pointer or focus on another item stretches it there: the leading edge runs ahead in 240ms, the trailing edge follows in 440ms, then it settles with a squash and a 620ms ripple; it goes back to rest when pointer and focus leave. The pointer lifts a highlight on the rim. Positions are custom properties set through the CSSOM (style-src 'self' allows it).
- **Keys:** Arrow Left / Right, Home and End move focus along the items; focus is the 2px green outline at 1px offset, round.
- **Fallbacks:** no stretch, ripple or rim light under reduced motion (the drop jumps); solid white with a control-border ring under reduced transparency; ButtonBorder edge and a Highlight-outlined drop in forced colours.
- **Mobile:** below 560px the pill takes the full width under the mark.

### Footer (porcelain bubbles)
Every page but the review workspace: three opaque porcelain bubbles, Geist Mono 10px uppercase in text-2 with green icons. Far left "© 2026 MARCUS" (copyright icon, "Copyright" for screen readers); middle "Built with [mug, gently rocking] by Kohulan.R at the Steinbeck Lab, Friedrich Schiller University Jena" (three links, new tab, no icons); far right "Disclaimer · Privacy" (scale-balanced, shield-halved). Each bubble is a white radial glaze (#FFFFFF to #EFEFE8) with the porcelain shadow and a soft highlight under the text. From 1024px the row sticks 12px above the window's bottom and follows the page in the flow, so at a page's end it rests under the content; below 1024px it is static and the bubbles stack, centred. Links are 24px tall targets. The review workspace keeps its thin mono line inside the page frame.

### Drop ring (landing)
The landing's drop zone is an empty benzene ring, 124px, drawn in control-border dashes on a white fill, with an upload arrow, "Drop a PDF here or browse" and "PDF up to 20 MB". One button (Enter, Space, click open the file picker). Hover and focus turn it green and draw its three double bonds; drag-over turns it orange, grows it 6% and runs the dashes (the Reading mark); a checked PDF closes the ring in accepted green with alternating double bonds (resonance) and "Uploading <file name>…" while the tool opens and uploads it; a refused file ("That file is not a PDF", "That PDF is larger than 20 MB") is struck through in charcoal like a rejected structure. Below 1024px it shows a monitor glyph and "Desktop screen needed" and takes no file. All motion is off under reduced motion.

### Icons
Font Awesome Free 6.7.2 (CC BY 4.0, credited on the Disclaimer page), solid, regular and brands, imported by name and rendered by one Icon component as an inline `<svg viewBox><path>`: no icon font, no injected CSS. 1.05em, the text's colour (green in the nav and footer), always decorative beside a word.

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
- **Do** keep every size, tint and rotation in a stylesheet class: no inline style attributes in pre-rendered components and no innerHTML (strict CSP). Positions that move at run time (the nav's drop) go through the CSSOM (style.setProperty).
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
