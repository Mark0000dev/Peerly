# Pilot API design

## Knowledge-area semantics (approved 9 November 2026)

The MVP catalogue contains broad knowledge areas, not APU course enrolments or completed modules. Existing `subject`, `subject_id` and `help_subjects` names are stable wire/storage names for these areas. Selecting “can help” is self-declared; institutional email verification establishes membership, never expertise, course completion or grades.

A goal uses its chosen area plus optional `topic` (80 characters) and `context` (240 characters). A helper may select up to five canonical areas, each with an optional `topic_note` (80 characters). For example, choose Databases and describe SQL joins in the topic/note; IDB, SSCC or BMK2 may appear as optional task/module context. Helpers with workplace knowledge and students from other courses remain eligible under the same existing account/source/pair guards.

Discovery matches equal canonical area IDs. Different topics or module contexts do not prevent an area match; the literal same-topic hint does not certify competence. Different area IDs and free-form custom labels never become equal through matching text or AI advice. Custom goals remain supported but have no exact canonical match until explicitly changed by their owner. Aliases are true equivalent labels only, not course-to-area or technology-to-area mappings. Future course mappings/AI suggestions are advisory, never permission or verified qualification. No taxonomy graph, multi-tag expansion, API rename or migration is introduced.

Status: incremental REST/stream contract for the current APU pilot. Health/readiness and the Google/session/institutional-verification slice are implemented locally with controlled external-provider tests; explicit registration completion is also implemented locally, while remaining product endpoints below are proposed. Export the actual enabled-auth schema with `uv run python -m studymate.export_openapi` from `backend/`. This replaces the old groups/sessions/percentage-matching API design; the external specification remains unchanged.

## Conventions

- Product base path `/api/v1`; JSON and opaque UUID resource IDs, UTC RFC3339 timestamps, explicit enum values. Operational health paths stay unchanged.
- Resolve the actor from the authenticated session, never `user_id`/`evaluator_id` supplied as authority in a command. Every resource read and command checks its actual owner/pair/visibility permissions.
- Cursor pagination with bounded `limit`, stable ordering and `next_cursor`; do not expose arbitrary SQL ordering or use client-computed totals.
- OpenAPI-derived readonly TypeScript contracts; shared validation messages use stable codes, not translated server prose or raw exception text. Extra request fields are rejected.
- Versioned resources expose an integer `version` and ETag. Edits use `If-Match`; command snapshots carry their referenced goal version. Reject stale state explicitly and return the safe current representation needed for recovery.
- Consequential POST commands carry `Idempotency-Key`. A logical intent retains the key across an uncertain retry. New intent uses a new key. The server persists payload fingerprints/results and rejects key reuse with different input. Response-body pruning must not discard the durable command identity/result resource reference. Expired retry windows never silently create another social action: check the durable operation/message identity first.
- `traceparent` links request spans; `X-Action-Id` links attempts to the same UI intent. The API returns its server-generated request ID and trace ID. Client-supplied correlation is validated metadata, not a user identity or permission.
- Standard HTTP results: 201 created, 202 queued/processing, 204 no body, 401 unauthenticated, 403 explicitly denied, 404 unavailable/not visible, 409 state/idempotency conflict, 412 stale edit version, 422 invalid fields, 429 rate limit with Retry-After. Neutral unavailability must not reveal that another person blocked/hid/restricted their account.

Error envelope (`application/problem+json`):

```json
{
  "type": "about:blank",
  "title": "Request context changed",
  "status": 409,
  "code": "goal_version_changed",
  "request_id": "opaque-request-id",
  "trace_id": "otel-trace-id",
  "errors": []
}
```

Field errors contain field paths and stable correction codes; no submitted private values. Only operation-specific safe recovery data may be added. HTTP errors do not carry stack traces, SQL or other users' hidden state.

## Read models

Expose typed resource state plus explicit capabilities. Examples: `can_review_request`, `can_accept`, `can_message`, `can_restore`, `reason_code`, `version`, `pending_limit`, `daily_remaining`, `retry_after`. Do not send a configurable UI tree, layout description, opaque match percentage or an executable policy to Angular.

The server owns countdown deadlines and eligibility. The client may display time until a supplied deadline, but it does not grant eligibility when a timer ends. A capability can become stale before a click; commands always revalidate.

## Identity, registration and profile

| Method  | Path under `/api/v1`                           | Purpose                                                                                            |
| ------- | ---------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| POST    | `/auth/email-challenges`                       | Authenticated institutional-verification challenge; actor-bound, enumeration-safe and rate-limited |
| POST    | `/auth/email-challenges/{challenge_id}/verify` | Verify institutional mailbox for current Google-authenticated account; does not create a session   |
| GET     | `/me`                                          | Private account bootstrap, onboarding state, analytics ID, registration receipt and capabilities   |
| POST    | `/auth/logout`                                 | Revoke current session and clear browser cookie                                                    |
| GET/PUT | `/me/profile`                                  | Read/edit own profile; required photo enforced before exposure                                     |
| GET/PUT | `/me/goal`                                     | Read/save the active goal; preserve stable identity and increment version                          |
| POST    | `/me/goal/complete`                            | Complete goal without rewriting prior snapshots                                                    |
| GET/PUT | `/me/help-subjects`                            | Canonical help subjects, with the configured maximum                                               |
| GET     | `/subjects?query=...`                          | Catalogue search; custom subject route has explicit non-exact relevance                            |
| PUT     | `/me/visibility`                               | Hide/restore; returns actual status and effects, never an optimistic client-only toggle            |
| PUT     | `/me/notification-preference`                  | `messages_and_requests` or explicit `all_updates`; distinct from OS permission                     |
| GET     | `/me/policy-status`                            | Actual registration versions and informational update notices; no analytics choice                 |
| GET     | `/people/{id}`                                 | Eligible public profile only, with relationship-dependent actions                                  |

Code and session credentials are never query parameters. Browser sessions use Secure HttpOnly host-only cookies with CSRF/origin protections. Native credentials reuse the same business use cases through a separately specified secure client adapter. Privacy notice versions and service terms versions are separate records.

## Discovery and requests

| Method | Path                                    | Purpose                                                                                             |
| ------ | --------------------------------------- | --------------------------------------------------------------------------------------------------- |
| GET    | `/discovery?mode=...&cursor=...`        | `find_help`, `offer_help`, `study_together`; eligibility and grounded reasons                       |
| POST   | `/discovery/passes`                     | Persist a private pass scoped to the relevant goal/context                                          |
| GET    | `/discovery/passes`                     | Review passed profiles for that context                                                             |
| DELETE | `/discovery/passes/{id}`                | Explicitly reconsider/undo eligible pass                                                            |
| GET    | `/people/{id}/request-preview?mode=...` | Exact proposed recipient/type/goal-version context and current send capability; no send side effect |
| POST   | `/requests`                             | Send the reviewed context with recipient, type, goal reference/version and optional note            |
| GET    | `/requests?direction=received           | sent&cursor=...`                                                                                    | Pending/accepted/history; safe per-user closed reason |
| GET    | `/requests/{id}`                        | Actual snapshot, state, applicable expiry/cooldown and actions                                      |
| PUT    | `/requests/{id}/viewed`                 | Mark received item viewed; does not accept                                                          |
| POST   | `/requests/{id}/accept`                 | Establish one connection/thread; no mandatory reply                                                 |
| POST   | `/requests/{id}/accept-and-send`        | Accept plus one explicitly reviewed human response with stable message ID                           |
| POST   | `/requests/{id}/decline`                | Close incoming request                                                                              |
| POST   | `/requests/{id}/withdraw`               | Close outgoing request without undoing daily send count                                             |

A positive swipe only opens a preview. It never sends, creates a hidden like, or accepts incoming interest. Server-side pending/daily limits, expiry and cooldowns use the specification's configurable pilot defaults. Display the backend's actual values.

The server snapshots the reviewed goal when committing a request. Same/opposite simultaneous sends resolve against the unique pair. Existing incoming interest returns an explicit `incoming_request_exists` recovery with the visible request; existing connection returns its thread. Neither response authorizes an automatic acceptance. A changed goal produces `goal_version_changed`; closing the refreshed preview sends nothing.

`accept-and-send` needs a durable result that distinguishes accepted connection from message delivery. Prefer one transaction for connection plus stored message. If later external attachment processing or delivery fails, return/open the established thread with that same failed message ID; retry the message, not acceptance. Automated system context is not a human message.

## Conversations, outcomes and feedback

| Method | Path                                      | Purpose                                                                               |
| ------ | ----------------------------------------- | ------------------------------------------------------------------------------------- |
| GET    | `/conversations?cursor=...`               | Accepted threads; subject context, latest human activity, unread counts               |
| GET    | `/conversations/{id}`                     | Request context, availability/capabilities and metadata                               |
| GET    | `/conversations/{id}/messages?cursor=...` | Cursor-paginated authorized history                                                   |
| POST   | `/conversations/{id}/messages`            | Text/link or processed-image reference, stable client message ID and idempotency key  |
| PUT    | `/conversations/{id}/read-position`       | Monotonic server message position for own unread state; no public read receipt        |
| POST   | `/conversations/{id}/goal-shares`         | Explicitly share the current goal, never overwrite pinned context silently            |
| PUT    | `/conversations/{id}/study-outcome`       | Own latest `yes`, `not_yet`, `did_not_work_out` report                                |
| PUT    | `/people/{id}/feedback`                   | Own current structured assessment; server checks prior eligible interaction           |
| GET    | `/people/{id}/feedback-summary`           | Thresholded distinct-partner summary, including all response categories               |
| POST   | `/media/uploads`                          | Create an owned bounded photo intent (JSON metadata); 202 is not proof of file upload |
| GET    | `/media/{id}`                             | Authorized status/read access; do not expose raw object-store keys                    |

Canonical ordering of messages comes from a committed per-conversation sequence, not a device clock or UUID. `client_message_id` is unique per sender/thread, so retries cannot duplicate a message even after a transient idempotency response cache expires. Message acknowledgements mean stored/sent, not delivered/read/studied.

The server checks live accepted-participant and unblocked contact authority on every new message; hidden/freshness-paused visibility alone does not restrict existing chats. Read-only history and previously eligible feedback/reporting remain available according to the specification. A profile's disappearance does not erase stored chat text. Live clients invalidate affected caches immediately; stale clients still cannot write.

## Safety, support and privileged inspection

| Method    | Path                                        | Purpose                                                          |
| --------- | ------------------------------------------- | ---------------------------------------------------------------- |
| GET/PUT   | `/me/blocks[/{person_id}]`                  | Own block management; no resurrection of old requests            |
| POST      | `/reports`                                  | Selected target/evidence and optional private note               |
| POST      | `/support-cases`                            | Access/support request; does not bypass university confirmation  |
| GET/PATCH | `/operator/cases[/{id}]`                    | Internal support/moderation workflow                             |
| GET       | `/operator/accounts?query=...`              | Privileged account search, including approved identity fields    |
| GET       | `/operator/accounts/{id}`                   | Full account data and links to related records                   |
| GET       | `/operator/conversations/{id}/messages`     | Full stored conversation, including historical/unavailable state |
| GET       | `/operator/resources/{type}/{id}/relations` | Typed, bounded, paginated edges across application records       |
| GET       | `/operator/media/{id}`                      | Privileged file inspection through controlled media access       |
| GET       | `/operator/actions/{id}`                    | Action attempts, canonical outcomes and telemetry links          |
| GET       | `/operator/audit-events`                    | Inspection/change audit                                          |

`operator` routes require a privileged operator account. They can inspect all application records/relationships, without requiring a related support case. This does not give product users these endpoints or expose them through public profile APIs. Ordinary moderation permissions remain separate from exhaustive inspection. All developers may view internal Grafana; this is not an additional Grafana restriction.

A graph is an application read model with known entity/edge types, not an arbitrary SQL endpoint. Inspecting data records an audit event with operator/target/trace, without logging the content. Business-data access returns data from PostgreSQL/object storage; telemetry contains navigable IDs, not copies of conversations.

## SSE protocol

`GET /api/v1/events`, authenticated, `text/event-stream`:

```text
id: 143
event: resource.changed
data: {"resource_type":"conversation","resource_id":"opaque-id","version":null}
```

IDs are ordered per recipient; payloads never contain message bodies, email or moderation evidence. Actual event variants are a typed allowlist, including unread/visibility changes and `reset_required`.

The client sends `Last-Event-ID` on resume; an initial connection establishes a current cursor with a full query refresh. Catch-up and live delivery use the same durable journal. When the cursor falls outside retention, the server emits a current reset cursor and the client refetches all active account queries. Do not advance the applied cursor ahead of successfully handled events.

Initial transport defaults to validate: 15-second heartbeat, bounded queues, 24-hour journal retention, periodic database reconciliation. A reset handles longer absences; it does not replay social commands. On logout/revocation, stop the stream and clear private caches. Recheck session validity during long connections; no stream holds a request transaction or pool connection for its whole lifetime.

### Mounted SSE implementation — actual64

`GET /api/v1/events` was first mounted at head0040 and remains mounted in the enabled-auth application at head0042. It requires the actual live verified, activated, nonbanned/nondeleted session cookie. It does not create a session, acknowledge viewing or confirm profile exposure. Before headers, invalid Last-Event-ID yields422 `invalid_change_cursor`; failed authority yields401/403; unavailable bounded SQL capacity yields503 `storage_unavailable` with Retry-After1. Last-Event-ID must be a canonical ASCII decimal string in0..9223372036854775807, with no signs, whitespace or leading zeroes except0. Preserve the SSE id as a string in browser code.

The only emitted events are `resource.changed` with JSON `{resource_type,resource_id,version}` and `reset_required` with `{}`; heartbeat is the comment `: heartbeat`. Resource types are exactly `account`, `request`, `conversation`, `ai_job`; IDs are owned opaque UUIDs and version is an actual positive source version or null. This invalidates guarded REST queries; it is not a business outcome, message body, peer read receipt or permission grant. Initial/future/expired cursors reset to the actual current head and require a full refresh of active owned queries. A resumed valid cursor returns retained contiguous recipient hints. Internal report-triage and operator inspection never emit student hints.

The read pool is independent of core/AI:2 connections, zero overflow,0.25-second acquisition/2-second connect bounds and a2-second total read transaction deadline. The separate publisher/retention worker has1 connection; no SQL lease spans network sending. Poll1s, heartbeat15s and individual ASGI send timeout5s are the implemented defaults. A stalled real socket is closed without pretending a complete HTTP body; Uvicorn emits its fixed incomplete-response diagnostic without private exception content. Session revocation/storage unavailability after committed headers closes the stream without a JSON error body or fake cursor progress. The separate changes worker must run for live journal publication; application construction does not start it or open idle SQL connections. Local source/ASGI/TCP/pool tests do not establish managed load, proxy/native reconnect or deployment acceptance.

## Client telemetry ingress

`POST /api/v1/telemetry/events` accepts bounded batches of versioned allowlisted UI/RUM event schemas. Server assigns receipt time and authenticated actor/analytics identity. Unique event IDs deduplicate retries. Client events remain explicitly client-observed and cannot claim that a request was accepted or a message stored.

Tracing export uses a separately bounded same-origin ingress to the local collector, with origin/auth/rate controls and attribute filtering; internal exporter credentials are never shipped in JavaScript. Exact SDK/export protocol is selected during instrumentation. No arbitrary request/response bodies, DOM snapshots or private text are accepted as event properties.

## Contract verification

Unit tests cover state transitions and error mapping. PostgreSQL integration tests cover authorization, constraints, transactions, idempotency and races. API tests verify schemas, cursors, neutral unavailable responses, session/CSRF behavior and generated-client drift.

Two-account full-stack tests must verify REST plus SSE/reconnect/refetch behavior. Playwright screenshot scenarios cover every implemented screen/state, including loading, failures, stale previews, permission changes and ambiguous retries. Deterministic boundary-mocked visual tests complement these full-stack checks rather than replacing them.

## AI jobs — implemented HTTP, disabled execution

The enabled-auth application exposes `POST /api/v1/ai/jobs`, `GET /api/v1/ai/jobs/{job_id}` and `POST /api/v1/ai/jobs/{job_id}/cancel`. Current composition keeps submission hard-disabled: a valid session, trusted Origin/CSRF and actual verified live student are checked before503 `ai_unavailable` with safe Retry-After; no job is admitted. There is no executor-enable setting or fake ready provider. Read/cancel remain available for the live verified owner independently; unknown/foreign/internal jobs return404 `ai_job_unavailable`. These student endpoints do not grant operator access. Real executor credential compatibility and model-tool secret isolation remain unvalidated release dependencies.

Create requires immutable Idempotency-Key and strict task discriminator `clarify_goal`, `suggest_subject` or `assess_photo`. Source must be tagged resource{id,version} or draft{id,version}; photo accepts only an owned READY resource. Explicit unsaved draft input is retained privately without saving/publishing a goal; its hash is computed by the server and returned for stale-result matching. No client hash, arbitrary prompt, system instruction, model/configuration, URL/path or student triage input is accepted. Clarification explicitly targets context<=240 or topic<=80; subject suggestions accept1..20 distinct known candidate IDs and require a label<=80 only for drafts. Actual OpenAPI is authoritative for the frozen discriminated request/result shapes.

When admission is explicitly composed with a controlled test executor, accepted durable intents return202 with Location, source/state/deadline and bounded polling hint. Production composition never takes that path yet. Quota429, source409 and bounded capacity/circuit/SQL-deadline503 are safe and content-free. Create JSON is bounded8192 bytes/5 seconds; cancel requires an empty body and is intrinsically idempotent by owned job/state, without an unused idempotency header. All responses are no-store and preserve server request/trace correlation. Responses exclude retained input text, storage capabilities, attempts, leases and executor configuration. Applying advice remains a separate ordinary goal edit using current goal identity/version; draft revision is not a goal version. No AI SSE delivery is currently implemented. See [AI contract](ai.md) and [execution evidence](planning/ai-progress.md).

BE-01 identity implementation defaults and verification requirements are detailed in the [first backend epic](planning/epic-be-01-identity.md); reconcile its concrete request/receipt schemas here as implemented.

## Google login and membership separation

Owner decision: Google OIDC authenticates users, and an actor-bound email code verifies `mail.apu.edu.my` membership separately. `GET /auth/google/start` and `GET /auth/google/callback` implement browser-bound authorization-code login with state/nonce/PKCE. Unverified sessions can only access bootstrap, institutional verification, applicable policy preferences and logout. Email verification is not a login endpoint. Persist external issuer/sub; never auto-link identities by email. Detailed contracts/tests are authoritative in the [revised BE-01 epic](planning/epic-be-01-identity.md) and must be reflected in OpenAPI as implemented.

### Concrete browser login transaction (BE-01 implementation contract)

`GET /api/v1/auth/google/start?return_to=/onboarding` accepts only the local routes `/` and `/onboarding` initially (default `/onboarding`). Other paths, absolute/network-path URLs, query strings and fragments are rejected. It creates a five-minute server-side transaction containing digests of random state/browser binding, encrypted nonce/PKCE material and the selected route. The short-lived browser-binding cookie is Secure, HttpOnly, host-only, SameSite=Lax and Path=/ (`__Host-studymate_login`). A subsequent start replaces that browser's active flow. Only `openid email profile` is requested, with S256; no offline access or university Google-domain restriction.

The callback accepts one bounded state and either code or provider cancellation, requires the browser cookie and atomically consumes the unexpired transaction before contacting Google. Invalid/missing/replayed state or wrong browser never creates a session. Discovery, token and JWKS endpoints are fixed trusted Google endpoints; metadata cannot redirect fetches to another host. Provider timeout/rejection consumes the flow and requires a fresh start. The application does not retry the single-use token exchange automatically. A callback retry after a lost response likewise requires a new flow; no credential replay envelope is promised.

After validated issuer/signature/audience/authorised-party/expiry/nonce, resolve issuer/sub and create one hashed-token application session atomically. Mark the login transaction completed in that same transaction. Replace/revoke the previous application session presented by this browser, without carrying its membership into a different Google identity. Set `__Host-studymate_session` (Secure, HttpOnly, SameSite=Lax, Path=/, seven days fixed) and delete the login cookie; redirect only to the stored local route. Raw Google errors and application session secrets never appear in response JSON or redirect query strings. Infrastructure must suppress raw callback query access logs.

The implementation is incremental: these are the target boundary contracts, not a claim that the endpoints are already wired. Native exchange, recovery/linking and additional return routes remain outside this epic.

## Approved lifecycle and policy update

[Approved decisions](planning/product-decisions-v1.md) supersede old optional preference/consent descriptions. Remove any optional analytics write endpoint from the implemented contract. Use read-only versioned Terms/Privacy documents, authentic registration receipt binding and informational update notices; no reacceptance or opt-out UI.

Implemented deletion uses `POST /me/deletion-workflows`, `POST /me/deletion` and separate-cookie `GET /me/deletion-status` under the actual session policy described below; no provider MFA or fresh authentication is inferred. Commit lifecycle flag/session revocation/pending-contact closure/audit+analytics and delivery intent changes atomically. Clear cookie; return stable confirmed outcome, handle uncertain result without saying deletion failed. Reauthentication never recreates a deleted identity. Operator inspection retains all underlying data. Existing peer history uses Deleted account, neutral avatar and disabled new contact. Ban uses distinct explicit audited administrator command. Hidden users retain accepted-chat read/send capabilities. Detailed transaction and worker cleanup is part of BE-07; BE-01 must already deny deleted identity authentication.

Decline transitions use a 10-second `undo_until`; pending decline occupies pair uniqueness, and commands resolve effective expiry using database time. Operator search supports account/resource/participant/correlation identifiers plus lifecycle/time filters with cursor pagination.

### Explicit registration context (BE-01 local implementation)

Google identification and institutional verification do not themselves record application registration under Terms/Privacy. `POST /me/registration-context` prepares a ten-minute, account/session-bound one-use context containing the published Terms/Privacy versions and the compact inline wording for the ordinary final registration action. It requires the authenticated verified account, approved Origin, CSRF and an idempotency key. It introduces no separate legal screen or checkbox. The first-party UI renders the returned wording/links before enabling that normal completion action; rendering is verified by its integration scenarios, never represented as proof that a human read a document.

`POST /me/registration` receives only that context ID at the explicit completion action. The server records its actual issued versions/wording/context, completion time and operation identity once. No context is fabricated in Google callbacks, no optional analytics flag exists, and registration never records a checked checkbox or document-reading claim. Technical account creation before registration is not product activation. Completion now atomically requires a saved display name, a READY current photo and the context required by the chosen initial task (active goal for find-help; at least one help subject for offer-help). Incomplete setup returns409 `onboarding_incomplete` with `errors[].path=["onboarding", requirement]` and `code="required"`; both receipt and context completion roll back. The same intent/context may be retried once actual prerequisites are saved, subject to its original expiry. Invalid or foreign contexts remain `registration_context_unavailable`, evaluated before profile requirements. A returning activated account does not need another context; retries return the existing receipt without changing original versions. A pre-existing genuine receipt without an activation marker can finish actual setup explicitly using that original receipt; this does not fabricate new notice versions or require reacceptance.

A valid issued context binds the versions actually presented, even if another version is published while the form is open. Later document changes are informational updates, not reacceptance or grace gates. Context expiry only refreshes the technical form context; it is not a legal reacceptance policy. Published document content/versions are operator input; missing documents yield an explicit unavailable result rather than invented production text. Controlled tests use clearly synthetic documents.

`GET /policies/{kind}` reads an actually published `terms` or `privacy` document, optionally by version. `GET /me/policy-status` returns the original registration receipt/version context and current publication references; it offers no choice/write/opt-out endpoint. Soft deletion retains these records. This slice is implemented locally with controlled tests; consult the exported schema for exact DTOs. Genuine published documents remain deployment inputs.

### Institutional challenge resume/status

`GET /auth/email-challenges/{challenge_id}` returns status only to the original authenticated account and session; other actors/sessions receive the same unavailable response as unknown IDs. `/me.email_challenge_id` identifies an outstanding challenge for that session, allowing reload recovery without browser persistence of codes or emails. Successful membership verification removes that reference. An unverified account retains its latest original-session challenge reference after a `support_required` result, so reloading preserves the neutral support recovery outcome.

The read model exposes challenge state, remaining attempts, effective resend deadline/capabilities, a terminal verification outcome when present, and delivery state (`queued`, `sending`, `sent`, `failed`, `cancelled`). `sent` means provider/SMTP acceptance, never proof of inbox arrival. Failed delivery does not invalidate a still-active code: an ambiguous provider outcome can still result in delivery. All responses use no-store; neither OTP hashes nor encrypted delivery envelopes are exposed. The schema exporter includes these additions; regenerate generated clients.

### Google callback failure admission

All callbacks, including malformed input without a valid browser cookie, enter a persistent source-based failure budget before login validation or provider I/O. Failed/cancelled/interrupted attempts retain a slot for the rolling hour; successful login atomically records its authenticated account and releases the slot with session creation. This budget is independent of login-start and institutional-email quotas. Exhaustion returns `429 login_rate_limited`, `Retry-After` seconds and `recovery.retry_at`; it never invokes the provider or fabricates a session. The validated deployment setting `AUTHENTICATION__CALLBACK_FAILURES_PER_HOUR` defaults to 30. Source quotas require explicit proxy configuration and shared-campus tuning before pilot acceptance.

### Implemented request correlation

The API assigns a fresh UUID for each HTTP attempt and returns it as `X-Request-ID`; handled problem bodies use that same value. A client-supplied request ID is not trusted as the server identity. Optional `X-Action-ID` accepts exactly one bounded UUID header for logical-action correlation; invalid/duplicate values are ignored and never become actor identity. The middleware records the matched route template only, with null for unmatched paths, and excludes actual query/path-parameter values, bodies and cookies. Concurrent request/cancellation contexts are isolated. `trace_id` is set by the explicit configured OTel runtime; it stays null when that runtime is disabled.

### Browser callback recovery (implemented locally)

A top-level navigation with `Accept: text/html` receives `303` on expected callback failures to the fixed configured public origin plus `/onboarding?auth_error=<code>&auth_ref=<UUID>`. Codes are `login_invalid`, `login_cancelled`, `login_provider_unavailable`, `login_rate_limited`, `account_unavailable` and `request_context_invalid`. The server-generated reference equals `X-Request-ID`; it grants no access to status, sessions or account data. `login_cancelled` requires a valid browser/state flow consumed with provider `access_denied`; forged, expired or replayed cancellation is `login_invalid`.

The redirect retains `Cache-Control: no-store`, `Referrer-Policy: no-referrer`, `Retry-After` when applicable, and `X-Auth-Error-Status` containing the original problem status. The temporary login cookie is cleared. It never echoes provider text, code, state, return query or session secret. Success continues to use the stored allowlisted route without outcome query. Clients without explicit HTML acceptance keep the existing problem JSON/status. Unexpected server failures and infrastructure-wide errors remain correlated server errors rather than being disguised as cancellation. The UI treats query values as untrusted presentation hints, uses a fixed code allowlist and removes them from browser history after consumption; it must not submit the reference as authentication or infer successful login from it. No new UI route or retry of the used authorization code is introduced.

### Private photo upload HTTP contract (BE02 incremental implementation)

Enabled-auth OpenAPI now includes these six paths; use the deterministic exporter rather than duplicating DTOs. This slice does not yet activate an account or finish profile/onboarding. The real external bucket/worker deployment remains unverified.

1. `POST /media/uploads` with Origin, CSRF and Idempotency-Key accepts `size_bytes` (1–10,000,000), lowercase SHA256 hex of the exact chosen JPEG/PNG bytes, `content_type` and `expected_photo_version`. It returns202 plus an owned upload ID/revision/state and deadlines. File conversion/crop must finish before calculating this immutable payload. Repeating the original key/payload returns the original accepted result; changing it conflicts. Creating an intent does not transfer or technically accept a file.
2. `POST /media/uploads/{id}/access` requires Origin/CSRF but no operation key. It returns a sensitive URL/form-fields pair for an exact-key, content-type/size-bounded signed POST to private storage. It works only while the original owned intent is uploading. Each ticket remains bounded by the original upload deadline and at most15 minutes; reissuing one never renews the intent. Send the returned fields and chosen file directly to that URL as the provider form requires. Never log/cache/persist the access response in ordinary analytics.
3. After storage accepts the transfer, `POST /media/uploads/{id}/finalize` with Origin/CSRF/Idempotency-Key queues durable technical processing and returns202 metadata. The worker verifies actual bytes/size/SHA256/format, decodes off-loop within limits, retains the original privately and creates a metadata-free display JPEG. It publishes only if the original photo version and current processing generation still match. AI is not a gate and no identity/face verification is claimed.
4. `GET /media/{id}` returns only the current owned upload status. Pending responses include a server poll hint. READY includes the same-origin authenticated `display_url`; it exposes no retained object-store key. `GET /media/{id}/display` serves that owner's ready JPEG with private/no-store/nosniff headers. Existing ready history remains available to its owner. Foreign/missing IDs are neutral404; lifecycle/membership still apply.
5. `POST /media/uploads/{id}/cancel` with Origin/CSRF/Idempotency-Key returns the committed outcome. READY stays READY: cancellation cannot undo a publication that already won. Pending cancellation prevents a late worker from publishing, even if private output copies finish. Replays return their original operation snapshot; always reload current status when resolving an uncertain response. A changed file or new expected-photo revision is a new intent only after the prior outcome is resolved.

Photo intent quotas are3 pending and20 starts per rolling account hour; replay spends no capacity. A conflicting current photo returns409 `photo_version_conflict` with owned `current_version`. Changed key/payload returns409 `idempotency_conflict`. Access to a nonuploading intent returns409 `upload_not_uploading` and must be resolved through owned status, without guessing whether it expired or finished. Provider ticket expiry returns409 `upload_expired`. Storage absence/failure is safe503 `media_storage_unavailable`, never fake file success. Technical failure uses the generated PhotoFailure enum in status. All JSON commands have bounded bodies; action/access endpoints take no JSON body. Private display bytes and signed fields never enter ordinary telemetry.

Temporary transport cleanup is durable and generation-checked. It waits until signed access has expired and processing no longer needs the source. Failures retry with bounded backoff. Only transport objects are deleted; retained originals/display/history survive replacement and account soft deletion. No zero-loss/provider-compatibility/deployment claim is implied by local controlled tests.

### Onboarding readiness and visibility (BE-02 local implementation)

`GET /me/onboarding` requires a live verified student. It returns `registered`, `setup_complete`, `setup_requirements`, `restore_requirements`, operation-specific `capabilities` and nullable `visibility`; profile, media and study content remain in their existing resource queries. Requirement values are `display_name`, `photo`, `study_goal`, `help_subjects`; restore requirements are `photo`, `study_context`. These are server facts, not a configurable UI tree or a server-chosen next screen. All responses are private/no-store. `/me.capabilities.can_use_student_features` now follows the durable activation marker; a receipt or photo alone cannot turn it on.

`visibility` has `version`, `hidden`, `completed_at`, `hidden_at`, `changed_at`. `PUT /me/visibility` requires Origin, CSRF and an idempotency key, with strict JSON `{ "hidden": true, "expected_version": 1 }`. Only activated students may change visibility. Successful requests return the actual immutable visibility revision. Identical intent retries return that original result even after later changes; reload onboarding status to get current state. A no-op does not invent a revision. A changed payload under the same key conflicts; stale expected versions return409 `visibility_version_conflict` with `recovery.current_version`.

Hidden stops discovery/new contact while preserving initial completion, private editing and existing-chat capability. Explicit restore requires a current READY photo and either an active goal or help selection, independently of the initial task. Missing requirements return409 `profile_restore_incomplete` with `errors[].path=["restore", requirement]` and `code="required"`; visibility remains hidden. Later loss/completion of context does not erase activation or revoke existing-chat capability. Ban, deletion and revoked membership still deny ordinary student actions. Request closing on hide will be integrated atomically with the real request model in BE-05; no pending-request effects are claimed by this profile-only slice. Restore never reopens requests.

After activation, clearing the display name returns422 `profile_name_required` (`errors[].path=["display_name"]`, `code="required"`). Drafts may still lack a name. This preserves completed-profile invariants without introducing optional-field signup gates.

### Discovery exposure freshness (BE-04 incremental implementation)

`GET /me/onboarding` now includes nullable `discovery_exposure` with `paused`, `can_confirm` and `requirements` (`photo`/`study_context`). It is null before genuine activation. The source default is30 days of inactivity. No timestamp/countdown or extra account lifecycle state is exposed. A paused exposure does not hide the account or by itself deny otherwise eligible outgoing contacts, browsing or existing chats. `can_discover`/`can_make_new_contacts` remain operation prerequisites, not a claim that the owner is currently shown as a candidate. Actual discovery filtering is the next capability, not an endpoint implemented by this readiness projection.

A foreground user command or successful Google session issuance records actual activity. Background reads, polling and reconnect do not warm that source. An expired exposure deadline is captured before the first returning foreground action changes activity time; Google callback cannot confirm or clear the pause. The inactivity interval applied to that activity source is retained, so a later configuration change cannot silently reopen an already expired exposure.

The small inline action is **Show my profile again**. It uses the existing strict `PUT /me/visibility` command with `hidden:false`, current expected visibility version and a fresh idempotency key for that new intent. Readiness is rechecked. A successful already-visible confirmation retains the existing visibility revision; it records a separate genuine exposure-confirmation fact and `discovery.exposure_confirmed` canonical event. No fake `profile.hidden`/`profile.restored` event is generated for that no-op visibility state. Invalidate/refetch onboarding status after success; the PUT response shape remains unchanged.

A retry of an old resolved intent returns its original visibility result and never confirms a later inactivity pause. A new explicit action needs its own key; do not silently replay a background confirmation. Missing publication prerequisites return the existing `profile_restore_incomplete` requirements. Manual hiding, ban and deletion remain dominant; the freshness widget does not restore or override those conditions. An actual explicit hidden-to-visible restore can also confirm expired exposure and records the genuine visibility change.

Freshness policy rows are versioned retained server configuration, initially30 days. New foreground activity/explicit confirmation applies the current published interval; an older source keeps the interval under which its deadline was established until that actual activity. Backfill uses existing activation, saved business, session and visibility timestamps; it creates no historical user click or policy receipt. Confirmed return facts stay linked to the owned original visibility intent independently of hot telemetry retention.

## Concrete owner photo recovery

`GET /api/v1/media/uploads` requires the current live verified owner session, including during onboarding before activation. There is no actor/account selector. It returns `{photo, uploads}`: `photo` reuses CurrentPhotoResponse or null; each upload item contains the existing PhotoUploadResponse under `upload` plus `source_sha256`, the owner's expected SHA256 of the exact bytes declared at Start. Existing Start/status responses remain unchanged. No signed tickets, storage keys, worker leases, intent keys, binary bytes or other account data are returned. Responses are no-store.

The snapshot includes all up to3 pending operations, the latest20 terminal operations ordered by updated_at/id, and the current published READY operation even when it is older than that terminal slice. Results are deduplicated and ordered by updated_at descending then UUID descending, at most24 items. This is a bounded recovery projection, not an exhaustive history or retention window. All historical records remain retained. Expired operations acquire a genuine stored terminal revision; reads never invent an upload version or confirm/warm discovery activity.

After reload or loss of a Start202 response, obtain operation IDs from this snapshot. Queued/processing work follows its current server outcome; READY plus the current photo pointer resolves committed publication. If uploading work has no local file, explicitly reselect. Hash the final selected/cropped upload bytes locally before reusing that operation: exact source_sha256 equality is required; matching size/type alone is insufficient. A mismatch requires an explicit new intent after resolving/cancelling the prior operation and refreshing current photo version. Never silently reuse the ID for different bytes, parse signed POST fields for a fingerprint, overwrite queued work or claim local-file availability based on server metadata. The fingerprint is owner-private metadata, not an authentication credential, and must not enter logs/analytics. Server storage/worker checks still verify actual bytes independently.

Pending-root locks precede the fresh revision/time reads used by expiry and competing worker claims. Original result replays remain immutable. A cancellation/finalisation/publication race resolves through the existing actual status response; cancellation must not promise that publication did not happen when READY already won. No browser persistence of files, credentials or signed tickets is needed for recovery.

## Concrete peer profile and safety HTTP

The enabled-auth bootstrap now exposes these five operations in addition to owner onboarding/media/AI contracts. Actual export contains35 unique paths and39 HTTP operations; use the execution ledger's current hash. Earlier artifact aliases31/36 counted the photo-recovery GET as a new path even though it shares POST/media/uploads; schemas/DTOs were unaffected by that reporting error.

- GET/people/{person_id} rechecks the live verified activated requester, current requester and peer new-contact eligibility and either-direction blocks. It returns only declared profile/current photo/active goal/help fields, a server-issued owned access_context_id and actual own_block state/version for later CAS. Programme/year/about are optional, not verified academic facts or matching scores. Institutional/Google identity, registration documents, storage references and other-side block state are not exposed. Unknown/hidden/ineligible/blocked/deleted peers share404 person_unavailable. Inactivity exposure pause alone is not a new direct-read/contact prohibition and this GET does not confirm or warm discovery activity.
- GET/people/{person_id}/photo/{photo_version} serves only the currently authorised published display JPEG. No SQL connection or permission lock is held during storage I/O; live actor/peer/pair/current-photo eligibility is checked again afterwards before bytes are returned. Private/no-store/nosniff applies. Storage failure503 does not change profile eligibility or turn a known peer into an empty deck. Original/historical peer photos are not served through this endpoint.
- GET/me/blocks returns at most20 own active blocks per opaque actor-bound keyset page. Names resolve the last owned disclosure reference, not the blocked person's later private edits; legacy missing evidence stays unknown. Deleted targets have deleted:true and no display_name. Existing own block management works while hidden and when the target becomes unavailable; another side's block is never revealed or removed. Live requester identity/membership/activation still applies.
- PUT/me/blocks/{person_id} accepts blocked:boolean, expected_version:nonnegative integer and optional context_id, plus trusted Origin/CSRF and immutable Idempotency-Key. First knowledge of a target needs an owned matching disclosure context; existing own history can be managed without a new read. Only this actor's directional state changes. Version0/false for an absent unblock creates no dummy pair/block revision. CAS conflicts return409 block_version_conflict with the current own version; altered same-key payload409 idempotency_conflict. Stable replay returns the original historical result, so refresh reads rather than treating an old receipt as current state. No-op/replay do not invent block.changed outcomes.
- POST/reports currently accepts only kind:profile, owned context_id, one of impersonation/harassment/inappropriate_content/spam/other, and optional private comment<=1000 Unicode codepoints; Other requires an explanation. It uses Origin/CSRF/Idempotency-Key and actor/hour budget10. Successful201 contains only id/kind/context_id/submitted_at, never the private comment. Immutable replay returns the original receipt before quota; changed same-key payload conflicts. An already owned disclosure reference remains reportable after the target is blocked/hidden/deleted without granting new public reads. Reporting does not block a person automatically. Quota429 returns safe Retry-After/retry_at. Unknown/foreign references share404 report_context_unavailable.

Public profile responses reuse the actual goal/help DTOs and use a current-photo URI scoped to peer authorization. Initial onboarding task is not a role. No request-send/accept capability is fabricated by this slice; requests/accepted-chat profile scopes follow their own later use cases. Reports/directional revisions/canonical outcomes and original execution refs are retained transactionally, including after lifecycle changes. Technical spans carry only opaque resource references; these never become metric labels. Ordinary logs/traces do not contain profile/goal/comment text or private media. Server disclosure records are reference facts, not claims of a human view or consent. All JSON state responses are no-store, and safety command JSON shares the8192-byte/5-second receive bound.

## Concrete Discovery deck and private decisions

Enabled schema now has37 unique paths /41 operations. The prior35 paths and all prior component schemas are unchanged. New routes are GET/api/v1/discovery and PUT/api/v1/discovery/passes/{person_id}. This is implemented local behavior; real pilot population/catalogue/provider/operational acceptance remains separate.

GET/discovery requires a live verified activated student and current own discovery eligibility. Required mode is find_help, offer_help or study_together; optional view is candidates (default) or passed. The server derives actual mode context from the owner's saved active canonical goal, or nonempty saved help revision for Offer help. Helper-only students do not need an own goal. Missing selected context returns context_required rather than changing mode/goal. An exposure pause alone does not deny the owner's browsing or existing chats.

The response contains context, people (at most20), next_cursor, empty_reason and undo_pass. Context is a mode-tagged ownerless reference: find_help/study_together carry goal_id/goal_version; offer_help carries help_version. It contains no client-selectable actor. Cards include the actual selected profile/name/about/current authorized photo URI, server-grounded reason/subject label/topic/optional reciprocal subject and own_pass state/version. They contain no institutional email, upload/storage reference, fabricated disclosure/view receipt, feedback/compatibility score or unsupported request-send capability. Open the existing person endpoint for the full profile and owned report disclosure context.

Candidate SQL excludes current ineligible/hidden/banned/deleted/unverified/incomplete/exposure-paused accounts, either-direction blocks, existing conversations and effectively pending requests (including the fixed decline-Undo window). Matching is grounded in declared canonical subjects and explicit shared preferences. Exact literal Unicode/whitespace topic keys rank ahead of subject-only fallback, then bounded internal activity buckets and stable person ID. Background reads do not warm activity or confirm exposure. Keyset cursors are authenticated/encrypted with a purpose-separated derivative of the existing envelope key; clients must treat them as opaque. Actor/mode/saved-context/view binding and current permissions are rechecked. No ranking timestamp/countdown is exposed. Invalid or stale-context cursor input returns422 invalid_cursor; refetch from the first page. Private decision commands with a replaced/edited source return409 discovery_context_changed.

PUT/discovery/passes/{person_id} requires trusted Origin/CSRF, an immutable Idempotency-Key and JSON {context,passed,expected_version,undo?}. The context uses the exact tagged reference returned by GET, with no actor/account selector. Passed/undo are strict booleans, version is a nonnegative integer and undo:true requires passed:false. New passes recheck current owner/peer eligibility and declared relevance. Reconsideration only changes an owned retained pass and does not redisclose or notify the target; it can resolve after target unavailability. Changed same-key payload returns409 idempotency_conflict; same-key replay returns the original historical receipt and never reapplies it over a later state. Refresh canonical reads after ambiguous success/replay. CAS conflicts return409 pass_version_conflict with current_version.

An absent own pass is projected as version0/false/null changed_at without creating fake history. State changes retain real immutable revisions and canonical discovery.pass_changed in the same transaction. The latest passed decision gets server-derived undo_pass only until the next committed deck decision; preview-open does not consume it, while an actual successful new Request send does. This Undo has no decline10-second timer. An expired/inapplicable Undo returns409 pass_undo_unavailable. Review passed uses the same current context and eligibility; empty states distinguish context_required, no_relevant_people, exhausted and no_available_passed_people without invented counts. Historical private decisions remain retained after they stop appearing in the current view.

Actual hiding and blocking now close both directions of pending requests transactionally, preserving immutable request/context/history and accepted conversations. A retry of an old resolved hide/block intent cannot close a newer request after restoration/unblocking. Derived unavailable transitions keep the real initiator/correlation without fabricating an additional foreground action; automatic deadline finality stays system-initiated and never warms student activity. Any closure/canonical failure rolls back parent and consequences together. All Discovery state responses are no-store; the write route shares the8192-byte/5-second JSON receive bound.

## Implemented Requests contract — actual45

The real bootstrap now mounts Requests under `/api/v1/requests`; enabled schema has45 unique paths/50 operations. Deterministic export: `/tmp/peerly-actual45-requests-openapi.json`, SHA256 `c4fd4764d7f175863f48a8a08ee269446f3fea7cd969d5e70b2994bc6efc82f2`. All prior37 paths/schema components remain structurally unchanged. This implemented contract supersedes the earlier proposed GET preview/PUT viewed/direction query table; accept-and-send is not exposed until the real BE06 message composition exists.

- `GET /requests?box=received|sent&view=active|history|recently_declined&cursor=...`: actor-owned20-row pages plus opaque next cursor, sent-at/id stable keyset, actual quota and total effective incoming `unread_received`. `recently_declined` is received-only so live10-second Undo remains reachable despite newer rows. ACK never reorders pages. Each summary carries retained submitted text/note and academic subject/topic; no invented greeting or unrelated source grant.
- `GET /requests/{request_id}`: participant-scoped exact immutable request source, live capability projection, stored version and technical `disclosure_id`. GET/poll does not acknowledge a human view, clear unread or record foreground activity. Foreign and unknown IDs are neutral404.
- `POST /requests/preview` with `{person_id,mode}`: resolves existing outgoing/incoming/connected pair before admitting a new composer; otherwise returns an actual retained preview. No send or autoaccept. An existing result is not a new preview ID.
- `POST /requests` with `{person_id,preview_id,text,note?}`: immutable reviewed intent, actual pending/daily quotas and authoritative pair/state/source checks. Original retries return their immutable original receipt. Changed payload under the same key conflicts.
- `POST /requests/{request_id}/{accept|decline|undo-decline|withdraw}` with `{person_id,expected_version}`: actual actor/peer pair, stored-version comparison and fixed10-second decline Undo. Acceptance returns the genuine conversation reference without fabricating a first message.
- `POST /requests/{request_id}/viewed` with `{disclosure_id}`: explicit owned acknowledgement of the actual disclosed stored revision; retains the first receipt and same-TX canonical `request.view_acknowledged` event. No peer read receipt or rejection push.

Writes require the existing session cookie, trusted Origin, session CSRF token and immutable Idempotency-Key. JSON body limits are8KiB/5seconds; errors contain sanitized correlated problems. Reads/writes use no-store. Request disclosure grants no private profile/avatar access; current public peer metadata uses the existing public guard, otherwise neutral unavailable/deleted identity. Accepted chat membership has a separate minimal current identity authority in BE06, including while hidden; no original/history/full-profile grant is implied.

Head0030 stores disclosures/ACKs and actual owned intent/event references; head0031 adds locally tested text-message persistence but does not expose message HTTP. The exact mounted Requests bootstrap flow and body/Origin/error boundaries pass5 PostgreSQL tests plus3 deterministic export checks. The latest accepted full backend gate is1477/head31/96.51%, followed by bounded closed-response-schema/source regression checks; actual45 handoff is a tested bounded integration checkpoint, not a completed backend MVP.

### Accepted conversation details and explicit read position

The mounted contract now includes text history/commands/outcome recovery, minimal current participant identity/avatar and explicit goal sharing. `GET /api/v1/conversations/{conversation_id}` returns the actual accepted request/version/context, current authorized minimal peer, last confirmed sequence, the caller’s own read position, actual incoming unread count and current `can_send`. Accepted participant authority survives hidden/freshness-paused/changed study context; deleted peers remain masked. This is not a Discovery/profile disclosure grant. GET does not acknowledge reading or warm activity.

`PUT /api/v1/conversations/{conversation_id}/read-position` requires the existing session, Origin/CSRF and Idempotency-Key. Its closed JSON body is `{ "through_sequence": 1 }`, referencing an actual confirmed message. Position advances monotonically; original retries return their own immutable receipt. Future/nonexistent sequence returns409 `conversation_read_sequence_unavailable`. Only the caller’s position is returned; no peer read receipt or delivery claim exists. Both routes retain standard private/no-store and correlated problem responses. Actual53/60 deterministic enabled export is `/tmp/peerly-actual53-conversation-details-openapi.json`; frontend consumes the export, not this example as a parallel DTO definition.

`GET /api/v1/conversations?cursor=...` is mounted with20 rows plus a server lookahead. Each row has actual acceptance/request IDs and original academic context, current authorized minimal peer, latest confirmed human message selected by conversation sequence, current send capability and caller-private incoming unread count. Activity ordering uses retained human timestamps with UUID tie-break; ACK and goal sharing do not invent human activity. Encrypted cursors bind actor, purpose and original query anchor, expire after one hour, and return422 `invalid_conversation_cursor` when invalid. Continuations retain the original human-time boundary; refreshed page1 sees later activity. Current identity/lifecycle/block authority is selected together in one SQL snapshot. This is not a durable snapshot or delivery/read receipt. Actual54/61 export is `/tmp/peerly-actual54-conversation-list-openapi.json`; old53 paths/components are unchanged.

## Locally mounted operator reads

The enabled-auth schema now includes GET `/operator/accounts`, `/operator/accounts/{account_id}`, `/operator/conversations/{conversation_id}/messages`, `/operator/events`, `/operator/events/{event_id}`, `/operator/audits/{audit_id}`, `/operator/reports`, `/operator/reports/{report_id}`, `/operator/accounts/{account_id}/profile-history`, `/operator/accounts/{account_id}/help-history`, `/operator/accounts/{account_id}/goals` and `/operator/accounts/{account_id}/goals/{goal_id}/history` under `/api/v1`. They require an explicit current application operator grant and a live Google-linked session; student membership/profile activation are not operator prerequisites. No default grant or provisioning HTTP endpoint exists. Every successful or missing-resource inspection commits metadata-only audit and canonical source atomically before returning private data; ordinary telemetry excludes the returned content. Source and timeline cursor limits/authority are enforced by their use cases. Timeline search is metadata-anchored search, not commit order or an exact replay snapshot; refresh to discover late commits above a visited keyset. These local PostgreSQL/root/export checks do not validate external trace-store integration or production provisioning.

## Current request composer preview projection

POST `/api/v1/requests/preview` retains its original idempotent preview id, created_at and immutable academic context. Its `preview` outcome now also returns server-owned suggested_text (deterministic from that retained mode/context, not an AI call), checked_at, quota, can_send, block_reason and cooldown_until. Quota includes actual outgoing_pending/successful_today, configured outgoing_pending_limit/daily_send_limit, server-clamped outgoing_pending_remaining/daily_sends_remaining and reset_at at the next Asia/Kuala_Lumpur midnight expressed as an aware instant. The client renders these facts without generating default copy or inferring admission.

The same preview intent can be retried: original id/context/suggestion stay fixed while availability/quota are freshly checked. This observation reserves nothing. A concurrent action can change capacity or source eligibility afterward; final Send always repeats its actual pair, source/context and quota checks. Current block_reason is null when can_send is true; otherwise it is existing_outgoing, incoming, connected, cooldown, source_changed, unavailable, outgoing_pending_limit or daily_send_limit. Only an actual cooldown includes cooldown_until; unavailable reveals no private peer lifecycle/block cause. Initial existing-outgoing/incoming/connected recovery union responses remain unchanged.

Fresh checks create no additional preview/send intents, spend no quota and do not settle pending finality or fabricate canonical actions. Expired/pending-decline effective state still follows existing authoritative source/deadline rules. The retained preview is not a new profile/media permission. Application authorization is checked again before returning the observation.

### Retained operator report and profile history

The report list is a bounded50-item metadata projection with filters for reporter, target, retained disclosure context, category and an aware half-open submission interval. Its opaque cursor binds the actual operator grant and filters. Listing never returns the private comment. Report detail returns the retained comment and disclosure references, with the actual submission event origin separately when present; missing historical origin stays absent. No case assignment/status or student disclosure capability is fabricated.

Profile history reads all retained profile revisions for the actual target account, including history beyond its current pointer, ordered by descending version with50-item cursor pages. Languages retain stored slot order; raw saved profile fields are not revalidated through today's student form or catalogue. Existing accounts without revisions return an empty history. Hidden/banned/deleted target state does not remove privileged history access. Both capabilities use the existing final live-session/grant check and same-transaction metadata audit/canonical outcome; they grant no student media/original/history access.

### Retained operator academic history — actual67

Help history returns actual saved revision versions with selections in original slot order, including an explicit empty saved clear. It reads all stored revisions independently of the current pointer and current catalogue state. Goal roots list both active and ended records with bounded50-item metadata keysets, optional active/completed and aware half-open creation filters. Its actual first observed root anchors pagination; this is not commit order or an exact snapshot, and refresh observes later metadata/commits. Goal history reads all actual owner-bound revisions ordered by version, preserving saved subject labels, topic keys/context and completion data without today's student-form validation. Hidden/deleted/banned target state does not remove privileged access. Existing account with unknown/foreign goal returns404 after a truthful account-container READ audit; an absent account records NOT_FOUND. No fake goal-version UUID, full student profile grant or published-media availability is inferred.

### Canonical revision updates — head0042

New material profile/help saves and actual profile-photo publication append `profile.saved`, `help.saved`, `photo.published` to the existing canonical journal in the same source transaction. Each references the exact owner-bound stored revision. Existing records are not backfilled; missing historical provenance remains absent. Photo publication uses the actual retained queued execution origin when available, with no ambient/created-origin substitution, and background completion does not record foreground activity.

Own-account hints refresh dependent REST queries. A display-name change or photo publication also stages an unversioned `account` invalidation for currently eligible accepted/pending contacts; its resource_id is the recipient's own account aggregate, not another person's private profile. About-only edits do not signal peers, and blocked/unavailable receivers are excluded at staging. Hidden/freshness state does not restrict existing accepted-contact identity. Actual stage recipients remain frozen in the existing outbox: later blocking cannot destroy their retained transport source, and new connections cannot receive old events retroactively. These hints carry no names, bodies, reasons, profile grant or extra business outcome journal.

### Privileged retained profile photos — actual70/head0043

The enabled-auth root mounts GET `/operator/accounts/{account_id}/photo-uploads`, `/operator/accounts/{account_id}/photo-uploads/{upload_id}/history` and `/operator/accounts/{account_id}/photo-uploads/{upload_id}/attempts/{attempt_id}/{kind}` under `/api/v1`. The first two inspect retained account-owned upload revisions and current recorded attempts, with bounded authenticated pagination. `latest_published_photo_ref` is the latest recorded reference, not complete publication history or a binary grant. Failed/stale objects and deleted target accounts remain inspectable by a current privileged operator.

Binary `kind` is `original` or `display`. Both require the exact owned upload and processing-attempt source, not current student photo eligibility or READY status. Storage reads occur between two short SQL authorization phases; the final phase requires the same live session, grant version and source, and commits source-bound audit plus canonical event before returning bytes. Missing source/object is audited404; unavailable or uncertain storage/audit yields503 with no bytes. Originals download as application/octet-stream and display objects as image/jpeg, both attachment/no-store/nosniff. Responses disclose no signed URL, storage key or worker lease. These local tests do not establish external bucket availability.

## Student feedback mounted follow-up (8 November 2026)

The tested post2928 root now exports77 paths/86 operations at unchanged schema head0043. Reproduce without provider/database connections using `cd backend && uv run python -m studymate.export_openapi --output /tmp/peerly-feedback-openapi.json`.

- `GET/PUT /api/v1/conversations/{conversation_id}/study-outcome`: participant-owned versioned outcome with idempotent writes.
- `GET/PUT /api/v1/conversations/{conversation_id}/feedback`: own retained structured assessment and private team note; another participant cannot read that note through their own feedback projection.
- `POST /api/v1/conversations/{conversation_id}/study-prompt-visits`: explicit foreground visit, returning an actual offered receipt or `no_offer`. Background GETs do not mark a prompt viewed.
- `GET /api/v1/me/feedback-summary` and `GET /api/v1/people/{person_id}/feedback-summary`: own or Discovery-authorized aggregate; public category counts require the existing three-distinct-partner threshold. No private notes or reviewer identities are exposed.

All three mutation paths use the existing Origin/CSRF/idempotency contract and shared JSON-only8KiB/5-second body bound. Actual business revisions and canonical metadata events commit together. They do not send chat messages or acknowledge message reading. Exact request/response fields come from the generated schema and `presentation/feedback` models. Local root checks do not constitute live-provider, deployment or frontend acceptance.

## Student lifecycle mounted boundary (head46)

Current tested export:81 paths/90 operations, `/tmp/peerly-actual81-head46-student-lifecycle-openapi.json`, SHA256 `1385819681385f5a1c642a1092a29599018eadd2a067741f6020a4f6a424d56d`.

- `POST /api/v1/me/deletion-workflows` with closed `{}` JSON and ordinary live-session Origin/CSRF headers prepares a stable workflow. Concurrent tabs/retry of a lost response reuse it. Response contains workflow ID/expiry; the separate status proof is only a Secure/HttpOnly/SameSite=Strict host cookie, not a JavaScript token.
- `POST /api/v1/me/deletion` with workflow ID and normal idempotent write headers commits soft deletion and retires the application-session cookie. It preserves the dedicated status cookie. All original business data/identity uniqueness/analytics remain retained; this is not erasure or self-restore.
- `GET /api/v1/me/deletion-status` requires only `DeletionStatusCookie`, never a public account/workflow ID or a new normal application session. It returns its owned `pending` or actual committed `deleted` receipt. Pending is not proof a delayed command cannot commit. Missing/expired proof returns404 `deletion_status_unavailable`, not an assertion of failure or reversal. Frontend normal-session guards must not block this narrow recovery screen after session revocation.
- `PUT /api/v1/operator/accounts/{account_id}/ban` is the explicit current-operator-grant mutation for ban/unban. Replays return the original committed receipt, not a current-account-state claim; no-op does not invent a new business source/event. Lifting a ban preserves deletion and other restrictions. No private reason is returned in mutation receipts or ordinary telemetry.

Canonical `account.lifecycle_changed` references the actual retained source, actor, target, version and operation. Existing operator timeline enums/facts were extended to read that actual event, without adding operator UI scope. Current login transactions are not bound to accounts before callback resolution; their source/IP digests are not invented ownership. Deleted-identity callback denial remains mandatory and is tested. In-flight external work is not claimed to be physically recalled by a database cancellation.

Real-root tests cover deletion/recovery/two sessions, deleted Google identity denial, ban permissions, idempotency and the actual body/timeout limits. Combined backend, live providers, frontend screenshot acceptance and staging deployment remain separate gates.

## Student chat image mounted boundary (head48)

Current tested export:87 paths/97 operations, `/tmp/peerly-actual87-head48-chat-images-openapi.json`, SHA256 `cb6859d1e8535e1bc2e5f8c0bb692d396c6892efb6f6c6388e5cf85963a588e1`. This supersedes the81-path lifecycle snapshot without changing its routes.

- `POST /conversations/{conversation_id}/image-preparations` binds a new preparation to one actual owner/conversation/client-message intent and immutable size/SHA256/content-type. The202 receipt is historical, not current worker status. Normal Origin/CSRF/idempotency headers apply. Processing never sends a message.
- `GET` on the collection resumes up to3 pending and20 recent terminal/ready owned preparations. Individual `GET /{image_id}` reads the current source and effective state. Owner-only `expected_source` permits exact local-file matching after reload without parsing signed fields or persisting capabilities. `message_outcome.attachment_confirmed` uses the actual message attachment FK, not a merely matching client ID or confirmed text message. No source revision is invented for effective expiry.
- Bodyless `POST /{image_id}/upload-access` returns a transient authorized signed multipart capability. It rechecks the same live actor/source after signing; no transaction spans signing. Bodyless idempotent `POST /{image_id}/finalize` queues processing, with bounded admission and worker attempts. Original receipt retries remain historical; poll the current preparation after an uncertain outcome.
- `GET /{image_id}/display` is the owner's current READY preview. Only explicit existing `POST /conversations/{conversation_id}/messages` with the bound client-message ID and `image_id` publishes that owned READY rendition; optional `text` is the caption. Text alone cannot repurpose a source-bound client ID. Confirmed message projections now contain nullable `text` and nullable `image_id`, with at least one actual content source.
- `GET /conversations/{conversation_id}/messages/{message_id}/image` reads the exact confirmed rendition under accepted participant authorization, independent of Discovery visibility/freshness. It grants no owner-preparation or original-media access. Responses are normalized JPEG, private/no-store/nosniff; no storage keys, worker leases or signed read URLs are exposed.

Shared media runtime services profile processing, chat-image processing and both temporary-transport cleanup queues sequentially using one bounded image processor. Upload transport can be cleaned after its approved terminal/deadline rules; original/display business media and immutable message associations remain retained. Local controlled-storage/root tests are not real S3 browser/large-file, production worker or staging acceptance.

## Confirmed image-report mounted boundary (head49)

Tested export:88 paths/98 operations, `/tmp/peerly-actual88-head49-image-reports-openapi.json`, SHA256 `c5c50483734e19d49ce18ede424c6c3eda9a3f9b8499c4d0d7ddbf7589dd4a79`. No new settings, engines or cross-origin authority are introduced.

Bodyless `POST /conversations/{conversation_id}/messages/{message_id}/report-contexts` uses the ordinary browser Origin/CSRF contract and returns201 with the owned context ID, kind `message_image`, conversation/message/image IDs and actual issue timestamp. It accepts only a peer-authored confirmed image in the actor's accepted conversation. A preparation ID, text-only message, own image or foreign conversation is not such evidence. Current actor policy remains mandatory; peer hidden/freshness/block/ban/deletion do not erase authorized stored-message reporting. Context issuance grants no future read or submission permission.

Existing `POST /reports` now accepts a closed discriminator union `kind:profile|message_image` with owned `context_id`, existing category and bounded optional private comment. Other still requires an explanation. Image reports recheck the actual message/rendition FK and current actor/session; they do not ask Discovery for a public-profile grant. Both kinds share the retained report root, actor/key registry,10/hour budget and `report.created` source. Exact retries return the original kind/context receipt; changing kind/context/payload with that key conflicts. Neither receipt nor ordinary telemetry copies the private comment/message/image content. Actual source references establish causality; wall timestamps may move backwards and are not invented or ordered to prove it.

Existing privileged report list/detail now expose actual summary kind and a mandatory tagged context (`profile` or `message_image`). Image context contains retained references/timestamps/origin, never fictitious profile/photo revisions or a student media capability. This preserves existing exhaustive inspection correctness; it adds no operator UI, route, filter or separate outcomes stream. The timeline's historical technical locator `profile_report` still points to the shared report root; evidence kind comes from that root's actual tagged context.

JSON submission retains existing8KiB/5-second bounds and idempotency; context issuance rejects any nonempty body. Root checks include actor/source isolation, foreign Origin rejection, closed payload errors and body limits. Scoped acceptance and local migration/provider doubles remain separate from the next full gate, frontend screenshots and real internal-stage deployment.

## Student support and notification preference — code candidate

The following mounted head52 contract is code-complete integration in progress, not final-gate or real-staging acceptance. The current generated code export is authoritative; do not infer deployment from the older immutable head50 first boot.

- `GET /me/notification-preference` returns `mode`, `version`, nullable `changed_at`. `PUT` takes the exact two-value mode (`messages_and_requests` / `all_updates`) and `expected_version`, with session CSRF and Idempotency-Key. Version0 is the unchosen default; no-op does not fabricate a revision/event. This is a persisted product choice, not OS permission, a native delivery capability, marketing consent or an analytics/security-email opt-out. Native push transport remains a separate rollout.
- `POST /support-context` with JSON `{}` and exact same-origin Origin issues a separate opaque HttpOnly/Secure/SameSiteStrict proof cookie and returns its CSRF token/expiry. It is available without login, institutional verification or activation, with bounded observed-source quota. This proof never creates/authenticates/merges/reactivates an account.
- `POST /support-cases` requires that proof cookie, its CSRF and Idempotency-Key, not a student session. `topic`, `reply_address`, `message` and optional `details` become retained private business content. The response is an actual `received` receipt, not a claim of email/Telegram delivery or automatic resolution. An entered address does not bind an account or prove ownership/competence.
- `GET /support-cases/{case_id}` checks the current proof's actual ownership; a case UUID alone is no authority. `GET /support-cases` discovers at most20 recent owned receipt projections in server received-at/ID descending order, enabling recovery after a lost response/reload without browser storage of the case body, key or credential. It is explicitly a bounded recent projection, not an exhaustive history.
- `POST /me/support-cases` uses the actual session plus separate support proof to bind the authenticated actor; unverified/banned accounts retain this limited support capability. `GET /me/support-cases[/{case_id}]` checks the actual current session/actor and provides the corresponding recent/specific receipt. Deleted identities use the separate anonymous flow and never silently regain account authority.
- `GET /operator/cases/{case_id}` and `PUT /operator/cases/{case_id}/status` require the existing current operator grant and atomic inspection audit. Status takes CAS version/idempotent intent and records a real operator/grant-bound revision; no student or support proof can set it. This is minimal backend support operation, not renewed operator UI scope.

Support creation has a32KiB byte cap and5-second JSON-read deadline; other new commands retain8KiB/5seconds. Replays preserve the original receipt/version rather than pretending a newer status was the original result; current state comes from owned reads. Foreign/expired proofs do not disclose account/case existence. No private support content, reply address, proof or auth secret belongs in ordinary telemetry. Anonymous cases retain their actual business source and server request/trace references without a fictitious canonical account actor; known actors and real operator changes append source-validated canonical events.


## Locally accepted BE07 operator expansion — head54,106paths

The coherent150-case targeted acceptance (136unit/14actualPG) mounts ten additional
GETs under `/api/v1`: account-scoped connection-requests plus raw history and
disclosures; chat-image-uploads plus raw history; peer-feedback plus raw history
and removals; `/operator/cases` and `/operator/cases/{case_id}/history`. These are
privileged retained reads, not student disclosure/media grants or new mutations.
Actual enabled-auth export:106paths/119operations, SHA256
`4da93c8717724c4c4c8472c9ce6593e9fd2af3683f2c4e1e2968da2fa9a9e433`.
Existing96 path objects are unchanged; `OperatorAction` additively includes
`search_support_cases`, supported by the already shipped immutable0053 schema.
No new migration or role is introduced. Local acceptance is not a staging
deployment/publication receipt.

Support inbox returns50-item metadata pages with exact case/actor/topic/status/
anonymous and half-open aware received-time filters. Status is explicitly
`current_at_each_request`; received-at/id keysets and metadata anchors do not
promise commit snapshots. No private reply address/message/details/proof enters
the list. Detail is the existing deliberate private-content read. History returns
actual retained status versions and original operator/grant provenance,50-item
version-descending pages anchored to the first observed max version. Every read,
empty search and missing-resource inspection commits the real bounded metadata
audit/canonical fact before response; role/session/final-commit failure exposes
no data. All new reads require current explicit operator authority, not student
activation, participant membership or a support-case permission grant.

### Operator account conversation index (head54, local107-path contract)

`GET /api/v1/operator/accounts/{account_id}/conversations` requires the current
explicit operator grant/session and commits mandatory READ_ACCOUNT container audit.
A known empty account returns an empty page; a missing account records NOT_FOUND
before404. Rows contain `id`, `relationship_id`, `low_id`, `high_id`, `request_id`,
`accepted_request_version` only. Both actual participants remain inspectable after
visibility/deletion changes. No student profile grant, message content, attachment
access, invented timestamp or message count is implied. UUID-descending50+1 keyset
pagination binds opaque cursor to operator/grant/target; refresh is required to
observe inserts above an already visited key. This is not a commit snapshot.

### BE08 — locally accepted head55 contract

POST `/api/v1/telemetry/events` admits at most20 closed schema1 observations/16KiB
raw JSON with actual session, Origin, CSRF, idempotency and account-bound rate. The
sixth `quality.observed` variant is a strict client claim with finite reason/count,
not evidence of permanent loss. Actor changes discard local history, not reattribute
it; submitted expected_actor_id is only a server-checked fence. Unknown public
release/asset maps reject numeric frames; no URL/raw-stack fallback is accepted.

GET `/api/v1/operator/delivery-sources` supports actual actor/kind filters and
opaque grant/operator/query-bound cursor; GET `/{source_id}` returns actual typed
source and at most2delivery states/16attempts. Both require current explicit
operator authority and same-transaction canonical inspection audit. No provider
secret/body or send/retry mutation is exposed. Only Umami+Telegram Support sinks
exist. See planning/be08-firstboot.md for source truth and deployment limitations.

### Operator retained chat attachments (local head56)

GET `/api/v1/operator/accounts/{account_id}/chat-image-uploads/{image_id}/attempts/{attempt_id}/{kind}`
accepts only original/display and no open query overrides. Exact retained image-owner
and attempt joins supply authority source proof independently of student Discovery,
READY/current image state or target lifecycle. A current explicit operator/session
is checked before and after bounded object I/O; the final mandatory canonical audit
commits before bytes are returned. Missing object/source is audited NOT_FOUND;
storage/timeout/oversize never masquerades as a successful inspection. No SQL
transaction remains open during object reads. Original is an octet-stream attachment;
display is a JPEG attachment, both no-store/nosniff/CSP-sandbox with no storage URLs.

Audit metadata uses distinct requested_chat_owner_id, requested_chat_attempt_id,
requested_chat_kind and actual_source_image_id fields. Existing profile fields/FKs
are not repurposed. Actual source image/owner and image/attempt tuples have retained
RESTRICT FK proof; audit/canonical failures release no bytes. Retained chat inspection
facts prevent unsafe56downgrade. Actual111/124 schema is exported after scoped tests;
this is not an external deployment or full-suite acceptance claim.

### Operator inspection journal search (local head57)

GET `/api/v1/operator/audits` returns at most50 actual audit details plus opaque
next_cursor and DB search_anchor_at. Filters are exact operator_id/action,
requested_kind/requested_id (ID requires kind), http_request_id/action_id/trace_id,
and aware half-open occurred_from/occurred_before. Requested filters apply only to
actual nonnull requested target; a search row's physical family kind is not an
invented requested resource. No freeform content/identity search is added here.

Rows retain the original active grant/version even if that operator is later
revoked/deleted. Caller authority is separately checked now and before commit.
Each page commits mandatory SEARCH_AUDITS metadata audit of only visible audit IDs;
failed audit returns no result. Descending occurred_at/UUID cursor binds actor,
grant revision, normalized query fingerprint and DB-time anchor; late commits may
require refresh and no commit-order/snapshot or human-view claim is made. Existing
GET/audits/{audit_id} detail and all earlier111 path objects remain unchanged.
