# Requests implementation handoff

Parent authorizes Aquinas immediately after Discovery ledger finalization. Exclusive
writes: `src/app/screens/requests/**` and `../docs/planning/requests-frontend-progress.md`.
Discovery and Person are frozen. Halley owns shared routing, fixtures/driver seeds,
contracts, transport/auth/query helpers, theme/assets, packages and browser lease.
No Git operations, subagents, provider calls, secret reads or own backend edits.

## Deliverable

Export standalone `Requests` in `requests/requests.ts`. Halley integrates lazy
`/requests` under existing content routes/QueryClient once importable. URL owns
`box=received|sent`, `view=active|history|recently_declined`, opaque `cursor`, and
optional selected `request` ID. Default received/active; recently_declined is
received-only. Clear cursor/selection on changing box/view; query key contains
all actual server parameters. No copied list/detail state or new QueryClient.

Implement genuine list, selected detail, explicit owned acknowledgement, accept,
decline, Undo decline and withdraw. Initial slice excludes compose/preview/send:
those APIs exist but Discovery CTA waits for its real lifecycle consumer. No fake
request button in Discovery/Person. Accepted conversation ID is factual data;
no link to nonexistent Chats screen, no fabricated first message or accept-and-send.
Record compose as the next ready bounded task after this lifecycle slice.

Read root/frontend AGENTS, workflow, docs/design-review-v2.md and docs/api.md
Implemented Requests section. V2 source package remains read-only at
/tmp/peerly-design-v2/peerly-design-package. Approved boards: R01-Received,
R01-Decline, R02-Sent, R03-Detail, R03-Pair. R04-AltResponse requires separate
real composer; do not implement invented accept-and-send. D03 preview belongs
to the subsequent actual compose task. Use public Taiga APIs/existing tokens.

## Actual contract

Generated Api is actual54 paths/61 operations, SHA256
`d85683a39dbf3e24b65f38f1a7d916a90de6cc06560ba36f3c4aa28ccc59c7cf`.
Current source `/tmp/peerly-actual54-conversation-list-openapi.json`.
Use generated schemas and unknown-response validation, not handwritten DTOs.

- GET /api/v1/requests?box=...&view=...&cursor=... -> RequestPageResponse.
  Actual outgoing quota, incoming unread,20-row opaque pagination; ACK does not
  reorder rows. No local inferred counts or unbounded client filtering.
- GET /api/v1/requests/{id} -> RequestDetailResponse, exact immutable academic
  context/text/note plus technical disclosure_id. GET is not an ACK/activity.
- POST /requests/{id}/viewed {disclosure_id} -> ViewedResponse. Only after actual
  selected detail is rendered/visible to the user, never list load/prefetch/poll.
  Preserve immutable unknown intent; no automatic retry or fabricated receipt.
- POST /requests/{id}/{accept|decline|undo-decline|withdraw}
  {person_id,expected_version} -> RequestMutationResponse. Current actor/peer,
  actual stored version, CSRF and immutable Idempotency-Key, no social auto retry.
  Version/CAS conflicts need canonical refresh and explicit next action.
- Decline Undo is the actual fixed10-second server deadline. Render from
  observed_at/undo_until; timer is ephemeral presentation, server authoritative.
  Refetch expired capabilities without claiming client timer changed server state.
  Recently declined remains reachable even when active page omits that request.
- Peer public/unavailable/deleted masking and capabilities are authoritative.
  A retained request/disclosure is NOT a grant to private profile/photo. No source
  context leaked into telemetry, no guessed image endpoints. Use genuine
  /people/:id link only if actual view_profile capability and public peer permit.
- Preserve immutable original receipts on retry, then reread canonical state;
  stale replay does not recreate an old live Undo window or change latest UI.

## Public shared boundaries

Use screens/session.ts sessionOptions with existing QueryClient; screens/brand.ts
Brand; api-http.ts readJson/writeJson/readJpeg/ApiFailure, screens/uncertain.ts
isUncertain. Check actual signatures. Abort query transport with provided signal.
Private keys start ['account',actorId,'requests',...]. Account change/401/logout/
destroy clear owned sensitive queries/mutations/drafts; ignore old-actor callbacks.
Never import other screen internals; ask Halley for a third-consumer extraction.
No extra facade/store/event bus or credentials in URLs/browser persistence.

## Acceptance and fixture ownership

Colocate meaningful *.spec.ts, *.visual.spec.ts, *.fullstack.spec.ts and scenario
matrix. All browser scenarios use testing/visual checkpoints, actual behavior plus
named PNGs across Chromium mobile/WebKit mobile/Chromium desktop. At least95%
all application coverage measures, strict lint/styles/format/types/Knip. Include
loading/empty/error/retry/auth/stale CAS/unknown committed result/pagination/
foreground ACK/peer lifecycle/Undo expiry and320px/200%/keyboard coverage.

Halley owns testing/backend_fixture.py, people_fixture.py and new real Requests
seed helpers. Send the required actor/state/use-case scenario list; never fabricate
server outcomes or seed guessed lifecycle rows. Existing prepareDiscoveryFixture
is not a Requests fixture. Boundary doubles supplement real FastAPI+Postgres.
Request a serialized browser lease before browser/full-PG runs; units/static may
run independently unless a coordinated freeze is active.

Global known blocker: aggregate619 units/339 boundary assertions passed but runtime
CLI EXIT1 on native RO at desktop photo contexts; PG phase did not start. Scoped
Discovery PG9/boundary57 remain separate valid evidence. No whole-gate rerun until
concrete fix/new causal evidence. Do not suppress diagnostics or add observer probes.
Run scoped Requests gates and accurately report limits; coordinate aggregate with
Halley rather than repeating known failing whole checks. No baseline weakening.
