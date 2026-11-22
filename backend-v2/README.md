# MARCUS v2 backend

FastAPI + Celery + Postgres. One Python distribution `marcus` (`src/marcus/`).

## Run

```bash
# CPU stack with fake engines (fast, no GPU); nginx is the only published port
docker compose -p marcus-v2 -f docker-compose.yml -f docker-compose.fake.yml up -d --build
```

### Web UI

nginx serves the web UI as well as the API: its image (`marcus-v2-nginx:local`) is built from
`../frontend-v2/` (`frontend-v2/Dockerfile`: `npm ci && npm run build`, then `dist/` and
`deploy/ui-locations.conf` on top of `nginx-unprivileged`). `docker/nginx.conf` stays a bind
mount and includes the locations file inside its `server {}`: the pages, `/app/...`, the assets
and the Ketcher editor, each with its own full header set (the app and Ketcher CSPs). A UI
change needs `up -d --build nginx`. The app is at http://localhost:18090/.

### Networks

`internal` is an internal Docker network (no route out of the host); every service is on it.
Only `nginx` (its published port needs a non-internal network) and `worker-cpu` (the DOI
lookups) also join `egress`; nginx's only outbound calls are the COCONUT relay below. nginx keeps the fixed
address 172.30.0.10 outside the dynamic pool (`MARCUS_TRUSTED_PROXIES`). With the monitoring
override, Grafana publishes 127.0.0.1:13000 through its own `grafana-edge` network, which does no
masquerading (no route out either).

### COCONUT relay

COCONUT sends no CORS headers, so the browser cannot call it. nginx relays exactly three calls
to the fixed host `https://coconut.naturalproducts.net` (TLS verified against the system CA
bundle, SNI): `POST /api/v2/coconut/auth/login`, `/reports/mutate`, `/search` →
`/api/auth/login`, `/api/reports/mutate`, `/api/search`. Anything else under
`/api/v2/coconut/` is nginx's 404. In each of the three, in this order: a declared body over
the limit 413 (8 KB login and search, 2 MB mutate), another method 405, a query 400, a non-JSON
body 415, the rate limits 429, a chunked body over the limit 413. Only Host, Content-Type,
Accept, a fixed User-Agent and (mutate only) Authorization go upstream; only the status, the
body and its Content-Type come back (njs filter `docker/coconut-relay.js`). The password and
the token pass through and are never stored or logged (the relay's access log has the path
only). The API stays without internet.

Limits, per client (an IPv6 client by its /64) and then in total, because COCONUT sees every
MARCUS user as this one server: login 3/min per client (burst 3) and 30/min in total (burst
10); search 10/min (burst 10) and 20/min in total (burst 10); mutate 60/min (burst 20) and
120/min in total (burst 40). Login and search together stay at 50/min, under a typical 60/min
per-address API limit at COCONUT. Owner item: ask the COCONUT team to allow-list the MARCUS
server's address, so that COCONUT's own per-address limits never apply to all MARCUS users at
once.

"POST only" holds for this hop: COCONUT (Laravel) may treat a `_method` field in a JSON body as
another method on the same fixed path. The relay adds no credential, so that gives a caller
nothing their own token does not.

The fake stack (`docker-compose.fake.yml`) adds a fake COCONUT (`tests/fake_coconut/`) under
COCONUT's name on the internal network and makes nginx trust only its test CA: the same relay
config runs, and nothing reaches the real COCONUT. Login `curator@example.org` /
`fake-coconut-password`.

Switching a running stack to these networks: run `up -d --force-recreate` once (or `down` first;
volumes stay). Compose recreates a changed network, but containers it does not recreate (e.g.
postgres, redis) are re-attached without their service aliases, so `postgres` stops resolving.

### GPU (production host)

```bash
docker compose -p marcus-v2 -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
# + -f docker-compose.monitoring.yml (last) for Prometheus/Grafana; Prometheus then also
#   scrapes dcgm-exporter:9400 (GPU metrics, internal network only)
```

The override builds the CUDA images (`VARIANT=cuda`: `marcus-v2-tf:cuda`, `marcus-v2-torch:cuda`;
the CPU images keep their `:local` tags), reserves the GPU for worker-segment, worker-decimer,
worker-molnextr and worker-molscribe, and sets their memory budgets: TensorFlow
`MARCUS_GPU_MEM_MB` 2048 (segment, measured peak under 1 GB) and 4096 (decimer), torch `MARCUS_TORCH_MEM_FRACTION` 0.09
each (about 2.9 GB of the 32 GB card); the sum stays under 20 GB (deploy test). Each budget can be
overridden from the environment (`MARCUS_SEGMENT_GPU_MEM_MB`, `MARCUS_DECIMER_GPU_MEM_MB`,
`MARCUS_MOLNEXTR_TORCH_MEM_FRACTION`, `MARCUS_MOLSCRIBE_TORCH_MEM_FRACTION`). MolScribe runs on
the GPU here (`MARCUS_MOLSCRIBE_DEVICE=cuda`; v1 and the CPU stack use cpu): the D4 fixture judge
showed no loss (the same SMILES on 205 of 205 crops).
CUDA library versions: `docker/MODEL_PINS.md`.

Host requirements: NVIDIA driver with CUDA 12.8 support, the NVIDIA Container Toolkit, and the
card in compute mode DEFAULT (four processes share it). The boot unit
`ops/systemd/nvidia-compute-default.service` runs `nvidia-smi -i 0 -c DEFAULT` after
nvidia-persistenced and before Docker starts, then reads the mode back (`ExecStartPost`), so a
switch that did not take fails the unit. It is not installed by anything here. On switch day:

1. Find what sets Exclusive_Process at boot (jarvis's card goes back to it on reboot; the driver's
   own default is Default), read-only, and disable it (or, if it is a systemd unit that must stay,
   add `After=<that unit>` to the boot unit):

   ```bash
   systemctl list-unit-files | grep -i nvidia
   grep -rnE "compute-mode|-c 3|-c EXCLUSIVE|EXCLUSIVE_PROCESS" /etc/systemd /etc/rc.local \
     /etc/cron* /etc/nvidia* /etc/modprobe.d /usr/lib/systemd/system/nvidia* 2>/dev/null
   crontab -l 2>/dev/null | grep -i nvidia; sudo crontab -l 2>/dev/null | grep -i nvidia
   systemctl cat nvidia-persistenced.service    # nvidia-persistenced options
   ```

   **Found on jarvis (D4 GPU session, 2026-11-17, read-only; nothing changed).** The setter is
   `nvidia-v100-setup.service` (`/etc/systemd/system/`, enabled, `Type=oneshot`,
   `After=multi-user.target`), which runs `/usr/local/bin/nvidia-v100-setup.sh` (root, dated
   2025-03-19). The script loads the modules, makes the device nodes, then runs
   `nvidia-smi -pm 1` and `nvidia-smi -c 3` (`# Set compute mode to COMPUTE_EXCLUSIVE_PROCESS`).
   The grep above misses it: it does not search `/usr/local/bin` (add it:
   `grep -rlnE "nvidia-smi.*-c|--compute-mode" /etc /usr/local/bin /usr/local/sbin /opt` finds it).
   Order matters: that unit runs after `multi-user.target`, i.e. after Docker and after
   `nvidia-compute-default.service` (`Before=docker.service`), so it would set Exclusive_Process
   again after our unit set Default. `After=nvidia-v100-setup.service` in our unit would form an
   ordering cycle with `Before=docker.service` (Docker is part of `multi-user.target`). The owner's
   switch-day choice: change the script's `nvidia-smi -c 3` to `nvidia-smi -c DEFAULT` (then the
   boot unit is only a check), or drop that line and keep the boot unit. The mode is Default
   today (set by hand on 2026-11-16) until the next reboot.

2. Install and start:

   ```bash
   sudo install -m 644 ops/systemd/nvidia-compute-default.service /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl enable --now nvidia-compute-default.service
   nvidia-smi --query-gpu=compute_mode --format=csv    # Default
   ```

3. Acceptance: reboot once; the mode must still be Default and the unit active (not failed):

   ```bash
   sudo reboot
   nvidia-smi --query-gpu=compute_mode --format=csv    # Default
   systemctl status nvidia-compute-default.service     # active (exited)
   ```

### Switch day: open items (from the D4 GPU session, 2026-11-17)

- **Outer reverse proxy (141.35.136.10) not read yet: no access.** Production `marcus.decimer.ai`
  sits behind it. Before v2 takes public traffic, read its setup (read only) and write the values
  here: the address it connects from (that is what `MARCUS_TRUSTED_PROXIES` / nginx must trust for
  `X-Forwarded-For`, never a CIDR), its body size limit (must allow 20 MB uploads; v2's nginx caps at
  21 MiB, v1's at 10 MB), whether it buffers responses (SSE at `/api/v2/papers/{id}/events` needs
  buffering off or `X-Accel-Buffering: no` honoured), and where TLS ends (the owner cookie is
  `Secure`; the browser must see https).
- **Client addresses behind the outer proxy (nginx `real_ip`, off by default).** Without it every
  user is the proxy's address: one per-IP budget for the world (rate limit, new owners, active
  papers, nginx `limit_conn`). Once the proxy is read: put the address(es) nginx sees it connect
  from (every proxy hop in front of nginx, e.g. a proxy on jarvis and 141.35.136.10;
  comma-separated single addresses, no names, no ranges) in `.env` as `MARCUS_REAL_IP_FROM=...`,
  run `docker compose -p marcus-v2 ... up -d nginx`, and check that `docker compose logs nginx`
  shows real client addresses (first field of each access line). `MARCUS_TRUSTED_PROXIES` (the
  API) stays nginx's own address. A bad value stops nginx at start. **A blocker for the COCONUT
  relay:** without it all users share one login budget (3/min, burst 3), and one user's typos
  lock everyone out of the COCONUT login for about 20 s.
- The Exclusive_Process setter (`nvidia-v100-setup.sh`, above) must be changed before the reboot test.
- **Wipe the v2 data volumes before deploying c69cdbc** (or anything after it) over an older v2 stack: crops
  stored before it are already red/blue swapped, and the OCSR handler would swap them a second time.
- GPU finding to close before the switch (judges/results/2026-11-17-gpu-session.md):
  dcgm-exporter exports no GPU metrics as configured (its DCGM host engine refuses to watch fields
  when not root). (Fixed in D4 fix round 1: worker-segment now keeps its TensorFlow budget,
  measured at 2048 MiB; MolScribe runs on cuda.)

### Decisions from the D4 GPU session (owner, 2026-11-17)

- **One GPU slot each** for segmentation (q.segment) and DECIMER OCSR (q.decimer). The Throughput gate (two papers
  at once faster than one after the other) stays FAIL as a known limit: 0.99× at 1 slot; 2 slots measured 1.02×,
  about the size of the 1-slot run-to-run spread (judges/results/2026-11-17-gpu-session.md).
- **Crops are stored in true colour** (what `GET /segments/{id}/image` serves). v1 saved crops with red and blue
  swapped (`cv2.imwrite` of an RGB array) and its engines read them that way, so for v1-identical accuracy the OCSR
  handler gives every engine that swapped image (`marcus.workers.ocsr.handler.v1_engine_input`; segment crops only,
  never image jobs). A crop downloaded and resubmitted as an image job is NOT swapped, so on a coloured structure
  it can get a different SMILES than the segment did.
- The segment worker replaces its process every 200 pages (`--max-tasks-per-child 200`): the segmentation library
  leaks about 3 MiB of GPU memory per page.

### Paper annotation (the local MARCUS model)

On demand per paper (`POST /api/v2/papers/{id}/annotation`, routes in
`marcus.api.routes.annotation`): an `annotate` step on q.llm builds the model input from the
paper's Docling text (title, abstract, introduction, as trained), asks the MARCUS model and
locates every value in the whole text. The GPU override runs the model in llama.cpp's
`llama-server` (`docker/Dockerfile.llama`, built at the GGUF's converter commit 7fce543 for the
V100) on its own internal network, shared only with `worker-llm`, with the GGUF mounted read-only:

```bash
MARCUS_LLM_GGUF=/path/to/qwen3.5-9b-marcus-v1-Q8_0.gguf MARCUS_LLM_USER="$(stat -c %u:%g "$MARCUS_LLM_GGUF")" \
  docker compose -p marcus-v2 -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

Measured on the jarvis V100 (2026-11-20): 8.9 GB of GPU memory at ctx 8192, about 2 s per short
paper. `worker-llm` (one process) calls it; the fake stack runs `worker-fake-annotate` instead (values
picked from the text by fixed rules). Without either, the API answers 503 (`annotate_enabled`).
Real-model smoke test, outside any stack (the sample PDF through docling, then the step's own
handler against llama-server): `MARCUS_LLM_GGUF=... ops/annotate_smoke.sh` (`--cpu` without a
GPU; about 70 s per paper on 16 CPU threads).

### R-group rows of a scaffold (the local R-group model)

On demand per prediction with R-group labels (`POST /api/v2/predictions/{id}/rgroups`; read with
`GET /api/v2/papers/{id}/rgroups` or `GET /api/v2/predictions/{id}/rgroups`; routes in
`marcus.api.routes.rgroups`): an `rgroups` step on q.rgroup sends the scaffold's labels, the text of
pages P-1..P+1 and the page image (scaled to the 150 dpi size, at most 1.3 MP) to the R-group
model (nuextract3-rgroup-v1, vision, Q8_0) in a second llama-server, `llama-rgroup`, and stores
the rows (`rgroup_extractions`, one per prediction; a re-run replaces them). Of the labels, only
those the page text names are asked for (all of them when it names none): OCSR sometimes adds a
label the drawing does not have, and the model would fill that column too. An unlabelled point
(`*`) is never asked for: the model was trained on printed labels only. A structure whose only
label is `*` is refused like one without R-groups (409), and the UI offers no reading for it. The request is the
one the model was trained on (`marcus.core.rgroup_extraction`, byte for byte the bake-off
client's). The step never reopens the paper. Exports: JSON `rgroup_rows` per segment, SDF
`MARCUS_RGROUP_ROWS`. The GPU override runs `llama-rgroup` beside `llama-server` (same image,
its own internal network `rgroup`, both GGUF files mounted read-only; 6.0 GB measured on a V100)
and `worker-rgroup` (one process) on its own queue q.rgroup, so an annotation run never holds back
an R-group reading, nor the other way round; the fake stack runs the fake reader in
`worker-fake-rgroup`. Without either, the API answers 503 (`rgroup_enabled`). Real-model smoke test against a running server:
`python ops/rgroup_smoke.py --url http://127.0.0.1:8080 --pdf paper.pdf --page 3 --labels R1,R2 --text docling.json`.

### nginx and api restarts

nginx re-resolves `api` every second (Docker DNS) and retries idempotent requests (GET, HEAD,
...) on a connection error or timeout, never uploads. `python ops/check_api_recreate.py [-f ...]`
recreates the api container and reports the longest stretch of 5xx answers through nginx.

## Test

```bash
docker compose -f docker-compose.test.yml up -d        # postgres :55432, redis :56379
uv run --extra tools pytest tests -q -m "not ml and not e2e"
uv run ruff check src tests alembic
```

ML tests run inside the model images (no network): `docker compose -p marcus-v2 run --rm
worker-segment-test` (also `worker-decimer-test`, `worker-torch-test`). End-to-end tests need the
fake stack (`pytest -m e2e`).

## Admin

The CLI runs inside the api container:

```bash
docker compose -p marcus-v2 exec api marcus apikey create --label "partner lab" [--daily-pages 2000]
docker compose -p marcus-v2 exec api marcus apikey list [--json]
docker compose -p marcus-v2 exec api marcus apikey revoke <id>
docker compose -p marcus-v2 exec api marcus purge --paper <id>     # delete one paper now
docker compose -p marcus-v2 exec api marcus purge --expired        # run the retention purge once
```

- `apikey create` prints the key (`mk_...`) once; only its SHA-256 is stored. Clients send it as
  `Authorization: Bearer <key>`. `list` never shows secrets. `revoke` is idempotent.
- Daily page quota (API keys only, default 2000, UTC day): a paper counts its pages once
  `check_pdf` knows them (1 while still checking), an image job counts 1. Above the quota,
  uploads get `429 {"detail": "daily quota exceeded"}`. A single upload may overshoot by its own
  page count. Browser owners are not subject to it.
- Exit codes: 0 ok, 1 not found or invalid input, 2 usage error.
