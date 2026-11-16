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
