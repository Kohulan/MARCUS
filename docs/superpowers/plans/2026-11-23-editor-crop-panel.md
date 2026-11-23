# Edit structure: crop panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The "Edit structure" dialog shows the crop beside Ketcher, a "Use coordinates" toggle, and "Find on paper" / "Back" to see the structure's place on its page.

**Architecture:** Extend the existing `Editor` modal (frontend-v2/src/workspace/Editor.tsx) with an optional left panel described by a new `source` prop; the two callers (SegmentEditor, ImageResult) pass it. The toggle only changes what the existing `marcus:load` message carries. No backend change.

**Tech Stack:** React + TypeScript, vitest + Testing Library, Playwright @mocked.

**Spec:** docs/superpowers/specs/2026-11-23-editor-crop-panel-design.md

## Global Constraints
- UI copy exactly: "Use coordinates", "Find on paper", "Back". No other new visible text except the image alt texts below.
- Toggle on at every opening; no saved setting (no localStorage, no API).
- Toggle enabled only when `initial.molfile` is non-empty and `imageLayout(initial.molfile)` is true (frontend-v2/src/api/engines.ts). Disabled: Ketcher gets `initial` unchanged (today's behaviour).
- Enabled + on: Ketcher gets `{smiles, molfile}`; enabled + off: `{smiles, molfile: null}`.
- Switching the toggle re-posts `marcus:load` with the starting structure (unsaved drawing lost). Never post before `marcus:ready`.
- No change to the bridge message format (editorBridge.ts), saving, statuses, or the curation API.
- Commits: author only, no trailers, no Claude attribution. `git add` named files only (hook forbids `git add -A`). Never push.

## Review Focus
1. Crop image fails to load (expired paper, 404): the panel shows the alt text; Ketcher and saving still work. Test in Task 2.
2. Page image is 300 DPI (about 2480 × 3508 px): it scales to the panel width and the box stays on the structure (percent box via `boxStyle`, natural size from the image's `load`). Test in Task 2.
3. Toggle pressed before Ketcher is ready: no `marcus:load` is posted early; the first load after `marcus:ready` uses the toggle's current state. Test in Task 1.
4. Focus after "Find on paper" goes to "Back", and after "Back" to "Find on paper"; Escape still closes the dialog from either view. Test in Task 2.
5. Narrow screen (< 720 px wide): the panels stack (source above Ketcher), no horizontal page scroll. Checked in Task 3's Playwright run at 390 px.

---

### Task 1: Use coordinates toggle

**Files:**
- Modify: `frontend-v2/src/workspace/Editor.tsx`
- Modify: `frontend-v2/src/workspace/editor.css`
- Test: `frontend-v2/src/workspace/Editor.test.tsx`

**Interfaces:**
- Produces: `export function editorLoad(initial: {smiles: string|null; molfile: string|null}, coords: boolean): {smiles: string|null; molfile: string|null}` and `export function hasImagePositions(initial: {molfile: string|null}): boolean` in Editor.tsx.

- [ ] **Step 1: Write the failing tests** (in Editor.test.tsx; build an image-layout molfile and a computed-layout molfile as engines.test.ts already does for `imageLayout`, reuse its fixtures if exported)
  - `hasImagePositions({molfile: null})` is false; computed-layout molfile false; image-layout molfile true.
  - `editorLoad(start, true)` returns `start`; `editorLoad(start, false)` returns `{smiles: start.smiles, molfile: null}` when `hasImagePositions(start)`, else returns `start` unchanged.
  - Dialog with an image-layout molfile: checkbox labelled "Use coordinates" is checked and enabled; after `marcus:ready` the frame got `{molfile}`; unchecking posts a second `marcus:load` with `molfile: null`; checking again posts the molfile.
  - Dialog without image positions: the checkbox is disabled; the frame gets `initial` as today.
  - Unchecking before `marcus:ready` posts nothing; the load sent on `marcus:ready` has `molfile: null`.
- [ ] **Step 2: Run** `cd frontend-v2 && npx vitest run src/workspace/Editor.test.tsx` — the new tests FAIL.
- [ ] **Step 3: Implement** both functions and a `coords` state (default true) in `Editor`; the `marcus:ready` handler and the toggle's change handler post `editorLoad(initial, coords)` (read `coords` through the existing `latest` ref so the listener is still added once). The toggle sits in a row between the SMILES form and the frame, styled like Compare's toggle.
- [ ] **Step 4: Run** the same command — all Editor tests PASS.
- [ ] **Step 5: Commit** `git add frontend-v2/src/workspace/Editor.tsx frontend-v2/src/workspace/editor.css frontend-v2/src/workspace/Editor.test.tsx && git commit -m "feat(editor): Use coordinates toggle"`

### Task 2: Source panel with Find on paper

**Files:**
- Create: `frontend-v2/src/workspace/EditorSource.tsx`
- Modify: `frontend-v2/src/workspace/Editor.tsx`, `frontend-v2/src/workspace/editor.css`
- Test: `frontend-v2/src/workspace/EditorSource.test.tsx`

**Interfaces:**
- Consumes: `boxStyle(bbox, w, h)` from `./pageBox`.
- Produces: `export type EditorSourceInfo = { image: string; page: { url: string; bbox: [number, number, number, number]; page0: number } | null }`; `export function EditorSource({ source }: { source: EditorSourceInfo }): JSX.Element`; `Editor` gets an optional prop `source?: EditorSourceInfo` (absent: the dialog looks as today).

- [ ] **Step 1: Write the failing tests** (EditorSource.test.tsx)
  - Renders `<img>` with `src = source.image` and alt "Crop the engines read"; a button "Find on paper".
  - `page: null`: no "Find on paper" button.
  - Click "Find on paper": the crop is gone, an `<img>` with `src = page.url` and alt `Page ${page0 + 1}` shows, a "Back" button has focus; after firing `load` on the page image with `naturalWidth` 2480 / `naturalHeight` 3508 (define them on the element), the marker element carries `boxStyle(bbox, 2480, 3508)` CSS variables.
  - Click "Back": the crop shows again and "Find on paper" has focus.
  - Crop `error` event: the alt text stays visible (no broken layout element removed), the button still works.
  - In Editor.test.tsx: with `source`, Escape from the page view still calls onClose; without `source`, no `img` is rendered (today's dialog).
- [ ] **Step 2: Run** `cd frontend-v2 && npx vitest run src/workspace/EditorSource.test.tsx src/workspace/Editor.test.tsx` — the new tests FAIL.
- [ ] **Step 3: Implement** `EditorSource` (state `view: "crop" | "page"`, page natural size from `onLoad`, marker uses the paper view's marker class or a local one fed by `boxStyle`; image `object-fit: contain`, max height the panel). In `Editor`, when `source` is given, wrap the existing content in a two-column grid: `EditorSource` left, today's SMILES form + toggle + frame right; widen the modal (class `editor--split`). Stack the columns below 720 px.
- [ ] **Step 4: Run** the same command — PASS.
- [ ] **Step 5: Commit** `git add` the four files, `git commit -m "feat(editor): crop panel with Find on paper"`

### Task 3: Wire the callers and gate

**Files:**
- Modify: `frontend-v2/src/workspace/SegmentEditor.tsx`, `frontend-v2/src/images/ImageResult.tsx`
- Modify: `frontend-v2/e2e/editor.spec.ts`

**Interfaces:**
- Consumes: `Editor`'s `source` prop and `EditorSourceInfo` (Task 2); `api.segmentImageUrl(id)`, `api.pageImageUrl(paperId, page0)`, `api.imageUrl(id)` from `src/api/client.ts`.

- [ ] **Step 1: Write the failing e2e check** in e2e/editor.spec.ts (@mocked, same fixtures as the existing editor test): open the editor on a structure; expect the crop image, "Use coordinates", "Find on paper"; click it, expect the page image and "Back"; click "Back", expect the crop. At viewport 390 × 844, expect `document.documentElement.scrollWidth <= 390`.
- [ ] **Step 2: Implement**: SegmentEditor passes `source={{ image: api.segmentImageUrl(segment.id), page: { url: api.pageImageUrl(paperId, segment.page), bbox: segment.bbox, page0: segment.page } }}`; ImageResult passes `source={{ image: api.imageUrl(job.id), page: null }}` (use the job id variable already in scope there).
- [ ] **Step 3: Gate** (all must pass):
  - `cd frontend-v2 && npx vitest run` — all pass (baseline 1015 + new).
  - `npm run typecheck && npm run lint` — clean.
  - `npm run build && npm run serve:local` (serves this worktree's dist on marcus-ui-dev), then `npx playwright test --grep @mocked` — all pass (baseline 50 + new).
- [ ] **Step 4: Commit** `git add` the three files, `git commit -m "feat(editor): show the crop and its page in the editor"`
