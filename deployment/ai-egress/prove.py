"""One credential-free isolated Docker proof; no public/provider requests or shared DB."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
import uuid
from pathlib import Path

IMAGE = (
    "haproxy@sha256:96ec3c75a9264ba94e733eeacb44051ed6e7b79bb77a73c2c36f236b6423f1f0"
)
DOMAINS = ("auth.openai.com", "chatgpt.com", "s3.cloud.ru")
SERVER = """
import socket,ssl,threading
ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain('/proof/cert.pem','/proof/key.pem')
def serve(port,tls):
 s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('0.0.0.0',port));s.listen(24)
 def reply(c):
  try:
   if tls:c=ctx.wrap_socket(c,server_side=True)
   data=c.recv(1024)
   if data:c.sendall(b'fixed-synthetic-upstream:'+data)
  except (OSError,ssl.SSLError):pass
  finally:c.close()
 while True:
  c,_=s.accept();threading.Thread(target=reply,args=(c,),daemon=True).start()
threading.Thread(target=serve,args=(5432,False),daemon=True).start();serve(9443,True)
"""
CLIENT = """
import socket,ssl,time,json
ctx=ssl.create_default_context(cafile='/proof/cert.pem');checks=[]
for domain in ('auth.openai.com','chatgpt.com','s3.cloud.ru'):
 deadline=time.monotonic()+12
 while True:
  try:
   with socket.create_connection((domain,443),timeout=2) as raw:
    with ctx.wrap_socket(raw,server_hostname=domain) as s:
     s.sendall(b'positive');assert s.recv(1024)==b'fixed-synthetic-upstream:positive'
   break
  except OSError:
   if time.monotonic()>deadline:raise
   time.sleep(.15)
 checks.append('verified_tls_passthrough:'+domain)
for sni in ('unknown.invalid','auth.openai.com.attacker.invalid',None):
 denied=False
 try:
  with socket.create_connection(('auth.openai.com',443),timeout=7) as raw:
   test=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);test.check_hostname=False;test.verify_mode=ssl.CERT_NONE
   with test.wrap_socket(raw,server_hostname=sni):pass
 except (OSError,ssl.SSLError):denied=True
 assert denied,repr(sni)
 checks.append('denied_sni:'+str(sni))
with socket.create_connection(('auth.openai.com',443),timeout=7) as s:
 s.sendall(b'CONNECT example.com:443 HTTP/1.1\\r\\n\\r\\n');assert not s.recv(1024)
checks.append('plaintext_CONNECT_denied')
with socket.create_connection(('peerly-ai-db',5432),timeout=2) as s:
 s.sendall(b'db-positive');assert s.recv(1024)==b'fixed-synthetic-upstream:db-positive'
checks.append('fixed_database_forward')
for host,port in [('auth.openai.com',80),('UPSTREAM_IP',9443),('1.1.1.1',443)]:
 try:s=socket.create_connection((host,port),timeout=1)
 except OSError:pass
 else:s.close();raise AssertionError('unexpected direct egress '+host)
checks.append('no_other_port_or_direct_network_egress')
try:socket.getaddrinfo('example.com',443)
except socket.gaierror:checks.append('external_dns_no_forwarder')
else:raise AssertionError('unexpected DNS answer')
print(json.dumps(checks))
"""


def run(*args: str, stdin: str | None = None) -> str:
    result = subprocess.run(
        args, input=stdin, text=True, capture_output=True, timeout=90, check=False
    )
    if result.returncode:
        raise RuntimeError(f"{args[0:3]} failed: {result.stdout} {result.stderr}")
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python-image",
        required=True,
        help="Already built immutable production backend image ID",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prefix = "peerly-egress-" + uuid.uuid4().hex[:10]
    private, public = prefix + "-private", prefix + "-public"
    containers: list[str] = []
    networks: list[str] = []
    source = Path(__file__).with_name("haproxy.cfg").read_text()
    with tempfile.TemporaryDirectory(
        prefix=".synthetic-" + prefix, dir=Path(__file__).resolve().parent
    ) as directory:
        folder = Path(directory)
        folder.chmod(0o755)
        run(
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-keyout",
            str(folder / "key.pem"),
            "-out",
            str(folder / "cert.pem"),
            "-subj",
            "/CN=synthetic-egress-proof",
            "-addext",
            "subjectAltName=" + ",".join("DNS:" + d for d in DOMAINS),
        )
        # Synthetic private key is fixture-only, never a real provider credential.
        (folder / "key.pem").chmod(0o644)
        (folder / "server.py").write_text(SERVER)
        try:
            for name, internal in [(private, True), (public, False)]:
                run(
                    "docker",
                    "network",
                    "create",
                    *(["--internal"] if internal else []),
                    name,
                )
                networks.append(name)
            upstream = prefix + "-upstream"
            containers.append(upstream)
            common = [
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--pids-limit",
                "32",
                "--memory",
                "64m",
                "--cpus",
                "0.25",
            ]
            run(
                "docker",
                "run",
                "-d",
                "--name",
                upstream,
                "--network",
                public,
                *common,
                "--mount",
                f"type=bind,src={folder},dst=/proof,readonly",
                args.python_image,
                "python",
                "/proof/server.py",
            )
            ip = run(
                "docker",
                "inspect",
                "--format",
                f'{{{{(index .NetworkSettings.Networks "{public}").IPAddress}}}}',
                upstream,
            )
            config = source
            for domain in DOMAINS:
                config = config.replace(
                    domain
                    + ":443 resolvers public_dns init-addr none resolve-prefer ipv4",
                    ip + ":9443",
                )
            # Only upstream target substitution; exact production frontend ACLs unchanged.
            (folder / "haproxy.cfg").write_text(config)
            gateway = prefix + "-gateway"
            containers.append(gateway)
            run(
                "docker",
                "create",
                "--name",
                gateway,
                "--network",
                private,
                *[
                    arg
                    for domain in (*DOMAINS, "peerly-ai-db")
                    for arg in ("--network-alias", domain)
                ],
                *common,
                "--sysctl",
                "net.ipv4.ip_unprivileged_port_start=0",
                "-e",
                "AI_DATABASE_FORWARD_IP=" + ip,
                "--mount",
                f"type=bind,src={folder}/haproxy.cfg,dst=/cfg,readonly",
                IMAGE,
                "haproxy",
                "-W",
                "-db",
                "-f",
                "/cfg",
            )
            run("docker", "network", "connect", public, gateway)
            run("docker", "start", gateway)
            client = prefix + "-client"
            containers.append(client)
            result = run(
                "docker",
                "run",
                "--rm",
                "-i",
                "--name",
                client,
                "--network",
                private,
                "--dns",
                "127.0.0.1",
                *common,
                "--mount",
                f"type=bind,src={folder}/cert.pem,dst=/proof/cert.pem,readonly",
                args.python_image,
                "python",
                "-",
                stdin=CLIENT.replace("UPSTREAM_IP", ip),
            )
            evidence = {
                "image": IMAGE,
                "python_image": args.python_image,
                "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                "checks": json.loads(result),
                "real_provider_requests": False,
                "tls_client_verified_synthetic_ca": True,
                "frontend_acl_unchanged": True,
            }
        finally:
            for name in reversed(containers):
                subprocess.run(
                    ["docker", "rm", "-f", name], capture_output=True, check=False
                )
            for name in reversed(networks):
                run("docker", "network", "rm", name)
        evidence["cleanup_verified"] = not run(
            "docker", "ps", "-aq", "--filter", "name=" + prefix
        )
        args.output.write_text(json.dumps(evidence, indent=2) + "\n")
        print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
