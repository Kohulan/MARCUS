"""Static checks on the compose files, nginx.conf, Prometheus and systemd configs.

Most tests read the YAML directly. The merged-override tests run `docker compose config` (the
Docker CLI only, no daemon) and are skipped where it is missing.
"""

import ipaddress
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.yml"
FAKE = ROOT / "docker-compose.fake.yml"


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text())


def _compose_config(*files: str) -> dict:
    """`docker compose config` of these files, as JSON, independent of the local .env: an empty
    env file, dummy passwords, nothing else from the caller's environment."""
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker CLI not available")
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", "/tmp"),
        "POSTGRES_PASSWORD": "test",
        "REDIS_PASSWORD": "test",
        "GRAFANA_ADMIN_PASSWORD": "test",  # the monitoring override
    }
    args = [docker, "compose", "--project-directory", str(ROOT), "--env-file", os.devnull]
    for name in files:
        args += ["-f", str(ROOT / name)]
    args += ["config", "--format", "json"]
    try:
        out = subprocess.run(args, env=env, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"docker compose not usable: {exc}")
        raise  # not reached: skip() raises
    if out.returncode != 0 and "is not a docker command" in out.stderr:
        pytest.skip("docker compose plugin not available")
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _nginx_address(compose) -> ipaddress.IPv4Address:
    return ipaddress.ip_address(
        compose["services"]["nginx"]["networks"]["internal"]["ipv4_address"]
    )


def test_nginx_address_is_outside_the_dynamic_pool(compose):
    """Docker gives other containers the lowest free address of `ip_range` (or of the whole
    subnet without one): nginx's fixed address must never be handed out, else a container
    started first takes it (nginx fails to start, or that container becomes the trusted proxy)."""
    (ipam,) = compose["networks"]["internal"]["ipam"]["config"]
    subnet = ipaddress.ip_network(ipam["subnet"])
    pool = ipaddress.ip_network(ipam["ip_range"])
    nginx = _nginx_address(compose)
    assert pool.subnet_of(subnet)
    assert nginx in subnet
    assert nginx not in pool


def test_trusted_proxies_is_exactly_nginx(compose):
    env = compose["services"]["api"]["environment"]
    assert json.loads(env["MARCUS_TRUSTED_PROXIES"]) == [str(_nginx_address(compose))]


def _dockerfile_api_cmd() -> list[str]:
    text = (ROOT / "docker" / "Dockerfile.api").read_text().replace("\\\n", " ")
    line = next(ln for ln in text.splitlines() if ln.startswith("CMD "))
    return json.loads(line[len("CMD ") :])


def _gunicorn_commands(compose) -> dict[str, list[str]]:
    return {
        "compose api": compose["services"]["api"]["command"],
        "Dockerfile.api": _dockerfile_api_cmd(),
    }


def test_gunicorn_trusts_no_forwarded_headers(compose):
    """R19: gunicorn's default --forwarded-allow-ips (127.0.0.1,::1) lets a loopback peer set the
    client IP via X-Forwarded-For before the app's own trusted-proxy walk. Both commands turn
    it off: the app alone (marcus.api.deps.client_ip) reads X-Forwarded-For."""
    for where, cmd in _gunicorn_commands(compose).items():
        flags = [a for a in cmd if a.startswith("--forwarded-allow-ips")]
        assert flags == ["--forwarded-allow-ips="], (where, cmd)


def _uvicorn_worker(argv: list[str]):
    """The UvicornWorker gunicorn would start for this command line (gunicorn's own parser)."""
    from gunicorn.config import Config
    from gunicorn.glogging import Logger
    from uvicorn.workers import UvicornWorker

    argv = [re.sub(r"\$\{[A-Z_]+:-([^}]*)\}", r"\1", a) for a in argv]  # compose defaults
    cfg = Config()
    for key, value in vars(cfg.parser().parse_args(argv)).items():
        if value is not None and key != "args":
            cfg.set(key.lower(), value)
    assert cfg.worker_class_str == "uvicorn.workers.UvicornWorker"
    return UvicornWorker(0, os.getpid(), [], None, 30, cfg, Logger(cfg))


def test_spoofed_xff_from_loopback_does_not_change_client_ip(compose, monkeypatch):
    """The command lines run through gunicorn's parser and uvicorn's worker config: a request
    from 127.0.0.1 with X-Forwarded-For reaches the app with 127.0.0.1 as its client IP."""
    import asyncio

    from fastapi import Request

    from marcus.api.deps import client_ip
    from marcus.core.settings import get_settings

    monkeypatch.setenv("MARCUS_TRUSTED_PROXIES", '["172.30.0.10"]')
    get_settings.cache_clear()
    try:
        for where, cmd in _gunicorn_commands(compose).items():
            seen = {}

            async def app(scope, receive, send):
                seen["ip"] = client_ip(Request(scope))

            worker = _uvicorn_worker(cmd[1:])
            worker.config.app = app
            worker.config.load()
            scope = {
                "type": "http",
                "scheme": "http",
                "method": "GET",
                "path": "/",
                "query_string": b"",
                "client": ("127.0.0.1", 40000),
                "headers": [(b"x-forwarded-for", b"6.6.6.6"), (b"x-forwarded-proto", b"https")],
            }
            asyncio.run(worker.config.loaded_app(scope, None, None))
            assert seen == {"ip": "127.0.0.1"}, where
    finally:
        get_settings.cache_clear()


def test_only_nginx_publishes_a_port(compose):
    published = {name for name, svc in compose["services"].items() if svc.get("ports")}
    assert published == {"nginx"}
    assert compose["services"]["nginx"]["ports"] == ["127.0.0.1:18090:8080"]


SEG_VERSION_SERVICES = ("api", "worker-cpu", "worker-segment")


def test_seg_version_is_the_pinned_segmenter_commit(compose):
    """The segmentation cache key must name the segmenter that really runs: the commit pinned in
    Dockerfile.tf, which is also DecimerSegmenter.version."""
    from marcus.workers.segment import DECIMER_SEGMENTATION_COMMIT

    dockerfile = (ROOT / "docker" / "Dockerfile.tf").read_text()
    assert f"DECIMER-Image-Segmentation.git@{DECIMER_SEGMENTATION_COMMIT}" in dockerfile
    for name in SEG_VERSION_SERVICES:
        env = compose["services"][name]["environment"]
        assert env["MARCUS_SEG_VERSION"] == DECIMER_SEGMENTATION_COMMIT, name


def test_fake_stack_seg_version_is_the_fake_segmenter():
    from marcus.workers.segment import FakeSegmenter

    fake = yaml.safe_load(FAKE.read_text())
    for name in ("api", "worker-cpu", "worker-fake-segment"):
        env = fake["services"][name]["environment"]
        assert env["MARCUS_SEG_VERSION"] == FakeSegmenter.version, name


def _command(svc: dict) -> list[str]:
    cmd = svc.get("command") or []
    return cmd.split() if isinstance(cmd, str) else list(cmd)


def _concurrency(cmd: list[str]) -> int:
    return int(cmd[cmd.index("-c") + 1])


def test_worker_cpu_has_one_process_more_than_its_slots(compose):
    """The dispatcher fills SLOTS['q.cpu'] = 4 with steps; the daily retention purge (a plain
    Celery task on q.cpu, no Step row) needs a process of its own, or a 4th step would wait
    behind it in the broker until the watchdog fails it as worker_lost."""
    from marcus.core.queues import SLOTS

    expected = SLOTS["q.cpu"] + 1
    assert _concurrency(_command(compose["services"]["worker-cpu"])) == expected
    dockerfile = (ROOT / "docker" / "Dockerfile.cpu").read_text()
    cmd_line = next(line for line in dockerfile.splitlines() if line.startswith("CMD"))
    assert f'"-c", "{expected}"' in cmd_line


def test_segment_worker_recycles_its_process(compose):
    """D4: the segmentation library leaks ~3 MiB of GPU memory per page; a budgeted process ran
    out after ~390 pages. The pool process is replaced every 200 pages (compose and image CMD)."""
    cmd = _command(compose["services"]["worker-segment"])
    assert cmd[cmd.index("--max-tasks-per-child") + 1] == "200"
    assert _concurrency(cmd) == 1
    dockerfile = (ROOT / "docker" / "Dockerfile.tf").read_text()
    assert '"--max-tasks-per-child", "200"' in dockerfile


def test_exactly_one_service_runs_celery_beat(compose):
    fake = yaml.safe_load(FAKE.read_text())
    services = {**compose["services"]}
    for name, svc in fake["services"].items():
        services[name] = {**services.get(name, {}), **svc}
    beat = sorted(name for name, svc in services.items() if "-B" in _command(svc))
    assert beat == ["worker-cpu"]
    assert "replicas" not in compose["services"]["worker-cpu"].get("deploy", {})


def test_durability_shortcuts_only_on_the_test_database(compose):
    """fsync=off & co. speed up the throwaway test DB; the real stack must keep durability."""
    test = yaml.safe_load((ROOT / "docker-compose.test.yml").read_text())
    assert "fsync=off" in _command(test["services"]["postgres"])
    for path in (COMPOSE, FAKE, ROOT / "docker-compose.gpu.yml"):
        if path.exists():
            assert "fsync" not in path.read_text(), path.name


# --- metrics, monitoring ----------------------------------------------------------------------

MONITORING = ROOT / "docker-compose.monitoring.yml"


def test_metrics_service_is_internal_and_reads_data_read_only(compose):
    svc = compose["services"]["metrics"]
    assert svc["command"] == ["python", "-m", "marcus.api.metrics"]
    assert "ports" not in svc
    assert svc["networks"] == ["internal"]
    assert svc["volumes"] == ["data:/data:ro"]
    assert svc["image"] == compose["services"]["api"]["image"]


def test_nginx_sse_location_covers_images():
    conf = (ROOT / "docker" / "nginx.conf").read_text()
    assert "location ~ ^/api/v2/(papers|images)/[^/]+/events$ {" in conf


def test_nginx_never_proxies_metrics():
    conf = (ROOT / "docker" / "nginx.conf").read_text()
    assert "metrics" not in conf and "9100" not in conf


# --- the web UI: nginx serves frontend-v2 (F15) ------------------------------------------------

FRONTEND = ROOT.parent / "frontend-v2"
UI_LOCATIONS = FRONTEND / "deploy" / "ui-locations.conf"
UI_LOCATIONS_IN_IMAGE = "/etc/nginx/marcus/ui-locations.conf"
# Exact, from Global Constraints (frontend v2 plan).
APP_CSP = (
    "default-src 'self'; script-src 'self' https://matomo.nfdi4chem.de; "
    "connect-src 'self' https://pubchem.ncbi.nlm.nih.gov "
    "https://matomo.nfdi4chem.de; img-src 'self' data: blob: https://matomo.nfdi4chem.de; "
    "style-src 'self'; font-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'"
)
KETCHER_CSP = (
    "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; "
    "object-src 'none'; base-uri 'self'; form-action 'none'; frame-ancestors 'self'"
)
UI_HEADERS = {
    "content-security-policy",
    "x-content-type-options",
    "x-frame-options",
    "referrer-policy",
    "cross-origin-resource-policy",
    "permissions-policy",
}


UI_INCLUDE = re.compile(r"^(\s*)include (/etc/nginx/marcus/(\S+));$", re.M)


def _ui_locations() -> str:
    """ui-locations.conf with its header files (deploy/headers-*.conf) read in where it
    includes them, as nginx reads it."""

    def read_in(m: re.Match) -> str:
        part = (FRONTEND / "deploy" / m.group(3)).read_text()
        return "\n".join(m.group(1) + line for line in part.splitlines())

    return UI_INCLUDE.sub(read_in, UI_LOCATIONS.read_text())


def _strip_comments(conf: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in conf.splitlines())


def _location_blocks(conf: str) -> list[tuple[str, str]]:
    """Every `location … {}` block as (its match, its own body without nested blocks)."""
    text = _strip_comments(conf)
    blocks: list[tuple[str, str]] = []
    stack: list[tuple[str, list[str]]] = []  # (header, own body parts)
    pos = 0
    for m in re.finditer(r"[{}]", text):
        chunk = text[pos : m.start()]
        pos = m.end()
        if m.group() == "{":
            # the header is the last statement before the brace
            head = chunk.rsplit(";", 1)[-1].strip()
            if stack:
                stack[-1][1].append(chunk[: len(chunk) - len(chunk.rsplit(";", 1)[-1])])
            stack.append((head, []))
        else:
            head, parts = stack.pop()
            parts.append(chunk)
            if head.startswith("location"):
                blocks.append((head, "".join(parts)))
    return blocks


def test_nginx_service_is_built_from_the_frontend(compose):
    nginx = compose["services"]["nginx"]
    assert nginx["build"] == {"context": "../frontend-v2", "dockerfile": "Dockerfile"}
    assert nginx["image"] == "marcus-v2-nginx:local"
    # nginx.conf stays a bind mount: the image carries only the UI and its locations file
    assert "./docker/nginx.conf:/etc/nginx/nginx.conf:ro" in nginx["volumes"]


def test_frontend_image_serves_the_build_with_its_locations_file():
    dockerfile = (FRONTEND / "Dockerfile").read_text()
    froms = re.findall(r"^FROM\s+(\S+)", dockerfile, re.M)
    assert froms[0] == "node:22-alpine"
    assert re.fullmatch(r"nginxinc/nginx-unprivileged:\d+\.\d+-alpine", froms[-1]), froms[-1]
    assert re.search(r"^RUN npm ci && npm run build$", dockerfile, re.M)
    assert re.search(r"^COPY --from=\S+ /\S+/dist /usr/share/nginx/marcus-ui$", dockerfile, re.M)
    assert re.search(
        rf"^COPY deploy/ui-locations\.conf {re.escape(UI_LOCATIONS_IN_IMAGE)}$", dockerfile, re.M
    )
    # every header file it includes is in the image, and in the local dev nginx (serve-local.sh)
    included = [m.group(2) for m in UI_INCLUDE.finditer(UI_LOCATIONS.read_text())]
    assert {path.rsplit("/", 1)[1] for path in included} == {
        "headers-app.conf", "headers-ketcher.conf"
    }  # fmt: skip
    serve_local = (FRONTEND / "scripts" / "serve-local.sh").read_text()
    for path in set(included):
        name = path.rsplit("/", 1)[1]
        assert re.search(rf"^COPY deploy/{re.escape(name)} {re.escape(path)}$", dockerfile, re.M)
        assert f'"$PWD/deploy/{name}:{path}:ro"' in serve_local, name
    ignored = (FRONTEND / ".dockerignore").read_text().split()
    for name in ("node_modules", "dist", "dist-ssr", "test-results", "playwright-report",
                 ".impeccable"):  # fmt: skip
        assert name in ignored, name


def test_nginx_includes_the_ui_locations_instead_of_a_404():
    conf = (ROOT / "docker" / "nginx.conf").read_text()
    server = conf[conf.index("server {") :]
    assert re.search(rf"^\s{{8}}include {re.escape(UI_LOCATIONS_IN_IMAGE)};", server, re.M)
    assert not re.search(r"location\s+/\s*\{\s*return\s+404;", conf)
    # the API locations are still there, and the UI file defines no API location
    assert "location /api/v2/ {" in conf
    assert "/api/" not in _strip_comments(_ui_locations())


def test_ui_locations_carry_both_exact_csps_mime_types_and_gzip():
    conf = _ui_locations()
    # COCONUT only through the relay (same origin): the browser never connects to it
    assert "coconut" not in _strip_comments(conf)
    csps = set(re.findall(r'add_header Content-Security-Policy "([^"]*)" always;', conf))
    assert csps == {APP_CSP, KETCHER_CSP}
    assert re.search(r"^include /etc/nginx/mime\.types;", conf, re.M)
    assert re.search(r"^\s*gzip on;", conf, re.M)


def test_every_ui_location_with_headers_sets_all_six():
    """An add_header in a location drops every inherited one (the server's own security
    headers included): a location that sets any header must set the whole set, with always."""
    blocks = _location_blocks(_ui_locations())
    assert len(blocks) >= 5, blocks
    for head, body in blocks:
        names = {n.lower() for n in re.findall(r"^\s*add_header\s+(\S+)\s+.*\balways;", body, re.M)}
        if not re.search(r"^\s*add_header\b", body, re.M):
            continue
        assert UI_HEADERS <= names, (head, UI_HEADERS - names)
        # Ketcher CSP only under /ketcher/, the app CSP everywhere else
        csp = re.search(r'add_header Content-Security-Policy "([^"]*)"', body).group(1)
        assert csp == (KETCHER_CSP if "/ketcher/" in head else APP_CSP), head


def test_dispatcher_healthcheck_reads_the_heartbeat(compose):
    hc = compose["services"]["dispatcher"]["healthcheck"]
    assert hc["test"] == ["CMD", "python", "-m", "marcus.dispatcher.health"]


def test_gunicorn_uses_json_logs(compose):
    assert "marcus.api.main:create_app(json_logs=True)" in compose["services"]["api"]["command"]


def test_monitoring_is_a_separate_override_with_grafana_on_loopback():
    mon = yaml.safe_load(MONITORING.read_text())
    assert set(mon["services"]) == {"prometheus", "grafana"}
    assert "ports" not in mon["services"]["prometheus"]
    assert mon["services"]["grafana"]["ports"] == ["127.0.0.1:13000:3000"]
    env = mon["services"]["grafana"]["environment"]
    assert env["GF_AUTH_ANONYMOUS_ENABLED"] == "false"
    assert "GRAFANA_ADMIN_PASSWORD" in env["GF_SECURITY_ADMIN_PASSWORD"]
    base = yaml.safe_load(COMPOSE.read_text())["services"]
    assert not {"prometheus", "grafana"} & set(base)


def test_prometheus_scrapes_metrics_every_15s():
    cfg = yaml.safe_load((ROOT / "ops" / "prometheus.yml").read_text())
    assert cfg["global"]["scrape_interval"] == "15s"
    jobs = {job["job_name"]: job for job in cfg["scrape_configs"]}
    assert set(jobs) == {"marcus", "dcgm"}
    assert jobs["marcus"]["static_configs"][0]["targets"] == ["metrics:9100"]


def test_dashboard_covers_the_required_panels():
    dash = json.loads((ROOT / "ops" / "grafana" / "marcus.json").read_text())
    exprs = " ".join(t["expr"] for p in dash["panels"] for t in p["targets"])
    for needle in (
        "marcus_queue_pending", "marcus_queue_running", "marcus_wait_seconds_bucket",
        "marcus_step_seconds_bucket", "marcus_first_smiles_seconds_bucket",
        "marcus_steps_failed", "marcus_disk_free_bytes",
        "marcus_dispatcher_heartbeat_age_seconds",
    ):  # fmt: skip
        assert needle in exprs, needle


def test_dashboard_never_rates_windowed_series():
    """Last-hour windows are gauges: rate()/increase() on them would read the drops as resets."""
    dash = json.loads((ROOT / "ops" / "grafana" / "marcus.json").read_text())
    for p in dash["panels"]:
        for t in p["targets"]:
            e = t["expr"]
            if "marcus_" in e and not e.startswith("marcus_dispatcher"):
                assert "rate(" not in e and "increase(" not in e, e
    assert "marcus_step_failures_total" not in json.dumps(dash)


def test_prometheus_alerts_on_low_disk():
    """Review I6 / spec section 12: a disk-use alarm, not only a gauge and a panel. The rule
    file is loaded by prometheus.yml and mounted by the monitoring override."""
    cfg = yaml.safe_load((ROOT / "ops" / "prometheus.yml").read_text())
    assert cfg["rule_files"] == ["/etc/prometheus/alerts.yml"]
    rules = yaml.safe_load((ROOT / "ops" / "prometheus-alerts.yml").read_text())
    alerts = {r["alert"]: r for g in rules["groups"] for r in g["rules"]}
    low = alerts["MarcusDiskLow"]
    assert "marcus_disk_free_bytes" in low["expr"] and low["labels"]["severity"] == "warning"
    full = alerts["MarcusDiskUploadsRefused"]
    assert "marcus_disk_free_bytes" in full["expr"] and full["labels"]["severity"] == "critical"
    # the critical threshold is the API's upload floor (Settings.min_free_disk_bytes default)
    from marcus.core.settings import Settings

    floor = Settings.model_fields["min_free_disk_bytes"].default
    assert f"< {floor}" in full["expr"]
    assert alerts["MarcusMetricsDown"]["expr"].startswith('up{job="marcus"}')
    mon = yaml.safe_load(MONITORING.read_text())
    assert (
        "./ops/prometheus-alerts.yml:/etc/prometheus/alerts.yml:ro"
        in mon["services"]["prometheus"]["volumes"]
    )


def test_prometheus_negotiates_openmetrics_first():
    cfg = yaml.safe_load((ROOT / "ops" / "prometheus.yml").read_text())
    for job in cfg["scrape_configs"]:
        assert job["scrape_protocols"] == ["OpenMetricsText1.0.0", "PrometheusText0.0.4"], job


# --- networks: internal-only, egress for nginx and worker-cpu ---------------------------------

EGRESS_SERVICES = {"nginx", "worker-cpu"}  # nginx: published port; worker-cpu: DOI lookups


def _non_internal_members(config: dict) -> set[str]:
    """Services attached to any network that is not `internal: true` (incl. the default one)."""
    networks = config.get("networks", {})
    members = set()
    for name, svc in config["services"].items():
        if svc.get("network_mode") == "none":
            continue
        joined = svc.get("networks") or {"default": None}
        for net in joined:
            if not networks.get(net, {}).get("internal", False):
                members.add(name)
    return members


def test_internal_network_is_internal_and_egress_is_not(compose):
    nets = compose["networks"]
    assert nets["internal"]["internal"] is True
    assert not nets["egress"].get("internal", False)
    # the reserved nginx address and the dynamic pool stay as they were
    (ipam,) = nets["internal"]["ipam"]["config"]
    assert ipam == {"subnet": "172.30.0.0/24", "ip_range": "172.30.0.128/25"}


@pytest.mark.parametrize(
    "files",
    [
        ("docker-compose.yml",),
        ("docker-compose.yml", "docker-compose.fake.yml"),
        ("docker-compose.yml", "docker-compose.gpu.yml"),
    ],
    ids=["base", "fake", "gpu"],
)
def test_only_nginx_and_worker_cpu_leave_the_internal_network(files):
    config = _compose_config(*files)
    assert _non_internal_members(config) == EGRESS_SERVICES
    for name in EGRESS_SERVICES:
        assert set(config["services"][name]["networks"]) == {"internal", "egress"}, name
    nginx = config["services"]["nginx"]["networks"]["internal"]
    assert nginx["ipv4_address"] == "172.30.0.10"
    published = {name for name, svc in config["services"].items() if svc.get("ports")}
    assert published == {"nginx"}


def test_monitoring_keeps_prometheus_internal_and_grafana_without_egress():
    """Grafana publishes a loopback port, which needs a non-internal network; its own edge
    network does no masquerading, so it has no route out. Prometheus stays internal-only."""
    mon = yaml.safe_load(MONITORING.read_text())
    assert mon["services"]["prometheus"]["networks"] == ["internal"]
    assert set(mon["services"]["grafana"]["networks"]) == {"internal", "grafana-edge"}
    edge = mon["networks"]["grafana-edge"]
    assert edge["driver_opts"]["com.docker.network.bridge.enable_ip_masquerade"] == "false"


# --- GPU override -----------------------------------------------------------------------------

GPU = "docker-compose.gpu.yml"
GPU_SERVICES = ("worker-segment", "worker-decimer", "worker-molnextr", "worker-molscribe")
# Production card (Task D4 host): 32 GB. Budgets cap the frameworks' allocators; each process's
# CUDA context comes on top and is counted here at a generous 512 MiB.
GPU_TOTAL_MIB = 32 * 1024
CUDA_CONTEXT_MIB = 512
BUDGET_LIMIT_MIB = 20 * 1024
# llama-server (the one MARCUS model, nuextract3-marcus-multi-v1, for annotation and R-group rows):
# the Q8_0 GGUF + its f16 vision projector, two slots of 10240 tokens (ctx 20480), measured 6.33 GB
# after load and 6.46 GB peak on a V100 (MARCUS-training models/nuextract3-marcus-multi-v1/
# README.md, 2026-11-22), counted here as 6.5 GiB; llama.cpp cannot be capped, so it is counted on
# top of the model workers' budgets and the card must still keep CARD_HEADROOM_MIB free.
LLAMA_GPU_MIB = 6656
LLAMA_CTX = 20480  # what LLAMA_GPU_MIB was measured with
LLAMA_SLOTS = 2
CARD_HEADROOM_MIB = 2 * 1024


def _gpu_reservation(svc: dict) -> list[dict]:
    return svc.get("deploy", {}).get("resources", {}).get("reservations", {}).get("devices", [])


def test_gpu_override_budget_under_20gb():
    config = _compose_config("docker-compose.yml", GPU)
    services = config["services"]
    env = {name: services[name]["environment"] for name in GPU_SERVICES}
    assert env["worker-segment"]["MARCUS_GPU_MEM_MB"] == "2048"  # D4: peak < 1 GB
    assert env["worker-decimer"]["MARCUS_GPU_MEM_MB"] == "4096"
    assert env["worker-molnextr"]["MARCUS_TORCH_MEM_FRACTION"] == "0.09"
    assert env["worker-molscribe"]["MARCUS_TORCH_MEM_FRACTION"] == "0.09"
    # D4: no loss on the fixture judge, so MolScribe runs on the GPU in the GPU stack
    assert env["worker-molscribe"]["MARCUS_MOLSCRIBE_DEVICE"] == "cuda"
    budget = int(env["worker-segment"]["MARCUS_GPU_MEM_MB"])
    budget += int(env["worker-decimer"]["MARCUS_GPU_MEM_MB"])
    for name in ("worker-molnextr", "worker-molscribe"):
        budget += float(env[name]["MARCUS_TORCH_MEM_FRACTION"]) * GPU_TOTAL_MIB
    budget += CUDA_CONTEXT_MIB * len(GPU_SERVICES)
    assert budget <= BUDGET_LIMIT_MIB, budget
    card = budget + LLAMA_GPU_MIB + CUDA_CONTEXT_MIB
    assert card <= GPU_TOTAL_MIB - CARD_HEADROOM_MIB, card
    cmd = services["llama-server"]["command"]
    assert cmd[cmd.index("--ctx-size") + 1] == str(LLAMA_CTX)  # what LLAMA_GPU_MIB was sized for
    assert cmd[cmd.index("--parallel") + 1] == str(LLAMA_SLOTS)
    assert "llama-rgroup" not in services  # one model server, no second one on the card

    published = {name for name, svc in services.items() if svc.get("ports")}
    assert published == {"nginx"}
    assert _non_internal_members(config) == EGRESS_SERVICES


def test_llama_gpu_memory_is_the_measured_figure_everywhere():
    """Measured on a V100 (2026-11-22): the one llama-server (multi-task model + projector, two
    slots, ctx 20480) takes about 6.5 GB. The old figures (8.9 GB for the 9B annotation model,
    6.0 GB for the R-group server, the "about 11 GB" estimate) are gone from the files that size
    the card."""
    assert LLAMA_GPU_MIB == 6656
    for path in (ROOT / GPU, ROOT / "ops" / "annotate_smoke.sh", ROOT / "README.md"):
        text = path.read_text()
        assert "6.5 GB" in text, path.name
        for old in ("11 GB", "8.9 GB", "6.0 GB"):
            assert old not in text, (path.name, old)


def test_gpu_override_reserves_the_gpu_for_exactly_the_model_workers():
    services = _compose_config("docker-compose.yml", GPU)["services"]
    reserved = {name for name, svc in services.items() if _gpu_reservation(svc)}
    assert reserved == {*GPU_SERVICES, "llama-server", "dcgm-exporter"}
    for name in reserved:
        (device,) = _gpu_reservation(services[name])
        assert device["driver"] == "nvidia" and device["capabilities"] == ["gpu"], name
        assert device["count"] == 1, name


def test_gpu_override_builds_the_cuda_images():
    services = _compose_config("docker-compose.yml", GPU)["services"]
    expected = {
        "worker-segment": ("docker/Dockerfile.tf", "marcus-v2-tf:cuda"),
        "worker-decimer": ("docker/Dockerfile.tf", "marcus-v2-tf:cuda"),
        "worker-molnextr": ("docker/Dockerfile.torch", "marcus-v2-torch:cuda"),
        "worker-molscribe": ("docker/Dockerfile.torch", "marcus-v2-torch:cuda"),
    }
    for name, (dockerfile, image) in expected.items():
        svc = services[name]
        assert svc["build"]["dockerfile"] == dockerfile, name
        assert svc["build"]["args"]["VARIANT"] == "cuda", name
        assert svc["build"]["target"] == "runtime", name
        assert svc["image"] == image, name
    # the base stack keeps the CPU images
    base = yaml.safe_load(COMPOSE.read_text())["services"]
    for name in expected:
        assert base[name]["build"]["args"]["VARIANT"] == "cpu", name
        assert not base[name]["image"].endswith(":cuda"), name


def test_dcgm_exporter_is_internal_only_and_scraped():
    services = _compose_config("docker-compose.yml", GPU)["services"]
    dcgm = services["dcgm-exporter"]
    assert set(dcgm["networks"]) == {"internal"}
    assert not dcgm.get("ports")
    assert re.fullmatch(r"nvcr\.io/nvidia/k8s/dcgm-exporter:[\w.-]+", dcgm["image"])
    cfg = yaml.safe_load((ROOT / "ops" / "prometheus.yml").read_text())
    targets = [
        t for job in cfg["scrape_configs"] for c in job["static_configs"] for t in c["targets"]
    ]
    assert "dcgm-exporter:9400" in targets
    base = yaml.safe_load(COMPOSE.read_text())["services"]
    assert "dcgm-exporter" not in base


@pytest.mark.parametrize("name", ["worker-segment", "worker-decimer"])
def test_tf_workers_cap_blas_threads(compose, name):
    """OpenMP / OpenBLAS read their variables when numpy is first imported (before TF's own
    thread settings apply), so compose sets them for the TF workers too."""
    env = compose["services"][name]["environment"]
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        assert env[var] == "${MARCUS_TF_INTRA_THREADS:-4}", (name, var)


# --- boot unit --------------------------------------------------------------------------------


UNIT = ROOT / "ops" / "systemd" / "nvidia-compute-default.service"
MODE_CHECK = "nvidia-smi -i 0 --query-gpu=compute_mode --format=csv,noheader"


def _unit_settings() -> dict[str, list[str]]:
    settings: dict[str, list[str]] = {}
    for line in UNIT.read_text().splitlines():
        if "=" in line and not line.startswith(("#", "[")):
            key, value = line.split("=", 1)
            settings.setdefault(key, []).append(value)
    return settings


def test_nvidia_compute_default_unit_runs_before_docker():
    unit = _unit_settings()
    assert unit["ExecStart"] == ["/usr/bin/nvidia-smi -i 0 -c DEFAULT"]
    assert unit["Type"] == ["oneshot"]
    assert "docker.service" in unit["Before"][0].split()
    assert "nvidia-persistenced.service" in unit["After"][0].split()
    assert "nvidia-persistenced.service" in unit["Wants"][0].split()
    assert unit["WantedBy"] == ["multi-user.target"]


def test_nvidia_compute_default_unit_fails_when_the_mode_is_not_default():
    """A switch that did not take must fail the unit (not show active while the card is still
    Exclusive_Process): ExecStartPost reads the mode back."""
    (post,) = _unit_settings()["ExecStartPost"]
    assert MODE_CHECK in post and "grep -qx Default" in post


def test_switch_day_steps_find_the_boot_time_setter_and_check_after_a_reboot():
    """jarvis's card goes back to Exclusive_Process on reboot, so something sets it at boot: the
    switch-day steps (unit header and README) find and disable it, then reboot once and check."""
    readme = (ROOT / "README.md").read_text()
    for text in (UNIT.read_text(), readme):
        assert "systemctl list-unit-files | grep -i nvidia" in text
        assert "EXCLUSIVE" in text and "/etc/rc.local" in text and "/etc/cron" in text
        assert "nvidia-persistenced" in text
        assert "sudo reboot" in text
        assert "nvidia-smi --query-gpu=compute_mode --format=csv" in text


# --- nginx: re-resolve the api quickly, retry idempotent requests ------------------------------


def test_nginx_re_resolves_the_api_quickly_and_retries_only_idempotent_requests():
    conf = (ROOT / "docker" / "nginx.conf").read_text()
    resolver = re.search(r"^\s*resolver\s+127\.0\.0\.11\s+valid=(\d+)s", conf, re.M)
    assert resolver and int(resolver.group(1)) <= 2
    assert re.search(r"server api:8000 [^;]*\bresolve\b", conf)
    nexts = re.findall(r"^\s*proxy_next_upstream\s+([^;]+);", conf, re.M)
    assert nexts, "proxy_next_upstream not set"
    for value in nexts:
        assert {"error", "timeout"} <= set(value.split()), value
        assert "non_idempotent" not in value  # POST/PATCH (uploads) are never sent twice
    tries = re.findall(r"^\s*proxy_next_upstream_tries\s+(\d+);", conf, re.M)
    assert tries and all(1 < int(t) <= 5 for t in tries)


# --- upload buffering is bounded (review I7) --------------------------------------------------


def _size_bytes(text: str) -> int:
    m = re.fullmatch(r"(\d+)([kmg])", text.strip().lower())
    assert m, text
    return int(m.group(1)) * {"k": 2**10, "m": 2**20, "g": 2**30}[m.group(2)]


@pytest.mark.parametrize("name", ["nginx", "api"])
def test_upload_spool_tmpfs_is_sized_and_inside_the_memory_limit(compose, name):
    """nginx spools request bodies and Starlette spools uploads to /tmp, a tmpfs (memory): each
    has a size, and the container a memory limit above it, so a slow-body flood fills a bounded
    tmpfs (that upload fails) instead of the host's memory."""
    svc = compose["services"][name]
    (tmp,) = [t for t in svc["tmpfs"] if t.split(":")[0] == "/tmp"]
    opts = dict(o.split("=", 1) for o in tmp.split(":", 1)[1].split(",")) if ":" in tmp else {}
    assert "size" in opts, tmp
    assert "mem_limit" in svc, name
    assert _size_bytes(opts["size"]) < _size_bytes(svc["mem_limit"])


def test_nginx_limits_connections_and_uploads_per_address():
    conf = (ROOT / "docker" / "nginx.conf").read_text()
    zones = dict(re.findall(r"^\s*limit_conn_zone\s+(\$\w+)\s+zone=(\w+):\w+;", conf, re.M))
    assert zones.get("$binary_remote_addr") == "perip"
    # uploads: only POST /api/v2/papers and /api/v2/images bodies, keyed by address
    assert zones.get("$upload_key") == "uploads"
    assert re.search(r'"~\^POST:/api/v2/\(papers\|images\)\$"\s+\$binary_remote_addr;', conf)
    # the values come from the environment at start (docker/nginx-edge.sh), included by exact
    # path inside the server block: nginx does not start without them
    assert re.search(r"^\s{8}include /tmp/nginx/limits\.conf;", conf, re.M)
    script = (ROOT / "docker" / "nginx-edge.sh").read_text()
    assert 'conn="${MARCUS_NGINX_CONN_PER_IP:-64}"' in script
    assert 'uploads="${MARCUS_NGINX_UPLOADS_PER_IP:-4}"' in script
    assert re.search(r"^\s*limit_conn_status\s+429;", conf, re.M)
    timeout = re.search(r"^\s*client_body_timeout\s+(\d+)s;", conf, re.M)
    assert timeout and int(timeout.group(1)) <= 20


def test_nginx_edge_script_is_mounted_executable_into_the_entrypoint(compose):
    nginx = compose["services"]["nginx"]
    assert "./docker/nginx-edge.sh:/docker-entrypoint.d/25-marcus-edge.sh:ro" in nginx["volumes"]
    assert os.access(ROOT / "docker" / "nginx-edge.sh", os.X_OK)
    env = nginx["environment"]
    assert env["MARCUS_NGINX_CONN_PER_IP"] == "${MARCUS_NGINX_CONN_PER_IP:-64}"
    assert env["MARCUS_NGINX_UPLOADS_PER_IP"] == "${MARCUS_NGINX_UPLOADS_PER_IP:-4}"


# --- the nginx container itself (docker; skipped without it) ----------------------------------

NGINX_IMAGE = "nginxinc/nginx-unprivileged:1.31-alpine"  # as frontend-v2/Dockerfile
# The files compose mounts into the production nginx (the UI locations are baked into its image).
_NGINX_MOUNTS = [
    "-v", f"{ROOT / 'docker' / 'nginx.conf'}:/etc/nginx/nginx.conf:ro",
    "-v", f"{ROOT / 'docker' / 'nginx-edge.sh'}:/docker-entrypoint.d/25-marcus-edge.sh:ro",
    "-v", f"{ROOT / 'docker' / 'coconut-relay.js'}:/etc/nginx/marcus/coconut-relay.js:ro",
    "-v", f"{UI_LOCATIONS}:{UI_LOCATIONS_IN_IMAGE}:ro",
    *(arg for name in ("headers-app.conf", "headers-ketcher.conf") for arg in (
        "-v", f"{FRONTEND / 'deploy' / name}:/etc/nginx/marcus/{name}:ro")),
]  # fmt: skip


def _docker_or_skip() -> str:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker CLI not available")
    probe = subprocess.run([docker, "image", "inspect", NGINX_IMAGE], capture_output=True)
    if probe.returncode != 0:
        pytest.skip(f"{NGINX_IMAGE} not pulled")
    return docker


def _nginx_run(env: dict[str, str], *cmd: str) -> subprocess.CompletedProcess:
    """The production nginx config in the production image (read-only root, tmpfs /tmp, no
    network), its entrypoint scripts included, running `cmd` instead of the server."""
    docker = _docker_or_skip()
    args = [
        docker, "run", "--rm", "--network", "none", "--read-only", "--tmpfs", "/tmp",
        "--add-host", "api:127.0.0.1",
        *_NGINX_MOUNTS,
    ]  # fmt: skip
    for key, value in env.items():
        args += ["-e", f"{key}={value}"]
    args += [NGINX_IMAGE, *cmd]
    return subprocess.run(args, capture_output=True, text=True, timeout=120)


def test_nginx_starts_with_the_default_limits():
    out = _nginx_run({}, "nginx", "-T")
    assert out.returncode == 0, out.stderr
    assert "limit_conn perip 64;" in out.stdout and "limit_conn uploads 4;" in out.stdout


def test_nginx_limits_follow_the_environment_and_refuse_garbage():
    out = _nginx_run(
        {"MARCUS_NGINX_CONN_PER_IP": "500", "MARCUS_NGINX_UPLOADS_PER_IP": "50"}, "nginx", "-T"
    )
    assert out.returncode == 0, out.stderr
    assert "limit_conn perip 500;" in out.stdout and "limit_conn uploads 50;" in out.stdout
    for bad in ("0", "-1", "64;", "lots"):
        out = _nginx_run({"MARCUS_NGINX_UPLOADS_PER_IP": bad}, "nginx", "-T")
        assert out.returncode != 0, bad
        assert "MARCUS_NGINX_UPLOADS_PER_IP must be a positive integer" in out.stdout + out.stderr


# --- switch day: client addresses behind the outer proxy (review I9) ---------------------------


def _client_seen_by_nginx(env: dict[str, str], xff: str) -> str:
    """Start the production nginx (fake outer proxy = a request from 127.0.0.1 inside the
    container carrying `xff`) and return the client address nginx logs (= the address it sends
    the API in X-Forwarded-For)."""
    docker = _docker_or_skip()
    name = f"marcus-realip-test-{os.getpid()}-{abs(hash((tuple(env.items()), xff)))}"
    args = [
        docker, "run", "-d", "--name", name, "--network", "none", "--read-only",
        "--tmpfs", "/tmp", "--add-host", "api:127.0.0.1",
        *_NGINX_MOUNTS,
    ]  # fmt: skip
    for key, value in env.items():
        args += ["-e", f"{key}={value}"]
    started = subprocess.run([*args, NGINX_IMAGE], capture_output=True, text=True, timeout=60)
    assert started.returncode == 0, started.stderr
    try:
        for _ in range(50):
            ready = subprocess.run(
                [docker, "exec", name, "sh", "-c", "test -f /tmp/nginx.pid"], capture_output=True
            )
            if ready.returncode == 0:
                break
            subprocess.run(["sleep", "0.1"])
        subprocess.run(
            [
                docker,
                "exec",
                name,
                "wget",
                "-q",
                "-O",
                "/dev/null",
                "--header",
                f"X-Forwarded-For: {xff}",
                "http://127.0.0.1:8080/not-api",
            ],
            capture_output=True,
            timeout=30,
        )  # fmt: skip  (404 by design: wget exits 1)
        logs = subprocess.run([docker, "logs", name], capture_output=True, text=True, timeout=30)
        lines = [ln for ln in logs.stdout.splitlines() if '"GET /not-api ' in ln]
        assert len(lines) == 1, logs.stdout + logs.stderr
        return lines[0].split(" ", 1)[0]
    finally:
        subprocess.run([docker, "rm", "-f", name], capture_output=True, timeout=60)


def test_real_ip_switch_is_off_by_default():
    """Off: X-Forwarded-For from the peer is ignored, the socket peer is the client."""
    assert _client_seen_by_nginx({}, "203.0.113.7") == "127.0.0.1"


def test_real_ip_from_the_configured_proxy_only():
    on = {"MARCUS_REAL_IP_FROM": "127.0.0.1"}
    assert _client_seen_by_nginx(on, "203.0.113.7") == "203.0.113.7"
    # a client-sent entry in front of the proxy's own is never taken
    assert _client_seen_by_nginx(on, "198.51.100.9, 203.0.113.7") == "203.0.113.7"
    # a peer that is not the configured proxy cannot pick its address
    other = {"MARCUS_REAL_IP_FROM": "10.1.2.3"}
    assert _client_seen_by_nginx(other, "203.0.113.7") == "127.0.0.1"
    # several hops (a proxy on the host behind the outer one), comma-separated
    hops = {"MARCUS_REAL_IP_FROM": "10.1.2.3,127.0.0.1"}
    assert _client_seen_by_nginx(hops, "203.0.113.7, 10.1.2.3") == "203.0.113.7"


@pytest.mark.parametrize(
    "bad", ["proxy.example", "10.0.0.0/8", "0.0.0.0/0", "1.2.3", "1.2.3.4;", "256.1.1.1", "::"]
)
def test_real_ip_refuses_names_ranges_and_garbage(bad):
    out = _nginx_run({"MARCUS_REAL_IP_FROM": bad}, "nginx", "-T")
    assert out.returncode != 0, bad


def test_real_ip_switch_is_wired_in_compose_and_documented(compose):
    nginx = compose["services"]["nginx"]
    assert nginx["environment"]["MARCUS_REAL_IP_FROM"] == "${MARCUS_REAL_IP_FROM:-}"
    conf = (ROOT / "docker" / "nginx.conf").read_text()
    assert re.search(r"^\s{4}include /tmp/nginx/real_ip\.conf;", conf, re.M)
    readme = (ROOT / "README.md").read_text()
    assert "MARCUS_REAL_IP_FROM" in readme


# --- request body sizes: only the two upload routes take 21 MB (re-review N2) ------------------


@pytest.fixture(scope="module")
def nginx_url():
    """The production nginx (config and entrypoint script) on a loopback port, no API behind
    it: a request nginx lets through ends as 502, one it refuses for its size as 413.

    It runs on Docker's default bridge, which has a route out but no embedded DNS (no
    127.0.0.11): the relay's upstream name never resolves, so the relay tests below reach no
    COCONUT. Never move it to a user-defined network (those have Docker's DNS): the relay would
    then send their logins to the real COCONUT."""
    docker = _docker_or_skip()
    name = f"marcus-bodysize-test-{os.getpid()}"
    args = [
        docker, "run", "-d", "--name", name, "--read-only", "--tmpfs", "/tmp",
        "-p", "127.0.0.1::8080", "--add-host", "api:127.0.0.1",
        *_NGINX_MOUNTS,
        NGINX_IMAGE,
    ]  # fmt: skip
    started = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert started.returncode == 0, started.stderr
    try:
        port = (
            subprocess.run(
                [docker, "port", name, "8080/tcp"], capture_output=True, text=True, timeout=30
            )
            .stdout.strip()
            .rsplit(":", 1)[1]
        )
        url = f"http://127.0.0.1:{port}"
        httpx = pytest.importorskip("httpx")
        for _ in range(50):
            try:
                httpx.get(f"{url}/x", timeout=1)
                break
            except httpx.HTTPError:
                subprocess.run(["sleep", "0.1"])
        yield url
    finally:
        subprocess.run([docker, "rm", "-f", name], capture_output=True, timeout=60)


def _send(url: str, method: str, path: str, size: int) -> int | str:
    import httpx

    body = b"%PDF-1.4\n" + b"0" * (size - 9)
    headers = {"Content-Type": "application/pdf"}
    try:
        return httpx.request(
            method, url + path, content=body, headers=headers, timeout=30
        ).status_code
    except httpx.HTTPError as exc:
        return f"no answer: {type(exc).__name__}"


MB2 = 2 * 1024 * 1024


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v2/papers/"),  # trailing slash: not the upload route
        ("POST", "/api/v2/images/"),
        ("PUT", "/api/v2/segments/00000000-0000-0000-0000-000000000000/curation"),
        ("POST", "/api/v2/tools/mcs"),
    ],
)
def test_big_bodies_only_on_the_upload_routes(nginx_url, method, path):
    assert _send(nginx_url, method, path, MB2) == 413


@pytest.mark.parametrize("path", ["/api/v2/papers", "/api/v2/images"])
def test_uploads_still_take_20_mb(nginx_url, path):
    assert _send(nginx_url, "POST", path, 20 * 1024 * 1024) == 502  # through to the (absent) API
    assert _send(nginx_url, "POST", path, 22 * 1024 * 1024) == 413


def test_upload_locations_are_exact(compose):
    conf = (ROOT / "docker" / "nginx.conf").read_text()
    assert re.search(r"location = /api/v2/papers \{[^}]*client_max_body_size 21m;", conf)
    assert re.search(r"location = /api/v2/images \{[^}]*client_max_body_size 21m;", conf)
    assert re.search(r"location /api/v2/ \{[^}]*client_max_body_size 1m;", conf)


# --- paper annotation: llama-server + worker-llm (GPU), the fake annotator (fake stack) --------

LLAMA_COMMIT = "7fce5439fe451cd48340b112ec37d2befe02c776"  # the GGUF's converter commit (b12554)
LLAMA_DOCKERFILE = ROOT / "docker" / "Dockerfile.llama"


def _arg(command: list[str], flag: str) -> str:
    return command[command.index(flag) + 1]


MULTI_MODEL = "nuextract3-marcus-multi-v1"  # the one model of both jobs (owner, 2026-11-22)
MULTI_VERSION = "Q8_0 llama.cpp b12554"


def test_llama_server_is_internal_read_only_and_mounts_model_and_projector_read_only():
    """The one model server: the multi-task model and its vision projector, both bound read-only
    from the host (never a new directory), the model README's serving flags with two slots."""
    services = _compose_config("docker-compose.yml", GPU)["services"]
    llama = services["llama-server"]
    assert not llama.get("ports")
    assert llama["read_only"] is True and llama["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in llama["security_opt"]
    assert llama["tmpfs"] == ["/tmp"]
    vols = {v["target"]: v for v in llama["volumes"]}
    assert set(vols) == {"/models/marcus.gguf", "/models/mmproj.gguf"}
    for vol in vols.values():
        assert vol["type"] == "bind" and vol["read_only"] is True
        assert vol["bind"]["create_host_path"] is False  # a wrong path fails, never a new dir
    assert vols["/models/marcus.gguf"]["source"].endswith(f"{MULTI_MODEL}-Q8_0.gguf")
    assert vols["/models/mmproj.gguf"]["source"].endswith(f"{MULTI_MODEL}-mmproj-f16.gguf")
    assert llama["user"] == "10001:10001"
    cmd = llama["command"]
    assert _arg(cmd, "--model") == "/models/marcus.gguf"
    assert _arg(cmd, "--mmproj") == "/models/mmproj.gguf"
    assert _arg(cmd, "--alias") == MULTI_MODEL
    # two slots of 10240 tokens: one for worker-llm, one for worker-rgroup
    assert _arg(cmd, "--parallel") == "2" and _arg(cmd, "--ctx-size") == "20480"
    assert _arg(cmd, "--reasoning") == "off" and "--jinja" in cmd and "--no-webui" in cmd
    assert _arg(cmd, "--n-gpu-layers") == "999"
    assert llama["healthcheck"]["test"] == ["CMD", "curl", "-fsS", "http://127.0.0.1:8080/health"]
    assert llama["build"]["dockerfile"] == "docker/Dockerfile.llama"
    assert llama["build"]["args"] == {"VARIANT": "cuda", "CUDA_ARCH": "70"}
    assert llama["image"] == "marcus-v2-llama:cuda-b12554"
    assert int(llama["mem_limit"]) >= 8 * 2**30  # the model files are mapped into memory
    base = yaml.safe_load(COMPOSE.read_text())["services"]
    assert "llama-server" not in base and "worker-llm" not in base


def test_one_model_server_for_both_jobs():
    """Owner decision 2026-11-22: one model on one llama-server for annotation and R-group rows.
    No second model server; each slot of the server belongs to one queue's single process."""
    from marcus.core.queues import SLOTS

    services = _compose_config("docker-compose.yml", GPU)["services"]
    assert "llama-rgroup" not in services
    servers = {name for name, svc in services.items()
               if svc.get("image", "").startswith("marcus-v2-llama:")}  # fmt: skip
    assert servers == {"llama-server"}
    cmd = services["llama-server"]["command"]
    llm, rg = services["worker-llm"], services["worker-rgroup"]
    slots = int(_arg(cmd, "--parallel"))
    assert slots == SLOTS["q.llm"] + SLOTS["q.rgroup"]
    assert int(_arg(llm["command"], "-c")) + int(_arg(rg["command"], "-c")) == slots
    # each slot keeps the context both jobs were trained and scored with
    assert int(_arg(cmd, "--ctx-size")) // slots == 10240
    # stored results name the model that made them: the server's model, for both jobs
    assert llm["environment"]["MARCUS_ANNOTATE_MODEL"] == MULTI_MODEL == _arg(cmd, "--alias")
    assert rg["environment"]["MARCUS_RGROUP_MODEL"] == MULTI_MODEL
    assert llm["environment"]["MARCUS_ANNOTATE_MODEL_VERSION"] == MULTI_VERSION
    assert rg["environment"]["MARCUS_RGROUP_MODEL_VERSION"] == MULTI_VERSION


def test_model_settings_defaults_are_the_compose_defaults():
    """An image run outside compose stores the same model name and version as the GPU stack."""
    from marcus.core.settings import Settings

    services = _compose_config("docker-compose.yml", GPU)["services"]
    llm = services["worker-llm"]["environment"]
    rg = services["worker-rgroup"]["environment"]
    s = Settings()
    assert (s.annotate_model, s.annotate_model_version) == (
        llm["MARCUS_ANNOTATE_MODEL"],
        llm["MARCUS_ANNOTATE_MODEL_VERSION"],
    )
    assert (s.rgroup_model, s.rgroup_model_version) == (
        rg["MARCUS_RGROUP_MODEL"],
        rg["MARCUS_RGROUP_MODEL_VERSION"],
    )
    assert s.annotator_url == llm["MARCUS_ANNOTATOR_URL"]
    assert s.rgroup_url == rg["MARCUS_RGROUP_URL"]


def test_llama_server_shares_its_own_internal_network_only_with_the_two_model_workers():
    """A-M8: no other container (not even one on `internal`) can reach llama-server: its own
    internal network `llm` has only the server, worker-llm and worker-rgroup."""
    config = _compose_config("docker-compose.yml", GPU)
    services = config["services"]
    assert config["networks"]["llm"]["internal"] is True
    assert "rgroup" not in config["networks"]
    members = {name for name, svc in services.items() if "llm" in svc.get("networks", {})}
    assert members == {"llama-server", "worker-llm", "worker-rgroup"}
    assert set(services["llama-server"]["networks"]) == {"llm"}
    for worker in ("worker-llm", "worker-rgroup"):
        assert set(services[worker]["networks"]) == {"internal", "llm"}, worker


def test_llama_image_is_built_at_the_pinned_commit_for_the_v100():
    text = LLAMA_DOCKERFILE.read_text()
    assert f"ARG LLAMA_COMMIT={LLAMA_COMMIT}" in text
    assert 'test "$(git rev-parse HEAD)" = "${LLAMA_COMMIT}"' in text
    assert "ARG CUDA_ARCH=70" in text and "-DCMAKE_CUDA_ARCHITECTURES=${CUDA_ARCH}" in text
    assert "ARG CUDA_VERSION=12." in text  # CUDA 13 has no Volta (sm_70) support
    assert "-DLLAMA_USE_PREBUILT_UI=OFF" in text  # nothing downloaded but the pinned source
    assert ".gguf" not in text.replace("/models/marcus.gguf", "")  # no model in the image


def test_worker_llm_serves_q_llm_with_one_process_and_reads_data_only():
    services = _compose_config("docker-compose.yml", GPU)["services"]
    worker = services["worker-llm"]
    cmd = worker["command"]
    assert _arg(cmd, "-Q") == "q.llm" and _arg(cmd, "-c") == "1"
    assert _arg(cmd, "--include") == "marcus.workers.annotate"
    assert set(worker["networks"]) == {"internal", "llm"} and worker["read_only"] is True
    (vol,) = worker["volumes"]
    assert vol["target"] == "/data" and vol["read_only"] is True
    assert set(worker["depends_on"]) >= {"llama-server"}
    assert worker["depends_on"]["llama-server"]["condition"] == "service_healthy"
    env = worker["environment"]
    assert env["MARCUS_ANNOTATOR"] == "llama"
    assert env["MARCUS_ANNOTATOR_URL"] == "http://llama-server:8080"
    assert env["MARCUS_ANNOTATE_MODEL"] == MULTI_MODEL
    assert not any(key.startswith("MARCUS_RGROUP_") for key in env)
    assert "MARCUS_ENABLE_FAKE_ENGINES" not in env
    from marcus.core.queues import SLOTS

    assert SLOTS["q.llm"] == 1


def test_worker_rgroup_serves_q_rgroup_with_one_process_and_reads_data_only():
    """R-group rows have their own queue and worker: an annotation run never holds back an
    R-group reading, and the other way round (one llama-server with a slot for each)."""
    services = _compose_config("docker-compose.yml", GPU)["services"]
    worker = services["worker-rgroup"]
    cmd = worker["command"]
    assert _arg(cmd, "-Q") == "q.rgroup" and _arg(cmd, "-c") == "1"
    assert _arg(cmd, "--include") == "marcus.workers.rgroups"
    assert set(worker["networks"]) == {"internal", "llm"} and worker["read_only"] is True
    assert worker["image"] == services["worker-llm"]["image"]
    (vol,) = worker["volumes"]
    assert vol["target"] == "/data" and vol["read_only"] is True
    assert worker["depends_on"]["llama-server"]["condition"] == "service_healthy"
    env = worker["environment"]
    assert env["MARCUS_RGROUP_READER"] == "llama"
    assert env["MARCUS_RGROUP_URL"] == "http://llama-server:8080"
    assert env["MARCUS_RGROUP_MODEL"] == MULTI_MODEL
    assert env["MARCUS_RGROUP_MODEL_VERSION"] == MULTI_VERSION
    assert not any(key.startswith("MARCUS_ANNOTAT") for key in env)
    assert "MARCUS_ENABLE_FAKE_ENGINES" not in env
    from marcus.core.queues import SLOTS

    assert SLOTS["q.rgroup"] == 1
    base = yaml.safe_load(COMPOSE.read_text())["services"]
    assert "worker-rgroup" not in base


def test_annotation_is_offered_only_where_q_llm_is_served():
    base = _compose_config("docker-compose.yml")["services"]["api"]["environment"]
    assert base.get("MARCUS_ANNOTATE_ENABLED", "0") in ("0", "false", "")
    assert base.get("MARCUS_RGROUP_ENABLED", "0") in ("0", "false", "")
    assert not {"q.llm", "q.rgroup"} & set(base["MARCUS_EXPECTED_QUEUES"].split(","))
    for files, workers in (
        ((GPU,), ("worker-llm", "worker-rgroup")),
        (("docker-compose.fake.yml",), ("worker-fake-annotate", "worker-fake-rgroup")),
    ):
        services = _compose_config("docker-compose.yml", *files)["services"]
        api = services["api"]["environment"]
        assert api["MARCUS_ANNOTATE_ENABLED"] == "1", files
        assert api["MARCUS_RGROUP_ENABLED"] == "1", files
        expected = api["MARCUS_EXPECTED_QUEUES"].split(",")
        assert "q.llm" in expected and "q.rgroup" in expected, files
        for worker in workers:
            assert worker in services, files


def test_fake_stack_runs_the_fake_annotator_and_the_fake_rgroup_reader():
    services = _compose_config("docker-compose.yml", "docker-compose.fake.yml")["services"]
    worker = services["worker-fake-annotate"]
    cmd = worker["command"]
    assert _arg(cmd, "-Q") == "q.llm" and _arg(cmd, "-c") == "1"
    assert _arg(cmd, "--include") == "marcus.workers.annotate"
    env = worker["environment"]
    assert env["MARCUS_ANNOTATOR"] == "fake" and env["MARCUS_ENABLE_FAKE_ENGINES"] == "1"
    (vol,) = worker["volumes"]
    assert vol["read_only"] is True
    worker = services["worker-fake-rgroup"]
    cmd = worker["command"]
    assert _arg(cmd, "-Q") == "q.rgroup" and _arg(cmd, "-c") == "1"
    assert _arg(cmd, "--include") == "marcus.workers.rgroups"
    env = worker["environment"]
    assert env["MARCUS_RGROUP_READER"] == "fake" and env["MARCUS_ENABLE_FAKE_ENGINES"] == "1"
    (vol,) = worker["volumes"]
    assert vol["read_only"] is True
    assert "llama-server" not in services and "llama-rgroup" not in services


# --- the COCONUT relay (owner decision 2026-11-20) ---------------------------------------------
# COCONUT sends no CORS headers, so the browser cannot call it: nginx (already on `egress`)
# relays exactly three fixed calls to the fixed host. The API stays without internet.

NGINX_CONF = ROOT / "docker" / "nginx.conf"
RELAY_JS = ROOT / "docker" / "coconut-relay.js"
COCONUT_HOST = "coconut.naturalproducts.net"
RELAY = {
    "/api/v2/coconut/auth/login": "/api/auth/login",
    "/api/v2/coconut/reports/mutate": "/api/reports/mutate",
    "/api/v2/coconut/search": "/api/search",
}
FAKE_COCONUT_DIR = ROOT / "tests" / "fake_coconut"


def _relay_blocks() -> tuple[str, dict[str, str]]:
    """(the prefix block's own body, {exact path: its body}) of the relay locations."""
    blocks = _location_blocks(NGINX_CONF.read_text())
    prefix = [b for h, b in blocks if h == "location ^~ /api/v2/coconut/"]
    assert len(prefix) == 1, [h for h, _ in blocks]
    exact = {h.split()[2]: b for h, b in blocks if h.startswith("location = /api/v2/coconut/")}
    return prefix[0], exact


def _full_block(conf: str, head: str) -> str:
    """The whole text of the block `head {...}`, nested blocks (the `if`s) included."""
    text = _strip_comments(conf)
    start = text.index(head + " {") + len(head) + 2
    depth = 1
    for i in range(start, len(text)):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            return text[start:i]
    raise AssertionError(f"unclosed {head}")


def _directive(body: str, name: str) -> list[str]:
    return [v.strip() for v in re.findall(rf"^\s*{name}\s+([^;]+);", body, re.M)]


def test_coconut_relay_has_exactly_three_fixed_routes():
    prefix, exact = _relay_blocks()
    assert set(exact) == set(RELAY)
    for path, body in exact.items():
        # the fixed upstream path, never built from the request
        assert _directive(body, "proxy_pass") == [f"https://coconut{RELAY[path]}"], path
        body = _full_block(NGINX_CONF.read_text(), f"location = {path}")
        # POST only; no query; a JSON body only (a cross-site form post cannot send one)
        assert re.search(r"if \(\$request_method != POST\)\s*\{\s*return 405;\s*\}", body), path
        assert re.search(r"if \(\$is_args\)\s*\{\s*return 400;\s*\}", body), path
        assert re.search(r'if \(\$content_type !~\* "[^"]*application/json[^"]*"\)\s*\{\s*'
                         r"return 415;\s*\}", body), path  # fmt: skip
    # anything else under the prefix: nginx's own 404 (never COCONUT, never the API)
    assert _directive(prefix, "return") == ["404"]
    conf = _strip_comments(NGINX_CONF.read_text())
    assert len(re.findall(r"^\s*proxy_pass\s+https://", conf, re.M)) == 3
    assert "$" not in "".join(re.findall(r"proxy_pass\s+https://([^;]+);", conf))


def test_coconut_upstream_is_the_fixed_host_with_tls_verification():
    conf = _strip_comments(NGINX_CONF.read_text())
    upstream = re.search(r"upstream coconut \{([^}]*)\}", conf)
    assert upstream, "upstream coconut missing"
    # resolve: nginx starts (and the rest of MARCUS works) while COCONUT's name does not resolve
    assert _directive(upstream.group(1), "server") == [f"{COCONUT_HOST}:443 resolve"]
    prefix, _ = _relay_blocks()
    assert _directive(prefix, "proxy_ssl_verify") == ["on"]
    assert _directive(prefix, "proxy_ssl_server_name") == ["on"]
    assert _directive(prefix, "proxy_ssl_name") == [COCONUT_HOST]
    assert _directive(prefix, "proxy_ssl_trusted_certificate") == [
        "/etc/ssl/certs/ca-certificates.crt"
    ]
    assert int(_directive(prefix, "proxy_ssl_verify_depth")[0]) >= 2


def test_coconut_relay_sends_only_its_own_headers():
    """No cookie, no client address, no Referer or Origin goes upstream: only the headers set
    here. Authorization only on the mutate call (the one that needs the token)."""
    prefix, exact = _relay_blocks()
    assert _directive(prefix, "proxy_pass_request_headers") == ["off"]
    sent = {
        v.split()[0].lower(): v.split(None, 1)[1] for v in _directive(prefix, "proxy_set_header")
    }
    assert set(sent) == {"host", "content-type", "accept", "authorization", "user-agent"}
    assert sent["host"] == COCONUT_HOST
    assert sent["content-type"] == "$content_type"
    assert sent["authorization"] == "$coconut_authorization"
    for body in exact.values():  # a proxy_set_header here would drop the whole set above
        assert not _directive(body, "proxy_set_header")
    conf = _strip_comments(NGINX_CONF.read_text())
    amap = re.search(r"map \$uri \$coconut_authorization \{([^}]*)\}", conf)
    assert amap, "map $uri $coconut_authorization missing"
    rows = dict(r.split() for r in _directive(amap.group(1), ""))
    assert rows == {"default": '""', "/api/v2/coconut/reports/mutate": "$http_authorization"}


def test_coconut_relay_returns_only_status_body_and_content_type():
    """The njs header filter keeps Content-Type and Content-Length of COCONUT's answer and drops
    every other upstream header (cookies, CORS, redirects, caching); nginx adds its own fixed
    security headers. The judge checks it against the fake upstream."""
    conf = _strip_comments(NGINX_CONF.read_text())
    assert re.search(r"^load_module modules/ngx_http_js_module\.so;", conf, re.M)
    assert "js_import coconut from /etc/nginx/marcus/coconut-relay.js;" in conf
    prefix, _ = _relay_blocks()
    assert _directive(prefix, "js_header_filter") == ["coconut.onlyStatusAndBody"]
    for name in ("Set-Cookie", "Content-Security-Policy", "Access-Control-Allow-Origin"):
        assert name in _directive(prefix, "proxy_hide_header"), name
    added = {v.split()[0].lower() for v in _directive(prefix, "add_header")}
    assert UI_HEADERS - {"permissions-policy"} <= added
    assert "cache-control" in added
    js = RELAY_JS.read_text()
    keep = re.search(r"const KEEP = \[([^\]]*)\]", js)
    assert keep, js
    assert set(re.findall(r'"([^"]+)"', keep.group(1))) == {
        "content-type",
        "content-length",
        "cache-control",
        *(UI_HEADERS - {"permissions-policy"}),
    }


def test_coconut_relay_limits():
    """Every call is limited per client (an IPv6 client by its /64), then in total: COCONUT sees
    every MARCUS user as one address. Login is strict (credential stuffing); login and search
    together stay under 60/min in total. Bodies sized to what the client sends; the client's
    own timeouts."""
    conf = _strip_comments(NGINX_CONF.read_text())
    zones = {
        z: (key, int(rate))
        for key, z, rate in re.findall(
            r"^\s*limit_req_zone\s+(\$\w+)\s+zone=(\w+):\w+\s+rate=(\d+)r/m;", conf, re.M
        )
    }
    assert "js_set $coconut_client coconut.clientKey;" in conf
    assert re.search(r"map \$request_method \$coconut_all \{\s*default all;\s*\}", conf)
    for call in ("login", "search", "mutate"):
        assert zones[f"coconut_{call}"][0] == "$coconut_client", call
        assert zones[f"coconut_{call}_all"][0] == "$coconut_all", call
    assert zones["coconut_login"][1] <= 5
    assert zones["coconut_login_all"][1] + zones["coconut_search_all"][1] <= 50
    _, exact = _relay_blocks()
    login, mutate, search = (exact[p] for p in RELAY)
    # per client first: a request refused for its client does not use up the total
    assert _directive(login, "limit_req") == [
        "zone=coconut_login burst=3 nodelay",
        "zone=coconut_login_all burst=10 nodelay",
    ]
    assert _directive(search, "limit_req") == [
        "zone=coconut_search burst=10 nodelay",
        "zone=coconut_search_all burst=10 nodelay",
    ]
    assert _directive(mutate, "limit_req") == [
        "zone=coconut_mutate burst=20 nodelay",
        "zone=coconut_mutate_all burst=40 nodelay",
    ]
    assert re.search(r"^\s*limit_req_status\s+429;", conf, re.M)
    assert _directive(login, "client_max_body_size") == ["8k"]
    assert _directive(search, "client_max_body_size") == ["8k"]
    assert _directive(mutate, "client_max_body_size") == ["2m"]  # 50 reports per chunk
    assert _directive(login, "proxy_read_timeout") == ["30s"]
    assert _directive(mutate, "proxy_read_timeout") == ["60s"]
    assert _directive(search, "proxy_read_timeout") == ["10s"]


def test_no_log_records_bodies_queries_or_credentials():
    """The password and the token pass through and are never logged: no log format has a body,
    a header with a secret, or a query; the relay logs the path without its query."""
    secret = re.compile(r"\$(request_body|http_authorization|http_cookie|args|query_string|"
                        r"request_uri|arg_\w+|sent_http_\w+|upstream_http_\w+)\b")  # fmt: skip
    confs = (NGINX_CONF, FRONTEND / "deploy" / "dev-nginx.conf", UI_LOCATIONS)
    for path in confs:
        text = _strip_comments(path.read_text())
        for fmt in re.findall(r"log_format\s+\w+\s+((?:'[^']*'\s*)+);", text):
            assert not secret.search(fmt), (path.name, fmt)
    conf = _strip_comments(NGINX_CONF.read_text())
    relay_fmt = re.search(r"log_format coconut\s+((?:'[^']*'\s*)+);", conf)
    assert relay_fmt and "$request " not in relay_fmt.group(1) + " "
    assert '"$request_method $uri $server_protocol"' in relay_fmt.group(1)
    prefix, _ = _relay_blocks()
    assert _directive(prefix, "access_log") == ["/dev/stdout coconut"]


def test_relay_js_is_mounted_into_nginx(compose):
    nginx = compose["services"]["nginx"]
    assert "./docker/coconut-relay.js:/etc/nginx/marcus/coconut-relay.js:ro" in nginx["volumes"]


def test_production_points_at_the_real_coconut_and_only_the_fake_stack_at_the_fake(compose):
    """Production (base, + GPU, + monitoring): nobody answers for COCONUT's name and nginx
    trusts the system CA bundle. The fake stack: a fake COCONUT holds the name on the internal
    network, and nginx trusts only the test CA, so even a lookup that reached the real host would
    fail verification before sending."""
    for files in (
        ("docker-compose.yml",),
        ("docker-compose.yml", "docker-compose.gpu.yml"),
        ("docker-compose.yml", "docker-compose.gpu.yml", "docker-compose.monitoring.yml"),
    ):
        services = _compose_config(*files)["services"]
        for name, svc in services.items():
            for net in (svc.get("networks") or {}).values():
                assert COCONUT_HOST not in ((net or {}).get("aliases") or []), (files, name)
        targets = [v["target"] for v in services["nginx"]["volumes"]]
        assert not any("ca-certificates" in t or t.startswith("/etc/ssl") for t in targets), files
        assert "fake-coconut" not in services, files
    services = _compose_config("docker-compose.yml", "docker-compose.fake.yml")["services"]
    fake = services["fake-coconut"]
    assert set(fake["networks"]) == {"internal"}
    assert fake["networks"]["internal"]["aliases"] == [COCONUT_HOST]
    assert "ports" not in fake
    mounts = {v["target"]: v for v in services["nginx"]["volumes"]}
    assert mounts["/etc/ssl/certs"]["type"] == "volume"
    assert mounts["/etc/ssl/certs"]["source"] == "fake-coconut-tls"
    assert mounts["/etc/ssl/certs"].get("read_only") is True
    fake_mounts = {v["target"]: v.get("source") for v in fake["volumes"]}
    assert fake_mounts["/data"] == "fake-coconut-tls"
    assert fake["environment"]["MARCUS_FAKE_TLS_DIR"] == "/data"
    assert services["nginx"]["depends_on"]["fake-coconut"]["condition"] == "service_healthy"


def test_fake_coconut_certificate_is_for_the_coconut_name_and_signed_by_the_test_ca(tmp_path):
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.skip("openssl not available")
    subprocess.run(["sh", str(FAKE_COCONUT_DIR / "gen-certs.sh"), str(tmp_path)], check=True)
    ca, cert = tmp_path / "ca.pem", tmp_path / "cert.pem"
    out = subprocess.run([openssl, "verify", "-CAfile", str(ca), str(cert)],
                         capture_output=True, text=True)  # fmt: skip
    assert out.returncode == 0, out.stdout + out.stderr
    text = subprocess.run([openssl, "x509", "-in", str(cert), "-noout", "-ext", "subjectAltName"],
                          capture_output=True, text=True).stdout  # fmt: skip
    assert f"DNS:{COCONUT_HOST}" in text
    assert (tmp_path / "ca-certificates.crt").read_bytes() == ca.read_bytes()
    # the CA's key was thrown away after signing: only the server's own test key is kept
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "ca-certificates.crt",
        "ca.pem",
        "cert.pem",
        "key.pem",
    ]


def test_no_tls_key_or_certificate_is_tracked_by_git():
    """The fake makes its TLS files at its first start (gen-certs.sh); a key in git is a leak
    alarm for secret scanners, even a test one."""
    git = shutil.which("git")
    if git is None or not (ROOT.parent / ".git").exists():
        pytest.skip("not a git checkout")
    out = subprocess.run([git, "-C", str(ROOT.parent), "ls-files", "*.pem", "*.key"],
                         capture_output=True, text=True)  # fmt: skip
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == []


def _relay(url: str, method: str, path: str, body: bytes = b"{}", ctype="application/json",
           **headers: str) -> int | str:  # fmt: skip
    import httpx

    hdrs = {"Content-Type": ctype, **headers} if ctype else dict(headers)
    try:
        return httpx.request(method, url + path, content=body, headers=hdrs, timeout=30).status_code
    except httpx.HTTPError as exc:
        return f"no answer: {type(exc).__name__}"


@pytest.mark.parametrize("path", list(RELAY))
@pytest.mark.parametrize("method", ["GET", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS"])
def test_relay_refuses_every_method_but_post(nginx_url, path, method):
    assert _relay(nginx_url, method, path) == 405


@pytest.mark.parametrize(
    "path",
    [
        "/api/v2/coconut/",
        "/api/v2/coconut/auth",
        "/api/v2/coconut/auth/logout",
        "/api/v2/coconut/auth/login/",
        "/api/v2/coconut/auth/login/x",
        "/api/v2/coconut/reports",
        "/api/v2/coconut/reports/1",
        "/api/v2/coconut/search/x",
        "/api/v2/coconut/users",
        "/api/v2/coconut/https://example.org/",
        "/api/v2/coconut//coconut.naturalproducts.net/api/auth/login",
    ],
)
def test_relay_refuses_every_other_path(nginx_url, path):
    assert _relay(nginx_url, "POST", path) == 404


@pytest.mark.parametrize("path", list(RELAY))
def test_relay_refuses_a_query_and_a_body_that_is_not_json(nginx_url, path):
    assert _relay(nginx_url, "POST", path + "?url=https://example.org/") == 400
    assert _relay(nginx_url, "POST", path, ctype="application/x-www-form-urlencoded") == 415
    assert _relay(nginx_url, "POST", path, ctype="text/plain") == 415
    assert _relay(nginx_url, "POST", path, ctype=None) == 415


def test_relay_body_limits(nginx_url):
    login, mutate, search = RELAY
    assert _relay(nginx_url, "POST", login, b"{" + b" " * 9 * 1024 + b"}") == 413
    assert _relay(nginx_url, "POST", search, b"{" + b" " * 9 * 1024 + b"}") == 413
    assert _relay(nginx_url, "POST", mutate, b"{" + b" " * 3 * 1024 * 1024 + b"}") == 413


def test_relay_without_an_upstream_is_a_502_and_login_is_rate_limited(nginx_url):
    """No COCONUT behind this nginx (no DNS): a relayed call is nginx's 502, which the client
    reads as "Could not reach COCONUT". The 5th login within the burst is 429 before it is
    relayed. Only this test sends valid logins to this nginx."""
    login, mutate, search = RELAY
    assert _relay(nginx_url, "POST", mutate, Authorization="Bearer x") == 502
    assert _relay(nginx_url, "POST", search) == 502
    answers = [_relay(nginx_url, "POST", login) for _ in range(6)]
    assert answers[:4] == [502] * 4, answers
    assert answers[4:] == [429, 429], answers


def _chunks(size: int):
    yield b"{"
    for _ in range(size // 1024):
        yield b" " * 1024
    yield b"}"


def test_relay_refuses_a_chunked_body_over_the_limit(nginx_url):
    """No Content-Length: the limit is met while the body is read (after the rate limits), still
    413. Search and mutate here (login has the same directive; its budget belongs to the test
    below)."""
    import httpx

    _, mutate, search = RELAY
    for path, size in ((search, 9 * 1024), (mutate, 3 * 1024 * 1024)):
        r = httpx.post(nginx_url + path, content=_chunks(size),
                       headers={"Content-Type": "application/json"}, timeout=30)  # fmt: skip
        assert r.request.headers.get("transfer-encoding") == "chunked"
        assert r.status_code == 413, (path, r.status_code)


_POSTS = r"""
while read -r path xff; do
  out=$(wget -q -O /dev/null --header "X-Forwarded-For: $xff" \
        --header "Content-Type: application/json" --post-data '{}' \
        "http://127.0.0.1:8080$path" 2>&1)
  code=$(echo "$out" | sed -n 's/.*HTTP\/1\.1 \([0-9][0-9][0-9]\).*/\1/p' | head -n 1)
  echo "${code:-200}"
done
"""


def _relay_from(posts: list[tuple[str, str]]) -> list[int]:
    """A fresh production nginx (no network at all: the relay reaches nothing, an allowed call
    is 502) with the real_ip switch on for 127.0.0.1; each (path, client address) is POSTed from
    inside the container with that address in X-Forwarded-For. Returns the statuses."""
    docker = _docker_or_skip()
    name = f"marcus-relaylimit-test-{os.getpid()}-{abs(hash(tuple(posts)))}"
    args = [docker, "run", "-d", "--name", name, "--network", "none", "--read-only",
            "--tmpfs", "/tmp", "--add-host", "api:127.0.0.1", *_NGINX_MOUNTS,
            "-e", "MARCUS_REAL_IP_FROM=127.0.0.1", NGINX_IMAGE]  # fmt: skip
    started = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert started.returncode == 0, started.stderr
    try:
        for _ in range(50):
            ready = subprocess.run(
                [docker, "exec", name, "sh", "-c", "test -f /tmp/nginx.pid"], capture_output=True
            )
            if ready.returncode == 0:
                break
            subprocess.run(["sleep", "0.1"])
        lines = "".join(f"{path} {xff}\n" for path, xff in posts)
        out = subprocess.run([docker, "exec", "-i", name, "sh", "-c", _POSTS], input=lines,
                             capture_output=True, text=True, timeout=120)  # fmt: skip
        assert out.returncode == 0, out.stderr
        return [int(x) for x in out.stdout.split()]
    finally:
        subprocess.run([docker, "rm", "-f", name], capture_output=True, timeout=60)


def test_relay_counts_an_ipv6_client_by_its_64():
    login = "/api/v2/coconut/auth/login"
    posts = [(login, "2001:db8:1:2::a")] * 4 + [
        (login, "2001:db8:1:2:ffff:ffff:ffff:ffff"),  # same /64: limited
        (login, "2001:db8:1:2:0:1::"),  # same /64, another spelling
        (login, "2001:db8:1:3::a"),  # the next /64: its own budget
        (login, "203.0.113.5"),
        (login, "203.0.113.6"),  # IPv4: per address
    ]
    assert _relay_from(posts) == [502, 502, 502, 502, 429, 429, 502, 502, 502]


@pytest.mark.parametrize(
    ("path", "burst"),
    [
        ("/api/v2/coconut/auth/login", 10),
        ("/api/v2/coconut/search", 10),
        ("/api/v2/coconut/reports/mutate", 40),
    ],  # fmt: skip
)
def test_relay_caps_every_call_in_total(path, burst):
    """Many clients, one call each: past the total's burst (plus what its rate refills while
    the burst runs) the relay answers 429, so no number of clients can push MARCUS over
    COCONUT's limits."""
    n = burst + 15
    answers = _relay_from([(path, f"198.51.{i // 250}.{i % 250 + 1}") for i in range(n)])
    assert answers[: burst + 1] == [502] * (burst + 1), answers
    assert set(answers) == {502, 429}, answers
    assert answers.count(429) >= 5, answers
