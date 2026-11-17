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
| F5: 4 of 190 crops differed from v1 | **root cause**: v1 writes the library's RGB crop with `cv2.imwrite`, which takes the array as BGR, so red and blue are swapped in every v1 crop file (shown to users, read by the OCSR engines). The 4 differing crops were exactly the coloured ones (158, 158, 314, 158 pixels with R != B). Fixed (f0e4e8e): crops are stored in v1's channel order; unit tests + the ML test (5 passed in the tf test image). Now **190 of 190 crops pixel-identical to v1**, and MolNexTR synth_190 is 154 = v1 | `jarvis_v2_CROPPARITY_20261117T185245.json`, `round1/ml_segment_test.log` |
| MolScribe on the GPU | compose default for the GPU stack is now cuda (db9ab15); morning: same SMILES on 205 of 205 crops as cpu; round 1: 12/15 and 169/190 on cuda | `jarvis_v2_ACC_20261117T183735_v2gpu-r1b.json` |
| I2: guard on every jarvis judge | robustness and gold set now run inside the jarvis guard (`--target jarvis --prod-stopped`), port 8080/9000 refused on loopback (f40a0d0) | result files carry `guard` |

The first run of round 1 (15:46-16:45Z, segment budget 2048 without recycling) is kept as evidence of the leak:
its S1-S5 and fixture accuracy finished before the leak hit and agree with the final run; its gold set failed from
page ~390 on (`jarvis_v2_*_d4r1.json`, `round1/v2_r1a_gpu_checks.log`).

## Checks on the GPU

| Check | Result |
|---|---|
| TF 2.15 on the V100 (sm_70) | works; TF 2.15.1 build has native sm_70 kernels (sm_50, sm_60, sm_70, sm_75, compute_80) |
| MolScribe GPU vs CPU | no loss (above); moved to cuda |
| dcgm-exporter | **does not work** as configured: `DCGM collector for entity type 'GPU' cannot be initialized ... Host engine is running as non-root`, `/metrics` returns no GPU metric (F3, open) |
| docling CPU time per page (morning; unchanged code) | 5.4-7.4 s per page on the fixtures, 2.8-6.6 s per page on the gold papers, 12-27 s for a 1-page PDF (fixed start cost); no docling timeout |
| Exclusive_Process setter (read-only) | `nvidia-v100-setup.service` runs `/usr/local/bin/nvidia-v100-setup.sh` with `nvidia-smi -c 3`; it runs after `multi-user.target`, i.e. after the planned boot unit, and the README's search missed it (F6, switch day; nothing changed) |

## Findings still open

- **F4 Throughput FAIL at the shipping configuration** (0.99×). Two slots for q.segment and q.decimer reach 1.02×
  and 19 % shorter walls, at 15.5 GB peak on the card; whether to ship 2 slots (and whether 1.02× satisfies the spec's
  "faster") is a decision for the owner/controller.
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
