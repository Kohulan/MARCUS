"""Static checks on docker-compose.yml (no Docker needed)."""

import ipaddress
import json
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.yml"
FAKE = ROOT / "docker-compose.fake.yml"


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text())


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
    (job,) = cfg["scrape_configs"]
    assert job["static_configs"][0]["targets"] == ["metrics:9100"]


def test_dashboard_covers_the_required_panels():
    dash = json.loads((ROOT / "ops" / "grafana" / "marcus.json").read_text())
    exprs = " ".join(t["expr"] for p in dash["panels"] for t in p["targets"])
    for needle in (
        "marcus_queue_pending", "marcus_queue_running", "marcus_wait_seconds_bucket",
        "marcus_step_seconds_bucket", "marcus_first_smiles_seconds_bucket",
        "marcus_step_failures_total", "marcus_disk_free_bytes",
        "marcus_dispatcher_heartbeat_age_seconds",
    ):  # fmt: skip
        assert needle in exprs, needle
