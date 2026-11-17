# v1 vs v2 GPU session on jarvis (Task D4, 2026-11-17)

One Tesla V100-PCIE-32GB (sm_70, driver 580.178.04, compute mode Default), 32 cores, 376 GB RAM.
Production v1 was already stopped by the owner (maintenance page `marcus-maintenance` on 8080/9000 since
09:48:56Z) and stayed stopped; the maintenance page answered 503 on 127.0.0.1:8080 and :9000 after the session.
The v1 judge copy and the v2 test stack ran one after the other, never together (GPU 0 MiB in between).

| | v1 | v2 |
|---|---|---|
| build | `marcus-backend:latest` 976396a5 (production image), judge copy `marcus-judge-backend` on 127.0.0.1:19000 (`judges/stack/docker-compose.yml` + `docker-compose.jarvis.yml`) | branch v2-backend 2eb2c74, built on jarvis in `~/Project_MARCUS/v2-test/` (api, cpu, tools, tf:cuda, torch:cuda), compose project `marcus-v2-test`, nginx on 127.0.0.1:18090 (`backend-v2/docker-compose.yml` + `docker-compose.gpu.yml` + `judges/stack/docker-compose.v2-jarvis.yml`). Run lines say `v2-unknown` (no git on jarvis) = 2eb2c74 |
| copies | **as shipped** (4 page threads) 11:03-11:46Z; **single-thread** (the judges' shim, v1's own 1-thread path, `judges/load/docker-compose.jarvis-single-thread.yml`) 11:47-12:58Z, because the as-shipped copy crashes on every 24-page PDF | security mode (fake engines, `docker-compose.fake.yml`) 12:58-13:04Z; GPU mode 13:14-14:19Z |
| deviations | none | (1) `Dockerfile.tf` + `tzdata` (one line; without it no TF worker starts, see F1); (2) worker-segment ran **without** its 6144 MiB TensorFlow budget (F2) |

Judges ran on jarvis against 127.0.0.1 (`judges/` copy, uv env), guard in `--prod-stopped` mode (production must
stay stopped, free GPU >= 3 GiB), `JUDGE_GPU_BUDGET_S=36000` (R20); on jarvis the guard's read-only ssh commands run
locally through a shim (`.bin-guard/ssh`, whitelist still enforced in Python). v2 timings on a cold OCSR cache (R21:
`DELETE FROM ocsr_cache` in `marcus-v2-test-postgres-1` before every scenario, arm and accuracy run); every v2 timing
in this file has `ocsr_cache_hits == 0` and `timing_valid == true`. `run_goldset.py` runs had no guard (it enables
it only for port 29000); nothing shared the GPU then. Raw files: `judges/load/results/*20261117T1[2-5]*`,
`judges/runs/*-d4*.jsonl`, `judges/results/2026-11-17-gpu-session/`.

## Gates (spec §3)

| Gate | Pass rule | v1 (jarvis GPU) | v2 (jarvis GPU) | Result | Raw files |
|---|---|---|---|---|---|
| **Safe** | 17 of 17, each proves its v2 endpoint exists | 0 of 17 (v1 suite on v1, `judges/security/README.md`, not rerun) | **19 passed, 1 skipped** (`needs_frontend`: browser half of #14, no React UI yet); 17 mapped tests: 16 pass + #14 API half pass + browser half skipped; + 2 XFF tests pass | **PASS** (with the expected skip) | `load/results/jarvis_v2_SECURITY_20261117T135859.xml`, `2026-11-17-gpu-session/v2_security.log` |
| **Fair** | small paper (15) starts segmentation < 10 s and first SMILES < 60 s while a 190-structure paper runs | as shipped: crashes on the 190 paper (S4, ACC); single-thread: start not observable, **first SMILES 100.1 s**, small wall 160.1 s (3.1x its S1) | **start 2.4 s, first SMILES 6.7 s**, small done 36.3 s (wall 37.5 s, 1.2x S1); big paper 190/190 with full OCSR; in S5's S2: 2.7 s / 7.1 s | **PASS** | `jarvis_S2_20261117T134939_d4-single-thread.json`, `jarvis_v2_S2_20261117T142118_d4.json`, `jarvis_v2_S5_20261117T145156_d4.json` |
| **Responsive** | `/health` p95 < 100 ms during heavy work; depict p95 < 2 s | single-thread: S3 health p95 **78,393 ms** (max 82.5 s, idle 8.3 ms); S2 p95 79,797 ms (97 % > 200 ms); depict not measured on v1 | S3 health p95 **5.6 ms** (max 39.7), heartbeat 15.5 ms; S2 health p95 5.3 ms; depict p95 **35.8 ms** (S3), 46.5 ms (S2), 35.0 ms (S5) | **PASS** | `jarvis_S3_20261117T135813_d4-single-thread.json`, `jarvis_v2_S3_20261117T142402_d4.json`, S2/S5 above |
| **Robust** | a bad PDF fails only its own paper; no worker crash takes down the API; 0 lost pages on S1 fixture | as shipped: S1 lost pages (molscribe pages 0, 2; ACC decimer 2, 3, molnextr 2, molscribe 0, 2), **5 backend crashes** in the session (24-page fixture, gold-set paper, S4); single-thread: 0 lost pages | 8 adversarial PDFs at once next to a good paper: 1 refused at upload (415, PNG as .pdf), 4 failed alone (garbage, encrypted, zero pages: `check_pdf` bad_input; 200-inch page: `render_page` + `docling` bad_input), 3 harmless ones done (XSS text, 1 GiB flate bomb, truncated PDF); good paper 15/15, no lost page; `/health` 200 on every probe; 0 container restarts. S1 0 lost pages (3 engines), S4 0 lost pages / 0 page errors, all 2,764 OCSR steps first attempt | **PASS** | `jarvis_v2_ROBUST_20261117T151405.json`, `jarvis_v2_S1_20261117T141713_d4.json`, `jarvis_v2_S4_20261117T144605_d4.json`, `jarvis_ACC_20261117T120647_v1gpu.json`, `jarvis_S4_20261117T124539_d4.json` |
| **Not less accurate** | per engine, exact-match structures on the fixtures >= v1 (as shipped, jarvis GPU, same session) | see table below | see table below | **PASS against v1 as shipped**; against the single-thread copy equal except MolNexTR synth_190 153 vs 154 (F5) | `jarvis_ACC_20261117T120647_v1gpu.json`, `jarvis_ACC_20261117T124813_v1gpu-single-thread.json`, `jarvis_v2_ACC_20261117T145157_v2gpu.json` |
| gold-set recall (reported, no bar) | 2 papers, all engines | see table below | v2 >= v1 on every paper and engine | reported | `runs/v1-jarvis-gpu-d4.jsonl`, `runs/v2-jarvis-gpu-d4.jsonl`, `2026-11-17-gpu-session/goldset_score_v1_v2.md` |
| **Throughput** | S4 full pipeline: 2 papers at once faster than one after the other | as shipped: crashed after 10 s (2 fatal, 48 lost pages); v1 serialises requests anyway (local S4) | two 12-page halves of synth_190 (96 + 94 structures): sequential **224.4 s**, concurrent **227.0 s** (0.99x, 2 repeats each, valid); control 8 one-page PDFs: 130.8 s vs 78.7 s (1.66x faster) | **FAIL** (F4) | `jarvis_v2_S4_20261117T144605_d4.json` |

### Fixture accuracy (exact = full InChIKey of a prediction on the slot's page; skeleton = first block)

| engine | synth_015 (15) v1 as shipped | v1 single-thread | **v2** | synth_190 (190) v1 as shipped | v1 single-thread | **v2** |
|---|---|---|---|---|---|---|
| decimer | 7 (9 segments, pages 2, 3 lost) | 9 | **9** | 0 (crash after 32 s) | 148 | **148** |
| decimer-hand | 12 | 12 | **12** | 0 (backend down) | 160 | **160** |
| molnextr | 10 (page 2 lost) | 12 | **12** | 0 (backend down) | 154 | **153** |
| molscribe (CPU in v1 and v2) | 7 (pages 0, 2 lost) | 12 | **12** | 0 (backend down) | 169 | **169** |
| molscribe v2 on **cuda** | | | **12** | | | **169** |

v2 found every segment (15/15, 190/190) with every engine; v1 single-thread too. Slot by slot, v2 and the v1
single-thread copy match the same slots for every engine and fixture except MolNexTR slot 154 (F5).

### Gold set (2 papers that draw structures; recall full / skeleton, segments)

| engine | PMC6273634 (11 expected) v1 | v2 | PMC7689812 (6 expected) v1 | v2 |
|---|---|---|---|---|
| decimer | 5/11, 8/10, 14 seg | 5/11, 8/10, 14 seg | 0/6, 0/6, 8 seg (4 page errors) | 0/6, 0/6, 16 seg |
| decimer-hand | 6/11, 9/10 | 6/11, 9/10 | 0/6, 0/6, 16 seg | 0/6, 0/6, 16 seg |
| molnextr | 6/11, 9/10 | 6/11, 9/10 | 0/6, 0/6, 16 seg (2 page errors) | 0/6, 0/6, 16 seg |
| molscribe | 7/11, 9/10 (2 page errors) | 7/11, 9/10 (cpu and cuda) | 0/6, 0/6, **1 seg** (3 page errors) | 0/6, **1/6**, 16 seg |

v1 = as shipped (it crashed 3 times during these 8 runs; crashed runs were redone after a restart, the scorer keeps
the latest line). PMC7689812 (tetrapeptides) scores 0 full for every system: COCONUT's structures are not what the
paper draws in a readable way; the paper still has 16 drawn structures.

### Times (not gates)

| | v1 | v2 |
|---|---|---|
| S1 synth_015 wall (v1) / OCSR done (v2), decimer / molnextr / molscribe | 51.1 / 95.0 / 43.7 s (as shipped) | 20.9 / 15.5 / 22.4 s (cpu MolScribe), 16.2 s (cuda MolScribe); v2 paper wall incl. docling 29-31 s |
| first SMILES, synth_015 alone | — | 3.8-4.7 s |
| OCSR per structure p50 (engine time) | client round trip 2.4 / 5.7 / 3.0 s | engine 0.98 / 0.71 / 1.19 s (cpu), 0.77 s (cuda MolScribe) |
| synth_190 full run, decimer | 509 s (single-thread; v1 rate limit 20 req/min) | 226 s (paper wall incl. docling) |
| S5 script user p95 alone / during S2 | 898 ms / 8,386 ms (max 94.9 s) | 1,178 ms / 2,552 ms (max 4.0 s) |
| first image job of a fresh stack (warm-up) | 4.5 s decimer | 23.3 s decimer (first TF run on the GPU), 0.9 s molnextr, 1.4 s molscribe |

## Checks on the GPU

| Check | Result |
|---|---|
| TF 2.15 on the V100 (sm_70) | **Works.** `tf.sysconfig.get_build_info()` in marcus-v2-tf:cuda: TF 2.15.1, CUDA 12.2, cuDNN 8, `cuda_compute_capabilities` sm_50, sm_60, **sm_70**, sm_75, compute_80, so native sm_70 kernels, no PTX JIT. Segmentation and DECIMER (normal and hand-drawn) ran on GPU 0 for the whole session (462 segment_page steps and every decimer / decimer-hand OCSR step, 0 failures). (C4's "sm_75 + compute_80" reading was incomplete.) |
| MolScribe GPU vs CPU | **No loss: GPU allowed.** cuda vs cpu: the same SMILES on 205 of 205 fixture crops, the same exact counts (12/15, 169/190), the same gold-set result; engine time p50 1.08 s -> 0.66 s (synth_190), paper 240 s -> 159 s. Decision recorded: the spec rule is met, MolScribe may move to `MARCUS_MOLSCRIBE_DEVICE=cuda` (880 MiB on the card). The default in `docker-compose.yml` is unchanged in this task (controller's call). Note for B4 (cache key ignores the device): no CPU/GPU difference was seen for MolScribe. |
| dcgm-exporter | **Does not work as configured (F3).** It starts and serves :9400, but `DCGM collector for entity type 'GPU' cannot be initialized; err: error watching fields: Host engine is running as non-root`; `/metrics` returned 0 lines (read from the metrics container on the internal network). |
| docling CPU time per page (v2, CPU, 4 threads, jarvis) | 24-page synth_190: 5.4-6.1 s/page (130-145 s); 12-page halves 6.1-7.4 s/page (two at once); 5-page synth_015: 5.6-7.3 s/page; real papers: PMC6273634 2.8-2.9 s/page, PMC7689812 6.0-6.6 s/page; 1-page PDFs 12-27 s (fixed start cost ~10 s per step). 73 of 74 docling steps done on the first attempt, no timeout; the one failure is the 200-inch adversarial page (bad_input). v1 runs docling on the GPU only on request (not measured; the judge client does not call it). |
| Exclusive_Process setter (read-only search) | **Found:** `nvidia-v100-setup.service` (enabled, `After=multi-user.target`) runs `/usr/local/bin/nvidia-v100-setup.sh`, which ends with `nvidia-smi -c 3` (EXCLUSIVE_PROCESS). The README's grep misses it (no `/usr/local/bin`); it runs after Docker and after the planned boot unit, so it would undo it. Nothing changed. `2026-11-17-gpu-session/exclusive_process_setter.txt`; switch-day note in `backend-v2/README.md` (F6). |
| GPU memory (v2, nvidia-smi every 5 s) | peak 21,008 MiB for the whole card; per process: worker-segment 15,690 MiB (no budget, F2), worker-decimer 4,428 MiB (budget 4096 + context), worker-molnextr 880-926 MiB, worker-molscribe (cuda) 880 MiB. GPU utilisation mean 18 % during S4. |
| watchdog / retries (ledger A6) | 0 steps with attempts > 1, 0 timeouts, 0 watchdog failures in the whole v2 GPU run (2,764 OCSR, 462 segment_page, 74 docling steps). |

## Findings (each goes back as a task)

- **F1 (blocker, one-line fix applied):** `marcus-v2-tf:cuda` has no time-zone data (the nvidia/cuda Ubuntu base has
  no `tzdata`, the venv no `tzdata` wheel), so `celery` dies at import (`ZoneInfoNotFoundError: 'No time zone found
  with key UTC'`, kombu timer) and worker-segment and worker-decimer restart forever. Fix: `tzdata` added to the
  runtime stage's `apt-get install` in `backend-v2/docker/Dockerfile.tf` (separate commit). The CPU variant and the
  torch image have it. No test runs the CUDA image, so C4 could not see it. Log: `v2_gpu_attempt1_tzdata.log` (not
  committed), first lines in the report.
- **F2 (blocker, worked around in the test stack only):** with its budget (`MARCUS_GPU_MEM_MB=6144`, from
  `docker-compose.gpu.yml`) worker-segment cannot load the segmenter: `limit_tf_memory` configures a logical device,
  then `import decimer_segmentation` runs `configure_gpu(memory_growth=True)` (`mrcnn/model.py:51`) and TensorFlow
  raises `ValueError: Cannot set memory growth on device when virtual devices configured`; the worker exits and
  restarts in a loop. worker-decimer guards the same call (`marcus/workers/ocsr/decimer.py:98-116`), segment.py does
  not. The session ran the segment worker with no budget (`docker-compose.v2-jarvis.yml`), so TF grew to 15.7 GB.
  After the fix, the 6 GB budget itself must be measured (Mask R-CNN at 300 dpi may need more).
- **F3:** dcgm-exporter exports no GPU metrics (non-root DCGM host engine). Needs a decision (run it as root /
  `SYS_ADMIN`, or drop it and read nvidia-smi / NVML from the metrics service).
- **F4 (gate FAIL, Throughput):** two papers at once are not faster than one after the other (227.0 s vs 224.4 s).
  Each paper's segmentation takes 53 s instead of 26 s when two run (one `q.segment` slot), and OCSR has one slot per
  engine (`q.decimer`), so the pipeline is serial on the GPU work while the GPU is 18 % busy on average. One-page PDFs
  do gain (1.66x), because their docling/render CPU work overlaps. Candidates: 2 slots (processes) for q.decimer and
  q.segment within the memory budget, or batching OCSR crops per call.
- **F5 (accuracy detail):** 4 of 190 synth_190 crops differ between v1 and v2 (158-314 pixels each, same box size;
  each build is deterministic run to run). MolNexTR reads one of them differently (slot 154), so v2 has 153 vs the v1
  single-thread copy's 154; the same v2 model on v1's crop gives v1's answer (`crop_diff_molnextr.txt`). Not a gate
  failure against v1 as shipped, but it is a pre-processing difference (spec anti-goal); cause not found (Mask R-CNN
  mask on GPU vs v1's process, or the crop/masking step; worker-segment ran without budget, F2).
- **F6:** the Exclusive_Process setter (above) must be changed on switch day; the README search command misses it.
- **F7 (open item, no access):** the outer reverse proxy (141.35.136.10) was not read: trusted proxy address, body
  limit, SSE buffering, TLS end. Written as a switch-day open item in `backend-v2/README.md`.

## How to rerun

On jarvis, `~/Project_MARCUS/v2-test/` (copy of v2-backend + judges, `env.sh`, `run_v1_asshipped.sh`,
`run_v1_single.sh`, `run_v2_security.sh`, `run_v2_gpu.sh`, logs in `logs/`). New judge tools of this session:
`judges/load/fixture_accuracy.py` (fixtures x engines, exact/skeleton per slot, v1 or v2, cache cleared per run),
`judges/load/robustness_v2.py` (adversarial PDFs next to a good paper, health probes, container restarts);
`client_v1` maps `decimer-hand` to v1's `hand_drawn=true` (the Vue UI never sets it), `run_goldset --engines`
accepts `decimer-hand`.
