# Discovery implementation handoff

Parent authorizes Aquinas to implement this slice immediately. Exclusive writes:
`src/app/screens/discovery/**` and `../docs/planning/discovery-progress.md`.
Person source remains frozen. Halley owns every shared file, root routes/providers,
generated contracts, transport/auth helpers, theme/assets, packages/tooling,
backend fixtures and the browser lease. No own subagents or Git operations.
Read root/frontend AGENTS, autonomous workflow and design review v2.

## Concrete deliverable and routes

Export standalone class **Discovery** from `screens/discovery/discovery.ts`.
Tell Halley when it is importable; Halley adds lazy `/discover` to the existing
content route group with its existing QueryClient. Do not add another provider or
edit shared routing. The route title will be `Discover · Peerly`.

URL owns mode, view, opaque cursor and optional `person` selected-card ID:

- Default `mode=find_help`; other actual modes are `offer_help`, `study_together`.
- Default `view=candidates`; the other actual view is `passed`.
- Changing mode/view removes cursor and selected person. Never silently switch a
  valid mode because its saved context is missing.
- `person` selects only a card actually present in the returned page; it is not an
  API parameter. Preserve the URL on full-profile navigation/back, then revalidate
  eligibility. Do not persist a copied deck/index in a store.

Actual profile navigation is `/people/:personId`. Existing setup entry is
`/onboarding`; no direct-editor query parameter exists yet. Label it honestly as
study/profile setup, not a guaranteed direct editor. Halley owns FE03.5 and will
coordinate its eventual completion entry with the actual selected mode.

This slice delivers Discovery read, private pass, server Undo and reconsideration.
No Requests composer/preview consumer is integrated yet, despite mounted API
declarations. **Omit request CTA/right-swipe preview, fake navigation, Requests/Chat
badges and nonexistent bottom-nav destinations.** Genuine profile/setup links and
pass buttons are allowed. Do not promise a gesture or action that is absent.

## Design reference

Use the reviewed v2 package at `/tmp/peerly-design-v2/peerly-design-package/`:

- `spec/boards/D01-Discover.json` and `design/D01-Discover.dc.html`: mode/card,
  relevance, pass and photo failure. Any next-card hint must use a real returned
  card and remain noninteractive. No synthetic candidates.
- D04-Empty: loading, offline/failure, context required, no relevant candidates,
  exhaustion and broader subject relevance are distinct states.
- D05-Passed: empty/list/reconsideration. Reconsidering does not promise front
  placement; server ranking remains authoritative.
- D02-Profile is the existing separate Person route. D03 preview/state boards are
  outside this slice until a genuine Requests lifecycle consumer is coordinated.

Offer-help context covers the saved help revision, not a selected-subject request
parameter. Study-together selection must not silently opt a goal into sharing.
The page projection has no current-goal title, feedback endpoint or request-send
capability. Do not invent those fields or derive a current-goal title from a peer's
relevance. No shared readiness/context-label helper exists yet. Coordinate any
necessary additional actual source read before expanding this bounded slice.

Use existing public Taiga APIs/theme tokens and existing approved assets. No
package export CSS/runtime, internal selectors, new fonts/theme exceptions or
global styles. Request a curated asset from Halley if the existing public assets
are insufficient; do not edit shared assets/provenance yourself.

## Actual API baseline

Generated `Api` is actual51 paths/58 operations, source hash
`31ab54db052a1f5f0bb31ff3b78747c0b6fe992ea4c7c3c91543c5fcc648fba7`.
Source export: `/tmp/peerly-actual51-goal-sharing-openapi.json`. Previous50 paths
and schemas are unchanged. Drift, app/spec/e2e typing and6 contract checks passed.
Read `docs/api.md`, implemented Discovery section; the older proposed route table
is historical. Never handwrite duplicate server DTO interfaces.

Shared declarations subsequently advanced to actual53/60, source SHA256
`962f50af563bbd3bf1b41d9bbe85e5a7da8fe53276d796e52fc5f220d29cb000`;
all51 operations/components remain unchanged. Shared types/routes were frozen at
that checkpoint before the worker unit lease. This does not expand Discovery scope.

`GET /api/v1/discovery?mode=...&view=...&cursor=...` returns
DiscoveryPageResponse: nullable tagged context, people, next_cursor, empty_reason
and undo_pass. No limit, subject selector or offset parameter exists. Context is:

- find_help/study_together: mode, goal_id, goal_version;
- offer_help: mode, help_version.

DiscoveryCardResponse contains id/display_name/about/photo/version/own_pass and
the declared relevance fields only. Relevance reasons are can_help, you_can_help,
shared_goal; use actual subject/topic/reciprocal projection, no scores or matching
algorithm in the browser. Photo exposes an actual private display URL/version;
permission is checked again when reading bytes.

Private query key: `['account', actorId, 'discovery', mode, view, cursor]`. Every
server parameter belongs in the key, selected-card UI state does not. Consume the
AbortSignal and preserve same-actor page/navigation semantics without mirroring
query state. Refetch canonical eligibility when returning from Person; a block or
hidden/deleted target must not survive merely because a cached card exists.

`PUT /api/v1/discovery/passes/{person_id}` takes generated ChangePassRequest:
the exact returned context, passed, expected_version, optional undo. Use actual
Origin/browser behavior, actor CSRF, immutable idempotency key and no automatic
mutation retry. Never add an actor selector. Preserve the exact intent on unknown
outcomes; prevent stale actor/lifetime work from sending or updating a new screen.

The response is a retained historical receipt, not proof of current state after
replay. Refetch canonical discovery/passed projections after success/replay.
Handle pass_version_conflict, discovery_context_changed and idempotency_conflict
with explicit recovery, never an automatic new-version write. invalid_cursor422
requires a first-page recovery. Do not infer a person's current pass state from
absence on only the first page of a paginated view.

**Pass Undo has no ten-second countdown.** GET's undo_pass is server-owned until
the next committed deck decision; undo writes passed:false, undo:true with its
actual version/context. pass_undo_unavailable409 is authoritative. The ten-second
decline Undo belongs to Requests, not this decision. Reconsider uses the actual
owned pass and does not notify or redisclose the peer. Missing own history is the
server's version0/false/null projection; do not create local history.

Empty reasons are context_required, no_relevant_people, exhausted and
no_available_passed_people. No fake counts, unrelated fallback candidates,
client ranking, background activity warming or automatic exposure confirmation.

## Shared interfaces available

- `screens/session.ts`: sessionOptions(http, client), the existing `['session']`
  query, IdentityResponse|null.401 becomes null; revalidation cancels/removes
  account-prefixed reads. No private read before resolved verified active actor
  and actual capabilities. Guest/restricted states use genuine recovery links.
- `api-http.ts`: abort-aware readJson, deliberate writeJson (method PUT supported),
  readJpeg and safe ApiFailure status/code/requestId/retryAt. Never echo raw bodies.
- `screens/uncertain.ts`: isUncertain for status0/408/5xx.
- `screens/brand.ts`: public Brand component if needed.
- Inject the existing QueryClient. Prefer public QueryObserver/MutationObserver
  with typed subscriptions/cleanup, as in the accepted lead integration. Avoid
  compatibility imports that pull Angular's namespace into the initial bundle.
- Image resources are actor-bound. The view owns/revokes object URLs; never persist
  credentials, private bytes, image URLs or copied identity/deck state. No imports
  from Person/onboarding internals, no speculative store/facade/event bus.

Halley's readiness query key for FE03.5 will be
`['account', actorId, 'onboarding']`; no shared factory currently exists. Ask before
adding a second consumer, so canonical state is not duplicated under another key.

## Tests and lead-owned fixture extension

Keep unit/boundary/fullstack specs, typed fixture values, PNGs and scenario matrix
under discovery. Use real Angular/HttpClient/query behavior; test fixtures may use
`satisfies Api[...]`, not duplicate interfaces. Every browser scenario must include
behavior plus named screenshots through `testing/visual`, zero tolerance and no
runtime-error exemptions. Maintain95% thresholds and zero warnings.

Cover all modes/views/context-required and distinct empty states; cursor recovery,
safe network/server failures, unavailable JPEG, valid full-profile navigation,
pass/Undo/reconsideration,409 and uncertain immutable replay, stale actor/cancel,
320px/200%/keyboard and cleanup. Candidate PNG creation is not ordinary acceptance.
The global native teardown error remains open; a passing assertion count cannot
override a failing CLI gate. Do not patch/filter it in this slice.

Current real fixture baseline: fresh HEAD33 and48 normal scenarios passed with
runtime CLI EXIT0. Controlled provider/storage boundaries only; no live services,
secrets or shared DB resets. Halley owns `testing/backend_fixture.py`,
`people_fixture.py`, new discovery seed/helper and every shared config/driver.

Available `preparePersonFixture(page)` seeds two verified, genuinely activated
canonical-goal students with real photo worker/registration. It does **not** yet
seed help selections or shared-learning opt-in, so it is not a positive Discovery
fixture for all modes. Do not fake those capabilities or patch SQL activation.

Lead-owned next hook: `testing/discovery-fixture.ts` will export
`prepareDiscoveryFixture(page, namespace) -> {viewerId, personId, subjectId, subjectLabel}`.
Namespace is required: `modes/${project}`, `pass/${project}` or `undo/${project}`
for the three fullstack scenarios, where project is the actual configured browser
project. Driver-only `POST /__fixture/discovery` receives `{namespace}`. Each of
the nine scopes gets a distinct real canonical fixture subject with a stable human
label and correct domain normalization; identities use DB time, then actual
profile/goal/help/photo/registration use cases establish readiness/shared goals.
This isolates matches through real server subject matching, without SQL resets,
hiding other tests, fake filters or falsely normalized duplicate SQL labels. Synthetic cookie handling stays inside the helper. No credential values
or private hashes in tests/logs. Do not run its new namespaced fullstack cases before Halley confirms
the multi-cohort fixture proof. Do not hardcode SQL as the returned subject label. Request concrete paging/ineligibility/race fixture variants from Halley;
no shared-file edits or backend-test helper imports.

Real PG minimum: relevant card/private JPEG for real mode contexts, pass persists
across reload into passed view, explicit reconsideration and real server Undo.
Mock boundary scenarios supplement these; they do not replace them.

All browser work, including Angular's real-Chromium units, needs a lease through
Halley before launching. No concurrent WebKit/boundary/PG runs. Static reads,
typing/lint/format may proceed independently. Use the existing Node24/browser
environment and task port after agreement; do not stop unknown user processes.
Report completed slices, concrete shared dependencies and changed paths in your
separate discovery ledger, not the backend or Halley ledger.
