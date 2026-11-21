# MARCUS v2 Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new MARCUS backend (PDF in, segments + SMILES + text out) with owned papers, a fair Postgres-driven scheduler, Celery workers per engine, and every v1 security failure closed, proven by the judges in `judges/`.

**Architecture:** FastAPI (`marcus.api`) never runs ML work; it writes papers and steps to Postgres. One dispatcher process (`marcus.dispatcher`) picks the next fair step per queue and sends a Celery task that carries only the step id. One worker process per queue (`marcus.workers`) runs the step, writes the result, and creates the next steps through the pipeline planner (`marcus.core.pipeline`). Progress goes to the browser by Redis pub/sub and SSE.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2 (async in the API, sync in workers), Alembic, Postgres 16, Redis 7, Celery 5, PyMuPDF, docling, pdf2doi, RDKit, JPype + CDK 2.10, TensorFlow 2.15, torch 2.1.0 cu118, prometheus-client, pytest, ruff, Docker Compose, nginx.

**Spec:** `docs/superpowers/specs/2026-11-16-marcus-v2-backend-design.md` (read it before any task).

## Global Constraints

- All code lives in `backend-v2/` as one Python distribution `marcus` (`backend-v2/src/marcus/`), with extras `api`, `cpu`, `tools`, `tf`, `torch`, `dev`. Branch: `v2-backend`.
- Python 3.11 in every image. ruff line length 100, rules `E,F,I,N,W` (copy `ChemAudit/backend/pyproject.toml` `[tool.ruff]`).
- Model packages pinned exactly as v1 `backend/Dockerfile`: `tensorflow==2.15.0`, `torch==2.1.0` + `torchvision==0.16.0` from the cu118 index, `decimer` (PyPI, `--no-deps`), MolNexTR from `git+https://github.com/Kohulan/MolNexTR.git`, MolScribe at commit `250f683f52f5050eb624870ccfd04bccbcaa27e1`, DECIMER-Image-Segmentation from the `development` branch, `numpy==1.24.3`. Branch refs are resolved to a commit hash once (Task B1) and pinned by hash.
- Page render: PyMuPDF `fitz.Matrix(300/72, 300/72)`, `alpha=False`. Segmentation call: `segment_chemical_structures(img, expand=True, return_bboxes=True)`.
- Limits: `MAX_UPLOAD_BYTES = 20 * 1024 * 1024` (20 MB + 1 byte gets 413); `MAX_PAGES = 100`; `RETENTION_DAYS = 30`; browser owner max 3 active papers; per IP max 10 new owners per hour and max 6 active papers; DOI network lookups 5 s per call and 15 s per paper.
- Time limits (soft / hard seconds): `check_pdf` 20/30, `render_page` 30/45, `segment_page` 60/90, `ocsr` 30/45, `docling` 300/360, `doi` 15/20, tools 5/10. A step is retried once; the second failure is final.
- Engines: `decimer` (default), `decimer-hand` (lazy load), `molnextr`, `molscribe`; `fake` exists only when `MARCUS_ENABLE_FAKE_ENGINES=1` and must be refused otherwise.
- No client-supplied string ever becomes part of a filesystem path. Every owned resource of another owner returns the same 404 as a missing one.
- Only nginx publishes a port. API, Postgres, Redis, metrics stay on the internal Docker network.
- CDK and centres jars are baked into the `worker-tools` image at build time (v1 downloads them at runtime in `backend/app/modules/cdk_wrapper.py:30-41`).
- Never point anything at production. Production stops only in a GPU test session (Task D4), per the owner's rule.
- Accuracy runs use 1-2 papers (owner rule), plus the S1/S2 fixtures with known truth.

## Review Focus

1. **A PDF that is encrypted, has 0 pages, or is a renamed PNG** — the paper ends `failed` with `error_class=bad_input` and a readable error, in < 30 s; no worker stays stuck. Test added to Task A8.
2. **The same PDF uploaded twice by one owner** — two separate papers; the second uses the segmentation cache and both reach `done`. Test added to Task B4.
3. **A paper deleted while its steps are queued or running** — its pending steps become `cancelled`, running steps' results are dropped, files are removed, and the dispatcher never sends its steps again. Test added to Task A5.
4. **A segment with 0 width or 0 height from the segmenter** — skipped, not saved, no OCSR step (v1 does this at `decimer_segmentation_wrapper.py:139`). Test added to Task A9.
5. **The SSE client disconnects or the browser reloads mid-paper** — the paper keeps running; `GET /papers/{id}` gives the full current state, so a reconnect loses nothing. Test added to Task A10.

---

## File map

```
backend-v2/
  pyproject.toml                     extras per image; ruff; pytest config
  alembic.ini, alembic/              migrations (env.py uses marcus.core.db)
  src/marcus/core/
    settings.py                      Settings (pydantic-settings), get_settings()
    enums.py                         StepKind, StepStatus, ErrorClass, Engine, OwnerKind, PaperStatus, PriorityClass
    queues.py                        queue_for(), SLOTS, TIME_LIMITS
    storage.py                       server-made paths only
    db.py                            async + sync engines, sessions, Base
    models.py                        Owner, Paper, Step, Segment, Prediction, Curation, ImageJob, SegCache, OcsrCache
    tokens.py                        new_token(), hash_token()
    pipeline.py                      start_paper(), complete_step(), fail_step(), cancel_paper()
    events.py                        publish_event(), channel names
    celery_app.py                    Celery config, queues, beat schedule
  src/marcus/api/
    main.py                          create_app()
    deps.py                          current_owner (cookie / API key), client_ip()
    uploads.py                       read_limited(), sniff_pdf(), sniff_image()
    security.py                      headers middleware, rate limit, error handler + request id
    routes/papers.py, segments.py, images.py, tools.py, queue.py, health.py, events.py
    metrics.py                       DB-backed Prometheus collector
  src/marcus/dispatcher/
    pick.py                          pick_next(), free_slots(), dispatch_once(), watchdog_once()
    __main__.py                      LISTEN loop
  src/marcus/workers/
    runtime.py                       run_step task, handler registry, error mapping
    cpu.py                           check_pdf, render_page, docling, doi, purge_expired
    pdfsafe.py                       subprocess PDF open with RLIMIT_AS + timeout
    segment.py                       Segmenter protocol, DecimerSegmenter, FakeSegmenter, segment_page handler
    ocsr/base.py                     OcsrEngine protocol, OcsrResult, get_engine()
    ocsr/decimer.py, molnextr.py, molscribe.py, fake.py
    tools.py                         depict, smiles_to_molfile, mcs, compare (CDK + RDKit)
    gpu.py                           limit_tf_memory(), limit_torch_memory()
  src/marcus/cli.py                  marcus apikey create|revoke|list, marcus purge
  docker/Dockerfile.api, Dockerfile.cpu, Dockerfile.tools, Dockerfile.tf, Dockerfile.torch, nginx.conf
  docker-compose.yml                 full CPU stack (fake engines off)
  docker-compose.fake.yml            override: fake segment/OCSR workers, for fast fairness tests
  docker-compose.gpu.yml             override: GPU reservations + memory budgets + dcgm-exporter
  docker-compose.test.yml            postgres + redis on 127.0.0.1:55432 / 56379 for pytest
  ops/grafana/marcus.json, ops/systemd/nvidia-compute-default.service
  tests/                             mirrors src/marcus (tests/core, tests/api, ...), conftest.py
judges/common/client_v2.py, judges/security/v2/, judges/load/v2_adapter.py   (Phase D)
```

Steps are created only when their inputs exist (the planner creates successors on completion), so `steps` has no `depends_on` column. This is a builder refinement of spec §7; behaviour is the same.

---

## Phase A — Core platform (CPU, fake engines)

### Task A1: Package scaffold, settings, enums, queues, storage

**Files:**
- Create: `backend-v2/pyproject.toml`, `backend-v2/docker-compose.test.yml`, `src/marcus/__init__.py`, `src/marcus/core/{settings,enums,queues,storage}.py`, `tests/conftest.py`
- Test: `tests/core/test_queues.py`, `tests/core/test_storage.py`, `tests/core/test_settings.py`

**Interfaces:**
- Produces:
  - `Settings` fields: `database_url: str`, `redis_url: str`, `data_root: Path`, `max_upload_bytes: int = 20971520`, `max_pages: int = 100`, `retention_days: int = 30`, `browser_max_active_papers: int = 3`, `ip_max_new_owners_per_hour: int = 10`, `ip_max_active_papers: int = 6`, `fair_window_s: int = 300`, `trusted_proxies: list[str] = []`, `enable_fake_engines: bool = False`, `cookie_secure: bool = True`; env prefix `MARCUS_`. `get_settings() -> Settings` (lru_cache).
  - Enums (str enums): `StepKind{CHECK_PDF="check_pdf", RENDER_PAGE="render_page", SEGMENT_PAGE="segment_page", OCSR="ocsr", DOCLING="docling", DOI="doi", ANNOTATE="annotate"}`, `StepStatus{PENDING, QUEUED, RUNNING, DONE, FAILED, CANCELLED}`, `ErrorClass{TIMEOUT, WORKER_LOST, BAD_INPUT, ENGINE_ERROR}`, `Engine{DECIMER="decimer", DECIMER_HAND="decimer-hand", MOLNEXTR="molnextr", MOLSCRIBE="molscribe", FAKE="fake"}`, `OwnerKind{BROWSER="browser", API_KEY="api_key"}`, `PaperStatus{CHECKING, PROCESSING, DONE, FAILED, DELETED}`, `PriorityClass(IntEnum){BROWSER=0, API=1}`.
  - `queue_for(kind: StepKind, engine: Engine | None) -> str`: `check_pdf|render_page|docling|doi -> "q.cpu"`, `segment_page -> "q.segment"`, `ocsr+decimer|decimer-hand -> "q.decimer"`, `ocsr+molnextr -> "q.molnextr"`, `ocsr+molscribe -> "q.molscribe"`, `ocsr+fake -> "q.fake"`, `annotate -> "q.llm"`. Tools use `"q.tools"` (not a step).
  - `SLOTS: dict[str, int]` default 1 per queue except `"q.cpu": 4`; overridable by env `MARCUS_SLOTS_<QUEUE>` (dots to underscores).
  - `TIME_LIMITS: dict[StepKind, tuple[int, int]]` with the Global Constraints values.
  - `storage.pdf_path(paper_id: UUID) -> Path`, `page_image_path(paper_id, page: int) -> Path`, `segment_image_path(paper_id, segment_id: UUID) -> Path`, `image_job_path(job_id: UUID) -> Path`, `paper_dir(paper_id) -> Path`. Layout: `{data_root}/papers/{paper_id}/source.pdf`, `.../pages/{page:04d}.png`, `.../segments/{segment_id}.png`, `{data_root}/images/{job_id}.png`.

- [ ] **Step 1: Write failing tests**
  - `test_queue_for_every_kind_and_engine`: table of all combinations above; `queue_for(StepKind.OCSR, None)` raises `ValueError`.
  - `test_storage_paths_are_under_data_root`: for a fixed UUID each path `.resolve()` is relative to `data_root.resolve()`.
  - `test_storage_rejects_non_uuid`: `pdf_path("../../etc/passwd")` raises `TypeError` (only `uuid.UUID` accepted).
  - `test_settings_defaults`: `Settings().max_upload_bytes == 20 * 1024 * 1024`, `retention_days == 30`, `enable_fake_engines is False`.
- [ ] **Step 2: Run** `cd backend-v2 && uv run pytest tests/core -q` — Expected: FAIL (import errors).
- [ ] **Step 3: Implement** the four modules and `pyproject.toml` (extras listed in File map; `dev` = pytest, pytest-asyncio, httpx, ruff, fakeredis). `docker-compose.test.yml` runs `postgres:16-alpine` on `127.0.0.1:55432` and `redis:7-alpine` on `127.0.0.1:56379`. `tests/conftest.py` sets `MARCUS_DATABASE_URL`, `MARCUS_REDIS_URL`, `MARCUS_DATA_ROOT=tmp_path`.
- [ ] **Step 4: Run** `uv run pytest tests/core -q && uv run ruff check src tests` — Expected: PASS, no lint errors.
- [ ] **Step 5: Commit** `feat(v2): scaffold marcus package, settings, queues, storage`

### Task A2: Database models and first migration

**Files:**
- Create: `src/marcus/core/db.py`, `src/marcus/core/models.py`, `alembic.ini`, `alembic/env.py`, `alembic/versions/0001_initial.py`
- Test: `tests/core/test_migrations.py`, `tests/core/test_models.py`

**Interfaces:**
- Produces: `db.async_session`, `db.sync_session`, `db.Base`, `db.get_db()` (FastAPI dependency) — same pattern as `ChemAudit/backend/app/db/__init__.py` (async URL `+asyncpg`, sync `+psycopg`).
- Tables (UUID primary keys, `timestamptz` everywhere):
  - `owners(id, kind, token_hash UNIQUE, priority_class int, created_ip inet, created_at, last_seen_at, revoked_at NULL, daily_page_quota int NULL, label text NULL)`
  - `papers(id, owner_id FK, display_name text, pdf_sha256 char(64), bytes int, pages int NULL, doi text NULL, engine text, ocsr_mode text CHECK in ('auto','off'), status, error text NULL, created_at, expires_at)`; index `(owner_id, status)`
  - `steps(id, paper_id FK NULL, image_job_id FK NULL, kind, queue text, engine text NULL, page int NULL, segment_id FK NULL, seq int, status, attempts int default 0, error_class NULL, error NULL, created_at, queued_at, started_at, finished_at, worker_name NULL)`; CHECK exactly one of paper_id/image_job_id; index `(queue, status)` and `(paper_id, status)`
  - `segments(id, paper_id FK, page int, idx int, bbox int[4], image_sha256 char(64))`, UNIQUE `(paper_id, page, idx)`
  - `predictions(id, segment_id FK NULL, image_job_id FK NULL, engine, engine_version, smiles text, molfile text NULL, valid bool, ms int, created_at)`
  - `curation(segment_id PK FK, status text CHECK in ('unchecked','accepted','rejected'), smiles NULL, molfile NULL, note NULL, updated_at)`
  - `image_jobs(id, owner_id FK, display_name, image_sha256, engine, status, error NULL, created_at, expires_at)`
  - `seg_cache(pdf_sha256, seg_version, payload jsonb, created_at)` PK `(pdf_sha256, seg_version)`; `ocsr_cache(image_sha256, engine, engine_version, smiles, molfile NULL, created_at)` PK `(image_sha256, engine, engine_version)`
  - All child FKs `ON DELETE CASCADE`.
- Postgres trigger on `steps` insert/update of `status` runs `pg_notify('marcus_steps', NEW.queue)`.

- [ ] **Step 1: Write failing tests**
  - `test_upgrade_then_downgrade_clean`: `alembic upgrade head` then `downgrade base` on the test DB; table list empty after.
  - `test_step_needs_exactly_one_parent`: inserting a step with both or neither of `paper_id`/`image_job_id` raises `IntegrityError`.
  - `test_notify_on_step_status_change`: a `LISTEN marcus_steps` connection receives payload `"q.cpu"` after a step with that queue changes status.
- [ ] **Step 2: Run** `docker compose -f docker-compose.test.yml up -d && uv run pytest tests/core/test_migrations.py tests/core/test_models.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** models and migration `0001_initial`.
- [ ] **Step 4: Run** the same command — Expected: PASS.
- [ ] **Step 5: Commit** `feat(v2): database models and initial migration`

### Task A3: Owners, tokens, and the auth dependency

**Files:**
- Create: `src/marcus/core/tokens.py`, `src/marcus/api/deps.py`, `src/marcus/api/main.py` (minimal `create_app()` with health route only)
- Test: `tests/api/test_owner_auth.py`

**Interfaces:**
- Produces:
  - `new_token() -> str` (`secrets.token_urlsafe(32)`), `hash_token(token: str) -> str` (hex SHA-256).
  - `client_ip(request) -> str`: the socket peer, unless the peer is in `settings.trusted_proxies`, then the right-most `X-Forwarded-For` entry that is not a trusted proxy.
  - Browser owners get `priority_class = PriorityClass.BROWSER`; API-key owners `PriorityClass.API`.
  - `current_owner(request, response, db) -> Owner` dependency: `Authorization: Bearer <key>` → API-key owner (401 if unknown or revoked); else cookie `marcus_owner` → browser owner; else create a browser owner (subject to the per-IP limit of 10 new owners per hour → 429) and set cookie `marcus_owner` with `HttpOnly`, `SameSite=Strict`, `Secure` when `settings.cookie_secure`, `Path=/api/v2`, max age 30 days. Updates `last_seen_at`.
- [ ] **Step 1: Write failing tests**
  - `test_first_request_sets_httponly_cookie` (cookie flags present).
  - `test_same_cookie_same_owner`, `test_unknown_cookie_gets_new_owner`.
  - `test_api_key_owner_and_revoked_key_401`.
  - `test_eleventh_new_owner_from_one_ip_in_an_hour_is_429`.
  - `test_xff_ignored_from_untrusted_peer` and `test_xff_used_from_trusted_proxy` (`client_ip` unit tests with fake requests).
- [ ] **Step 2: Run** `uv run pytest tests/api/test_owner_auth.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement.** The per-IP owner limit counts `owners.created_ip` in the last hour.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(v2): owner tokens, API keys, auth dependency`

### Task A4: Upload a paper

**Files:**
- Create: `src/marcus/api/uploads.py`, `src/marcus/api/routes/papers.py` (POST only here), `src/marcus/core/pipeline.py` (only `start_paper` here)
- Test: `tests/api/test_upload_paper.py`

**Interfaces:**
- Consumes: `current_owner` (A3), `storage.pdf_path` (A1), models (A2).
- Produces:
  - `read_limited(upload: UploadFile, limit: int) -> bytes` raising `HTTPException(413)` as soon as `limit + 1` bytes are read (stream in 1 MiB chunks; never trust `Content-Length`).
  - `sniff_pdf(data: bytes) -> None` (415 unless data starts with `%PDF-` within the first 1024 bytes), `sanitize_display_name(name: str | None) -> str` (NFKC, strip control chars, keep basename only, max 200 chars, HTML-special chars kept as text — the API only returns JSON).
  - `POST /api/v2/papers` multipart `file`, form `engine: Engine = decimer`, `ocsr: Literal["auto","off"] = "auto"` → 202 `{"paper_id": str, "status": "checking"}`. Refuses `engine=fake` with 422 unless fake engines are on. 429 when the owner has 3 active papers (browser) or the IP has 6.
  - `pipeline.start_paper(session, owner, data: bytes, display_name, engine, ocsr_mode) -> Paper`: writes `source.pdf` (mode 0600), inserts `papers` row (`expires_at = now + retention_days`) and one `check_pdf` step.
- [ ] **Step 1: Write failing tests**
  - `test_upload_returns_202_and_one_check_pdf_step`.
  - `test_20mb_plus_one_byte_is_413` (exactly `20 * 1024 * 1024 + 1` bytes); `test_exactly_20mb_is_accepted`.
  - `test_png_named_pdf_is_415`.
  - `test_traversal_filename_never_reaches_disk`: filename `../../../tmp/evil.pdf` → stored file is `papers/<uuid>/source.pdf`, nothing exists at `tmp/evil.pdf` under or above `data_root`, `display_name == "evil.pdf"`.
  - `test_fourth_active_paper_is_429`.
  - `test_fake_engine_refused_when_disabled`.
- [ ] **Step 2: Run** `uv run pytest tests/api/test_upload_paper.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(v2): paper upload with size, type and name checks`

### Task A5: Pipeline planner

**Files:**
- Modify: `src/marcus/core/pipeline.py`
- Test: `tests/core/test_pipeline.py`

**Interfaces:**
- Produces (all take a sync `Session`, run in the caller's transaction):
  - `complete_step(session, step_id: UUID, result: dict) -> list[Step]` — sets `done`, stores result rows, returns the new successor steps. Successors:
    - `check_pdf` result `{"pages": n}` → `render_page` ×n (seq = page), one `docling`, one `doi`; paper → `processing`.
    - `render_page` (page p) → one `segment_page` for p.
    - `segment_page` result `{"segments": [{"idx", "bbox", "image_sha256"}]}` → `segments` rows (each also gets a `curation` row `unchecked`); if paper `ocsr_mode == "auto"`, one `ocsr` step per segment with the paper engine, `seq = page * 1000 + idx`.
    - `ocsr` result `{"smiles", "molfile", "valid", "ms", "engine_version"}` → `predictions` row (segment or image job).
    - `docling`/`doi` results stored on the paper (`doi`) or as file `papers/{id}/text.json` (path from storage).
  - After any change: if the paper has no step in `pending|queued|running`, paper → `done` (or `failed` if `check_pdf` failed or every `render_page` failed).
  - `fail_step(session, step_id, error_class: ErrorClass, error: str, retryable: bool) -> None` — `retryable and attempts < 2` → back to `pending`; else `failed`; then the same finish check.
  - `cancel_paper(session, paper_id) -> None` — pending/queued steps → `cancelled`; paper → `deleted`; deletes `paper_dir`.
  - `complete_step` on a step whose paper is `deleted` or whose status is `cancelled` is a no-op returning `[]`.
  - `request_ocsr(session, segment_id, engine) -> Step` (for rerun with another engine).
- [ ] **Step 1: Write failing tests**
  - `test_check_pdf_creates_render_docling_doi`.
  - `test_render_creates_segment_step_for_same_page`.
  - `test_segment_creates_ocsr_steps_when_auto_and_none_when_off`.
  - `test_paper_done_when_last_step_finishes`, `test_paper_failed_when_all_pages_fail`.
  - `test_fail_retries_once_then_final`.
  - Review Focus 3: `test_delete_while_running_cancels_and_drops_late_result` — cancel a paper with one `running` step, then `complete_step` on it returns `[]`, creates no rows, and the paper dir is gone.
- [ ] **Step 2: Run** `uv run pytest tests/core/test_pipeline.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(v2): pipeline planner for paper steps`

### Task A6: Fair dispatcher

**Files:**
- Create: `src/marcus/dispatcher/pick.py`, `src/marcus/dispatcher/__main__.py`
- Test: `tests/dispatcher/test_pick.py`, `tests/dispatcher/test_watchdog.py`

**Interfaces:**
- Consumes: models, `SLOTS`, `TIME_LIMITS`.
- Produces:
  - `free_slots(session, queue: str) -> int` = `SLOTS[queue]` − count of steps in that queue with status `queued|running`.
  - `pick_next(session, queue: str) -> Step | None` — one statement, locks the row with `FOR UPDATE OF steps SKIP LOCKED`. Order:

    ```sql
    -- usage per owner on this queue in the fair window
    WITH usage AS (
      SELECT COALESCE(p.owner_id, j.owner_id) AS owner_id, count(*) AS n
      FROM steps s LEFT JOIN papers p ON p.id = s.paper_id LEFT JOIN image_jobs j ON j.id = s.image_job_id
      WHERE s.queue = :q AND (s.status IN ('queued','running')
            OR s.finished_at > now() - make_interval(secs => :window))
      GROUP BY 1)
    SELECT s.* FROM steps s
      LEFT JOIN papers p ON p.id = s.paper_id LEFT JOIN image_jobs j ON j.id = s.image_job_id
      JOIN owners o ON o.id = COALESCE(p.owner_id, j.owner_id)
      LEFT JOIN usage u ON u.owner_id = o.id
    WHERE s.queue = :q AND s.status = 'pending'
    ORDER BY o.priority_class, COALESCE(u.n, 0), COALESCE(p.created_at, j.created_at), s.seq, s.created_at
    LIMIT 1 FOR UPDATE OF s SKIP LOCKED
    ```
  - `dispatch_once(session, send: Callable[[str, UUID], None]) -> int` — for every queue, while `free_slots > 0` and `pick_next` returns a step: set `queued`, `queued_at`, commit, then `send(queue, step.id)`. Returns the number sent.
  - `watchdog_once(session) -> int` — steps `queued|running` longer than hard limit + 30 s: `fail_step(..., ErrorClass.WORKER_LOST, retryable=True)`.
  - `__main__`: `LISTEN marcus_steps` on a psycopg connection; loop: wait for notify or 1 s, `dispatch_once`, every 10 s `watchdog_once`. `send` = `celery_app.send_task("marcus.run_step", args=[str(step_id)], queue=queue, soft_time_limit=soft, time_limit=hard)` with `(soft, hard) = TIME_LIMITS[step.kind]`, so `send` takes the step kind too: `send(queue: str, step_id: UUID, kind: StepKind)`.
- [ ] **Step 1: Write failing tests**
  - `test_small_paper_jumps_big_paper_backlog`: owner A has a paper with 190 pending ocsr steps, 5 done in the window; owner B uploads later with 15 pending; with 1 slot the next pick is B's step.
  - `test_browser_before_api_key`.
  - `test_oldest_paper_first_within_one_owner`.
  - `test_free_slots_respected` (`dispatch_once` sends nothing when the slot is busy).
  - `test_two_dispatchers_never_send_same_step`: two sessions call `pick_next` at once in threads; the two returned ids differ (or one is None).
  - `test_watchdog_requeues_stuck_running_step_then_fails_it`.
- [ ] **Step 2: Run** `uv run pytest tests/dispatcher -q` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(v2): fair dispatcher with skip-locked pick and watchdog`

### Task A7: Worker runtime and events

**Files:**
- Create: `src/marcus/core/celery_app.py`, `src/marcus/core/events.py`, `src/marcus/workers/runtime.py`
- Test: `tests/workers/test_runtime.py`, `tests/core/test_celery_config.py`

**Interfaces:**
- Produces:
  - `celery_app` with `task_serializer="json"`, `worker_prefetch_multiplier=1`, `task_acks_late=True`, `task_reject_on_worker_lost=True`, one `Queue` per name in `SLOTS` plus `"q.tools"`, result backend Redis with `result_expires=600` (tools only).
  - `register(kind: StepKind, handler: Callable[[Step, Session], dict]) -> None` and `HANDLERS`.
  - Celery task `marcus.run_step(step_id: str)`: load step; if status not `queued` (cancelled, or a re-delivered message for a step that finished) → return; increment `attempts`, set `running`, `started_at`, `worker_name`, commit; run the handler under `TIME_LIMITS[kind]` (`soft_time_limit`/`time_limit` passed via `apply_async` options by the dispatcher, or checked with `SoftTimeLimitExceeded`); on success `complete_step`; on `SoftTimeLimitExceeded` → `fail_step(TIMEOUT, retryable=True)`; on `BadInput` (new exception in runtime) → `fail_step(BAD_INPUT, retryable=False)`; on any other exception → `fail_step(ENGINE_ERROR, retryable=True)`. Message text is stored, never returned raw to clients.
  - A step found `running` at task start (redelivery after worker loss) counts as an attempt; past 2 attempts → `fail_step(WORKER_LOST, retryable=False)`.
  - `events.publish_event(paper_id: UUID, event: dict) -> None` on Redis channel `marcus:paper:{paper_id}`; called after each commit in `run_step` with `{"type": "step", "step_id", "kind", "status", "page", "segment_id"}`.
- [ ] **Step 1: Write failing tests** (call `run_step` directly with handlers registered in the test):
  - `test_success_calls_complete_step_and_publishes`.
  - `test_soft_timeout_is_retried_then_failed_timeout`.
  - `test_bad_input_not_retried`.
  - `test_cancelled_step_is_skipped`.
  - `test_redelivered_running_step_counts_attempt_and_fails_worker_lost_after_two`.
  - `test_celery_config_values` (prefetch 1, acks_late, reject_on_worker_lost, every SLOTS queue declared).
- [ ] **Step 2: Run** `uv run pytest tests/workers/test_runtime.py tests/core/test_celery_config.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(v2): worker runtime, error classes, progress events`

### Task A8: CPU worker — check, render, docling, DOI

**Files:**
- Create: `src/marcus/workers/pdfsafe.py`, `src/marcus/workers/cpu.py`
- Test: `tests/workers/test_cpu.py`, fixtures in `tests/fixtures/pdfs/` (small real PDF with 2 pages; encrypted PDF; 0-page PDF; PNG renamed `.pdf`; copy 2 adversarial PDFs from `judges/security/payloads.py`)

**Interfaces:**
- Produces:
  - `pdfsafe.page_count(path: Path, timeout_s: int, mem_mb: int = 2048) -> int` — opens the PDF with PyMuPDF in a child process (`multiprocessing` spawn) with `resource.setrlimit(RLIMIT_AS)`; raises `BadInput` on parse error, encryption, 0 pages, or > `max_pages`; raises `BadInput("timeout")` when the child exceeds `timeout_s` (child killed).
  - `pdfsafe.render_page_png(path, page: int, out: Path, timeout_s: int) -> None` — same isolation; 300 DPI exactly as Global Constraints; writes PNG.
  - Handlers registered for `check_pdf` → `{"pages": n}`, `render_page` → `{}`, `docling` → `{"text_path": "text.json"}` (docling export as v1 `routers/docling_conversion.py:68-127` does), `doi` → `{"doi": str | None}` (`pdf2doi` with network timeouts 5 s per call, 15 s per paper; returns None on timeout, never fails the paper).
- [ ] **Step 1: Write failing tests**
  - `test_check_pdf_counts_pages` (2).
  - Review Focus 1: `test_encrypted_zero_page_and_png_pdf_fail_bad_input_fast` — each raises `BadInput` in < 30 s.
  - `test_adversarial_pdf_times_out_without_hanging_worker` — `page_count(..., timeout_s=5)` returns or raises within 10 s.
  - `test_render_page_is_300_dpi` — PNG width = round(page width pt × 300/72).
  - `test_doi_timeout_returns_none` (monkeypatch the lookup to sleep 30 s).
- [ ] **Step 2: Run** `uv run pytest tests/workers/test_cpu.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(v2): cpu worker with isolated PDF handling`

### Task A9: Segment and OCSR handlers with fake engines

**Files:**
- Create: `src/marcus/workers/segment.py`, `src/marcus/workers/ocsr/{base,fake}.py`
- Test: `tests/workers/test_segment.py`, `tests/workers/test_ocsr.py`

**Interfaces:**
- Produces:
  - `class Segmenter(Protocol): version: str; def load(self) -> None; def segment(self, page_png: Path) -> list[tuple[np.ndarray, tuple[int,int,int,int]]]` (image, bbox `x0,y0,x1,y1`).
  - `FakeSegmenter(per_page: int, delay_s: float)` (env `MARCUS_FAKE_SEGMENTS_PER_PAGE`, `MARCUS_FAKE_SEGMENT_DELAY_S`) draws `per_page` crops.
  - `segment_page` handler: runs the segmenter on the page PNG, skips crops with 0 width or height, saves each crop at `storage.segment_image_path`, returns `{"segments": [{"idx", "bbox", "image_sha256"}]}`.
  - `@dataclass OcsrResult(smiles: str, molfile: str | None)`; `class OcsrEngine(Protocol): name: Engine; version: str; def load(self) -> None; def predict(self, image: Path) -> OcsrResult`.
  - `get_engine(name: Engine) -> OcsrEngine` — one instance per process, `load()` on first use; `Engine.FAKE` raises `RuntimeError` unless fake engines are on.
  - `FakeEngine(delay_s)` (env `MARCUS_FAKE_OCSR_DELAY_S`) returns `OcsrResult("c1ccccc1", None)`.
  - `ocsr` handler: `predict`, RDKit `Chem.MolFromSmiles` for `valid`, measures `ms`, returns the A5 result dict.
- [ ] **Step 1: Write failing tests**
  - `test_segment_page_saves_crops_and_returns_bboxes`.
  - Review Focus 4: `test_zero_width_crop_is_skipped` (segmenter stub returns one 0×10 crop and one good crop → 1 segment).
  - `test_ocsr_handler_marks_invalid_smiles` (engine stub returns `"C1CC"` → `valid False`).
  - `test_fake_engine_refused_in_production_settings`.
- [ ] **Step 2: Run** `uv run pytest tests/workers/test_segment.py tests/workers/test_ocsr.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(v2): segment and ocsr handlers, fake engines`

### Task A10: Read, curate, export, queue and SSE routes

**Files:**
- Modify: `src/marcus/api/routes/papers.py`
- Create: `src/marcus/api/routes/segments.py`, `routes/queue.py`, `routes/events.py`
- Test: `tests/api/test_papers_read.py`, `tests/api/test_ownership.py`, `tests/api/test_events.py`

**Interfaces:**
- Consumes: `current_owner`, `pipeline.cancel_paper`, `pipeline.request_ocsr`, storage.
- Produces (all under `/api/v2`, response models in `src/marcus/api/schemas.py`):
  - `GET /papers` (own only, newest first), `GET /papers/{id}` → `{id, display_name, status, pages, doi, engine, ocsr_mode, created_at, expires_at, counts: {steps_by_status}, segments: [{id, page, idx, bbox, curation, predictions: [...]}]}`.
  - `DELETE /papers/{id}` → 204 (calls `cancel_paper`).
  - `GET /papers/{id}/pages/{n}/image`, `GET /segments/{id}/image` → `image/png` with `Cache-Control: private`.
  - `POST /segments/{id}/predictions {engine}` → 202 `{step_id}`; `PUT /segments/{id}/curation {status, smiles?, molfile?, note?}` → 200 (RDKit-checks `smiles` if given, 422 if invalid).
  - `GET /papers/{id}/text` (the docling JSON), `GET /papers/{id}/export?format=json|sdf|csv` (sdf from molfile, else RDKit from smiles; curated values win over predictions).
  - `GET /queue` → `{papers: [{id, steps_ahead_by_queue}], estimate_s}` (estimate = steps ahead × median step time of last hour per queue).
  - `GET /papers/{id}/events` → `text/event-stream`, subscribes to `marcus:paper:{id}`, sends `: ping` every 15 s, header `X-Accel-Buffering: no`.
  - Not found and not owned both → `404 {"detail": "not found"}` with identical body.
- [ ] **Step 1: Write failing tests**
  - `test_list_shows_only_own_papers`.
  - `test_other_owner_gets_same_404_as_missing` for every route above (parametrized).
  - `test_curation_rejects_invalid_smiles`.
  - `test_export_sdf_uses_curated_smiles`.
  - `test_rerun_with_other_engine_creates_step`.
  - Review Focus 5: `test_state_complete_after_sse_disconnect` — open SSE, close it after the first event, finish the remaining steps through `complete_step`, then `GET /papers/{id}` shows all segments and predictions.
- [ ] **Step 2: Run** `uv run pytest tests/api -q` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(v2): paper read, curation, export, queue, SSE routes`

### Task A11: Single image OCSR

**Files:**
- Create: `src/marcus/api/routes/images.py`
- Modify: `src/marcus/api/uploads.py` (add `sniff_image`)
- Test: `tests/api/test_images.py`

**Interfaces:**
- Produces: `sniff_image(data) -> str` (PNG/JPEG/TIFF/WEBP magic bytes, else 415; Pillow `verify()`; max 10 000 × 10 000 px and 50 MP, else 413); `POST /api/v2/images` multipart `file`, form `engine` → 202 `{image_job_id}` (creates `image_jobs` row + one `ocsr` step); `GET /api/v2/images/{id}` → `{status, prediction}`; counts toward owner limits like a paper.
- [ ] **Step 1: Write failing tests** — `test_image_20mb_plus_one_is_413`, `test_pdf_sent_as_image_is_415`, `test_decompression_bomb_is_413`, `test_image_job_owned`.
- [ ] **Step 2: Run** `uv run pytest tests/api/test_images.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(v2): single image OCSR jobs`

### Task A12: Tools (depiction, molfile, MCS, compare)

**Files:**
- Create: `src/marcus/workers/tools.py`, `src/marcus/api/routes/tools.py`
- Test: `tests/workers/test_tools.py`, `tests/api/test_tools_routes.py`

**Interfaces:**
- Produces: Celery tasks on `q.tools`: `marcus.tools.depict(smiles: str, fmt: Literal["svg","png"], width: int, height: int) -> str` (CDK, ported from v1 `backend/app/modules/depiction.py` and `cdk_wrapper.py`; JVM started once per process with jars from `/opt/cdk/`), `marcus.tools.smiles_to_molfile(smiles) -> str` (CDK SDG as v1 `get_CDK_SDG_mol`), `marcus.tools.mcs(molfiles: list[str]) -> dict` and `marcus.tools.compare(smiles_a, smiles_b) -> dict` (ported from v1 `routers/similarity_router.py:38-298`, RDKit, MCS timeout 5 s). API routes `POST /api/v2/tools/{depict,smiles-to-molfile,mcs,compare}` wait for the result with the tools hard limit (10 s) → 504 on timeout. Input caps: SMILES ≤ 2000 chars, ≤ 20 molfiles, each ≤ 200 kB.
- [ ] **Step 1: Write failing tests** — port v1 behaviour checks: `test_depict_svg_for_benzene`, `test_smiles_to_molfile_has_coordinates`, `test_mcs_of_two_known_molecules` (expected MCS SMARTS from v1 output on the same input, recorded once from the v1 local copy), `test_long_smiles_422`, `test_tool_timeout_is_504` (stub task sleeping 20 s).
- [ ] **Step 2: Run** `uv run pytest tests/workers/test_tools.py tests/api/test_tools_routes.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(v2): depiction and similarity tools on their own queue`

### Task A13: Security layer

**Files:**
- Create: `src/marcus/api/security.py`
- Modify: `src/marcus/api/main.py`
- Test: `tests/api/test_security_layer.py`

**Interfaces:**
- Produces:
  - Middleware adding to every response: `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'` (API responses), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `X-Request-ID`.
  - Redis fixed-window rate limits keyed by owner id and by `client_ip`: uploads 10/min per owner, tools 60/min per owner, everything 300/min per IP; 429 with `Retry-After`. No path is exempt except `/api/v2/health`.
  - Exception handler: 500 body `{"detail": "internal error", "request_id": ...}`; full trace in the log only.
  - CORS: only `settings.cors_origins` (add field, default empty).
  - No route resets or lists data across owners (there is no such route; a test asserts the app route list).
- [ ] **Step 1: Write failing tests** — `test_headers_on_every_route`, `test_rate_limit_hits_429`, `test_xff_spoof_does_not_reset_limit` (untrusted peer changes XFF each call and still gets 429), `test_500_body_has_no_trace`, `test_no_admin_or_reset_routes_exposed`.
- [ ] **Step 2: Run** `uv run pytest tests/api/test_security_layer.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(v2): security headers, rate limits, safe errors`

### Task A14: Local stack and end-to-end fairness

**Files:**
- Create: `docker/Dockerfile.api`, `docker/Dockerfile.cpu`, `docker/Dockerfile.tools`, `docker/nginx.conf`, `docker-compose.yml`, `docker-compose.fake.yml`, `src/marcus/api/routes/health.py` (`/ready`)
- Test: `tests/e2e/test_stack.py` (marked `e2e`, needs the stack running)

**Interfaces:**
- Produces:
  - Services: `nginx` (only published port, `127.0.0.1:18090:8080` locally; `client_max_body_size 21m`; `proxy_buffering off` for `/api/v2/papers/*/events`; the same security headers), `api` (gunicorn + uvicorn workers, runs `alembic upgrade head` once at start), `dispatcher`, `worker-cpu` (`-Q q.cpu -c 4`, beat with `-B`), `worker-tools` (`-Q q.tools -c 2`), `postgres`, `redis`. `docker-compose.fake.yml` adds `worker-fake-segment` (`-Q q.segment`) and `worker-fake-ocsr` (`-Q q.fake`) with fake engines on.
  - `GET /api/v2/ready` → 200 only if DB and Redis answer and `celery_app.control.inspect().active_queues()` shows a consumer for every queue in `SLOTS` that the compose file runs; else 503 with the missing parts.
- [ ] **Step 1: Write failing tests**
  - `test_upload_to_done_with_fake_engines` (2-page fixture → `done`, segments = 2 × per_page, every segment has a prediction).
  - `test_small_paper_starts_within_10s_behind_big_paper` — fake delays: segment 2 s/page, OCSR 1 s; upload a 20-page paper (owner A), wait 5 s, upload a 2-page paper (owner B); B's first `segment_page` `started_at` − B `created_at` < 10 s and B's first prediction < 60 s.
  - `test_health_fast_during_load` — 50 `/api/v2/health` calls during the big paper; p95 < 100 ms.
  - `test_ready_503_when_a_worker_is_stopped`.
- [ ] **Step 2: Run** `docker compose -f docker-compose.yml -f docker-compose.fake.yml up -d --build && uv run pytest -m e2e -q` — Expected: FAIL first, then fix.
- [ ] **Step 3: Implement** Dockerfiles and compose; fix what the e2e run shows.
- [ ] **Step 4: Run** the same command — Expected: PASS.
- [ ] **Step 5: Commit** `feat(v2): local compose stack, readiness, e2e fairness test`

---

## Phase B — Real ML workers

### Task B1: TF worker image and DECIMER segmentation

**Files:**
- Create: `docker/Dockerfile.tf`, `src/marcus/workers/gpu.py`
- Modify: `src/marcus/workers/segment.py` (add `DecimerSegmenter`)
- Test: `tests/workers/test_decimer_segmenter.py` (marked `ml`)

**Interfaces:**
- Produces: `DecimerSegmenter(version=<pinned commit>)` calling `segment_chemical_structures(img, expand=True, return_bboxes=True)` on the PNG loaded as RGB `uint8` (same as v1 `process_single_page`), converting `(y0, x0, y1, x1)` to `(x0, y0, x1, y1)`. `gpu.limit_tf_memory(mb: int)` sets one logical device with `memory_limit=mb` before the model loads (env `MARCUS_GPU_MEM_MB`); no-op without a GPU. One model per process; `-c 1`.
- [ ] **Step 1: Resolve and pin** the DECIMER-Image-Segmentation `development` commit hash and MolNexTR `HEAD` hash; write them in `Dockerfile.tf` / `Dockerfile.torch` and in `docs/superpowers/plans/` notes.
- [ ] **Step 2: Write failing test** `test_segment_count_matches_v1_on_s1_fixture`: on the S1 fixture pages (`judges/load/make_fixtures.py` output), total segments == 15, and per page equals v1's offline count from `judges/load/count_segments_offline.py`.
- [ ] **Step 3: Run** in the TF image: `docker compose run --rm worker-segment pytest -m ml tests/workers/test_decimer_segmenter.py -q` — Expected: FAIL.
- [ ] **Step 4: Implement.**
- [ ] **Step 5: Run** — Expected: PASS (CPU, slow is fine).
- [ ] **Step 6: Commit** `feat(v2): DECIMER segmentation worker`

### Task B2: DECIMER OCSR engines (normal and hand-drawn)

**Files:**
- Create: `src/marcus/workers/ocsr/decimer.py`
- Test: `tests/workers/test_decimer_ocsr.py` (`ml`)

**Interfaces:**
- Produces: `DecimerEngine(hand_drawn: bool)` → `predict_SMILES(str(path), confidence=False, hand_drawn=hand_drawn)` (v1 `ocsr_wrapper.py:22-45`), `molfile=None`. The `q.decimer` worker serves both `decimer` and `decimer-hand`; the hand-drawn model loads on its first request only. `version` = installed `decimer` package version (+ `-hand`).
- [ ] **Step 1: Write failing tests** — `test_same_smiles_as_v1_on_three_fixture_segments` (expected SMILES recorded once from the v1 local copy on the same crops, stored in `tests/fixtures/v1_decimer.json`), `test_hand_model_not_loaded_until_asked`.
- [ ] **Step 2: Run** `docker compose run --rm worker-decimer pytest -m ml tests/workers/test_decimer_ocsr.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(v2): DECIMER OCSR engines`

### Task B3: Torch worker image, MolNexTR and MolScribe

**Files:**
- Create: `docker/Dockerfile.torch`, `src/marcus/workers/ocsr/{molnextr,molscribe}.py`
- Modify: `src/marcus/workers/gpu.py` (`limit_torch_memory(fraction: float)`)
- Test: `tests/workers/test_torch_ocsr.py` (`ml`)

**Interfaces:**
- Produces: `MolnextrEngine` (port v1 `ocsr_wrapper.py:48-103`, returns smiles + predicted molfile), `MolscribeEngine` (port v1 `ocsr_wrapper.py:105-183`; checkpoint from `hf_hub_download` baked into the image; device `cuda` when available — the B3 test and D4 judge must show no loss vs v1 on CPU, else keep CPU as v1). Separate compose services `worker-molnextr` (`-Q q.molnextr`) and `worker-molscribe` (`-Q q.molscribe`) from the same image. Weights baked into the image (v1 downloaded 1.06 GB on first call).
- [ ] **Step 1: Write failing tests** — `test_molnextr_same_smiles_as_v1_on_three_segments`, `test_molscribe_same_smiles_as_v1_on_three_segments` (fixtures recorded from v1 like B2).
- [ ] **Step 2: Run** in the torch image — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(v2): MolNexTR and MolScribe workers`

### Task B4: Segmentation and OCSR caches

**Files:**
- Modify: `src/marcus/core/pipeline.py`, `src/marcus/workers/segment.py`, `src/marcus/workers/ocsr/base.py`
- Test: `tests/core/test_caches.py`

**Interfaces:**
- Produces: on `check_pdf` done, if `seg_cache` has `(pdf_sha256, seg_version)`, the planner copies segments (re-saving crops from the cached paper's files if they still exist, else falls back to normal steps) and skips `render_page`/`segment_page`. `ocsr` handler checks `ocsr_cache (image_sha256, engine, engine_version)` before `predict` and writes it after.
- [ ] **Step 1: Write failing tests** — Review Focus 2: `test_same_pdf_twice_same_owner_two_papers_second_from_cache` (second paper has no `segment_page` steps, same segment count, both `done`); `test_ocsr_cache_hit_skips_engine` (engine stub call count 0 on second run); `test_cache_never_exposes_other_owner_ids` (second owner's segments have new ids and paths under its own paper).
- [ ] **Step 2: Run** `uv run pytest tests/core/test_caches.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(v2): segmentation and OCSR caches`

---

## Phase C — Operations

### Task C1: Retention job

**Files:**
- Modify: `src/marcus/workers/cpu.py` (`purge_expired`), `src/marcus/core/celery_app.py` (beat: daily 03:00 UTC)
- Test: `tests/workers/test_retention.py`

**Interfaces:**
- Produces: `purge_expired(session, now) -> int` deletes papers and image jobs with `expires_at < now` (rows cascade, files removed), and cache rows older than 30 days; also removes orphan directories under `data_root/papers` with no DB row and older than 1 day.
- [ ] **Step 1: Write failing tests** — `test_expired_paper_rows_and_files_removed`, `test_fresh_paper_kept`, `test_orphan_dir_removed`.
- [ ] **Step 2–4:** run `uv run pytest tests/workers/test_retention.py -q` (FAIL → implement → PASS).
- [ ] **Step 5: Commit** `feat(v2): 30-day retention job`

### Task C2: Metrics, logs, dashboard

**Files:**
- Create: `src/marcus/api/metrics.py`, `ops/grafana/marcus.json`, `ops/prometheus.yml`
- Modify: `src/marcus/api/main.py` (`/metrics`, served only on the internal port `9100` of the api container), logging config in `src/marcus/core/settings.py`
- Test: `tests/api/test_metrics.py`

**Interfaces:**
- Produces: a `prometheus_client` custom collector that reads Postgres on scrape: `marcus_queue_pending{queue}`, `marcus_queue_running{queue}`, `marcus_step_seconds{kind,engine}` (histogram from the last hour), `marcus_wait_seconds{queue}` (queued_at − created_at), `marcus_first_smiles_seconds` (per paper, last hour), `marcus_step_failures_total{error_class}`, `marcus_disk_free_bytes`. JSON logs with `request_id`, `paper_id`, `step_id` in API, dispatcher, workers.
- [ ] **Step 1: Write failing tests** — `test_metrics_lists_each_queue`, `test_metrics_not_on_public_router` (`/api/v2/metrics` → 404).
- [ ] **Step 2–4:** run `uv run pytest tests/api/test_metrics.py -q` (FAIL → implement → PASS).
- [ ] **Step 5: Commit** `feat(v2): metrics, JSON logs, Grafana dashboard`

### Task C3: Admin CLI

**Files:**
- Create: `src/marcus/cli.py` (entry point `marcus`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `marcus apikey create --label TEXT [--daily-pages N]` (prints the key once), `marcus apikey revoke ID`, `marcus apikey list` (no secrets), `marcus purge --paper ID`, `marcus purge --expired`. Daily page quota enforced in `POST /papers` for API keys (429 above quota).
- [ ] **Step 1: Write failing tests** — `test_create_prints_key_once_and_stores_hash_only`, `test_revoked_key_401`, `test_quota_exceeded_429`.
- [ ] **Step 2–4:** run `uv run pytest tests/test_cli.py -q` (FAIL → implement → PASS).
- [ ] **Step 5: Commit** `feat(v2): admin CLI for API keys and purge`

### Task C4: GPU compose and boot unit

**Files:**
- Create: `docker-compose.gpu.yml`, `ops/systemd/nvidia-compute-default.service`, `backend-v2/README.md` (run, test, deploy)
- Test: `tests/test_compose_config.py`

**Interfaces:**
- Produces: GPU override with nvidia device reservations for `worker-segment`, `worker-decimer`, `worker-molnextr`, `worker-molscribe`; `MARCUS_GPU_MEM_MB`: segment 6144, decimer 4096; `MARCUS_TORCH_MEM_FRACTION`: molnextr 0.09, molscribe 0.09 (≈ 3 GB each of 32 GB); `dcgm-exporter` service on the internal network. The systemd unit runs `nvidia-smi -i 0 -c DEFAULT` at boot (applied on switch day only).
- Network rule (spec: workers reach the internet only for the DOI lookup): compose network `internal` has `internal: true`; only `nginx` and `worker-cpu` also join network `egress`.
- [ ] **Step 1: Write failing test** — `test_gpu_override_budget_under_20gb` parses `docker compose -f docker-compose.yml -f docker-compose.gpu.yml config` and checks the sum of budgets ≤ 20 GB, that only `nginx` publishes ports, and that only `nginx` and `worker-cpu` join a non-internal network.
- [ ] **Step 2–4:** run `uv run pytest tests/test_compose_config.py -q` (FAIL → implement → PASS).
- [ ] **Step 5: Commit** `feat(v2): GPU compose override and boot unit`

---

## Phase D — Judges on v2

### Task D1: v2 judge client

**Files:**
- Create: `judges/common/client_v2.py`
- Modify: `judges/load/run_goldset.py` (`--client v1|v2`, default v1)
- Test: `judges/load/test_client_v2.py`

**Interfaces:**
- Consumes: the v2 API (A4, A10, A11).
- Produces: `run_paper(pdf_path: Path, engine: str, *, base_url: str) -> PaperRun` with the same `PaperRun` and JSONL fields as `client_v1.py` (`build="v2-<git short hash>"`); fills `segment_ms` from step timestamps, `page_errors` from failed `render_page`/`segment_page` steps with `error_class`, `ocsr_ms` per segment. Uses SSE, falls back to polling every 2 s; refuses production hosts through `common/target.py`.
- [ ] **Step 1: Write failing tests** with `httpx.MockTransport`: `test_run_paper_maps_steps_to_paperrun`, `test_failed_page_becomes_page_error`, `test_refuses_production_host`.
- [ ] **Step 2–4:** `cd judges && uv run pytest load/test_client_v2.py -q` (FAIL → implement → PASS).
- [ ] **Step 5: Commit** `feat(judges): v2 client with the v1 PaperRun contract`

### Task D2: Security judge on v2

**Files:**
- Create: `judges/security/v2/conftest.py`, `judges/security/v2/test_*.py` (one per v1 test file), `judges/security/v2/README.md`
- Test: the suite itself

**Interfaces:**
- Produces: for each of the 17 v1 tests, a v2 test that attacks the same weakness on the v2 route (mapping table in the README: v1 route → v2 route). Each test first calls the v2 route with a valid request and asserts a non-404 success, so a missing route fails. New test `test_xff_spoof_cannot_escape_rate_limit`. The stored-XSS browser test is marked `needs_frontend` and skipped with that reason until the React UI exists; its API half (`display_name` returned only as JSON with `application/json`) runs now. `MARCUS_FS_PROBE=docker:<v2 api container>` for file checks.
- [ ] **Step 1: Write the v2 tests.**
- [ ] **Step 2: Run on v1 for sanity:** v2 tests against v1 must FAIL at the existence check (route missing), proving no vacuous pass.
- [ ] **Step 3: Run on the local v2 stack:** `cd judges && MARCUS_BACKEND_URL=http://localhost:18090 MARCUS_FS_PROBE=docker:marcus-v2-api-1 uv run pytest security/v2 -v` — Expected: all pass except the one `needs_frontend` skip.
- [ ] **Step 4: Fix v2** for any failure (each fix gets its own unit test in `backend-v2/tests`).
- [ ] **Step 5: Commit** `feat(judges): security suite ported to v2 routes`

### Task D3: Load judge on v2

**Files:**
- Create: `judges/load/v2_adapter.py`
- Modify: `judges/load/scenarios.py` (`--client v1|v2`; adds `first_segment_start_s` and `depict_p95_ms` measurements; S2 for v2 runs full OCSR, `--big-cap` ignored with a log line)
- Test: `judges/load/test_v2_adapter.py`

**Interfaces:**
- Produces: the adapter maps each v1 call used by `scenarios.py` (session create/heartbeat, `generate_smiles`, `extract_segments`, health) to its v2 form (cookie owner, `POST /images`, `POST /papers` + events, `/api/v2/health`). S4 for v2 measures the full pipeline.
- [ ] **Step 1: Write failing tests** (MockTransport) — `test_adapter_maps_every_v1_call_used_by_scenarios` (grep the call list from `scenarios.py`; each has a mapping).
- [ ] **Step 2: Implement** and pass.
- [ ] **Step 3: Run locally** with the fake-engine stack: `uv run python load/scenarios.py --target local --client v2 --scenarios S2 S3 S4 S5` and with the real CPU workers for S1 only — record results in `load/results/`.
- [ ] **Step 4: Commit** `feat(judges): load scenarios run against v2`

### Task D4: GPU test session on jarvis

**Files:**
- Create: `judges/stack/docker-compose.v2-jarvis.yml`, `judges/results/2026-xx-xx-gpu-session.md`

Steps (no code; each is a checkable action):

- [ ] **Step 1:** Read (only) the outer reverse proxy setup for `marcus.decimer.ai` (141.35.136.10, or ask the owner for access): trusted proxy address, body limit, SSE buffering, TLS end. Write the values into `backend-v2/README.md`.
- [ ] **Step 2:** Copy the v2 images to jarvis (`docker save | ssh ... docker load`), separate compose project `marcus-v2-test`, ports bound to `127.0.0.1` only. Tell the owner the session starts.
- [ ] **Step 3:** Stop v1 (`docker stop marcus-backend`); note the time. Run the v1 baseline on GPU with the v1 judge copy: S1 + S2 fixtures, all 4 engines, and 2 gold-set papers that draw structures.
- [ ] **Step 4:** Stop the v1 judge copy; start `marcus-v2-test`; run: security v2 suite, load S1–S5 (v2), fixture accuracy, 2 gold-set papers, all engines.
- [ ] **Step 5:** Stop `marcus-v2-test`; start v1 (`docker start marcus-backend`); check `curl http://127.0.0.1:9000/health` on jarvis gives 200; report the downtime.
- [ ] **Step 6:** Write the results table (v1 vs v2, every gate in spec §3) into `judges/results/...-gpu-session.md`. Any failed gate goes back as a task.
- [ ] **Step 7: Commit** `docs(judges): v1 vs v2 GPU session results`

---

## Phase E — Annotation with a local LLM (blocked: needs the owner's training data)

### Task E1: Annotation eval harness

**Files:**
- Create: `judges/annotation/{README.md,split.py,score.py,test_score.py}`

**Interfaces:**
- Produces: `split.py` makes a fixed held-out test part (seeded, 20 %) of the owner's training data; `score.py` computes label-level precision, recall, F1 per label and micro-F1, comparing extracted values after the same normalization v1 `find_positions` uses (`split(", ")`, strip `"' "`, drop `"nan"`).
- [ ] **Step 1–4:** tests for the scorer on hand-made examples (FAIL → implement → PASS).
- [ ] **Step 5:** Record the v1 fine-tuned model's F1 on the held-out part, only if a working OpenAI key exists; else the bar is set from the labels' own baseline with the owner.
- [ ] **Step 6: Commit** `feat(judges): annotation scorer`

### Task E2: llama.cpp service and the annotate step

**Files:**
- Create: `src/marcus/workers/annotate.py`, `docker-compose.llm.yml`, `src/marcus/api/routes/annotations.py`
- Test: `tests/workers/test_annotate.py`

**Interfaces:**
- Produces: `annotate` handler on `q.llm` (calls the llama.cpp server's OpenAI-style `/v1/chat/completions` with the v1 system prompt "Extract the compound information from the Paragraph."; parses the label dict; computes offsets like v1 `find_positions`); `POST /api/v2/papers/{id}/annotate`, `GET /api/v2/papers/{id}/annotations`. Model file chosen in E3.
- [ ] **Step 1–4:** tests with a stub server (FAIL → implement → PASS).
- [ ] **Step 5: Commit** `feat(v2): annotate step with a local LLM server`

### Task E3: Pick the model by measurement

- [ ] **Step 1:** Run 2–3 candidate 7–9B GGUF models (Q8 or Q5, ≤ 10 GB) on the held-out part (CPU locally on a small sample, GPU in a test session).
- [ ] **Step 2:** Keep the best one whose micro-F1 ≥ the E1 bar. If none reaches it, write a LoRA fine-tune task and stop for the owner's decision.
- [ ] **Step 3: Commit** the chosen model name and scores in `judges/annotation/README.md`.
