# P05 deletion and proof-cookie recovery

Current controlled-boundary acceptance:47 unit checks CLI0 (unchanged95 coverage
threshold),45 normal browser cases CLI0 across all3 projects,90 reviewed references.
Raw `/tmp/peerly-p05-focus-unit9.log`, `/tmp/peerly-p05-http45-normal2.log`.
Actual Postgres6 normal comparisons passed CLI0/40.3s on freshhead50;
24 references reviewed. Raw `/tmp/peerly-p05-pg6-normal1.log`. Whole-app gates
and aggregate ResizeObserver diagnostics remain unresolved. Design P05 functional
consequences are shown here; detailed data retention remains on Privacy/Terms
only, without an extra consent checkbox.

| Boundary                            | Required behavioral and screenshot coverage                                                                                                                                        |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Signed-in preparation               | Opening the page makes no destructive write. Explicit Delete prepares one workflow; cancel closes confirmation without deletion. CSRF/Origin follow normal transport.              |
| Explicit confirmation               | Only the second destructive action sends actual workflow plus stable idempotency key. Pending prevents repeat submission; no automatic retry.                                      |
| Preparation failures                | Network/403/503 and invalid envelopes are actionable errors without invented workflow/confirmation. Safe reference only.                                                           |
| Unknown deletion result             | Lost/invalid response navigates to cookie-proof recovery; never states failure or success from uncertainty.                                                                        |
| Committed deletion                  | Actual receipt clears private account cache, mutations and session, then recovery reads canonical committed outcome.                                                               |
| Recovery independent of session     | Direct reload works without /me authority, workflow ID, query parameter or JavaScript proof token. No session guard redirects.                                                     |
| Pending recovery                    | Pending is not failure or assurance a delayed command cannot commit; explicit Check again obtains actual result.                                                                   |
| Missing/expired proof               | Actual404 is unknown, never deletion reversal or account existence oracle. Help remains reachable.                                                                                 |
| Recovery transient/invalid response | Safe reference and explicit retry; no stale cached success displayed while rechecking.                                                                                             |
| Actor/navigation lifetime           | Account replacement hides old preparation and ignores late destructive callbacks; destruction cancels owned reads and retires recovery cache.                                      |
| Accessibility/reflow                | Public Taiga confirmation, semantic headings/actions, real keyboard/focus,320px and200% text without horizontal overflow or clipped essential text.                                |
| Real FastAPI/Postgres               | Prepare/delete/status across two sessions, revoked normal session, retained identity/chat consequences and unknown-response reload. Fresh fixture lease after backend full PG END. |

Each implemented browser scenario must include behavior and a named screenshot
comparison in all three required projects. Raw screenshots alone do not satisfy
visual comparison. Controlled-boundary checks supplement actual PG integration.
No live provider calls, fake account state, credential storage, skipped tests,
masks, raised tolerance or diagnostic filters.

Proof recovery renders a request-specific confirmed result independently of /me.
After actual confirmed proof, a nonblocking ordinary session recheck retires stale
private query data and resolves revoked authority; a newer live account is not
assumed deleted. Preparation callbacks from an old actor must not retire a newer
proof query. These additional recovery regressions are source WIP until their
current unit/static/browser checks pass.

Fullscreen confirmation compares the actual visible viewport, with separate top
and scrolled action views at320px/200% text. The closed form retains a full-page
comparison. Paragraph/action horizontal bounds, native scrolling, one public
Taiga heading and real keyboard cancellation are asserted. Old full-page captures
of the fixed overlay/inert underlying page are retained under
`/tmp/peerly-p05-pre-heading-and-viewport-fix`, not accepted as baselines.

Current authored browser matrix:15 HTTP scenarios ×3 projects (45 cases), plus
2 actual FastAPI/PostgreSQL scenarios ×3 projects (6 cases). Complete new-source
formatter/typed ESLint, e2e TypeScript and Angular app ngc pass in
`/tmp/peerly-p05-complete-source-{format2,lint2,e2e2,ngc2}.log`.
Only the earlier6-scenario capture set has runtime evidence so far; the expanded
matrix is not called accepted until capture/review/normal comparisons finish.
Real PG uses controlled real accepted-chat cohorts, server revocation/proof and
exact retained message snapshots. The synthetic peer switch is a second identity,
not a claim of two independently issued sessions for the same account; all-session
revocation additionally has backend root/integration coverage.

The preparation action retains keyboard focus using standard aria-disabled and
aria-busy while its pending command guard prevents repeated writes. It remains
focusable for Taiga's normal dialog focus restoration. Real keyboard cancellation
at320px/200% returns to the original action in all3 browsers; no pointer handling,
direct focus mutation, delayed callback, tolerance or disabled font scaling.

Real deletion-specific cohorts include the controlled durable Google issuer/sub
source, as well as their session and institutional binding. The first run exposed
that missing source with a truthful401; the actual server guard remains unchanged.
Preparation now asserts real HTTP200 and the actual workflow schema. Confirmed and
lost-response cases prove revoked owner authority, request-specific proof reload,
a different still-live peer account and exact retained history/Deleted readonly
projection. They do not claim two independently issued owner sessions; exhaustive
same-account session retirement is covered by backend lifecycle integration tests.

## Design v2 implementation batch · 12 November 2026

Targets: P05-Delete explain/confirm/deleting/done/failure/unknown; W05-Deletion
public desktop/mobile. Peer deletion appearance belongs to the frozen Chats cohort;
operator frame is a separate owner, never a reason to invent public access.

Public same-route /account/delete now provides real in-app/web/sign-in/recovery/help
instructions and functional consequences in responsive native cards with the shared
public header/footer. Detailed retention stays in Privacy, following design-review-v2
rather than copying the obsolete W05 disclosure. Authenticated P05 uses native AppBar
and consequence card; preparation stays explicitly focusable aria-disabled/aria-busy,
with the existing guard preventing duplicate preparation. Native confirmation remains
fullscreen on mobile and a small floating dialog on desktop via public breakpoint.
No email/name is invented: IdentityResponse supplies neither. Original “cannot sign
in again” is superseded by owner-authorized distinct fresh account and reverification.

Proof status uses native BlockStatus for confirmed/pending/unavailable and the shared
public shell. No proof/workflow/session identifier is placed in URL or JS storage.
Unknown remains unknown; current live replacement accounts are never assumed deleted.
New guest behavior assertions cover genuine sign-in/recovery/privacy/help links,
functional copy and absence of preparation/deletion writes. Existing keyboard/focus,
unknown result, replacement actor and separate fresh registration regressions remain.

Current source needs combined build/matched reference capture and coordinated affected
acceptance; old47/45/PG receipts above predate this layout. No new screenshots/goldens,
unit/coverage/PG or staging-green claim from this source batch.
