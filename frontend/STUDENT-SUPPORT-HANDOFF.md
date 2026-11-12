# A04/W04 support and P02 notification preference — code-first handoff

This assignment supersedes Aquinas's completed AI implementation scope. Parent
explicitly approves these exclusive NEW paths:

- `src/app/screens/help/contact/**`
- `src/app/screens/notifications/**`
- `../docs/planning/student-support-frontend-progress.md`

Keep earlier AI production code unchanged except a concrete coordinated integration
fix. Halley owns existing Help page, root routes/navigation/session/transport,
generated DTOs, shared fixtures, Profile/AI parent mounting and overall candidate.
No other shared-file edits, Git operations, subagents, provider calls or deployment.
Do not wait for routine permission: implement the full ready code and meaningful
tests/matrices first, final test batch later. No intermediate suites or captures.

## Actual code contract, not tested readiness

Head52 actual enabled exporter now has96 paths/109 operations. Halley regenerated
`api.generated.ts` and `contracts/openapi.json` using the existing pipeline after
the real recent-receipt GETs were mounted. These are actual generated readonly
DTOs, **not a tested/frozen backend or PG-ready claim**. Read current `docs/api.md`
and source semantics directly. Coordinate with backend Noether
01a1b436-9c16-7572-91c6-34b826d23a07 and Plato
01a1c007-a557-7c53-9a83-28a1aa6c13fc for concrete ambiguities; never invent fields.

Actual routes:

- POST `/api/v1/support-context`, empty SupportPreparationBody, same-origin
  proof-cookie preparation; SupportPreparationResponse CSRF token/expiry.
- POST/GET `/api/v1/support-cases` and GET `/api/v1/support-cases/{case_id}`:
  anonymous browser-proof owner, independent of login. POST idempotency/CSRF
  headers exactly as exported. RecentSupportCasesResponse contains receipts only.
- POST/GET `/api/v1/me/support-cases` and GET `/{case_id}`: actual session owner.
  Recent receipts make lost-response/reload recovery possible without retained RAM
  case ID or idempotency key. Never interpret a proof as login or attach/rebind an
  anonymous case to a later Google account.
- SupportBody: topic actual SupportTopic; reply_address<=254, message<=4000,
  optional details<=2000. Receipt has case_id, received_at, changed_at, status,
  version. Actual statuses received/in_review/resolved. No reply/inbox/delivery
  promise beyond these fields; no invented support ticket body retrieval.
- GET/PUT `/api/v1/me/notification-preference`: PreferenceResponse mode/version/
  changed_at, PreferenceBody mode/expected_version. One enum field with TWO values
  `messages_and_requests` and `all_updates`, not two boolean toggles. PUT actual
  required idempotency key and CSRF; no arbitrary opt-out value or quiet-hours.

## Concrete exports for parent routes

Implement standalone public route components:

- `SupportContact` from `help/contact/support-contact.ts` for `/help/contact`.
- `SupportRecovery` from `help/contact/support-recovery.ts` for
  `/help/contact/status`. Optional ordinary case ID/owner-scope URL selection may
  use validated query parameters; no proof, key, token, message or reply address
  in URLs or persistent storage. Initial recovery always supports actual recent
  receipt discovery when no ID is present.
- `NotificationPreferences` from `notifications/notification-preferences.ts` for
  `/profile/notifications`.

Use existing shared QueryClient/sessionOptions/readJson/writeJson/ApiFailure and
trustedVerifiedActor as appropriate to the ACTUAL backend guard. Do not create a
second query provider or cross-screen internals imports. These full route consumers
can render their own account checking/retry/continue-to-real-onboarding states;
parent adds routes and Help/Profile links after export readiness. Send exact
exports and canLeave contract when coherent. Use public Taiga controls only.

Read A04, W04 and P02 approved boards. Minimal broad-area terminology corrections
apply, but support topics are actual enum labels. Signup/legal agreements and
mandatory analytics remain Terms/Privacy only; no consent/analytics settings.
Saved notification preference is distinct from OS permission, security email and
actual native push delivery. No fake permission grant/request, native token setup
or promise that a push was delivered. Native delivery remains a separate phase.

## Ownership, recovery and privacy

Server data/status/receipts live in actor- or proof-scoped Query caches. Forms own
unsent inputs. Unknown create outcomes are not confirmed failures or successes;
keep the same immutable body/key for an explicit retry while the intent exists,
and expose actual recent-receipt recovery after reload/lost response. Cookie proof
is HttpOnly and is never read, copied to JS/storage or placed in URLs. Missing or
expired proof is not proof that no case was created. Canonical receipts/status
must be fetched under their actual owner; never discover cases by student email.

Pending/failed session revalidation is not authority for new authenticated writes.
Preserve same-actor form drafts, block commands while checking, retire on actual
account replacement/logout/destroy and guard late callbacks. Anonymous browser
proof ownership remains separate from the session, including after login changes;
use honest browser/account recovery labels and coordinate exact server semantics.
Never store or log private support content/reply addresses in telemetry or test
command output. Do not invent a case chat, operator reply or notification channel.

Handle context expiry, validation,429/503, uncertain admission, replay snapshots,
version conflicts, lost responses, recent-list/status errors, empty recovery,
auth changes, cancellation/leave confirmation and long text accessibly. Preference
replay must not overwrite a newer canonical preference with an older receipt.
No mutation auto-retry, optimistic delivery claim, localStorage or sessionStorage.

Author real component/query/form and contract tests plus behavioral/screenshot
scenario matrices on all three projects,320/200%, keyboard/focus/overflow. Author
real FastAPI/Postgres cases against parent-controlled fixtures; request exact new
hooks/namespaces rather than editing them. Do not run these intermediate suites.
At code completion report exact files/features, remaining actual-contract gaps and
final batch commands/evidence needs. Global ResizeObserver remains open and must
never be filtered or declared fixed by these features.
