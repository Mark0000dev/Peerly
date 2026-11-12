# AI transport gateway

HAProxy provides a fixed-destination transport boundary for the isolated AI worker:

```text
worker -- internal AI network --> gateway -- public network --> allowed TLS hosts
                                   |
                                   +-- fixed PostgreSQL address:5432
```

The [Dockerfile](Dockerfile) uses the digest-pinned HAProxy base and copies only
the transport configuration and optional OTLP entrypoint. [compose.yml](compose.yml)
requires an immutable `PEERLY_AI_EGRESS_IMAGE` digest. Configuration and image
publication do not establish that this topology is deployed or accepted.

## Transport policy

The gateway runs nonroot with a read-only filesystem, no capabilities, no-new-
privileges, one thread, 48 connections, PID limit 32, 64MiB memory and 0.25 CPU.
It has no published host ports, credentials, Docker/control sockets or general
CONNECT/SOCKS proxy. A container-scoped unprivileged-port sysctl permits port 443
without restoring capabilities.

TLS passes through without termination. Clients retain normal certificate and
hostname verification; do not add custom CAs, TLS bypasses or proxy variables.
Only these exact ClientHello SNI values route to their matching fixed port 443:

| SNI               | Purpose                                               |
| ----------------- | ----------------------------------------------------- |
| `auth.openai.com` | CLI device authentication, token exchange and refresh |
| `chatgpt.com`     | Subscription model transport                          |
| `s3.cloud.ru`     | Path-addressed retained display-media reads           |

Unknown, absent or noncanonical SNI, plaintext and CONNECT are rejected. There
are no wildcard, suffix, user-supplied or alternate-provider destinations. This
supports TCP TLS/WebSocket streams, not QUIC or hidden-SNI ECH. HAProxy resolves
upstreams using its explicit public resolvers, not Docker aliases; DNS failure
fails closed. Inspection/connect/queue bounds are 5s, stream inactivity bounds
120s, with one connection retry.

The boundary cannot inspect encrypted HTTP paths, Host, model identity or token
use. It is not content-aware exfiltration prevention. Source validation, worker
sandboxing and credential isolation remain required. Do not enable payload,
request, credential or DNS-query logging to diagnose live traffic.

The database listener forwards only to canonical operator-configured
`AI_DATABASE_FORWARD_IP:5432`, with three upstream connections. It does not enforce
SQL roles or database selection. Preserve the deployment's existing database,
dedicated role and credentials; only the worker DSN host becomes `peerly-ai-db`.
The current staging connection uses `ssl=disable`; do not apply that policy to a
different deployment or disable verification to work around certificate names.

## Deployment configuration

1. Supply `PEERLY_AI_EGRESS_IMAGE` as a published digest,
   `PEERLY_AI_EGRESS_NETWORK` as the actual private network name, and the fixed
   database IPv4. Validate configuration from this directory with
   `docker compose --env-file /path/to/private-input -f compose.yml config --quiet`.
   Never print secret-bearing rendered configuration.
2. Attach the worker to exactly the gateway's `internal: true` AI network. The
   gateway alone also joins its public network. No worker public/default network,
   host networking or extra external route is allowed.
3. Preserve Docker's internal aliases while denying external DNS forwarding from
   the worker, using the reviewed worker DNS policy (`dns: [127.0.0.1]`). The TLS
   names and `peerly-ai-db` must resolve to the gateway's private endpoint. An
   internal Docker network alone does not prove external DNS is blocked.
4. Keep the S3 origin `https://s3.cloud.ru` with path addressing and the CLI's
   subscription transport defaults. Set no HTTP/HTTPS/ALL proxy, alternate model
   base URL or TLS bypass. Authentication browser redirects do not justify adding
   browser identity-provider/CDN hosts to the worker allowlist.
5. Inspect actual network membership, internal flags, aliases, routes, DNS,
   security/resource limits and fixed database forwarding before using credentials.
   Do not expose the gateway through host ports, ingress or an application network.
   New provider hosts require explicit configuration review, not automatic retries
   with a wider allowlist.

Build from the repository root:

```sh
docker build --file deployment/ai-egress/Dockerfile --tag peerly-ai-egress:local deployment/ai-egress
```

Validate the default image configuration with synthetic, nonsecret input:

```sh
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --env AI_DATABASE_FORWARD_IP=192.0.2.10 \
  peerly-ai-egress:local haproxy -c -f /usr/local/etc/haproxy/haproxy.cfg
```

Parser success is not DNS, forwarding or provider acceptance. Run transport and
worker-containment controls on the actual topology before live authentication.

## Optional telemetry

[OTLP.md](OTLP.md) describes the explicit fixed collector overlay, local protocol
proof and activation requirements. Building the image alone does not enable the
OTLP listener or attach a telemetry network. See the
[HAProxy 3.2 reference](https://docs.haproxy.org/3.2/configuration.html) for the
configuration semantics.
