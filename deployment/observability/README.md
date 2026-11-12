# Observability deployment

The observability bundle receives sanitized application telemetry and exposes
private query/scrape endpoints. See [system observability](../../docs/observability.md)
for event ownership, privacy and operational requirements.

## Components

| Files                            | Responsibility                                                         |
| -------------------------------- | ---------------------------------------------------------------------- |
| `compose.yml`, `collector/`      | OpenTelemetry ingestion, safe processing and exporters                 |
| `tempo/`, `tempo-s3.compose.yml` | Trace storage and S3-backed Tempo deployment                           |
| `prometheus/`                    | Scrape configuration, recording/alert rules and rule tests             |
| `grafana/`                       | Dashboard and data-source templates                                    |
| `alertmanager/`                  | Technical alert routing template                                       |
| `gateway/`                       | Authenticated private metrics, trace-query and log-ingestion routes    |
| `archive/`                       | Sanitized archive export, client encryption and offline recovery tools |
| `images.json`                    | Pinned component images used by validation                             |

Prometheus, Alertmanager, Grafana and Loki may be supplied by existing monitoring
infrastructure. Render templates with the actual deployment's endpoints and
separate reader/writer credentials. Do not commit filled configuration.

## Network and storage

Keep OTLP ingestion private. Browser clients submit bounded observations through
the application API; they do not receive collector, Loki or Grafana credentials.
The staging reader gateway exposes authenticated GET/HEAD query and scrape
routes. The monitoring writer gateway accepts only the configured authenticated
log-ingestion POST route. Do not expose a generic upstream proxy.

Preserve all required Compose overlays when changing a running installation:
base, trace-storage configuration, gateway, archive, and the AI telemetry network.
AI workers use the isolated fixed OTLP gateway described in
[AI worker telemetry](AI_WORKER_TELEMETRY.md). They do not join the general
application or monitoring network.

Provision restrictive data-directory permissions and explicit disk/resource
budgets. Preserve export queues and archive state during updates; deleting them
can discard accepted telemetry. Configure S3 access, retention and encryption
according to the environment. Archive recovery requires the separately protected
key/configuration and an actual restore exercise.

## Telemetry contract

The collector accepts closed safe attributes and events. Do not forward chat
bodies, prompts, verification codes, credentials, raw private errors or arbitrary
browser payloads. Producer `service_release` supplies `service.version`; never
invent a static version for unknown historical producers. Actor identity comes
from authenticated server context rather than client-provided IDs.

Dashboards and alert rules distinguish availability, errors, latency, pool and
queue pressure, worker freshness, delivery lag and storage headroom. Unknown or
stale queue samples must not appear as healthy zero values. Technical alerts use
Alertmanager routing; product support notices use the external-delivery worker.

## Validation

Run the credential-free native validation from the repository root:

```sh
python3 deployment/observability/validate.py --output /tmp/peerly-observability-validation
```

The validator uses pinned images and synthetic loopback fixtures. The GitHub
observability workflow prepares its required tooling and runs the corresponding
checks. Source/configuration validation does not prove real remote ingestion,
alerts, storage or restoration; verify those separately after deployment.

No automatic deployment or production credentials are included in this bundle.
