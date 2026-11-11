# FE05 Chats developer handoff

Parent activated this implementation slice after accepting D03 scoped87 HTTP/27 PG,
273 reviewed PNGs. Aquinas owns ONLY `src/app/screens/chats/**` and
`../docs/planning/chats-progress.md`. Previous Person/Requests/Discovery/composer
production and ledgers are frozen. Halley owns root routes, session, transport,
generated types, shared testing/fixtures, browser leases, global SSE, theme, tooling
and packages. No subagents or shared Git operations. Read applicable AGENTS,
`../docs/design-review-v2.md` and the current API documentation first.

## Start and continue independently

Detail the local scenario matrix and implement C01 list + C02 actual selected-thread
read first; then text send/recovery, private read position and explicit goal shares.
Continue dependency-ready slices without routine permission. Export `Chats` from
`chats.ts` once the first real consumer exists, then notify Halley to mount the lazy
`/chats` route under the existing content QueryClient. Do not create an empty route
placeholder. Selection is URL query `conversation`; list pagination `cursor`, message
pagination `history_cursor`, goal-sharing pagination `share_cursor`. Clear dependent
cursors when changing selection. Halley adds cross-screen links only when the
corresponding consumer works. Do not edit routes/shared files yourself.

Use boards `/tmp/peerly-design-v2/peerly-design-package/spec/boards/`:
C01-ChatList, C02-Conversation, C02-Delivery, C03-Lifecycle, C04-SharedGoal and their
corresponding approved design HTML. C03-Image waits for an exposed tested image API.
No fake attachment picker, unsupported delivery/read receipts, typing presence,
study-outcome endpoint or inert navigation. Keep current public theme/fonts.

## Actual API boundary

Current generated `src/app/api.generated.ts` is coherent67/head42, source SHA256
`7cfe497e064fb4bc7fcc756b476fb9be60e134f70034f0202f261f6bfcf3c44a`.
Generate nothing manually. Backend43 is currently transitional: no fresh PG fixture
until Noether supplies coherent runtime/export READY. Existing chat paths are actual.

All paths below start `/api/v1`. Inspect exact generated parameters and statuses.

| Actual operation                                                         | Generated response/body                                                                                                                             |
| ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| GET `/conversations?cursor=...`                                          | `ConversationListResponse`: conversations, next_cursor; rows `ConversationSummaryResponse`                                                          |
| GET `/conversations/{id}`                                                | `ConversationDetailsResponse`: original_context, accepted_request_version, peer, last_confirmed_sequence, own read_position, unread_count, can_send |
| GET `/conversations/{id}/participant`                                    | `ChatParticipantResponse`                                                                                                                           |
| GET `/conversations/{id}/participant/avatar/{photo_version}`             | JPEG Blob; distinct chat grant, never a Discovery profile request                                                                                   |
| GET `/conversations/{id}/messages?cursor=...`                            | `MessageHistoryResponse`: messages, next_cursor, anchor_sequence                                                                                    |
| POST `/conversations/{id}/messages`                                      | `SendMessageBody`: client_message_id, text(1–2000 codepoints); confirmed/cancelled operation union                                                  |
| GET `/conversations/{id}/message-operations/{client_message_id}`         | confirmed/cancelled/unobserved operation union                                                                                                      |
| POST `/conversations/{id}/message-operations/{client_message_id}/cancel` | no body; confirmed/cancelled operation union                                                                                                        |
| PUT `/conversations/{id}/read-position`                                  | `ConversationReadPositionBody` through_sequence; `ConversationReadPositionResponse`                                                                 |
| GET `/conversations/{id}/goal-shares?cursor=...`                         | `ConversationGoalSharePageResponse`: baseline/current_context_version/anchor_version/latest/history/next_cursor                                     |
| POST `/conversations/{id}/goal-shares`                                   | `ShareCurrentGoalBody`: goal_id/expected_goal_version/expected_context_version; `ConversationGoalShareReceiptResponse`                              |

Rows contain request_id, conversation_id, accepted_at, activity_at, original_context,
peer, nullable last_message, unread_count and can_send. `MessageResponse` contains
message_id/conversation_id/author_id/client_message_id/sequence/text/sent_at. Preserve
canonical sequence ordering; no local timestamps/UUID ordering. Empty accepted
threads contain no invented human message. Peer.state is exactly available,
unavailable or deleted; display_name/photo_version are nullable. Use actual masking,
not a historical name/profile fallback. Hidden/freshness-paused users retain chats.

Operation discriminators have optional default metadata in generated responses;
validate actual discriminant and nested shape at the transport boundary. Confirmed
means stored, not delivered/read. Unobserved is not proof a send cannot still win.
Unknown sends retain the exact immutable text/message ID/idempotency key; explicit
retry/cancel only. Cancel racing commit can return confirmed. Keep unsent text in
component forms, not a new global draft store or browser storage. Clear on logout,
actor replacement/destroy and confirmed success; no server projection mirrors.

Own read position advances only through a confirmed message genuinely displayed in
an active visible conversation. GET/history/background refresh is not a read ACK.
No peer read receipt. Sharing uses actual current goal plus context/source versions;
original accepted context stays immutable. baseline/entry can_complete is server
permission; no auto completion on opening/sharing. Do not import Goal screen internals.

## Existing shared helpers and guards

- `screens/session.ts` exports `sessionOptions(http, client)`, the one `['session']`
  GET/me query. IdentityResponse|null, retryfalse; revalidation cancels/removes
  account-prefixed private reads. Never mirror its identity/loading/error in signals.
- Inject the existing QueryClient from content.routes. Prefer established public
  QueryObserver/MutationObserver: installed injectQuery namespace retention breaks
  the initial500kB budget. No dependency forks, deep imports or budget weakening.
- `api-http.ts`: `readJson(http, relativeUrl, AbortSignal, guard)`;
  `writeJson(http, relativeUrl, body, headers, guard, method='POST')` supports PUT.
  Bodyless cancel uses undefined. Guards narrow unknown to generated readonly DTOs,
  including nested arrays/unions/nullable values; no casts/defaults masking bad data.
- Writes use current actor csrf_token as x-csrf-token plus immutable idempotency-key
  from crypto.randomUUID. Origin is browser-owned. No mutation retry defaults.
- `readJpeg(http, relativeUrl, signal)` returns validated bytes. ObjectURL ownership
  may retain only native Blob identity/URL; canonical data stays in Query. Release
  after the relevant DOM update/removal. Halley owns any shared native-resource
  extraction at a third actual consumer; request it rather than importing another
  screen's internals. Coordinate this before adding the chat avatar consumer.
- `ApiFailure` exposes safe status/code/requestId/retryAt only. Never show raw error
  bodies/provider messages or log message text. `screens/uncertain.ts:isUncertain`
  covers ApiFailure0/408/5xx. `screens/brand.ts:Brand` is available.

Private keys start `['account', actorId, 'chats', ...]`, then use `list`, conversation
ID and `details|messages|participant|avatar|goal-shares|operation` plus every cursor,
version/message ID as applicable. Halley SSE invalidates this prefix initially;
no separate stream/store/client in chats. Keep the prefix stable and notify Halley
of exact final keys. Check a trusted current account/can_use_student_features before
private reads or commands, and block actions during session refetch.401 revalidates
session; remove owned draft/mutation/native resources before actor replacement.
Late callbacks must check original actor/lifetime/selection. Do not reauthorize a
replacement actor from an earlier request's failure.

## SSE ownership

GET `/events` is real but OpenAPI describes wire text, not frame DTOs. Halley builds
one shared account-owned stream through public transport/lifecycle APIs. Chat code
consumes canonical queries after invalidation, never copies event bodies into a
store. Actual resource.changed hints contain resource_type(account/request/
conversation/ai_job), resource_id, nullable version; reset_required invalidates
private canonical reads. IDs are canonical decimal strings, never credentials or
message sequence/read positions. Heartbeats carry no content. No automatic social
resend, ACK or goal sharing on reconnect. Signal shared invalidation needs to Halley;
do not implement another SSE connection in this screen.

## Meaningful tests and real fixtures

Own all chats unit/visual specs, fixtures confined to this screen, scenario matrix
and reference PNGs. Use `testing/visual` behavior+named checkpoint for every scenario
on mobile Chromium/WebKit/desktop Chromium; strict viewport/error/action visibility,
320px/200%, keyboard/reduced motion, no masks/relaxed tolerances/skips. Keep95% all
unit thresholds; mocks supplement real FastAPI+Postgres. Raw stdout+stderr for every
command goes to a unique /tmp file, preserving exit code. Serialize ALL browser/PG
and heavy unit/build runs with Halley; no unknown browser/process termination.

Ready existing driver: `testing/composer-fixture.ts:prepareComposerFixture(page,
'find_help','connected',project)` calls POST `http://127.0.0.1:8768/__fixture/composer`
with `composer/find_help/connected/{project}` and installs only the synthetic secure
session cookie. Both students have actual profile/photo/goal/registration, request
Send and Accept use cases. It returns viewerId/personId/subjectId/subjectLabel,
NOT conversationId; find the real thread through GET/conversations. Namespace is
single-use per fixture: do not reuse it across chat scenarios or conflict with D03.

For the complete chat matrix Halley will extend shared cohort drivers under new
chat-specific namespaces and add genuine message/share/read/cancel setup through
actual use cases. Those extensions are NOT implemented yet. Send exact first cases
and desired selectors; do not edit shared helpers/backend fixture, manufacture
conversation IDs/activation rows or add mock-only production routes. Core frontend
fixture upgrades a fresh isolated Alembic schema to coherent HEAD, owns independent
core/AI/change pools and loopback TLS/storage/provider doubles. No reset of shared
Postgres, live Google/email/S3/Codex calls or secrets/auth reads. Ask Halley for
controlled deterministic time strategy before timestamp-sensitive real PNGs.

Initial units/read-only HTTP-boundary fixtures can proceed immediately. Notify
Halley when Chats export is ready so the real route exists before boundary browser
runs. Each real-stack lease needs explicit fresh Noether READY, own START/END and
schema/pools/TLS/listeners cleanup. Latest source is transitional43, not a valid
old42 fixture reuse. Current global native ResizeObserver gate stays OPEN; scoped
passes do not imply full npm check, native OS/provider validation or deployment.

## Selected real-PG date strategy

Keep actual server chronology. No future2050 hooks, process-wide clock patch or
separate fixed-clock command. The v2 natural UI is today HH:mm / Yesterday / older
date, preserving source datetime and absolute title. Boundary scenarios cover
exact today times and KL midnight/year boundaries. `prepareChatsFixture` reads
actual details/history, returns those typed sources and fixes only browser wall
time to next KL calendar noon for Yesterday screenshots. Tests must assert exact
API timestamps/sequence/text separately; they may not mask, rewrite server DTOs or
relax image comparison. The single-KL-source-day fixture prerequisite is explicit.
Source-only probe FE05-chat-source-smoke2 has passed actual empty/messages cohorts
on head43/actual70 with real timestamps, sequence and no GET ACK. Browser clock and
Yesterday PNG validation still await a fresh named lease and actual scenarios. No server time/expiry/freshness
or transport determinism is claimed from changing the browser clock.
