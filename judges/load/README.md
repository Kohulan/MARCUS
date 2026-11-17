# Load and fairness judge

Question: how long does a paper take, and does a small paper wait behind a big one? The same scenarios run
against v1 today and against the rebuilt service (v2) later; only the client adapter (`common/client_v1.py`
vs a future `common/client_v2.py`) and the target change.

`scenarios.py --client v2` runs the same scenarios against backend-v2 (`v2_adapter.py` maps each v1 call, see
"v2" below). First v1 measurements are in the last sections.

## Files

| File | What |
|---|---|
| `../common/client_v1.py` | `run_paper(pdf, engine, base_url=...) -> dict`: one paper through v1 the way the browser does it. Returns one run line in the shared format plus extra fields. |
| `../common/remote.py` | read-only `docker logs` and `nvidia-smi` (local, or jarvis over ssh with a command whitelist); parser for the backend's hidden page errors. |
| `guard_jarvis.py` | safety guard for jarvis (below). |
| `make_fixtures.py` | synthetic PDFs with a known number of RDKit-drawn structures: 15, 190, 2,020 (`data/fixtures/`, plus a `.json` sidecar with the expected structure of every slot). |
| `run_goldset.py` | gold-set papers x engines through the client into `runs/<name>.jsonl`; resumable. |
| `scenarios.py` | S1 to S5, `--client v1|v2`. Raw results in `results/<target>[_v2]_<scenario>_<time>.json`. |
| `v2_adapter.py` | the scenarios' calls in v2 form (owner cookie, `/images`, `/tools/depict`, `/api/v2/health`); papers via `../common/client_v2.py`. |
| `report.py` | Markdown tables from the newest result files (`uv run python load/report.py jarvis`). |
| `count_segments_offline.py` | counts segments of a big PDF with one process per page, inside the image, no HTTP (used for the 2,020 fixture). |
| `docker-compose.local-private.yml` | a private local copy of the backend image on :19100 (see "Local copy"). |
| `docker-compose.jarvis-single-thread.yml` | optional override for the jarvis judge copy (owner decides), see "Jarvis runbook". |
| `shim/sitecustomize.py` | makes v1 segment with one thread (see "Local copy"). |
| `test_guard.py`, `test_client_v1.py`, `test_client_v2.py`, `test_v2_adapter.py` | offline tests: guard, ssh whitelist, log parser, client call sequence (`uv run pytest load -q`). |

`data/` is git-ignored; `results/` holds the JSON (commit what you want to keep).

## How to run

```bash
cd judges
# 0. private local copy (CPU, from the production image); wait until healthy (3-5 min)
docker compose -p marcus-judge-load -f load/docker-compose.local-private.yml up -d

# 1. fixtures (seconds)
uv run python load/make_fixtures.py                      # synth_015 / synth_190 / synth_2020 (.pdf + .json)
uv run python load/make_fixtures.py --check 15 --base-url http://localhost:19100   # segments v1 finds, no OCSR

# 2. gold set. The full run is the lead's to launch: --split all = 100 papers x 3 engines.
uv run python load/run_goldset.py --name v1-local-smoke --papers PMC3229060 PMC7689812 --base-url http://localhost:19100 --reuse-segmentation
uv run python goldset/score.py runs/v1-local-smoke.jsonl --out /tmp/score.json --md /tmp/score.md
uv run python load/run_goldset.py --name v1-jarvis --base-url http://localhost:29000 --split dev   # guarded, resumable

# 3. scenarios (results in load/results/)
uv run python load/scenarios.py --target local  --scenarios S1 S4
uv run python load/scenarios.py --target jarvis --scenarios S1 S2 S5 S3 S4         # GPU copy, guarded
uv run python load/scenarios.py --target jarvis --scenarios S2_2020                # optional, long
uv run python load/report.py jarvis

uv run pytest load -q                                    # offline tests
```

`--target local` means the private copy on :19100; `--base-url` overrides. Jarvis is `http://localhost:29000`
through the SSH tunnel. `common/target.py` refuses production hosts. Useful scenario options: `--engine`
(S2-S5, default decimer), `--big-cap` (S2: OCSR only the first N segments of the big paper, default 80),
`--s2-small-count`, `--s4-size`, `--s4-repeats`, `--s5-seconds`, `--s1-repeats`.

### Client options worth knowing (`run_paper`)

| Option | Default | Meaning |
|---|---|---|
| `ui_extras` | False | also do what the page does around the pipeline: `POST /session/create`, `extract_doi` (a second upload of the PDF), one `get_segment_image` per segment, one `depiction/generate` per structure. |
| `on_429` | `retry` | the backend rate limiter answers 429 (about 20 requests/min per client, all endpoints in one bucket). The UI shows an error row; the client waits `Retry-After` and retries, so recognition results stay comparable. The events are recorded; `fail` gives UI behaviour. |
| `reuse_upload` | False | stable upload name and bytes, so a second engine reuses the first segmentation (what a user does when switching engine). Default is a unique name and unique bytes per run, because the backend reuses uploads by file name and caches segmentation by MD5 of the PDF. |
| `max_segments` | None | OCSR only the first N listed segments (0 = segmentation only). |
| timeouts | UI values | `segment_timeout_s=300`, `ocsr_timeout_s=60` as in the frontend; scenarios use 3600 / 900 so the wait is measured, not cut. |

### The run line

`run_paper` returns the shared format of `judges/README.md`. Conventions: `segment_id` is `page_<p>_<i>` from the backend's file
name `page_<p>_<i>_segmented.png`, `page` is the **0-based** page index (same numbering as `page_errors[].page` and the
backend log), `page_number` is the 1-based number the UI shows; `pdf_sha256` is the hash of the original file (it joins with
the manifest), `upload_sha256` the hash of what was sent (a nonce is appended after `%%EOF`). Extra fields (ignored by
`goldset/score.py`): `timings_ms`, `http_calls`, `http_calls_by_step`, `rate_limit_events`, `server_segment_s`, `listed_pages`,
`backend_crash`, `no_segments` (a paper that draws no structure is a result, not an error), `fatal_error`, `aborted`,
`segments[].fallback / first_error / rate_limited / t_start_ms`. A client uses no keep-alive connections, like the nginx in
front of production (guess: with keep-alive the backend dropped one in-flight request in a 13-call run).

## HTTP calls per paper (what the client does, matches the frontend code)

N = number of segments found.

| Step | Call | Count |
|---|---|---|
| segmentation | `POST /latest/decimer/extract_segments` (multipart `pdf_file`, `collect_all=true`) | 1 |
| listing | `GET /latest/decimer/list_directory/<stem>/all_segments` | 1 |
| recognition | `POST /latest/ocsr/generate_with_depiction` (image_path, engine, svg depiction), sequential | N |
| fallback | `POST /latest/ocsr/generate_both` after any failed first attempt | 0 to N |
| **core total** | | **2 + N** (+ fallbacks) |
| browser extras (`ui_extras`) | session create 1, `extract_doi` 1, segment image N, `depiction/generate` N | 2 + 2N |
| **with browser extras** | | **4 + 3N** |

Examples: 15 structures = 17 core / 49 with extras; the production median paper (about 15 segments) the same;
190 structures = 192 / 574; 2,020 structures = 2,022 / 6,064. Heartbeats (websocket or HTTP every 15 s) are not
counted. The UI's own order is also reproduced: segments are processed in the order the server lists them
(no sorting), one at a time.

## v2 (`--client v2`, `v2_adapter.py`)

```bash
# fake stack (backend-v2: docker compose -p marcus-v2 -f docker-compose.yml -f docker-compose.fake.yml up -d)
uv run python load/scenarios.py --target local --client v2 --engines fake --engine fake --scenarios S1 --tag fake
uv run python load/scenarios.py --target local --client v2 --engine fake --scenarios S2 S3 S4 S5
# real engines (stack without the fake override), S1 only on CPU
uv run python load/scenarios.py --target local --client v2 --scenarios S1
# jarvis (D4): the guard runs for --target jarvis on any tunnel port. In the owner's GPU window with v1 production
# stopped on purpose add --prod-stopped: the guard then requires marcus-backend to STAY stopped (State.Status exited/
# created) instead of healthy; free GPU memory >= 3 GiB and the GPU-time ledger (JUDGE_GPU_BUDGET_S) still apply.
uv run python load/scenarios.py --target jarvis --client v2 --base-url http://localhost:<port> --prod-stopped --scenarios S1 S2 S3 S4 S5
```

Default base URLs: local `http://localhost:18090` (the v2 nginx), jarvis `http://localhost:29090` (pass `--base-url`).
Results: `results/<target>_v2_<scenario>_<time>.json`; the S2 slowdown uses the newest v2 S1 of the same engine.

| v1 call (scenarios.py) | v2 form |
|---|---|
| `GET /health` | `GET /api/v2/health` |
| `POST /session/create` | a browser owner: `GET /api/v2/papers` without a cookie, cookie `marcus_owner` from Set-Cookie (Secure, so sent by hand) |
| `POST /session/heartbeat/{sid}` | `GET /api/v2/papers` with the owner cookie |
| `DELETE /session/remove/{sid}` | none (no sessions) |
| `POST /latest/ocsr/generate_smiles` | `POST /api/v2/images` + `GET /api/v2/images/{id}` every 0.25 s until done/failed |
| `client_v1.run_paper` | `client_v2.run_paper` (`POST /api/v2/papers`, SSE events, `GET /papers/{id}`, `GET /papers/{id}/steps`) |
| page errors from docker logs | failed `render_page` / `segment_page` steps in each record |
| (v2 only) | `POST /api/v2/tools/depict` probe every `--depict-period-s` (2 s) in S2, S3, S5: `depict_p95_ms` |

**Cold OCSR cache (R21).** v2 caches OCSR per (crop or image bytes, engine, engine version), image jobs included, so a
fixture or probe image seen before is answered in about 0 ms. Before every scenario, S1 run, S4 arm and the S5 S2 part the
judge empties the cache table of the TEST stack: `docker exec <container> psql -U marcus -d marcus -c 'DELETE FROM
ocsr_cache'` (`--cache-pg-container`, env `MARCUS_TEST_PG_CONTAINER`; local default `marcus-v2-postgres-1`; on jarvis the
`marcus-v2-test` project's postgres, required; `DOCKER_HOST` reaches a remote docker). Production, v1 judge and non-Postgres
names are refused, and on jarvis only `marcus-v2-test*`. Each script/warm-up image gets 4 random near-white corner pixels,
so no two calls share bytes. Every paper records `ocsr_cache_hits` (the `cached` flag, or an engine time of 0 ms) and every
image job its engine `ms`. A timed run or arm with a hit, or with a failed `check_pdf`/`docling`/`doi` step (`failed_steps`:
its wall is then a time limit), gets `timing.valid: false` with the reasons; S4's concurrent-vs-sequential comparison is
then `valid: false` with no `concurrent_faster`. `--allow-warm-cache` (off by default) skips the clearing and accepts hits.
Every v2 result has `ocsr_cache.cleared`, `validity` and `v2_created` (paper and image-job ids). S4 v2 submits the two
halves of the fixture as its two papers (a second copy of one PDF has the same crops).

**Guard trip on v2.** The pipeline runs on the server, so closing clients is not enough: the guard deletes every live
paper as its owner (`DELETE /api/v2/papers/{id}`, `client_v2.cancel_papers`), stops posting image jobs and polling
(`v2_adapter.abandon_all`; the open jobs are listed, v2 has no image-job DELETE), and every probe and the S3/S5 idle and
alone phases end at once. What was cancelled goes into `guard.cancelled`.

Differences: S2's big paper runs full OCSR (`--big-cap` ignored, logged); S3 and S4 use `--engine`; S4 runs the full
pipeline (spec: two papers at once must finish faster than one after the other); every paper is its own owner; the S5
script user moves to a new owner before its 10th upload per owner (the per-owner limit is 10 uploads per minute; v1's
script user had its own rate-limit bucket for the same reason). New fields: `first_segment_start_s`, `first_smiles_s`,
`ocsr_done_s` (v1-comparable end: a v2 paper's `wall_s` also includes docling: 77-89 s for synth_015 on the loaded CPU
host, and the 24-page synth_190 hit docling's time limit at about 330 s),
`segment_compute_s`, `ocsr_compute_p50_ms`, `ocsr_cache_hits`, `depict_p95_ms`, probe `n_503`, `host_load`
(1/5/15-min load average at start and end), `v2_http_errors` (every answer >= 400 the adapter saw) and `v2_breaker_503`
(`503 {"detail": "service unavailable"}`: the rate limiter's circuit breaker was open). The fake stack makes 2
segments per page (the 15-structure fixture gives 10, the 190 one 48), so fake-stack segment counts are not recall.

## Guard (`guard_jarvis.py`)

Production runs on the same V100. Before every scenario and every 30 s during it (read-only, over ssh):
`docker inspect -f '{{.State.Health.Status}}' marcus-backend` must be `healthy` and free GPU memory at least
3 GiB. If either fails, or the check itself cannot run (fail closed), the guard sets an abort flag, closes every
open HTTP client of the client, and writes the reason to `results/guard_events.jsonl` and into the scenario's result
(`guard.trip_reason`). It keeps a ledger of GPU test time in `results/gpu_time_ledger.json` and refuses to start
when the 45 min budget is used up (`JUDGE_GPU_BUDGET_S`). Only the commands whitelisted in `common/remote.py` can be
sent (tested); nothing is ever started, stopped, restarted or changed. Every sample (production health, GPU free/used/
utilisation) is stored in the scenario result under `guard.events`.

## What the numbers mean

All times are milliseconds measured by the client around each HTTP call. Percentiles use linear interpolation on the
raw samples; the raw samples are in the JSON.

| Name | Meaning |
|---|---|
| `wall_ms` | first byte uploaded to last OCSR answer of the paper (what the user waits). |
| `segment_ms` | the `extract_segments` call: upload, page rendering, DECIMER segmentation. When another request holds the server this includes the wait. |
| `ocsr_ms` per segment | one `generate_with_depiction` call (plus the fallback call if the first failed); `p50`/`p95` over the segments of a paper. |
| `server_segment_s` | the backend's own `get_segments_with_bbox took N seconds` line(s) in the run's log window; compare with `segment_ms` to see queueing. |
| `page_errors` | `Error processing page N` lines the backend prints (the API hides them). N is the 0-based page. `kind: exception` (for example PyramidROIAlign) means the page's work failed and its segments are lost; `kind: timeout_30s` (CPU only) means the main thread gave up waiting after 30 s while the worker finishes and still writes its files. Attribution is by log time window: exact for runs that do not overlap. |
| lost page | a fixture page that holds structures but produced no segment file (exact: the fixture sidecar knows the count per page). For gold-set papers only `page_errors` is available. |
| `backend_crash` | the log window contains glibc/JVM/TensorFlow crash lines (`SIGSEGV`, `corrupted size vs. prev_size`, ...). The process is dead or wedged afterwards. |
| slowdown (S2) | small-paper `wall_ms` in S2 divided by the same engine's S1 `wall_ms`. |
| `rate_limit_events` | HTTP 429 answers (see `on_429`). |

### Scenarios

* **S1 baseline.** `synth_015` (15 structures, 5 pages) alone, per engine. One warm-up OCSR call per engine first (first
  use loads weights); its time is reported separately as the cold-start cost.
* **S2 fairness.** The 190-structure paper (24 pages) starts; 5 s later the 15-structure paper is submitted
  (`--s2-small-count N` adds N-1 more, 10 s apart). Reported: small-paper `wall_ms`, its `extract_segments` time (queue
  wait + own work), slowdown vs S1. The big paper's OCSR is capped (`--big-cap`, default 80) to save GPU time; its
  segmentation is complete. `S2_2020` uses the 2,020-structure paper (169 pages) as the big one.
* **S3 responsiveness.** `/health` and `POST /session/heartbeat/<id>` once a second, open loop (probes overlap when the
  server is blocked, like a browser timer), 15 s idle before and after, and during the segmentation of the
  190-structure paper. p50/p95/max, idle vs during. Tests whether segmentation blocks the event loop. Probes that never
  get an answer (server crashed) are counted as errors and their waiting time is the lower bound.
* **S4 concurrency correctness.** Part 1: two copies of the same multi-page fixture (different bytes) segmented one after
  the other (`sequential`) or at the same moment (`concurrent`), repeated. Part 2 (control): one-page PDFs, so no thread
  pool inside a request, again sequential and concurrent. Reported: segments found, lost pages, page errors, and how many
  error pages share a batch of 4 (the backend renders pages in a thread pool of 4 that shares one Keras model).
* **S5 script user.** `generate_smiles` with an uploaded PNG, one call every 3.5 s after the previous answer (closed
  loop), alone for 60 s, then during an S2 run. Own rate-limit bucket (`X-Session-ID`).

## Targets the rebuild (v2) must beat

From the plan:

1. A 15-structure paper finishes in **under 30 s (p95)** while a 2,020-structure paper is running (S2_2020 with several
   small papers, `--s2-small-count`).
2. **Zero lost pages** (S4: every page that holds structures yields segments, no `page_errors`, sequential and concurrent
   give the same segment counts; gold-set runs: no `page_errors` in any paper).
3. **Health p95 under 200 ms** while a heavy paper is processed (S3: `/health` and heartbeat).

Suggested additions (mine, not in the plan): `generate_smiles` p95 during a big paper within 2x of its idle p95 (S5); no
HTTP 429 for a single user doing the normal UI flow; no backend crash in any scenario.

## Local copy

The shared local copy on :19000 is used by other judges at the same time (the security tests start 2-minute docling
jobs that block the one event loop), so timings there are not clean. `docker-compose.local-private.yml` starts a second,
private copy of the same image on :19100 (own uploads folder, CPU only).

**It runs with `shim/sitecustomize.py`.** v1 renders pages in a thread pool sized from the machine's RAM
(`min(4, GiB of RAM)`), so on any real machine 4 threads share one fitz document and one Keras model. On the CPU copy
that crashed the backend process on every PDF with 2 or more pages that we tried (5 of 5 attempts: glibc `corrupted size vs.
prev_size`, TensorFlow protobuf `SIGSEGV`), after which the container is dead or wedged. The shim reports 1 GiB of RAM to
the app, so v1 takes its own low-memory path (one worker thread). No app code changes. Consequences: local runs are
stable but cannot show the intra-request thread race (S4 local shows serialisation of concurrent requests only), and CPU
page rendering takes about 28 s per page, so the backend's 30 s per-page limit sometimes fires (`timeout_30s`, pages not
lost). Remove the two shim lines in the compose file to run v1 exactly as shipped (and watch it crash).

## Jarvis runbook

The judge copy on jarvis (`marcus-judge-backend`) has no restart policy. On 2026-11-16 at 11:02 UTC it crashed during
the 24-page segmentation of S3 (see results) and stays down. The load judge must not touch containers, so the owner
restarts it: `docker restart marcus-judge-backend`, or the compose command in the header of
`docker-compose.jarvis-single-thread.yml` to also make it single-threaded and give it `restart: unless-stopped`.
Recommended: run S2, S5 and S3 (blocking, fairness; need a copy that survives a 24-page paper) on the single-thread
copy, and S1, S4 and the gold set on the as-shipped copy, where lost pages and crashes are part of the result. If the
as-shipped copy dies, `scenarios.py` stops with "backend not answering /health" and `run_goldset.py` stops after 2
consecutive connection failures; restart and rerun with the same `--name` to resume.

## v1 behaviour that shapes the results (read from the code, then measured)

* `extract_segments` and the OCSR endpoints are `async def` but call blocking code, so one segmentation or one OCSR call
  blocks the whole event loop, and every other request, for its full duration (S3).
* Segmentation renders pages in a `ThreadPoolExecutor` (up to 4 threads) that shares one `fitz` document and one Keras
  Mask R-CNN model. Failed pages are `print`ed and silently dropped; some failures corrupt the heap and kill the process.
* The backend caches segmentation by MD5 of the PDF and reuses uploads by file name (a glob on the file stem, so a
  name that is a prefix of another also matches), so every client run uses a unique name and unique bytes.
* The rate limiter counts all endpoints in one bucket per client IP (or `X-Session-ID`): 15 requests + 5 burst per
  60 s for OCSR and for most other paths. The session middleware is bypassed for `/latest` and `/v1` (its exempt list
  contains `/latest`), so no session is needed to call the API.
* The production nginx rewrites `/api/latest/...` to `/v1/...` and limits bodies to 10 MB (`client_max_body_size`):
  gold-set PDFs above 10 MB (for example PMC9259500, 48.7 MB) cannot be uploaded through the web UI.

## First measurements (v1, 2026-11-16)

Fixtures: v1 finds every structure when no page fails: `synth_015` 15 of 15 (5 pages), `synth_190` 190 of 190 (24 pages,
8 per page, API on the local single-thread copy), `synth_2020` 2,020 of 2,020 (169 pages, 12 per page; counted offline with
`count_segments_offline.py`, one process per page, same library call as the backend). The failures below are therefore
not detection misses; they are lost pages.

### Jarvis (shared V100, v1 as shipped, 4 page threads), result files `results/jarvis_*.json`

| Scenario | Result |
|---|---|
| S1 `synth_015`, decimer | wall 56.6 s, segmentation 21.5 s, 15 of 15 segments, OCSR p50 1.6 s / p95 5.0 s, no page error |
| S1 molnextr | wall 69.5 s, segmentation 16.0 s, **9 of 15 segments, pages 0 and 1 lost (PyramidROIAlign)**, OCSR p50 5.5 s / p95 8.2 s |
| S1 molscribe | wall 40.7 s, segmentation 9.8 s, **9 of 15 segments, pages 1 and 3 lost (PyramidROIAlign)**, OCSR p50 2.9 s / p95 5.4 s |
| first call of an engine (warm-up) | decimer 0.9 s (already loaded by the smoke test), molscribe 18.4 s, **molnextr 149.5 s** (the backend downloads `molnextr_best.pth`, 1.06 GB, and builds the model on the first request) |
| S3 `synth_190` segmentation | idle `/health` p95 9.7 ms, heartbeat 9.1 ms. During segmentation **no probe was answered for 36 s** (38 of 38 probes waited until the backend crashed; latency of the oldest 36.5 s, p50 18 s). 9 page errors on 9 of 24 pages (PyramidROIAlign, DetectionLayer), then **SIGSEGV: the judge container exited** after 38 s (see Jarvis runbook). |
| S2, S4, S5 | not run: the judge copy was down after S3 |

Guard: 20 checks over 4 runs (including a 1-page smoke test), no trip, no guard event file. Production stayed `healthy`; free
GPU memory 4.7 to 5.2 GiB while the judge copy was loaded (rule: at least 3 GiB; the judge copy held about 10 GB: 27.7 to 17.6 GB
used when it crashed), 14.5 GiB free after its crash. GPU test time used: 473 s of the 45 min budget (ledger).

Is the "concurrent use of one shared model causes PyramidROIAlign" guess right? Partly. The errors appear with **one paper
alone** (S1, S3: no other request existed), so concurrent requests are not needed. They cluster inside the 4-page batches of
one request: S3 error pages 0,1 | 8,10,11 | 16,17,18 | 20 (batches 0-3, 8-11, 16-19, 20-23); S1 pages (0,1) and (1,3); the
production log sample showed 2,3 and 8,9. That fits the guess **"the 4 page threads of one request share one Keras model"**
(guess: the exact race is not proven; on the single-thread CPU copy no exception-type page error appeared in about 20 segmentations, only
30 s timeouts; but that is CPU, not the GPU path). Two requests cannot overlap anyway because the endpoint blocks the event loop (S4 local: wall of a concurrent
pair equals the sum of the two segmentation times).

### Local CPU copy (private copy, single-thread shim, machine shared with other jobs: shapes only, not production speed)

| Scenario | Result |
|---|---|
| S1 `synth_015`, decimer (OCSR of the first 6 of 15 segments) | wall 231 s, segmentation 98 s, 15 of 15 segments listed, OCSR p50 15.5 s / p95 44 s (CPU); molnextr and molscribe not run locally: their first request builds the model on CPU, several minutes under the shared load |
| S3 `synth_015` (163 s of segmentation) | idle p95 24 ms; **during: health p50 83 s, p95 155 s, max 162 s** (= the whole segmentation; nothing answered); heartbeat the same |
| S4 two papers, `synth_015` x 2 | sequential wall 223 s (server 213 s), concurrent wall 224 s (server 219 s), 15 of 15 segments each, no lost page: the backend runs them one after the other |
| S4 one-page PDFs x 4 | sequential 155 s, concurrent 97 s (server 154 s / 97 s), 8 of 8 each; the only page error was a CPU 30 s timeout whose segments were still written |
| S2 smoke (big = `synth_015`, small submitted after 5 s; CPU) | small paper `extract_segments` waited 387 s (big segmentation 201 s, then its own); wall **880 s**; health 99.9 % of probes over 200 ms (max 560 s); the big paper's own listing call waited behind the small paper's segmentation |
| gold-set smoke (`PMC3229060`, `PMC7689812` x 3 engines, `--reuse-segmentation --max-segments 1..4`) | `runs/v1-local-smoke.jsonl`; `goldset/score.py` reads it (2 of 50 dev papers per engine). `PMC3229060` draws no structure: 0 segments, recorded as `no_segments`, not as an error. `PMC7689812`: 16 of 16 listed, 6 pages, DECIMER OCSR of the first 4. On CPU the first MolNexTR request needs about 5 min to build the model and a single image takes more than 5 min, so local engine comparisons beyond DECIMER are not practical. |

Crashes of the as-shipped (4 threads) CPU copies: 5 of 5 attempts on PDFs with 2 or more pages (2 on the shared :19000 copy,
3 on private copies; a 1-page PDF worked). The GPU copy: 1 crash in 4 multi-page runs (the 24-page one).
