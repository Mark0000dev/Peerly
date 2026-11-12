# Fixed AI SDK OTLP transport

The optional [otlp.override.yml](otlp.override.yml) enables a fixed HTTP route for
trusted SDK traces/metrics. The default [compose.yml](compose.yml) command loads
only provider/database transport: building the image does not enable port 4318.

## Configuration and trust

The worker origin is `OBSERVABILITY__COLLECTOR_ORIGIN=http://peerly-ai-otel:4318`.
That alias resolves to the gateway on its existing private AI network, not the
collector. Explicitly merging the overlay selects `/usr/local/bin/peerly-ai-otlp`
and attaches only the gateway to the external `PEERLY_AI_TELEMETRY_NETWORK`.
The worker must retain exactly its private AI network and existing containment.

Supply these public configuration addresses:

- `AI_OTLP_BIND_IP`: the gateway's actual RFC1918 address on the private AI network.
- `AI_OTLP_COLLECTOR_IP`: the collector's fixed RFC1918 address on the reviewed
  telemetry network, always port 4318.
- `AI_DATABASE_FORWARD_IP`: the existing canonical fixed database IPv4, port 5432.

The entrypoint rejects missing/malformed/leading-zero addresses, URLs, wildcard
values, injected arguments and identical bind/collector IPs. It starts HAProxy
with only PATH and those three public IP variables; credentials and arbitrary
proxy/config overrides are not inherited. Its `--check` mode validates address
shape only. Actual Docker endpoint membership and interface selection must be
checked independently; a private IP alone proves neither.

## HTTP and resource bounds

Only POST to exact origin-form `/v1/traces` or `/v1/metrics`, with the single Host
`peerly-ai-otel:4318`, is forwarded to the fixed collector. Content type must be
`application/x-protobuf`; exactly one canonical decimal Content-Length is required,
at most 1MiB. Chunked/compressed bodies, auth/proxy-auth, cookies, upgrades, queries,
absolute URLs, alternate paths/hosts, logs and control endpoints are denied.
Forwarding headers are stripped and upstream Host is fixed. Collector redirects
become 502. No access/body logging or TLS interception is added. This transport
does not validate protobuf privacy; source telemetry still needs its allowlist.

Limits are four frontend and two collector connections, queue depth two, 250ms
connect/queue, 1s headers and 2s client/server inactivity. There are no backend
retries; responses close connections. Inactivity bounds are not an absolute 2s
lifetime for a trickling client. The SDK's independent 2s export deadline and
bounded queue remain necessary. Global gateway resource limits and provider/DB
transport policy stay unchanged.

## Local validation and protocol proof

Prepare the locked backend environment first. From `deployment/ai-egress/`:

```sh
../../backend/.venv/bin/ruff check --config pyproject.toml prove_otlp.py otlp_client.py otlp_fixture.py tests/test_otlp_gateway.py
../../backend/.venv/bin/ruff format --config pyproject.toml --check prove_otlp.py otlp_client.py otlp_fixture.py tests/test_otlp_gateway.py
../../backend/.venv/bin/mypy --config-file ../../backend/pyproject.toml --strict prove_otlp.py otlp_client.py otlp_fixture.py tests/test_otlp_gateway.py
../../backend/.venv/bin/pytest -c pyproject.toml tests/test_otlp_gateway.py
```

Build the gateway as described in [README.md](README.md). The proof requires its
immutable local image ID and a local Python image containing the locked native
OpenTelemetry SDK dependencies. From the repository root:

```sh
backend/.venv/bin/python deployment/ai-egress/prove_otlp.py \
  --gateway-image sha256:REPLACE_LOCAL_GATEWAY_IMAGE_ID \
  --python-image sha256:REPLACE_LOCAL_SDK_IMAGE_ID \
  --output /tmp/peerly-ai-otlp-proof.json
```

The proof uses the local Unix Docker socket, an empty client-auth configuration,
unique labeled internal networks, no host ports and synthetic native SDK trace/
metric exports. It tests default route off, HTTP/framing/size/redirect restrictions,
wrong-interface bind, direct collector/wrong-port/DNS bypass and slow collector/
queue failures. Exact fixture counts distinguish valid denials from a dead proxy.
It checks inherited synthetic environment markers are absent and removes all owned
resources, verifying absence. It reads no provider credentials and makes no model
calls. Tests/proof dependencies are not added to the gateway image.

## Activation

Local proof and image publication do not establish remote topology, live collector
delivery, provider permissions or actual worker resource fit. Preserve AppArmor,
seccomp, restricted mounts, read-only root, no-new-privileges, dropped capabilities
and auth isolation. Verify that model tools cannot use the collector route.
Only the gateway gains the telemetry attachment.

An image or network change invalidates an unchanged-deployment renewal anchor.
Disable its renewal before changing topology, complete actual containment,
transport and provider acceptance, then explicitly seed a new anchor. Never
silently reuse an old deployment proof. No deployment is performed by building
or publishing this image. The [HAProxy reference](https://docs.haproxy.org/3.2/configuration.html)
defines the timeout, ACL and queue semantics.
