# AI gateway telemetry delivery

Current: implemented and locally verified; live activation/provider40 acceptance
pending parent. Existing live gateway/worker and accepted c59 renewal timer were
not modified. Next Nash task is parent-assigned AI image overlay cleanup in
backend/Dockerfile.ai-worker + .github/workflows/ai-image.yml; basepin stays parent-owned.

Changed owned paths: Dockerfile and context allowlist admit separate dormant
OTLP config/entrypoint; explicit otlp.override.yml, public contract OTLP.md,
strict standalone quality config, config regressions, native SDK/protocol fixtures
and label-owned local proof driver. Original haproxy.cfg/compose.yml/provider
DNS/SNI/fixed PostgreSQL listener stay unchanged. No application settings/API,
source permissions, DB schema or provider/credentials code changed.

Public origin agreed with Noether: http://peerly-ai-otel:4318 on existing private
AI network. Gateway alone gets reviewed telemetry network, with public fixed
private-interface bind and collector IPv4 values; collector backend always4318.
No arbitrary target, CONNECT, runtime flags, provider secrets or inherited env.

Evidence and exact commands: OTLP.md and outside-Git source/evidence manifest
.peerly-ops/nash/otlp-gateway-20261112/manifest.json. Local image ID1bf8f2a6...;
strict Ruff/format/mypy4 and16 targeted unit tests. Native SDK trace+metrics and
negative network/protocol/resource controls pass; bounded queue measurement
2.0095s; exact fixture counts; owned containers/networks fully cleaned. No broad
backend/frontend/PG/provider reruns or live deployments. Source fixture/debug
failures and expected offline/DNS CLI warnings remain in the evidence record.

Parent integration request: extend the gateway image publisher's default-only
smoke to optional parser/entrypoint and the strict native protocol gate, preserve
separate explicit opt-in topology and never enable the current32PID worker from
this local proof. After any actual gateway image/network change the old c59
anchor cannot attest unchanged deployment; parent must control that transition.
