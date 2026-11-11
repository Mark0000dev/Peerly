# Student frontend code candidate — 9 November 2026

This is a source-complete candidate for the coordinated internal-team staging batch.
It is not final acceptance, a runtime-clean claim, native delivery, or an external
student launch. Operator expansion remains paused.

## Final source integration

- `src/app/content.routes.ts`: real support/contact recovery, notification preference,
  own profile overview, profile/goal/help editors, visibility and blocked-list routes.
  Editors use their real `canLeave()` contracts. There is one route-scoped QueryClient.
- `screens/student-navigation.ts`: shared Discover/Requests/Chats/Profile navigation
  used by the four actual student surfaces, with public router active-page semantics.
- `screens/onboarding/profile-page.*`: actual profile, current goal, help areas,
  visibility, feedback summary, settings links and authenticated sign-out. No fabricated
  historical goal list, role switch, notification count or background push capability.
- `screens/onboarding/profile/complete-goal.*`: explicit confirmed completion against
  the actual goal/version, immutable idempotent retry after an uncertain result,
  replacement-owner and delayed-confirmation guards, canonical query invalidation.
- `screens/onboarding/profile/blocked-people.*`: actual cursor-based owner list,
  deleted-account labels, CAS unblock, same-command recovery and actor retirement.
- `screens/draft-exit.ts` and `screens/verified-actor.ts`: actual shared editor leave
  confirmation and fresh verified authority. A retained cached actor is ownership,
  not permission to issue a private command during an unknown session check.
- Profile/goal/help workspaces retain form-owned drafts during same-actor revalidation;
  replacement/logout/destruction retire them. Captured editing source versions expose
  remote changes instead of silently rebasing a draft. Explicit reload adopts canonical
  state. Photo File/crop/upload intent lifetime is separate from command authority.
- G01/O02 optional AI widgets are integrated into the real Goal/Profile parents. Only
  explicit Apply changes a draft; normal Save remains separate. Real unavailability
  leaves manual flows usable. Photo guidance is bound to the actual photo identity
  and version; it neither replaces nor automatically uploads a photo.
- F03 own summary is integrated into the profile overview; the actual public summary
  remains in the peer profile. Existing study feedback/outcome and chat image source
  checkpoints remain part of this candidate.
- Aquinas' `screens/help/contact/**` and `screens/notifications/**` source is complete;
  exact exports and recovery semantics are in `STUDENT-SUPPORT-HANDOFF.md` and
  `../docs/planning/student-support-frontend-progress.md`.

P02 persists `messages_and_requests` or `all_updates`. Device/background delivery is
unavailable in this preview; browser permission is not evidence of delivery. There
are no OS permission requests without a real delivery consumer, analytics choices,
security-email toggles or native push completion claims.

## Contracts and regression definitions

Generated readonly DTOs and `contracts/openapi.json` come from the actual final
head52 exporter: 96 paths / 109 operations, source SHA256
`ed527677f73fad580877c076dd999b21e6f5f9d8a63ab20ae5c55aee5f94348b`.
No future routes or hand-authored DTOs were added.

New regression definitions cover fresh authority vs retained ownership, actor
replacement, same-actor form identity, remote CAS changes, delayed completion
confirmation, immutable lost-response recovery, malformed block receipts, P01/P04
behavior plus screenshot checkpoints, and actual PG-backed profile/completion after
registration. Existing scenario definitions cover the Profile/AI/feedback/image/
support/preferences integration. Definitions are not execution evidence.

Final realPG orchestration now uses six fresh isolated Alembic-head cohorts:
ordinary/anonymous and authenticated-support separately for each of mobile Chromium,
mobile WebKit and desktop Chromium. This preserves both the genuine Google-start
source-admission budget and the five/source/day support limit. No request.client,
quota, proof, server clock or recovery behavior changes. Each invocation owns its
schema, fixture, reports and cleanup; never reset the shared database.

## Final batch still required

Freeze the exact source manifest with the parent before the consolidated unit,
coverage, tooling, static, clean-install, production build and reviewed browser/real
PG matrix. Review all intended area-copy/navigation/profile layout references as
one batch. Preserve all strict diagnostics and resource cleanup assertions.

The aggregate Chromium ResizeObserver diagnostic remains unresolved. Historical
scoped passes and assertion totals do not retire that global runtime failure.
The narrow accepted WebKit OPEN/ZOOM capture adapter remains limited to those
Preview states and is not a ResizeObserver fix.

Parent owns deployment files, credentials, real-provider/staging smoke and final
Git publication. Real AI readiness, native delivery and the mandatory monitoring
required before external users remain separate acceptance boundaries.

## Parent-coordinated final command sequence

Use the pinned Node/npm and task-local browser dependencies, persist raw stdout and
stderr for each command, and retain its actual exit status. Serialize browser suites
and obtain the backend's named resource/source lease before the real PG matrix.

1. `npm ci` — reproduce only the approved pinned dependency patch and install checks.
2. Run the existing `contracts:check`, `format:check`, `lint`, `lint:styles`, `knip`,
   `typecheck`, `test:tooling`, `test:unit` and `build` package scripts once in the
   coordinated final batch. Unit coverage and production warnings/budgets stay strict.
3. `npm run test:public -- --workers=1`, then
   `npm run test:integration -- --workers=1`, then
   `npm run test:fullstack -- --workers=1`. The fullstack script owns cohort
   filters/projects and creates one fresh fixture per cohort. Reports and test
   results use distinct `<cohort>-<project>` subtrees. Any failed cohort keeps the
   whole command failed; timeout/cancellation stops subsequent fixtures. All keep
   the unchanged runtime guard. Scoped diagnostics use `tooling/browser-gate.mjs`
   directly. Do not rerun a whole matrix while known RO remains without a fix.
4. Parent executes the actual provider/staging smoke with authorised services;
   frontend source checks do not establish deployed integration or AI readiness.

## Executed final boundary —9 November2026

Clean install/approved dependency patch, contracts, static gates, whole1492 units
and95%global coverage passed; production initial513.84kB remains under525kB.
After one concrete browser/fixture fix batch, tooling69 passes, all static gates
and build pass; whole units were not repeated for CSS/templates and test-driver
changes. Public no-JS3 pass. Frozen HTTP1080 completed across disjoint374/706
partitions (first aggregate600s timeout124);996 assertion passes/84 failures were
preserved. Bounded affected120 gave118/2, then genuine Support layout/readability
fix gives30/30. Subsequent Help/P02/F03 concrete fixes give33/33, CLI0;42 intentional
candidate refs reviewed. The same33 normal comparisons pass CLI0 in39.5s without
updating references; this remains bounded evidence, not full1080 green.

RealPG228 distinct scenarios completed across interrupted186 (external143), exact
remaining39, and authenticated3:188 assertion passes/40 failures. Cleanup verified.
One bounded repair46, in fresh schemas per project, gives43 passes/3P02 driver
failures, all cohorts exit1. The three failures waited for a Save control that is
correctly replaced on success; its exact actual "Use current saved preference"
readiness assertion was corrected after END and static-checked. Exact P02three
then passes3/3 capture and3/3 normal (25.5s). All412 PG reference deltas were reviewed;
a desktop reload READY image showing loading was rejected, and the driver now
waits for actual conversation, settled preparation and resumed SSE. Exact reload
three passes3/3 capture and3/3 normal (29.7s); real APIREADY/zero implicit sends and
explicit-send actual image FK assertions remain. Original desktop strict-locator
failure2/3 is preserved before its semantic Selected conversation scope correction.
Each normal cohort uses a fresh head52 schema, explicit lease and verified cleanup.
No API/guard/timeout/coverage/pixel or runtime waiver. Global Chromium RO remains
OPEN; no full228 normal or1080 runtime pass is claimed. Other PG references retain
capture/review evidence. All runners ended; final ledger records a bounded causal
RO proposal and the remaining parent-owned real-service/staging acceptance.

Raw logs, partition metadata, failed traces, reference reviews and source deltas:
`/tmp/peerly-frontend-final-acceptance/`. The progress ledger records exact boundary
hashes and pending commands. Parent coordinates the next frozen acceptance window;
no automatic broad reruns or deployment readiness claim.
