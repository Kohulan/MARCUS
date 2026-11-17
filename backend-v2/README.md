# MARCUS v2 backend

FastAPI + Celery + Postgres. One Python distribution `marcus` (`src/marcus/`).

## Run

```bash
# CPU stack with fake engines (fast, no GPU); nginx is the only published port
docker compose -p marcus-v2 -f docker-compose.yml -f docker-compose.fake.yml up -d --build
```

### nginx and api restarts

nginx re-resolves `api` every second (Docker DNS) and retries idempotent requests (GET, HEAD,
...) on a connection error or timeout, never uploads. `python ops/check_api_recreate.py [-f ...]`
recreates the api container and reports the longest stretch of 5xx answers through nginx.

### Networks

`internal` is an internal Docker network (no route out of the host); every service is on it.
Only `nginx` (its published port needs a non-internal network) and `worker-cpu` (the DOI
lookups, the only internet access the spec allows) also join `egress`. nginx keeps the fixed
address 172.30.0.10 outside the dynamic pool (`MARCUS_TRUSTED_PROXIES`). With the monitoring
override, Grafana publishes 127.0.0.1:13000 through its own `grafana-edge` network, which does no
masquerading (no route out either).

Switching a running stack to these networks: run `up -d --force-recreate` once (or `down` first;
volumes stay). Compose recreates a changed network, but containers it does not recreate (e.g.
postgres, redis) are re-attached without their service aliases, so `postgres` stops resolving.

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
