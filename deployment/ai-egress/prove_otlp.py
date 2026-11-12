"""One local isolated synthetic OTLP proof. No auth/provider/core DB or host ports."""

import argparse
import hashlib
import ipaddress
import json
import os
import re
import stat
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

BASE = Path(__file__).resolve().parent
LIMIT = 131072
COMMON = (
    "--read-only",
    "--cap-drop=ALL",
    "--security-opt=no-new-privileges",
    "--pids-limit=32",
    "--memory=64m",
    "--cpus=0.25",
    "--log-driver=local",
    "--log-opt=max-size=1m",
    "--log-opt=max-file=2",
)

PYTHON_COMMON = tuple("128m" if value == "64m" else value for value in COMMON)


def require(value: bool, code: str) -> None:
    if not value:
        raise RuntimeError(code)


def immutable(value: str) -> str:
    require(
        re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None, "immutable_local_image_required"
    )
    return value


def string_list(encoded: str) -> list[str]:
    value: object = json.loads(encoded)
    require(isinstance(value, list), "invalid_checks")
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise RuntimeError("invalid_checks")
    return [item for item in value if isinstance(item, str)]


@dataclass(slots=True)
class Proof:
    gateway_image: str
    python_image: str
    folder: Path
    socket: Path = Path("/var/run/docker.sock")
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    checks: list[str] = field(default_factory=list)
    failure_latency: float | None = None
    transcript: Path | None = None

    def __post_init__(self) -> None:
        allowed = {Path("/var/run/docker.sock"), Path.home() / ".docker/desktop/docker.sock"}
        require(self.socket in allowed, "only_explicit_local_engine_socket")
        info = self.socket.lstat()
        require(
            stat.S_ISSOCK(info.st_mode) and info.st_uid in {0, os.getuid()},
            "untrusted_local_engine_socket",
        )

    def command(self, *args: str) -> str:
        docker = next(
            (path for path in ("/usr/local/bin/docker", "/usr/bin/docker") if Path(path).is_file()),
            None,
        )
        if docker is None:
            raise RuntimeError("docker_unavailable")
        config = self.folder / "empty-docker-config"
        config.mkdir(exist_ok=True)
        require(not any(config.iterdir()), "docker_config_not_empty")
        result = subprocess.run(  # noqa: S603 - fixed trusted local Docker binary and internally built argv.
            (docker, "--config", str(config), "--host", "unix://" + str(self.socket), *args),
            env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C.UTF-8"},
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        require(len(result.stdout) + len(result.stderr) <= LIMIT, "docker_output_bound")
        if self.transcript is not None:
            # Task-only synthetic diagnostic output; no production inputs or body logs.
            line = json.dumps(
                {
                    "operation": args[0],
                    "exit": result.returncode,
                    "stdout": result.stdout[-8192:],
                    "stderr": result.stderr[-8192:],
                }
            )
            with self.transcript.open("a") as output:
                output.write(line + "\n")
        if result.returncode:
            raise RuntimeError("owned_docker_command_failed")
        return result.stdout.strip()

    @property
    def label(self) -> str:
        return "dev.peerly.otlp-proof=" + self.run_id

    def network(self, suffix: str) -> str:
        return "peerly-otlp-" + self.run_id + "-" + suffix

    def ip(self, name: str, network: str) -> str:
        result = self.command(
            "inspect",
            "--format",
            '{{(index .NetworkSettings.Networks "' + network + '").IPAddress}}',
            name,
        )
        return str(ipaddress.IPv4Address(result))

    def fixture(self) -> tuple[str, str, str]:
        for suffix in ("private", "collector"):
            self.command(
                "network", "create", "--internal", "--label", self.label, self.network(suffix)
            )
        # Static --ip needs user-configured IPAM. Reclaim ONLY our just-created,
        # empty network's engine-selected subnet instead of guessing host CIDRs.
        private = self.network("private")
        subnet = self.command(
            "network", "inspect", "--format", "{{(index .IPAM.Config 0).Subnet}}", private
        )
        subnet = str(ipaddress.IPv4Network(subnet))
        self.command("network", "rm", private)
        self.command(
            "network", "create", "--internal", "--label", self.label, "--subnet", subnet, private
        )
        collector = self.network("sink")
        self.command(
            "run",
            "-d",
            "--pull=never",
            "--name",
            collector,
            "--label",
            self.label,
            "--network",
            self.network("collector"),
            *PYTHON_COMMON,
            "--mount",
            f"type=bind,src={BASE / 'otlp_fixture.py'},dst=/proof-fixture.py,readonly",
            self.python_image,
            "python",
            "/proof-fixture.py",
        )
        return collector, self.ip(collector, self.network("collector")), self.network("gateway")

    def create_gateway(self, name: str, collector_ip: str) -> str:
        self.command(
            "create",
            "--pull=never",
            "--name",
            name,
            "--label",
            self.label,
            "--network",
            self.network("private"),
            "--network-alias",
            "peerly-ai-otel",
            *COMMON,
            "--sysctl",
            "net.ipv4.ip_unprivileged_port_start=0",
            "-e",
            "AI_DATABASE_FORWARD_IP=" + collector_ip,
            self.gateway_image,
        )
        self.command("network", "connect", self.network("collector"), name)
        self.command("start", name)
        return self.ip(name, self.network("private"))

    def client(self, suffix: str, network: str, code: str) -> str:
        return self.command(
            "run",
            "--rm",
            "--pull=never",
            "--name",
            self.network(suffix),
            "--label",
            self.label,
            "--network",
            network,
            "--dns=127.0.0.1",
            *PYTHON_COMMON,
            self.python_image,
            "python",
            "-c",
            code,
        )

    def default_off(self, gateway: str) -> None:
        self.command("start", gateway)
        code = (
            "import socket; s=socket.socket();s.settimeout(2);"
            "result=s.connect_ex(('peerly-ai-otel',4318));s.close();"
            "raise SystemExit(0 if result else 1)"
        )
        self.client("default-client", self.network("private"), code)
        require(
            self.command("inspect", "--format", "{{.State.Running}}", gateway) == "true",
            "default_gateway_not_running",
        )
        self.checks.append("default_image_otlp_port_closed")
        self.command("rm", "-f", gateway)

    def opt_in(self, name: str, collector_ip: str) -> str:
        # Create before start so the exact private-interface address can be supplied.
        args = (
            "create",
            "--pull=never",
            "--name",
            name,
            "--label",
            self.label,
            "--network",
            self.network("private"),
            "--network-alias",
            "peerly-ai-otel",
            *COMMON,
            "--sysctl",
            "net.ipv4.ip_unprivileged_port_start=0",
        )
        # Parent supplies a fixed bind IP. In the fixture reserve it explicitly with
        # Docker's assigned stopped-container endpoint, then recreate at that same IP.
        bind_ip = self.create_gateway(name, collector_ip)
        self.command("rm", "-f", name)
        self.command(
            *args,
            "--ip",
            bind_ip,
            "-e",
            "AI_DATABASE_FORWARD_IP=" + collector_ip,
            "-e",
            "AI_OTLP_BIND_IP=" + bind_ip,
            "-e",
            "AI_OTLP_COLLECTOR_IP=" + collector_ip,
            "-e",
            "SYNTHETIC_FORBIDDEN=must-not-reach-haproxy",
            self.gateway_image,
            "/usr/local/bin/peerly-ai-otlp",
        )
        self.command("network", "connect", self.network("collector"), name)
        self.command("start", name)
        return self.ip(name, self.network("collector"))

    def actual_sdk(self, collector_ip: str) -> None:
        result = self.command(
            "run",
            "--rm",
            "--pull=never",
            "--name",
            self.network("sdk"),
            "--label",
            self.label,
            "--network",
            self.network("private"),
            "--dns=127.0.0.1",
            *PYTHON_COMMON,
            "-e",
            "SYNTHETIC_COLLECTOR_IP=" + collector_ip,
            "--mount",
            f"type=bind,src={BASE / 'otlp_client.py'},dst=/proof-client.py,readonly",
            self.python_image,
            "python",
            "/proof-client.py",
        )
        value: object = json.loads(result)
        if not isinstance(value, dict) or value.get("result") != "PASS":
            raise RuntimeError("sdk_proof_failed")
        self.checks.extend(string_list(json.dumps(value.get("checks"))))
        latency: object = value.get("queue_failure_seconds")
        if type(latency) not in {int, float} or not isinstance(latency, int | float):
            raise RuntimeError("invalid_latency_measurement")
        self.failure_latency = float(latency)

    def nonprivate_denial(self, public_ip: str) -> None:
        code = (
            "import socket; s=socket.socket();s.settimeout(2);"
            f"result=s.connect_ex(('{public_ip}',4318));s.close();"
            "raise SystemExit(0 if result else 1)"
        )
        self.client("other-interface", self.network("collector"), code)
        self.checks.append("collector_interface_listener_absent")

    def sanitized_environment(self, gateway: str) -> None:
        # Owned synthetic container ONLY; marker is never a real credential.
        code = "tr '\\000' '\\n' < /proc/1/environ | cut -d= -f1 | sort"
        names = self.command("exec", gateway, "/bin/sh", "-c", code).splitlines()
        require(
            set(names)
            == {"PATH", "AI_DATABASE_FORWARD_IP", "AI_OTLP_BIND_IP", "AI_OTLP_COLLECTOR_IP"},
            "gateway_environment_not_closed",
        )
        self.checks.append("gateway_inherited_environment_denied")

    def collector_counts(self, collector_ip: str) -> None:
        code = (
            "import http.client,json;"
            f"c=http.client.HTTPConnection('{collector_ip}',4318,timeout=2);"
            "c.request('GET','/fixture-counts');r=c.getresponse();v=json.loads(r.read(4096));"
            "c.close();expected={'traces':4,'metrics':1,'redirect':1,'slow':2};"
            "raise SystemExit(0 if v==expected else 1)"
        )
        self.client("sink-check", self.network("collector"), code)
        self.checks.append("only_expected_exports_reached_collector")

    def clean(self) -> None:
        containers = self.command("ps", "-aq", "--filter", "label=" + self.label).split()
        for container in containers:
            require(re.fullmatch(r"[0-9a-f]{12,64}", container) is not None, "invalid_owned_id")
            self.command("rm", "-f", container)
        networks = self.command("network", "ls", "-q", "--filter", "label=" + self.label).split()
        for network in networks:
            require(re.fullmatch(r"[0-9a-f]{12,64}", network) is not None, "invalid_owned_id")
            self.command("network", "rm", network)
        require(
            not self.command("ps", "-aq", "--filter", "label=" + self.label), "container_cleanup"
        )
        require(
            not self.command("network", "ls", "-q", "--filter", "label=" + self.label),
            "network_cleanup",
        )

    def run(self) -> dict[str, object]:
        self.command("image", "inspect", "--format", "{{.Id}}", self.gateway_image)
        self.command("image", "inspect", "--format", "{{.Id}}", self.python_image)
        try:
            _collector, collector_ip, gateway = self.fixture()
            self.create_gateway(gateway, collector_ip)
            self.default_off(gateway)
            other_ip = self.opt_in(gateway, collector_ip)
            self.sanitized_environment(gateway)
            self.actual_sdk(collector_ip)
            self.nonprivate_denial(other_ip)
            self.collector_counts(collector_ip)
        finally:
            self.clean()
        return {
            "result": "PASS",
            "gateway_image": self.gateway_image,
            "python_image": self.python_image,
            "checks": self.checks,
            "cleanup": "verified",
            "provider_calls": False,
            "queue_failure_seconds": self.failure_latency,
            "declared_gateway_limits": "64MiB,32PIDs,.25CPU,48globalconn,4OTLPconn/2backend/2queue",
            "declared_fixture_limits": "128MiB,32PIDs,.25CPU each",
            "model_tool_denial_proof": "pending_parent_actual_final40_namespace_proof",
            "files": {
                name: hashlib.sha256((BASE / name).read_bytes()).hexdigest()
                for name in ("haproxy.cfg", "otlp.cfg", "otlp-entrypoint.sh", "Dockerfile")
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-image", required=True)
    parser.add_argument("--python-image", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--docker-socket", type=Path, default=Path("/var/run/docker.sock"))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="peerly-otlp-proof-") as temporary:
        proof = Proof(
            immutable(args.gateway_image),
            immutable(args.python_image),
            Path(temporary),
            args.docker_socket,
            transcript=args.output.with_suffix(".commands.jsonl"),
        )
        result = proof.run()
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
