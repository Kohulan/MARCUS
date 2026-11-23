# Edit structure: crop panel, Use coordinates, Find on paper (design)

Owner request 2026-11-23, approved the same day.

## Why
A curator who fixes a structure in Ketcher must see what the paper shows. Today the editor
dialog has only the SMILES field and Ketcher; the curator must remember the crop.

## Goals
- The editor dialog shows the crop the engines read on the left, and the SMILES field and
  Ketcher on the right.
- A "Use coordinates" toggle above Ketcher (on at every opening, this dialog only, no saved
  setting). On: Ketcher opens the structure in the positions its engine read from the image.
- A "Find on paper" button below the crop. It replaces the crop with the paper page, only
  this structure's box marked, and a "Back" button that returns to the crop. Same dialog;
  Ketcher stays open and keeps the drawing.

## Non-goals
- No change to saving, decisions, statuses or the curation API.
- No borrowed positions: a structure without its own image positions (DECIMER, a curated
  SMILES without molfile) is never laid out on another engine's template (owner choice).
- No new backend endpoint.

## Decided
- Toggle applies only when the structure the editor opens has its own image positions: a
  molfile that passes `imageLayout` (frontend api/engines.ts; the test inside Compare's
  `usableTemplate`).
  Otherwise the toggle is shown disabled and Ketcher gets what it gets today (the molfile when
  there is one, e.g. a curated Ketcher drawing; else the SMILES).
- Toggle on: Ketcher gets the molfile (as today). Off: Ketcher gets the SMILES only (Ketcher
  lays it out). Switching the toggle loads the starting structure again; unsaved drawing
  changes are lost (builder's call, accepted with the design).
- Uploaded single image (images/ImageResult.tsx): the left side shows the uploaded image;
  no "Find on paper".
- Page view: the page image (api.pageImageUrl) with one marker for this segment's bbox, in
  the same box style as the paper view (workspace/pageBox.ts). Fits the left panel; no zoom.
- Minimal UI copy (owner rule): "Use coordinates", "Find on paper", "Back".

## Approaches
1. Extend the existing Editor modal with an optional left panel (chosen): one dialog, the
   callers pass what the left side shows. Reuses the crop URL, page URL and box style.
2. A new full-screen editor page: more room, but a second editor to keep in step and a route
   change that loses the workspace context.
3. Show the crop inside Ketcher as a background image: Ketcher's API does not support it well,
   and the page view would not fit.

## Left to the builder
- Exact widths and the narrow-screen layout (stack the panels below a breakpoint).
- Keyboard and focus order (crop panel buttons before the SMILES field is fine).
- Tests: vitest for the toggle rule and the panel switch; one Playwright @mocked check.
