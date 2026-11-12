# AI transport gateway — credential-free deployment template

Only `deployment/ai-egress/**` belongs to this change. Backend/API, worker sandbox,
credentials, actual networks and Portainer deployment remain separate. Parent owns
provisioning/publication/deployment. Local synthetic acceptance is not a remote
runtime receipt, real provider acceptance or permission to authenticate.

## Topology and authority

```
worker -- internal ai_private --> gateway -- ai_public --> fixed destinations
          no public route        TLS passthrough :443
                                 fixed DB forward :5432
```

The gateway uses the official HAProxy3.2.26 image pinned to OCI manifest digest
`sha256:96ec3c75a9264ba94e733eeacb44051ed6e7b79bb77a73c2c36f236b6423f1f0`.
`Dockerfile` copies the reviewed `haproxy.cfg` into that pinned base as mode0444.
The deny-by-default `.dockerignore` admits only Dockerfile/config inputs. Compose
requires a separately published `PEERLY_AI_EGRESS_IMAGE` immutable digest; no
host config bind or Portainer host-file provisioning is needed. The configured
image must be built from this exact reviewed configuration, not an arbitrary
image carrying the same tag.

It runs nonroot, read-only, capability-free with NNP, one HAProxy thread, 48 total
connections, PID32, 64MiB and0.25CPU. There are no host ports, Docker socket,
credential mounts, control sockets, general CONNECT/SOCKS or client-supplied
forwarding targets. `net.ipv4.ip_unprivileged_port_start=0` is scoped to this
container network namespace so it can bind443 without restoring capabilities.

No TLS termination or interception: the original client handshake and encrypted
stream reach the fixed upstream. Native CLI and S3 SDK continue certificate and
hostname verification normally; no custom CA, `verify=False`, proxy variables or
application changes. The gateway has no request/connection logging destination;
startup diagnostics contain configuration failures only. Never enable payload,
HTTP, token, DNS query or credential logging to debug live traffic.

The ClientHello must contain exactly one of these canonical SNI strings:

| SNI | Fixed upstream | Purpose |
| --- | --- | --- |
| `auth.openai.com` | `auth.openai.com:443` | Dedicated CLI device-auth polling/token exchange/refresh |
| `chatgpt.com` | `chatgpt.com:443` | Subscription model transport |
| `s3.cloud.ru` | `s3.cloud.ru:443` | Existing path-addressed retained DISPLAY media reads |

Pinned CLI0.167.0 source review by the runtime owner used upstream commit
`086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a`.
[`login/src/device_code_auth.rs`](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/login/src/device_code_auth.rs)
uses the issuer for `/api/accounts/deviceauth/usercode` and `/deviceauth/token`;
[`login/src/server.rs`](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/login/src/server.rs)
defaults that issuer to `https://auth.openai.com` and exchanges at `/oauth/token`.
[`auth/manager.rs`](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/core/src/auth/manager.rs)
refreshes at the same issuer.
[`model-provider-info/src/lib.rs`](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/model-provider-info/src/lib.rs)
selects `https://chatgpt.com/backend-api/codex` for ChatGPT subscription auth;
the API-key branch is outside this MVP. Model listing, response streams and
WebSocket upgrades retain that host. Owner browser device verification/Google
redirects occur outside the worker and do not justify adding browser IdP/CDN
hosts to its allowlist. This is source-reviewed default transport, not a claim
that live provider redirects/residency behaviour have already been observed.

No wildcards, suffix matching, `api.openai.com`, course/user-provided endpoint,
virtual-hosted bucket alias or alternate model provider. Public DNS resolution is
explicitly1.1.1.1/9.9.9.9 in HAProxy, **not** Docker DNS or libc startup lookup;
`init-addr none` prevents the internal domain aliases from looping into the
gateway. DNS unavailability fails closed. TLS SNI is inspected for at most5s;
connect/queue timeouts5s, stream idle timeouts120s, one connect retry. This supports
TCP TLS/WebSocket streaming, not QUIC/UDP or ECH with hidden SNI. Unknown, missing,
noncanonical SNI, HTTP plaintext and CONNECT are rejected, never default-routed.

This is a hostname/port transport boundary, not an HTTP path or account policy.
HAProxy cannot verify encrypted HTTP Host, model name, URL paths, CDN domain
fronting behaviour or token use inside the permitted hosts. Application source
validation, native sandbox/credential isolation and provider-side identity remain
required. Do not describe this as content-aware exfiltration prevention.

The PostgreSQL listener forwards **only** to operator-supplied fixed
`AI_DATABASE_FORWARD_IP:5432`, with max3 connections matching the dedicated worker
budget. Supply a canonical IPv4, no URL/hostname/port. It does not inspect SQL,
select databases or enforce roles. The owner explicitly chose ordinary non-TLS
Peerly staging PostgreSQL: preserve the existing staging DB name, dedicated role,
credentials and `ssl=disable`; change **only host** to `peerly-ai-db`. Never use
`default_db`. If TLS with hostname validation is later enabled, re-evaluate DB
hostname/certificate binding rather than disabling verification.

## Parent deployment integration

1. Supply private `AI_DATABASE_FORWARD_IP` and a unique
   `PEERLY_AI_EGRESS_NETWORK`, and the pipeline-published
   `PEERLY_AI_EGRESS_IMAGE=ghcr.io/...@sha256:<digest>`, using
   `gateway.env.example` as a shape only.
2. Validate `docker compose --env-file <private-input> -f compose.yml config --quiet`.
   The published image also supports
   `haproxy -c -f /usr/local/etc/haproxy/haproxy.cfg`; supply only the nonsecret
   fixed DB IP for that validation. Build with
   `docker build -t <local-gateway-tag> deployment/ai-egress`; parent owns CI
   publication and immutable image provenance.
3. Deploy this Compose topology first. Its gateway owns an **internal:true**
   network named `PEERLY_AI_EGRESS_NETWORK` plus a distinct public network. If
   Portainer uses another network name, explicitly bind the worker to that same
   actual network; do not create a second similarly named public network.
4. Merge `worker-dns.override.yml` into the existing worker Compose. Its existing
   `ai-egress` external network must be this gateway's internal `ai_private`.
   The worker must have **exactly that one network**, no public/default network,
   host networking or extra host routes. Keep worker namespace/security policy
   from the separately accepted containment proof.
5. Worker `dns: [127.0.0.1]` preserves Docker's internal service/alias resolution
   but makes external DNS forwarding unusable. Required TLS names resolve through
   the gateway's private network aliases. Other domain queries fail. Do not let
   the worker use public DNS directly; an internal Docker network alone does not
   necessarily stop the embedded resolver from forwarding external queries.
6. Keep S3 endpoint `https://s3.cloud.ru` and path addressing, and subscription CLI
   source-canonical defaults. Change worker DB host to `peerly-ai-db` as above.
   Set no HTTP_PROXY/HTTPS_PROXY/ALL_PROXY, custom model base URL or TLS bypass.
7. Inspect actual network membership/internal flag/aliases, DNS, ports, fixed DB
   target and security/resource configuration before starting any private
   credential-bearing worker. Run the credential-free controls on the actual
   host/topology first. The public gateway must never expose ports through
   Traefik/host publication or join the general application network.
8. Parent coordinates real auth/refresh and synthetic model/media smoke only
   after transport and runtime containment acceptance. Redirects/new runtime
   hosts stay blocked until their exact purpose/source is reviewed; do not
   auto-expand the allowlist after a connection failure.

The shared worker template is intentionally unchanged by this task. Parent must
incorporate the DNS override and actual network identity in its deployment;
copying the HAProxy file alone does not restrict worker egress.

## One bounded local proof

Requires Docker, local OpenSSL and an already built production backend image
(used only as a Python interpreter; no application settings, credentials or DB).

```sh
python3 deployment/ai-egress/prove.py \
  --python-image sha256:<immutable-local-backend-image> \
  --output /tmp/peerly-ai-egress-evidence.json
```

The proof creates unique isolated Docker networks and a synthetic upstream with
an ephemeral fixture certificate/key. Nothing contacts OpenAI/S3/PostgreSQL.
Only fixed backend addresses are substituted in a copy of `haproxy.cfg`; the
production SNI ACL/frontend/limits are unchanged. The worker-like client belongs
only to the internal network with no external DNS forwarder. It verifies TLS
against the synthetic CA for all3 actual allowlisted SNI names, checks fixed DB
forwarding, then rejects unknown/suffix/no-SNI, plaintext CONNECT, wrong ports,
direct upstream/public IP bypass and an ordinary external DNS name. Synthetic
certificate trust is confined to this test, never deployment configuration.
Owned containers/networks/temp fixtures are removed in `finally`; no shared DB,
Docker prune, live credentials or full backend/browser suite is involved.

Local result: all listed controls passed; Compose and production HAProxy config
validate. Evidence `/tmp/peerly-ai-egress-evidence.json`, raw log
`/tmp/peerly-ai-egress-proof.log`. Actual host/networks/real CLI transport remain
separate acceptance; this task neither deploys nor changes backend source.

## References

- [HAProxy official image](https://hub.docker.com/_/haproxy)
- [HAProxy DNS resolution](https://www.haproxy.com/documentation/haproxy-configuration-tutorials/proxying-essentials/dns-resolution/)
- [HAProxy3.2 configuration reference](https://docs.haproxy.org/3.2/configuration.html)

## Future optional SDK telemetry route

See [OTLP.md](OTLP.md). The optional image files alone enable nothing: only an
explicit reviewed `otlp.override.yml` adds a fixed private-interface HTTP route
and a gateway-only collector network attachment. The default provider gateway
configuration, worker network and current live runtime remain unchanged.
