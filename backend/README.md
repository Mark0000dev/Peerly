# Peerly backend

FastAPI, PostgreSQL/asyncpg, typed SQLAlchemy 2 (`Mapped`/`mapped_column`) and Alembic. Domain and use cases are independent of frameworks; Import Linter enforces dependency direction. Read [mandatory rules](AGENTS.md).

The local student API includes Google OIDC and separate institutional verification, explicit policy-backed registration, profiles/goals/help/catalogue/media, Discovery, Requests, accepted chats and image/report flows, private feedback, lifecycle recovery and SSE change hints. The tested public boundary is88 paths at head49. [Progress](../docs/planning/progress.md) distinguishes the immutable bounded candidate, exact gate evidence and postcandidate work; [the staging handoff](../docs/planning/backend-student-staging-candidate.md) records runtime inputs and real-provider/first-boot dependencies. This does not claim a deployed or complete AI-enabled MVP. Authentication/media require explicit configuration; liveness is `/api/health`, DB connectivity readiness is `/api/ready`.

## Setup

Install uv, then run:

```bash
uv sync --locked
cp .env.example .env
make run
```

The application requires `DATABASE_URL=postgresql+asyncpg://...`; no SQLite fallback. Python is selected by `.python-version`. Settings are frozen and database credentials are redacted in representations.

## Local PostgreSQL and checks

From the repository root:

```bash
docker compose up -d --wait postgres postgres-test
```

Then from `backend`:

```bash
export TEST_DATABASE_URL=postgresql+asyncpg://studymate:studymate@localhost:5433/studymate_test
make check
```

Development data uses port 5432 and a named volume. Tests use a separate PostgreSQL instance on port 5433 with ephemeral storage, and each persistence test owns a unique schema. Tests refuse database names without `_test` and fail when the service is missing.

`make test-unit` does not need PostgreSQL. `make test-integration` needs the test instance. `make check` runs Ruff, format checking, strict mypy (including tests), import contracts, both test suites, and branch-aware coverage with a 95% floor. Coverage reports are local/CI artifacts. JUnit reporting uses the configured `legacy` family because controlled-load tests intentionally retain `record_property` metrics. Add `--junitxml=...` when an XML artifact is needed; no per-command family override or warning filter is required.

The initial tests exercise use-case outcomes, adapter failures, HTTP status mapping, actual application lifespan, PostgreSQL readiness, commit/rollback across sessions, and database uniqueness. They are foundation coverage, not evidence that the unimplemented pilot scenarios work.

## Migrations

```bash
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "Describe the schema change"
```

Six local revisions create identities/sessions, encrypted one-use OIDC transactions, institutional challenges and delivery outbox, genuine registration documents/receipts, callback attempt metadata and retained email execution origins. Review migrations before applying them; tests upgrade/downgrade only disposable schemas. Only persistence models use SQLAlchemy; domain entities and application results must remain independent and immutable.

The SQLAlchemy `run_sync` bridge is limited to Alembic and integration-test metadata setup; request persistence remains fully asynchronous. No table creation runs at app startup.

## Authentication configuration in progress

`AUTHENTICATION__CLIENT_ID`, `AUTHENTICATION__CLIENT_SECRET`, `AUTHENTICATION__PUBLIC_ORIGIN`, `AUTHENTICATION__ENVELOPE_KEY` and `AUTHENTICATION__BROWSER_SIGNING_KEY` and `AUTHENTICATION__CODE_KEY` configure this slice. Origin must be HTTPS without a path; register its `/api/v1/auth/google/callback` with Google. All three keys are distinct 32-byte hexadecimal secrets; no default keys, fake-provider fallback or real credentials are supplied. Partial configuration fails validation. Absent authentication configuration exposes only the health/readiness scaffold; it is not a deploy-ready product configuration.

Use `make run` (`uv run python -m studymate.server --reload`), which disables raw access logs because callback query strings contain authorization codes. The shared API/worker logging setup emits only source-allowlisted JSON and sanitized stack locations, using a bounded background stdout queue. Do not enable request-query/body logging for authentication. Google assertions are verified by maintained Authlib/JOSE libraries; controlled tests use signed synthetic tokens and mock external transport, never live Google. The async SMTP adapter and worker are locally verified with controlled external boundaries; real deliverability and safe operational instrumentation remain pending.

## Export the enabled authentication contract

From `backend/`, run:

```bash
uv run python -m studymate.export_openapi --output /tmp/studymate-auth-openapi.json
```

Omit `--output` for JSON on stdout. The command builds the actual enabled-auth app using synthetic configuration, bypasses `.env`, enters/closes its lifespan and never connects to PostgreSQL or Google. Unit checks prohibit those I/O boundaries and compare repeated exports for determinism. This exports implemented endpoints/DTOs, not the proposed social/AI API. Regenerate as the backend contract evolves; health-only default OpenAPI is insufficient for frontend integration.

The exported header models document `Idempotency-Key`, `X-CSRF-Token` and browser Origin, plus the Secure cookie security scheme and safe problem response. Registration completion/context receipts are implemented; they record actually displayed policy versions at the explicit action. There is no checkbox/analytics-choice contract or existing-user reacceptance gate. Fresh first boot still requires actual published policy content and a curated catalogue; the supported explicit-file provisioning CLI is a separately tested postcandidate supplement.

## Email worker sender and replies

`studymate.email_worker` reads `.env.worker` or injected environment. The dedicated [email-worker.env.example](email-worker.env.example) contains synthetic placeholders for its required settings. Copy it to the ignored `.env.worker` only for local configuration and replace placeholders using owner-managed values; this task does not send mail or configure a provider. The real `SMTP__SENDER` must be chosen and verified with the provider before delivery acceptance.

Optional `SMTP__REPLY_TO` sets one `Reply-To` email header for replies to the verification email. Use a bare ASCII mailbox with a DNS domain, such as the synthetic `support@example.test`; display names, address lists, whitespace and header injection are rejected. Leave it unset to omit the header. It does not change From, the SMTP envelope sender, the student recipient, SMTP credentials or the stable Message-ID. Choose the actual monitored support inbox separately; no real support address is hardcoded. Configuration validation performs no DNS or provider calls. Real sender verification, deliverability and inbox operation remain external checks.

## Google callback failure budget

`AUTHENTICATION__CALLBACK_FAILURES_PER_HOUR` is an optional positive limit (default 30, maximum 10000). Callback failures are independent of login-start quotas. Persist a source-digest-only reservation before validation/provider I/O; failed, cancelled and interrupted attempts keep it for the rolling hour. Successful callbacks release their slot in the same transaction that creates the session, retaining nonsecret attempt metadata linked to the authenticated account. The API returns safe 429/retry deadlines without contacting Google when exhausted. PostgreSQL serialises competing reservations; no transaction spans provider I/O.

Deploy behind an explicitly trusted reverse proxy so the application sees the actual source address; arbitrary forwarding headers are never trusted by application code. Tune source quotas and validate shared-campus-NAT behavior before pilot load acceptance. Do not interpret these source limits as per-account quotas or as evidence of tested 500-user capacity.

## Local diagnostics boundary

API attempts receive a server-generated `X-Request-ID`; handled problem responses use the same ID. Optional syntactically valid `X-Action-ID` is correlation only, never authorization or account identity. Client `X-Request-ID` does not override the server ID. Completion records include method, route template (unmatched routes use null), status and elapsed time; URL/query, route parameter values, cookies, bodies, arbitrary log messages/arguments and exception text are excluded. Context resets after cancellation and concurrent requests remain isolated. `trace_id` is present when the explicit OTel runtime is configured and null when it is disabled.

`studymate.server` and `studymate.email_worker` configure the same JSON formatter and uncaught-error boundary. Only already sanitized strings enter the bounded 1024-record queue. A blocked or broken stdout stream cannot hold request execution; overflow/output failures increment the handler's drop counter. Process shutdown gives the daemon writer a bounded half-second drain; this is not zero-loss delivery or archive acceptance. Manual HTTP/worker tracing, actor/action links, outcome metrics and persisted delivery causality are locally implemented; real remote collection/archiving and dashboard/alert validation remain external operational acceptance. Do not use raw uvicorn startup/logging defaults for deployment.

## Explicit OTLP runtime and email causality

Set `OBSERVABILITY__COLLECTOR_ORIGIN` to a private HTTP(S) collector origin without credentials/path, plus actual `OBSERVABILITY__ENVIRONMENT` and `OBSERVABILITY__RELEASE`, separately for API and worker. `OBSERVABILITY__TRACE_QUEUE_CAPACITY` defaults to 512 (validated 16–4096); batches contain at most 64 spans. Standard OTLP exporter configuration is deployment-owned; no collector/auth defaults or real endpoints are provided. With observability absent, logging and durable request/action links remain active while no remote exporter starts.

The API owns private OTel providers and does not replace global SDK providers. Automatic framework instrumentation stays disabled; only manual source-allowlisted spans/metrics export. Metrics contain bounded method/route/status or worker-outcome dimensions, never identity/resource IDs. Export runs in SDK background threads with a two-second network timeout; shutdown/flush runs off-loop. SDK warnings stay visible through sanitized `component=telemetry` logs. Overload can drop traces, so queue capacity is not a delivery guarantee. Collection/drop alerts and archive-before-hot-expiry acceptance remain required before pilot.

The outbox records initiating request/action/trace/span IDs at the actual enqueue transaction; existing unknown origins stay null. Each claimed worker attempt starts a separate consumer trace with a link to the origin, including trusted account/delivery IDs; retries do not overwrite the initiating context. Metadata survives secret-envelope cleanup. Idle polling creates no fictitious delivery span. Controlled PostgreSQL/SDK tests prove retry links, redaction, cancellation/context restoration and invalid-origin constraints. This does not prove actual collector delivery or university email arrival.

Source quota settings under `AUTHENTICATION__` include `GOOGLE_STARTS_PER_HOUR` (30), `CALLBACK_FAILURES_PER_HOUR` (30), `EMAIL_DELIVERIES_PER_ACCOUNT_HOUR` (5), `EMAIL_DELIVERIES_PER_ADDRESS_HOUR` (5) and `EMAIL_STARTS_PER_SOURCE_HOUR` (30). Values are positive and bounded; tune source quotas against actual campus NAT before pilot acceptance. These settings do not change the fixed OTP lifetime, resend minimum or wrong-attempt limit. Unexpected 500 responses also use safe correlated problem JSON; their existence is not converted into success or a swallowed programming error.

## Private photo worker (local implementation)

`make run-media-worker` runs `python -m studymate.media_worker` with bounded photo processing and transport cleanup. It reads `.env.media-worker` or injected environment, independently of Google/SMTP settings. Required fields are `DATABASE_URL`, `MEDIA__ENDPOINT_ORIGIN` (HTTPS origin), `MEDIA__BUCKET` (private DNS-compatible bucket), `MEDIA__REGION`, `MEDIA__ACCESS_KEY_ID` and `MEDIA__SECRET_ACCESS_KEY`. Use owner-managed secrets; no credential defaults or host AWS profile/credential fallback exists. Optional observability fields use the same `OBSERVABILITY__` contract. The API uses those same media field names; absent storage stays unavailable rather than silently producing a fake grant.

S3 metadata/SSL cache preparation runs off-loop. API lifespan owns its async client and storage binding; worker lifespan owns a separate client, two-connection PostgreSQL pool and one bounded codec thread. SDK automatic retries are disabled; durable attempts own retry decisions. SIGTERM/SIGINT cancels current I/O, leaves durable leases recoverable and closes resources. Native image work retains its slot until it actually finishes; process/container limits remain necessary and no hard thread-kill guarantee is claimed.

The enabled OpenAPI export includes media intents, grant/finalize/cancel/status and protected display. Exact JSON fields, immutable retry semantics, direct signed storage form and technical states are documented in `../docs/api.md`. Source limit is10,000,000 bytes; only actual nonanimated JPEG/PNG, at most24MP/8192-pixel edge. Display images contain fresh RGB pixels inside1024px with orientation normalized and private metadata removed. Original accepted images remain privately retained for authorized inspection.

Cleanup waits for signed access expiry and source-processing needs, retries temporary failures and only deletes transport keys. Retained original/display objects and SQL history are never cleanup targets. Real bucket privacy/CORS, conditional writes/range interoperability, backups, throughput and deployed worker/collector delivery remain external validation; local checked adapters are not evidence of a production rollout.

## Retained outcomes and media correlation

Migration0015 retains actual upload creation and finalization execution IDs separately. Photo processing and transport cleanup start new consumer spans linked to the retained finalization origin (creation is the fallback for unfinished uploads). Retries keep the original logical link and receive distinct attempt spans. Worker counters/histograms use only bounded worker/outcome dimensions; upload/account/attempt IDs belong to spans/logs, never metric labels. Slow controlled storage is tested without holding the upload status lock or API readiness.

Migration0016 adds canonical `product_events` for committed membership confirmation, initial profile readiness, goal save/completion and hide/restore. Their typed resource/version references and booleans contain no arbitrary content/payload field. Business writes and events commit or roll back together; original intent replays and no-op writes do not invent conversions. A missing historical trace stays missing; migrations do not fabricate old events or links. These records are retained application truth for later analytics delivery/inspection; Umami forwarding, dashboards, archive and real collector acceptance are still separate work.

Migration0017 registers the separately implemented AI job/intent/budget/singleton/attempt schema, including its seeded singleton and owned deferred lease constraint. Schema availability does not enable a real executor or public AI routes. No developer authentication, live Codex inference or production credentials are needed by local migrations/tests.

## Discovery exposure source facts

Migration0019 adds versioned freshness policy and owned exposure-source records plus genuine confirmation fields on visibility intents. The initial inactivity default is30 days. This is separate from hidden/ban/deletion and does not deny existing chats or otherwise eligible outgoing contact. Current published policy is applied to new foreground source observations; existing source intervals are retained so configuration or the first return cannot erase an expired pause.

Background HTTP reads do not warm activity. Actual user command writes and Google session issuance do; they preserve a crossed pause before advancing activity. `GET /me/onboarding.discovery_exposure` is the minimal paused/can-confirm/requirements projection. Explicit `PUT /me/visibility` with hidden:false rechecks readiness and records real return confirmation; an already-visible profile keeps its visibility revision and emits only the truthful exposure-confirmation event. Original intent replay cannot reconfirm a later pause. No countdown, new lifecycle mode, fake history or automatic Google-return restoration exists.

## Requests maintenance worker (locally verified)

`make run-requests-worker` runs `python -m studymate.requests_worker`. It reads `.env.requests-worker` or injected environment. Only `DATABASE_URL` is required; optional observability uses the existing `OBSERVABILITY__COLLECTOR_ORIGIN`, `OBSERVABILITY__ENVIRONMENT`, `OBSERVABILITY__RELEASE` and bounded trace queue contract. No Google, email, S3 or AI credentials are loaded by worker settings. Real deployment remains separately authorised.

The worker uses a dedicated one-connection asyncpg pool, no overflow, a two-second pool wait and five-second connect timeout. One actual expiry batch (max100) executes at a time. Empty polling waits1second; a storage outage waits5seconds; SIGINT/SIGTERM interrupts waits and cancels/awaits current work before engine/telemetry shutdown. Unexpected programming/constraint failures propagate; they are not treated as successful processing. API reads/writes already use effective deadlines and do not depend on a running worker to extend Undo or keep expired requests actionable.

Finalizations retain actual request/revision/canonical source, use original expiry/decline deadline, have SYSTEM initiation and never warm either participant. Fixed-dimension counters/histogram report batches/outcomes/finalized states; spans contain safe request IDs only, logs contain no source text or exception values, and idle polling invents no work span. Actual collector/archive/alerts and production worker supervision remain release checks. Controlled SDK/unit tests plus a real PostgreSQL one-connection/10-second finalization test pass; this is local implementation evidence, not deployment.

### Transport maintenance worker

`make run-changes-worker` starts the separately composed publication/retention process. Its frozen `ChangesWorkerSettings` reads `.env.changes-worker`: only `DATABASE_URL` and optional existing `OBSERVABILITY` settings are needed; no Google, email, S3 or AI credentials. Keep that local environment file outside Git.

A single bounded SQL connection serves serial publication batches and bounded transport-prefix cleanup; API/core and AI engines are independent. SIGINT/SIGTERM cancel and await in-flight transactions, and unexpected invariant failures terminate the worker for supervisor handling. Metrics use fixed maintenance/outcome dimensions; ordinary logs never contain business payloads. Only the24-hour transport journal expires: canonical outcomes, business history and deduplication markers remain retained.

This entrypoint is locally tested; no process was deployed or started against external infrastructure. The SSE HTTP factory is not yet mounted in the root API, so running maintenance alone does not claim live client delivery.

## Dedicated AI worker candidate

`make run-ai-worker` starts the explicitly configured singleton worker. It reads process environment only; `.env.ai-worker.example` documents inputs. Configuration is not an enablement grant: the accepted artifact, native pin/policy, private credential codec and runtime readiness must validate. Admission derives actual availability from the fresh singleton fact; there is no user-facing environment enable switch. Read [runtime readiness](../docs/planning/ai-runtime-readiness.md) and [staging configuration](../deployment/backend/AI_RUNTIME.md). The code candidate and container configuration remain unaccepted until the final frozen proof/gate batch; do not authenticate or infer from this run command alone.
