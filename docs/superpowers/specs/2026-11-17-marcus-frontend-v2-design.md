# MARCUS frontend v2: design

Date: 2026-11-17. Status: approved by the owner on 2026-11-17. §7 updated the same day
for the owner's "Survey Sheet" direction (light only, glass buttons, Geist fonts).
Owner decisions are marked **(decided)**. My own calls are marked **(call)** and can be changed.
Backend this builds on: `docs/superpowers/specs/2026-11-16-marcus-v2-backend-design.md` (v2 API, section 9).

## 1. Intent

MARCUS turns a journal article (PDF) into checked chemical structures for COCONUT.
The v2 backend is built (`backend-v2/`). The current Vue UI (`frontend/`) talks only to
v1 and is not ported **(decided, backend spec §1)**. The switch to v2 waits for this UI.

Why a redesign **(decided: all four count)**:

1. Curators must check structures faster (fewer clicks, keyboard).
2. The look and layout are dated and confusing for new users.
3. v2 brings live results, a queue, per-page status, a papers list and curation; the UI must use them.
4. MARCUS is a showcase: a first-time visitor from a talk or the paper must understand and trust it fast.

## 2. Users

- **Casual visitor (decided):** comes from the paper or a talk, tries one paper, maybe exports.
- **Power curator (decided):** processes many papers, reviews hundreds of structures,
  submits accepted ones to COCONUT.
- **Desktop only (decided):** curation is a desktop job. On a phone the landing page
  works and the tool shows a short note "MARCUS is made for a desktop screen".
  Minimum supported width for the tool **(call)**: 1024 px.
- Script users use the API with keys; no web page for them **(decided)**.

## 3. Goals, non-goals, anti-goals

Goals, each with a check:

| Goal | Check |
|---|---|
| Fast review | A curator can accept/reject a structure with one key in focus mode; bulk-accept from the grid. Playwright test drives a 15-structure paper to all-reviewed with the keyboard only. |
| Live | The first structure card appears without a reload while the paper is still running (SSE; polling fallback). e2e test against the v2 fake stack. |
| Honest status | Each failed page shows its reason (from `GET /papers/{id}/steps` `error_class`); queue position shown while waiting. |
| Safe | The v2 security judge's stored-XSS browser test (`judges/security/v2`, marked `needs_frontend`) passes; no `dangerouslySetInnerHTML` with server or user data; strict CSP. |
| Accessible | WCAG 2.2 AA on landing and tool (axe in CI: 0 serious/critical), full keyboard path, visible focus. |
| Fast landing | Landing pre-rendered HTML; Lighthouse performance >= 90 on desktop. |

Non-goals: phone-first tool, login accounts, other languages than English, an API docs
page, annotation logic (phase E of the backend; the UI only reserves its place).

Anti-goals (a failure even if it works):

- Any feature of v1 a curator relies on is missing on switch day (see §6 checklist).
- The UI hides a failure (a failed page or engine looks like "no structures").
- Server text or SMILES/molfile reaches the DOM as HTML.
- A design that looks like a generic AI dashboard template.

## 4. Approaches (decided: A)

| | Approach | Trade-off |
|---|---|---|
| **A (picked)** | One Vite + React + TypeScript app. Landing/about/privacy pages are pre-rendered to HTML at build time; the tool is a client app. Served as static files by the v2 nginx on the same domain as `/api/v2`. | One project, one look, no new server on jarvis. Landing is static and fast. |
| B | Next.js with a Node server | Better SEO tooling, but a Node server to run and secure; little gain because the tool part is private per browser. |
| C | Astro landing + separate React tool | Fastest landing, but two projects and two styles to keep in sync. |

## 5. Structure of the site

1. **Landing** `/` (pre-rendered): what MARCUS does in one sentence, a real example
   (page crop → structure → SMILES), the pipeline (segment → recognise → curate →
   COCONUT), engines (DECIMER default, MolNexTR, MolScribe, DECIMER hand-drawn),
   "How to cite" (decided, below), links to DECIMER and COCONUT, a "Start" button to the tool.
2. **About / Privacy / Disclaimer** (pre-rendered): content carried over from v1
   (`frontend/src/views/AboutPage.vue`, `PrivacyPolicyPage.vue`, `DisclaimerPage.vue`),
   updated for v2 (30-day deletion, no login, Matomo).
3. **Tool home** `/app`: drop zone for a PDF (max 20 MB) or a single image; engine
   choice (default DECIMER) and `ocsr=auto|off`; a "Try a sample paper" button
   **(call: our own synthetic fixture `synth_015`, no licence issue)**; the list of
   this browser's papers (`GET /papers`) with status, counts and "deleted in N days"
   (`expires_at`); delete per paper.
4. **Paper workspace** `/app/papers/:id`, with a view toggle **(decided)**:
   - **Review view (default):** a grid of all structure cards (crop, depiction,
     engine, validity, curation state). Filters: all / to review / accepted / rejected /
     failed. Select many → accept or reject. Enter or click → **focus mode**: one
     structure large, its crop and its page with the box (`bbox`) beside it, SMILES,
     actions. Keys **(call)**: A accept, R reject, E edit (Ketcher), C compare engines,
     ←/→ previous/next, Esc back to grid, ? shows the key list.
   - **Paper view:** the cleaner v1 three columns: page images with boxes around each
     structure | extracted text (docling) with the annotation area | structure list
     using the same cards. Clicking a box selects the card and the other way round.
   - Both views share one status bar: paper state, queue position (`GET /queue`),
     per-step progress, failed pages with reason, retry-per-segment with another engine.
5. **Single image result** `/app/images/:id`: the image, the structure, SMILES, copy,
   edit, compare.

Annotation (local LLM, backend phase E) gets its place in the text column now with a
"coming later" state **(call)**; no OpenAI calls from the UI.

## 6. Features (v1 parity checklist plus new)

Kept from v1 **(decided)**: upload, DOI shown as a link, COCONUT DOI check (count of
molecules already in COCONUT for this DOI), engine choice incl. DECIMER hand-drawn,
depiction, SMILES copy, structure image download, Ketcher editor, compare engines
(run all engines on one segment; Tanimoto similarity; MCS highlight; pick one),
PubChem lookup of a structure, text view and download, JSON export, notifications,
footer links, Matomo. The v1 theme toggle (light/dark) is **not** kept: the owner chose
light mode only on 2026-11-17 (§7), so it is not a missing v1 feature.

New with v2: live results; queue position; per-page failures with reasons; explicit
accept / reject with note **(decided)**; edit SMILES or molfile (curation stored on the
server); bulk review; keyboard focus mode; papers list with expiry; delete paper;
CSV and SDF export (v2 `GET /papers/{id}/export`); single image OCSR (`POST /images`);
paper view with boxes on the page.

**COCONUT batch submit (decided):**
- Submits all accepted structures of a paper in one go, with the curator's own COCONUT
  login (as v1; token kept in memory or session storage, never sent to our backend **(call)**).
- Form: paper-level fields filled once (DOI = reference, organism(s) with parts,
  location, ecosystems, evidence) and inherited by every structure; per structure the
  curator can change name, comment, structural comments, organism **(decided)**.
- One `POST https://coconut.naturalproducts.net/api/reports/mutate` with one `create`
  operation per structure (the endpoint takes a list; verified in the COCONUT OpenAPI
  spec, untested with a real login). If the server limits the list, send in chunks and
  show progress. Show per-structure result (created report id or error).
- First real submit is tested once by the owner with a test structure before switch day.

v1 rough edges not carried over: dead feature links, the non-existent router link,
"max 10 MB" text (v2 limit is 20 MB), "CDK engine" tag on every structure, queue
"N/3" screen (v2 has a real queue), `v-html` injection.

## 7. Look

- **Brand (decided):** keep the MARCUS logo (navy papers + green hexagon lens) and the
  Gmarket Sans wordmark; build a fresh visual style around them. The maintenance page
  (`maintenance/site/maintenance/index.html`) is the first sketch of that direction.
- **Direction (decided 2026-11-17): "Survey Sheet".** The owner first picked "Field Sheet"
  (a remix of directions 4 "Specimen Sheet" and 5 "Clean Standard"; board copy kept for
  history in `frontend-v2/reference/field-sheet-board.html` and `.png`). On the same day
  the owner asked for a remix of Field Sheet with heronaiapp.com (screenshot
  `frontend-v2/reference/heron-hero.png`), looked at three mockups (A Survey Sheet,
  B Green Ledger, C Night Plate; canvas https://claude.ai/artifact/FJzPyqJpGLGUCMaCxQeLhs)
  and chose **A, Survey Sheet**. It **replaces Field Sheet as the visual truth**. From
  Field Sheet it keeps two parts: the specimen label table (dark header bar, ruled rows)
  and the round accepted stamp. Made with `/impeccable` (seed key 6b4eb402). The build is
  **code-led**: the board `frontend-v2/reference/survey-sheet-board.html` (a canvas
  artboard source, read as source; it uses inline styles and Google Fonts only because it
  is a mockup) and the contract below are the reference; there is no comp.
- **Owner decisions (2026-11-17), Survey Sheet:**
  1. **Drawing-sheet look (decided).** Field Sheet remixed with heronaiapp.com: a
     drawing-sheet frame (hairline borders, ruler ticks, "+" corners), UPPERCASE tight
     headlines, mono uppercase labels, numbered tags `[01]`, bbox and step readouts. The
     landing hero is a paper page with orange-marked structures.
  2. **Green leads, orange asks (decided).** Green `#1E4D33` is the primary colour
     (headings, links, nav, accept and send); accepted is `#2D7A46`. Bold orange `#FA3600`
     means "needs your eyes": found-structure markers, the main call to action, the
     "To check" state. Small orange **text** on paper uses `#B82800` (contrast); text on an
     orange fill is `#141414`.
  3. **States (decided):** Accepted = green stamp and word; To check = orange badge;
     Rejected = charcoal and a cross-out (no red); Failed = charcoal tag on a hatched
     ground; "Reading…" and "Not read yet" stay. The red (rust) and amber state colours
     are removed.
  4. **Liquid-glass pill buttons (decided).** Reference liquid-glass.glassapp.dev, made
     with CSS only (no WebGPU library): `backdrop-filter` blur + saturate, an SVG
     `feDisplacementMap` refraction filter where supported (Chromium), inset highlight
     edges; tints orange (primary), green (accept, send), clear (secondary). A solid
     fallback under `prefers-reduced-transparency: reduce` and where `backdrop-filter` is
     not supported. Text contrast is WCAG AA on every tint. The SVG filter is an inline
     `<svg>` in the DOM, mounted once, with classes only (no `style` attribute in
     pre-rendered pages); the app CSP already allows it.
  5. **Light mode only (decided).** No dark theme, no theme toggle, no theme script, no
     dark tokens.
  6. **Fonts (decided):** Geist (headings and text) and Geist Mono (labels, SMILES, keys),
     self-hosted, at most two weights each. Gmarket Sans Light stays for the wordmark
     only. Bricolage Grotesque, Hanken Grotesk and JetBrains Mono are dropped.
  7. **Minimal copy (decided):** "reduce text, do not be chatty". UI copy is short; the
     landing keeps a headline, one sentence, two buttons and three short cards; tool labels
     are terse.
  8. **Tokens (decided, light, exact):** paper `#F4F3EA`, surface `#FFFFFF`, sunken
     `#ECEBE1`, ink `#1C211D`, text-2 `#3F443D`, muted `#5E625B`, line `#B9BCB2`, hair
     `#D9DACF`, tick `#9FA398`, green `#1E4D33`, accepted `#2D7A46`, orange `#FA3600`,
     orange-ink `#B82800`, on-orange `#141414`, charcoal `#1C211D`. Line `#B9BCB2` is
     about 1.7:1 on paper, so it is for hairlines only; control borders use control-border
     `#7E8279` (3.5:1 on paper, 3.9:1 on surface, 3.3:1 on sunken) **(call)**.
- **Contract** (goes as an HTML comment, first child of `<body>` in the root layout):
  - THESIS: every structure is a marked find on its page, numbered and measured like a
    drawing sheet; no generic SaaS card dashboard.
  - OWN-WORLD: light only. Drawing-sheet paper `#F4F3EA` in a hairline frame (`#B9BCB2`)
    with ruler ticks and "+" corners; ink `#1C211D`. Green `#1E4D33` leads (headings,
    links, accept, send), `#2D7A46` accepted. Bold orange `#FA3600` only for what needs
    your eyes: found-structure markers, the main action, To check; small orange text
    `#B82800`, text on orange `#141414`. Rejected and failed are charcoal (cross-out,
    hatched ground), never red. Specimen label tables and round stamps show decisions.
    Liquid-glass pill buttons: orange, green, clear. Geist UPPERCASE tight headings and
    Geist text, Geist Mono uppercase labels and numbered tags [01], Gmarket Sans wordmark.
  - STORY: the visitor sees a paper page where MARCUS has marked every structure,
    follows a marker to its checked structure, trusts where it came from, and uploads a
    PDF.
  - FIRST VIEWPORT: the drawing-sheet hero, a paper page with orange-marked structures
    ([01] found, [02] Reading…) and bbox and step readouts; under it "Every molecule has a
    source." (UPPERCASE, green), one sentence, a CTA cell with "Upload a PDF" (orange
    glass) and "Try a sample paper" (clear glass); three numbered cards Find, Read, Curate.
  - FORM: Survey Sheet, owner remix of Field Sheet with heronaiapp.com (2026-11-17);
    seed key 6b4eb402.
  - FINISH: unreviewed and undocumented is unfinished; this build ends with the finish
    review, the verdict, and DESIGN.md.
- **Signature interaction (call):** pressing A or R lands a stamp on the structure
  (scale and rotate in about 160 ms; instant with reduced motion). The orange marker and
  its card are one thing: a marker on a page and its structure card carry the same
  numbered tag `[nn]`; hovering or selecting either outlines the other, and clicking a
  marker selects and scrolls to its card (Paper view and focus mode; the landing hero
  shows the markers without cards). Every state also has a word and a shape, never
  colour alone.
- **States (decided):**

  | State | Word (exact) | Shape | Colour |
  |---|---|---|---|
  | Accepted | "Accepted" | round stamp rotated −12° with the word; the word in the card's tag row | green `#2D7A46` |
  | To check | "To check" | filled badge; the card gets a 2 px orange outline; a solid orange marker on the page | `#FA3600` fill, `#141414` text |
  | Rejected | "Rejected" | "✕" and the word; the drawing is crossed by a diagonal line and dimmed, the SMILES struck through; with R a round charcoal stamp lands | charcoal `#1C211D`, muted text |
  | Failed | "Failed" | filled charcoal tag on a hatched ground (135° stripes `#E6E5DC` on paper), the reason, a retry | charcoal `#1C211D`, tag text `#F4F3EA` |
  | Reading… | "Reading…" | dashed orange marker on the page; the word on the card | orange outline, ink word |
  | Not read yet | "Not read yet" | hollow square "□" and the word | muted `#5E625B` |

- **Tool screens:** the Survey Sheet board shows the review grid (tag row `[03] · PAGE 2`,
  structure, SMILES, state, glass Accept / Reject / Compare, the keys line, the export
  line). The Paper view keeps the Field Sheet board's layout (page, text, structure list)
  in the Survey Sheet look; focus mode uses the same parts: drawing-sheet frame, numbered
  tags, orange markers, label tables, stamps.
- Light mode only **(decided 2026-11-17)**: no dark theme and no theme toggle.
- `DESIGN.md` is written from the finished build by the impeccable documenter.

## 8. Technical calls

- Folder `frontend-v2/` **(call)**; `frontend/` stays until switch day.
- Vite, React, TypeScript (strict), React Router with pre-rendering of the static pages,
  TanStack Query for server state, no global store beyond that unless needed **(call)**.
- Ketcher from npm (`ketcher-react` + `ketcher-standalone`), loaded only when the editor opens **(call)**.
- Depictions from `POST /api/v2/tools/depict` (same drawing as v1); similarity and MCS
  from `/tools/compare` and `/tools/mcs`; no chemistry code in the browser **(call)**.
- Page images from `GET /papers/{id}/pages/{n}/image`; crops from
  `GET /segments/{id}/image`; no PDF viewer library **(call)**.
- Live updates: `GET /papers/{id}/events` (SSE) with polling fallback every 2 s.
- Same origin: the built files are served by the v2 nginx (`backend-v2/docker/nginx.conf`)
  at `/`, the API stays at `/api/v2`; the owner cookie (`Path=/api/v2`, SameSite=Strict)
  works without CORS.
- CSP for the app: `default-src 'self'`; `connect-src 'self'` plus
  `https://pubchem.ncbi.nlm.nih.gov`, the Matomo host (COCONUT sends no CORS headers: since
  2026-11-20 the browser reaches it only through the MARCUS relay `/api/v2/coconut/...`, same
  origin; backend-v2/README.md "COCONUT relay");
  `script-src 'self'` plus the Matomo host; no inline scripts (Matomo snippet moved to a file).
- Matomo **(decided)**: same tracker as v1 (`https://matomo.nfdi4chem.de/`, site id 7).
- Tests: Vitest + Testing Library for components; Playwright e2e against the v2 fake
  stack (`backend-v2/docker-compose.fake.yml`); axe checks in e2e; the security judge's
  stored-XSS test enabled.
- Build output goes into an nginx image stage; one compose change in `backend-v2`.

## 9. Backend touch points

The UI uses the v2 routes (backend spec §9 plus `GET /papers/{id}/steps`). The builder
check (2026-11-17) found gaps; each becomes a small backend task **before** the UI tasks
that need it (task group F0, in `backend-v2`, same review rules as the backend plan).
All are my calls:

1. **Depictions without a request storm.** A 200-structure grid cannot call
   `/tools/depict` 200 times (60/min tool limit). The OCSR worker renders the depiction
   (SVG, same CDK/RDKit drawing as `/tools/depict`) once per prediction and stores it;
   `GET /segments/{id}/depiction?engine=` serves it (owner-checked, cacheable). Edited
   curation structures get their depiction from one `/tools/depict` call.
2. **Bulk curation.** `PUT /papers/{id}/curation` with a list of `{segment_id, status, note?}`
   (one transaction, owner-checked, limit 500 per call).
3. **Rate limits for the tool.** Page/crop/depiction GETs of the owner's own paper do not
   count against the 300/min IP bucket the same way as writes; set limits so a 200-structure
   paper loads in one go (measured in the e2e test).
4. **Single image jobs.** `GET /images` (this owner's image jobs), `GET /images/{id}/image`
   (the uploaded image), image events on SSE, and `POST /images/{id}/predictions {engine}`
   so compare works for single images.
5. **Papers list counts.** `PaperSummary` gains `structures`, `accepted`, `rejected`,
   `to_review`, `failed_pages`.
6. **Title.** The DOI step also fetches the title (Crossref, then DataCite) from the
   worker that has egress and stores it on the paper; `GET /papers` and `/papers/{id}`
   return `title`. The browser does not call Crossref/DataCite.
7. **Export with curation.** Columns/fields `status`, `engine`, `note`, `edited`;
   `?status=accepted|all` filter (default `accepted` for SDF, `all` for JSON/CSV).
8. **Retry a failed page.** `POST /papers/{id}/pages/{n}/retry` re-queues render+segment
   for a page whose step failed (owner-checked, at most 2 manual retries per page).
9. `GET /queue` returns waiting steps per queue plus an estimate (exists); the status bar
   shows "about N min" from the estimate, not a position number.

**Ketcher and the CSP (my call):** Ketcher runs inside a same-origin iframe served from
`/ketcher/`, with its own CSP that allows `'wasm-unsafe-eval'` and `worker-src blob:` only
there (Indigo as WebAssembly, no server needed). The main app keeps the strict CSP and
talks to the iframe by `postMessage` with an origin check. The old call "no chemistry code
in the browser" stays true for the app; the editor is the one isolated exception.

## 10. How to cite (decided)

Rajan K., Weißenborn V., Lederer L., Zielesny A., Steinbeck C. MARCUS: molecular
annotation and recognition for curating unravelled structures. *Digital Discovery*
2025, 4(11), 3137–3148. https://doi.org/10.1039/d5dd00313j

## 11. Order of work

1. This document approved.
2. `/impeccable`: PRODUCT.md, visual direction, DESIGN.md; owner approves the look.
3. Implementation plan (writing-plans), then build task by task with reviews, after the
   backend final review has fixed the API.
4. Switch day (owner picks): v2 backend + this UI replace v1 and the maintenance page.

## 12. Left to the builder

Component structure, file layout, exact key bindings beyond §5, empty and loading
states, animation details (within DESIGN.md), copy wording (plain English, product terms
as in v1: segment, structure, engine, SMILES, molfile).
