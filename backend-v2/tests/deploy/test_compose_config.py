"""Static checks on docker-compose.yml (no Docker needed)."""

import ipaddress
import json
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yml"


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
