# MARCUS frontend v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new React web UI for MARCUS v2 (landing page plus curation tool) in the "Field Sheet" look, with the small backend changes it needs.

**Architecture:** Group F0 adds eight small, tested changes to `backend-v2` (counts, title, bulk curation, depictions, asset rate limits, image job routes, export fields, page retry). Group F builds `frontend-v2/`: one Vite + React + TypeScript app. The landing, about, privacy and disclaimer pages are pre-rendered to HTML. The tool under `/app` is a client app on TanStack Query and SSE. The v2 nginx serves the build on the same origin as `/api/v2`. Ketcher runs in an isolated same-origin iframe at `/ketcher/`.

**Tech Stack:** Backend: Python 3.11, FastAPI, SQLAlchemy, Alembic, Celery, pytest (`uv run pytest`). Frontend: Node 22, npm, Vite, React 18, TypeScript strict, React Router 6, TanStack Query 5, Vitest + Testing Library, Playwright + `@axe-core/playwright`, `@fontsource` font packages, `ketcher-react` + `ketcher-standalone`.

**Spec:** `docs/superpowers/specs/2026-11-17-marcus-frontend-v2-design.md` (approved 2026-11-17). Backend API: `docs/superpowers/specs/2026-11-16-marcus-v2-backend-design.md` §9. Visual reference: `frontend-v2/reference/field-sheet-board.html` and `.png`. Product context: `frontend-v2/PRODUCT.md`.

## Global Constraints

- Commits: author Kohulan Rajan only. No `Co-Authored-By`, no `Claude-Session`, no "Generated with" lines. Never push. Never touch `main`. Branch: `v2-backend` (F0) and the same branch for F (the frontend folder is new).
- Never point any test, judge or script at production (jarvis ports 8080, 9000, or `marcus-backend`/`marcus-frontend` containers). Do not touch the `marcus-maintenance` container.
- Never print `.env` secret values.
- F0 tasks follow the backend plan's rules: every new route is owner-checked with `current_owner` and returns the one shared 404 (`not_found()` from `marcus.api.deps`) for missing, deleted and other owners' items; no raw error text leaves the API.
- Upload limit text in the UI: "max 20 MB". PDF or one image.
- Engines shown to users: DECIMER (default), DECIMER hand-drawn, MolNexTR, MolScribe. Wire values: `decimer`, `decimer-hand`, `molnextr`, `molscribe`. `fake` is never shown.
- `ocsr` mode values: `auto` (default) and `off`.
- Minimum tool width 1024 px. Below that the tool shows exactly: "MARCUS is made for a desktop screen". The landing works at phone width.
- No `dangerouslySetInnerHTML`, `innerHTML`, `outerHTML` or `insertAdjacentHTML` anywhere with server or user data. SVG depictions are shown with `<img src>`, never inlined. An ESLint rule (`react/no-danger`: error) enforces it.
- CSP of the app (exact): `default-src 'self'; script-src 'self' https://matomo.nfdi4chem.de; connect-src 'self' https://coconut.naturalproducts.net https://pubchem.ncbi.nlm.nih.gov https://matomo.nfdi4chem.de; img-src 'self' data: blob: https://matomo.nfdi4chem.de; style-src 'self'; font-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`. No inline scripts. No inline `<style>` blocks (React `style={}` props are allowed: they are not covered by `style-src` for elements set through the CSSOM).
- CSP of `/ketcher/` only (exact): the app CSP plus `script-src 'self' 'wasm-unsafe-eval'`, `worker-src 'self' blob:`, `style-src 'self' 'unsafe-inline'`, and `frame-ancestors 'self'`.
- Fonts are self-hosted (no Google Fonts at run time): Bricolage Grotesque (headings), Hanken Grotesk (text), JetBrains Mono (SMILES, keys), Gmarket Sans Light (wordmark only, file `maintenance/site/maintenance/GmarketSansLight.otf`).
- Colour tokens, light (exact): paper `#FAFAF7`, surface `#FFFFFF`, sunken `#F4F6F2`, ink `#15241B`, text-2 `#3E5044`, muted `#55675A`, line `#DCE3DA`, green `#1E4D33`, accepted `#2D7A46`, to-check `#9A5B0C`, rejected `#B23A2A`, failed-bg `#F7EEEB`, failed-ink `#7A3B30`. Dark values are the builder's call in the same world, each pair checked for WCAG AA (4.5:1 text, 3:1 UI).
- State words (exact, used everywhere): "Accepted", "Rejected", "To check", "Failed". A state always shows its word and its shape (stamp or badge), never colour alone.
- Keys in focus mode (exact): A accept, R reject, E edit, C compare, ← previous, → next, Esc back to grid, ? key list.
- Matomo: tracker `https://matomo.nfdi4chem.de/`, site id `7`, loaded from a file `/matomo.js`, not inline.
- Citation text (exact): "Rajan K., Weißenborn V., Lederer L., Zielesny A., Steinbeck C. MARCUS: molecular annotation and recognition for curating unravelled structures. Digital Discovery 2025, 4(11), 3137–3148. https://doi.org/10.1039/d5dd00313j"
- Sample paper: `backend-v2/tests/fixtures/pdfs/synth_015.pdf`, copied to `frontend-v2/public/sample/synth_015.pdf`; the "Try a sample paper" button fetches it and uploads it through `POST /api/v2/papers` like any PDF.
- Design contract: the HTML comment in spec §7 ("Contract"), word for word, is the first child of `<body>` in `frontend-v2/index.html` and survives `npm run build` (a test greps `dist/index.html` for `6b4eb402`).
- Copy: plain English, product words as in v1: segment, structure, engine, SMILES, molfile, page, paper.

## Review Focus

1. **A paper still running when the curator opens it.** Cards must appear as steps finish, without a reload, and a card whose OCSR step has not finished shows "Reading…" not "no structure". Test in F7 (SSE event adds a card) and F6 (polling fallback when the event stream fails).
2. **A page or engine that failed.** It must show as a failed page with its reason and a retry, never as an empty paper. Test in F6 (failed `segment_page` step renders "Page 5 could not be read" with the reason text from `error_class`), and in F0-1 (`failed_pages` counts it).
3. **Hostile text from the PDF.** Extracted text, display names, notes and SMILES containing `<img src=x onerror=…>` must render as text. Test in F9 (text column) and F15 (judge `test_stored_xss_frontend` passes).
4. **A big paper (200 structures).** The grid must load without 429s and stay usable. Test in F0-5 (400 asset GETs pass, the 301st plain GET is limited) and F15 (e2e loads a 200-segment seeded paper with no 429).
5. **Expired or deleted paper, or another browser's paper link.** The UI must show one plain "This paper is not here any more" page, never a crash or a spinner. Test in F6 (API 404 → that page).

---

## Group F0 — backend support (`backend-v2/`)

Run all F0 tests with `cd backend-v2 && uv run pytest <path> -q`. Use the seeding helpers in `tests/api/conftest.py` (`new_owner`, `make_client`, `ocsr_result`, `SEGS`, and the planner-driven seeding there). Each F0 task ends with the full API suite green: `uv run pytest tests/api -q`.

### Task F0-1: Paper counts on summaries

**Files:**
- Modify: `backend-v2/src/marcus/api/schemas.py` (`PaperSummary`)
- Modify: `backend-v2/src/marcus/api/read.py` (where summaries are built; add one grouped query per list, no N+1)
- Modify: `backend-v2/src/marcus/api/routes/papers.py` (`list_papers`, `get_paper`)
- Test: `backend-v2/tests/api/test_papers_read.py`

**Interfaces:**
- Produces: `PaperSummary` gains `structures: int`, `accepted: int`, `rejected: int`, `to_review: int`, `failed_pages: int`. `structures` = segments of the paper; `accepted`/`rejected` = curations with that status; `to_review = structures - accepted - rejected`; `failed_pages` = distinct pages with a `render_page` or `segment_page` step in status `failed` and no later `done` step of the same kind for that page.

- [ ] **Step 1: Write the failing tests**

```python
async def test_list_papers_has_counts(...):
    # seed: 1 paper, 3 segments; curation accepted on 1, rejected on 1; page 2 segment_page failed
    body = (await client.get("/api/v2/papers")).json()["papers"][0]
    assert (body["structures"], body["accepted"], body["rejected"], body["to_review"], body["failed_pages"]) == (3, 1, 1, 1, 1)

async def test_failed_page_retried_ok_is_not_counted(...):
    # page 2 segment_page failed, then a later segment_page step for page 2 is done
    assert body["failed_pages"] == 0

async def test_list_papers_query_count_does_not_grow_with_papers(...):
    # 1 paper vs 5 papers: same number of SQL statements (count with a SQLAlchemy event listener)
```

- [ ] **Step 2: Run them, expect FAIL** (`KeyError: 'structures'`)
- [ ] **Step 3: Implement** the grouped counts and the five fields; `PaperDetail` inherits them.
- [ ] **Step 4: Run `uv run pytest tests/api -q`, expect PASS**
- [ ] **Step 5: Commit** `feat(v2): paper summaries carry structure and failure counts`

### Task F0-2: Paper title from the DOI step

**Files:**
- Create: `backend-v2/alembic/versions/0005_paper_title.py` (`papers.title TEXT NULL`)
- Modify: `backend-v2/src/marcus/core/models.py` (`Paper.title`)
- Modify: `backend-v2/src/marcus/workers/cpu.py` (`doi` handler)
- Modify: `backend-v2/src/marcus/core/pipeline.py` (`_check_doi_result`, `_after_doi`)
- Modify: `backend-v2/src/marcus/api/schemas.py` (`PaperSummary.title: str | None`)
- Test: `backend-v2/tests/workers/test_cpu.py`, `backend-v2/tests/core/test_pipeline.py`, `backend-v2/tests/core/test_migrations.py`

**Interfaces:**
- Produces: `fetch_title(doi: str, timeout_s: float) -> str | None` in `marcus/workers/cpu.py`: Crossref `https://api.crossref.org/works/{doi}` (`message.title[0]`), then DataCite `https://api.datacite.org/dois/{doi}` (`data.attributes.titles[0].title`); `httpx` with `timeout_s`; any error → `None`; result stripped of tags and whitespace runs, cut to `TITLE_MAX_CHARS = 500`. The DOI step result becomes `{"doi": str|None, "title": str|None}`; the title call shares the existing `DOI_TOTAL_S = 12` budget (skip it when less than 1 s is left).
- `_check_doi_result` accepts a missing `title` (old results) and rejects a non-string, non-null one.

- [ ] **Step 1: Write the failing tests:** `test_fetch_title_crossref_then_datacite` (respx mocks: Crossref 404, DataCite 200 → DataCite title), `test_fetch_title_strips_markup_and_cuts` (`"<i>Coffea</i>  alkaloids"` → `"Coffea alkaloids"`; 600 chars → 500), `test_fetch_title_error_is_none`, `test_after_doi_stores_title`, `test_check_doi_result_rejects_non_string_title`, `test_migration_0005_up_down`.
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement** as in Interfaces. The worker stays the only code with internet access; the API never calls Crossref or DataCite.
- [ ] **Step 4: Run `uv run pytest tests/workers/test_cpu.py tests/core -q` and `tests/api -q`, expect PASS**
- [ ] **Step 5: Commit** `feat(v2): doi step stores the paper title`

### Task F0-3: Bulk curation

**Files:**
- Modify: `backend-v2/src/marcus/api/routes/papers.py` (new route), `backend-v2/src/marcus/api/schemas.py`
- Test: `backend-v2/tests/api/test_bulk_curation.py`

**Interfaces:**
- Produces: `PUT /api/v2/papers/{paper_id}/curation`, body `BulkCurationIn{items: list[BulkCurationItem]}` with `BulkCurationItem{segment_id: UUID, status: CurationStatus, note: str | None (max MAX_NOTE_CHARS)}`; `1 <= len(items) <= 500` (else 422). One transaction. Every `segment_id` must belong to this paper, else 404 for the whole call and nothing changes. Keeps an existing curated `smiles`/`molfile` (only status and note change). Returns `BulkCurationOut{updated: int}`. Rate limit: only the plain IP bucket, the same as `PUT /segments/{id}/curation`.

- [ ] **Step 1: Write the failing tests:** `test_bulk_accept_three`, `test_bulk_keeps_curated_smiles`, `test_bulk_foreign_segment_404_and_nothing_changed`, `test_bulk_other_owner_paper_404`, `test_bulk_501_items_422`, `test_bulk_empty_422`.
- [ ] **Step 2: Run, expect FAIL** (405)
- [ ] **Step 3: Implement** with one `SELECT … FOR UPDATE` of the paper's segments, then upserts.
- [ ] **Step 4: Run `uv run pytest tests/api -q`, expect PASS**
- [ ] **Step 5: Commit** `feat(v2): bulk curation for one paper`

### Task F0-4: Stored depictions per structure

Ruling (refines spec §9.1): the GPU OCSR images have no Java, and the CDK drawing lives only in the tools image. So the depiction is drawn lazily, on the first request, by the existing `marcus.tools.depict` task on `q.tools`, and stored on disk keyed by the SMILES. Later requests read the file. Same drawing as `/tools/depict`, drawn once per distinct SMILES, not 200 tool calls per page view.

**Files:**
- Modify: `backend-v2/src/marcus/core/storage.py` (`depiction_path`)
- Modify: `backend-v2/src/marcus/api/routes/segments.py` (new route)
- Modify: `backend-v2/src/marcus/workers/retention.py` (purge old depictions)
- Test: `backend-v2/tests/api/test_depiction.py`, `backend-v2/tests/workers/test_retention.py`, `backend-v2/tests/core/test_storage.py`

**Interfaces:**
- Produces: `depiction_path(smiles_sha256: str) -> Path` = `<data root>/depictions/<sha[:2]>/<sha>.svg`; rejects anything but 64 lowercase hex chars.
- Produces: `GET /api/v2/segments/{segment_id}/depiction?engine=<Engine>`: the newest valid prediction of that engine for the segment. With `engine` omitted it draws the structure that export would choose (curated SMILES, else the paper engine's newest valid prediction, else any valid one; reuse `export.choose`). 404 when there is none. Response `image/svg+xml`, headers `Cache-Control: private, max-age=86400`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'`. On a miss it calls `run_tool("marcus.tools.depict", {...same kwargs as POST /tools/depict with defaults...}, WAIT_S)` in a thread, writes the file atomically (tmp + `os.replace`), and returns it. It does not count against the per-owner `tools` bucket. A tool failure returns 503 with `Retry-After: 5` and writes nothing.
- Retention: files under `depictions/` with mtime older than 30 days are deleted by the daily purge.

- [ ] **Step 1: Write the failing tests:** `test_depiction_miss_draws_once_then_reads_file` (monkeypatch `run_tool`, call twice, assert one call and same bytes), `test_depiction_two_segments_same_smiles_one_draw`, `test_depiction_curated_smiles_used_without_engine`, `test_depiction_no_valid_prediction_404`, `test_depiction_other_owner_404`, `test_depiction_headers`, `test_depiction_tool_failure_503_no_file`, `test_depiction_path_rejects_bad_sha`, `test_retention_purges_old_depictions`.
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Run `uv run pytest tests/api tests/workers/test_retention.py tests/core/test_storage.py -q`, expect PASS**
- [ ] **Step 5: Commit** `feat(v2): stored depiction per structure`

### Task F0-5: Asset requests get their own IP bucket

**Files:**
- Modify: `backend-v2/src/marcus/core/settings.py` (`rate_limit_ip_assets_per_min: int = 3000`)
- Modify: `backend-v2/src/marcus/api/security.py` (`IpRateLimitMiddleware`, `RateLimiter` scopes)
- Test: `backend-v2/tests/api/test_security_layer.py`

**Interfaces:**
- Produces: `ASSET_GET = re.compile(r"^/api/v2/(papers/[0-9a-f-]{36}/pages/\d{1,4}/image|segments/[0-9a-f-]{36}/(image|depiction)|images/[0-9a-f-]{36}/image)$")`. A `GET` whose path matches uses scope `ip_assets` (3000/min per IP or IPv6 /64); every other request keeps scope `ip` (300/min). Both fail open like today.

- [ ] **Step 1: Write the failing tests:** `test_400_asset_gets_not_limited` (limit settings at defaults, 400 GETs of a segment image → no 429), `test_plain_gets_still_limited_at_301`, `test_post_to_asset_path_uses_plain_bucket`, `test_asset_regex_rejects_traversal` (`/api/v2/segments/../papers/x/image` does not match).
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run `uv run pytest tests/api -q`, expect PASS**
- [ ] **Step 5: Commit** `feat(v2): separate rate bucket for page, crop and depiction images`

### Task F0-6: Image job routes for the tool

**Files:**
- Modify: `backend-v2/src/marcus/api/routes/images.py`, `backend-v2/src/marcus/api/routes/events.py`, `backend-v2/src/marcus/api/schemas.py`, `backend-v2/src/marcus/core/pipeline.py` (`request_image_ocsr`)
- Modify: `backend-v2/docker/nginx.conf` (SSE location also for `^/api/v2/images/[^/]+/events$`)
- Test: `backend-v2/tests/api/test_images.py`, `backend-v2/tests/api/test_events.py`, `backend-v2/tests/core/test_pipeline.py`

**Interfaces:**
- Produces: `GET /api/v2/images` → `ImageJobList{jobs: list[ImageJobSummary]}` (this owner's jobs, newest first, not expired; `ImageJobSummary{id, display_name, status, engine, created_at, expires_at}`).
- Produces: `GET /api/v2/images/{job_id}/image` → the stored PNG (`image/png`, `Cache-Control: private, max-age=86400`).
- Produces: `GET /api/v2/images/{job_id}/events` → SSE on `image_channel(job_id)`, same frame format, ping, slot limit and end frame as paper events.
- Produces: `POST /api/v2/images/{job_id}/predictions {engine}` → 202 `StepAccepted`; `request_image_ocsr(session, job_id, engine) -> Step` mirrors `request_ocsr` (same per-owner limits, fake engine refused unless enabled).
- Changes: `ImageJobOut` gains `predictions: list[PredictionOut]` (all, newest first); its existing latest-prediction fields stay.

- [ ] **Step 1: Write the failing tests:** `test_list_images_only_mine`, `test_image_bytes_owner_only`, `test_image_events_stream_and_end`, `test_image_predictions_second_engine`, `test_image_job_out_lists_all_predictions`, `test_image_predictions_fake_engine_refused`.
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run `uv run pytest tests/api tests/core/test_pipeline.py -q`, expect PASS**
- [ ] **Step 5: Commit** `feat(v2): image job list, image, events and extra predictions`

### Task F0-7: Export carries curation

**Files:**
- Modify: `backend-v2/src/marcus/api/export.py`, `backend-v2/src/marcus/api/routes/papers.py` (`export_paper`)
- Test: `backend-v2/tests/api/test_export.py` (create; move existing export tests here if they live elsewhere)

**Interfaces:**
- Changes: `Chosen` gains `status: Literal["accepted", "rejected", "to_review"]`, `engine: str | None` (engine of the chosen prediction; `None` for a curated structure), `note: str | None`, `edited: bool` (curation has its own SMILES or molfile).
- Changes: `choose(..., include_rejected: bool)`; rejected segments are kept only when `include_rejected` and they have a structure.
- Produces: `GET /papers/{id}/export?format=json|csv|sdf&status=accepted|all`. Default `status`: `accepted` for SDF, `all` for JSON and CSV. `accepted` keeps only `status == "accepted"`.
- CSV header (exact order): `segment_id,page,idx,smiles,status,engine,note,edited,source`. SDF data fields: `MARCUS_STATUS`, `MARCUS_ENGINE`, `MARCUS_NOTE`, `MARCUS_EDITED`, plus the existing ones. JSON objects gain the four keys. Notes in CSV pass through `csv_cell` (formula-injection guard stays).

- [ ] **Step 1: Write the failing tests:** `test_csv_header_exact`, `test_sdf_default_only_accepted`, `test_json_default_all_includes_rejected`, `test_status_accepted_filter_json`, `test_note_formula_guarded_in_csv` (`"=HYPERLINK(...)"` → starts with `'`), `test_edited_flag`.
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run `uv run pytest tests/api -q`, expect PASS**
- [ ] **Step 5: Commit** `feat(v2): export carries status, engine, note and edited`

### Task F0-8: Retry one failed page

**Files:**
- Modify: `backend-v2/src/marcus/core/pipeline.py` (`retry_page`), `backend-v2/src/marcus/api/routes/papers.py`
- Test: `backend-v2/tests/core/test_pipeline.py`, `backend-v2/tests/api/test_page_retry.py`

**Interfaces:**
- Produces: `retry_page(session: Session, paper_id: uuid.UUID, page: int) -> Step`: locks the paper; requires that the page's newest `render_page` or `segment_page` step is `failed` and no step of the paper for that page is pending, queued or running; requires fewer than `MANUAL_PAGE_RETRIES = 2` earlier manual retries of that page (count `render_page` steps for the page beyond the first); creates a new `render_page` step for the page (its normal successors follow); sets a `done`/`failed` paper back to `processing`. Raises `RetryNotAllowed(reason: Literal["not_failed", "busy", "limit"])`.
- Produces: `POST /api/v2/papers/{paper_id}/pages/{n}/retry` → 202 `StepAccepted`; `RetryNotAllowed` → 409 with `detail` one of `"Page has not failed"`, `"Page is still running"`, `"No retries left for this page"`; other owner → 404; `n` outside `1..pages` → 404.

- [ ] **Step 1: Write the failing tests:** `test_retry_failed_page_creates_render_step_and_reopens_paper`, `test_retry_page_not_failed_409`, `test_retry_busy_409`, `test_third_retry_409_limit`, `test_retry_other_owner_404`, `test_retry_page_out_of_range_404`, and `test_retried_page_success_finishes_paper_done` (drive the planner through render → segment → ocsr done; paper ends `done`).
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run `uv run pytest tests/core tests/api -q`, expect PASS**
- [ ] **Step 5: Commit** `feat(v2): retry one failed page`

---

## Group F — the web UI (`frontend-v2/`)

Commands (run in `frontend-v2/`): `npm run lint`, `npm run typecheck`, `npm test -- --run <path>` (Vitest), `npm run build`, `npm run e2e -- <spec>` (Playwright against the fake stack). Every F task ends with `npm run lint && npm run typecheck && npm test -- --run` green.

**Design rule for every UI task:** before editing UI files, load the `impeccable:impeccable` skill (it carries the craft floor) and keep to the contract in spec §7 and the board `frontend-v2/reference/field-sheet-board.png`. The tool is Operate mode; the landing is Persuade mode.

### Task F1: Project skeleton, tokens, fonts, contract, test tooling

**Files:**
- Create: `frontend-v2/package.json`, `vite.config.ts`, `tsconfig.json`, `eslint.config.js`, `playwright.config.ts`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/routes.tsx`, `src/styles/tokens.css`, `src/styles/base.css`, `src/styles/fonts.css`, `public/fonts/GmarketSansLight.otf`, `public/sample/synth_015.pdf`, `scripts/prerender.tsx`, `src/test/setup.ts`, `.gitignore`
- Test: `frontend-v2/src/App.test.tsx`, `frontend-v2/scripts/prerender.test.ts`

**Interfaces:**
- Produces: routes (React Router `createBrowserRouter`): `/` Landing, `/about`, `/privacy`, `/disclaimer`, `/app` ToolHome, `/app/papers/:id` Workspace, `/app/images/:id` ImageResult, `*` NotFound. Page components are placeholders here; later tasks fill them.
- Produces: CSS custom properties in `tokens.css` named `--paper --surface --sunken --ink --text-2 --muted --line --green --accepted --to-check --rejected --failed-bg --failed-ink` plus `--font-head --font-text --font-mono --font-mark`; dark values under `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {…} }` and `:root[data-theme="dark"] {…}`.
- Produces: `npm run build` = `vite build && tsx scripts/prerender.tsx`; prerender renders `/`, `/about`, `/privacy`, `/disclaimer` with `react-dom/server` `renderToString` + `StaticRouter` into `dist/<route>/index.html`; `main.tsx` uses `hydrateRoot` when `#root` has children, else `createRoot`.
- ESLint: `react/no-danger: error`, `no-restricted-properties` for `innerHTML`/`outerHTML`/`insertAdjacentHTML`.

- [ ] **Step 1: Write the failing tests:** `App.test.tsx` renders `/app` and finds the text "MARCUS"; `prerender.test.ts` runs the build output check: `dist/index.html` contains `6b4eb402` and the text "Every molecule has a source." (the landing placeholder carries the headline already), and `dist/about/index.html` exists.
- [ ] **Step 2: Run `npm test -- --run`, expect FAIL**
- [ ] **Step 3: Implement** the skeleton; fonts from `@fontsource/bricolage-grotesque`, `@fontsource/hanken-grotesk`, `@fontsource/jetbrains-mono` (only the weights used: 400, 600, 700, 800 head; 400, 500, 600, 700 text; 400 mono); the contract comment from spec §7 as the first child of `<body>`.
- [ ] **Step 4: Run `npm run build && npm test -- --run && npm run lint && npm run typecheck`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): skeleton, tokens, fonts, design contract`

### Task F2: API layer and live updates

**Files:**
- Create: `frontend-v2/src/api/types.ts`, `src/api/client.ts`, `src/api/queries.ts`, `src/api/useLiveEvents.ts`
- Test: `frontend-v2/src/api/client.test.ts`, `src/api/useLiveEvents.test.ts`

**Interfaces:**
- Produces: `types.ts` mirrors `backend-v2/src/marcus/api/schemas.py` after F0 (PaperSummary with counts and title, PaperDetail, SegmentOut, PredictionOut, CurationOut, StepOut, QueueOut, ImageJobOut, ImageJobSummary) plus `type Engine = "decimer" | "decimer-hand" | "molnextr" | "molscribe"` and `type CurationStatus = "unchecked" | "accepted" | "rejected"` (from `marcus/core/enums.py`; `unchecked` and no curation both show as "To check").
- Produces: `api` object in `client.ts`: `listPapers()`, `getPaper(id)`, `getSteps(id)`, `uploadPaper(file, {engine, ocsr})`, `deletePaper(id)`, `putCuration(segmentId, body)`, `putBulkCuration(paperId, items)`, `runPrediction(segmentId, engine)`, `retryPage(paperId, n)`, `getQueue()`, `getText(id)`, `exportUrl(id, format, status)`, `pageImageUrl(id, n)`, `segmentImageUrl(id)`, `depictionUrl(segmentId, engine?)`, `depict(smiles, opts)`, `compare(smilesList)`, `mcs(molfiles)`, `smilesToMolfile(smiles)`, `uploadImage(file, engine)`, `listImages()`, `getImageJob(id)`, `runImagePrediction(id, engine)`, `imageUrl(id)`. All `fetch` with `credentials: "same-origin"`, base `/api/v2`. Errors throw `ApiError{status: number, detail: string, retryAfter?: number}`; 404 maps to `ApiError` with `status 404`.
- Produces: `useLiveEvents(kind: "paper" | "image", id: string, onEvent: () => void): {mode: "live" | "polling" | "ended"}` — `EventSource` on `/api/v2/{papers|images}/{id}/events`; on error or no event for 30 s it closes and polls (calls `onEvent`) every 2000 ms; stops at an end frame. `queries.ts` hooks call `queryClient.invalidateQueries` from `onEvent`.

- [ ] **Step 1: Write the failing tests:** `client.test.ts` (fetch mocked): 404 → `ApiError(404)`; 429 with `Retry-After: 7` → `retryAfter === 7`; `uploadPaper` sends `multipart/form-data` with `engine` and `ocsr`. `useLiveEvents.test.ts` (fake `EventSource`, fake timers): an event calls `onEvent`; an `error` switches `mode` to `"polling"` and calls `onEvent` every 2000 ms; an end frame sets `"ended"` and stops timers.
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run `npm test -- --run src/api`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): typed API client and live updates`

### Task F3: Field Sheet parts and app frame

**Files:**
- Create: `frontend-v2/src/ui/SpecimenLabel.tsx`, `src/ui/Stamp.tsx`, `src/ui/StateBadge.tsx`, `src/ui/Structure.tsx`, `src/ui/Smiles.tsx`, `src/ui/Button.tsx`, `src/ui/Kbd.tsx`, `src/ui/Toasts.tsx`, `src/ui/ThemeToggle.tsx`, `src/ui/Header.tsx`, `src/ui/Footer.tsx`, `src/ui/DesktopOnly.tsx`, `src/ui/ui.css`
- Test: `frontend-v2/src/ui/ui.test.tsx`

**Interfaces:**
- Produces: `<SpecimenLabel title: string rows?: [string, ReactNode][] tone?: "ink" | "failed">` (dark header bar, ruled rows, as on the board); `<Stamp state: "accepted" | "rejected" size?: "sm" | "lg" animate?: boolean>` (round, rotated −12°, word inside; with `animate` it scales from 1.4 and settles in 160 ms; no motion when `prefers-reduced-motion: reduce`); `<StateBadge state: "accepted" | "rejected" | "to-check" | "failed" | "reading">` with the exact words from Global Constraints plus "Reading…"; `<Structure src: string alt: string>` (`<img>`, `loading="lazy"`, `decoding="async"`, a quiet placeholder until loaded, "No drawing" on error); `<Smiles value: string>` (mono, wraps, a Copy button that writes to the clipboard and shows a toast "SMILES copied"); `useToast(): (msg: string, tone?: "info" | "error") => void`; `<ThemeToggle>` cycles system → light → dark, stores the choice in `localStorage` key `marcus-theme` (wrapped in try/catch), sets `data-theme` on `<html>`; `<DesktopOnly>` renders children at ≥ 1024 px and the exact note below that.
- Header: logo (`public/logo.png` from `maintenance/site/maintenance/logo.png`), "MARCUS" in Gmarket Sans, nav (How it works, Cite, GitHub `https://github.com/Kohulan/MARCUS`), primary "Open the tool". Footer links: About, Privacy, Disclaimer, DECIMER `https://decimer.ai`, COCONUT `https://coconut.naturalproducts.net`, GitHub.

- [ ] **Step 1: Write the failing tests:** each state badge shows its exact word; `Stamp` has `aria-label` "Accepted"/"Rejected"; `Stamp animate` adds class `stamp--landing` only when reduced motion is off (mock `matchMedia`); `Structure` renders an `<img>` with the given `src` and never an `<svg>` element; `Smiles` copy calls `navigator.clipboard.writeText` with the exact value; `ThemeToggle` survives a throwing `localStorage`; `DesktopOnly` at 800 px shows the exact note.
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement** (load `impeccable:impeccable` first)
- [ ] **Step 4: Run `npm test -- --run src/ui`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): Field Sheet parts and app frame`

### Task F4: Landing, about, privacy, disclaimer, Matomo

**Files:**
- Create: `frontend-v2/src/pages/Landing.tsx`, `src/pages/landing.css`, `src/pages/About.tsx`, `src/pages/Privacy.tsx`, `src/pages/Disclaimer.tsx`, `src/assets/caffeine.svg` (static, our own drawing; used via `<img>`), `public/matomo.js`
- Test: `frontend-v2/src/pages/pages.test.tsx`, `frontend-v2/e2e/landing.spec.ts`

**Interfaces:**
- Landing (Persuade mode) follows the contract's FIRST VIEWPORT: headline "Every molecule has a source." (80 px, `--green`), one paragraph, "Upload a PDF" → `/app` with the file picker opened, "Try a sample paper" → `/app?sample=1`, the taped specimen sheet with caffeine, an ACCEPTED stamp and its label table (Source: Sample paper, page 2 · Organism: *Coffea arabica* · Engine: DECIMER · SMILES `Cn1cnc2c1c(=O)n(C)c(=O)n2C`), then three numbered features (Three engines · Curate fast · Into COCONUT), then below the fold: the pipeline (segment → recognise → curate → COCONUT), the engines (DECIMER default, MolNexTR, MolScribe, DECIMER hand-drawn), "How to cite" with the exact citation and a Copy button, links to DECIMER and COCONUT. No invented numbers (PRODUCT.md evidence rule).
- About, Privacy, Disclaimer: content carried over from `frontend/src/views/AboutPage.vue`, `PrivacyPolicyPage.vue`, `DisclaimerPage.vue` as plain JSX text, updated for v2: files deleted after 30 days, no login, Matomo as the only tracker, upload limit 20 MB. Remove anything about OpenAI.
- `public/matomo.js`: the v1 tracker code from `frontend/public/index.html` lines ~127–140 (site id 7, `https://matomo.nfdi4chem.de/`), loaded with `<script src="/matomo.js" defer>` in `index.html`.

- [ ] **Step 1: Write the failing tests:** `pages.test.tsx`: Landing has one `h1` with the exact headline, both buttons, the exact citation text, and no element with `dangerouslySetInnerHTML`; Privacy contains "30 days" and "Matomo" and not "OpenAI". `e2e/landing.spec.ts` (Playwright on `vite preview`): the pre-rendered `/` has the headline in the HTML before JS runs (`page.route` blocks `*.js`); axe finds 0 serious/critical on `/`, `/about`, `/privacy`, `/disclaimer` in light and dark; at 390 px width there is no horizontal scroll.
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement** (load `impeccable:impeccable`, Persuade mode)
- [ ] **Step 4: Run `npm run build && npm test -- --run src/pages && npm run e2e -- landing`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): landing and info pages`

### Task F5: Tool home

**Files:**
- Create: `frontend-v2/src/tool/ToolHome.tsx`, `src/tool/DropZone.tsx`, `src/tool/PapersList.tsx`, `src/tool/tool.css`
- Test: `frontend-v2/src/tool/ToolHome.test.tsx`

**Interfaces:**
- Consumes: `api.uploadPaper`, `api.uploadImage`, `api.listPapers`, `api.listImages`, `api.deletePaper`, `useToast`, `DesktopOnly`.
- DropZone: one drop area and a file button; accepts `application/pdf`, `image/png`, `image/jpeg`, `image/webp`; rejects files over 20 MB in the browser with "This file is larger than 20 MB." Engine select (the four engines, DECIMER default) and an "Find structures automatically" switch (`ocsr` `auto` on, `off` off; PDF only). A PDF goes to `/app/papers/:id` after upload; an image to `/app/images/:id`. `?sample=1` fetches `/sample/synth_015.pdf` and uploads it with display name "Sample paper (synthetic)". A 429 shows its detail text and "Try again in N s" when `retryAfter` is set.
- PapersList: rows with title (or display name), status word, the counts from F0-1 ("15 structures · 9 accepted · 2 rejected · 4 to check · 1 failed page"), "Deleted in N days" from `expires_at` (N rounded up; "Deleted today" when < 1), Open, Delete (confirm dialog "Delete this paper and its results? This cannot be undone."). Image jobs listed below in their own short list. Empty state: one line and the sample button.

- [ ] **Step 1: Write the failing tests:** 21 MB file → message and no request; PDF upload calls `uploadPaper` with `{engine: "decimer", ocsr: "auto"}` and navigates to `/app/papers/<id>`; PNG goes to `uploadImage`; `?sample=1` fetches `/sample/synth_015.pdf`; list row shows "Deleted in 3 days" for `expires_at` 2.2 days ahead; delete asks first and calls `deletePaper` only after confirm; 429 with `retryAfter 7` shows "Try again in 7 s"; a display name `<img src=x onerror=alert(1)>` renders as text.
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement** (load `impeccable:impeccable`, Operate mode)
- [ ] **Step 4: Run `npm test -- --run src/tool`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): tool home with upload and papers list`

### Task F6: Paper workspace frame and status bar

**Files:**
- Create: `frontend-v2/src/workspace/Workspace.tsx`, `src/workspace/StatusBar.tsx`, `src/workspace/ExportMenu.tsx`, `src/workspace/GonePage.tsx`, `src/workspace/useWorkspace.ts`, `src/workspace/workspace.css`
- Test: `frontend-v2/src/workspace/Workspace.test.tsx`

**Interfaces:**
- Consumes: `api.getPaper`, `api.getSteps`, `api.getQueue`, `api.retryPage`, `api.exportUrl`, `useLiveEvents("paper", id, …)`.
- Produces: `useWorkspace(id): {paper, segments, steps, failedPages: {page: number, reason: string}[], selection, setSelection, view: "review" | "paper", setView}`; `view` and the focused segment live in the URL (`?view=paper&s=<segmentId>`) so reload and back work.
- Header row: title (or display name), DOI as a link `https://doi.org/<doi>` (text only, `rel="noopener noreferrer"`), counts, view toggle Review | Paper, Export menu (JSON, CSV, SDF; "Accepted only" / "All" for each; plain links to `exportUrl`), "Send N to COCONUT" (opens F13; disabled with a reason when N = 0).
- StatusBar: paper state word; while waiting "About N min in the queue" from `QueueOut.estimate_s` (rounded up to whole minutes; "Less than a minute" under 60 s); per-step progress "Pages read 6/8 · Structures read 12/15"; each failed page "Page 5 could not be read: <reason>" + "Retry page" (`retryPage`; 409 detail shown as a toast). Reason text from `error_class`: `TIMEOUT` → "it took too long", `BAD_INPUT` → "the page could not be opened", `ENGINE_ERROR` → "the engine failed", anything else → "an unknown error".
- A 404 from `getPaper` renders `GonePage`: "This paper is not here any more." + "It was deleted, it expired after 30 days, or it was opened in another browser." + link to `/app`.

- [ ] **Step 1: Write the failing tests:** failed `segment_page` step on page 5 with `TIMEOUT` → "Page 5 could not be read: it took too long" and a Retry button that calls `retryPage(id, 5)`; 409 → toast with the detail; queue `estimate_s 130` → "About 3 min in the queue"; 404 → GonePage text; export menu builds `/api/v2/papers/<id>/export?format=sdf&status=accepted`; `?view=paper` opens the paper view; live mode `"polling"` shows a small "Live updates paused, checking every 2 s" note.
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement** (load `impeccable:impeccable`)
- [ ] **Step 4: Run `npm test -- --run src/workspace`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): paper workspace frame and status bar`

### Task F7: Review grid

**Files:**
- Create: `frontend-v2/src/workspace/ReviewGrid.tsx`, `src/workspace/StructureCard.tsx`, `src/workspace/GridFilters.tsx`, `src/workspace/BulkBar.tsx`
- Test: `frontend-v2/src/workspace/ReviewGrid.test.tsx`

**Interfaces:**
- Consumes: `useWorkspace`, `api.putBulkCuration`, `api.depictionUrl`, `api.segmentImageUrl`, `Stamp`, `SpecimenLabel`, `StateBadge`, `Structure`.
- StructureCard: depiction (`depictionUrl(segment.id)`), a small crop toggle, label header "No. <n> · page <p>" where n is the 1-based position in (page, idx) order, engine and validity row, state (stamp for accepted/rejected, "To check" badge otherwise, "Reading…" when the segment has no prediction and its OCSR step is not finished, "Failed" when its OCSR step failed). Two engines that differ (two valid predictions with different SMILES) show "Engines differ".
- Filters (exact labels): All · To check · Accepted · Rejected · Failed, each with its count. Selection: click a checkbox, Shift-click a range, "Select all shown"; BulkBar: "Accept N", "Reject N", "Clear" → one `putBulkCuration` call (chunks of 500), optimistic update, rollback and toast on error. Enter or double-click on a card opens focus mode (F8). The grid lazy-loads images (`loading="lazy"`); cards are keyboard focusable in reading order.

- [ ] **Step 1: Write the failing tests:** 3 segments (accepted, rejected, none) → 1 stamp "Accepted", 1 stamp "Rejected", 1 "To check"; filter "Accepted" shows 1 card; select 2 + "Accept 2" → one `putBulkCuration` call with both ids; API error rolls back and toasts; a segment without prediction and a running OCSR step shows "Reading…"; a live event that adds a segment makes a new card appear without reload (invalidate → refetch); 1,200 selected → 3 calls of ≤ 500.
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement** (load `impeccable:impeccable`)
- [ ] **Step 4: Run `npm test -- --run src/workspace`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): review grid with bulk review`

### Task F8: Focus mode and keyboard review

**Files:**
- Create: `frontend-v2/src/workspace/FocusMode.tsx`, `src/workspace/useReviewKeys.ts`, `src/workspace/KeyHelp.tsx`
- Test: `frontend-v2/src/workspace/FocusMode.test.tsx`, `frontend-v2/e2e/keyboard-review.spec.ts`

**Interfaces:**
- Consumes: `api.putCuration`, `useWorkspace`, `Stamp animate`, `SpecimenLabel`, `Smiles`, page image with the box from `bbox`.
- Produces: `useReviewKeys(handlers: {accept, reject, edit, compare, prev, next, close, help}): void` — keys exactly as in Global Constraints; ignored while focus is in an input, textarea, select or the Ketcher iframe, and when Ctrl, Meta or Alt is held.
- FocusMode: one structure large; its crop; its page image scaled with the `bbox` drawn as a box; SMILES; engine predictions listed; a note field (saved with the next accept or reject); actions with their keys shown (`<Kbd>`). Accept/Reject land the stamp (signature interaction), save with `putCuration`, then move to the next "To check" structure after 250 ms (no wait with reduced motion). Esc returns to the grid with the same card focused. `?` toggles KeyHelp (a dialog with focus trap; Esc closes it).

- [ ] **Step 1: Write the failing tests:** pressing `a` calls `putCuration(segId, {status: "accepted", note})` and shows the Accepted stamp; `r` rejects; `ArrowRight` moves to the next structure; typing `a` in the note field does not accept; `Escape` closes and the grid card has focus; `?` opens a dialog named "Keys". `e2e/keyboard-review.spec.ts` on the fake stack: upload `synth_015.pdf`, wait for all structures, open the first with Enter, review every structure with only `a`/`r`/arrows, then the filter "To check" shows 0; axe 0 serious/critical in focus mode.
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement** (load `impeccable:impeccable`)
- [ ] **Step 4: Run `npm test -- --run src/workspace && npm run e2e -- keyboard-review`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): focus mode and keyboard review`

### Task F9: Paper view

**Files:**
- Create: `frontend-v2/src/workspace/PaperView.tsx`, `src/workspace/PageWithBoxes.tsx`, `src/workspace/TextColumn.tsx`
- Test: `frontend-v2/src/workspace/PaperView.test.tsx`

**Interfaces:**
- Consumes: `api.pageImageUrl`, `api.getText`, `useWorkspace` selection, `StructureCard` (list mode).
- Three columns as on the board: pages (each page image with a box per segment from `bbox`, numbered "No. n", colour by state, dashed for "To check") | text from the paper (`getText`, shown as text nodes split on blank lines; "Download text" saves a `.txt` via a `Blob` link) with the annotation area "Annotations (compounds, organisms, methods) come in a later version." | the structure list. Clicking a box selects and scrolls to its card; selecting a card scrolls its page into view and outlines its box. Boxes are buttons with `aria-label` "Structure n on page p".
- Text that is missing (docling step failed or not finished) shows "The text of this paper is not ready" or "The text could not be read: <reason>".

- [ ] **Step 1: Write the failing tests:** the text `<img src=x onerror=window.__xss=1>` renders as visible text and `window.__xss` stays undefined; 2 segments on page 2 → 2 box buttons with the exact aria labels; clicking box 2 selects card 2; "Download text" creates a `blob:` link with the file name `<display name>.txt`; a failed docling step shows the failure line.
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement** (load `impeccable:impeccable`)
- [ ] **Step 4: Run `npm test -- --run src/workspace`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): paper view with boxes and text`

### Task F10: Compare engines

**Files:**
- Create: `frontend-v2/src/workspace/Compare.tsx`
- Test: `frontend-v2/src/workspace/Compare.test.tsx`

**Interfaces:**
- Consumes: `api.runPrediction` (segments) or `api.runImagePrediction` (images), `api.compare`, `api.mcs`, `api.smilesToMolfile`, `api.depict`, `api.putCuration`.
- Produces: `<Compare target: {kind: "segment" | "image", id: string} predictions: PredictionOut[] onPick: (smiles: string) => void>` — "Run all engines" starts a prediction for each engine that has none yet; results appear live; a table of engines with their depictions side by side, pairwise Tanimoto from `/tools/compare` (shown with two decimals), and "Show common part" draws each with the MCS highlighted (`/tools/mcs` → `depict` with `highlight`). "Use this one" calls `onPick` (for segments: `putCuration(id, {status: "accepted", smiles})`).

- [ ] **Step 1: Write the failing tests:** with one prediction, "Run all engines" calls `runPrediction` for the three other engines; Tanimoto 0.8734 shows "0.87"; "Use this one" on MolNexTR calls `putCuration` with that SMILES and status accepted; a 429 from the tools bucket shows "Too many requests, try again in N s".
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run `npm test -- --run src/workspace`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): compare engines`

### Task F11: Structure editor (Ketcher in an isolated frame)

**Files:**
- Create: `frontend-v2/ketcher/index.html`, `frontend-v2/ketcher/main.tsx` (a second Vite entry, built to `dist/ketcher/`), `frontend-v2/src/workspace/Editor.tsx`, `frontend-v2/src/workspace/editorBridge.ts`
- Modify: `frontend-v2/vite.config.ts` (two inputs)
- Test: `frontend-v2/src/workspace/editorBridge.test.ts`, `frontend-v2/e2e/editor.spec.ts`

**Interfaces:**
- Produces: message protocol (both directions, `postMessage` to `window.location.origin` only; every handler checks `event.origin === window.location.origin` and `event.source` is the expected window): parent → frame `{type: "marcus:load", molfile: string | null, smiles: string | null}`; frame → parent `{type: "marcus:ready"}`, `{type: "marcus:save", molfile: string, smiles: string}`, `{type: "marcus:cancel"}`. Messages of any other shape are ignored.
- Produces: `<Editor segmentId: string initial: {smiles: string | null, molfile: string | null} onSaved: () => void>`: a dialog with the iframe `src="/ketcher/"`, `sandbox="allow-scripts allow-same-origin"`; on save calls `putCuration(segmentId, {status: <current or "accepted">, smiles, molfile})`, then the card's depiction comes from `api.depict(smiles)` once (shown with `URL.createObjectURL` on the returned SVG blob, never inlined).
- Ketcher loads only when the dialog opens (dynamic iframe).

- [ ] **Step 1: Write the failing tests:** `editorBridge.test.ts`: a message from another origin is ignored; a message with an unknown `type` is ignored; `marcus:save` from the frame resolves with its molfile and SMILES. `e2e/editor.spec.ts`: open a structure, press `e`, wait for Ketcher, save without change, the curation is stored (API check), and the `/ketcher/` response carries its own CSP header (checked in F15 once nginx serves it; here assert the frame loads and `marcus:ready` arrives).
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run `npm test -- --run src/workspace && npm run e2e -- editor`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): structure editor in an isolated frame`

### Task F12: Lookups and downloads

**Files:**
- Create: `frontend-v2/src/lookup/pubchem.ts`, `src/lookup/coconutDoi.ts`, `src/workspace/StructureActions.tsx`
- Test: `frontend-v2/src/lookup/lookup.test.ts`

**Interfaces:**
- Produces: `pubchemBySmiles(smiles: string): Promise<{cid: number, name: string | null, url: string} | null>` — `GET https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/cids/JSON?smiles=<encoded>` then the title from `/rest/pug/compound/cid/<cid>/property/Title/JSON`; `url = https://pubchem.ncbi.nlm.nih.gov/compound/<cid>`; any error → `null`. Same lookup as v1 `frontend/src/services/publicationService.js` `searchPubChemBySmiles`.
- Produces: `coconutCountForDoi(doi: string): Promise<number | null>` — the v1 DOI check (read `frontend/src/services/coconutService.js` and `frontend/src/components/coconut/` for the exact COCONUT search request) without login.
- StructureActions (in focus mode and card menu): Copy SMILES, Download image (the depiction SVG as `<name>-<n>.svg` via a blob link), Look up in PubChem (shows CID, name, link), Edit (F11), Compare (F10). The workspace header shows "N already in COCONUT for this DOI" when the count is known.

- [ ] **Step 1: Write the failing tests** (fetch mocked): SMILES with `#` and `+` is URL-encoded; PubChem 404 → `null`; CID 2519 → url `https://pubchem.ncbi.nlm.nih.gov/compound/2519`; COCONUT count parsed; network error → `null` and no crash.
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run `npm test -- --run src/lookup`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): PubChem and COCONUT lookups, downloads`

### Task F13: COCONUT batch submit

**Files:**
- Create: `frontend-v2/src/coconut/coconutApi.ts`, `src/coconut/CoconutLogin.tsx`, `src/coconut/SubmitForm.tsx`, `src/coconut/SubmitResults.tsx`
- Test: `frontend-v2/src/coconut/coconut.test.tsx`

**Interfaces:**
- Produces: `coconutLogin(email, password): Promise<string>` (token; the v1 request from `frontend/src/services/coconutService.js` `login`), token kept in `sessionStorage` key `marcus-coconut-token` (try/catch; memory fallback), never sent to `/api/v2`.
- Produces: `submitReports(token, items: ReportCreate[], onProgress): Promise<SubmitResult[]>` — `POST https://coconut.naturalproducts.net/api/reports/mutate` with body `{mutate: items.map(i => ({operation: "create", attributes: i}))}` (check the exact attribute names against v1 `submitToCoconut` and the COCONUT OpenAPI spec; record what you used in the task report). Sends chunks of `COCONUT_CHUNK = 50`; when the server answers 413 or 422 about the list size, halves the chunk and retries that chunk once. `SubmitResult = {segmentId, ok: true, reportId} | {segmentId, ok: false, error: string}`.
- SubmitForm: paper-level fields filled once (DOI as reference, organism(s) with parts, location, ecosystems, evidence) inherited by every accepted structure; per structure the curator can change name, comment, structural comments, organism (expandable row). Submit shows progress "Sent 50 of 120" and then SubmitResults (created report id or the error per structure).

- [ ] **Step 1: Write the failing tests** (fetch mocked): 120 items → 3 requests (50, 50, 20); a 413 on chunk 2 → chunk 2 resent as 25 + 25; per-structure override wins over the paper-level organism; the token never appears in any request to `/api/v2`; a failed item shows its error and others show their report id.
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement** (load `impeccable:impeccable` for the form)
- [ ] **Step 4: Run `npm test -- --run src/coconut`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): COCONUT batch submit`

Note: the first real submit with a test structure is done by the owner before switch day (spec §6). Do not submit to the real COCONUT in any test.

### Task F14: Single image result

**Files:**
- Create: `frontend-v2/src/images/ImageResult.tsx`
- Test: `frontend-v2/src/images/ImageResult.test.tsx`

**Interfaces:**
- Consumes: `api.getImageJob`, `api.imageUrl`, `useLiveEvents("image", id, …)`, `Smiles`, `Compare` (kind `image`), `Editor` (local only: an edited image structure is shown and copyable, not stored), `StructureActions`.
- Layout: the uploaded image | the structure (depiction from `api.depict(smiles)` as a blob URL) with its specimen label (engine, valid, time) | actions. States: waiting (queue estimate), reading, done, failed with reason; 404 → the GonePage text with "image" instead of "paper".

- [ ] **Step 1: Write the failing tests:** done job shows its SMILES and engine; failed job shows the reason; a live event refetches; 404 shows "This image is not here any more."
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run `npm test -- --run src/images`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): single image result`

### Task F15: Serve it from the v2 stack, CSP, end-to-end gates

**Files:**
- Create: `backend-v2/docker/Dockerfile.nginx` (stage 1 `node:22-alpine` runs `npm ci && npm run build` in `frontend-v2/`; stage 2 `nginxinc/nginx-unprivileged:1.27-alpine` with the conf and `dist/`)
- Modify: `backend-v2/docker/nginx.conf` (`location /` serves `dist/` with `try_files $uri $uri/index.html /app/index.html`; long cache for hashed `/assets/`; `no-cache` for HTML; the app CSP header from Global Constraints on everything but `/ketcher/`, which gets the Ketcher CSP; `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: camera=(), microphone=(), geolocation=()`; `/api/v2/` unchanged)
- Modify: `backend-v2/docker-compose.yml` (nginx service builds `Dockerfile.nginx`, build context the repo root)
- Modify: `judges/security/v2/test_stored_xss_frontend.py` (remove the `needs_frontend` skip; point the browser at the stack's nginx)
- Create: `frontend-v2/e2e/live.spec.ts`, `frontend-v2/e2e/big-paper.spec.ts`, `frontend-v2/e2e/csp.spec.ts`
- Test: `backend-v2/tests/deploy/test_compose_config.py`

**Interfaces:**
- e2e runs against `backend-v2/docker-compose.fake.yml` (fake engines) on 127.0.0.1 only, through the stack's nginx (so the real headers are tested).

- [ ] **Step 1: Write the failing tests:** `test_compose_config.py`: the nginx service builds `docker/Dockerfile.nginx`; `nginx -T` output (in the built image) has the exact app CSP and a different CSP inside `location /ketcher/`. `e2e/csp.spec.ts`: the response of `/`, `/app`, `/app/papers/x` has the exact app CSP; `/ketcher/` has the Ketcher CSP; no CSP violation is reported on landing, tool home, workspace and the editor (listen to `securitypolicyviolation`). `e2e/live.spec.ts`: upload `synth_015.pdf`, the first structure card appears without a reload while the paper is still processing. `e2e/big-paper.spec.ts`: a paper seeded with 200 segments (use the backend test seeding helpers through a small script `backend-v2/tests/e2e/seed_big_paper.py` that prints the paper id and owner token) loads all cards and depictions with no 429 in the network log. Lighthouse (desktop preset) on the built `/` scores performance ≥ 90 (`npx lighthouse … --preset=desktop --only-categories=performance`, record the score in the report).
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run** `cd backend-v2 && uv run pytest tests/deploy -q`, then the fake stack up, then `cd frontend-v2 && npm run e2e`, then `cd judges/security/v2 && <the README's run command>`. Expected: all PASS; the judge reports 20 passed, 0 skipped.
- [ ] **Step 5: Commit** `feat(v2): nginx serves the new UI with strict CSP; e2e gates`

### Task F16: Finish review and DESIGN.md

**Files:**
- Create: `frontend-v2/.impeccable/review/desktop.png` (1440 wide: landing first viewport), `frontend-v2/.impeccable/review/tool.png` (1440 wide: review grid), `frontend-v2/.impeccable/review/focus.png`, `frontend-v2/.impeccable/review/paper.png`, `frontend-v2/.impeccable/review/mobile.png` (390 wide: landing), each also in dark mode with a `-dark` suffix
- Create: `frontend-v2/DESIGN.md` and its sidecar (written by the documenter)

**Interfaces:**
- This task runs the closing steps of `impeccable:impeccable` new-work: run its detector once on the changed targets (`node <skill-base-dir>/scripts/detect.mjs --json`), fix what is mechanical, then spawn `impeccable:impeccable-finish-reviewer` fresh with the request, the contract (spec §7), the screenshots above, the detector findings, and the board PNG as the critique reference (code-led: no comp). Apply its material fixes in one batch, recapture, and get its verdict (two rounds at most). Then spawn `impeccable:impeccable-documenter` to write `DESIGN.md` from the built world.

- [ ] **Step 1: Capture the screenshots** with Playwright against the fake stack.
- [ ] **Step 2: Run the detector and the finish reviewer**; record the verdict table in the task report.
- [ ] **Step 3: Apply the fixes**, rerun `npm run lint && npm run typecheck && npm test -- --run && npm run e2e`, expect PASS.
- [ ] **Step 4: Run the documenter**; `frontend-v2/DESIGN.md` exists.
- [ ] **Step 5: Commit** `docs(frontend-v2): finish review fixes and DESIGN.md`

---

## Order and gates

1. F0-1 … F0-8 (backend) first, after the backend final whole-branch review has fixed the API (spec §11).
2. F1 … F14 in order (each needs the parts before it).
3. F15 needs F0 and F1–F14.
4. F16 last. Then the final whole-branch review of the frontend work.
5. Switch day stays the owner's choice.
