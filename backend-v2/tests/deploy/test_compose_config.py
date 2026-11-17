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
    }
    args = [docker, "compose", "--project-directory", str(ROOT), "--env-file", os.devnull]
    for name in files:
        args += ["-f", str(ROOT / name)]
    args += ["config", "--format", "json"]
    try:
        out = subprocess.run(args, env=env, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"docker compose not usable: {exc}")
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
    assert "--forwarded-allow-ips=127.0.0.1" in compose["services"]["api"]["command"]


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


def test_nginx_never_proxies_metrics():
    conf = (ROOT / "docker" / "nginx.conf").read_text()
    assert "metrics" not in conf and "9100" not in conf


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


def _gpu_reservation(svc: dict) -> list[dict]:
    return svc.get("deploy", {}).get("resources", {}).get("reservations", {}).get("devices", [])


def test_gpu_override_budget_under_20gb():
    config = _compose_config("docker-compose.yml", GPU)
    services = config["services"]
    env = {name: services[name]["environment"] for name in GPU_SERVICES}
    assert env["worker-segment"]["MARCUS_GPU_MEM_MB"] == "6144"
    assert env["worker-decimer"]["MARCUS_GPU_MEM_MB"] == "4096"
    assert env["worker-molnextr"]["MARCUS_TORCH_MEM_FRACTION"] == "0.09"
    assert env["worker-molscribe"]["MARCUS_TORCH_MEM_FRACTION"] == "0.09"
    budget = int(env["worker-segment"]["MARCUS_GPU_MEM_MB"])
    budget += int(env["worker-decimer"]["MARCUS_GPU_MEM_MB"])
    for name in ("worker-molnextr", "worker-molscribe"):
        budget += float(env[name]["MARCUS_TORCH_MEM_FRACTION"]) * GPU_TOTAL_MIB
    budget += CUDA_CONTEXT_MIB * len(GPU_SERVICES)
    assert budget <= BUDGET_LIMIT_MIB, budget

    published = {name for name, svc in services.items() if svc.get("ports")}
    assert published == {"nginx"}
    assert _non_internal_members(config) == EGRESS_SERVICES


def test_gpu_override_reserves_the_gpu_for_exactly_the_model_workers():
    services = _compose_config("docker-compose.yml", GPU)["services"]
    reserved = {name for name, svc in services.items() if _gpu_reservation(svc)}
    assert reserved == {*GPU_SERVICES, "dcgm-exporter"}
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


def test_nvidia_compute_default_unit_runs_before_docker():
    unit = (ROOT / "ops" / "systemd" / "nvidia-compute-default.service").read_text()
    lines = {line.split("=", 1)[0]: line.split("=", 1)[1] for line in unit.splitlines()
             if "=" in line and not line.startswith("#")}
    assert lines["ExecStart"] == "/usr/bin/nvidia-smi -i 0 -c DEFAULT"
    assert lines["Type"] == "oneshot"
    assert "docker.service" in lines["Before"].split()
    assert lines["WantedBy"] == "multi-user.target"


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
