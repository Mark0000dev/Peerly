# AI container safe-log relay

Host-only stdlib Python3.12 service forwarding allowlisted metadata from one
explicit full container ID to native syslog TCP127.0.0.1:5514. It is not an AI
sidecar and receives no provider credentials, app configuration or job mounts.

Verify the reviewed runtime source digest separately from the host-specific
Docker executable pin before installation.

## Install

Install ai_log_relay.py root:root0644 at
/usr/local/lib/peerly-ai-log-relay/ai_log_relay.py. Render the service template:
`@CANONICAL_AI_CONTAINER_ID@` is the selected full64 lowercase-hex container ID;
`@ROOT_OWNED_DOCKER_SHA256@` is SHA256 of the actual root-owned /usr/bin/docker
file, not an image digest. Never use a container name or moving lookup.
Install the rendered unit root:root0644 under /etc/systemd/system/, validate with
systemd-analyze verify, then reload/start through the authorized host operator.
Do not place filled host identities or environment exports in product source.

The root service necessarily has Docker daemon authority through its fixed Unix
socket. Its pinned reviewed code issues only logs --follow --timestamps
--since30s --tail200 for the configured ID; this is not daemon per-container RBAC.
It requires fixed trusted /usr/bin/docker and /usr/bin/logger, checks executable
ownership/modes and Docker hash, and uses an empty0700 private Docker config.
No developer Docker home, ambient context, login or credential configuration is
used. StateDirectory creates /var/lib/peerly-ai-log-relay with0700 permissions.

## Privacy and bounds

Only reconstructed safe event/time/level/release and closed failure/tracing/stack
metadata is forwarded. Producer release must be an actual nonzero40hex field;
missing identity is dropped, never filled from a container label. Raw messages,
exception text, private IDs, prompts, results and tokens are discarded. Invalid,
duplicate-key, nonfinite, unrecognized or oversized JSON is rejected.

Input lines are bounded16KiB, encoded bodies8KiB, queue64; overload drops new
records. Each logger send is bounded2s. Native logger stderr is discarded.
Service limits are64MiB/10%CPU/32tasks/64FD; restart5s with5 starts per300s.
The unit restricts networking to loopback and drops capabilities. Its task budget
is separate from the AI container's UID10002/cgroup resource budget.

Delivery uses RFC5424 tag studymate-ai-worker. Collector mapping promotes the
actual body.service_release to service.version. TCP send success is not Loki
acknowledgement. There is no durable cursor: restarts may duplicate recent lines;
rotation, queue overload and transport failure can lose records. No lossless or
exactly-once delivery is claimed. Only closed aggregate counters reach the relay
journal; no raw source or subprocess stderr is copied there.

## Replacement and verification

The service never follows a replacement container automatically. After an
intentional AI cutover, update the full ID and verify the Docker binary pin,
rendered unit and native receiver before restarting the relay. Stopping this
service terminates its reader/logger children, not the application container.

Synthetic tests validate privacy, framing, queue bounds, command pins and mocked
transport failure without Docker, provider calls or live log reads. Runtime
acceptance additionally needs one genuine canonical worker event in Loki with
its correct service and producer release. An idle listener, synthetic syslog
message or docker-exec print is not that proof. Do not provoke application errors
or restart the worker merely to manufacture telemetry evidence.


## Quality gate

From the product repository's backend directory, using its locked environment:

```sh
uv run --no-sync ruff check --config ../deployment/observability/pyproject.toml ../deployment/observability/log_relay ../deployment/observability/tests/test_ai_log_relay.py
uv run --no-sync ruff format --check --config ../deployment/observability/pyproject.toml ../deployment/observability/log_relay ../deployment/observability/tests/test_ai_log_relay.py
uv run --no-sync mypy --config-file pyproject.toml --strict ../deployment/observability/log_relay ../deployment/observability/tests/test_ai_log_relay.py
uv run --no-sync pytest -c pyproject.toml ../deployment/observability/tests/test_ai_log_relay.py
```

The observability workflow includes these sources in its existing strict directory
gate and runs the 15 synthetic relay cases alongside storage-budget tests. The
assertion allowance is scoped to this pytest file only. Tests use anonymous pipes
and mocked logger execution; they require neither Docker nor a daemon socket
mount. Workflow changes also trigger on backend quality configuration/lock changes.

Active-process record counters are unavailable in this version; aggregate counters
are emitted on exit. Do not signal or restart a service to obtain those counters.
