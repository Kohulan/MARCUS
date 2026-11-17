# MARCUS frontend v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new React web UI for MARCUS v2 (landing page plus curation tool) in the "Field Sheet" look, with the small backend changes it needs.

**Architecture:** Group F0 adds eight small, tested changes to `backend-v2` (counts, title, bulk curation, depictions, asset rate limits, image job routes, export fields, page retry). Group F builds `frontend-v2/`: one Vite + React + TypeScript app. The landing, about, privacy and disclaimer pages are pre-rendered to HTML. The tool under `/app` is a client app on TanStack Query and SSE. nginx serves the build on the same origin as `/api/v2`, with one shared file of static locations (`frontend-v2/deploy/ui-locations.conf`) that is proven in F1b and shipped unchanged in F15. Ketcher runs in an isolated same-origin iframe at `/ketcher/`, built separately so its worker and WebAssembly are served under the Ketcher CSP.

**Tech Stack:** Backend: Python 3.11, FastAPI, SQLAlchemy, Alembic, Celery, pytest (`uv run pytest`). Frontend: Node 22, npm, Vite, React 18, TypeScript strict, React Router 6 (declarative `<Routes>`), TanStack Query 5, Vitest + Testing Library, Playwright + `@axe-core/playwright`, `@fontsource` font packages, `ketcher-react`, `ketcher-standalone` and `ketcher-core` pinned at exactly `3.18.0`.

**Spec:** `docs/superpowers/specs/2026-11-17-marcus-frontend-v2-design.md` (approved 2026-11-17). Backend API: `docs/superpowers/specs/2026-11-16-marcus-v2-backend-design.md` §9. Visual reference: `frontend-v2/reference/field-sheet-board.html` and `.png`. Product context: `frontend-v2/PRODUCT.md`.

## Global Constraints

- Commits: author Kohulan Rajan only. No `Co-Authored-By`, no `Claude-Session`, no "Generated with" lines. Never push. Never touch `main`. Branch: `v2-backend` (F0) and the same branch for F (the frontend folder is new).
- Never point any test, judge or script at production (jarvis ports 8080, 9000, or `marcus-backend`/`marcus-frontend` containers). Do not touch the `marcus-maintenance` container.
- Never print `.env` secret values.
- F0 tasks follow the backend plan's rules: every new route is owner-checked with `current_owner` and returns the one shared 404 (`not_found()` from `marcus.api.deps`) for missing, deleted and other owners' items; no raw error text leaves a new route; route modules never import each other (shared code goes to a module under `marcus/api/`, as `read.py` says). Every new owner-checked route is added to `ROUTES` in `backend-v2/tests/api/test_ownership.py`.
- **Pages are 0-based in the API** (steps, segments, `GET /papers/{id}/pages/{n}/image`, `POST …/pages/{n}/retry`). The UI always shows `page + 1` ("Page 5" is API page 4) and always sends the 0-based value.
- **`bbox` is `[x0, y0, x1, y1]` in pixels of the 300 DPI page PNG** (`marcus/workers/segment.py:30`), not x, y, width, height.
- **`error_class` values (exact, lower case, `marcus/core/enums.py`):** `timeout`, `worker_lost`, `bad_input`, `engine_error`; `null` when the step did not fail. UI text (exact): `timeout` → "it took too long", `worker_lost` → "the worker stopped while reading it", `bad_input` → "the page could not be opened", `engine_error` → "the engine failed", anything else → "an unknown error". Raw error text (`Paper.error`, `ImageJobOut.error`) is never shown.
- **Curation writes:** `PUT /segments/{id}/curation` replaces the whole curation ("omitted fields are cleared", `api/schemas.py:108`). Ruling: the client always sends the full record (`status`, `smiles`, `molfile`, `note`), built by `curationBody(current, change)` (F2) from the cached current curation; no caller builds a body by hand. Why: no backend change, and one pure function is easy to pin with tests.
- Upload limit text in the UI: "max 20 MB". PDF or one image (PNG, JPEG or TIFF: the types `marcus/api/uploads.py` accepts; no WebP).
- Engines shown to users: DECIMER (default), DECIMER hand-drawn, MolNexTR, MolScribe. Wire values: `decimer`, `decimer-hand`, `molnextr`, `molscribe`. `fake` is never shown and never in the built UI; e2e tests that need OCSR upload through the API with `engine=fake` (see Group F commands).
- `ocsr` mode values: `auto` (default) and `off`.
- Minimum tool width 1024 px. Below that the tool shows exactly: "MARCUS is made for a desktop screen". The landing works at phone width.
- No `dangerouslySetInnerHTML`, `innerHTML`, `outerHTML` or `insertAdjacentHTML` anywhere with server or user data. SVG depictions are shown with `<img src>`, never inlined. An ESLint rule (`react/no-danger`: error) enforces it.
- CSP of the app (exact): `default-src 'self'; script-src 'self' https://matomo.nfdi4chem.de; connect-src 'self' https://coconut.naturalproducts.net https://pubchem.ncbi.nlm.nih.gov https://matomo.nfdi4chem.de; img-src 'self' data: blob: https://matomo.nfdi4chem.de; style-src 'self'; font-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`. No inline scripts. No inline `<style>` blocks. **No `style` prop in any component that a pre-rendered page renders** (Landing, About, Privacy, Disclaimer, NotFound, Header, Footer, Stamp, SpecimenLabel, Smiles, Button, ThemeToggle): in pre-rendered HTML it becomes a `style="…"` attribute, which `style-src 'self'` blocks. Client-only tool components may set styles through React's `style` prop (applied through the CSSOM, which the CSP does not block); prefer classes and CSS custom properties.
- CSP of `/ketcher/` only (exact, starting point; F1b may only remove sources, never add `'unsafe-eval'`): `default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' data: blob:; object-src 'none'; base-uri 'self'; form-action 'none'; frame-ancestors 'self'`. F1b records the final value here if it removes a source.
- Fonts are self-hosted (no Google Fonts at run time): Bricolage Grotesque (headings), Hanken Grotesk (text), JetBrains Mono (SMILES, keys), Gmarket Sans Light (wordmark only; source `maintenance/site/maintenance/GmarketSansLight.otf`, shipped as a WOFF2 subset of the letters of "MARCUS").
- Colour tokens, light (exact): paper `#FAFAF7`, surface `#FFFFFF`, sunken `#F4F6F2`, ink `#15241B`, text-2 `#3E5044`, muted `#55675A`, line `#DCE3DA`, green `#1E4D33`, accepted `#2D7A46`, to-check `#9A5B0C`, rejected `#B23A2A`, failed-bg `#F7EEEB`, failed-ink `#7A3B30`. Dark values are the builder's call in the same world, each pair checked for WCAG AA (4.5:1 text, 3:1 UI).
- State words (exact, used everywhere): "Accepted", "Rejected", "To check", "Failed", plus the transient "Reading…" and, for papers uploaded with `ocsr=off`, "Not read yet". A state always shows its word and its shape (stamp or badge), never colour alone. The API value `unchecked` (and a missing curation) is "To check" in the UI and `unchecked` on the wire and in exports.
- Keys in focus mode (exact): A accept, R reject, E edit, C compare, ← previous, → next, Esc back to grid, ? key list.
- Matomo: tracker `https://matomo.nfdi4chem.de/`, site id `7`, loaded from a file `/matomo.js`, not inline. Route changes send a page view with the route template (`/app/papers/:id`), never a real paper, segment or image id.
- Citation text (exact): "Rajan K., Weißenborn V., Lederer L., Zielesny A., Steinbeck C. MARCUS: molecular annotation and recognition for curating unravelled structures. Digital Discovery 2025, 4(11), 3137–3148. https://doi.org/10.1039/d5dd00313j"
- Sample paper: `backend-v2/tests/fixtures/pdfs/synth_015.pdf`, copied to `frontend-v2/public/sample/synth_015.pdf`; the "Try a sample paper" button fetches it and uploads it through `POST /api/v2/papers` as a `File` named `Sample paper (synthetic).pdf` (the display name is the file name, `marcus/api/uploads.py:119-124`).
- Design contract: the HTML comment in spec §7 ("Contract"), word for word, is the first child of `<body>` in `frontend-v2/index.html` and survives `npm run build` (`scripts/check-dist.mjs` greps `dist/index.html` and `dist/app/index.html` for `6b4eb402`).
- Copy: plain English, product words as in v1: segment, structure, engine, SMILES, molfile, page, paper.
- Never name a frontend folder `lib` (the root `.gitignore:17` ignores `lib/`).

## Review Focus

1. **A paper still running when the curator opens it.** Cards must appear as steps finish, without a reload, and a card whose OCSR step has not finished shows "Reading…" not "no structure". Test in F2 (named SSE frames, reconnect, polling only while the stream is down), F7 (SSE event adds a card) and F15 `live.spec.ts`.
2. **A page or engine that failed.** It must show as a failed page with its reason and a retry, never as an empty paper. Test in F6 (failed `segment_page` step on API page 4 renders "Page 5 could not be read: it took too long"; a failed `check_pdf` renders its own line; a page failed then retried and done is not shown), F7 (failed OCSR → "Failed" + "Try another engine"), and F0-1 (`failed_pages` counts it).
3. **Hostile text from the PDF.** Extracted text, display names, titles, notes and SMILES containing `<img src=x onerror=…>` must render as text. Test in F5 (display name), F6 (title), F7 (note, SMILES), F9 (text column) and F15 (judge `test_stored_xss_frontend` passes after it has seen the payload as text).
4. **A big paper (200 structures).** The grid must load without 429s and stay usable. Test in F0-5 (400 asset GETs pass, the 301st plain GET is limited) and F15 (e2e loads a seeded 200-segment paper with 200 distinct SMILES, at the default 300/min IP limit, with no 429 and every image loaded).
5. **Expired or deleted paper, or another browser's paper link.** The UI must show one plain "This paper is not here any more" page, never a crash or a spinner. Test in F6 (API 404 → that page).
6. **Curation never loses data.** Accept after an edit keeps the edited structure; an edit keeps the note; bulk accept keeps notes. Test in F2 (`curationBody`), F8, F10, F11, F0-3.

---

## Group F0 — backend support (`backend-v2/`)

Run all F0 tests with `cd backend-v2 && uv run pytest <path> -q`. Use the seeding helpers in `tests/api/conftest.py` (`new_owner`, `make_client`, `ocsr_result`, `SEGS`, and the planner-driven seeding there). Each F0 task ends with the full API suite green: `uv run pytest tests/api -q`. Step 2 of every task ("run, expect FAIL") and step 4 ("run, expect PASS") are the TDD loop; the commands are given once per task.

### Task F0-1: Paper counts on summaries; engine on steps

**Files:**
- Modify: `backend-v2/src/marcus/api/schemas.py` (`PaperSummary`, `StepOut`)
- Modify: `backend-v2/src/marcus/api/read.py` (new `paper_counts(db, paper_ids) -> dict[uuid, Counts5]`: one grouped query set per call, no N+1)
- Modify: `backend-v2/src/marcus/api/routes/papers.py` (`list_papers`, `get_paper` build the summaries; `PaperSummary.model_validate(paper)` gets the counts passed in)
- Test: `backend-v2/tests/api/test_papers_read.py`, `backend-v2/tests/api/test_paper_steps.py`

**Interfaces:**
- Produces: `PaperSummary` gains `structures: int`, `accepted: int`, `rejected: int`, `to_review: int`, `failed_pages: int`. `structures` = segments of the paper; `accepted`/`rejected` = curations with that status; `to_review = structures - accepted - rejected` (every segment has a curation row, `pipeline.py:386`); `failed_pages` = distinct pages whose newest `render_page` or `segment_page` step (by `created_at`, then `seq`) is `failed`. A page whose failed step was followed by a newer step of the same kind that is `done` or still active is not counted.
- Produces: `StepOut` gains `engine: str | None` (the step's engine; set for `ocsr` steps). Compare (F10) and the cards (F7) need it to tell which engine is reading or failed.

- [ ] **Step 1: Write the failing tests:** `test_list_papers_has_counts` (1 paper, 3 segments; accepted on 1, rejected on 1; page 1 `segment_page` failed → `(3, 1, 1, 1, 1)`), `test_failed_page_retried_ok_is_not_counted`, `test_failed_page_retry_running_is_not_counted`, `test_list_papers_query_count_does_not_grow_with_papers` (1 vs 5 papers: same number of SQL statements, counted with a SQLAlchemy event listener), `test_step_out_has_engine`.
- [ ] **Step 2: Run** `uv run pytest tests/api/test_papers_read.py tests/api/test_paper_steps.py -q`, expect FAIL (`KeyError: 'structures'`).
- [ ] **Step 3: Implement** the grouped counts and the fields; `PaperDetail` inherits them.
- [ ] **Step 4: Run `uv run pytest tests/api -q`, expect PASS**
- [ ] **Step 5: Commit** `feat(v2): paper summaries carry structure and failure counts`

### Task F0-2: Paper title from the DOI step

**Files:**
- Create: `backend-v2/alembic/versions/0005_paper_title.py` (`papers.title TEXT NULL`)
- Modify: `backend-v2/src/marcus/core/models.py` (`Paper.title`)
- Modify: `backend-v2/src/marcus/workers/cpu.py` (`doi` handler, `fetch_title`)
- Modify: `backend-v2/src/marcus/core/pipeline.py` (`_check_doi_result`, `_after_doi`)
- Modify: `backend-v2/src/marcus/api/schemas.py` (`PaperSummary.title: str | None`)
- Test: `backend-v2/tests/workers/test_cpu.py`, `backend-v2/tests/core/test_pipeline.py`, `backend-v2/tests/core/test_migrations.py`

**Interfaces:**
- Produces: `fetch_title(doi: str, timeout_s: float) -> str | None` in `marcus/workers/cpu.py`. Ruling: uses `requests` (already in the cpu image through `pdf2doi`, `uv.lock`), not `httpx` (only in `dev`) and not `respx` (nowhere); no new dependency. Requests: Crossref `https://api.crossref.org/works/{quote(doi, safe="")}` (`message.title[0]`), then DataCite `https://api.datacite.org/dois/{quote(doi, safe="")}` (`data.attributes.titles[0].title`); `allow_redirects=False` (a redirect counts as no title); `timeout=timeout_s`; at most 256 KiB of body read; any error or non-200 → `None`. The DOI comes from an untrusted PDF, hence the quoting. Result: tags removed (`<[^>]+>`), HTML entities unescaped, whitespace runs folded to one space, stripped, cut to `TITLE_MAX_CHARS = 500`; empty → `None`.
- The DOI step result becomes `{"doi": str|None, "title": str|None}`; the title call runs only when a DOI was found and shares the existing `DOI_TOTAL_S = 12` budget (skipped when less than 1 s is left; each call gets `min(DOI_CALL_TIMEOUT_S, time left)`).
- `_check_doi_result` accepts a missing `title` (old results) and rejects a non-string, non-null one. `_after_doi` stores `paper.title`.

- [ ] **Step 1: Write the failing tests** (a fake `requests` transport: a `requests.adapters.BaseAdapter` subclass mounted on the session `fetch_title` uses, or `monkeypatch` of `requests.Session.get`): `test_fetch_title_crossref_then_datacite` (Crossref 404, DataCite 200 → DataCite title), `test_fetch_title_strips_markup_and_cuts` (`"<i>Coffea</i>  alkaloids"` → `"Coffea alkaloids"`; 600 chars → 500), `test_fetch_title_quotes_doi_in_path` (`10.1/../x?y` → path contains `10.1%2F..%2Fx%3Fy`), `test_fetch_title_redirect_is_none`, `test_fetch_title_error_is_none`, `test_doi_step_skips_title_when_budget_spent`, `test_after_doi_stores_title`, `test_check_doi_result_rejects_non_string_title`, `test_check_doi_result_accepts_missing_title`, `test_migration_0005_up_down`.
- [ ] **Step 2: Run** `uv run pytest tests/workers/test_cpu.py tests/core -q`, expect FAIL.
- [ ] **Step 3: Implement** as in Interfaces. The worker stays the only code with internet access; the API never calls Crossref or DataCite.
- [ ] **Step 4: Run `uv run pytest tests/workers/test_cpu.py tests/core -q` and `tests/api -q`, expect PASS**
- [ ] **Step 5: Commit** `feat(v2): doi step stores the paper title`

### Task F0-3: Bulk curation

**Files:**
- Modify: `backend-v2/src/marcus/api/routes/papers.py` (new route), `backend-v2/src/marcus/api/schemas.py`
- Modify: `backend-v2/tests/api/test_ownership.py` (`ROUTES` gains `("PUT", "/api/v2/papers/{p}/curation", {"items": [{"segment_id": "{s}", "status": "accepted"}]})`; extend the test's formatting so `{s}` is filled inside JSON bodies as it is in paths)
- Test: `backend-v2/tests/api/test_bulk_curation.py`

**Interfaces:**
- Produces: `PUT /api/v2/papers/{paper_id}/curation`, body `BulkCurationIn{items: list[BulkCurationItem]}` with `BulkCurationItem{segment_id: UUID, status: CurationStatus, note: str | None (max MAX_NOTE_CHARS, same NUL and blank-to-None cleaning as CurationIn)}`, `extra="forbid"`; `1 <= len(items) <= 500` (else 422). A `segment_id` that appears twice in one call → 422. One transaction. Every `segment_id` must belong to this paper, else 404 for the whole call and nothing changes.
- Ruling (note): a `note` key that is **absent** from an item keeps the existing note; a `note` key that is **present** (a string, or `null`) replaces it. Implemented with `item.model_fields_set`. Why: "Accept N" sends no note and must not wipe notes.
- An existing curated `smiles`/`molfile` is always kept (only status and note change). Returns `BulkCurationOut{updated: int}`. Rate limit: only the plain IP bucket, the same as `PUT /segments/{id}/curation`.

- [ ] **Step 1: Write the failing tests:** `test_bulk_accept_three`, `test_bulk_keeps_curated_smiles_and_molfile`, `test_bulk_absent_note_keeps_note`, `test_bulk_null_note_clears_note`, `test_bulk_duplicate_segment_422`, `test_bulk_foreign_segment_404_and_nothing_changed`, `test_bulk_other_owner_paper_404`, `test_bulk_501_items_422`, `test_bulk_empty_422`.
- [ ] **Step 2: Run** `uv run pytest tests/api/test_bulk_curation.py -q`, expect FAIL (405).
- [ ] **Step 3: Implement** with one `SELECT … FOR UPDATE` of the paper's segments named in the call, then updates of their curation rows.
- [ ] **Step 4: Run `uv run pytest tests/api -q`, expect PASS**
- [ ] **Step 5: Commit** `feat(v2): bulk curation for one paper`

### Task F0-4: Stored depictions per structure

Ruling (refines spec §9.1): the GPU OCSR images have no Java, and the CDK drawing lives only in the tools image. So the depiction is drawn lazily, on the first request, by the existing `marcus.tools.depict` task on `q.tools`, and stored on disk keyed by the SMILES. Later requests read the file. Same drawing as `/tools/depict`, drawn once per distinct SMILES, not 200 tool calls per page view.

Ruling (bounding the write path, review C3): the SMILES drawn always comes from the owner's own stored rows (a valid prediction, or the curation), never from the request. A miss for a **prediction** SMILES is free: predictions are made only by OCSR workers, which the upload limits already bound, and each distinct SMILES is drawn once. A miss for a **curated** SMILES (client-chosen through `PUT curation`, up to 10 000 chars) counts one hit against the owner's `tools` bucket (60/min, the `/tools/*` limit). A cache hit is free. SMILES longer than `MAX_SMILES = 2000` (the tools route's limit) are never drawn. Why: a curator's grid of engine output must not hit the tools limit, and a client that writes curations in a loop is held to the tools limit.

Ruling (cache busting, review C2): the depiction URL carries a version the client computes from the inputs (`v=<depictionKey(segment)>`, F2); the server ignores `v` and keeps `Cache-Control: private, max-age=86400`. Why: a changed structure gets a new URL both after a reload and inside the same page (the HTML "list of available images" may reuse an image for an unchanged URL whatever its cache headers say, so `ETag` + `no-cache` alone would still show the old drawing in the open page).

**Files:**
- Create: `backend-v2/src/marcus/api/tooling.py` (`run_tool`, `WAIT_S`, `MAX_SMILES` and `_send_and_wait`/`_release` moved here from `routes/tools.py`, which now imports them; routes never import each other)
- Create: `backend-v2/src/marcus/api/depiction.py` (`shown_structure`, `draw_or_read`)
- Modify: `backend-v2/src/marcus/api/routes/tools.py` (imports from `tooling`), `backend-v2/src/marcus/api/routes/segments.py` (new route)
- Modify: `backend-v2/src/marcus/core/storage.py` (`depiction_path`, `depiction_marker_path`)
- Modify: `backend-v2/src/marcus/workers/retention.py` (purge old depictions, size cap)
- Modify: `backend-v2/tests/api/test_ownership.py` (`ROUTES` gains `("GET", "/api/v2/segments/{s}/depiction", None)`)
- Test: `backend-v2/tests/api/test_depiction.py`, `backend-v2/tests/api/test_tools_routes.py` (unchanged, must stay green), `backend-v2/tests/workers/test_retention.py`, `backend-v2/tests/core/test_storage.py`

**Interfaces:**
- Produces: `depiction_path(smiles_sha256: str) -> Path` = `<data root>/depictions/<sha[:2]>/<sha>.svg`; `depiction_marker_path(sha) -> Path` = same with `.nodraw`; both reject anything but 64 lowercase hex chars.
- Produces: `shown_structure(paper, segment, curation, predictions, engine: Engine | None) -> tuple[str, Literal["curated", "predicted"]] | None` in `marcus/api/depiction.py`. With `engine`: the newest valid prediction of that engine (`"predicted"`). Without: the curated SMILES (or the SMILES derived from a curated molfile with `smiles_from_molfile`) when the curation has one (`"curated"`), else the newest valid prediction of the paper's engine, else the newest valid prediction of any engine. **Curation status is ignored** (a rejected structure still has a drawing); it does not reuse `export.choose`, which skips rejected segments.
- Produces: `GET /api/v2/segments/{segment_id}/depiction?engine=<Engine>&v=<ignored>`: owner-checked through `get_owned_segment`. 404 (the shared `not_found()`) when `shown_structure` is `None`, when the SMILES is longer than `MAX_SMILES`, or when a `.nodraw` marker exists. On a hit: the file. On a miss: for a `"curated"` source call `tools_limit(request, owner)` first (429 with `Retry-After` when over); then `run_tool("marcus.tools.depict", {"smiles": s, "fmt": "svg", "width": 512, "height": 512, "highlight": ""}, WAIT_S)` in the threadpool. Results: SVG text of at most `DEPICTION_MAX_BYTES = 512 * 1024` bytes → written atomically (tmp + `os.replace`) and returned; larger → returned once, not stored; a 422 from `run_tool` (CDK cannot read the SMILES) → empty `.nodraw` marker written, 404; a 504 or 500 → 503 with `Retry-After: 5`, nothing written.
- Response headers: `Content-Type: image/svg+xml`, `Cache-Control: private, max-age=86400`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'`.
- Retention (daily purge in worker-cpu): files under `depictions/` with mtime older than `DEPICTION_MAX_DAYS = 30` are deleted; then, while the directory holds more than `DEPICTIONS_MAX_BYTES = 2 * 1024**3`, the oldest files are deleted first.

- [ ] **Step 1: Write the failing tests:** `test_depiction_miss_draws_once_then_reads_file` (monkeypatch `marcus.api.depiction.run_tool`, call twice, assert one call and same bytes), `test_depiction_two_segments_same_smiles_one_draw`, `test_depiction_curated_smiles_used_without_engine`, `test_depiction_curated_molfile_only_uses_derived_smiles`, `test_depiction_rejected_segment_still_drawn`, `test_depiction_engine_param_picks_that_engine`, `test_depiction_v_param_ignored`, `test_depiction_no_valid_prediction_404`, `test_depiction_other_owner_404`, `test_depiction_headers`, `test_depiction_tool_timeout_503_no_file`, `test_depiction_bad_smiles_404_marker_then_no_redraw`, `test_depiction_smiles_over_2000_404_no_draw`, `test_depiction_svg_over_cap_not_stored`, `test_depiction_curated_miss_counts_tools_bucket` (61st curated miss in a minute → 429; prediction misses and cache hits do not count), `test_depiction_path_rejects_bad_sha`, `test_retention_purges_old_depictions`, `test_retention_depictions_size_cap_oldest_first`.
- [ ] **Step 2: Run** `uv run pytest tests/api/test_depiction.py tests/workers/test_retention.py tests/core/test_storage.py -q`, expect FAIL.
- [ ] **Step 3: Implement** per Interfaces (move `run_tool` first, keep `test_tools_routes.py` green).
- [ ] **Step 4: Run `uv run pytest tests/api tests/workers/test_retention.py tests/core/test_storage.py -q`, expect PASS**
- [ ] **Step 5: Commit** `feat(v2): stored depiction per structure`

### Task F0-5: Asset requests get their own IP bucket

**Files:**
- Modify: `backend-v2/src/marcus/core/settings.py` (`rate_limit_ip_assets_per_min: int = 3000`)
- Modify: `backend-v2/src/marcus/api/security.py` (`IpRateLimitMiddleware`, `RateLimiter.limit_for` scopes)
- Test: `backend-v2/tests/api/test_security_layer.py`

**Interfaces:**
- Produces: `ASSET_GET = re.compile(r"^/api/v2/(papers/[0-9a-f-]{36}/pages/\d{1,4}/image|segments/[0-9a-f-]{36}/(image|depiction)|images/[0-9a-f-]{36}/image)$")`, matched against `scope["path"]` (no query string). A `GET` whose path matches uses scope `ip_assets` (3000/min per IP or IPv6 /64); every other request keeps scope `ip` (300/min). Both fail open like today.

- [ ] **Step 1: Write the failing tests:** `test_400_asset_gets_not_limited` (limit settings at defaults, 400 GETs of a segment image → no 429), `test_depiction_get_with_query_uses_asset_bucket`, `test_plain_gets_still_limited_at_301`, `test_post_to_asset_path_uses_plain_bucket`, `test_asset_regex_rejects_traversal` (`/api/v2/segments/../papers/x/image` does not match).
- [ ] **Step 2: Run** `uv run pytest tests/api/test_security_layer.py -q`, expect FAIL.
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run `uv run pytest tests/api -q`, expect PASS**
- [ ] **Step 5: Commit** `feat(v2): separate rate bucket for page, crop and depiction images`

### Task F0-6: Image job routes for the tool

**Files:**
- Modify: `backend-v2/src/marcus/api/routes/images.py` (routes; `ImagePrediction` and `ImageJobOut` move out of it), `backend-v2/src/marcus/api/schemas.py` (receives `ImagePrediction`, `ImageJobOut`, new `ImageJobSummary`, `ImageJobList`, `ImageStepOut`), `backend-v2/src/marcus/api/routes/events.py` (stream generalised over channel and status reader), `backend-v2/src/marcus/core/pipeline.py` (`request_image_ocsr`, image job status rule in `complete_step` / `fail_step`)
- Modify: `backend-v2/docker/nginx.conf` (SSE location regex becomes `^/api/v2/(papers|images)/[^/]+/events$`)
- Modify: `backend-v2/tests/api/test_ownership.py` (image routes; it has an image job fixture or gains one)
- Test: `backend-v2/tests/api/test_images.py`, `backend-v2/tests/api/test_events.py`, `backend-v2/tests/core/test_pipeline.py`, `backend-v2/tests/deploy/test_compose_config.py` (nginx SSE location)

**Interfaces:**
- Produces: `GET /api/v2/images` → `ImageJobList{jobs: list[ImageJobSummary]}` (this owner's jobs, newest first, not expired, not deleted; `ImageJobSummary{id, display_name, status, engine, created_at, expires_at}`).
- Produces: `GET /api/v2/images/{job_id}/image` → the stored PNG (`image/png`, `IMAGE_HEADERS`).
- Produces: `GET /api/v2/images/{job_id}/events` → SSE on `image_channel(job_id)`, same frames (`event: snapshot` with `{status}`, unnamed `data:` frames, `: ping`, `event: end`, `event: error`), slot limit and duration as paper events; terminal statuses `done`, `failed`, `deleted`.
- Produces: `POST /api/v2/images/{job_id}/predictions {engine}` → 202 `StepAccepted`. The route copies the duplicate-click guard of `POST /segments/{id}/predictions` (`routes/segments.py:45-58`: an active ocsr step for this job and engine is returned instead of a new one) and refuses `fake` unless enabled (422 "Engine not available"). `request_image_ocsr(session, job_id, engine) -> Step` mirrors `request_ocsr`: locks the job, raises `ValueError` for a missing or deleted job, creates a pending `ocsr` step, and sets the job's status to `queued`. There are no per-owner limits on `request_ocsr` and none are added.
- Ruling (image job status with several predictions): while any ocsr step of the job is active the job is `queued`; when the last active step finishes, the job is `done` if it has at least one prediction, else `failed`. So a failed second engine never turns a job with a good first result into `failed`, and a new request reopens the job so its event stream does not end at once. `ImageJobOut.error` keeps its current value for API compatibility; the UI never shows it.
- Changes: `ImageJobOut` gains `predictions: list[PredictionOut]` (all, newest first), `error_class: str | None` (of the newest failed step), and `steps: list[ImageStepOut{engine: str, status: str, error_class: str | None}]` (newest first); its existing `prediction` field stays.

- [ ] **Step 1: Write the failing tests:** `test_list_images_only_mine`, `test_image_bytes_owner_only`, `test_image_events_stream_and_end`, `test_image_predictions_second_engine`, `test_image_predictions_repeat_click_same_step`, `test_image_predictions_fake_engine_refused`, `test_image_job_out_lists_all_predictions_and_steps`, `test_image_job_second_engine_fails_job_stays_done`, `test_image_job_only_engine_fails_job_failed_with_error_class`, `test_request_image_ocsr_reopens_done_job`, `test_nginx_sse_location_covers_images`.
- [ ] **Step 2: Run** `uv run pytest tests/api/test_images.py tests/api/test_events.py tests/core/test_pipeline.py -q`, expect FAIL.
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run `uv run pytest tests/api tests/core/test_pipeline.py tests/deploy -q`, expect PASS**
- [ ] **Step 5: Commit** `feat(v2): image job list, image, events and extra predictions`

### Task F0-7: Export carries curation

**Files:**
- Modify: `backend-v2/src/marcus/api/export.py`, `backend-v2/src/marcus/api/routes/papers.py` (`export_paper`)
- Test: `backend-v2/tests/api/test_export.py` (create; move existing export tests here if they live elsewhere)

**Interfaces:**
- Changes: `Chosen` gains `status: Literal["accepted", "rejected", "unchecked"]` (the API's own value; a missing curation is `unchecked`), `engine: str | None` (engine of the chosen prediction; `None` for a curated structure), `note: str | None`, `edited: bool` (curation has its own SMILES or molfile).
- Changes: `choose(..., include_rejected: bool)`; rejected segments are kept only when `include_rejected` and they have a structure.
- Produces: `GET /papers/{id}/export?format=json|csv|sdf&status=accepted|all`. Default `status`: `accepted` for SDF, `all` for JSON and CSV. `accepted` keeps only `status == "accepted"`; `all` keeps everything with a structure, rejected included.
- CSV header (exact order): `segment_id,page,idx,smiles,status,engine,note,edited,source`. SDF data fields: `MARCUS_STATUS`, `MARCUS_ENGINE`, `MARCUS_NOTE`, `MARCUS_EDITED`, plus the existing ones. JSON objects gain the four keys. Notes in CSV pass through `csv_cell` (formula-injection guard stays). In SDF every `\r\n`, `\r` and `\n` in a note becomes one space (a note may hold a blank line or `$$$$` on its own line, which would end the record).

- [ ] **Step 1: Write the failing tests:** `test_csv_header_exact`, `test_sdf_default_only_accepted`, `test_json_default_all_includes_rejected`, `test_status_accepted_filter_json`, `test_status_value_is_unchecked_not_to_review`, `test_note_formula_guarded_in_csv` (`"=HYPERLINK(...)"` → starts with `'`), `test_sdf_note_newlines_folded` (note `"a\n\n$$$$\nb"` → field `"a  $$$$ b"`, each line break one space, and RDKit reads back the same number of records), `test_edited_flag`.
- [ ] **Step 2: Run** `uv run pytest tests/api/test_export.py -q`, expect FAIL.
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run `uv run pytest tests/api -q`, expect PASS**
- [ ] **Step 5: Commit** `feat(v2): export carries status, engine, note and edited`

### Task F0-8: Retry one failed page

**Files:**
- Modify: `backend-v2/src/marcus/core/pipeline.py` (`retry_page`), `backend-v2/src/marcus/api/routes/papers.py`
- Modify: `backend-v2/tests/api/test_ownership.py` (`ROUTES` gains `("POST", "/api/v2/papers/{p}/pages/0/retry", None)`)
- Test: `backend-v2/tests/core/test_pipeline.py`, `backend-v2/tests/api/test_page_retry.py`

**Interfaces:**
- Produces: `retry_page(session: Session, paper_id: uuid.UUID, page: int) -> Step` (`page` 0-based): locks the paper; requires that the page's newest `render_page` or `segment_page` step is `failed` and no step of the paper for that page is pending, queued or running; requires fewer than `MANUAL_PAGE_RETRIES = 2` earlier manual retries of that page (count `render_page` steps for the page beyond the first); creates a new `render_page` step for the page (its normal successors follow); sets a `done`/`failed` paper back to `processing`. Raises `RetryNotAllowed(reason: Literal["not_failed", "busy", "limit"])`.
- Produces: `POST /api/v2/papers/{paper_id}/pages/{n}/retry` → 202 `StepAccepted`; `RetryNotAllowed` → 409 with `detail` one of `"Page has not failed"`, `"Page is still running"`, `"No retries left for this page"`; other owner → 404; `n` outside `0..pages-1` (or `pages` null) → 404.

- [ ] **Step 1: Write the failing tests:** `test_retry_failed_page_creates_render_step_and_reopens_paper`, `test_retry_first_page_0_allowed`, `test_retry_page_not_failed_409`, `test_retry_busy_409`, `test_third_retry_409_limit`, `test_retry_other_owner_404`, `test_retry_page_equal_to_pages_404`, `test_retry_negative_page_404`, and `test_retried_page_success_finishes_paper_done` (drive the planner through render → segment → ocsr done; paper ends `done`).
- [ ] **Step 2: Run** `uv run pytest tests/core/test_pipeline.py tests/api/test_page_retry.py -q`, expect FAIL.
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run `uv run pytest tests/core tests/api -q`, expect PASS**
- [ ] **Step 5: Commit** `feat(v2): retry one failed page`

---

## Group F — the web UI (`frontend-v2/`)

Commands (run in `frontend-v2/`): `npm run lint`, `npm run typecheck`, `npm test -- --run <path>` (Vitest; never reads `dist/`), `npm run build` (client build, Ketcher build, SSR build, prerender, `check-dist`; fails on any check), `npm run e2e -- <spec>` (Playwright, `baseURL` from `MARCUS_UI_URL`, default `http://localhost:18091`). Every F task ends with `npm run lint && npm run typecheck && npm test -- --run` green.

**How e2e runs before F15 (ruling for review I1):** from F1b on, e2e runs against a local nginx (`npm run serve:local`: the `nginxinc/nginx-unprivileged:1.27-alpine` image on the host network, port 18091) that serves `dist/` with the same `deploy/ui-locations.conf` that F15 ships, and proxies `/api/v2/` to the fake stack at `127.0.0.1:18090`. Why: the real headers and CSPs apply from the first e2e test, not only in F15. The fake stack for frontend e2e (from `backend-v2/`):

```bash
docker compose -p marcus-v2 -f docker-compose.yml -f docker-compose.fake.yml \
  -f ../frontend-v2/e2e/compose.e2e.yml up -d --build
```

`e2e/compose.e2e.yml` sets on `api`: `MARCUS_RATE_LIMIT_IP_PER_MIN: "300"` (the production default, so e2e proves the UI stays under it; the fake file sets 6000) and `MARCUS_COOKIE_SECURE: "false"` only if F1b shows that Playwright's Chromium drops the Secure owner cookie on `http://localhost` (record which). The fake stack OCSRs only engine `fake` (`docker-compose.fake.yml:17-26`), so every e2e test that needs structures uploads through `page.request.post("/api/v2/papers", {multipart: {file, engine: "fake", ocsr: "auto"}})` (`page.request` shares the browser context's cookies, so the paper belongs to the page's owner) and then opens `/app/papers/<id>`. The fake segmenter gives 2 segments per page, so `synth_015.pdf` (5 pages) gives 10 structures (the spec's "15-structure paper" is the real segmenter's count; the keyboard test drives the 10). Uploads made through the UI in e2e use `ocsr=off` (no OCSR step, so nothing waits on an absent engine worker).

**Design rule for every UI task:** before editing UI files, load the `impeccable:impeccable` skill (it carries the craft floor) and keep to the contract in spec §7 and the board `frontend-v2/reference/field-sheet-board.png`. The tool is Operate mode; the landing is Persuade mode.

### Task F1: Project skeleton, tokens, fonts, contract, prerender, test tooling

**Files:**
- Create: `frontend-v2/package.json`, `vite.config.ts`, `tsconfig.json`, `eslint.config.js`, `playwright.config.ts`, `index.html`, `src/main.tsx`, `src/entry-server.tsx`, `src/App.tsx`, `src/AppRoutes.tsx`, `src/styles/tokens.css`, `src/styles/base.css`, `src/styles/fonts.css`, `public/fonts/gmarket-mark.woff2`, `public/theme.js`, `public/sample/synth_015.pdf`, `scripts/prerender.mjs`, `scripts/check-dist.mjs`, `src/test/setup.ts`, `.gitignore` (`node_modules/`, `dist/`, `dist-ssr/`, `test-results/`, `playwright-report/`)
- Modify: `frontend-v2/PRODUCT.md` line 38 (CSP list: drop Crossref and DataCite, spec §8/§9.6)
- Test: `frontend-v2/src/App.test.tsx`, `frontend-v2/src/theme.test.ts`; `scripts/check-dist.mjs` (runs inside `npm run build`)

**Interfaces:**
- Ruling (prerender, review I6): one route tree, declarative. `AppRoutes` is a `<Routes>` element used by both sides: `<BrowserRouter><App/></BrowserRouter>` in `main.tsx`, `<StaticRouter location={url}><App/></StaticRouter>` (from `react-router-dom/server`) in `entry-server.tsx`. No data router, no loaders (server state is TanStack Query), so nothing needs hydration data and no inline `<script>` is emitted. Why: a data-router pair (`createStaticHandler` + `StaticRouterProvider`) adds an inline hydration script by default and a second route definition to keep in sync.
- Produces: routes in `AppRoutes`: `/` Landing, `/about`, `/privacy`, `/disclaimer`, `/app` ToolHome, `/app/papers/:id` Workspace, `/app/images/:id` ImageResult, `*` NotFound. Landing, About, Privacy, Disclaimer, NotFound are imported eagerly (they are hydrated); everything under `/app` is `React.lazy` (keeps the landing bundle small). Page components are placeholders here; later tasks fill them.
- Produces: `npm run build` = `vite build && vite build -c vite.ketcher.config.ts && vite build --ssr src/entry-server.tsx --outDir dist-ssr && node scripts/prerender.mjs && node scripts/check-dist.mjs` (`vite.ketcher.config.ts` arrives in F1b; until then the second command is absent). `entry-server.tsx` exports `render(url: string): string` (`renderToString`). `prerender.mjs` reads the built `dist/index.html` as the template (it keeps the hashed asset links), replaces the `<!--app-->` placeholder inside `<div id="root"><!--app--></div>` with `render(url)` for `/`, `/about`, `/privacy`, `/disclaimer` → `dist/index.html`, `dist/about/index.html`, `dist/privacy/index.html`, `dist/disclaimer/index.html`; renders `*` (NotFound) → `dist/404.html`; and writes the template with an empty root (contract comment kept) → `dist/app/index.html`, the shell nginx falls back to for every `/app/…` path.
- Produces: `main.tsx` uses `hydrateRoot` when `#root` has element children, else `createRoot`. Components touch `window`, `document`, `localStorage` and `matchMedia` only in effects or event handlers, never during render.
- Produces: `public/theme.js` (loaded with a blocking `<script src="/theme.js">` in `<head>`, before the CSS): reads `localStorage["marcus-theme"]` in try/catch and sets `data-theme` on `<html>` when it is `light` or `dark`. Why: no light flash on pre-rendered pages for a visitor who chose dark; inline scripts are not allowed.
- Produces: `check-dist.mjs` fails the build unless: `dist/index.html` and `dist/app/index.html` contain `6b4eb402`; `dist/index.html` contains "Every molecule has a source."; `dist/about/index.html`, `dist/privacy/index.html`, `dist/disclaimer/index.html`, `dist/404.html` exist; no HTML file under `dist/` (outside `dist/ketcher/`) contains ` style=` or a `<script` without `src=`; `dist/app/index.html` has an empty `#root`.
- Produces: CSS custom properties in `tokens.css` named `--paper --surface --sunken --ink --text-2 --muted --line --green --accepted --to-check --rejected --failed-bg --failed-ink` plus `--font-head --font-text --font-mono --font-mark`; dark values under `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {…} }` and `:root[data-theme="dark"] {…}`.
- Fonts: `@fontsource/bricolage-grotesque`, `@fontsource/hanken-grotesk`, `@fontsource/jetbrains-mono`, only the weights the board uses (read them from `field-sheet-board.html`; at most two per family, latin subset only), `font-display: swap`. Gmarket Sans: `pyftsubset GmarketSansLight.otf --text="MARCUS" --flavor=woff2 --output-file=public/fonts/gmarket-mark.woff2` (fonttools via `uvx --from fonttools[woff] pyftsubset`); the landing preloads only this file and the one heading weight of its `h1`.
- ESLint: `react/no-danger: error`, `no-restricted-properties` for `innerHTML`/`outerHTML`/`insertAdjacentHTML`, and `react/forbid-dom-props: ["error", {forbid: ["style"]}]` scoped to `src/pages/**`, `src/ui/**` (the pre-rendered set; see Global Constraints).

- [ ] **Step 1: Write the failing tests:** `App.test.tsx` renders `/app` (awaiting the lazy route) and finds the text "MARCUS"; renders `/` and finds the headline; `theme.test.ts` (jsdom) runs `public/theme.js` with `localStorage` throwing and with `"dark"` stored → no throw / `data-theme="dark"`.
- [ ] **Step 2: Run `npm test -- --run`, expect FAIL**
- [ ] **Step 3: Implement** the skeleton; the contract comment from spec §7 as the first child of `<body>`; fix `PRODUCT.md` line 38.
- [ ] **Step 4: Run `npm run build && npm test -- --run && npm run lint && npm run typecheck`, expect PASS** (the build runs `check-dist`)
- [ ] **Step 5: Commit** `feat(frontend-v2): skeleton, tokens, fonts, design contract, prerender`

### Task F1b: Serving, both CSPs and the Ketcher frame, proven early

Ruling (review I7): nginx, the two CSPs and Ketcher are proven here, before anything is built on them. Ketcher version, checked on npm and in the package files on 2026-11-17: `ketcher-react`, `ketcher-standalone`, `ketcher-core` **3.18.0** (latest, published 2026-09-02). `ketcher-core` 3.18.0 ships a pre-compiled schema validator (`dist/domain/serializers/ket/compiledSchema.js`, needs only `ajv/dist/runtime/ucs2length`) and no `new Function`/`eval` was found in the three packages' bundles, so no `'unsafe-eval'` should be needed (the old need came from run-time ajv compilation, epam/ketcher issue 853). `WebAssembly.instantiate` needs `'wasm-unsafe-eval'`. The default `ketcher-standalone` entry inlines the WebAssembly as base64 and starts its worker from a `Blob` (needs `worker-src blob:`); the `ketcher-standalone/dist/binaryWasm` entry loads `indigoWorker-*.js` with `new URL(…, import.meta.url)` and a separate `indigo-ketcher-1.46.0.wasm`. Use `ketcher-standalone/dist/binaryWasm`. A dedicated worker runs under the CSP of its own script response, so the worker and the `.wasm` must be served from `/ketcher/…` (the Ketcher CSP), not from the app's `/assets/`: hence a separate Vite build with `base: "/ketcher/"` and `outDir: "dist/ketcher"`.

**Files:**
- Create: `frontend-v2/deploy/ui-locations.conf` (included inside the `server {}` of both the dev and the production nginx), `frontend-v2/deploy/dev-nginx.conf`, `frontend-v2/scripts/serve-local.sh`, `frontend-v2/e2e/compose.e2e.yml`, `frontend-v2/e2e/helpers.ts`, `frontend-v2/e2e/csp.spec.ts`
- Create: `frontend-v2/vite.ketcher.config.ts` (root `ketcher/`, `base: "/ketcher/"`, `build.outDir: "../dist/ketcher"`, `build.emptyOutDir: true` (it owns only `dist/ketcher/`; it runs after the main build, which empties `dist/`), `define: {"process.env": {}}` as Ketcher needs), `frontend-v2/ketcher/index.html`, `frontend-v2/ketcher/main.tsx` (bare Ketcher: `<Editor staticResourcesUrl="/ketcher/" structServiceProvider={new StandaloneStructServiceProvider()} />` from `ketcher-react` and `ketcher-standalone/dist/binaryWasm`, `ketcher-react/dist/index.css`; on init posts `{type: "marcus:ready"}` to `window.parent` with target origin `window.location.origin`, and keeps the instance on `window.ketcher`)
- Modify: `frontend-v2/package.json` (`ketcher-react`, `ketcher-standalone`, `ketcher-core` at exactly `"3.18.0"`, no caret; `build` gains `vite build -c vite.ketcher.config.ts` after the client build; scripts `serve:local`, `serve:stop`, `e2e`), `frontend-v2/playwright.config.ts`

**Interfaces:**
- `ui-locations.conf` (exact behaviour):
  - `include /etc/nginx/mime.types;` (the v2 `nginx.conf` has only `default_type application/octet-stream`; module scripts and `application/wasm` need real types). `root /usr/share/nginx/marcus-ui;`.
  - Each static location sets its **full** header set (an `add_header` inside a location drops every inherited one, including the server-level map-based headers of `nginx.conf:76-80`): `Content-Security-Policy` (app or Ketcher, exact from Global Constraints), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` (app) or `SAMEORIGIN` (Ketcher), `Referrer-Policy: strict-origin-when-cross-origin`, `Cross-Origin-Resource-Policy: same-origin`, `Permissions-Policy: camera=(), microphone=(), geolocation=()`, all with `always`.
  - `location /assets/` (hashed): `Cache-Control: public, max-age=31536000, immutable`, app headers. `location /ketcher/`: `try_files $uri /ketcher/index.html`, Ketcher headers; `/ketcher/assets/` immutable cache. `location /app`: `try_files $uri /app/index.html`, `Cache-Control: no-cache`, app headers. `location /`: `try_files $uri $uri/index.html =404`, `error_page 404 /404.html`, `Cache-Control: no-cache` for HTML, app headers.
  - `gzip on; gzip_types text/css application/javascript text/javascript image/svg+xml application/json application/wasm; gzip_min_length 1024;` in the static locations only (not on `/api/v2/`).
- `dev-nginx.conf`: a full `nginx.conf` (pid and temp paths in `/tmp`, as the production one) with one server on `listen 127.0.0.1:18091`, `include /etc/nginx/marcus/ui-locations.conf;`, and `location /api/v2/ { proxy_pass http://127.0.0.1:18090; proxy_buffering off; proxy_read_timeout 1h; proxy_http_version 1.1; proxy_set_header Connection ""; }`.
- `serve-local.sh`: `docker run -d --rm --name marcus-ui-dev --network host -v "$PWD/dist:/usr/share/nginx/marcus-ui:ro" -v "$PWD/deploy/dev-nginx.conf:/etc/nginx/nginx.conf:ro" -v "$PWD/deploy/ui-locations.conf:/etc/nginx/marcus/ui-locations.conf:ro" nginxinc/nginx-unprivileged:1.27-alpine`; `serve:stop` removes it. Binds only the host's loopback port 18091.
- `e2e/helpers.ts`: `collectCspViolations(page): () => Promise<string[]>` (an `addInitScript` listener for `securitypolicyviolation` in every frame, reads `window.__cspViolations`), `uploadPaperViaApi(page, file: string, opts?: {engine?: "fake", ocsr?: "auto" | "off"}): Promise<string>` (returns the paper id), `expectNoA11yViolations(page, opts?: {theme?: "light" | "dark"})` (axe; fails on serious/critical).
- `playwright.config.ts`: `use.baseURL = process.env.MARCUS_UI_URL ?? "http://localhost:18091"`, Chromium only, `workers: 1` (one shared stack), no `webServer` (the stack and `serve:local` are started by hand, as written in the Group F header).

- [ ] **Step 1: Write the failing tests** in `e2e/csp.spec.ts`: `/`, `/about`, `/app`, `/app/papers/x` answer 200 with the exact app CSP and `X-Frame-Options: DENY`; `/app/papers/x` serves `dist/app/index.html`; `/nope` answers 404 with the NotFound page; `/ketcher/` has the exact Ketcher CSP and `X-Frame-Options: SAMEORIGIN`; one `/assets/*.js` has a JavaScript content type, the immutable cache header and `Content-Encoding: gzip` when asked; the `.wasm` under `/ketcher/` is `application/wasm`; **frame proof**: open `/app`, insert an `<iframe src="/ketcher/">` with `page.evaluate`, wait for `marcus:ready` from that frame, call `window.ketcher.setMolecule("c1ccccc1O")` then `getSmiles()` in the frame → a non-empty SMILES containing `O`; zero CSP violations in the page and the frame; **cookie proof**: `uploadPaperViaApi(page, synth_015.pdf, {ocsr: "off"})`, then the page's own `fetch("/api/v2/papers")` lists that paper (the owner cookie survived on `http://localhost`).
- [ ] **Step 2: Run** (fake stack up as in the Group F header, then) `npm run build && npm run serve:local && npm run e2e -- csp`, expect FAIL.
- [ ] **Step 3: Implement.** If Ketcher meets a CSP violation, the only allowed changes are: the `ketcher-standalone` entry (default vs `dist/binaryWasm`), the Vite settings of the Ketcher build, and removing or adding `data:`/`blob:` sources in the Ketcher CSP. If it still needs `'unsafe-eval'` or `'unsafe-inline'` scripts, **stop and ask the owner** (do not add them). Remove sources the Ketcher CSP turns out not to need and write the final policy into Global Constraints. If the cookie proof fails with the Secure cookie, set `MARCUS_COOKIE_SECURE: "false"` in `e2e/compose.e2e.yml` and note it there.
- [ ] **Step 4: Run** `npm run build && npm run serve:local && npm run e2e -- csp`, expect PASS. Record the Ketcher bundle sizes (`du -sh dist/ketcher`) in the task report.
- [ ] **Step 5: Commit** `feat(frontend-v2): local serving with both CSPs; Ketcher 3.18.0 frame proven`

### Task F2: API layer and live updates

**Files:**
- Create: `frontend-v2/src/api/types.ts`, `src/api/client.ts`, `src/api/queries.ts`, `src/api/useLiveEvents.ts`, `src/api/curation.ts`, `src/api/depictionKey.ts`, `src/api/reasons.ts`
- Test: `frontend-v2/src/api/client.test.ts`, `src/api/useLiveEvents.test.ts`, `src/api/curation.test.ts`, `src/api/depictionKey.test.ts`

**Interfaces:**
- Produces: `types.ts` mirrors `backend-v2/src/marcus/api/schemas.py` after F0 (`PaperSummary` with counts and `title`, `PaperDetail`, `SegmentOut` (`page` 0-based; `bbox: [x0, y0, x1, y1]` in 300 DPI page pixels), `PredictionOut`, `CurationOut`, `CurationIn` (all four keys required: `{status, smiles: string | null, molfile: string | null, note: string | null}`), `StepOut` (with `engine`), `QueueOut`, `QueuePaper`, `ImageJobOut`, `ImageJobSummary`, `ImageStepOut`, `StepAccepted`, `BulkCurationItem`) plus `type Engine = "decimer" | "decimer-hand" | "molnextr" | "molscribe"`, `type CurationStatus = "unchecked" | "accepted" | "rejected"`, `type ErrorClass = "timeout" | "worker_lost" | "bad_input" | "engine_error"`, `type UploadPaperReply = {paper_id: string, status: string}`, `type UploadImageReply = {image_job_id: string, status: string}`, `type DepictReply = {format: "svg" | "png", data: string}`, and `type DoclingDoc = {body?: {children: {$ref: string}[]}, texts: {self_ref: string, text: string, label: string}[], groups?: {self_ref: string, children: {$ref: string}[]}[]}` (only the fields read; `GET /papers/{id}/text` returns Docling's `export_to_dict()`, `workers/pdfsafe_child.py:76`).
- Produces: `api` object in `client.ts`: `listPapers()`, `getPaper(id)`, `getSteps(id)`, `uploadPaper(file, {engine, ocsr}): Promise<UploadPaperReply>`, `deletePaper(id)`, `putCuration(segmentId, body: CurationIn): Promise<CurationOut>`, `putBulkCuration(paperId, items: BulkCurationItem[])`, `runPrediction(segmentId, engine)`, `retryPage(paperId, page0: number)`, `getQueue()`, `getText(id): Promise<DoclingDoc>`, `exportUrl(id, format, status)`, `pageImageUrl(id, page0)`, `segmentImageUrl(id)`, `depictionUrl(segmentId, key: string, engine?: Engine)` (`/api/v2/segments/<id>/depiction?v=<key>[&engine=<e>]`), `depict(smiles, opts?: {highlight?: string}): Promise<DepictReply>`, `compare(smilesA, smilesB)` (the route takes exactly `smiles_a`, `smiles_b`, `api/routes/tools.py:53-55`), `mcs(molfiles)`, `smilesToMolfile(smiles)`, `uploadImage(file, engine): Promise<UploadImageReply>`, `listImages()`, `getImageJob(id)`, `runImagePrediction(id, engine)`, `imageUrl(id)`. Helper `svgBlobUrl(reply: DepictReply): string` builds a `Blob` (`image/svg+xml`) and returns `URL.createObjectURL` (callers revoke it on unmount). All `fetch` with `credentials: "same-origin"`, base `/api/v2`.
- Errors: every non-2xx throws `ApiError{status: number, detail: string, retryAfter?: number}`. `detail` is: the JSON `detail` when it is a string; the `msg` fields joined with "; " when it is a list (FastAPI 422, `api/security.py:168-171`); otherwise (nginx's own 413/502/504 HTML, or no body) a fixed text by status: 413 "This file is larger than 20 MB.", 502/503/504 "The server is busy, try again in a moment.", else "Something went wrong (HTTP <status>)." `retryAfter` from the `Retry-After` header.
- Produces: `curationBody(current: CurationOut | null, change: CurationChange): CurationIn` in `curation.ts`, with `CurationChange = {status?: CurationStatus; note?: string | null; structure?: {smiles: string | null; molfile: string | null}}`. Every key absent from `change` is copied from `current` (`current` null → `status: "unchecked"`, others null). `structure` sets both `smiles` and `molfile` together.
- Produces: `useSaveCuration(paperId)` in `queries.ts`: `save(segmentId, change)` reads the segment's current curation from the `["paper", paperId]` query cache, PUTs `curationBody(current, change)`, and writes the returned `CurationOut` into that cache, so the next change builds on it; saves for the same segment are chained one after another. It is the only way the UI writes a single curation.
- Produces: `depictionKey(segment: SegmentOut): string` = FNV-1a 32-bit hex of `JSON.stringify([segment.curation?.smiles ?? null, segment.curation?.molfile ?? null, validPredictionIds])` where `validPredictionIds` are the ids of the valid predictions in API order. It changes whenever any input of the server's choice changes (F0-4).
- Produces: `reasonText(errorClass: string | null): string` in `reasons.ts` with the exact texts of Global Constraints.
- Produces: `useLiveEvents(kind: "paper" | "image", id: string, onEvent: () => void): {mode: "connecting" | "live" | "polling" | "ended", reconnect: () => void}`. Wire format (`api/routes/events.py:1-26`): a named `event: snapshot` first, unnamed `data:` frames for worker events, a named `event: end` (then the server closes), a named `event: error` (Redis down; sent with `retry: 15000`, then the server closes), `: ping` comments every 15 s (never delivered to JS), and a close without `end` after 30 min (the browser reconnects by itself). Rules:
  - `addEventListener("snapshot")` and `onmessage` → `onEvent()`, mode `live`. `addEventListener("end")` → `onEvent()`, `close()`, all timers stop, mode `ended`.
  - `"error"` (the native error and the named `error` frame both arrive here) → mode `polling`, call `onEvent()` every 2000 ms. If `readyState === EventSource.CLOSED` (an HTTP error such as the 429 "Too many open event streams", 4 per owner) → open a new `EventSource` after 5, 10, 20, 40, then every 60 s; if `CONNECTING`, the browser reconnects itself. `"open"` → polling stops, back-off resets.
  - No inactivity timeout (pings are invisible to JS).
  - A tab hidden for more than 60 s closes its stream and stops polling; when it is shown again it reopens and calls `onEvent()` once. (One HTTP/1.1 connection per open stream: hidden tabs must not hold them.)
  - `reconnect()` opens a new stream when mode is `ended` (used after `runPrediction`, `runImagePrediction` and `retryPage`, which can reopen a finished paper or image job).
  - Polling while the stream is down refetches only the paper and its steps (2 requests per 2 s); the queue query has its own `refetchInterval` of 10 s while the paper is `checking` or `processing`.

- [ ] **Step 1: Write the failing tests:** `client.test.ts` (fetch mocked): 404 → `ApiError(404)`; 429 with `Retry-After: 7` → `retryAfter === 7`; a 422 with a list `detail` → the joined `msg` texts; a 413 HTML body → "This file is larger than 20 MB."; `uploadPaper` sends `multipart/form-data` with `engine` and `ocsr` and returns `paper_id`; `compare("CCO", "CCN")` posts `{smiles_a: "CCO", smiles_b: "CCN"}`; `depictionUrl("s1", "abc", "molnextr")` → `/api/v2/segments/s1/depiction?v=abc&engine=molnextr`. `curation.test.ts`: status change keeps `smiles`, `molfile` and `note`; a structure change keeps `note` and `status`; `current` null → `unchecked` with nulls. `depictionKey.test.ts`: same inputs → same key; a changed curated SMILES, a new valid prediction, or a prediction becoming invalid → different key. `useLiveEvents.test.ts` (a fake `EventSource` that dispatches **named** events through `addEventListener` and has `readyState`, fake timers): a `snapshot` and a `message` each call `onEvent`; an `error` with `CONNECTING` switches to `polling` and calls `onEvent` every 2000 ms, then `open` stops polling; an `error` with `CLOSED` opens a new `EventSource` after 5000 ms; an `end` sets `ended`, closes and stops timers; a listener only on `onmessage` would miss `end` (assert `end` is handled via `addEventListener`); `reconnect()` after `end` opens a new stream; hidden for 61 s closes, visible reopens.
- [ ] **Step 2: Run** `npm test -- --run src/api`, expect FAIL.
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run `npm test -- --run src/api`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): typed API client, curation bodies and live updates`

### Task F3: Field Sheet parts and app frame

**Files:**
- Create: `frontend-v2/src/ui/SpecimenLabel.tsx`, `src/ui/Stamp.tsx`, `src/ui/StateBadge.tsx`, `src/ui/Structure.tsx`, `src/ui/Smiles.tsx`, `src/ui/Button.tsx`, `src/ui/Kbd.tsx`, `src/ui/Toasts.tsx`, `src/ui/ThemeToggle.tsx`, `src/ui/Header.tsx`, `src/ui/Footer.tsx`, `src/ui/DesktopOnly.tsx`, `src/ui/ui.css`
- Test: `frontend-v2/src/ui/ui.test.tsx`

**Interfaces:**
- Produces: `<SpecimenLabel title: string rows?: [string, ReactNode][] tone?: "ink" | "failed">` (dark header bar, ruled rows, as on the board); `<Stamp state: "accepted" | "rejected" size?: "sm" | "lg" animate?: boolean>` (round, rotated −12°, word inside; with `animate` it scales from 1.4 and settles in 160 ms; no motion when `prefers-reduced-motion: reduce`); `<StateBadge state: "accepted" | "rejected" | "to-check" | "failed" | "reading" | "not-read">` with the exact words from Global Constraints ("Reading…", "Not read yet"); `<Structure src: string alt: string>` (`<img>`, `loading="lazy"`, `decoding="async"`, a quiet placeholder until loaded, "No drawing" on error); `<Smiles value: string>` (mono, wraps, a Copy button that writes to the clipboard and shows a toast "SMILES copied"); `useToast(): (msg: string, tone?: "info" | "error") => void`; `<ThemeToggle>` cycles system → light → dark, stores the choice in `localStorage` key `marcus-theme` (try/catch), sets `data-theme` on `<html>`, reads the stored value only in an effect; `<DesktopOnly>` renders children at ≥ 1024 px and the exact note below that, measured in an effect (it renders children during server rendering; it is used only under `/app`).
- None of these components uses a `style` prop (Global Constraints); sizes and rotations come from classes.
- Header: logo (`public/logo.png` from `maintenance/site/maintenance/logo.png`), "MARCUS" in Gmarket Sans, nav (How it works, Cite, GitHub `https://github.com/Kohulan/MARCUS`), primary "Open the tool". Footer links: About, Privacy, Disclaimer, DECIMER `https://decimer.ai`, COCONUT `https://coconut.naturalproducts.net`, GitHub.

- [ ] **Step 1: Write the failing tests:** each state badge shows its exact word; `Stamp` has `aria-label` "Accepted"/"Rejected"; `Stamp animate` adds class `stamp--landing` only when reduced motion is off (mock `matchMedia`); `Structure` renders an `<img>` with the given `src` and never an `<svg>` element; `Smiles` copy calls `navigator.clipboard.writeText` with the exact value; `ThemeToggle` survives a throwing `localStorage`; `DesktopOnly` at 800 px shows the exact note; `renderToString(<Header/>)`, `<Footer/>`, `<Stamp/>`, `<SpecimenLabel/>`, `<ThemeToggle/>` with `window` access spied → no access during render and no ` style=` in the output.
- [ ] **Step 2: Run** `npm test -- --run src/ui`, expect FAIL.
- [ ] **Step 3: Implement** (load `impeccable:impeccable` first)
- [ ] **Step 4: Run `npm test -- --run src/ui`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): Field Sheet parts and app frame`

### Task F4: Landing, about, privacy, disclaimer, Matomo

**Files:**
- Create: `frontend-v2/src/pages/Landing.tsx`, `src/pages/landing.css`, `src/pages/About.tsx`, `src/pages/Privacy.tsx`, `src/pages/Disclaimer.tsx`, `src/pages/NotFound.tsx`, `src/assets/caffeine.svg` (static, our own drawing; used via `<img>`), `src/assets/example-crop.png` (copy of `backend-v2/tests/fixtures/ocsr/synth015_p0_i0.png`), `src/assets/example-structure.svg`, `public/matomo.js`, `src/analytics.ts`
- Modify: `frontend-v2/index.html` (`<script src="/matomo.js" defer>`), `src/App.tsx` (page views)
- Test: `frontend-v2/src/pages/pages.test.tsx`, `frontend-v2/e2e/landing.spec.ts`

**Interfaces:**
- Landing (Persuade mode) follows the contract's FIRST VIEWPORT: headline "Every molecule has a source." (80 px, `--green`), one paragraph, "Upload a PDF" → `/app` with the file picker opened, "Try a sample paper" → `/app?sample=1`, the taped specimen sheet with caffeine, an ACCEPTED stamp and its label table, then three numbered features (Three engines · Curate fast · Into COCONUT).
- Ruling (honest example, review I12): the caffeine sheet is the contract's illustration and is labelled as one: its label header reads "Example specimen" and its rows are Organism: *Coffea arabica* · Engine: DECIMER · SMILES `Cn1cnc2c1c(=O)n(C)c(=O)n2C` (no invented "Sample paper, page 2" source). Below the fold, the spec's "real example (page crop → structure → SMILES)" is a strip with real pipeline output: `example-crop.png` (the crop the DECIMER segmenter cut from page 1 of `synth_015.pdf`), → `example-structure.svg`, → the SMILES v1's DECIMER read from that crop (`backend-v2/tests/fixtures/v1_decimer.json`, `crops[0].v1_smiles`), captioned "From our synthetic sample paper, page 1: the crop MARCUS found, the structure DECIMER read, its SMILES." `example-structure.svg` is drawn once with the fake stack's real tools worker (`POST /api/v2/tools/depict` with that SMILES, `data` saved as the file) and committed. Then the pipeline (segment → recognise → curate → COCONUT), the engines (DECIMER default, MolNexTR, MolScribe, DECIMER hand-drawn), "How to cite" with the exact citation and a Copy button, links to DECIMER and COCONUT. No invented numbers (PRODUCT.md evidence rule).
- About, Privacy, Disclaimer: content carried over from `frontend/src/views/AboutPage.vue`, `PrivacyPolicyPage.vue`, `DisclaimerPage.vue` as plain JSX text, updated for v2: files deleted after 30 days, no login, Matomo as the only tracker, upload limit 20 MB. Remove anything about OpenAI. NotFound: "This page does not exist." and a link to `/`.
- `public/matomo.js`: the v1 tracker code from `frontend/public/index.html` lines 125–138 (site id 7, `https://matomo.nfdi4chem.de/`). `analytics.ts`: `trackPage(template: string)` pushes `setCustomUrl` with the route template (`/`, `/about`, `/app`, `/app/papers/:id`, `/app/images/:id`) and `trackPageView`; `App.tsx` calls it on route change (no-op when `_paq` is absent).

- [ ] **Step 1: Write the failing tests:** `pages.test.tsx`: Landing has one `h1` with the exact headline, both buttons, the exact citation text, the "Example specimen" label, the example strip caption and the recorded SMILES, and no element with `dangerouslySetInnerHTML`; Privacy contains "30 days" and "Matomo" and not "OpenAI"; `trackPage` on `/app/papers/123` pushes `/app/papers/:id`. `e2e/landing.spec.ts` (on `serve:local`): the pre-rendered `/` has the headline in the HTML before JS runs (`page.route` blocks `*.js`); axe finds 0 serious/critical on `/`, `/about`, `/privacy`, `/disclaimer` in light and dark (`expectNoA11yViolations`); no CSP violation on these pages; with `localStorage["marcus-theme"] = "dark"` and a light system, the first paint of `/` already has `data-theme="dark"`; at 390 px width there is no horizontal scroll. The spec is tagged `@mocked` (it needs no API).
- [ ] **Step 2: Run** `npm run build && npm run serve:local && npm run e2e -- landing`, expect FAIL.
- [ ] **Step 3: Implement** (load `impeccable:impeccable`, Persuade mode)
- [ ] **Step 4: Run `npm run build && npm test -- --run src/pages && npm run e2e -- landing`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): landing and info pages`

### Task F5: Tool home

**Files:**
- Create: `frontend-v2/src/tool/ToolHome.tsx`, `src/tool/DropZone.tsx`, `src/tool/PapersList.tsx`, `src/tool/tool.css`
- Test: `frontend-v2/src/tool/ToolHome.test.tsx`

**Interfaces:**
- Consumes: `api.uploadPaper`, `api.uploadImage`, `api.listPapers`, `api.listImages`, `api.deletePaper`, `useToast`, `DesktopOnly`.
- DropZone: one drop area and a file button; accepts `application/pdf`, `image/png`, `image/jpeg`, `image/tiff` (the backend's types); rejects files over 20 MB in the browser with "This file is larger than 20 MB." Engine select (the four engines, DECIMER default) and a "Find structures automatically" switch (`ocsr` `auto` on, `off` off; PDF only; `aria-label` "Find structures automatically"). A PDF goes to `/app/papers/<paper_id>` after upload; an image to `/app/images/<image_job_id>`. `?sample=1` (or the sample button) fetches `/sample/synth_015.pdf` and uploads it as a `File` named `Sample paper (synthetic).pdf`; when the papers list already holds a paper with that display name, the button reads "Open the sample paper" and opens it instead of uploading again (each upload takes one of the 3 active-paper slots). A 429 shows its detail text and "Try again in N s" when `retryAfter` is set.
- PapersList: rows with title (or display name), status word, the counts from F0-1 ("15 structures · 9 accepted · 2 rejected · 4 to check · 1 failed page"), "Deleted in N days" from `expires_at` (N rounded up; "Deleted today" when < 1), Open, Delete (confirm dialog "Delete this paper and its results? This cannot be undone."). Image jobs listed below in their own short list. Empty state: one line and the sample button.

- [ ] **Step 1: Write the failing tests:** 21 MB file → message and no request; PDF upload calls `uploadPaper` with `{engine: "decimer", ocsr: "auto"}` and navigates to `/app/papers/<paper_id>`; the switch off sends `ocsr: "off"`; PNG and TIFF go to `uploadImage` and navigate to `/app/images/<image_job_id>`; a WebP file is refused in the browser; `?sample=1` fetches `/sample/synth_015.pdf` and uploads a file named `Sample paper (synthetic).pdf`; with that paper already listed the button opens it without an upload; list row shows "Deleted in 3 days" for `expires_at` 2.2 days ahead; delete asks first and calls `deletePaper` only after confirm; 429 with `retryAfter 7` shows "Try again in 7 s"; a display name and a title `<img src=x onerror=alert(1)>` render as text (no `img` element created).
- [ ] **Step 2: Run** `npm test -- --run src/tool`, expect FAIL.
- [ ] **Step 3: Implement** (load `impeccable:impeccable`, Operate mode)
- [ ] **Step 4: Run `npm test -- --run src/tool`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): tool home with upload and papers list`

### Task F6: Paper workspace frame and status bar

**Files:**
- Create: `frontend-v2/src/workspace/Workspace.tsx`, `src/workspace/StatusBar.tsx`, `src/workspace/ExportMenu.tsx`, `src/workspace/GonePage.tsx`, `src/workspace/useWorkspace.ts`, `src/workspace/pageFailures.ts`, `src/workspace/workspace.css`
- Test: `frontend-v2/src/workspace/Workspace.test.tsx`, `src/workspace/pageFailures.test.ts`

**Interfaces:**
- Consumes: `api.getPaper`, `api.getSteps`, `api.getQueue`, `api.retryPage`, `api.exportUrl`, `useLiveEvents("paper", id, …)`, `reasonText`.
- Produces: `pageFailures(steps: StepOut[]): {page0: number, errorClass: string | null, retrying: boolean}[]` — the same rule as the server's `failed_pages` (F0-1): per page, the newest `render_page` or `segment_page` step (by `created_at`); the page is listed when that step is `failed`, or with `retrying: true` when a newer step of the page is active after a failed one; a page whose newest step is `done` is not listed.
- Produces: `useWorkspace(id): {paper, segments, steps, failedPages, checkFailure: string | null, selection, setSelection, view: "review" | "paper", setView, live: ReturnType<typeof useLiveEvents>}`; `view` and the focused segment live in the URL (`?view=paper&s=<segmentId>`) so reload and back work.
- Header row: title (or display name), DOI as a link `https://doi.org/${encodeURI(doi)}` (text only, `rel="noopener noreferrer"`), counts, view toggle Review | Paper, Export menu (JSON, CSV, SDF; "Accepted only" / "All" for each; plain links to `exportUrl`), "Send N to COCONUT" (opens F13; disabled with a reason when N = 0).
- StatusBar: paper state word; while waiting "About N min in the queue" from this paper's `QueueOut.papers[].estimate_s` (rounded up to whole minutes; "Less than a minute" under 60 s); per-step progress "Pages read 6/8 · Structures read 12/15"; each entry of `failedPages`: "Page <page0 + 1> could not be read: <reasonText(errorClass)>" + "Retry page" (`retryPage(id, page0)`, then `live.reconnect()`; 409 detail shown as a toast); with `retrying` the line reads "Page <n>: retrying…" and has no button. A failed `check_pdf` step (`checkFailure`) shows one line instead of the progress: "This PDF could not be read: <reason>", where `bad_input` reads "it is encrypted, damaged or has more than 100 pages" and other classes use `reasonText`. Live mode `"polling"` shows "Live updates paused, checking every 2 s".
- A 404 from `getPaper` renders `GonePage`: "This paper is not here any more." + "It was deleted, it expired after 30 days, or it was opened in another browser." + link to `/app`.

- [ ] **Step 1: Write the failing tests:** a failed `segment_page` step on API page 4 with `error_class: "timeout"` → "Page 5 could not be read: it took too long" and a Retry button that calls `retryPage(id, 4)` and then `reconnect`; `worker_lost` → "the worker stopped while reading it"; an unknown class → "an unknown error"; `pageFailures`: failed then a newer `render_page` done → not listed; failed then a newer step running → `retrying` and no button; 409 → toast with the detail; a failed `check_pdf` with `bad_input` → "This PDF could not be read: it is encrypted, damaged or has more than 100 pages"; queue `estimate_s 130` → "About 3 min in the queue"; 404 → GonePage text; export menu builds `/api/v2/papers/<id>/export?format=sdf&status=accepted`; `?view=paper` opens the paper view; live mode `"polling"` shows the note; a title `<img src=x onerror=window.__xss=1>` renders as text and `window.__xss` stays undefined.
- [ ] **Step 2: Run** `npm test -- --run src/workspace`, expect FAIL.
- [ ] **Step 3: Implement** (load `impeccable:impeccable`)
- [ ] **Step 4: Run `npm test -- --run src/workspace`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): paper workspace frame and status bar`

### Task F7: Review grid

**Files:**
- Create: `frontend-v2/src/workspace/ReviewGrid.tsx`, `src/workspace/StructureCard.tsx`, `src/workspace/GridFilters.tsx`, `src/workspace/BulkBar.tsx`, `src/workspace/cardState.ts`
- Modify: `frontend-v2/src/workspace/Workspace.tsx` (mounts the grid)
- Test: `frontend-v2/src/workspace/ReviewGrid.test.tsx`

**Interfaces:**
- Consumes: `useWorkspace`, `api.putBulkCuration`, `api.runPrediction`, `api.depictionUrl`, `depictionKey`, `api.segmentImageUrl`, `Stamp`, `SpecimenLabel`, `StateBadge`, `Structure`.
- Produces: `cardState(segment, steps, paper): "accepted" | "rejected" | "to-check" | "reading" | "failed" | "not-read"`: curation `accepted`/`rejected` win; else with no valid prediction: `reading` when an `ocsr` step for the segment is pending, queued or running; `failed` when its newest `ocsr` step failed; `not-read` when it has no `ocsr` step (paper uploaded with `ocsr=off`); else `to-check`.
- StructureCard: depiction (`depictionUrl(segment.id, depictionKey(segment))`), a small crop toggle, label header "No. <n> · page <page + 1>" where n is the 1-based position in (page, idx) order, engine and validity row, the SMILES (`<Smiles>`, as text), the note's first line if any (as text), state (stamp for accepted/rejected, badge otherwise). Two engines that differ (two valid predictions with different SMILES) show "Engines differ". Actions by state: `failed` → "Try another engine" (a menu of the other three engines → `runPrediction`, then `live.reconnect()`), with the reason from `reasonText`; `not-read` → "Read with <paper engine name>" (and the same engine menu).
- Filters (exact labels): All · To check · Accepted · Rejected · Failed, each with its count ("Reading…" and "Not read yet" cards count under To check). Selection: click a checkbox, Shift-click a range, "Select all shown"; BulkBar: "Accept N", "Reject N", "Clear" → `putBulkCuration` with items `{segment_id, status}` and **no `note` key** (F0-3 keeps notes), chunks of 500, optimistic update, rollback and toast on error; "Read N with <engine>" when selected cards are `not-read` (calls `runPrediction` at most 4 at a time). Enter or double-click on a card opens focus mode (F8). The grid lazy-loads images (`loading="lazy"`); cards are keyboard focusable in reading order.

- [ ] **Step 1: Write the failing tests:** 3 segments (accepted, rejected, none) → 1 stamp "Accepted", 1 stamp "Rejected", 1 "To check"; filter "Accepted" shows 1 card; select 2 + "Accept 2" → one `putBulkCuration` call with both ids and no `note` key; API error rolls back and toasts; a segment without prediction and a running OCSR step shows "Reading…"; a failed OCSR step shows "Failed", its reason, and "Try another engine" → `runPrediction(segId, "molnextr")`; a paper with `ocsr_mode: "off"` and no OCSR steps shows "Not read yet" and "Read with DECIMER"; a live event that adds a segment makes a new card appear without reload (invalidate → refetch); 1,200 selected → 3 calls of ≤ 500; a card's depiction `src` changes after its curated SMILES changes in the cache; a note and an (invalid) predicted SMILES `<img src=x onerror=window.__xss=1>` render as text and `window.__xss` stays undefined.
- [ ] **Step 2: Run** `npm test -- --run src/workspace`, expect FAIL.
- [ ] **Step 3: Implement** (load `impeccable:impeccable`)
- [ ] **Step 4: Run `npm test -- --run src/workspace`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): review grid with bulk review`

### Task F8: Focus mode and keyboard review

**Files:**
- Create: `frontend-v2/src/workspace/FocusMode.tsx`, `src/workspace/useReviewKeys.ts`, `src/workspace/KeyHelp.tsx`
- Modify: `frontend-v2/src/workspace/Workspace.tsx` (opens focus mode)
- Test: `frontend-v2/src/workspace/FocusMode.test.tsx`, `frontend-v2/e2e/keyboard-review.spec.ts`

**Interfaces:**
- Consumes: `useSaveCuration`, `useWorkspace`, `Stamp animate`, `SpecimenLabel`, `Smiles`, page image with the box from `bbox` (`[x0, y0, x1, y1]` in page pixels, scaled to the shown image size).
- Produces: `useReviewKeys(handlers: {accept, reject, edit, compare, prev, next, close, help}): void` — keys exactly as in Global Constraints; ignored while focus is in an input, textarea, select or the Ketcher iframe, and when Ctrl, Meta or Alt is held. F10 and F11 fill `compare` and `edit`; until then they are no-ops.
- FocusMode: one structure large; its crop; its page image scaled with the `bbox` drawn as a box; SMILES; engine predictions listed; a note field (saved with the next accept or reject, and on blur with `save(segId, {note})`); actions with their keys shown (`<Kbd>`). Accept/Reject call `save(segId, {status, note})` (curated `smiles`/`molfile` are kept by `curationBody`), land the stamp (signature interaction), then move to the next "To check" structure after 250 ms (no wait with reduced motion). Esc returns to the grid with the same card focused. `?` toggles KeyHelp (a dialog with focus trap; Esc closes it).

- [ ] **Step 1: Write the failing tests:** pressing `a` calls `putCuration(segId, {status: "accepted", smiles: null, molfile: null, note})` for an unedited structure and shows the Accepted stamp; **accept after edit keeps the edited SMILES and molfile**: with curation `{status: "unchecked", smiles: "CCO", molfile: "<m>", note: "n"}`, `a` sends `{status: "accepted", smiles: "CCO", molfile: "<m>", note: "n"}`; `r` rejects with the same rule; blur of the note field saves the note and keeps status and structure; `ArrowRight` moves to the next structure; typing `a` in the note field does not accept; `Escape` closes and the grid card has focus; `?` opens a dialog named "Keys". `e2e/keyboard-review.spec.ts` (on `serve:local`): `uploadPaperViaApi(page, synth_015.pdf, {engine: "fake"})`, open `/app/papers/<id>`, wait until the status word is "Done" and 10 cards show, open the first with Enter, review every structure with only `a`/`r`/arrows, then the filter "To check" shows 0; axe 0 serious/critical in focus mode; no CSP violation.
- [ ] **Step 2: Run** `npm test -- --run src/workspace`, expect FAIL.
- [ ] **Step 3: Implement** (load `impeccable:impeccable`)
- [ ] **Step 4: Run `npm test -- --run src/workspace && npm run build && npm run e2e -- keyboard-review`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): focus mode and keyboard review`

### Task F9: Paper view

**Files:**
- Create: `frontend-v2/src/workspace/PaperView.tsx`, `src/workspace/PageWithBoxes.tsx`, `src/workspace/TextColumn.tsx`, `src/workspace/doclingText.ts`
- Modify: `frontend-v2/src/workspace/Workspace.tsx` (mounts the view)
- Test: `frontend-v2/src/workspace/PaperView.test.tsx`, `src/workspace/doclingText.test.ts`

**Interfaces:**
- Consumes: `api.pageImageUrl`, `api.getText`, `useWorkspace` selection, `StructureCard` (list mode).
- Produces: `doclingBlocks(doc: DoclingDoc): {kind: "heading" | "paragraph", text: string}[]`: walks `body.children` in order, resolving `#/texts/<i>` to `texts[i]` and recursing into `#/groups/<i>`; skips tables and pictures; `label` `title` or `section_header` → `heading`, every other text label → `paragraph`; without `body`, uses `texts` in array order. Plain strings only; rendered as React text nodes.
- Three columns as on the board: pages (each page image `pageImageUrl(id, page0)` with `loading="lazy"`, a box per segment from `bbox` (`[x0, y0, x1, y1]` in 300 DPI page pixels, scaled by the shown width over the image's natural width), numbered "No. n", colour by state, dashed for "To check") | text from the paper (`getText` fetched only while the Paper view is open: the file can be large; "Download text" saves the blocks joined by blank lines as a `.txt` via a `Blob` link) with the annotation area "Annotations (compounds, organisms, methods) come in a later version." | the structure list. Clicking a box selects and scrolls to its card; selecting a card scrolls its page into view and outlines its box. Boxes are buttons with `aria-label` "Structure n on page p" (p = page0 + 1).
- Text that is missing (docling step failed or not finished) shows "The text of this paper is not ready" or "The text could not be read: <reasonText(errorClass)>".

- [ ] **Step 1: Write the failing tests:** a text item `<img src=x onerror=window.__xss=1>` renders as visible text and `window.__xss` stays undefined; `doclingBlocks` keeps `body` order through a group and maps `section_header` to a heading; 2 segments on API page 1 → 2 box buttons labelled "Structure 1 on page 2", "Structure 2 on page 2"; a `bbox` `[100, 200, 300, 400]` on a 2480 px image shown 620 px wide → a box at left 25, top 50, width 50, height 50 (CSS px); clicking box 2 selects card 2; `getText` is not called in the Review view; "Download text" creates a `blob:` link with the file name `<display name>.txt`; a failed docling step shows the failure line.
- [ ] **Step 2: Run** `npm test -- --run src/workspace`, expect FAIL.
- [ ] **Step 3: Implement** (load `impeccable:impeccable`)
- [ ] **Step 4: Run `npm test -- --run src/workspace`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): paper view with boxes and text`

### Task F10: Compare engines

**Files:**
- Create: `frontend-v2/src/workspace/Compare.tsx`, `src/workspace/useCompare.ts`
- Modify: `frontend-v2/src/workspace/FocusMode.tsx` (`c` opens Compare), `src/workspace/StructureCard.tsx` (menu entry)
- Test: `frontend-v2/src/workspace/Compare.test.tsx`

**Interfaces:**
- Consumes: `api.runPrediction` (segments) or `api.runImagePrediction` (images), `api.compare`, `api.mcs`, `api.smilesToMolfile`, `api.depict` (MCS highlight, and every image-job drawing), `api.depictionUrl` (segment drawings per engine, free of the tools bucket), `useLiveEvents().reconnect`.
- Produces: `<Compare target: {kind: "segment" | "image", id: string} predictions: PredictionOut[] steps: {engine: string | null, status: string, error_class: string | null}[] onPick: (p: PredictionOut) => void>` — "Run all engines" starts a prediction for each engine that has neither a prediction nor an active step, then calls `reconnect()`; engines with an active step show "Reading…", a failed one "Failed: <reasonText>"; results appear live. A table of engines with their depictions side by side, pairwise Tanimoto from `api.compare(a, b)` once per unordered pair of distinct SMILES (4 engines → at most 6 calls; shown with two decimals), and "Show common part" draws each with the MCS highlighted (`smilesToMolfile` per SMILES → `mcs` → `depict` with `highlight`).
- Tool budget: one full Compare with "Show common part" is about 15 calls of the 60/min per-owner tools bucket. Every tools result is a TanStack Query entry keyed by its inputs (`["compare", a, b]` with `a < b`, `["molfile", smiles]`, `["mcs", ...sortedMolfiles]`, `["depict", smiles, highlight]`, `staleTime: Infinity`), so reopening Compare costs nothing. A 429 shows "Too many requests, try again in N s".
- "Use this one" calls `onPick`. For segments the caller runs `save(segId, {status: "accepted", structure: {smiles: p.smiles, molfile: p.molfile ?? null}})`: the note is kept by `curationBody`, and the old curated molfile is replaced, not left describing another structure.

- [ ] **Step 1: Write the failing tests:** with one prediction, "Run all engines" calls `runPrediction` for the three other engines and then `reconnect`; an engine with an active step is not requested again; Tanimoto 0.8734 shows "0.87"; three distinct SMILES → exactly 3 `compare` calls, and reopening makes 0 more; "Use this one" on MolNexTR with curation `{note: "keep me", smiles: "CCO", molfile: "<m>"}` sends `{status: "accepted", smiles: <molnextr smiles>, molfile: <molnextr molfile or null>, note: "keep me"}`; a failed engine shows "Failed: the engine failed"; a 429 from the tools bucket shows "Too many requests, try again in N s".
- [ ] **Step 2: Run** `npm test -- --run src/workspace`, expect FAIL.
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run `npm test -- --run src/workspace`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): compare engines`

### Task F11: Structure editor (Ketcher in an isolated frame)

**Files:**
- Modify: `frontend-v2/ketcher/main.tsx` (from the F1b proof to the full bridge), `frontend-v2/src/workspace/FocusMode.tsx` (`e` opens the editor), `src/workspace/StructureCard.tsx` (menu entry)
- Create: `frontend-v2/src/workspace/Editor.tsx`, `frontend-v2/src/workspace/editorBridge.ts`
- Test: `frontend-v2/src/workspace/editorBridge.test.ts`, `frontend-v2/src/workspace/Editor.test.tsx`, `frontend-v2/e2e/editor.spec.ts`

**Interfaces:**
- Produces: message protocol (both directions, `postMessage` with target origin `window.location.origin` only; every handler checks `event.origin === window.location.origin` **and** `event.source` is the expected window — the frame is same-origin, so the source check is what tells the app from the frame): parent → frame `{type: "marcus:load", molfile: string | null, smiles: string | null}`; frame → parent `{type: "marcus:ready"}`, `{type: "marcus:save", molfile: string, smiles: string}`, `{type: "marcus:cancel"}`. Messages of any other shape are ignored.
- Produces: `<Editor initial: {smiles: string | null, molfile: string | null} onSave: (s: {smiles: string, molfile: string | null}) => Promise<void> onClose: () => void>`: a dialog with a "SMILES" text field (the spec's "edit SMILES or molfile": saving from the field sends `{smiles: <field>, molfile: null}`) above the iframe `src="/ketcher/"`, `sandbox="allow-scripts allow-same-origin"` (kept for the separate CSP; it gives no isolation from a same-origin parent). The editor does not write the curation itself: the caller decides. For segments the caller passes `onSave = s => save(segId, {status: current.status === "unchecked" ? "accepted" : current.status, structure: s})` (note kept by `curationBody`); the card's depiction updates through its new `depictionKey`, with no blob. F14 passes a local-only `onSave`.
- Save failure: when `onSave` rejects (for example a 422 "SMILES could not be parsed" or "molfile could not be parsed" from `CurationIn`), the dialog stays open and shows "Save failed: <ApiError.detail>".
- Ketcher loads only when the dialog opens (the iframe is created then). Ketcher packages stay at `3.18.0`.

- [ ] **Step 1: Write the failing tests:** `editorBridge.test.ts`: a message from another origin is ignored; a same-origin message from a window other than the frame is ignored; a message with an unknown `type` is ignored; `marcus:save` from the frame resolves with its molfile and SMILES. `Editor.test.tsx`: **save in the editor keeps the note** (segment caller with curation `{status: "accepted", note: "n"}` → `putCuration` body `{status: "accepted", smiles, molfile, note: "n"}`); an `unchecked` structure becomes `accepted` on save; the SMILES field sends `molfile: null`; a rejected `onSave` with detail "SMILES could not be parsed" keeps the dialog open and shows "Save failed: SMILES could not be parsed". `e2e/editor.spec.ts` (on `serve:local`): API upload with `engine: "fake"`, open a structure, press `e`, wait for `marcus:ready`, save without change, the curation is stored (API check: `smiles` and `molfile` set, note unchanged), the card's depiction URL changed; the `/ketcher/` response carries the Ketcher CSP; no CSP violation in the page or the frame.
- [ ] **Step 2: Run** `npm test -- --run src/workspace`, expect FAIL.
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run `npm test -- --run src/workspace && npm run build && npm run e2e -- editor`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): structure editor in an isolated frame`

### Task F12: Lookups and downloads

**Files:**
- Create: `frontend-v2/src/lookup/pubchem.ts`, `src/lookup/coconutDoi.ts`, `src/workspace/StructureActions.tsx`
- Modify: `frontend-v2/src/workspace/Workspace.tsx` (DOI count in the header), `src/workspace/FocusMode.tsx`, `src/workspace/StructureCard.tsx` (actions menu)
- Test: `frontend-v2/src/lookup/lookup.test.ts`

**Interfaces:**
- Produces: `pubchemBySmiles(smiles: string): Promise<{cid: number, name: string | null, url: string} | null>` — `GET https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/cids/JSON?smiles=<encoded>` then the title from `/rest/pug/compound/cid/<cid>/property/Title/JSON`; `url = https://pubchem.ncbi.nlm.nih.gov/compound/<cid>`; any error → `null`. Same lookup as v1 `frontend/src/services/publicationService.js` `searchPubChemBySmiles`.
- Produces: `coconutCountForDoi(doi: string): Promise<{count: number, more: boolean, url: string} | null>` — v1's request (`frontend/src/components/pdf-viewer/PdfViewerObject.vue:207-300`): `POST https://coconut.naturalproducts.net/api/search` with JSON `{type: "tags", tagType: "citations", query: <doi>, limit: 20, sort: "desc", page: 1, offset: 0}`, no login. Results from `data.data.data`, else `data.data`, else `data.results`, else the array itself; count = unique `id` (else `coconut_id`, else `identifier`). `more` is true when the page is full (20): the header then says "20 or more". `url = https://coconut.naturalproducts.net/search?q=<encoded doi>&tagType=citations&type=tags&activeTab=citations`. Any error → `null`.
- StructureActions (in focus mode and card menu): Copy SMILES, Copy molfile and Download molfile (`<name>-<n>.mol`; the curated molfile, else the chosen prediction's molfile, else `api.smilesToMolfile`), Download image (the depiction SVG fetched from `depictionUrl` and saved as `<name>-<n>.svg` via a blob link), Look up in PubChem (shows CID, name, link), Edit (F11), Compare (F10). The workspace header shows "N already in COCONUT for this DOI" (a link to `url`) when the count is known.

- [ ] **Step 1: Write the failing tests** (fetch mocked): SMILES with `#` and `+` is URL-encoded; PubChem 404 → `null`; CID 2519 → url `https://pubchem.ncbi.nlm.nih.gov/compound/2519`; the COCONUT request body is exactly v1's; counts from each of the three response shapes; 20 results → `more: true`; network error → `null` and no crash; Download molfile prefers the curated molfile.
- [ ] **Step 2: Run** `npm test -- --run src/lookup`, expect FAIL.
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run `npm test -- --run src/lookup src/workspace`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): PubChem and COCONUT lookups, downloads`

### Task F13: COCONUT batch submit

**Files:**
- Create: `frontend-v2/src/coconut/coconutApi.ts`, `src/coconut/types.ts`, `src/coconut/CoconutLogin.tsx`, `src/coconut/SubmitForm.tsx`, `src/coconut/SubmitResults.tsx`
- Modify: `frontend-v2/src/workspace/Workspace.tsx` ("Send N to COCONUT" opens the form)
- Test: `frontend-v2/src/coconut/coconut.test.tsx`

**Interfaces:**
- Produces in `types.ts` (from v1 `frontend/src/services/coconutService.js:123-150`):
  ```ts
  type Organism = {name: string; parts: string[]; locations: {name: string; ecosystems: string[]}[]};
  type ReportCreate = {
    title: string; evidence: string; comment: string;
    suggested_changes: {new_molecule_data: {
      canonical_smiles: string; reference_id: string; name: string; link: string;
      structural_comments: string;
      references: {doi: string; organisms: Organism[]}[];
    }};
  };
  ```
  The request body is `{mutate: items.map(i => ({operation: "create", attributes: i, relations: []}))}`.
- Produces: `coconutLogin(email, password): Promise<string>` — `POST https://coconut.naturalproducts.net/api/auth/login` with `{email, password}`, token from `access_token`; kept in `sessionStorage` key `marcus-coconut-token` (try/catch; memory fallback), never sent to `/api/v2`.
- Produces: `submitReports(token, items: {segmentId: string, report: ReportCreate}[], onProgress): Promise<SubmitResult[]>` — `POST https://coconut.naturalproducts.net/api/reports/mutate` with `Authorization: Bearer <token>`. Sends chunks of `COCONUT_CHUNK = 50`; when the server answers 413, or 422 about the list size, halves the chunk and retries that chunk once. A network error or timeout in the middle of a chunk is **not** retried: every item of that chunk gets `{ok: false, error: "Unknown: check COCONUT before sending again"}`, and sending stops. `SubmitResult = {segmentId, ok: true, reportId} | {segmentId, ok: false, error: string}`.
- Duplicate guard: segment ids that got `ok: true` are stored in `localStorage` key `marcus-coconut-sent:<paperId>` (try/catch); the form marks them "Already sent" and leaves them out unless the curator ticks "Send again", which asks for confirmation. The Submit button is disabled while a submit runs.
- SubmitForm: paper-level fields filled once (title, DOI as reference, organism(s) with parts, location, ecosystems, evidence, comment) inherited by every accepted structure; per structure the curator can change name, comment, structural comments, organism (expandable row). Submit shows progress "Sent 50 of 120" and then SubmitResults (created report id or the error per structure).

- [ ] **Step 1: Write the failing tests** (fetch mocked): login posts to `/api/auth/login` and stores `access_token`; one item's body equals the v1 shape exactly (including `title` and `relations: []`); 120 items → 3 requests (50, 50, 20); a 413 on chunk 2 → chunk 2 resent as 25 + 25; a network error on chunk 2 → its 50 items "Unknown: check COCONUT before sending again", chunk 3 not sent; already-sent ids are left out until "Send again" is confirmed; a double click sends once; per-structure override wins over the paper-level organism; the token never appears in any request to `/api/v2`; a failed item shows its error and others show their report id.
- [ ] **Step 2: Run** `npm test -- --run src/coconut`, expect FAIL.
- [ ] **Step 3: Implement** (load `impeccable:impeccable` for the form)
- [ ] **Step 4: Run `npm test -- --run src/coconut`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): COCONUT batch submit`

Note: the first real submit with a test structure is done by the owner before switch day (spec §6). Do not submit to the real COCONUT in any test.

### Task F14: Single image result

**Files:**
- Create: `frontend-v2/src/images/ImageResult.tsx`
- Test: `frontend-v2/src/images/ImageResult.test.tsx`

**Interfaces:**
- Consumes: `api.getImageJob`, `api.imageUrl`, `useLiveEvents("image", id, …)`, `Smiles`, `Compare` (kind `image`, `steps` from `ImageJobOut.steps`), `Editor` (with a local `onSave`: the edited structure is shown and copyable in this page only, not stored; the page says "Edited here, not saved"), `StructureActions`, `reasonText`.
- Layout: the uploaded image | the structure (depiction from `api.depict(smiles)` via `svgBlobUrl`, revoked on unmount) with its specimen label (engine, valid, time) | actions. States: waiting (queue estimate), reading, done, failed with `reasonText(job.error_class)` (never `job.error`); 404 → the GonePage text with "image" instead of "paper". Running another engine from Compare calls `reconnect()`.

- [ ] **Step 1: Write the failing tests:** done job shows its SMILES and engine; failed job with `error_class: "engine_error"` shows "the engine failed" and not the raw `error` text; a live event refetches; an editor save changes the shown SMILES and makes no API write; 404 shows "This image is not here any more."
- [ ] **Step 2: Run** `npm test -- --run src/images`, expect FAIL.
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run `npm test -- --run src/images`, expect PASS**
- [ ] **Step 5: Commit** `feat(frontend-v2): single image result`

### Task F15: Serve it from the v2 stack, end-to-end gates

**Files:**
- Create: `frontend-v2/Dockerfile` (stage 1 `node:22-alpine` runs `npm ci && npm run build`; stage 2 `nginxinc/nginx-unprivileged:1.27-alpine` with `dist/` at `/usr/share/nginx/marcus-ui` and `deploy/ui-locations.conf` at `/etc/nginx/marcus/ui-locations.conf`), `frontend-v2/.dockerignore` (`node_modules`, `dist`, `dist-ssr`, `test-results`, `playwright-report`, `.impeccable`)
- Ruling (build context, review I7): the context is `frontend-v2/` (a few MB), not the repo root (5.4 GB, no root `.dockerignore`). Why: the image needs only the frontend and its own conf file; `nginx.conf` stays a bind mount as today.
- Modify: `backend-v2/docker/nginx.conf` (inside `server {}`: `include /etc/nginx/marcus/ui-locations.conf;` replaces `location / { return 404; }`; the SSE and `/api/v2/` locations stay unchanged and keep the server-level map-based headers)
- Modify: `backend-v2/docker-compose.yml` (nginx service: `build: {context: ../frontend-v2, dockerfile: Dockerfile}`, `image: marcus-v2-nginx:local`; the conf bind mount stays)
- Modify: `judges/security/v2/test_stored_xss_frontend.py` (remove the `needs_frontend` skip; new flow below)
- Create: `frontend-v2/e2e/live.spec.ts`, `frontend-v2/e2e/big-paper.spec.ts`, `frontend-v2/e2e/a11y.spec.ts`, `frontend-v2/e2e/fixtures/` (API JSON for the mocked a11y run), `backend-v2/tests/e2e/seed_big_paper.py`, `frontend-v2/scripts/lighthouse-gate.mjs`, `.github/workflows/frontend-v2.yml`
- Test: `backend-v2/tests/deploy/test_compose_config.py`

**Interfaces:**
- e2e runs against the stack's own nginx (`MARCUS_UI_URL=http://localhost:18090`), so the shipped image and headers are tested. The stack is brought up as in the Group F header (with `e2e/compose.e2e.yml`).
- `seed_big_paper.py`: runs **inside the api container** (the api image has the app and Pillow but not `tests/`, and Postgres is not published): `docker compose -p marcus-v2 exec -T api python - < tests/e2e/seed_big_paper.py`. With `marcus.core.db.sync_session()` it creates a browser owner (`new_token`, `hash_token`), a `done` paper with 10 pages, writes 10 page PNGs (Pillow, white 1240 × 1754) at `storage.page_image_path`, 200 segments (20 per page, `bbox` on a grid) with their crop PNGs at `storage.segment_crop_path`, an `unchecked` curation each, and one valid `decimer` prediction each with **200 distinct SMILES** (for k in 1..200: `"C" * k` for k ≤ 100, `"C" * (k - 100) + "O"` above). Prints one JSON line `{"paper_id": …, "token": …}`. Never run against anything but the local `marcus-v2` project.
- `big-paper.spec.ts`: adds the cookie `marcus_owner=<token>` (Path `/api/v2`, host `localhost`) to the context, opens `/app/papers/<id>`, scrolls the grid to the end, and asserts: no response with status 429 in the network log; every card's depiction and crop `<img>` has `naturalWidth > 0` within 120 s (the tools worker draws 200 misses). Runs at the default `MARCUS_RATE_LIMIT_IP_PER_MIN=300` (from `compose.e2e.yml`).
- `live.spec.ts`: `uploadPaperViaApi(page, synth_015.pdf, {engine: "fake"})`, open `/app/papers/<id>` at once; the first structure card appears while the status word is still "Processing", without a reload; the page never makes a 2 s polling request while the stream is open.
- `a11y.spec.ts` (tagged `@mocked`): with `page.route("**/api/v2/**")` serving `e2e/fixtures/*.json` (and an SSE body `event: end\ndata: {"status":"done"}\n\n`), axe 0 serious/critical in light and dark on: tool home, review grid, focus mode, paper view, compare, editor dialog (frame excluded), COCONUT form, image result. It needs no stack, so CI can run it.
- `.github/workflows/frontend-v2.yml`: on pull requests and pushes that touch `frontend-v2/**`: `npm ci`, lint, typecheck, `npm test -- --run`, `npm run build`, `npx playwright install --with-deps chromium`, `npx vite preview --port 4173 &`, `MARCUS_UI_URL=http://localhost:4173 npm run e2e -- --grep @mocked`. This is the spec's "axe in CI"; the stack-based e2e stays the local gate (it needs the docker stack).
- `lighthouse-gate.mjs`: runs `npx lighthouse http://localhost:18090/ --preset=desktop --only-categories=performance --output=json --quiet --chrome-flags=--headless`, prints the score, exits 1 below 90.
- Judge `test_stored_xss_frontend.py` flow: `page.goto(target.frontend_url() + "/app")`; turn off "Find structures automatically" (so the paper finishes without an OCSR engine); set the file input; wait for the URL `/app/papers/<id>` (this also proves the owner cookie worked); open `?view=paper`; wait until the payload text (`onerror=window.<XSS_MARKER>`) is visible as text in the text column and the display name is visible in the header; then assert `window.<XSS_MARKER>` is not `true`. Run with `MARCUS_FRONTEND_URL=http://localhost:18090`.

- [ ] **Step 1: Write the failing tests:** `test_compose_config.py`: the nginx service builds `../frontend-v2` with `Dockerfile`; `nginx.conf` includes `/etc/nginx/marcus/ui-locations.conf` and no longer has `return 404` for `/`; `ui-locations.conf` holds the exact app CSP and the exact Ketcher CSP (as in Global Constraints), `include /etc/nginx/mime.types`, `gzip on`, and every location with an `add_header` sets all six headers. The e2e specs above; `csp.spec.ts` (from F1b) runs again against port 18090.
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run** `cd backend-v2 && uv run pytest tests/deploy -q`; the stack up with `compose.e2e.yml`; `cd frontend-v2 && MARCUS_UI_URL=http://localhost:18090 npm run e2e && node scripts/lighthouse-gate.mjs`; then the stack up again **without** `compose.e2e.yml` (the judge expects the fake file's limits and the Secure cookie) and `cd judges && MARCUS_BACKEND_URL=http://localhost:18090 MARCUS_FRONTEND_URL=http://localhost:18090 MARCUS_FS_PROBE=docker:marcus-v2-api-1 uv run pytest security/v2 -v`. Expected: all PASS; Lighthouse ≥ 90; the judge reports 20 passed, 0 skipped.
- [ ] **Step 5: Commit** `feat(v2): nginx serves the new UI with strict CSP; e2e gates`

### Task F16: Finish review and DESIGN.md

**Files:**
- Create: `frontend-v2/.impeccable/review/desktop.png` (1440 wide: landing first viewport), `frontend-v2/.impeccable/review/tool.png` (1440 wide: review grid), `frontend-v2/.impeccable/review/focus.png`, `frontend-v2/.impeccable/review/paper.png`, `frontend-v2/.impeccable/review/mobile.png` (390 wide: landing), each also in dark mode with a `-dark` suffix
- Create: `frontend-v2/DESIGN.md` and its sidecar (written by the documenter)

**Interfaces:**
- This task runs the closing steps of `impeccable:impeccable` new-work: run its detector once on the changed targets (`node <skill-base-dir>/scripts/detect.mjs --json`), fix what is mechanical, then spawn `impeccable:impeccable-finish-reviewer` fresh with the request, the contract (spec §7), the screenshots above, the detector findings, and the board PNG as the critique reference (code-led: no comp). Apply its material fixes in one batch, recapture, and get its verdict (two rounds at most). Then spawn `impeccable:impeccable-documenter` to write `DESIGN.md` from the built world.

- [ ] **Step 1: Capture the screenshots** with Playwright against the stack's nginx (`MARCUS_UI_URL=http://localhost:18090`, fake stack up).
- [ ] **Step 2: Run the detector and the finish reviewer**; record the verdict table in the task report.
- [ ] **Step 3: Apply the fixes**, rerun `npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run e2e`, expect PASS.
- [ ] **Step 4: Run the documenter**; `frontend-v2/DESIGN.md` exists.
- [ ] **Step 5: Commit** `docs(frontend-v2): finish review fixes and DESIGN.md`

---

## Order and gates

1. F0-1 … F0-8 (backend) first, after the backend final whole-branch review has fixed the API (spec §11).
2. F1, then F1b (serving, CSPs, Ketcher proof). Nothing after F1b starts until `csp.spec.ts` passes; if Ketcher needs `'unsafe-eval'`, stop and ask the owner.
3. F2 … F14 in order (each needs the parts before it). Their e2e specs run on `serve:local` with the fake stack.
4. F15 needs F0 and F1–F14.
5. F16 last. Then the final whole-branch review of the frontend work.
6. Switch day stays the owner's choice.
