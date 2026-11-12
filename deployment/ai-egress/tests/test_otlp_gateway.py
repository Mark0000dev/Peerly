"""No Docker/provider required: closed public config and opt-in packaging."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = {
    "AI_DATABASE_FORWARD_IP": "172.24.0.10",
    "AI_OTLP_BIND_IP": "172.25.0.2",
    "AI_OTLP_COLLECTOR_IP": "172.26.0.2",
}


def check(values: dict[str, str], *arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(  # noqa: S603 - fixed owned shell script, synthetic public input only.
        ("/bin/sh", str(ROOT / "otlp-entrypoint.sh"), *arguments),
        env=values,
        capture_output=True,
        timeout=2,
        check=False,
    )


def test_explicit_public_config_valid_no_provider_settings() -> None:
    result = check(PUBLIC, "--check")
    assert result.returncode == 0
    assert result.stdout == b"OTLP public configuration valid\n"
    assert result.stderr == b""


@pytest.mark.parametrize(
    "invalid",
    [
        "",
        "0.0.0.0",  # noqa: S104 - rejected synthetic value, never a listener.
        "127.0.0.1",
        "1.1.1.1",
        "172.32.0.2",
        "172.16.0.256",
        "010.0.0.2",
        "192.168.1",
        "192.168.1.1:4318",
        "http://172.26.0.2",
        "172.26.0.2\n",
        "*",
        "$(id)",
    ],
)
def test_public_destination_not_url_port_wildcard_or_code(invalid: str) -> None:
    result = check(PUBLIC | {"AI_OTLP_COLLECTOR_IP": invalid}, "--check")
    assert result.returncode != 0
    assert result.stdout == b""
    assert result.stderr == b"OTLP public configuration rejected\n"


def test_no_defaults_or_arbitrary_runtime_arguments() -> None:
    for missing in PUBLIC:
        values = {key: value for key, value in PUBLIC.items() if key != missing}
        assert check(values, "--check").returncode != 0
    assert check(PUBLIC, "--check", "--check").returncode != 0
    assert check(PUBLIC, "--unknown").returncode != 0
    assert (
        check(PUBLIC | {"AI_OTLP_BIND_IP": PUBLIC["AI_OTLP_COLLECTOR_IP"]}, "--check").returncode
        != 0
    )


def test_existing_gateway_default_has_no_otlp_listener_or_environment_inheritance() -> None:
    base = (ROOT / "haproxy.cfg").read_text()
    assert "4318" not in base
    compose = (ROOT / "compose.yml").read_text()
    assert "otlp" not in compose
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert dockerfile.split("CMD ", 1)[1].strip() == (
        '["haproxy", "-W", "-db", "-f", "/usr/local/etc/haproxy/haproxy.cfg"]'
    )
    wrapper = (ROOT / "otlp-entrypoint.sh").read_text()
    assert "exec /usr/bin/env -i" in wrapper
    assert "HTTP_PROXY" not in wrapper
    assert "OTEL_EXPORTER" not in wrapper
