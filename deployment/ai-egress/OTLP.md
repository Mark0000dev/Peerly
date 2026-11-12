# Optional fixed AI SDK OTLP transport

Implementation is for a FUTURE reviewed gateway image/topology. Default gateway
CMD and haproxy.cfg are unchanged: no4318 listener, new network, alias or worker
observability setting is activated by building the image. Existing live32PID
worker/provider/security/credential policy is unchanged. Parent owns publication,
actual topology, controlled restart and final40PID containment/provider proof.

## Closed public contract agreed with Noether

Worker public origin: `OBSERVABILITY__COLLECTOR_ORIGIN=http://peerly-ai-otel:4318`.
This alias points only at the gateway on its existing private AI network; it is
NOT an alias for the actual collector and grants no worker app-network access.

Explicitly merging `otlp.override.yml` with `compose.yml` selects the separate
`peerly-ai-otlp` entrypoint and adds ONLY the gateway to the reviewed external
collector telemetry network `PEERLY_AI_TELEMETRY_NETWORK`. Worker is not present
in this overlay. Parent must arrange the collector's attachment and actual
network ownership separately, and check network membership before use.

The overlay requires two PUBLIC fixed RFC1918 IPv4 values:

- `AI_OTLP_BIND_IP`: actual gateway endpoint on the existing private AI network.
  It is not0.0.0.0, the gateway's public interface, or the collector network IP.
- `AI_OTLP_COLLECTOR_IP`: actual reviewed collector endpoint on the telemetry
  network, always port4318. No URL, DNS, alternative port or request-derived
  target is accepted. This is operator configuration, not client authority.

Existing `AI_DATABASE_FORWARD_IP` retains canonical fixed IPv4 semantics and its
5432 port; public/DB-only operator addresses are not changed by this feature.
The entrypoint rejects missing fields, malformed/leading-zero IPv4, wildcard,
URL, injected arguments and identical private bind/collector IPs, then execs
HAProxy with an explicit environment containing only PATH and those three public
IP values. No provider/auth/exporter credentials, proxy variables or generic
HAProxy argument/config overrides are inherited. `--check` validates only the
public IP shape and never starts HAProxy or grants application readiness.

IP-shape validation cannot establish network membership: parent must compare the
actual Docker endpoints. Wrong-interface bind is not accepted just because the
address is private. A collector IP change requires reviewed configuration and
transport/receipt/anchor reassessment; there is no DNS fallback or dynamic target.

## HTTP boundary

Only plaintext HTTP POST with exact origin-form URI `/v1/traces` or `/v1/metrics`
and Host `peerly-ai-otel:4318` is forwarded. Protobuf only; Content-Length must
appear once as canonical decimal and be at most1MiB. Transfer-Encoding/chunked,
request compression, authorization/proxy-authorization, cookies and upgrades
are rejected. Other methods, CONNECT, absolute URLs, queries, encoded path
alternatives, logs/control endpoints and alternate hosts are denied. Forwarded
routing headers are stripped and upstream Host is fixed. No access/body logging
or TLS interception is added. Collector3xx becomes502 so exporters cannot follow
an upstream redirect to another origin. HAProxy is a transport boundary, not a
protobuf business-content/privacy validator; source telemetry remains allowlisted.

OTLP has max4 frontend connections, max2 collector connections, maxqueue2,
250ms connect/queue timeouts,1s HTTP-header timeout,2s client/server inactivity
limits, no backend retries and connection closure after each response. These
are inactivity/header bounds, not a claim that a byte-trickling malicious stream
has a2s absolute lifetime. Worker SDK's independent2s export deadline and bounded
queue remain required; model-tool network denial is a mandatory actual proof.
The existing global48conn/one-thread/64MiB/PID32/.25CPU gateway bounds remain.
Provider SNI passthrough/public DNS/fixed DB configuration bytes are unchanged.

## Local source and protocol batch

Use backend locked tools, with the owned config extending ALL backend Ruff
selectors. Only pytest assertions receive the usual narrow test S101 allowance.
No gate thresholds, dependency versions or shared backend files are changed.

```sh
cd deployment/ai-egress
../../backend/.venv/bin/ruff check --config pyproject.toml prove_otlp.py otlp_client.py otlp_fixture.py tests/test_otlp_gateway.py
../../backend/.venv/bin/ruff format --config pyproject.toml --check prove_otlp.py otlp_client.py otlp_fixture.py tests/test_otlp_gateway.py
../../backend/.venv/bin/mypy --config-file ../../backend/pyproject.toml --strict prove_otlp.py otlp_client.py otlp_fixture.py tests/test_otlp_gateway.py
../../backend/.venv/bin/pytest tests/test_otlp_gateway.py
```

After the resource window is coordinated, build only this gateway image from
its exact cached pinned base; don't publish or pull a new/unreviewed base.
The allowlisted context includes only Dockerfile, original config, optional
config and entrypoint. Tests/proof scripts/dependencies are never image contents.

`prove_otlp.py` accepts only explicit immutable LOCAL gateway and Python/backend
image IDs. It uses the local Unix Docker socket with a task-empty Docker config
and cleared environment; no account login, registry credentials or remote engine.

```sh
python3 prove_otlp.py --gateway-image sha256:REPLACE_LOCAL_IMAGE_ID \
  --python-image sha256:REPLACE_LOCAL_BACKEND_IMAGE_ID \
  --output /tmp/REPLACE_OWNED_PROOF_OUTPUT.json
```

Proof networks are unique/internal, have no host ports or external provider/DNS
route, and are tagged with a unique ownership label. Native locked Python SDK
trace+metric exporters send synthetic protobuf to an isolated decoder fixture.
Negative controls cover default route OFF, prohibited methods/paths/hosts,
framing/body/type/auth/compression/redirect restrictions, wrong-interface bind,
direct collector/wrong-port/DNS bypass and bounded slow collector/queue failure.
Fixture counts ensure only expected exports reached it. Synthetic environment
marker must disappear from actual HAProxy process env. Finally, every owned
container/network is removed by exact proof label and absence is verified.
No shared DB, Docker prune, account credentials or real model calls occur.

## Actual activation boundary

This local proof does NOT prove remote networking, actual worker resource fit,
model-tool denial or provider permission. Parent must preserve the actual named
AppArmor/seccomp/proc-only rootRO/NNP/caps0/auth isolation controls and prove the
new fixed collector route cannot be used by model tools. The gateway alone gains
its reviewed telemetry attachment; the worker stays on its sole private network.
The changed gateway image/network facts invalidate the old unchanged-deployment
renewal anchor. Parent disables that timer before topology changes, completes
final namespace/transport/provider40 acceptance, then explicitly seeds a NEW
anchor; never reuse or silently amend the old accepted deployment proof.

Reference: [official pinned HAProxy3.2 manual](https://docs.haproxy.org/3.2/configuration.html),
HTTP ACLs, request timeouts, fixed bind/server and server maxqueue semantics.

## Accepted local checkpoint — 12 November 2026

Source is code-complete and the bounded local network/native SDK proof passed.
Local gateway **image ID** (not a published registry manifest):
`sha256:1bf8f2a6fd46f0234446f34a4c935136f5d1c01f48152a80a9d0dccc10dddc27`.
Pinned base remains HAProxy3.2.26, manifest96ec3c75..., no browser/Python added.
Fixture Python image IDc99a69ac... is actual backend sourceb11a84f...; this does
not claim that the future canonical58+producer/40PID image has been validated.

Actual proof: SDK trace and metric exports accepted; default port remains closed
while default gateway stays running; exact HTTP/routing denials; body limit;
redirect becomes502; direct collector/other-port/external-DNS bypass denied;
listener absent on the telemetry interface; inherited synthetic environment
marker absent from actual HAProxy process; exact expected collector counts.
Four concurrent slow requests returned503/504 within2.0095seconds with no retries
or limit changes. This is a synthetic engineering measurement, not provider or
whole-app throughput. All labeled task containers/networks were removed and
absence verified. Local image is retained for review; nothing was published.

Strict inherited backend Ruff/format/mypy4files and16 public-config pytest cases
pass. Pytest warnings are errors. A missing standalone pytest async-scope setting
was corrected, not filtered. Logs retain earlier concrete failures: unsupported
HAProxy default error bodies for413/415 (fixed static bodies), fixture explicit
IPAM requirement (fixed only fixture network allocation), and malformed upgrade
fixture. A real Upgrade requires both Connection:upgrade and Upgrade; that
corrected request is denied. Bare unpaired hop headers can be normalized away
by HTTP parsing; they cannot establish a tunnel. Denials are recorded truthfully
as either an HTTP error or a closed connection, never a fabricated400 status;
subsequent successful controls and exact collector counts prevent a crashed
proxy from being mistaken for a successful negative.

Offline parser validation with `--network=none` emits DNS socket warnings for
original public resolvers; Docker also warns that the intentional localhost
DNS choice can fail. These are retained diagnostic outcomes of denying external
routing in this fixture, not suppressed warnings or live-DNS readiness evidence.
No Python/static warning gate was weakened. Default provider configuration SHA
remains`de69397f6b2ffd0c246ceae89da7ab88eededefe7ccc17f5b53a894da7604043`.

Local Docker Desktop uses an explicit allowlisted Unix socket when the system
socket is inaccessible:
`--docker-socket /home/aleksei/.docker/desktop/docker.sock`.
This accesses only that local engine socket and task-empty client config; no
Docker auth/context files are read and no host group/daemon changes are made.
The default socket remains`/var/run/docker.sock`; remote/TCP/custom endpoints
are rejected. A future parent/CI runner chooses its actual approved local socket.

Receipt/logs and source manifest are outside Git under
`.peerly-ops/nash/otlp-gateway-20261112/`. Final fixture-script edits after the
successful network run were formatting/import sorting only; packaged runtime
configuration/entrypoint/Dockerfile bytes still match the tested image receipt.

External remaining: parent review/publication, actual Compose/Portainer endpoint
composition, final40PID worker image/collector delivery/model-tool route-denial
and new unchanged-deployment anchor. Existing ai-egress-image.yml smoke validates
only the default config; parent must add opt-in parser/wrapper and strict/protocol
checks to its publisher gate before calling CI acceptance. That workflow is
outside this task's ownership and was read only.
