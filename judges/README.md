# MARCUS judges

Outside judges for the MARCUS rebuild. Each judge must give a number or a
pass/fail for the current build (v1) **and** for the rebuilt service (v2),
with no change to the judge itself. Only the client adapter changes.

| Judge | Folder | Question it answers |
|---|---|---|
| Security | `security/` | Can an attacker read or write files, run script in the page, or break other users' work? Each test asserts the SAFE behaviour, so it FAILS on a vulnerable build. |
| Load and fairness | `load/` | How long does a paper take, and does a small paper wait behind a big one? Replays the production traffic shape. |
| Gold set | `goldset/` | How many of the structures that COCONUT records for a paper does MARCUS find in that paper, per OCSR engine? |

## Rules

- Never point a judge at production (`marcus.decimer.ai`, `jarvis.ian.uni-jena.de`,
  port 9000 on the public host). `common/target.py` refuses those hosts.
- Never copy user uploads off production. Test PDFs come from open-access
  sources only (`goldset/`).
- Downloaded PDFs and data live in `*/data/` and are git-ignored. Manifests
  (DOI, source URL, sha256) are committed, so anyone can fetch the same files.

## Local copy of production

`stack/docker-compose.yml` runs the exact production images (copied from
jarvis with `docker save`, image IDs in `stack/IMAGES.md`), CPU only:

- backend: http://localhost:19000 (docs at `/latest/docs`)
- frontend: http://localhost:18080 (nginx proxies `/api` to the backend)

## Shared run format (`common/`)

`common/client_v1.py` drives the current build the way the frontend does.
A v2 client will expose the same function:

```python
run_paper(pdf_path, engine, *, base_url) -> PaperRun
```

Each run is one JSON line (`runs/*.jsonl`):

```json
{"paper_id": "...", "pdf_sha256": "...", "engine": "decimer|molnextr|molscribe",
 "build": "v1-976396a5", "started_at": "ISO-8601", "wall_ms": 0,
 "segment_ms": 0, "pages_total": 0, "pages_with_segments": 0,
 "page_errors": [{"page": 0, "error": "..."}],
 "segments": [{"segment_id": "page_3_1", "page": 3, "smiles": "...",
               "ocsr_ms": 0, "error": null}]}
```

### v1 vs v2 key meanings

The same key means the same thing in both builds; numbers only v2 can give have their own key.

| Key | v1 (`client_v1`) | v2 (`client_v2`) |
|---|---|---|
| `segment_ms` | wall time of the `extract_segments` call: upload to all segments listed | client upload round trip + (last `segment_page` finished_at - paper's first step created_at): upload, check_pdf, render and queue wait included. None if the paper has no `segment_page` step (segmentation cache hit) |
| `segment_compute_ms` | None (not available) | first `segment_page` started_at to last finished_at (worker time only) |
| `segments[].ocsr_ms` | client round trip of the OCSR call (incl. fallback, 429 waits) | newest `ocsr` step created_at to finished_at: queue wait, retries, timeouts included. None when the timing is missing; never replaced by the engine time |
| `segments[].ocsr_compute_ms` | None | the engine's own ms (0 for a cache hit) |
| `ocsr_cache_hits` | 0 | predictions served from the v2 OCSR cache (`cached` flag on the prediction) |

**v2 timing runs need a cold OCSR cache.** The cache is keyed by the crop image, engine and engine version, so
re-running a paper with the same engine (or `run_goldset --retry-failed`) serves OCSR from the cache in about
0 ms; the unique upload bytes only defeat the PDF-level segmentation cache. Time a paper+engine on its first
run or on a fresh stack, and check `ocsr_cache_hits == 0` (`run_goldset` warns otherwise). Accuracy (SMILES) is
unaffected by the cache. There is no cache-bypass switch in the backend, on purpose.
