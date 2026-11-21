# MARCUS v2 backend: design

Date: 2026-11-16. Status: draft for approval.
Owner decisions are marked **(decided)**. My own calls are marked **(call)** and can be changed.

## 1. Intent

MARCUS takes a journal article (PDF) and gives back the chemical structures in it
(segmentation, then OCSR = image to SMILES), the text, and annotations, so that a
curator can check them for COCONUT.

v1 does all heavy work inside the web process. The judges in `judges/` showed:

- 17 of 17 security tests fail (file read, path tricks, stored XSS, data leaks
  between users, no upload limit, spoofable rate limit).
- One big paper blocks everyone. A small paper waited 387 s behind a big one (CPU).
- Two papers at once are not faster than one after the other (224 s vs 223 s).
- During segmentation the server does not answer health checks for 36 s, and then
  it crashed (SIGSEGV). As shipped, the CPU copy crashed on 5 of 5 multi-page papers.
- 4 page threads share one Keras model; molnextr and molscribe lost 2 of 4 pages
  on the S1 fixture (9/15 structures).
- The v1 "queue" (`backend/app/modules/session_manager.py`) is an in-memory list
  of 3 sessions. It does not control the GPU work.
- Uploads and results are kept forever; disk grows without limit.

v2 is a new backend, built correctly from the start, with real workers and a real
queue. It keeps the core idea. v1 is taken down at the switch **(decided)**.

**Switch timing (decided):** the switch waits for the React UI (the next project).
v1 stays live until both the v2 backend and the React UI are ready. The current Vue
UI is not ported to v2.

**GPU test time (decided):** the owner allows stopping v1 production on jarvis to use
the V100 for tests. Each test session: stop v1, run the judges (v1 baseline and v2),
start v1 again, and report the downtime.

## 2. Users and flow

- **First user: a curator in the browser (decided).** Scripts come second.
- **Scripts** use the same job API with an API key, at a lower priority than browser
  users. The old v1 endpoints go away; the owner tells the script owners **(decided)**.
- **Flow (decided):**
  1. The curator uploads a PDF and picks an OCSR engine (default DECIMER).
  2. v2 checks the file, renders pages, and segments each page.
  3. Right after segmentation, OCSR runs on all segments in the background with the
     chosen engine. Results appear one by one while the curator starts to check.
  4. The curator can run one segment again with another engine, edit the SMILES or
     molfile, and mark each segment accepted or rejected.
  5. Text extraction (docling) runs beside segmentation. The DOI is found from the PDF.
  6. Annotation (local LLM) comes in a later phase (section 11).
- **Ownership (decided):** no login. Each browser gets a secret owner token. Only that
  token can see, change, or delete its papers. Scripts get API keys (also owners).
- **Retention (decided):** a nightly job deletes PDFs, images, and results older than
  30 days. The API returns `expires_at` so the browser can show it.
- **Engines (decided):** decimer, molnextr, molscribe all stay. DECIMER is the default.
  The DECIMER hand-drawn model stays as a fourth engine, `decimer-hand`; the decimer
  worker loads it only when it is first asked for **(decided)**.
- **Single image OCSR (call):** scripts and the v1 UI can send one image and get
  SMILES back. v2 keeps this as `POST /images` (an owned, quota-counted job with one
  `ocsr` step that goes through the same fair dispatcher).
- **OCSR mode (call):** upload takes `ocsr=auto|off` (default `auto`). `off` gives
  segments only; the curator or script can start OCSR later per segment.

## 3. Goals, non-goals, anti-goals

Goals (each one has an outside judge):

| Goal | Judge | Pass |
|---|---|---|
| Safe | `judges/security` (ported to v2 routes, section 10) | 17 of 17 pass, and each test proves its v2 endpoint exists (no pass by 404) |
| Fair | `judges/load` S2 on jarvis GPU | small paper (15 structures) starts segmentation in < 10 s and shows its first SMILES in < 60 s while a 190-structure paper runs **(decided)** |
| Responsive | `judges/load` S3, S5 | `/health` p95 < 100 ms during heavy work; tool calls (depict) p95 < 2 s during heavy work |
| Robust | load S3 + adversarial PDFs from the security judge | a bad PDF fails only its own paper; no worker crash takes down the API; 0 lost pages on S1 fixture |
| Not less accurate | S1 and S2 fixtures (known truth: 15 and 190 structures) and `judges/goldset` (2 papers that really draw structures; PMC3229060 is replaced) | per engine, exact-match structures on the fixtures >= v1, with v1 as shipped running on the jarvis GPU in the same test session; gold-set recall reported beside v1 (2 papers are too few for a hard bar) |
| Throughput | load S4, full pipeline (segment + OCSR) | 2 papers at once finish faster than one after the other |

Baseline rules **(call)**: the v1 baseline is v1 as shipped (not the single-thread
shim), on the jarvis GPU. Moving MolScribe from CPU (v1) to GPU is allowed only if
the fixture judge shows no loss.

Non-goals for this project:

- The React frontend (next project). v2 must expose everything the current Vue UI
  needs, so the React UI can be built on it.
- Login accounts, multi-GPU or multi-host scaling, Kubernetes.
- Retraining OCSR or segmentation models.
- Migration of v1 data **(call)**: v1 results have no owner and retention is 30 days.

Anti-goals (a failure even if it works):

- Lower accuracy than v1 because model versions or image pre-processing changed.
- A judge that passes because an endpoint does not exist.
- Any change to production on jarvis before the switch day the owner picks.
- Secrets in logs, errors, or the browser.

## 4. Constraints

- Production host: jarvis, one Tesla V100 32 GB (compute capability 7.0, no bf16).
  GPU compute mode was `Exclusive_Process` and goes back to it on reboot; v2 runs
  several GPU processes, so the switch must set `Default` permanently (section 12).
- Build machine: no GPU, 60 CPU cores, 188 GB RAM. Local tests run on CPU; real GPU
  timings come only from jarvis **(decided: build and test locally, then replace)**.
- Model packages and versions must match v1 exactly (see `backend/Dockerfile`):
  TensorFlow 2.15, torch 2.1.0 cu118, `decimer` (PyPI), MolNexTR from
  `git+https://github.com/Kohulan/MolNexTR.git`, MolScribe at commit
  `250f683f52f5050eb624870ccfd04bccbcaa27e1`, DECIMER-Image-Segmentation `development`
  branch, numpy 1.24.3. Pin by commit hash, not by branch **(call)**.
- Page rendering must match v1: PyMuPDF at 300 DPI, `segment_chemical_structures(img,
  expand=True, return_bboxes=True)`.
- Reference stack: the owner's ChemAudit backend (`/home/kohulan/ChemAudit/backend`):
  FastAPI, Postgres 16, Redis 7, Celery with separate queues, Alembic, Prometheus,
  Grafana. Copy its structure and conventions where they fit.

## 5. Approaches considered

1. **Celery workers + Postgres fair dispatcher (chosen, decided).** Postgres stores
   every step. A small dispatcher picks the next fair step and sends it to the right
   Celery queue. Celery gives time limits, kills hung steps, and restarts crashed
   workers. Same parts as ChemAudit.
2. **Postgres-only queue.** Workers take steps with `SELECT ... FOR UPDATE SKIP LOCKED`.
   Fewer parts, but we must write timeouts, hung-step kill, and restarts ourselves.
3. **Model servers (Triton or Ray Serve) with batching.** Best GPU throughput, but
   heavy to run and the TF and torch models need conversion. MARCUS traffic is too
   low to need it.

Plain Celery FIFO alone was rejected: a big paper would put 190 OCSR tasks in the
queue before a small paper's first task.

## 6. Architecture

```
browser / script
      |  HTTPS
   nginx (only public port; size limit, security headers)
      |
   api (FastAPI, no ML libs)  --SSE progress-->  browser
      |                \
   Postgres           Redis (Celery broker + pub/sub for progress + rate limit)
      |                 ^
   dispatcher ----------+   picks next fair step, sends Celery task
      |
   Celery queues, one worker process per queue:
     q.cpu        worker-cpu        PDF check, page render, docling, DOI, cleanup
     q.tools      worker-tools      CDK depiction, molfile convert (fast, high priority)
     q.segment    worker-segment    GPU, TF: DECIMER segmentation
     q.decimer    worker-decimer    GPU, TF: DECIMER OCSR
     q.molnextr   worker-molnextr   GPU, torch: MolNexTR
     q.molscribe  worker-molscribe  GPU, torch: MolScribe
     (later) llm  llama.cpp server  GPU: annotation
   prometheus + grafana (internal only)
```

Images **(call)**: `marcus-api` (Python 3.11, FastAPI, RDKit, no TF/torch),
`marcus-worker-tf` (segment + decimer), `marcus-worker-torch` (molnextr + molscribe),
`marcus-worker-cpu` (PyMuPDF, docling, pdf2doi, JPype + CDK for depiction). All use
Python 3.11 (TF 2.15 supports it). One shared package `marcus_core` (settings, DB
models, step kinds, storage paths) is installed in every image.

Code location **(call)**: new folder `backend-v2/` in the MARCUS repo, on branch
`v2-backend`. `backend/` (v1) stays as a reference until the switch, then is deleted.

## 7. Data model (Postgres, Alembic migrations)

- `owners`: id, kind (`browser` | `api_key`), token_hash (SHA-256 of the secret;
  the secret is never stored), priority class, created_at, last_seen_at, quota fields.
- `papers`: id (UUID), owner_id, display_name (sanitized, never used in a path),
  pdf_sha256, bytes, pages, doi, engine (default for OCSR), status
  (`checking` | `processing` | `done` | `failed` | `deleted`), error, created_at,
  expires_at.
- `steps`: id, paper_id, kind (`check_pdf` | `render_page` | `segment_page` | `ocsr`
  | `docling` | `doi` | `annotate`), page, segment_id, engine, depends_on, status
  (`pending` | `queued` | `running` | `done` | `failed` | `cancelled`), attempts,
  error_class, error, queued_at, started_at, finished_at, worker_name.
- `segments`: id, paper_id, page, index, bbox (page pixels at 300 DPI), image_key,
  image_sha256.
- `predictions`: id, segment_id, engine, engine_version, smiles, molfile, valid
  (RDKit parse), ms, created_at.
- `curation`: segment_id, status (`unchecked` | `accepted` | `rejected`), smiles,
  molfile, note, updated_at.
- `seg_cache` (owner + pdf_sha256 + seg model version -> segments, and the paper that made
  it) and `ocsr_cache` (owner + image_sha256 + engine + version -> smiles/molfile). Both are
  per owner: a hit only ever follows the same owner's own earlier work, so a skipped step,
  `cached` or `ms` 0 says nothing about other owners (security review F3/F6). Results are
  copied into the owner's new paper. Deleting the paper drops its seg_cache row; deleting
  an owner drops both (foreign keys, ON DELETE CASCADE); retention ages them out.
- Stored structure drawings (`data_root/depictions/<owner id>/`) are per owner too: a
  stored drawing or `.nodraw` marker never answers another owner's request (F2/F4).

Files on disk under one data root, `/data/{paper_id}/...`. The server makes every
file name. A client name never reaches a path. This removes the whole path-trick
class of v1 bugs.

## 8. Scheduling (the core of "fair")

- The API writes a paper and its first steps (`check_pdf`, then the others become
  `pending` with `depends_on`). It never runs ML work.
- The **dispatcher** is one process. It wakes on a Postgres `NOTIFY` (step done, new
  paper) or every 1 s. For each queue with a free slot, it picks one ready step:
  1. priority class: browser before api_key;
  2. fair share between owners: the owner with the fewest steps running or done in
     the last 5 minutes on that queue goes first;
  3. inside one owner: the oldest paper first, then step order.
  It marks the step `queued` (`FOR UPDATE SKIP LOCKED`, so a second dispatcher could
  never double-send) and sends a Celery task that carries only the step id.
- Slots per queue = worker processes on that queue, so Redis never holds a long
  backlog. The small paper's first step runs as soon as the current step ends.
  Each GPU step is short (one page or one segment, about 1-6 s on the V100), so the
  small paper starts in well under 10 s.
- Celery settings: `acks_late=True`, `task_reject_on_worker_lost=True`,
  `worker_prefetch_multiplier=1`, prefork pool with concurrency 1 on GPU workers,
  model loaded once in `worker_process_init`, `max_memory_per_child` set per worker.
- Time limits per step kind (soft / hard, **call**, tune on jarvis): check_pdf
  20 s / 30 s, render_page 30 / 45, segment_page 60 / 90, ocsr 30 / 45, docling
  300 / 360, depiction 5 / 10.
- Failure rules: a step that times out or loses its worker is retried once; the second
  failure marks it `failed` with an `error_class` (`timeout`, `worker_lost`,
  `bad_input`, `engine_error`). A paper finishes as `done` with some failed steps; it
  is `failed` only if `check_pdf` or all pages fail. A watchdog moves steps stuck in
  `queued` or `running` past hard limit + grace back to `pending`.
- Owner limits **(call)**: browser owner max 3 active papers; PDF max 20 MB and
  100 pages; API keys have a daily page quota set per key.
- Abuse limit **(call)**: a client without a cookie gets a new browser owner, so one
  IP may create at most 10 owners per hour and hold at most 6 active papers across
  all its browser owners. Scripts that skip API keys are bounded by this.
- Network **(call)**: workers may reach the internet only for the DOI lookup
  (`pdf2doi` online fallbacks, Crossref), with a 5 s timeout per call and 15 s per
  paper. Everything else stays offline.

## 9. API (all under `/api/v2`, JSON only, OpenAPI published)

Auth: browser owner token in an HttpOnly, Secure, SameSite=Strict cookie, created on
the first request; scripts send `Authorization: Bearer <api key>`. Every resource is
checked against the owner. A resource of another owner gives 404, the same as a
missing one (no existence oracle).

- `POST /papers` (multipart PDF, optional engine) -> 202 `{paper_id}`
- `GET /papers`, `GET /papers/{id}`, `DELETE /papers/{id}`
- `GET /papers/{id}/events` (SSE: step and segment updates; the client can also poll
  `GET /papers/{id}`)
- `POST /images` (one image, engine) -> 202 `{image_job_id}`; `GET /images/{id}`
- `GET /papers/{id}/pages/{n}/image`, `GET /papers/{id}/segments`,
  `GET /segments/{id}/image`
- `POST /segments/{id}/predictions` `{engine}` (run again with another engine)
- `PUT /segments/{id}/curation` `{status, smiles?, molfile?, note?}`
- `GET /papers/{id}/text` (docling result), `GET /papers/{id}/export?format=json|sdf|csv`
- `GET /queue` (my papers' positions and an estimate)
- Tools, no paper needed, rate limited: `POST /tools/depict`,
  `POST /tools/smiles-to-molfile`, `POST /tools/mcs`, `POST /tools/compare`
  (cover v1 depiction and similarity routes). A depict `highlight` is drawn only with
  the `highlight_token` that `/tools/mcs` returned with that SMARTS: an HMAC over the
  SMARTS and the molecules (RDKit canonical SMILES without stereo) the MCS was computed
  from, valid 30 minutes, and only for one of those molecules. So CDK never searches with a
  client-chosen pattern (a pattern absent from the molecule can search for minutes); at
  most 32 matches are highlighted (F5). Key: `MARCUS_HIGHLIGHT_KEY`, else one random key
  per deployment kept in Redis.
- `GET /health` (process alive, no DB call), `GET /ready` (DB, Redis, each queue has a
  live worker), `GET /metrics` (internal network only)
- Admin by CLI only, never HTTP: create or revoke API keys, purge, reset.

## 10. Security (maps to the 17 v1 failures)

- No client value becomes a path; files are found by DB id and owner.
- Upload limit in nginx (`client_max_body_size`) and in the API (stream and count
  bytes; 413 above 20 MB). Images also checked by magic bytes and pixel size.
- PDFs are opened only in `worker-cpu` with a hard time limit and an address-space
  limit (`RLIMIT_AS`), so a bad PDF cannot hang or crash the API.
- Owner checks on every route; no list returns another owner's data; no HTTP reset.
- Rate limit in Redis by owner and by client IP; the IP comes from
  `X-Forwarded-For` only when the request comes from the trusted nginx address.
- Headers on every response: CSP, `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY` (or `frame-ancestors 'none'`), `Referrer-Policy`.
- The API returns JSON; display names are sanitized; the stored-XSS judge test must
  still pass once the React UI exists.
- Only nginx is published; the API, Postgres, Redis, and metrics stay on the internal
  Docker network (v1 published port 9000 to the world).
- Secrets only in env; logs mask tokens; errors are generic to the client and full in
  the server log with a request id.

**Judge port (part of this project):** the security suite calls v1 routes. Each test
gets a v2 form that attacks the same weakness on the v2 route, and first proves the
v2 route exists with a valid request (so a 404 can never count as a pass). Add the
X-Forwarded-For spoof test that the v1 report put aside. Add
`judges/common/client_v2.py` with the same `run_paper(pdf_path, engine, *, base_url)
-> PaperRun` contract. The gold-set scorer runs unchanged. `load/scenarios.py` calls
v1 routes directly, so it gets a v2 adapter for its calls; the scenario logic and
pass rules stay the same. Two new measurements go in: time from upload to the first
segmentation step, and tool (depict) p95 under load.

Frontend-side tests **(call)**: in this backend project, the header tests run against
the v2 nginx in front of the API. The stored-XSS browser test runs when the React UI
exists; until then, the backend part (names are sanitized and served only as JSON)
is tested at API level.

## 11. Annotation with a local LLM (last phase)

- **(decided)** A local open-weight LLM on our own GPU replaces the fine-tuned OpenAI
  model. No outside service.
- Runtime **(call)**: llama.cpp server (OpenAI-style HTTP, GGUF weights, supports the
  V100 and also runs on CPU for local tests). Step kind `annotate` on its own queue.
- Model choice: decided by measurement, not opinion. Candidates in the 7-9B range,
  quantized to fit about 10 GB.
- Judge: the v1 fine-tune training data (the owner will copy it; **missing now**).
  Hold out a test part. Pass = label-level F1 on the held-out part at least equal to
  the v1 fine-tuned model's F1 on the same part. If no base model reaches it, the next
  step is a LoRA fine-tune on the training part.
- Output format stays as v1: labels with values, plus character offsets in the text.
- This phase is blocked until the training data arrives. The core does not depend on it.

## 12. Observability, operations, switch

- Prometheus metrics: queue depth and wait time per queue, step time per kind and
  engine, time from upload to first SMILES per paper, failures by `error_class`,
  worker restarts, GPU memory per process. One Grafana dashboard.
- Logs: JSON lines with request_id, paper_id, step_id.
- GPU memory budget on the V100 **(call, measure on jarvis)**: segment 6 GB, decimer
  4 GB, molnextr 3 GB, molscribe 3 GB, LLM 10 GB, rest is headroom. TF workers set a
  fixed memory limit; torch workers set `per_process_memory_fraction`.
- Nightly retention job (30 days) and a disk-use alarm.
- Local test stack: `docker compose` with CPU workers, plus a `fake` engine that
  returns known SMILES after a set delay, so the fairness rules can be tested fast
  on CPU. The fake engine is off in production settings.
- Outer proxy: production sits behind a reverse proxy on another host
  (141.35.136.10). Before the first GPU test session, read its setup (read only) to
  fix the trusted `X-Forwarded-For` address, its body size limit (must allow 20 MB),
  SSE buffering, and where TLS ends (needed for the `Secure` cookie).
- Switch day (owner picks the date): set GPU compute mode to `Default` permanently
  (for example a systemd unit that runs `nvidia-smi -c DEFAULT` at boot), read the
  jarvis reverse-proxy setup for `marcus.decimer.ai`, stop v1, start v2, run the
  judges against v2 on jarvis, keep the v1 images for rollback.

## 13. Left to the builder

- Exact module layout inside `backend-v2/`, test layout, lint and type settings
  (copy ChemAudit's).
- SSE implementation details; Redis pub/sub channel names.
- Export file formats beyond what section 9 lists.
- Exact fair-share window and time limits, tuned with the load judge.
