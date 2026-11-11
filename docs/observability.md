# Observability, product analytics and privileged data inspection

Status: design baseline, 6 November 2026. No monitoring server has been accessed and no telemetry has been exported. Endpoints, versions, credentials, infrastructure capacity and data locations remain to be inventoried.

Owner decisions: pilot is APU, Malaysia only. Grafana is for the owner/developers, with no additional viewing restrictions within that team; product users cannot access it. A privileged operator must be able to inspect all application data and relationships, including conversations from PostgreSQL when needed. Conversation content must not appear in ordinary logs.

## 1. One correlated picture, distinct storage responsibilities

| Signal/data                                                 | Store                                              | Purpose                                                            |
| ----------------------------------------------------------- | -------------------------------------------------- | ------------------------------------------------------------------ |
| Metrics                                                     | Existing Prometheus                                | Rates, latency, saturation, availability and delivery health       |
| Structured technical logs                                   | Existing Loki                                      | Sanitized request/worker/error diagnostics                         |
| Distributed traces                                          | Add Tempo or another OTel-compatible trace backend | Request/use-case/database/provider timing and causal links         |
| UX/product exploration                                      | Existing Umami                                     | Screen/action journeys, funnels and observed client behavior       |
| Canonical business events and analytics views               | Managed PostgreSQL                                 | Deduplicated conversions, relationship outcomes and user timelines |
| Full profiles, requests, conversations, files and relations | PostgreSQL + private object storage                | Application truth and exhaustive privileged inspection             |
| Operator access/change audit                                | PostgreSQL                                         | Who inspected/changed which records and when                       |

Grafana connects these views. It is not itself a trace store, and Loki does not replace one. Tempo integrates with the existing Grafana/Prometheus/Loki stack. [Tempo documentation](https://grafana.com/docs/tempo/latest/).

Use a local collector/forwarder on the app VPS; default choice is Grafana Alloy unless the existing infrastructure already standardizes on an OTel Collector. Deploy one, not both. API/worker emit OTLP traces/metrics locally. The collector exposes a private Prometheus scrape endpoint and forwards traces to Tempo. Collect JSON stdout logs once and forward to Loki; do not duplicate the same logs through stdout and OTLP. Use private connectivity/TLS to the monitoring server. [Alloy's role](https://grafana.com/docs/alloy/latest/introduction/how-alloy-works/).

Prometheus pulls over a private network by default. If outbound-only forwarding is necessary, verify/configure a supported remote-write receiver before choosing that path; do not assume an existing Prometheus accepts pushes. Exporter queues are bounded and observable. Monitoring failure degrades telemetry, not business transactions or request latency.

## 2. Correlation model

| Identifier            | Meaning and owner                                                                           |
| --------------------- | ------------------------------------------------------------------------------------------- |
| `user_id`             | Internal authenticated account identity, resolved by server                                 |
| `analytics_id`        | Stable random non-email identity mapped to that account; explicitly linkable, not anonymous |
| `client_session_id`   | Random telemetry session identity; never the authentication cookie/token                    |
| `action_id`           | One logical human intent across requests/retries; validated client correlation              |
| `request_id`          | One server-generated HTTP attempt                                                           |
| `trace_id`, `span_id` | Technical execution and parent/child timing                                                 |
| `event_id`            | One deduplicated canonical/client-observed event                                            |
| `operation_id`        | Durable business command/idempotency result reference                                       |
| Resource IDs          | Request, relationship, conversation, message, goal/version, media or case references        |

This is intentionally identified analytics: the operator can resolve an analytics ID to the actual account and follow all its relationships. Do not call it anonymous or imply that hashing an email makes it anonymous.

Trace each meaningful action/request/use case and bounded background delivery, not every keystroke and not an entire multi-day user session. Browser HTTP propagation links a UI span to the API; authenticated identity is attached server-side. Store originating action/trace references with canonical events. Background work starts a new delivery span with a link to the originating context; failed attempts have separate spans and the same logical delivery ID.

An operator journey should be: product funnel → actor timeline → action/operation → canonical resource → full database record → request trace → relevant logs, with reverse links. An arbitrary record also has its related actions/events/audit history. A missing/expired trace is labeled as such; the stored conversation can still be inspected.

Do not accept a client-supplied actor/role as truth. Accept only bounded, syntactically valid trace context; never use it for authorization. Propagate trace context only to our services. Do not put personal identity in baggage or forward private baggage to Telegram, email, AI or storage providers. [OTel baggage considerations](https://opentelemetry.io/docs/concepts/signals/baggage/).

## 3. Instrumentation boundaries

Backend: FastAPI incoming requests, application use cases, SQLAlchemy query timing/transaction outcomes, asyncpg pool health, worker jobs, outbox age/retries, email/media/Telegram/Umami provider calls. Spans use stable operation and route-template names. Disable SQL parameter capture, body capture and credential-bearing URL attributes. Sanitize exception messages; database/provider errors can otherwise contain private values.

Frontend: explicit screen views and consequential interactions, request spans, rendering/navigation timings, network failures, sanitized JS errors, and Web Vitals where supported. Use one HTTP tracing integration, not both auto-instrumentation and a duplicate interceptor. Serve source maps privately as release artifacts for error diagnosis. Screen names are route templates, not URLs containing account/message IDs or search text.

Browser telemetry enters a bounded same-origin endpoint with origin/auth/rate controls and allowlisted attributes; collector ports and exporter credentials stay private. Browser observations are untrusted and identified separately from server-committed outcomes. Reset identities/queues on logout/account switch. Never export auth headers, cookies, form values, photo data or chat drafts.

Source-side allowlists plus collector-side filtering are required. No raw request/response-body logging or “log the whole DTO” convenience. Test secret/private-content scrubbing at every ingress, error path and export boundary. OpenTelemetry provides guidance for excluding/redacting sensitive attributes before storage. [Handling sensitive data](https://opentelemetry.io/docs/security/handling-sensitive-data/).

## 4. Metrics and logs

Initial metric families, with stable service/environment/release context:

- HTTP request count and duration by method, route template and outcome/status class; separate ordinary REST latency from long-lived SSE.
- Active/reconnecting SSE connections, event lag, resets and queue overflows; no per-user label.
- SQL pool in-use/capacity/wait and dependency failures; transaction conflict/deadlock counts.
- Worker heartbeat, due/leased/dead deliveries, oldest due age and provider attempt duration/outcome.
- Media processing queue age/failures and email delivery failures.
- Telemetry queue saturation/dropped exports and ingest rejection counts.

Do not label Prometheus metrics with user IDs, request/trace IDs, email, resource IDs or free-form error text. Store drilldown identifiers in trace attributes/log fields and use exemplars where supported. Bounded metric dimensions keep cardinality manageable. [Prometheus instrumentation guidance](https://prometheus.io/docs/practices/instrumentation/).

JSON log fields: `timestamp`, `severity`, `service`, `environment`, `release`, `event`, `operation`, `route_template`, `status`, `duration_ms`, `request_id`, `trace_id`, `span_id`, `action_id`, `analytics_id` and relevant opaque resource IDs. Raw path/query/body, cookie/auth headers, OTP, signed media URLs and user text are excluded. Third-party request logging must apply the same policy.

Loki index labels stay low-cardinality: service, environment and a small severity/stream set. User/trace/action/resource IDs are structured metadata or JSON fields, not index labels. All developers can search them in Grafana. [Loki structured metadata](https://grafana.com/docs/loki/latest/get-started/labels/structured-metadata/).

## 5. Canonical product event catalogue

Use versioned schemas and unique event IDs. Mandatory identified server outcomes are recorded with their business transaction; client observations use the validated telemetry ingress. A queued UI attempt never counts as successful server behavior.

| Event family                                                   | Source of truth                 | Useful noncontent dimensions                                                        |
| -------------------------------------------------------------- | ------------------------------- | ----------------------------------------------------------------------------------- |
| `screen.viewed`, `onboarding.step_viewed`                      | Client-observed                 | Screen ID, app version, surface, previous screen                                    |
| `auth.email_confirmed`, `profile.ready`                        | Server commit                   | Onboarding duration/step, photo readiness, surface                                  |
| `goal.saved`, `goal.completed`                                 | Server commit                   | Goal/version, canonical subject, topic-present flag, shared-learning setting        |
| `discovery.candidate_seen`                                     | Client-observed actual exposure | Candidate/goal IDs, mode, grounded reason code                                      |
| `discovery.candidate_passed`                                   | Server commit                   | Goal/candidate IDs, mode; distinguish failed attempts                               |
| `request.previewed`, `request.send_attempted`                  | Client-observed                 | Type, source gesture/button, goal/version, note-present flag                        |
| `request.sent`, `request.accepted`, `request.closed`           | Server commit                   | Pair/request IDs, type, timing, internal closure category                           |
| `message.stored`, `conversation.two_way_started`               | Server commit                   | Thread/message IDs, sender identity, attachment-present flag, elapsed time; no body |
| `study.reported`, `feedback.saved`                             | Server commit                   | Pair/actor IDs, structured answer, record revision                                  |
| `profile.hidden`, `profile.restored`, `block.changed`          | Server commit                   | Actor/target references and resulting state                                         |
| `support.case_opened`, `report.created`                        | Server commit                   | Case/category/target type, priority; no evidence/note text                          |
| `operator.resource_viewed`, `operator.resource_changed`        | Audit store                     | Operator, target/edge, operation, time, trace/action references                     |
| `account.deleted`, `account.banned`, `policy.notice_delivered` | Server commit                   | Account lifecycle or actual notice version/delivery, without private content        |

Analytics allowlists exclude names/email, message content, goals/topics as free text, private report notes, photos/attachments, exact location and auth material. Canonical subject IDs are fine. A privileged inspection link resolves the underlying content on demand through the operator API; do not copy it into the event payload.

The worker exports mandatory identified analytics; no optional preference gate exists. Soft deletion retains prior events and exports their actual history, without creating fictitious post-deletion user actions. Umami receives allowlisted events from the worker, using `analytics_id` as the Distinct ID and `event_id` as an event property. Only one collection path owns each event: no simultaneous browser tracker auto-pageview and server forwarding for the same screen. Validate the installed Umami version: Distinct IDs are available from v2.18.0; identity links visits/devices. [Distinct IDs](https://docs.umami.is/docs/distinct-ids).

Use the supported Sending Stats API rather than writing to Umami's database. Its ingestion endpoint and authenticated reporting API are different interfaces; reporting credentials never go to browsers. Keep actual client context when available and do not pretend a worker's IP/UA is the student. Avoid geographical/IP-derived conclusions for forwarded events. [Sending stats](https://docs.umami.is/docs/api/sending-stats), [reporting authentication](https://docs.umami.is/docs/api/authentication).

External ingestion is not an exactly-once ledger. After an ambiguous delivery timeout, Umami may contain duplicates. Exact conversion and cohort dashboards in Grafana use deduplicated PostgreSQL `analytics` views; Umami is an exploration tool. Do not query its private schema or invent a Grafana Umami plugin dependency.

## 6. Dashboards and measurements

Provision dashboards/query definitions in the repository when implementation starts. Everyone in the owner/developer Grafana organization sees the same dashboards; no per-user filtering is required.

| Dashboard             | Main questions and drilldowns                                                                                |
| --------------------- | ------------------------------------------------------------------------------------------------------------ |
| Service overview      | Availability, REST latency/error rate, release regressions, active streams, dependency health → trace/log    |
| Database and delivery | Connection budget, query waits, failed transactions, queue age, retries and terminal jobs                    |
| Client experience     | Navigation/action latency, browser errors, version/device family, failed uploads/sends and recovery          |
| Activation funnel     | Confirm email → profile ready → goal/help setup → relevant candidate → preview → confirmed request           |
| Connection outcomes   | Request acceptance, time to acceptance/two-way exchange, latest self-reported studying and response coverage |
| Discovery supply      | Eligible pool/exhaustion by subject/mode, newcomer exposure, broadening/reconsideration                      |
| Support and safety    | New/open/aged cases, notification delivery, restrictions/restorations and operator actions                   |
| Actor/action explorer | Identified timeline and links across account, event, operation, trace, conversation and full records         |
| Telemetry quality     | Rejected/duplicated events, missing correlations, delivery lag, volume/retention and dropped telemetry       |

Define cohorts before writing SQL. Acceptance rate uses requests sent in a stated cohort and their later outcomes, not accepted events divided by sent events in an unrelated wall-clock window. Two-way conversation requires human messages from both participants. Study-start measures count each pair once using the latest in-window answers; report at-least-one-Yes, conflicts and response coverage separately. Nonresponse is unknown. No events from fixtures/test accounts enter production funnels.

Trace collection targets 100% of instrumented meaningful pilot activity across browser/API/worker. Do not silently reduce sampling to satisfy load: use bounded buffering, resource isolation, capacity alerts and explicit gap/drop metrics; changes to coverage require an owner decision. Canonical product/audit records are never inferred from sampled traces. Session replay, DOM recording and keystroke capture are not part of the baseline.

Owner policy: retain all accumulated business/media, canonical analytics, audit and collected trace/log history, including after account soft deletion. Hot-store TTL is permitted only after verified durable archival and retrieval; no automatic loss of retained history. SSE transport hints can expire after 24 hours because canonical events/history remain; expired auth secrets/temp files still require cleanup. Budget and verify storage, archive/index/retrieval and backups before pilot; do not promise zero telemetry loss.

## 7. Alerts and Telegram

Start with a small actionable set; thresholds below are provisional pilot defaults, calibrated in staging. Every alert needs an owner, runbook, dashboard, environment and grouping key.

| Condition                                                       | Initial policy                                                     |
| --------------------------------------------------------------- | ------------------------------------------------------------------ |
| External API/frontend probe failing or DB readiness unavailable | Critical after 2 minutes                                           |
| REST error ratio >5%                                            | 10 minutes, with a minimum request count to avoid low-volume noise |
| REST p95 latency >1s                                            | 10 minutes, excluding SSE and with sufficient observations         |
| Oldest due outbox task >5 minutes or terminal critical delivery | Warning; escalate sustained auth/support delivery failures         |
| Worker heartbeat missing                                        | Critical after 2 minutes                                           |
| PostgreSQL connection budget >85%, or sustained connection wait | Warning, escalate continued exhaustion                             |
| Media queue age/errors or storage capacity exhaustion           | Warning/critical according to failure impact                       |
| Telemetry export dropping data / trace store unavailable        | Warning; visibility failure is not healthy service evidence        |
| Backup/PITR verification stale or restore drill failed          | Operational alert, not just a successful scheduled-job counter     |

Technical alerts go Prometheus → existing Alertmanager → Telegram, using native Telegram receiver support. Group related symptoms, deduplicate repeated firing, inhibit downstream dependency noise where appropriate and deliver resolution notifications. Keep alert-rule ownership in one place; Grafana renders dashboards rather than creating a second competing rule set. [Alertmanager Telegram configuration](https://prometheus.io/docs/alerting/latest/configuration/#telegram_config).

Support alerts are application workflow: `support.case_opened` → committed outbox → async worker → Telegram bot. The bot sends case ID/category/priority/time and an authenticated operator-console link. It does not forward the student's message or expose database access. Bot failure does not lose the case. At-least-once delivery may duplicate an ambiguous send; deduplicate/group where possible. No inbound bot-command/webhook service is needed for outbound notifications.

Use separate technical/support chat topics or channels to avoid drowning support in metrics. Telegram credentials/chat IDs are deployment secrets. Configure a second delivery channel for Telegram failure before relying on it as the only critical alert path. No messages are sent until integration is explicitly configured and tested.

## 8. Terms/Privacy, registration and exhaustive operator access

This is an engineering design, not a determination of the legal operator or PDPA applicability. The regulator's FAQ describes the Act's commercial-transaction scope; the operator/entity and the pilot's actual arrangement must be established before recruitment. Internal-only Grafana does not make identified telemetry nonpersonal. [Malaysia regulator FAQ](https://www.pdp.gov.my/en/faq/).

Owner-approved product UX: a compact inline registration sentence links Terms/Privacy; no separate legal step, checkbox, notice-acknowledgment control, analytics opt-out or repeated acceptance. Mandatory account-linked analytics, traces, privileged access, external AI processing and retained history after soft deletion are explained in those full pages. Record versions genuinely displayed at the explicit registration action; do not label the record as a checkbox opt-in or proof of reading. Updated documents generate an informational notification, no reacceptance/grace gate. This records product requirements, not a determination that authored terms satisfy applicable law. Final service-operator/contact/provider facts and documents remain to be supplied.

Managed PostgreSQL, the VPS, monitoring server, backups, object storage, email and Telegram may be in different countries. Inventory them before describing the system as Malaysia-only data hosting. The regulator's cross-border guidance requires an applicable transfer condition and notice when transferring personal data out of Malaysia; select and document the applicable arrangement rather than assuming a Malaysian user base solves hosting questions. [JPDP cross-border guidance](https://www.pdp.gov.my/ppdpv1/wp-content/uploads/2025/08/GP_CBPDT_EN.pdf).

The privileged explorer provides exhaustive business-data visibility, not just selected support evidence. Access logs record operator/target/time/result and correlation IDs; contents remain in PostgreSQL/object storage. This design cannot promise end-to-end encrypted conversations unreadable by the operator. State accurately what TLS, storage encryption and authorized operator access provide. Hiding changes discovery/new-contact only and keeps accepted chats usable. User account deletion is a distinct soft-delete lifecycle transition: public identity is removed and sessions revoked, while all accumulated business data, analytics and trace links remain available internally. Terms/Privacy must describe that retention accurately; no claim of physical erasure.

## 9. Implementation and acceptance

Before wiring exporters, inventory the installed versions, datasource UIDs, endpoints/auth, TLS/private network, regions, storage capacity and retention. Add Tempo only after choosing its storage/backup budget. No real student data is needed for this verification.

Test with synthetic identities and seeded nonprivate scenarios: browser action → API → SQL → canonical event → worker → delivery, linked in Grafana. Verify that a privileged operator can traverse all related records and read the stored conversation while the text is absent from exported signals. Test that product users cannot access Grafana/operator routes. All developers retain dashboard access.

Automate redaction/allowlist/schema tests, event-ID deduplication, registration receipt/identity reset, concurrent event ordering, exporter outage/backpressure, retention/cursor reset and bot delivery retries. Test alert rules with promtool and representative firing/resolution cases. Validate provisioned dashboards against the staging datasources; a JSON file alone does not prove the dashboard works.

## MVP AI queue

AI is in MVP scope using one Codex executor. Instrument admission/rejection, per-kind queue depth/oldest age, wait/execution, retries/timeouts, expired jobs, lease/singleton and auth/circuit availability. Correlate request -> job -> attempt with span links; record no prompt, image, returned text or raw CLI event stream. Alert independently from core API readiness. Validate overload isolation and orphan-process recovery using a slow/failing fake before enabling the real executor. AI input/output and metadata retention follows the owner-approved retained-history policy in [AI design](ai.md).
