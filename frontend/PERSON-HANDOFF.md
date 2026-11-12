# D02 person developer handoff

This is an implementation slice, delegated by the parent after backend acceptance. The new worker
owns only `src/app/screens/person/**` and the separate progress document assigned by the parent.
Halley retains routes, shared transport/session/helpers, generated contracts, providers, tooling,
package/config/theme/styles outside the screen, and all shared testing fixtures. No own subagents
or shared Git operations. Read root/frontend AGENTS and `docs/design-review-v2.md` first.

## Design and scope

Use `/tmp/peerly-design-v2/peerly-design-package/spec/boards/D02-Profile.json` and its corresponding
`design/D02-Profile.dc.html`. D02 is Full profile. **P02 is Notification settings**, not this slice.
S01-Report supplies the local report sheet; P04-Blocked documents related block semantics, without
a separate settings screen/route in this slice. Package AGENTS is not repository authority.

Implement real person read, current authorized display photo, local Block/Unblock and Profile report
surfaces against the actual generated contract. Omit request/review/send/chat/feedback actions and
relationship states lacking real APIs; do not fabricate disabled capabilities, compatibility scores,
Discovery decks or return routes. Initial task is not a role. Optional programme/year/about are not
verified academic facts. Keep the public theme/fonts and use supported Taiga controls/appearances.

The entry component contract is `Person` exported from `person.ts`. Halley added the lazy child route
`people/:personId` to `src/app/content.routes.ts`. Read the URL parameter
`personId` through ActivatedRoute; do not create a second router or edit root routes. Existing real
routes are `/`, `/onboarding`, `/terms`, `/privacy`, `/help`. Discovery-position return behavior awaits
its actual screen, not a fake destination. The parent coordinates any route-name correction.

## Shared implementation available now

- `src/app/api.generated.ts`: deeply readonly `Api` generated from actual53 unique paths/50 operations,
  raw source SHA256 `962f50af563bbd3bf1b41d9bbe85e5a7da8fe53276d796e52fc5f220d29cb000`.
  Read the exact schemas/operations; never handwrite duplicate server DTOs or edit generation output.
- `src/app/api-http.ts`: `readJson(http, relativeApiUrl, signal, runtimeGuard)` consumes abort through
  HttpClient; `writeJson(http, url, body, readonlyHeaders, runtimeGuard, method = 'POST')` also accepts
  `'PUT'`. Bodyless writes use undefined. Only same-origin `/api/v1/` is accepted. Supply the actual
  actor's CSRF token as `x-csrf-token`; deliberate writes use immutable `idempotency-key` from
  crypto.randomUUID(). No automatic social-mutation retries. Never forward these headers to storage.
- `readJpeg(http, relativeApiUrl, signal)` in the same transport returns validated JPEG Blob bytes;
  the consuming view owns object-URL creation/revocation, never Query/storage persistence.
- `ApiFailure`: safe status/code/requestId/retryAt only. Never render raw HTTP/provider error bodies
  or exception messages. Unknown mutation outcomes preserve the exact original payload/key.
- `src/app/screens/session.ts`: `sessionOptions(http, client)` returns the existing `['session']`
  query for actual GET/me, IdentityResponse|null, staleTime0/retryfalse. Revalidation cancels/removes
  `['account', ...]` reads before fetching.401 becomes null; other failures remain safe errors.
  This was moved from onboarding unchanged, with its tests, to avoid cross-screen imports.
- `src/app/screens/uncertain.ts`: `isUncertain(error)` means ApiFailure0/408/5xx. Also moved unchanged.
- `src/app/screens/brand.ts`: existing standalone `Brand` / `peerly-brand`, if needed.
- `src/app/content.routes.ts` supplies the **one existing QueryClient** to all content routes. Inject
  it; do not add another production provider/client/auth facade/store. Tests create isolated clients.
- `app.config.ts` supplies HttpClient, router, Taiga and runtime diagnostics; use the actual config
  for unit composition. Production files must not import another screen's internals.

Observe session readiness/capabilities directly, not a copied identity signal. Private query keys
start `['account', actor.account_id, ...]` and include person ID, photo version and paging parameters.
Do not start private reads from an untrusted/pending session. On401 revalidate the existing session;
clear local forms, old mutation observers/cache and private resources on logout/account replacement.
Old asynchronous results must check the original actor and component lifetime before changing UI.
The session factory clears reads; the consuming screen still owns its form/mutation/resource cleanup.

## Actual backend semantics

Read `docs/api.md`, Concrete peer profile and safety HTTP, plus generated DTOs:

- GET/people/{person_id} returns only its declared public fields, actual own_block and an owned
  access_context_id. Unknown/hidden/ineligible/blocked/deleted share404 person_unavailable. Do not
  distinguish the other side's block or infer why a person disappeared.
- GET/people/{person_id}/photo/{photo_version} is the current private display JPEG only. Permission
  is checked again after storage I/O.503 is an image-storage failure, not an empty deck/person proof.
  Never request originals/history or persist private image/credential data. Coordinate shared binary
  transport needs with Halley; do not edit api-http.ts or add a global image service yourself.
- GET/me/blocks is actor-bound cursor pagination, at most20 active own blocks per page. A missing
  target on the first page is not proof of no block. Deleted/unknown names follow actual projection.
- PUT/me/blocks/{person_id}: actual blocked/expected_version/context_id plus Origin/CSRF/idempotency.
  First target knowledge needs its owned disclosure context. A replay is an immutable historical
  outcome: invalidate/re-read canonical data, not a new-current-state assumption. Never invent a
  GET/me/blocks/{id} route or reveal/remove another side's block.409 uses explicit safe recovery.
- POST/reports supports only kind:profile and actual context_id/reason/comment. Other requires an
  explanation; maximum1000 **Unicode codepoints**, not UTF16 units.201 is a stored receipt, not proof
  of human review. Reporting does not automatically block. Context remains reportable after a
  previously disclosed target disappears, without granting another public read.429 carries safe
  retry metadata; unknown results must not claim either submission or nonsubmission.

## Testing and fixture ownership

Every implemented browser scenario needs behavior AND named screenshots, via `testing/visual`.
No runtime imports directly from @playwright/test in screen scenarios; type imports are fine.
Keep the scenario matrix and all unit/visual/PNG files under person. Maintain95% all coverage and
zero warnings; never weaken shared gates, errors, fonts or screenshot tolerances. Initial tests may
use HTTP boundary fixtures, clearly distinguished from real FastAPI/PostgreSQL verification.

Halley owns `testing/backend_fixture.py`, `testing/media_fixture.py`, `testing/verified-student.ts`,
proxy/Playwright/CLI configuration and the shared WebKit fixture. Request concrete driver/seed hooks
through the parent/Halley; do not edit them. Current fixture upgrades its unique schema to actual
HEAD (last normally accepted frontend checkpoint33; future heads require a coherent handoff), runs real auth/durable email/photo worker/codec with controlled Google/email/loopback HTTPS
storage. It never reads owner secrets, resets shared PG or calls live providers. New People seed
requirements must include real activated/verified/visible profile and photo/context/safety states.
`testing/people-fixture.ts` now exports `preparePersonFixture(page)`: the controlled driver seeds
verified identity/session facts using DB time, then actual profile/goal/photo/registration use cases
activate both people. It installs only the synthetic viewer cookie and returns viewerId/personId.
Actual People GET creates the owned disclosure context; do not manufacture contexts or capabilities.

Coordinate browser runs through Halley/parent: boundary and PG suites must not run concurrently
against the owned WebKit fixture. Existing settings: Node24 via the documented PATH,
PLAYWRIGHT_BROWSERS_PATH=/tmp/studymate-browsers,
STUDYMATE_WEBKIT_WS_ENDPOINT=ws://127.0.0.1:8879/; choose an agreed ephemeral test port. Do not stop
unknown user processes. The runtime gate fails native/page/console/forwarded diagnostics, including
ResizeObserver; there is no known-error exemption. That global intermittent issue remains open.
