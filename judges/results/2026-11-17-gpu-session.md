# v1 vs v2 GPU session on jarvis (Task D4, 2026-11-17, with fix round 1)

One Tesla V100-PCIE-32GB (sm_70, driver 580.178.04, compute mode Default), 32 cores, 376 GB RAM. Production v1 was
stopped by the owner before the session (maintenance page `marcus-maintenance` on 8080/9000 since 09:48:56Z) and stayed
stopped; after the last run the maintenance page answered 503 on 127.0.0.1:8080 and :9000, the GPU was at 0 MiB.
The v1 judge copy and the v2 test stack never ran at the same time.

**The verdicts below come from fix round 1 (14:40-18:20Z), which reran everything at the shipping configuration.**
The morning session (11:03-14:19Z) is kept at the end as history: its v2 GPU numbers were taken with worker-segment
running without its memory budget (F2, since fixed), and its "Not less accurate" verdict compared v2 with v1 runs
that had not run at all (the v1 copy was still down from a crash; review C1).

| | v1 | v2 |
|---|---|---|
| build | `marcus-backend:latest` 976396a5 (the production image) as judge copy `marcus-judge-backend`, 127.0.0.1:19000 (`judges/stack/docker-compose.yml` + `docker-compose.jarvis.yml`) | branch v2-backend at f40a0d0 + the process recycling of 188eecd, built on jarvis in `~/Project_MARCUS/v2-test/`; compose project `marcus-v2-test`, nginx 127.0.0.1:18090 (`backend-v2/docker-compose.yml` + `docker-compose.gpu.yml` + `judges/stack/docker-compose.v2-jarvis.yml`). Run lines: build `v2-r1b-f40a0d0+recycle` |
| configuration | **as shipped** (4 page threads); the judge copy restarted before EVERY (fixture, engine) run, 14:52-15:45Z. Reported beside it: the **single-thread** copy (the judges' shim, v1's own 1-thread path; morning) | **shipping**: every GPU budget on (segment 2048 MiB, decimer 4096 MiB, torch 0.09 each), MolScribe on cuda, segment process replaced every 200 pages. Only test deviation: per-IP limits raised for the single-IP judges (`docker-compose.v2-jarvis.yml`) |

Judges ran on jarvis against 127.0.0.1 with the jarvis guard in `--prod-stopped` mode on every run (scenarios,
fixture accuracy, gold set and robustness; GPU memory >= 3 GiB, production must stay stopped, GPU-time ledger,
`JUDGE_GPU_BUDGET_S=36000`, R20). The guard's read-only commands run locally through a shim (`.bin-guard/ssh`; the
whitelist is checked in Python first). Since f40a0d0 `target._check` also refuses ports 8080 and 9000 on any loopback
address. v2 timings on a cold OCSR cache (R21): every v2 timed run below has `ocsr_cache_hits == 0` and
`timing_valid == true`.

## Gates (spec §3): v2 at the shipping configuration against v1 as shipped

| Gate | Spec rule | v1 as shipped (jarvis GPU) | v1 single-thread (reported) | v2 shipping config (round 1) | Verdict |
|---|---|---|---|---|---|
| **Safe** | 17 of 17, each proves its v2 endpoint exists | 0 of 17 (`judges/security/README.md`) | — | 19 passed, 1 skipped (morning, `jarvis_v2_SECURITY_20261117T135859.xml`); not rerun: round 1 changed no API or nginx code | **PASS except #14 browser half** (`needs_frontend`, deferred to the React UI) |
| **Fair** | small paper (15) starts segmentation < 10 s and shows first SMILES < 60 s while a 190-structure paper runs | not measurable: the 190-structure paper crashed or wedged v1 as shipped in 5 of 6 attempts this day (see accuracy) | first SMILES 100.1 s, start not observable, small wall 160.1 s | **start 2.1 s, first SMILES 6.5 s**, small done 36.2 s; in S5's S2 2.5 s / 6.0 s; big paper 190/190 with full OCSR | **PASS** |
| **Responsive** | `/health` p95 < 100 ms during heavy work; depict p95 < 2 s | not measurable as shipped (it crashes on the 24-page paper); single-thread beside | S3 health p95 78,393 ms (max 82.5 s); depict not measured | S3 health p95 **5.8 ms** (max 38.1), heartbeat 13.8 ms; S2 health p95 5.3 ms; depict p95 **35.9 ms** (S3), 61.9 ms (S2), 33.2 ms (S5) | **PASS** |
| **Robust** | a bad PDF fails only its own paper; no worker crash takes the API down; 0 lost pages on the S1 fixture | lost pages on synth_015 (decimer-hand pages 0-2 this round; decimer 2, 3 / molnextr 2 / molscribe 0, 2 in the morning); 5 crashes and 1 wedge on 24-page PDFs | 0 lost pages | 8 adversarial PDFs next to a good paper: 1 refused (415), 4 failed alone (`check_pdf` / `render_page` + `docling` bad_input), 3 harmless ones done; good paper 15/15; `/health` 200 on 110 of 110 probes; 0 container restarts. S1 0 lost pages (3 engines). Whole run: 541 segment_page and 3,523 OCSR steps, all first attempt, 0 failed | **PASS** |
| **Not less accurate** | per engine, exact matches on the fixtures >= v1 as shipped (same session) | synth_015 9 / 12 / 12 / 12, synth_190 0 (wedge) / 0 (crash) / 0 (crash) / 128 (best as-shipped measurement per engine, table below) | 9 / 12 / 12 / 12 and 148 / 160 / 154 / 169 | **9 / 12 / 12 / 12 and 148 / 160 / 154 / 169** | **PASS** (v2 >= v1 as shipped for all 8 pairs; v2 = the single-thread copy for all 8) |
| gold-set recall (reported, no bar) | 2 papers that draw structures, all engines | see table below | — | equal to v1 on every paper and engine; MolScribe PMC7689812 skeleton 1/6 vs 0/6 | reported |
| **Throughput** | S4 full pipeline: two papers at once finish faster than one after the other | crashed after 10 s (morning; 2 fatal, 48 lost pages) | — | 1 slot (shipping): sequential 226.1 s, concurrent 227.3 s (**0.99×**, slower in both repeats) | **FAIL** at the shipping configuration. With 2 slots (experiment, not shipped): 184.4 s vs 181.6 s (1.02×, faster in both repeats) |

Engine order in the accuracy row: decimer / decimer-hand / molnextr / molscribe.

### Fixture accuracy (exact = full InChIKey of a prediction on the slot's own page; v1 as shipped measured per engine with a restart before each run)

| engine | synth_015 v1 as shipped: round 1 / morning | v1 single-thread | **v2** | synth_190 v1 as shipped (round 1) | v1 single-thread | **v2** |
|---|---|---|---|---|---|---|
| decimer | 9 / 7 (pages 2, 3 lost) | 9 | **9** | **0**: wedged; segmentation 243 s with 7 page errors (pages 20, 22, 23 lost), then 163 segments listed and no OCSR answer for 17 min (event loop blocked, unhealthy); the operator restarted it | 148 | **148** |
| decimer-hand | 4 (pages 0-2 lost) / 12 | 12 | **12** | **0**: crash after 64 s (`RemoteProtocolError`, 4 page errors) | 160 | **160** |
| molnextr | 12 / 10 (page 2 lost) | 12 | **12** | **0**: crash after 82 s (7 page errors) | 154 | **154** |
| molscribe (v1 cpu, v2 cuda) | 12 / 7 (pages 0, 2 lost) | 12 | **12** | **128** (145 segments; pages 3, 4, 7, 16, 19 lost) | 169 | **169** |

Per-run files: `jarvis_ACC_20261117T1553..T1633*_v1-asshipped-r1-*.json` (8 files), morning
`jarvis_ACC_20261117T120647_v1gpu.json` (synth_015 only counts; its synth_190 rows after decimer are connection
errors, not measurements), `jarvis_ACC_20261117T124813_v1gpu-single-thread.json`, v2
`jarvis_v2_ACC_20261117T183735_v2gpu-r1b.json`. v1 as shipped is not deterministic: the same engine on the same
5-page fixture lost different pages in the two runs (decimer-hand 12 then 4).

### Gold set (round 1 v2 vs v1 as shipped; recall full / skeleton, segments)

| engine | PMC6273634 v1 | v2 | PMC7689812 v1 | v2 |
|---|---|---|---|---|
| decimer | 5/11, 8/10, 14 seg | 5/11, 8/10, 14 seg | 0/6, 0/6, 8 seg (4 page errors) | 0/6, 0/6, 16 seg |
| decimer-hand | 6/11, 9/10 | 6/11, 9/10 | 0/6, 0/6, 16 seg | 0/6, 0/6, 16 seg |
| molnextr | 6/11, 9/10 | 6/11, 9/10 | 0/6, 0/6, 16 seg (2 page errors) | 0/6, 0/6, 16 seg |
| molscribe | 7/11, 9/10 (2 page errors) | 7/11, 9/10 | 0/6, 0/6, 1 seg (3 page errors) | 0/6, 1/6, 16 seg |

v1 = the morning as-shipped runs (crashed runs redone after restarts, the scorer keeps the latest line); v2 =
`runs/v2-jarvis-gpu-d4r1b.jsonl`. Score: `2026-11-17-gpu-session/round1/goldset_score_v1_v2_r1b.md`.

### Throughput detail (S4, full pipeline, 2 repeats per arm)

| | 1 slot (shipping) | 2 slots for q.segment and q.decimer (`docker-compose.v2-jarvis-2slot.yml`) |
|---|---|---|
| two 12-page papers (96 + 94 structures): sequential / concurrent | 227.2, 225.1 / 227.4, 227.2 s: **0.99×** | 185.6, 183.2 / 181.5, 181.6 s: **1.02×** |
| 8 one-page papers: sequential / concurrent | 130.6 / 78.6 s: 1.66× | 132.9 / 64.4 s: 2.06× |
| GPU utilisation, mean over the S4 run (nvidia-smi every 2 s) | 16.4 % | 64.5 % |
| card memory, peak | 8.6 GB | 15.5 GB (2 × 2380 MiB segment, 2 × 4428 MiB decimer, 2 × ~930 MiB torch) |
| lost pages / page errors / failed steps | 0 / 0 / 0 | 0 / 0 / 0 |

With one slot per GPU queue, a paper's own segmentation and OCSR already overlap, and two papers only share the same
two processes: each paper's segmentation takes about twice as long, and the pair finishes at the sum. Two slots make
everything about 19 % faster and give the concurrent pair a small but consistent edge (both repeats); the GPU is
still idle a third of the time. Files:
`jarvis_v2_S4_20261117T183144_d4r1b.json`, `jarvis_v2_S4_20261117T191739_d4r1b-2slot.json`; the aborted run
(below) gave 1.01× (`jarvis_v2_S4_20261117T171736_d4r1.json`).

## What fix round 1 changed and measured

| Item | Result | Evidence |
|---|---|---|
| F2: segment worker with its TF budget | fixed (f0e4e8e): the library's import-time `set_memory_growth` is skipped when a budget is set, as worker-decimer does; unit tests incl. a fail-first one. On jarvis: `TensorFlow limited to 2048 MiB`, `skipping decimer_segmentation's set_memory_growth`, segmenter loaded | `round1/v2_r1_gpu_checks.log` |
| Segment budget | TF allocator peak **896-982 MiB** over 44 pages at 300 dpi (synth_015, synth_190, both gold papers), identical segments and speed with a 6144, 2048 and even 1024 MiB cap. Set to **2048 MiB** (db9ab15) | `round1/seg_peak_*.log` |
| GPU memory leak (found in round 1) | the library leaks about **3.1 MiB of GPU memory per page** (allocator in use 281 → 583 → 899 → 1214 → 1527 MiB at pages 1/100/200/300/400). With 2048 MiB a process ran out after 390 pages in the stack (first run of round 1, 16:42Z: every later page failed `ResourceExhausted`) and after 394 pages in a stand-alone probe. Fix (188eecd): `--max-tasks-per-child 200` (compose and image CMD, pinned by a compose-config test that failed before the fix). **Long run after the fix: 541 segment_page steps (425 in the 1-slot phase), 0 failed, all first attempt, 0 OOM lines** | `round1/seg_leak_2048_final.log`, `round1/v2_r1b_failed_steps.txt` (only the 5 adversarial failures), `round1/run_logs_excerpt.txt` |
| F5: 4 of 190 crops differed from v1 | **root cause**: v1 writes the library's RGB crop with `cv2.imwrite`, which takes the array as BGR, so red and blue are swapped in every v1 crop file (shown to users, read by the OCSR engines). The 4 differing crops were exactly the coloured ones (158, 158, 314, 158 pixels with R != B). Fixed in round 1 (f0e4e8e) by storing crops in v1's channel order: **190 of 190 crops pixel-identical to v1**, and MolNexTR synth_190 154 = v1. **Round 2 (owner decision, see below):** the stored crop is true colour again (what users see) and the OCSR handler gives every engine v1's swapped pixels in memory; that engine input is pixel-identical to v1's file by construction (CPU test against a real `cv2.imwrite` of the library's array) | `jarvis_v2_CROPPARITY_20261117T185245.json`, `round1/ml_segment_test.log` |
| MolScribe on the GPU | compose default for the GPU stack is now cuda (db9ab15); morning: same SMILES on 205 of 205 crops as cpu; round 1: 12/15 and 169/190 on cuda | `jarvis_v2_ACC_20261117T183735_v2gpu-r1b.json` |
| I2: guard on every jarvis judge | robustness and gold set now run inside the jarvis guard (`--target jarvis --prod-stopped`), port 8080/9000 refused on loopback (f40a0d0) | result files carry `guard` |

The first run of round 1 (15:46-16:45Z, segment budget 2048 without recycling) is kept as evidence of the leak:
its S1-S5 and fixture accuracy finished before the leak hit and agree with the final run; its gold set failed from
page ~390 on (`jarvis_v2_*_d4r1.json`, `round1/v2_r1a_gpu_checks.log`).

## Fix round 2 (owner decisions, no GPU run)

- **Crop colour (N1).** OWNER DECISION: crops are stored in TRUE colour for people (`GET /segments/{id}/image`
  serves the page's colours), and the OCSR engines get v1's red/blue-swapped pixels in memory, so accuracy stays
  exactly v1's. One helper (`marcus.workers.ocsr.handler.v1_engine_input`) builds the engine input for segment crops
  only, never for image jobs; the OCSR cache is keyed on the engine-input bytes, so a crop and an image job with the
  same stored bytes never share a row; `seg_cache_key` carries a crop-format token (`|rgb`), so no cached
  segmentation from the old format is reused. No GPU run was needed: the round-1 GPU run showed v2's segmentation
  output equals v1's for 190 of 190 crops (then stored swapped and compared with v1's files); round 2 changes only
  where the swap happens, and a CPU test pins the engine input to a real `cv2.imwrite` (OpenCV 4.11.0, v1's version)
  of the library's RGBA array. `round1/crop_parity.py` now compares v1's files with the engine input.
- **GPU slots.** OWNER DECISION: v2 ships **1 slot each** for segmentation and DECIMER OCSR. **Throughput stays FAIL
  as a known limit**: 2 slots measured 1.02×, about the size of the run-to-run spread of the 1-slot runs (0.99× in
  the morning and in round 1's final run, 1.01× in round 1's first run); the 2-slot override stays a test file only.
- **Recycling evidence** (M4): `2026-11-17-gpu-session/round1/recycling_evidence.txt`.

## Checks on the GPU

| Check | Result |
|---|---|
| TF 2.15 on the V100 (sm_70) | works; TF 2.15.1 build has native sm_70 kernels (sm_50, sm_60, sm_70, sm_75, compute_80) |
| MolScribe GPU vs CPU | no loss (above); moved to cuda |
| dcgm-exporter | **does not work** as configured: `DCGM collector for entity type 'GPU' cannot be initialized ... Host engine is running as non-root`, `/metrics` returns no GPU metric (F3, open) |
| docling CPU time per page (morning; unchanged code) | 5.4-7.4 s per page on the fixtures, 2.8-6.6 s per page on the gold papers, 12-27 s for a 1-page PDF (fixed start cost); no docling timeout |
| Exclusive_Process setter (read-only) | `nvidia-v100-setup.service` runs `/usr/local/bin/nvidia-v100-setup.sh` with `nvidia-smi -c 3`; it runs after `multi-user.target`, i.e. after the planned boot unit, and the README's search missed it (F6, switch day; nothing changed) |

## Findings still open

- **F4 Throughput FAIL, a known limit by owner decision** (1 slot ships; 0.99×). Two slots reached 1.02× and 19 %
  shorter walls at 15.5 GB peak on the card, within the 1-slot run-to-run spread; not shipped.
- **F3** dcgm-exporter exports no GPU metrics (non-root DCGM).
- **F6** the Exclusive_Process setter must be changed on switch day; **F7** the outer proxy (141.35.136.10) was not
  read (no access; open item in `backend-v2/README.md`).
- The 3.1 MiB/page leak is in the segmentation library (Keras/TF across calls); recycling bounds it but does not
  remove it. Whether worker-decimer leaks the same way was not measured (it ran 3,523 OCSR steps without a failure).
- v1 as shipped is not deterministic (page losses differ run to run), so its numbers are a sample, not a constant.

## History: morning session (11:03-14:19Z), superseded for the verdicts

- v1 as shipped: synth_015 7/12/10/7; synth_190 decimer crashed after 32 s, the other three engines got
  `ConnectError` because the copy was not restarted (not measurements; review C1). Gold set and S1/S4 as above.
- v1 single-thread: fixture numbers above; S2/S3/S5 numbers used beside the gates.
- v2 (worker-segment WITHOUT budget, MolScribe cpu, 2eb2c74 + tzdata fix): Fair 2.4 s / 6.7 s; health p95 5.6 ms;
  Robust all true; fixture 9/12/12/12 and 148/160/153/169 (the 153 was the crop channel order, F5); Throughput 0.99×.
  Security 19 passed + 1 needs_frontend skip. Blockers then: F1 (no tzdata in tf:cuda, fixed 5a8e5e3) and F2.
- Files: `jarvis_*_20261117T1[2-5]*` (morning), `2026-11-17-gpu-session/*` (morning logs).

## How to rerun

On jarvis, `~/Project_MARCUS/v2-test/`: `run_v1_r1.sh` (v1 as shipped, restart before every engine run),
`run_v2_gpu_r1b.sh` (all v2 gates at the shipping configuration, then S4 with 2 slots). The probes are copied to
`2026-11-17-gpu-session/round1/`: `seg_gpu_peak.py` (segmenter memory per page in the tf:cuda image, `MODE=growth`
or `budget`), `seg_gpu_leak.py` (the same, pages repeated with `REPEAT`), `crop_parity.py` (v2 crops vs v1 crop files).

## D5 rerun after final fixes (2026-11-17, 21:01-21:16Z)

The gates whose code changed after D4 were rerun on the final code. Those are Safe, Responsive and a short Robust
smoke. The code they cover is the final-review fix wave (merge `7410155`) and the /simplify cleanup up to `e985b05`.
The build is branch v2-backend at HEAD **`bdcc6c5`**, which is `e985b05` plus the revert of `6e86c78`. The code went
to `~/Project_MARCUS/v2-test/` on jarvis with `git archive`, and the D4 trees are kept beside it as `*.d4`. All five
images were rebuilt on jarvis from that code (`marcus-v2-api:local`, `-cpu:local`, `-tools:local`, `-tf:cuda`,
`-torch:cuda`); a check in the image found the /simplify `storage.disk_is_full`. The stack ran with the same compose
files as D4 (`backend-v2/docker-compose.yml` + `docker-compose.gpu.yml`, or `docker-compose.fake.yml` for security
mode, + `judges/stack/docker-compose.v2-jarvis.yml`). Run line: build `v2-d5-bdcc6c5`.

- **Old data wiped first.** `down -v` ran on both stack modes, and afterwards no `marcus-v2-test` volume was left
  (crops stored before `c69cdbc` would be swapped twice).
- **nginx per-IP caps raised in the judge stack (ruling R25).** The fix wave added `MARCUS_NGINX_CONN_PER_IP` (64)
  and `MARCUS_NGINX_UPLOADS_PER_IP` (4). `docker-compose.v2-jarvis.yml` now raises them to 1000 and 100, like the
  API per-IP limits, and says why in its header. The nginx log showed `limit_conn perip 1000, uploads 100`, real_ip
  off. Every other edge setting was as in production:
  - `client_max_body_size 1m`, and 21m only on `POST /papers` and `/images`;
  - api `mem_limit` 6g and nginx 1536m, each with a 1g `/tmp` tmpfs (`d5/d5_security_stack.log`,
    `d5/d5_gpu_checks.log`).
- **Shipping GPU settings, checked in the running stack:**
  - `SLOTS` `q.segment` 1 and `q.decimer` 1 (owner decision);
  - worker-segment `MARCUS_GPU_MEM_MB=2048` with `--max-tasks-per-child 200`; its log shows
    `TensorFlow limited to 2048 MiB` and that the library's `set_memory_growth` was skipped;
  - worker-decimer 4096 MiB;
  - MolNexTR and MolScribe at torch 0.09 each, with MolScribe `loaded on cuda`.
- **Guard.** Every load and robustness run used the jarvis guard (`--target jarvis --prod-stopped`) and never
  tripped. The OCSR cache was cleared before each scenario.
- **Production.** v1 production stayed stopped (`marcus-backend` exited, restart policy `no`), and
  `marcus-maintenance` answered 503 on 127.0.0.1:8080 and :9000 before and after.

### Gate table (D5, v2 `bdcc6c5`, shipping configuration)

| Gate | Spec rule | D4 round 1 (v2 `f40a0d0`+recycle) | **D5 (v2 `bdcc6c5`)** | Verdict |
|---|---|---|---|---|
| **Safe** | 17 of 17, each proves its v2 endpoint exists | 19 passed, 1 skipped | **19 passed, 1 skipped** (`needs_frontend`: the browser half of #14, which waits for the React UI) in 260 s. All 16 v1 functions have a v2 test of the same name, and each passes its own existence check. Both XFF bursts (via nginx and direct to the API) were limited | **PASS except #14 browser half** (as D4) |
| **Responsive** | `/health` p95 < 100 ms during heavy work; depict p95 < 2 s | S3 health p95 5.8 ms; depict p95 35.9 ms (S3), 33.2 ms (S5) | **S3** (synth_190 segmentation, 131 s): health p95 **6.3 ms** (max 8.3, 130/130 ok), heartbeat p95 13.0 ms, depict p95 **46.9 ms** (65/65 ok). **S5** (during S2): depict p95 **39.2 ms** (145 calls), health p95 5.3 ms (290). No 429, 503 or error answers in either run | **PASS** |
| **Robust (smoke)** | a bad PDF fails only its own paper; no worker crash takes the API down; 0 lost pages | all 4 verdicts true, health 110/110 | the same 8 adversarial PDFs next to synth_015: `png_as_pdf` refused (415); garbage, zero-page and encrypted failed `check_pdf` bad_input; huge page failed `render_page` (the new 50-megapixel cap: `60001x60001 pixels ... limit 50 megapixels`) and docling bad_input; XSS text, the 1 GiB flate bomb and the cut synth_015 finished. Good paper 15/15 segments, 0 lost pages, 9 exact. `/health` 200 on **128 of 128** probes (max 8 ms); **0 restarts, 0 OOM**. Verdicts `good_paper_done_all_15`, `every_bad_paper_failed_or_rejected_alone`, `api_health_always_200`, `no_container_restart` all true | **PASS** |

Also measured (not rerun as gates):
- **S5's S2 part:** the small paper started segmenting at 2.5 s and showed its first SMILES at 7.2 s (Fair bar:
  10 s and 60 s; D4 2.5 s and 6.0 s). The big paper got 190/190 segments with full OCSR.
- **Script user (S5):** `generate_smiles` p95 was 1.19 s alone and 2.55 s during S2 (D4: 1.16 s and 2.72 s).
- **Whole GPU-mode session (S3, S5, robustness):**
  - 65 `segment_page`, 300 `ocsr`, 65 `render_page` and 11 `check_pdf` steps, all on the first attempt;
  - the only failed steps are the 5 adversarial ones listed above;
  - 0 `ResourceExhausted` or out-of-memory lines in the 4 GPU workers;
  - card peak 8,572 MiB; mean GPU utilisation 9.6 % (nvidia-smi every 2 s).

Not rerun, because D5's scope was Safe, Responsive and a Robust smoke: Fair (its S2 numbers come from S5 above),
Not less accurate, gold set and Throughput. Their D4 round 1 verdicts above stand for build `f40a0d0`+recycle and
round 2's crop change. Throughput stays FAIL as a known limit (owner decision, 1 slot).

Notes:
- The S3 idle depict p95 was 127.8 ms (D4: 28.6 ms). The idle phase has 16 samples, and its 128.9 ms maximum is
  the first depict call on a fresh tools worker. During segmentation the p95 was 46.9 ms.
- In the robustness run the good paper had 15 OCSR cache hits. This is because `robustness_v2.py` does not clear
  the cache, and S5 had just processed synth_015. It does not affect the Robust verdicts, which make no timing claim.
  D4 ran robustness after a cache clear, with 0 hits.
- `run_d5.sh` ran the whole session. Its last steps: `down -v` the stack (images kept); no `marcus-v2-test`
  container, volume or network left; GPU 0 MiB, compute mode Default.

Files:
- `load/results/jarvis_v2_SECURITY_20261117T220121_d5.xml`
- `load/results/jarvis_v2_S3_20261117T220912_d5.json`
- `load/results/jarvis_v2_S5_20261117T221503_d5.json`
- `load/results/jarvis_v2_ROBUST_20261117T221608.json`
- `2026-11-17-gpu-session/d5/`:
  - `run_d5.sh` and `v2_lib.sh` (the run script and its helpers);
  - `d5_run.log`, `d5_security.log` and `d5_security_stack.log`;
  - `d5_gpu_checks.log` (limits, slots, budgets, device), `d5_after.log` (restart counts, step table, failed
    steps, OOM count) and `d5_gpu.csv`.

The result file names carry jarvis local time (CET), as D4's did.
