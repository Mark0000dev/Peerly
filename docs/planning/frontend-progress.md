# Frontend progress

## Owner requirement reaffirmed — 11 November 2026

The full design-v2 fidelity/usability pass is mandatory after the current
infrastructure and feature integrations, without interrupting them. Its execution
and exit criteria are recorded in `frontend-roadmap.md`; the prepared coverage
inventory is `../../frontend/DESIGN-V2-FIDELITY-INVENTORY.md` (50 active design IDs,
84 boards, all actual visual comparisons still pending). Expand each applicable
screen into its real states during that phase and record reference-versus-build
captures, discrepancies, approved deviations and corrections. Existing regression
goldens are not evidence of design compliance. Mascot animation requires separate
real-build normal/reduced-motion evidence; no completion claim follows from this
planning receipt. This update changes no application source or acceptance status.

## Mascot native production proof END — 11 November 2026

Original animated SVGs plus native picture/source reduced-motion fallback are
accepted for the bounded Home/Onboarding artwork scope. Diagnostic nginx image
19555b985dfb23b8424a615e448165afbb96f34ffdceadecec8fa165e270f6e4;
final three browser projects × normal/reduced motion: six PASS, CLI0, diagnostics[].
All six artwork variants move in normal mode; reduced mode selects still vectors,
has zero changed pixels and matches all six reviewed references exactly. Actual
HTTP asset hashes, complete viewport geometry and strict native diagnostics stay
asserted. No real providers/credentials or deployment were involved.

The historical WebKit negative was capture cadence, not a new production defect:
public frame-clock control proves changing computed SVG transforms. Sampling at
600ms (quarter of the shortest continuous artwork cycle) fixes observation without
altering animation or comparison criteria. Both modes use the same observation
window. Final raw evidence: sibling
`.peerly-ops/frontend-client-observations-20261111/picture-fallback-delta/capture-final/`.
Runner lint/format CLI0; prior 32 App/Onboarding tests, template/style checks and
522.73kB production build remain valid for the unchanged application/artwork bytes.
See `frontend/MASCOT-MOTION-ACCEPTANCE.md`. Final supplement preserves the original
13-file receipt and adds reviewed references/documentation plus runner-only cadence
correction. Parent retains Git/publication authority. Global RO and the full
design-v2 screen/state fidelity phase remain explicitly unresolved.

Owner: Halley. Updated:9 November2026 (Europe/Moscow).

## Execution window

**Latest owner workflow supersedes intermediate acceptance sequencing:** finish all
remaining student/internal-staging code and configuration first. Write meaningful
tests alongside implementation, preserve existing failures/evidence, and batch
final checks on a frozen coherent candidate. Do not start repetitive slice unit,
coverage, screenshot capture/review/normal or PG loops. Fast compilation/types/lint
are allowed at coherent integration boundaries; focused reproduction only for a
concrete implementation-blocking defect. Final unit/static/build/clean-install,
browser+realPG reviewed matrix and real-provider/staging smoke remain mandatory.
No warning/coverage/security relaxations or globalRO green claim. Operator paused.
Current lead has completed the coordinated realPG partitions and one concrete fix batch. Final bounded P02/reload normal comparisons passed under explicit fresh Noether leases; all runners and leases ended. No broad matrix repeat. Halley completed offline PG reference review while Aquinas remains on parent hold.

### Coordinated final acceptance — static/unit/build boundary

Latest candidate static/unit/build is accepted locally, not the full browser/runtime
or real-service gate. Clean `npm ci` reproduced the approved font-watcher0.6 patch;
contracts/types/format/ESLint/Stylelint/Knip pass, tooling68/68 pass. Whole unit1492/1492
in85files passes with95.65%statements,95.04%branches,96.68%functions,98.11%lines.
Exact logs `/tmp/peerly-frontend-final-acceptance/unit-candidate-final.log` and
`unit-candidate-final-lcov.info`; SHA256 respectively
`95b45dda69f699fa0da322e743983a7e7152d89d41c3520202a9789649354708` and
`64c9a6e8e261c7ecfa60a2c47e416fded6869d54388b70a2430693cb72bbbae1`.
Latest production build is513.84kB under525kB, no warning, one prerendered route;
`build-candidate-final.log`. Full final static commands/statuses and every preserved
RED attempt are in the same artifact directory. No threshold or diagnostic waiver.

Concrete fixes cover immutable retries when canonical state changes, applying the
latest canonical read only after a committed write, unbound query namespace cleanup,
one status read for a newly created photo intent, and terminal-upload race feedback.
P01 visibility read errors are retryable; uncertain logout rechecks real identity
before allowing commands. Regression drivers now respect fresh authority, native
button readiness, explicit discard, request chronology and destructive HTTP matching.
The new P01/Photo/support/preferences boundary regressions exercise these contracts.

The parent approved the narrow Support PG dynamic receipt treatment: full stable
form/unknown-submit comparisons, full raw unmodified receipt/recovery attachments,
exact live ID/time/status DOM assertions, and controlled-HTTP full receipt/status
comparisons. Raw attachments are not visual comparisons. Overflow/runtime checks stay.

Noether released the explicit head52 realPG lease after backend repair END. The final
realPG matrix started with clean owned-resource preflight, two fresh migrated cohorts
(225 core/anonymous,3 authenticated support), count-derived aggregate budgets39.5min
and2.5min. No shared database reset or per-test timeout changes.
The aggregate ResizeObserver defect remains OPEN until the actual browser guard
passes. npm audit records26moderate dependency nodes, one minimatch advisory, zero
high/critical; no automatic dependency/lock changes were made.

### Final browser partitions and bounded fixes —9 November

The frozen HTTP matrix covered exactly1080 distinct cases in disjoint partitions:
original600s invocation exit124 (346 passed,28 failed,374 completed), then the exactly
identified706-case remainder under the approved30min aggregate budget exit1 (650
passed,56 failed). Combined996 assertion passes/84 failures; this is NOT one full
passing run. Metadata/coverage: `/tmp/peerly-frontend-final-acceptance/http-candidate-combined.json`.
All failed cases, raw CLI diagnostics and original references remain preserved.

Concrete fixes:31 missing `.png` checkpoint suffixes; Requests assertion scoped to
Existing pair rather than legitimate global Chats navigation; actual study-prompt
visit mutations distinguished from sending; keyboard scroll targets actual native
textfield; Person boundary supplies its newly consumed real feedback-summary DTO.
The exact affected120-case batch gave118 passes and2 actual A04 narrow overflow
failures. Supported semantic minmax grid tracks, external native labels and wrapping
submit layout fix the real overflow/clipping. Final complete Support HTTP file:
30/30 passes,CLI0,51.6s, all3 projects; `support-layout-http.log`. Aquinas reviewed
all3 narrow200% images; full Support/P02 candidate image review follows offline.
Latest direct format/ESLint/Stylelint0 (`support-layout-static-direct-status.json`),
production build0 unchanged513.84kB (`support-layout-static-build.log`). Earlier
snap-npx checks are NOT relied on; the direct pinned Node CLI results are authoritative.
No application logic changed after the accepted1492-unit boundary in this layout fix.

Final PG started under explicit Noether READYhead52 after HTTP END and free ports.
`pg-preflight.json`, `pg-candidate.log`, `pg-matrix-status.json` retain exact evidence.
Two fresh schemas separate genuine support source quotas; dynamic receipt recovery
keeps full raw attachments and exact API-derived DOM assertions, not golden claims.
Aggregate Chromium ResizeObserver diagnostics remain OPEN; scoped passing cases do
not retire that global blocker. No error filters or threshold changes.

RealPG original command was externally interrupted with143 after186 completed cases
(148 assertion passes/38 failures), before its39.5min orchestration deadline. This
is an execution interruption, not an application timeout. The wrapper could not
flush its final status/report. Exact raw outcomes and disjoint coverage are in
`pg-interrupted-partition.json`; no earlier failure is discarded by resumption.
All owned listeners closed. The sole orphan schema, absent in preflight, was
identified as this interrupted fixture, actual head0052_student_support verified,
then ONLY that disposable schema dropped with0otherDBsessions. Evidence:
`pg-interruption-owned-schema-cleanup.json`. No shared database reset.

Parent explicitly authorised exact remaining39 core desktop +3 authenticated
support scenarios in fresh schemas. `run-pg-remainder.mjs`, `pg-remainder.log` and
`pg-remainder-status.json` retain the count-derived8.5min/2.5min budgets and outcomes.
No source/test changes during either active candidate partition. Known failing
families and genuine Help/P02 clipping defects are queued in one prepared fix
batch outside the repository, never silently accepted as screenshots.

### RealPG END and one concrete fix batch END

Exact228 scenario coverage is verified disjoint in `pg-candidate-combined.json`:
original186 external143 gives148 assertion passes/38 failures; remaining39 gives
37/2 CLI1; authenticated3 gives3/0 CLI0. Combined188/40 is NOT single green.
Both original and repair cleanup prove no owned schemas/sessions/listeners remain.
No backend contract/source change was required.

The one batched fix preserves real Help action overlap and P02 clipped Save as
product defects: supported semantic wrapping layout and native text-Range bounds,
non-overlap/overflow/keyboard200% regressions fix both. Source changes also isolate
actual deletion fixture namespaces, distinguish exact study-prompt visits from
message/ACK writes, scope pair actions against global navigation, use truthful
storage-key checks, process the genuine worker until the captured own photo ID is
READY, settle the actual initial SSE revalidation before private safety sheets,
and supply the real blocks read in summary-only HTTP fixtures. Normal production
quotas/clock/source IP stay unchanged. Default fullstack orchestration now isolates
six fresh project/source-support cohorts; tooling69 validates partition/artifact/
cancellation behavior. Final format/lint/styles/types/Knip/build pass, initial513.84kB.

Affected HTTP33/33 capture CLI0 (`pg-fix-http.log`) and42 reviewed intentional
candidate images (`pg-fix-http-reference-review.json`) establish the layout fixes,
including real font28->17 restoration. The subsequent exact33 normal comparisons
also pass CLI0 in39.5s (`final-normal33.log`), without updating references. This is
bounded comparison proof, not a full1080 normal/runtime green.
New93 unit-failure diagnostic images were hash-preserved in
`unit-failure-diagnostics-preserved/` and isolated from source; no existing golden
was removed. Full1492-unit result remains the earlier accepted logic boundary.

Explicit named FE-PG-repair46 lease completed3 fresh project schemas:15mobile,
12WebKit,19desktop, budgets270/240/310s.43 assertions pass;3P02 driver failures keep
all3 cohort exits1. Original40 failures/143 evidence stays intact. The remaining
assertion incorrectly waited for Save after success; actual UI replaces it with
Use current saved preference. Corrected exact actual control after END, scoped
format/lint/e2e types pass. The exact three-project P02 verification subsequently
passes3/3 CLI0 in27.1s (`p02-three.log`), with owned cleanup verified. `pg-repair46-status.json`, raw log/traces and
`pg-repair46-cleanup.json` retain proof. No automatic follow-up runner or source
lease extension. Global historical Chromium RO remains OPEN despite no RO observed
in this bounded repair. Halley reviewed all412 PG reference deltas in three
contact-sheet inventories; six C03 reload frames were additionally inspected natively.
The prior desktop READY frame showed loading and was rejected. Its driver now waits
for cursor-bearing SSE reconnection, the actual Selected conversation heading,
settled preparation loading and enabled composer; real API READY/empty history/
zero implicit sends remain asserted. First capture2/3 failed only because the desktop
heading locator matched list and detail; scoped semantic-region correction gives
3/3 CLI0 in30.6s (`c03-reload-selectorfix.log`). Original failure preserved in
`c03-reload-first.log`. No production/auth/clock/quota or diagnostic change.
`pg-reference-final-review.json` records412 current hashes, review method and raw
versus compared Support receipts. Exact normal comparisons now pass without snapshot updates: P02three3/3 CLI0
in25.5s (`p02-normal3.log`) and C03reloadthree3/3 CLI0 in29.7s
(`c03-normal3.log`). Each used its own fresh head52 schema and named READY/START/END;
cleanup proves schemas[]/other sessions0 and ports8768/8769/38385 free. Their runtime
guards stayed clean. There is no active runner or backend hold. Passed46/228 were
not rerun wholesale; original aggregate failures and interrupted143 stay preserved.
Other PG references have capture/review evidence, not an invented full normal pass.
Full runtime and parent-owned real staging/service smoke remain pending.

### Frozen acceptance handoff and bounded RO next step

Global Chromium ResizeObserver remains OPEN. Recent scoped zero-diagnostic runs do
not retire the original HTTP/PG aggregate failure. Native tracing observed the
font-watcher foreign iframe BODY and same-value root font-offset0 writes around
snapshot resize/restore and teardown; the skipped observer target and causal write
remain unidentified. No diagnostic suppression, application lifecycle hack or
unproved scheduling patch was adopted. Only the proven pinned iframe-border source
correction is installed; real28->17 font restoration remains covered.

Halley owns the next bounded causal investigation proposal, not another matrix:
use an immutable temporary minimal fixture to capture a positive original native
callback/error lifecycle, then compare the outer-realm ResizeObserver with the
observed iframe document's own public ResizeObserver constructor. Record target,
realm, height, callback/root-write and teardown order. At most ten cycles per
variant; require positive baseline recurrence and preserved28->17/cleanup before
claiming a mechanism or proposing any dependency-source change. If the baseline
stays clean, stop and explicitly retain unknown cause. This is a hypothesis,
not evidence that cross-document realm is the defect. Subsequent bounded baseline
result is recorded below; it did not recur, so the realm variant was not run.
No whole browser rerun until a concrete causal fix/new evidence warrants it.

Source/config/tests and reviewed reference hashes are frozen in the final bounded
acceptance manifest under `/tmp/peerly-frontend-final-acceptance/`. Parent coordinates
remaining whole-runtime acceptance and real-provider/internal-staging smoke. No
production or external-user readiness claim.

### Approved finite RO baseline END — no causal fix

The approved realm/lifecycle comparison stopped after its original baseline:
10/10 native mobile360 capture/resize/restore/page-close cycles pass, CLI0 in4.8s,
zero native errors. Real font28->17 and disconnect controls pass (iframe removed,
font callbacks4before/4after a subsequent viewport resize). Installed source hashes
match the border-only watcher patch/provider/plugin provenance. This immutable
standalone fixture approximates captured aggregate inputs; the actual positive
Angular error was not reproduced. As explicitly required, owner-realm comparison
was NOT executed and no source patch was applied. The foreign BODY/same-value
font write remains temporal evidence, not proven cause. GlobalRO remains OPEN.

Full raw baseline/immutable sources/provenance are recorded in
`/tmp/peerly-ro-realm-bounded/evidence.json` and `frontend/RUNTIME-DIAGNOSTICS.md`.
No PG fixture, live provider, secret or whole matrix ran. Halley stopped at the
finite hypothesis bound rather than extending negative probes. Final delta after
the bounded acceptance freeze is documentation only; parent receives its manifest.

### Internal staging known-issue decision —10 November2026

Owner explicitly permits internal-team staging despite unresolved native RO and
freezes blind investigation. Original aggregate failure stays preserved and is not
relabelled green; external acceptance remains separate. Halley prepares a bounded
production-build browser smoke against Aquinas's actual nonroot nginx image:
Google callback recovery, real font28->17 restoration and explicit confirmed text
send, each across three required browser projects. Existing behavioral assertions,
reviewed goldens, native error/console guards and raw traces stay unchanged. This
checks production static assets/routing and visible/function impact against
controlled HTTP contracts; it does not establish real backend/providers/S3/AI.
No PG fixture, secret, deploy, Git or whole1080/228 matrix work is authorised here.
END: actual production nginx image SHA256
`74ca40e1215b9b07e7dc61470047db252cce78ff349603ad519fae35692bf5f9`,
Aquinas-owned container `peerly-frontend-aquinas-20261110`, loopback38543. Existing
frozen app source hashes match dc8d; Aquinas separately records parent Docker and
nginx build inputs (including the delegated actual underscore-hash cache-regex fix).
Browser9/9 CLI0 in8.4s, fifteen strict existing comparisons, zero new references.
Real font restoration/readable links, callback URL stripping and explicit confirmed
raw-text send work across all three required engines/viewports. No visible failure,
RO or JavaScript exception observed in this bounded production run; this is not
causal evidence or whole-gate acceptance.

Six raw resource console errors remain in `native-console-events.json`: three
intended401 `/me` responses and three unmocked ancillary `study-prompt-visits`404s
(no API proxy in this standalone image). Controlled text Send/canonical reads pass;
ancillary study prompts/live backend/providers are not proven here. No suppression
or source fix was added. All nine trace archives and exact log/exit0 are under
`/tmp/peerly-production-browser-smoke/`. No active owned browser/PG/build remains;
END sent Aquinas/parent/Nash and CPU slot released. Container retained for parent.
Internal staging proceeds under owner known-issue decision; external acceptance
and original historical diagnostic failures remain separate.

### Student code candidate — latest source boundary

Lead student implementation is now source-complete pending the coordinated final
batch: actual P01 overview/editor/visibility/blocks routes, goal completion, owned
unblock recovery, shared navigation, Profile/Goal/Help draft authority/CAS handling,
G01/O02 parent integration, F03 summary and root A04/W04/P02 wiring. Aquinas reports
support/preferences production source complete. Exact paths and limitations are in
`frontend/FRONTEND-CODE-COMPLETE.md`. No intermediate unit/browser/PG runs were
started for these additions. Cheap consolidated type/lint preflight logs are under
`/tmp/peerly-frontend-codecomplete-*`; these do not imply final gates or coverage.

Readonly contracts regenerated from actual final head52,96paths/109operations,
exportSHA `ed527677f73fad580877c076dd999b21e6f5f9d8a63ab20ae5c55aee5f94348b`.
Support PG cohorts are separated by fresh isolated schemas to respect the genuine
five/source/day limit; never spoof source, relax quota or change clocks.
Global aggregate ResizeObserver remains unresolved, historical whole1293 and build
513.26kB predate this source. No current whole-green/native push/live-AI claim.
Parent alone coordinates final freeze, deployment and Git. No frontend fixture,
browser lease or heavy test is running at this source boundary.

### Current student priority: C03 and P05 source work

Profile fields scoped unit7 now **78/78 PASS CLI0**,96.83/96.65/100/100,
raw warnings0/NG0956=0/console errors0 explicitly inspected. Preserved
`/tmp/peerly-profile-fields-unit7.log` and `-lcov.info`. Named verbose diagnostic
proved remaining warnings came only from artificial wholesale selected-code
replacement in tests; actual public CVA toggles and pure malformed-input guard
now cover those responsibilities without forcing impossible UI states. No console
filter, library patch or threshold change. Dirty-leave/root refresh lifetime,
visuals and real persistence remain unfinished.

Actual GoalAssistance parent mounting is source WIP: per-form UUID/edit revision,
fresh-session/source guarded Apply, explicit unsaved form edit and Back to my text,
normal CAS Save separate. Public readonly bridge and `[applyDisabled]=locked`
prevent discarding a result while parent save is pending/uncertain/conflicted.
Parent integration tests and actual disabled503/manual-save PG proof are next;
not a live provider or frontend acceptance claim. Existing AI43 scoped unit
checkpoint precedes new host-lock regression44 (first driver failure retained).

Current profile-fields checkpoint: scoped76/76 assertions pass CLI0 at
96.81/96.65/100/100 (`/tmp/peerly-profile-fields-unit6.log`, preserved LCOV).
This is NOT clean feature acceptance: NG0956 warnings remain in raw output.
A cached query select projection fixes unrelated-edit language-option DOM churn
and its real public CVA identity regression passes; remaining warning contexts
still need attribution. One named verbose profile-details subset is diagnostic,
not a broad pass or threshold waiver. Earlier74-pass statement94.87 failure and
CVA-driver failures preserved. Public readiness now waits loading state gone and
actual picker readonly=false, not an already-visible fallback hint. New fields
still need dirty-leave/root refresh lifetime, screenshots and real persistence.

Aquinas student-AI43/43 scoped units pass with95+ all metrics after a meaningful
RED older GET/cancel-receipt race fix; actual provider remains hardOFF. Component
and readonly bridge exported; lead Goal mounting/manual503-save integration not
yet implemented. No live AI or full frontend gate acceptance is implied.

C03 final scoped evidence: current nine HTTP families pass in disjoint ordinary
12+3+12 runs (not one27); last remaining12 normal5 CLI0/26.1s, all21 references
reviewed/hash-stable. Coherent realPG15 remains accepted. Sixty active HTTP
references58PNG+2JPEG,36 realPG PNGs. Aquinas now assigned student AI exclusively
under onboarding/study/ai/** plus student-ai-progress, actual hardOFF503/manual
path; lead owns real Goal integration/shared infrastructure. No operator expansion.

Halley next profile-fields source WIP: actual optional programme/year/languages/
about editor and reference-data query/guard added, no signup fields or DTO guesses.
Scoped production ESLint2 and app ngc1 passed; new test ESLint4 passed. Initial spec
compiler sees parallel AI missing-template source WIP, not a green test claim;
waiting coherent AI source before first browser-unit lease. Dirty-leave and
session-refresh draft lifetime remain explicit work, not silently complete P01.
Latest complete whole units1293/build513.26 predate this unaccepted profile WIP.

**Scoped Preview normal accepted:** ordinary3 **3/3 PASS CLI0/14.3s**, no updates,
strict diagnostics, source11; `/tmp/peerly-c03-preview3-normal4.log`. Nine reviewed
baselines: two WebKit OPEN/ZOOM compositor JPEGs, four Chromium OPEN/ZOOM PNGs and
three closed PNGs. Native frame freshness/dimensions/three-cycle exact-byte checks
remain strict; ordinary WebKit snapshots preserved as uncompared artifacts.
This resolves the capture acceptance for this scenario without app/CSS/dependency
changes. GlobalRO and four remaining image HTTP scenarios are separate boundaries.

Affected WebKit Preview capture9 **1/1 PASS CLI0/9.4s**: both OPEN and ZOOM
satisfy unchanged three-cycle fresh/exact-byte/full-viewport checks. Public
readiness evidence observed ZOOM's actual finite running animation endTime300,
awaited finished before native captures; OPEN fonts loaded and two images decoded.
`/tmp/peerly-c03-preview-wk1-capture9-evidence/` preserves extracted public/native
metadata; two JPEGs and closed PNG reviewed. The old failing native pixels were
not available, so no retrospective exact-pixel cause claim. Next only unexecuted
desktop capture and conditional ordinary3; globalRO unchanged.

Viewer adapter candidate capture8 correctly stopped: Chromium mobile passed;
WebKit OPEN three fresh frames were stable and produced JPEG, ZOOM failed exact
byte equality, desktop unrun. `/tmp/peerly-c03-preview3-capture8.log` retained;
no normal acceptance or tolerance change. Source trace places zoom frames255/282ms
after click against component300ms finite transition; public finite-animation
readiness is the bounded next hypothesis, not proven pixel cause. Lead added
per-cycle raw JPEG/native metadata attachments before stability validation so
future failure retains its exact evidence. All63 tooling pass (13 new), ESLint7
and e2e tsc3 CLI0. Only one affected WebKit check authorised after readiness/static;
no broad repeat or app/dependency change. GlobalRO stays open.

C03 nonviewer area-copy boundary accepted: ordinary HTTP12 normal3 **12/12
PASS CLI0/32.8s**, four cases across three projects, strict diagnostics/no updates.
`/tmp/peerly-c03-http-area12-normal3.log` and cleanup retain evidence. Thirty
reviewed references unchanged after normal. The earlier705-pixel failure and prior
references remain preserved; all refreshed differences were exactly approved
help subject→help area text with identical geometry. Not a whole HTTP27 pass.

Narrow WebKit Preview capture proof accepted by parent: public pinned1.65
screencast API works on WebKit; three fresh independent390×844 JPEG buffers match
exact bytes, ordinary before/after PNGs independently match and omit the correct
compositor dim backdrop. Lead personally reviewed both paths. Artifacts and
native timestamps: `/tmp/peerly-public-screencast-proof/manifest.json`, `run2.log`.
First config startup failure occurred prebrowser and is preserved as `run.log`.
No app/CSS/dependency patch. Resource ports clean after END.

Shared `testing/webkit-preview-frame.mts` plus narrowly opt-in checkpoint support
now implement WebKit OPEN/ZOOM only. Full viewport, fresh first frame, three-cycle
exact-byte stability and public API/start/cleanup failures are checked; ordinary
PNG remains an artifact, JPEG is the actual strict visual baseline. Other states
and engines keep standard PNG. Twelve new regression tests; all62 tooling pass
CLI0, typed ESLint5 and e2e tsc2 CLI0. See `frontend/WEBKIT-PREVIEW-CAPTURE.md`.
Owned viewer integration/candidate review/normal acceptance still pending;
historical globalRO is explicitly unresolved.

**Accepted scoped C03 real-backend milestone:** coherent ordinary NORMAL15
**15/15 PASS CLI0/1.7m**, source7, no baseline updates, strict diagnostics;
36 reviewed baseline hashes unchanged. `/tmp/peerly-c03-normal15-run1.log`,
`-results`, `-report`, `-preflight.json`, `-cleanup.json` retain evidence. This
covers real native transfer/worker/image FK, known202 reload, actual lost-finalize,
explicit same-intent Retry after auth pause, and cancellation across three projects.
Cleanup schema/ports/newTLS clean. Initial shutdown count1 DB session is preserved
in `-cleanup-initial.json`; immediate readonly `-db-postcheck.json` shows []/zero,
not silently discarded. Resource leases released. Current HTTP27 ordinary viewer
checks and historical globalRO remain separate unresolved acceptance boundaries.

C03 remaining9 capture8 FINAL END: WebKit4/4 CLI0/38.3s and desktop5/5
CLI0/39s, sequential with clean preflight/cleanup between. Raw prefixes
`/tmp/peerly-c03-pg-remaining9-wk4-capture8` and
`/tmp/peerly-c03-pg-remaining9-desktop5-capture8`. All fifteen distinct cases have
now passed across bounded capture pieces, NOT one ordinary fifteen-case gate.
Twenty new references under offline review. Normal15 is authorised only after
reference review and fresh named backend READY/preflight; strict diagnostics and
max-failures1 remain. Final cleanup schemas[],sessions0,owned ports closed,newTLS[].

Affected WebKit pipeline capture7 now PASS1/1 CLI0/20.1s after public initial
stream/Me readiness and enabled-picker preparation, with no product mutation.
Actual Start/native transfer/worker/image FK/JPEG/peer report verified. Raw
`/tmp/peerly-c03-pipeline-webkit1-capture7.log`; cleanup schemas[],sessions0,owned
ports closed,newTLS[]. Four WebKit PNGs under review. Chrome five-case/twelve-ref
manifest `/tmp/peerly-c03-pg6-chrome12-manifest.json` confirms eleven prior reviewed
hashes unchanged plus reviewed cancellation state. Next conditional fresh lease
covers only nine still-unexecuted project/cases, not an automatic whole rerun.
Ordinary15 comparison and global runtime/viewer issues remain open.

Latest C03 finite loss/auth checks: two distinct Chromium real-backend cases
passed capture2/2 CLI0/21s, `/tmp/peerly-c03-loss-auth-chrome2-capture5.log`.
Actual finalize202 followed by transport abort is separate from actual Start202
loss plus SSE/Me auth pause and explicit identical-key/body Retry. All five new
references reviewed; no automatic replay or authority relaxation.

Fresh Noether READY/current head0050 and clean preflight permitted full capture15
attempt6. It ended CLI1/max-failures1: all five Chromium cases passed, first WebKit
pipeline failed because local selected-image element was absent after file input;
nine cases unrun. Raw `/tmp/peerly-c03-pg15-capture6.log` and results/report retained.
No full-matrix acceptance. Aquinas is inspecting existing trace/native disabled
input/readiness ordering before any rerun or product change. Cleanup confirmed
schemas[],sessions0,owned ports closed,new TLS[]; lease released. New Chromium
cancellation reference review pending.

Existing WebKit trace orders native file-input action across initial SSE200 and
Me revalidation: input enabled before action, Me fetch starts before action ends,
then input disabled and selection absent. Actual change-event timestamp is not
captured, so exact callback causality is not claimed. Smallest approved driver
correction uses existing genuine initial stream/Me readiness helper before the
first pipeline file choice and asserts public picker enabled for every choice.
No production patch. Next authorised check is only affected WebKit pipeline1,
conditional fresh named backend READY/preflight; not another whole15. Late native
OS chooser/auth transition remains a separate potential regression, not resolved
by test readiness.

Preview diagnosis refined without a browser run: existing before/after compositor
frames are byte-identical, correctly dimmed, while same-state WebKit snapshot PNG
is undimmed. `/tmp/peerly-c03-preview3-screencast/manifest.json` records times and
hashes. This is capture-path evidence, not an application defect or RO cause;
no app/dependency patch justified. Ordinary viewer comparison remains unresolved.

Area-copy accessibility slice accepted: study112/112 CLI0 at95.95/95.28/100/100,
unchanged95 thresholds. Initial111 passed assertions but scoped branch94.96 failed;
added meaningful old-actor403-after-replacement regression proving new draft/cache
are not expired/erased, rather than weakening/excluding coverage. Raw
`/tmp/peerly-area-compact-study-unit4.log`, preserved `-lcov.info`. Latest whole
frontend1293 remains the earlier complete checkpoint; do not claim a single whole
1294 run from this scoped addition.

Initial new long labels were visibly ellipsed at200% (12 rejected refs preserved
`/tmp/peerly-area-reflow6-rejected-labels`). Visible labels are now concise
Area/Task/Context/Note, full native ARIA names and visible optional/module hints
preserved. No framework internals, scale reduction, hidden duplicate controls or
CSS adjustment. Normal6 CLI0/16.3s in `/tmp/peerly-area-reflow6-normal1.log`, all3
projects320px/200%, glyph-range fit and document overflow/keyboard assertions.
All12 updated references reviewed via native-size diagnostic tiles, SHA manifest
`/tmp/peerly-area-reflow6-review2/manifest.json`; tiles are review aids, full source
PNGs remain comparisons. Static7 typed ESLint/e2e/ngc-app/spec all0. Other area-copy
screens/reference states still require their own capture/review/normal checks.

C03 known-finalize202/reload finite Chromium case subsequently passed capture1/1
CLI0/16.2s using actual initialSSE/Me readiness and bounded real worker idle-only
polling until first non-idle, canonicalREADY required. Two refs reviewed; not a
lost-finalize or whole-matrix acceptance claim. Actual uncertain-finalize and
explicit auth-pause/retry are now distinct authored cases, matrix5×3=15; new shared
namespaces added, no production contract changes. Finite2 evidence and subsequent full capture attempt are recorded above; no
lead heavy/browser/PG currently active.

| Current boundary      | Accepted evidence                                                                                                     | Remaining limitation                                                                                              |
| --------------------- | --------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Whole frontend units  | 1293/1293,66 suites,96.74/96.03/98.14/98.95,CLI0                                                                      | Does not replace browser/runtime checks                                                                           |
| Production build      | 513.26kB initial,525both/style4,zero warnings,CLI0                                                                    | Native/live-provider and clean-install gates separate                                                             |
| P05 deletion          | 47 units,45 controlled HTTP and6 ordinary realPG cases accepted                                                       | Later area-label copy changes retained-context references; update those intentionally                             |
| C03 attachment intent | Deterministic RED for File loss/receipt race,80 owned checks and2 parent integrated regressions included in whole1293 | Coherent realPG normal15 accepted; current HTTP27 and whole-app gate separate                                     |
| C03 actual storage    | One Chromium PNG/native-transfer/real-worker/message-imageFK/peer-report case passed                                  | Coherent normal15 realPG passes all five cases across three projects; broader HTTP/viewer acceptance separate     |
| Knowledge areas       | Minimal source copy and static/unit/build checks pass; same IDs/contracts                                             | Relevant screenshot capture/review/normal comparisons pending                                                     |
| Global runtime        | Strict forwarded-error guard retained                                                                                 | Historical aggregate ResizeObserver and WebKit Preview snapshot/compositor discrepancy remain open; no proven fix |

C03 actual PG attempt2 after that correction: first Chromium pipeline passed
(native PNG transfer, real ProcessNextChatImage, normalized JPEG, actual stored
message image FK, peer grant/report). It is capture-only/one project evidence,
not full PG9 acceptance. Recovery helper reached actual Start202/upload-access200,
then initial SSE triggered same-actor /me revalidation. Strict authority correctly
stopped before transfer/finalize; UI retained File/caption and offered explicit
Retry, with no text fallback. Helper waited for finalize instead of acknowledging
that public pause contract. Attempt ended1pass/1failure/7unrun; cleanup schema[]/
sessions0/owned ports closed/own TLS[]; raw `/tmp/peerly-c03-pg9-capture2.log`.
First4 image references reviewed by Aquinas, candidate only. Next bounded work:
settle initial actual stream/Me/disabled-state readiness for the intended uncertain
finalize/reload case, keep an explicit auth-pause/retry scenario distinct, then one
affected Chromium case before fullPG9. No relaxed auth, automatic replay or sleeps.

Critical C03 lifetime correction, current coherent source:1293/1293 whole frontend
units CLI0,66 suites,96.74 statements/96.03 branches/98.14 functions/98.95 lines,
unchanged95. Raw `/tmp/peerly-c03-lifetime-all-unit4.log`, SHA-256
`e0a0f527e54a54e595f902267222b0e8a8192d8283e8422533f55d968cc375fc`,
preserved `-lcov.info`. Unit3 had1292pass/1 new parent test-driver failure: the real
recovered pipeline reads canonical state twice; the driver supplied only the first
response. Supplied the missing actual readiness GET, no production bypass.

Actual PG image capture1 exposed selected image silently lost on SAME-actor /me
refetch; explicit Send then stored text only. Trace matched child retiring its
File on temporary command-ineligibility. Deterministic child unit19 RED reproduced
selection loss; unit23 RED also proved owned confirmed receipt ignored during
revalidation. Local form File/immutable intent now survive pending/failed same-actor
checks; strict shared trustedChatActor still blocks new reads/writes while unknown.
Actual logout/null/account replacement/capability retirement/destroy clear lifetime.
Owned confirmed receipts retire drafts separately from fresh command authority;
parent clears the corresponding caption even while the same actor revalidates.
Two integrated parent regressions prove native JPEG routes through image Start,
never text fallback after refetch or unknown Start503, and actual image-ID receipt
retires caption once without resending. No File/DTO mirror or automatic replay.

Child unit24=80/static25 passed separately; coherent1293 includes both parent
regressions. Production build3 CLI0/6.976s,513.26kB initial, unchanged525both/style4,
zero warnings. Raw `/tmp/peerly-c03-lifetime-build3.log`, SHA-256
`6c5c15ce685d07548cedbf5903d60a42b3e6ff97d308fd50d6e0ba3843edf010`.
Parent typed ESLint CLI0. Aquinas has source freeze and next explicit browserlease
for true PG9 attempt2 only after freshNoether READY/preflight. No real pipeline
success or global ResizeObserver resolution inferred from unit/build evidence.

Production student build2 CLI0/6.533s, initial513.26kB (same measured initial),
unchanged525both/style4, zero warnings,1 public static route prerendered. Raw
`/tmp/peerly-student-areas-build2.log`, SHA-256
`0af161a186a5b95ce75ca67ce27472fc8935a340d3aa5bbbc2073163fa590c05`.
No whole-app/clean-install/native/provider acceptance inferred. C03-images-PG9
browser lease granted to Aquinas after his freshNoether head50 READY and this
build END; lead owns no heavy/browser/PG during that bounded run. Shared source
frozen; area screenshot updates wait until his END.

Whole frontend unit boundary after minimal areas copy:1286/1286 CLI0,66 suites,
96.70 statements/96.01 branches/98.08 functions/98.90 lines, unchanged95 all4.
Raw `/tmp/peerly-student-area-all-unit2.log` and preserved `-lcov.info`. First run
1280pass/6fail from stale copy/grammar expectations, all retained in unit1 log;
actual expectations updated, no guards/assertion coverage removed. New source
copy touches goal/help/setup/catalogue/discovery and current/history context labels
only; same DTOs/canonical IDs/optional lengths/CAS/save behavior. Topic/task and
module context stay optional, helper knowledge may come from work/independent
study/another module. Screen screenshot acceptance for this new copy is pending.
Static2 typed ESLint/e2e/ngc CLI0; existing composer conditional assertion refactored
into one parameter-selected visible detail with the same cooldown-date check,
no ignored warning. Relevant files listed `/tmp/peerly-area-copy-files.json`.

Shared C03 real fixture preparation: actual image worker hook at
POST`/__fixture/chat-images/process`, same controlled media/image processor/core
SQL, no fake READY or live provider. Distinct pipeline/recovery/cancel/report
namespaces added to existing controlled cohort allowlist/helper union, avoiding
full-suite collisions. Root fixture Ruff/format and frontend typed compile pass;
new namespaces and worker execution await Aquinas realPG checks. Existing real
bootstrap/P05 commands passed on head50. Aquinas owns images PGspec; shared
source frozen during his next scoped validation window.

Dependency integrity investigation resolved, not a mutation: installed Taiga core
5.31.0 modal source contains upstream teardown commentary that looked unusual.
Official pinned npm tarball SHA-512 equals package-lock integrity; all349 packaged
core files match installed bytes, no differences/missing files. Modal SHA-256
`d8fadb9ab2b623de76a31d1ad5ca2013cd5337a452a74ef7f07f95f5f01f75d3`.
Evidence `/tmp/peerly-taiga-modal-integrity/manifest.json`, both source copies and
empty diff retained. No dependency/app patch or reinstall was performed. Temporary
PG reservation was released before START, no fixture/DB mutations.

P05 targeted reflow capture5 exposed that original-action focus restoration is
not guaranteed in Chromium after asynchronous preparation disables the opener;
the new observable focus assertion failed before the closed-form checkpoint.
Raw `/tmp/peerly-p05-reflow-capture5.log`; this is pending accessibility/lifecycle
work, not accepted screenshots or a reason to blur keyboard focus. Candidate uses
standard aria-disabled/aria-busy during preparation so the opener remains focusable;
the existing pending command guard blocks repeat activation. Added duplicate-POST
regression, no pointer interception, direct focus manipulation or timing patch.
Candidate validation:47units CLI0 unchanged97.6/95.31/100/100;
`/tmp/peerly-p05-focus-unit9{.log,-lcov.info}`. Reflow capture6 all3projects CLI0,
original opener focused after keyboardCancel and reviewed3 changed focused-action
references; no manual DOM focus or pointer interception. Normal45 current source
completed CLI0 in `/tmp/peerly-p05-http45-normal2.log` (48.4s), no forwarded runtime
error in that run. All90 references reviewed; focused-action3 changed references
reviewed separately after semantic focus assertion. This scoped result does not
resolve the historical aggregate ResizeObserver gate or replace realPG6 pending. Prior capture45
remains capture-only evidence; normal45 remains20pass/1failure/24unrun.

P05 first realPG capture ended CLI1 before confirmation,5 unrun. Actual /me200
but preparation401 correctly enforced Google's durable identity source. Existing
controlled People factory seeded account/session/institutional binding but lacked
ExternalIdentityRecord; Noether confirmed lifecycle SQL intentionally checks it.
Controlled factory now includes its actual synthetic Google issuer/sub/accountFK
and database creation time, matching backend test setup. No fake response or
production guard change. PG spec asserts actual preparation200 and typed workflow.
Ruff/check/format and frontend typed ESLint/e2e pass after correction. First owned
fixture cleaned schemas[]/other sessions0/ports8768+8769closed; only1 own TLS dir
removed, preexisting dirs preserved. Raw `/tmp/peerly-p05-pg6-capture1.log`.
Fresh named head50 READY/START for corrected attempt2; preflight3 clean. Current
`/tmp/peerly-p05-pg6-capture2.log` completed6/6 CLI0 (46.3s),24 references
reviewed in `/tmp/peerly-p05-pg6-review2` with SHA manifest. New-source fixture
cleanup between runs confirms schemas[]/other sessions0/owned ports closed. Fresh
fixture normal6 completed CLI0/40.3s in `/tmp/peerly-p05-pg6-normal1.log`. Actual
head50; all3 browser projects assert real preparation200, canonical proof/reload,
ordinary401, different live peer200 and exact retained messages/Deleted readonly
projection. Final cleanup schemas[]/other sessions0, ports8768/8769/38385closed;
6 task-created TLS dirs removed, all preexisting dirs preserved. Noether runtime
hold released with explicit END. No whole-app/aggregate RO acceptance is implied.

Latest owner scope addition is a bounded knowledge-area copy/validation pass after
images/delete. Plan and actual affected consumers are in
frontend/KNOWLEDGE-AREAS-ADAPTATION.md. Backend confirms schema88/hash unchanged;
module context already optional, no course/enrolment gate exists, no guessed DTO
rewrite or new tag hierarchy. Aquinas remains exclusively images.

P05 scenario source now covers bootstrap loading/error/retry/guest, preparation
server/network/invalid response, committed/unknown/mismatched outcome, expired
session, navigation during an in-flight command, independent proof loading and
reflow. All15 HTTP cases and2 realPG case definitions passed the owned formatter, typed
ESLint, e2e TypeScript and Angular no-emit compilation. Current45 browser capture completed CLI0; all90 references were reviewed through
12 diagnostic contact sheets, with source SHA manifest in
`/tmp/peerly-p05-http45-review4/manifest.json`. Raw capture:
`/tmp/peerly-p05-http45-capture4.log`. First normal45 comparison ended CLI1:20 passed, WebKit closed-dialog200%
reference differs only in restored keyboard focus ring (2290pixels),24 not run.
Raw `/tmp/peerly-p05-http45-normal1.log` and diff preserved. Add an observable
original-action focus assertion after native dialog retirement before recapturing
that state; do not weaken tolerance or blur the keyboard focus. No full normal or
realPG acceptance is claimed yet. New realPG two-case×three-project source reuses controlled real
chat cohorts and verifies proof reload, ordinary401, a different live peer account,
retained exact messages and deleted/readonly peer projection. No DB/runtime run or
new source lease is claimed. Shared test helper installs only the synthetic peer's
HttpOnly cookie through Node; credentials never enter app JS/URLs/storage.

C03 capture failures remain owned actual fixture/layout defects, not waived:
report semantic row/min-content correction, full viewport Preview coverage and
actual history anchor validation. Finite affected captures replace broad repeats.
No new global RO cause/fix is established.

Current coherent Chats+Study+Images unit5:200/200 CLI0, unchanged95 aggregate
96.4 statements/95.73 branches/97.7 functions/98.85 lines. Raw and preserved LCOV
`/tmp/peerly-chats-images-integration-unit5{,-lcov.info}` (raw `.log`). Initial
shared run exposed6 real known-text/cancel receipts held behind unrelated image
preparation refresh plus1 test-driver expectation. Confirmed receipts now settle
without awaiting background invalidation; explicit regression keeps image refresh
pending/failing while text remains stored. Confirmed image markup/caption escaping,
authenticated JPEG read without implicit ACK and actual explicit private ACK are
covered. Intermediate header/Blob fixture errors remain in unit3/4 raw logs.
Untested prepared-image WIP was completed/tested by its owner, never excluded.

P05 current unit8:46/46 CLI0,97.6/95.31/100/100, including ordinary401 authority
retirement, overlap with account replacement, lost-response proof recovery and
nonblocking ordinary-session recheck. Confirmed proof is request-specific; another
live account is not assumed deleted. Current UI copy hides cookie/proof machinery.
Source app format fixes requested by parent were applied while no browser was active.
Current P05 browser recapture/normal and realPG remain pending after these changes.

Aquinas received the C03 HTTP capture window after this coherent boundary. Lead
holds application source during that browser run, works only on P05 specs/driver/docs.
Global RO and whole-application gates remain unresolved; these scoped unit gates
are not a whole-app claim. No Git/publication/deployment/provider credential work.

F01/F02 scoped ordinary acceptance complete: fresh named PG5 normal1 CLI0,
5/5/30s; raw `/tmp/peerly-study-pg5-normal1.log`. Prior ordinary2 nine passes plus
this targeted five cover all12 unique scenarios (two mobile eligible overlaps).
This is NOT a single12-test CLI0 run. New region references were reviewed once
before normal comparison; no updates/masks/tolerance during normal1. Exact server
read_position:null, zero ACK writes, version/CAS/idempotency, privacy, source IDs/
timestamps and overflow pass. Cleanup GLOBAL0/schema[]/ports closed/ownTLS removed,
prior TLS preserved and C03 source exactly restored; Noether runtime hold released.
Global RO and whole-app acceptance remain separate unresolved gates.

P05 capture3 targeted6/6 CLI0: redundant heading removed, single-heading regression,
actual fullscreen viewport top/actions snapshots at320/200 plus measured paragraph
and button horizontal bounds. Old fixed-overlay full-page captures preserved outside
source; new9 confirmation references reviewed alongside30 unchanged references.
The real visible dialog has no horizontal clipping in these checks. Current39 P05
reference images still require normal18 comparison and real PG before acceptance.

C03 receives deterministic controlled640x480 JPEG/PNG study-image test assets
under testing/fixtures with bytes/hash manifest `/tmp/peerly-c03-controlled-image-assets.json`.
These are test-only files, not product imagery/provider mocks. Aquinas fixes invalid
attachment silently falling through to text-only send before its HTTP capture;
Halley owns a parent composer regression. No native Back claim or fake history bridge.

Region capture1 finite END:3/3 actual PG CLI0,9 complete-region references and9
full-page **uncompared** artifacts reviewed. Manifest SHA256
`f8e8d351286963d77a89e637ca5e1f729ae1a3c87a27817799f28456fd90454a`,
`/tmp/peerly-study-region-pg3-review/manifest.json`. Actual read_position:null,
zero ACK writes, source IDs/times, private isolation, versions and overflow pass.
Cleanup GLOBAL0/schema[]/ports closed/ownTLS removed/prior preserved; C03 restored
exactly. Requested fresh `feedback-PG5-targeted-normal` lease; `--list` confirms
exactly5 selected cases (eligible3 + desktop unrun2), no whole12 repeat.

P05 first browser capture2:18/18 CLI0, no runtime diagnostics,36 PNG references.
These are capture results pending normal comparisons. Review caught redundant
inner dialog heading duplicating Taiga's public label; removed it and added exact
heading-count regression. Only affected confirmation references need intentional
recapture/review. No bad baseline acceptance. P05 realPG still pending.

Production student source build CLI0, rounded initial513.26kB below unchanged525kB,
style4kB and zero warnings. Raw `/tmp/peerly-student-p05-c03-build1.log` SHA256
`a00c6df110dde0a7b84786fe2627eb525837bd4c4beea25ca534861bd90578b4`.
This is not clean-install or whole-application acceptance. Global RO remains open.

Ordinary2 finite END: CLI1,9 passed/1 desktop eligible screenshot failure/2 not
run. Raw `/tmp/peerly-study-pg12-ordinary2.log`, artifacts/report same prefix.
The reviewed2152px diff is exclusively the separate native Mark read button's
viewport eligibility. Preserve the failed full-page reference/diff. No RO/Unhandled
message appears in this raw run; this does not resolve the global runtime blocker.
Cleanup schema[]/GLOBAL0,ports8768/8769/38385 closed,3 own TLS directories removed,
all prior TLS preserved. Noether hold released; C03 mount/unused worker restored
from saved source with exact hashes (`restored.json` under the isolation directory).

Parent explicitly approves complete Study region comparison plus full-page raw
uncompared artifacts ONLY for this feature's affected states, with actual server
read_position:null, zero real ACK writes and root overflow assertions. Implemented
test source uses distinct *-study-region reference names, preserving old full-page
references. New capture/review and targeted normal remaining cases are pending;
there will be no blind repeat of the unaffected nine passing scenarios.

Fresh named `student-feedback-PG12-ordinary2` received explicit Noether READY;
Halley START after Aquinas unit8 END. Preflight schema[]/GLOBAL sessions0 and
owned ports free passed. Only unaccepted C03 parent mount and unused worker hook
were reversibly isolated under `/tmp/peerly-c03-parent-mount-20261109`; composer
TS/HTML and confirmed-message TS exactly match accepted source hashes in its
isolation manifest. No Git restore or DB reset. Raw ordinary comparison run is
`/tmp/peerly-study-pg12-ordinary2.log`; result is pending, not passed yet. Restore
saved C03 source after finite END/cleanup. Short frontend source hold prevents HMR.

Latest shared static checkpoint: spec/e2e TypeScript, app Angular ngc and actual88
contract drift CLI0 (`/tmp/peerly-p05-{spec-static3,browser-static2,app-static3,contracts2}.log`).
C03 shared composition is mounted as SOURCE: one parent caption form, explicit
image Send delegation, confirmed image viewer, unchanged legacy text markup.
C03 integration behavior/visuals are NOT yet accepted. Driver-only actual chat-image
worker hook source exists; its fresh PG/runtime proof still awaits backend full
PG END. Aquinas has the next bounded unit window for its remaining branch coverage.

P05 scoped unit3 now passes38/38, CLI0, unchanged95 aggregate98.19 statements/
95.45 branches/100 functions/100 lines. Raw `/tmp/peerly-p05-unit3.log` and copied
LCOV `/tmp/peerly-p05-unit3-lcov.info`. Own ESLint/stylelint0; initial app ngc0.
Final static chain stopped on a sibling C03 test callable-type error (forwarded
owner), so do not claim latest whole static green. Five P05 browser definitions
are authored, with no accepted baselines or real PG yet. Entry from own profile
and banned account notice uses the actual routes. Aquinas unit6 window follows;
Halley continues source-only shared image composition.

Actual88/head49 contract generation and existing report compatibility units pass:
`/tmp/peerly-actual88-existing-report-compat-unit2.log`, unchanged95 aggregate
98.03 statements/96.69 branches/100 functions/99.3 lines. Typecheck2 CLI0;
these are scoped compatibility results, not a whole-frontend gate.
Aquinas owns only chats/images and its ledger; its unit resource window is active.
Halley has authored P05 preparation/explicit confirmation and independent cookie-proof
recovery source plus lazy routes. This new P05 source has NOT yet passed static,
unit, browser or PG acceptance. No automatic destructive retry or recovery token
in routes/storage. F03 summary browsers remain pending.

Ordinary feedback PG12 remains queued until backend full PG END; the earlier
global-session preflight conflict did not start a fixture and is not a product
failure or passing run. No reset/kill/waiver. Global ResizeObserver diagnostic is
still unresolved, with no newly proved causal mechanism or patch. No broad rerun.

### Composer draft validation corrected independently of the click-miss hypothesis

One bounded WebKit pointer trace did NOT reproduce the missing click: down/up/
click targeted Not yet, and the empty composer error/layout appeared afterward.
Raw `/tmp/peerly-study-wk-offered-pointer-probe1.log`; ring JSON same prefix.
Do not call this proof of the earlier miss's cause or an RO fix.

A separate deterministic UX regression was reproduced: leaving a pristine empty
unsent draft prompted Enter a message despite no attempted send. Unit RED18-pass/
1-fail19 is `/tmp/peerly-composer-pristine-blur-red1.log`. Empty drafts are now
valid editor state; explicit Send still runs the complete required/raw-content
validator and marks its control error. Dirty invalid input displays feedback
before blur, and successful reset does not create a false required error. Public
TuiError.error plus existing FormGroupDirective submitted/dirty/invalid state owns
presentation; no copied flags, reserved magic height, focus/pointer intervention
or internal selectors. Error is associated through native aria-describedby.

Coherent current-consumer125/125 unit CLI0; unchanged95 aggregate96.8 statements/
95.63 branches/96.86 functions/98.5 lines. Raw
`/tmp/peerly-composer-draft-validation-feature1.log`, LCOV same prefix. Typed lint
and Angular noEmit CLI0. Aquinas has the next finite three-project real-pointer
F01 verification/review on materially changed source, then normal comparisons.
No complete browser or global runtime pass is inferred. C03 viewer/read source
is being prepared outside the app while the owned browser source is frozen;
actual image-report API is a recorded backend dependency, not a fake action.

### Actual87 image contract consumed; existing text consumers coherent

Generated tested actual87/head48 schema SHA256
cb6859d1e8535e1bc2e5f8c0bb692d396c6892efb6f6c6388e5cf85963a588e1;
generation/drift check CLI0. Message.text is now nullable and image_id required/
nullable. Existing text fixtures explicitly supply null, preserve known-text
literal types, and real text-only source checks fail if the expected text is
missing. Student/retained metadata validators support actual image-only/captioned
wire shapes and reject invalid image IDs or empty content. No hand DTOs, invented
body fields or fallback empty text. Operator changes are minimum typed metadata
compatibility only; no resumed screens, image UI or privileged-preview claim.

All application/spec/e2e/native-config type checks, Angular noEmit and final typed
lint pass. Coherent existing-consumer unit123/123 CLI0 with unchanged95 aggregate
96.78 statements/95.61 branches/96.85 functions/98.49 lines; raw
`/tmp/peerly-actual87-existing-consumers-unit1.log`, LCOV same prefix. Logs for
export/check/types/compiler/lint use `/tmp/peerly-actual87-` prefix. This does not
implement image upload/display UI, still the next ready C03 work.

Noether's named INITIAL-AI-heavy START/END was respected: no frontend heavy/browser/
PG work during its actual window; Nash serialized Docker first. Backend full3582
continues and is not claimed green. No lead fixture active; Aquinas has the next
approved regional captures/normal69. Keep/Load compares the entire owned Study
region plus named full-page raw UNCOMPARED artifacts, since the separate manual
read button legitimately follows viewport visibility. No masks, altered observer,
filtered errors or claimed screenshot→RO causality. Native RO remains open.

### Same-actor draft lifetime corrected; complete Chats units green

A real parent integration regression exposed that /me revalidation removed the
query-owned details and destroyed the child-owned unsent feedback form. Clean
RED19-pass/1-fail20 proof is `/tmp/peerly-study-parent-draft-red2.log`. The child
now lives at the actor/conversation component lifetime, independent of transient
details availability; labels remain nullable query projections, the manual entry
still requires authoritative details, and existing write guards block untrusted
actions. Its existing session-cache observer reconfigures native query observers
after same-actor reauthorization. No form copying, DTO mirrors, persistent state
or weakened cache-clearing boundary. Actual logout/replacement/route changes
still retire private drafts, and a background check cannot replay visit admission.

The old one-item identity @for also emitted NG0956 in historical19/current20
logs. Removed this forced-remount workaround entirely; direct components use
normal ngOnChanges cleanup. GoalSharing now explicitly resets on actor change,
consistent with MessageComposer/StudyProgress. No track-index trick or warning
filter. Complete colocated Chats feature118/118 units CLI0 with unchanged95
aggregate97.05 statements/96.21 branches/97.81 functions/98.84 lines; zero warnings
in raw `/tmp/peerly-chats-study-lifetime-feature1.log`, LCOV same prefix. Exact
production snapshot `/tmp/peerly-chats-lifetime-production-source.json`.

HTTP69 prior run remains CLI1 (42 passed/1 WebKit transient Mark-read-state image
failure/26 not run) and independently contained nativeRO in a passing Chromium
403 context. Raw `/tmp/peerly-study-http69-normal1.log` is preserved. This lifecycle
fix is not claimed to resolve RO. Aquinas owns finite affected actual-account-hint
checks/image review then justified current-source normal comparisons, followed by
fresh backend PG lease. Accepted81 DTO snapshot is held while backend prepares a
new image contract; do not regenerate its untested intermediate schema.

### Real student feedback source checkpoint

Fresh named student-study-source1 lease completed CLI0 against coherent actual
HEAD0047. Four finite retained cohorts proved genuine prompt eligibility/at-most-
once admission, replay immutability versus canonical newer outcome/feedback,
private-only exclusion, peer-note isolation and worked-confirmation409. Raw
`/tmp/peerly-study-source1.log`; source driver/server logs share that prefix. This
is real API/PostgreSQL source proof, not browser screenshot acceptance. Fixture
1145328 stopped gracefully; own TLS removed, schemas[], database sessions0 and
8768/8769 closed. Source log SHA256 c6600ff81fb70db7760077de6990080741be1da8fcd646c87404663858cb3814.
Matching END released the backend hold. Generated actual81
lifecycle contracts and drift check both CLI0; no hand DTO or image contract guess.

### Own F03 consumer implemented; browser acceptance pending

Actual /me/feedback-summary now mounts in the existing owned Profile surface only
for the real activated capability and loaded profile. Two consumers retain local
WET guards/templates; no cross-screen imports or generic facade. The query uses
cached canonical session authority and native cancellation, with a private actor
key and canonical remount refresh. Non-public projection reveals no counts and
adds no guessed hidden/lifecycle reason.401/403 clears the draft/private cache and
emits to the actual parent session recheck; retired-actor/non-auth outputs cannot
retire current authority.

Own31 units CLI0; combined own-summary/Profile51 units CLI0 with unchanged95
aggregate96.96 statements/96.35 branches/100 functions/99.15 lines. Raw
`/tmp/peerly-own-feedback-summary-unit1.log` and
`/tmp/peerly-own-feedback-profile-unit1.log` (LCOV same prefix). Final typed lint
CLI0. Both public/own F03 now each define18 browser scenarios/24 image states,
including320px/200% text and native keyboard explanation. No baseline capture or
browser acceptance yet; existing Profile/Person references need reviewed updates
for the actual new card. Current browser resource remains Aquinas-owned.

### Current Person feature unit acceptance

All three colocated Person unit suites pass137/137 CLI0, including existing
contracts, parent safety/photo regressions and public summary. Entire Person
source coverage retains unchanged95 aggregate98.35 statements/96.28 branches/
98.96 functions/99.27 lines. Raw `/tmp/peerly-feedback-person-feature1.log`, LCOV
same prefix. Earlier intentionally partial test selection omitted existing guard
tests and did not meet95; it is not reported as accepted. No thresholds changed.
New actual401/403 summary failures clear actor-private cache and recheck /me;
queued former-actor and non-auth failures cannot retire current authority. A photo
refresh test now explicitly targets its profile query rather than waiting on an
unrelated newly mounted summary read. Its observed timeout and corrected complete
run remain recorded. No product error suppression or timeout increase.

Lead heavy lease END released to Aquinas ordinary66 comparisons after all147
images were reviewed. No lead browser/PG fixture active. Future PG leases must use
fresh coherent head (backend announced upcoming48), not inherit source47 hold.

### F03 freshness and scoped browser source

Public-summary32/32 units CLI0 with unchanged95 aggregate100 statements/
98.24 branches/100 functions/100 lines, including canonical remount refresh.
Raw `/tmp/peerly-feedback-summary-unit2.log`.15 public-summary browser cases/
21 image checkpoints authored, typed ESLint/e2e types pass; not captured yet.
Legacy Person visual references also require explicit review of the new actual
summary card, with deterministic boundary GETs and real-server summaries on PG.
No old references are silently accepted as current.

Aquinas new9 protocol capture CLI0,24 new images reviewed; all147 reference
manifest `/tmp/peerly-study-http147-manifest.json` SHA256
8075de09560eb4c88097ccc19b122403b372c001d3b6b05f0ee7c12f214caa70.
Ordinary66 comparisons wait the lead unit lease END; capture success is not
ordinary comparison success. Real study source proof is accepted separately.

### Current serialized browser follow-through

Aquinas final46 units CLI0 without the prior NG0956 warning; raw
`/tmp/peerly-study-unit10-final.log`, unchanged95 aggregate97.8 statements/
96.05 branches/100 functions/100 lines. Native unexpected exceptions remain
observable; only expected ApiFailure/CancelledError are consumed. New9 protocol
browser capture is running under its owned lease before review and ordinary66
comparisons. No result inferred while running. Lead authored15 public-summary
browser cases/21 image states (static typed ESLint/e2e types CLI0); capture is
pending serialized resource availability. Public-summary canonical remount now
refetches and a32nd unit regression is authored; last executed31-unit proof is
historical to that small freshness change, not a claimed32-unit result. Next
lead unit slot is after the current browser capture, without concurrent WebKit.

### Student pilot active checkpoint

Student feedback protocol now has meaningful RED→GREEN evidence:42 existing
checks passed and4 new regressions failed before the fix;46/46 then passed with
unchanged95 thresholds (98.24 statements/96.36 branches/100 functions/100 lines).
Raw `/tmp/peerly-study-unit7-protocol-red.log` and
`/tmp/peerly-study-unit8-protocol-green.log`. Draft CAS now retains the version
actually edited, requires explicit Keep/Load after reviewing newer saved answers,
and canonical reads supersede immutable old outcome receipts. Aquinas owns a
finite9-case capture/review followed by ordinary66-case comparison; no current
browser or real-PG completion inferred. Prior123 images were reviewed after real
320px grid/caption fixes through normal layout and public tuiButtonVertical.

Parent Chats integration19/19 CLI0; unchanged95 coverage98.27stmt/96.05branch/
97.14fn/99.04line. Raw `/tmp/peerly-study-parent-unit2.log`. Actual foreground
visit ownership, hidden-tab deferral, REST/SSE/history no-repeat, manual no_offer,
401/403 canonical recheck, replacement and queued old-DOM actions tested.

F03 public summary is mounted on Person;31/31 units CLI0 with100 statements/
98.24 branches/100 functions/100 lines. Raw
`/tmp/peerly-feedback-summary-unit1.log`. Actual optional discriminator omission
is accepted by validating guards; no required-state cast or generator relaxation.
Own-summary consumer and current browser/real-PG acceptance remain pending.
Finite real study fixtures are authored/static-checked, awaiting a fresh named
backend lease for source proof before the12 real-browser cases. No fixture is
currently active. New tested81-path lifecycle handoff is ready to regenerate;
no guessed deletion success/recovery fields. Head46 is the last announced coherent
runtime, with later image DDL requiring fresh coordination.

Parent proved real stagingS3 signed POST200, exact-origin CORS, authenticated
same-byte read and anonymous403 with probe cleanup. This is separate from browser,
large-image/worker and final image-send proof, all still pending. No local secrets,
live-provider calls or deployment by this worker. Full frontend gate/globalRO
remain open; no new causal RO fix or broad diagnostic rerun is claimed.

### Paused operator WIP isolated; accepted baseline restored exactly

Only seven NEW operator-profile-history source/test files and five new failure
PNGs moved outside src/test discovery to the preserved/tmp checkpoint. Existing
operator.ts and operator.html restored BYTE-EXACT to accepted hashes08fcc104… and
3d038c63…; all24 accepted operator production paths verified equal. Shared routes
and all accepted tests unchanged. Exact paths/full hashes/restoration patch and
manifest documented frontend/DEFERRED-OPERATOR-HISTORY.md. Prettier/typedESLint/
ngc noEmit green; no operator feature completion or test rerun. Prior67/5 result
belongs to the deferred checkpoint, not active discovered tests. No whole-gate
success inferred. Student work continues100%.

Corrected77 exporte42762684672d53186eee0f567ab700ae3d2beb5a4335768b5ec82386d71b211
regenerated successfully and drift-checkCLI0; safe422 now documented. Aquinas has
actualDTO+typedparentboundary and is implementing StudyProgress F01/F02 in approved
subtree. Lead owns parent foreground/manual tokens, F03summary and realfixtures.
StagingS3 provider proof belongsparent; no localcredentials/livecalls/deploy.

### Pilot student-feedback ownership and contract transition

Parent explicitly authorizes Aquinas new exclusive screens/chats/study/** and
student-feedback-progress.md; former Chats freeze has this exact subtree exception.
Halley retains Chats parent/shared session/transport/fixtures and F03 summary.
Exact handoff frontend/STUDENT-FEEDBACK-HANDOFF.md uses F01/F02 actual mounted
outcome/feedback/prompt contracts. One bounded operator72-unit/static checkpoint
pregranted, then freeze FE06.5 unaccepted visuals/PG and switch. No operator visual
expansion delays student feedback; no long fixture hold.

Actual77 initial artifact92eff… introduces undocumented default FastAPI422 on
public feedback summary, inconsistent with safe root problem contract. Existing
generator rejected open HTTPValidationError before writes; old72 remains intact.
Noether owns verifying invalid UUID/root annotation and fresh tested export before
regeneration. No generator relaxation or hand DTOs. Previous root2PG+3export proof
is focused, not a fresh full backend gate.

### Pilot priorities confirmed directly with backend

Noether confirms current public72 unchanged. Main owns chat images end-to-end and
student feedback mount; Nash owns pure ban/soft-delete before shared lifecycle
DDL/runtime/recovery. Await tested actual exports; no inferred DTO/UI. Aquinas
activated source-only bounded FE06.5 actual retained profile history (M04 explicit
Overview action/M06 semantic section, no invented tab); new PG only via a short
coordinated lease, no chained long holds. Student-ready feedback/deletion/support
will outrank further operator breadth. M05 final96manifest SHA256
`65521d48834c9a8c717bdd46b5ce87cb571c03945c29db18c8aac2421d0a4821`.
GlobalRO remains candidly without a proven fix after the finite negative owner
traces; no blind rerun or speculative patch scheduled.

### M05 scoped complete

Final61 operator units/static pass;72 HTTP references reviewed, prior HTTP nativeRO
CLI1 preserved. Actual PG12 candidateCLI0 and fresh ordinary12CLI0 in36s NOupdates:
all24 PostgreSQL references match, all96 M05 refs/source hashes unchanged. Raw
`/tmp/peerly-operator-conversation-pg12-normal1.log`; final manifest
`/tmp/peerly-operator-conversation-final96-manifest.json`. Actual retained pair/
accepted request version/messages50+3/empty and no student ACK mutations/audit
links proved. FreshHEAD0043 schema frontend_60c72b4ba51a46a886e7933d960ffca5.
END schemas[],DB0,graceful API/storage shutdown,38385/8768/8769 closed,only3new
owned empty TLS dirs removed/188 prior dirs preserved. No further M05 browser run.
Production remains506651/525000bytes, no warning. This is implemented text-only
M05 subset, not attachments/shared-goal/cases/full graph or global runtime success.

### M05 unit/HTTP/build checkpoint

Final61 scoped operator units CLI0 including existing48 common authority
regressions; unchanged95 aggregate98.25stmt/96.73branch/100fn/99.46line. Final public
Refresh layout static checks pass. ActualHTTP33 behavioral cases PASS59.9s but
strictwrapperCLI1 nativeRO persists. Raw
`/tmp/peerly-operator-conversation-http33-capture2.log`; first attempt's ambiguous
form alert selector was corrected without production changes. New PNG review
ongoing, no M05 visual/PG completion claimed.

ProductionCLI0 in4.607s, initial506651/525000bytes unchanged18349headroom, no
warnings/prerender1; stats SHA256
`9fe137fb336bf9311fc1cc29991e98c56a94818f6b881f3496623aeb37d9fed3`.
Raw `/tmp/peerly-operator-conversation-production-build1.log`. Source/build hold
released. Real PG12 waits complete offline review and a fresh Noether READY.

### M05 real fixture and bounded RO trace

M05 actual retained conversation helper/API proof CLI0:53 confirmed messages,
ASC first page4..53/tail1..3, accepted request/version2/pair refs, hidden+deleted
participants, incomplete operator privileged access, empty accepted container,
no student read-revision/position mutation,3audits/canonical links incl404,revoke403.
Raw `/tmp/peerly-operator-conversation-source1.log`; PID1093065 cleanup schemas[],
DB0,8768/8769closed,TLSremoved/explicitEND. New four finite conversation namespaces
and readonly source IDs/counter helper; Ruff/strictmypy/typedESLint/e2etypes pass.
Actual OperatorConversation lazily mounted at/operator/conversations;61 operator
units green after correcting a test's invalid-ID/cursor-reset assumption. Final
public Refresh template regression is being verified before HTTP33.

Halley executed ONE existing Reports desktop child403 normal screenshot scenario
with transparent owner/--t-side diagnostic trace under/tmp. CLI0,1case8s,twooriginal
reference comparisons, no source changes or snapshot updates;75 trace records,
13 observers/callback pairs,12 --t-side writes,6 disconnects,nativeerrors0. Raw
`/tmp/peerly-ro-side-trace/run1.log`; extractedtrace owner-trace-before-close.json
in same directory. This negative actual-scenario trace is NOT a runtime fix or
skipped-target identification. No further probe/rerun follows without new causal
evidence; aggregateRO remains OPEN, no proven application/dependency correction.

### FE06.3 accepted; FE06.4 actual M05 active

Aquinas completed final3 raw audit artifact review.129 actual compared references
(87HTTP+42PG), source hashes verified; manifest
`/tmp/peerly-operator-reports-final129-manifest.json` SHA256
`324b85c8230c5b3485258fac41c0ad0f34f03dc4b6d53f9aee7e6530a571fa58`.
Parent accepts scoped48units/18ordinaryPG, globalROopen. FE06.4 immediately
activated in same operator ownership: mounted single privileged messages GET,
approved M05 text-history subset only. No fake attachments/graph/moderation.
Lead owns actual retained fixture extension and lazy route once real exportready.

RO causal control corrected after actual PNG inspection found missing global CSS
in prior minimal fixture. One real-component run with built theme/local fonts has
actual span24×56→1×56→24×56 and --t-side writes, CLI0/noerrors,16traceevents.
Artifacts `/tmp/peerly-real-textfield-repro3/`; full limitations in
frontend/FONT-WATCHER-REPRO.md. This negative control is not a runtime fix. Next
bounded evidence is actual failing frame --t-side write/observer ordering, not
additional minimal variants or whole-suite retries. No proven source fix yet.

### FE06.3 fresh ordinary PostgreSQL comparison

Final current HTTP87 references reviewed;48 scoped units/static pass. Corrected
real-PG cases use six finite namespaces and actual reporter/context filters:
operator search is global, not automatically fixture-scoped. The earlier409
namespace reuse and empty-case assumption failures are preserved as fixture/test
corrections, not production fixes.

Actual18 PG behavioral scenarios completed;42 complete deterministic retained
report/event references and3 full raw UNCOMPARED audit artifacts reviewed. Exact
live audit IDs/request origins/timestamps/source chains are asserted in DOM; raw
audit artifacts are not counted as image comparisons. Earlier continuation CLI1
nativeRO remains preserved. Fresh ordinary18 NOupdates passes CLI0 in56.1s;
42 reviewed references match. Raw `/tmp/peerly-operator-reports-pg18-normal1.log`.
HEAD0043 observed in fresh schema frontend_ad2a0b89b9db4d869ae09cb368a7f829.
END schemas[],DB0,API/storage graceful shutdown,ports38385/8768/8769 closed,
only3 owned new empty TLS dirs removed,188 prior dirs preserved. Lease released.
Review of3 new full raw audit artifacts/final source hashes remains before final
scoped milestone. No whole frontend gate or aggregate RO resolution claimed.

### Complete-region screenshot checkpoint available

Shared testing/visual.ts checkpoint accepts either existing fullPage options or
an explicit readonly Locator target. Target uses public toHaveScreenshot on the
complete element with the same successful-checkpoint counter, runtime phases and
strict diagnostics; no masks/crops/tolerance overrides. Existing default full-page
behavior remains unchanged. Reports PG will compare complete stable semantic
report/event regions while attaching separately named full raw audit screenshots
and asserting exact real dynamic audit fields. Typed ESLint/e2etypes CLI0 and
existing tooling50/50 CLI0 `/tmp/peerly-region-checkpoint-tooling.log`. Real browser
consumer validation is still pending fresh PG READY; no pass claimed from helper
static checks alone.

### FE06.3 real-PG visual boundary agreed

First PG18 capture stopped after1 successful scenario and a fixture409: a one-shot
namespace was reused. Finite reports-events/reports-reflow namespaces added,
Ruff/helper ESLint/e2etypes green; no production fix. First4 real report PNGs
reviewed, remaining scenarios not accepted yet. Fresh READY required before retry.

Parent approved smallest truthful visual strategy for dynamic actual audit reads:
PG asserts exact live audit/request IDs, timestamps and stored source linkage;
full raw page screenshot is an artifact only, NOT a visual comparison. Baseline
comparison covers the complete deterministic retained report/event region. Full
audit rendering remains covered by controlled HTTP screenshots with deterministic
actual-shaped data. Every scenario still has screenshot coverage. No masks,
fabricated audit, global fixed clock or UUID patch. Technical search_anchor_at
panels are removed as absent from design, retaining contract guards and truthful
pagination behavior. Aquinas documents exact compared regions vs artifacts and DOM
assertions in its scenario matrix; current feature acceptance remains pending.

### FE06.3 consumer and production checkpoint

Real OperatorReports mounted feature-lazy at/operator/reports under the existing
QueryClient/session/stream boundary. Route ESLint/ngc pass. Actual new actor-cursor
bug reproduced and fixed in owned consumer: disabled observer keys retain actual
session ownership while actor validity gates reads/render, preventing old signed
cursor use after identity replacement.48/48 scoped operator units CLI0, coverage
97.90stmt/96.57branch/100fn/99.24lines with unchanged95 thresholds. Raw
`/tmp/peerly-operator-reports-unit2.log`; child403 sibling cancellation and401
revalidation tested. Meaningful HTTP/PG scenario authoring continues.

ProductionCLI0 in6.035s, initial506651/525000bytes(headroom18349), no budget warnings,
prerender1. Raw `/tmp/peerly-reports-production-build1.log`; stats SHA256
`dd7d0a3bd8d779c3304474403f15b3aae056965818b5630b1c12d872374ccd77`.
Source/build hold released; no FE06.3 browser or whole-gate acceptance claimed.

### FE06.3 real retained report fixture ready

Lead added only finite reports/reports-empty/reports-revocation/reports-replacement
namespaces and typed readonly report-source IDs to the existing synthetic helper.
New operator_reports_fixture.py retains53 reports with full context revision FKs,
52 actual canonical submission events, rich literal private comment, separate
context/submission origins and a legacy report with no recorded submission event.
No fake operator audit rows: actual successful GET creates the genuine audit and
canonical event. Original accepted cohorts unchanged.

Ruff, strict mypy2 helpers, typed ESLint and e2e noEmit pass. Fresh Noether lease
API proof CLI0 `/tmp/peerly-operator-reports-source1.log`: reports50+3,
submission timeline50+2, metadata list excludes comment, detail preserves literal
comment, legacy submission staysnull despite context origin,9 successful reads
link9 audits/canonical events, revoked grant403. PID1065820 graceful0/TLS removed;
cleanup CLI0 schemas[],DB0,8768/8769 closed, explicit lease END acknowledged.
This is source/API readiness, not FE06.3 browser/visual or whole-gate acceptance.
Aquinas continues actual reports consumer in exclusive operator directory.

### Initial200% operator clipping fixed; FE06.3 activated

Aquinas reproduced required active-tab clipping before focus, and later initial
button/fact text clipping. Public TuiTabsWithMore candidate was rejected; accepted
solution uses public vertical=start tabs with orientation semantics, concise
contextual Open/Close captions retaining full accessible names, and normal owned
heading/definition-list wrapping/min-inline-size. No Taiga internal styles,
forced scrolling, font-scaling disable or pointer workaround.33 units/static pass;
initial configured320px/200% direct tabs/history/overview and whole text-fragment
containment regressions pass.18 current MX images reviewed.57 affected HTTP cases
pass behavior; CLI1 RO preserved separately,96 changed images reviewed.

Affected actual PostgreSQL21 candidate CLI0;66 images reviewed, then fresh
ordinary21 CLI0 in1.3m NO updates and all66 match. Raw
`/tmp/peerly-operator-layout-pg21-normal1.log`. All243 current image hashes and
source manifest unchanged during normal run; fresh schema
frontend_2f42594b7a834341ae61875685420a6a observedHEAD43. END schemas[],DB0,
API/storage graceful shutdown,38385/8768/8769 closed,owned empty TLS removed.
This closes the scoped initial-caption/facts defects, superseding earlier
qualification below. Global aggregate RO remains OPEN, no whole-gate pass.

FE06.3 delegated to Aquinas immediately: read-only retained reports plus explicitly
opened canonical timeline/event/audit inspection, actual5 mounted GET contracts,
M06/M07 and retained facts from M02. Exact handoff frontend/OPERATOR-HANDOFF.md;
no fictional queue, moderation actions/counts/role flag. Same exclusive operator
files/ledger; Halley owns route/fixtures/shared infrastructure and causal RO work.

### FE06.2 acceptance qualification: required active tab visibility

Parent requested product assessment before next scope. Actual initial320/200
selected Goals caption is clipped (scrollLeft0, content396/container256), and is
fully visible only after natural keyboard focus. This is not a deliberate
ellipsis/full-label presentation; keyboard success does not close initial
visibility. FE06.2 evidence above remains valid, but completion is qualified by
this UX defect. Aquinas owns a bounded fix via documented public Taiga layout/tab
mechanisms and initial-label geometry regression; no forced scroll/internal CSS.
Next reports/investigation delegation follows this fix, without speculative APIs.
Halley owns independent aggregate RO; concrete next minimal real-TuiTextfield
causal trace and finite stopping criterion are in frontend/FONT-WATCHER-REPRO.md.
No full-app runtime rerun or new dependency patch authorized by that plan.

### FE06.2 academic slice: scoped acceptance

Actual goals/help operator tabs completed by Aquinas.33 scoped unit tests and
static checks green; HTTP39 behavior passed but original strict runtime wrapper
CLI1 RO remains preserved.75 HTTP images reviewed, including finite MX3 CLI0
keyboard accessibility checks (documented initial horizontal tab scroll limitation).
Real PostgreSQL candidate12/12 CLI0;42 PNGs reviewed, manifest
`/tmp/peerly-operator-academic-pg12-review/manifest.json` SHA256
`d47621c7976ab8b529202c47388b1a6fbf317ba1a81179bb664efd3931501605`.
Fresh-schema ordinary comparison12/12 CLI0 in51.6s with NO updates: all42 accepted
baselines unchanged/matched. Raw `/tmp/peerly-operator-academic-pg12-normal1.log`.
Observed HEAD43 and fresh schema frontend_0350e4020ce64261a4fcf7a54665b3a2.
Lease END: schemas[],other DB sessions0, graceful API/storage shutdown,
ports38385/8768/8769 closed and owned new empty TLS dirs removed. Source/fixture
hold released. This accepts the implemented academic slice with scoped evidence;
prior aggregate RO remains independently OPEN. No full frontend gate claimed.

### FE06.2 academic source proof and browser boundary

Aquinas final scoped33/33 units passed with95 thresholds unchanged; explicit
pending-roots regression first reproduced cancellation during history pagination,
then passed after scope cleanup was separated from cursor option updates. Static
ESLint/ngc/e2etypes/styles passed. HTTP39/39 behavioral assertions passed1.3m,
strict wrapper CLI1 nativeRO; raw
`/tmp/peerly-operator-academic-http39-candidate1.log`.72 PNGs await offline review;
this is not a clean runtime gate or accepted full academic feature.

Lead actual API-only fresh isolated HEAD43 academic fixture proof CLI0:
53 roots50+3,53 active-goal revisions50+3,53 help revisions50+3, explicit latest
saved clear, historical stored slot order/labels/literal context, privileged reads
for active/hidden/banned/deleted, empty incomplete owner,15 audited reads linked
to15 canonical events and revoked grant403. Raw
`/tmp/peerly-operator-academic-source2.log`; first source1 failed only its own
incorrect expected audit count16 instead of15 and is preserved. No production fix
or schema patch. PID1033333 graceful0/TLS removed; cleanup CLI0 proves schemas[],
other DB sessions0,ports8768/8769 closed. Explicit Noether lease END delivered.
No browser-based real-PG academic acceptance claimed yet.

### 8 November: approved bounded budget, superseding earlier budget blockers

Owner explicitly approved initial maximumWarning/maximumError525kB; component
styles remain4kB and warnings still fail. Actual current production CLI0,
506633bytes/525000,18367bytes headroom; stats SHA256
`44f651ff3cb568254ae26720bff8fcf4cd4e4d3fb06a924e1a521adc0655e9b5`.
Accepted FE06.1 immutable source with only approved budget config: CLI0,
504035bytes, stats SHA256
`16af9220e3d9a2cbeada4637d784571b8940c51da64c1de2a593c32197e0fe59`.
Both prerender1 public route, no budget warnings. Logs
`/tmp/peerly-budget-525-production-build.log` and
`/tmp/peerly-budget-525-fe061-baseline-build.log`.
See frontend/BUNDLE-BUDGET.md for source provenance, shared Angular forms/common
attribution, rejected larger temporary Signal Forms prototype, and future explicit
approval requirement. No undocumented attrs or forms migration adopted; byte
experiments stopped. This supersedes historical504.04/500 blockers below.
Existing tooling suite CLI0:50/50, no skipped tests; raw
`/tmp/peerly-budget-525-tooling.log`. Prettier completed for changed config/docs.
Global aggregate RO remains independently OPEN; no whole-gate success claimed.
FE06.2 academic implementation continues with Aquinas; lead's deterministic
academic fixture additions are static-checked, not yet real-PG accepted.

FE06 real PostgreSQL candidate completed12/12 assertions47.5s, CLI0 with no owned
runtime diagnostic in this run. Raw `/tmp/peerly-operator-pg12-candidate1.log`
SHA256 `9763f643c47b861a9d2539a5da8893bc43a1d66266941ec5e0bf12ea60d8efe1`.
Observed isolated migration HEAD0043_operator_profile_media, public72bba unchanged.
END cleanup: frontend schemas[]/other DB sessions0,3 new empty worker TLS dirs
removed/main TLS auto-removed,ports38385/8768/8769 closed,PID1015069 graceful exit.
Fixture finally disposes3 pools/admin; no direct per-pool telemetry claim. Aquinas
reviews27 candidate PNGs offline after END. Conditional ordinary12 NO updates is
allowed only after all images coherent and a fresh Noether READY lease, to verify
deterministic retained data across a fresh schema. This is not a whole-app check,
RO resolution or budget acceptance; strict504.04/500kB remains open.

Corrected FE06 operator HTTP images are now fully reviewed:87 references,
69 changed and18 original SHA-preserved, prior12 accepted image hashes verified.
Final manifest `/tmp/peerly-operator-remaining36-review/current87-reviewed.json`
SHA256 `dbde2cef9d94df70f06861c432caadbb54a15f5daafe13552827e4531b34ab26`.
Remaining36 candidate completed CLI0/1min, raw
`/tmp/peerly-operator-remaining36-candidate1.log` SHA256
`3d8f46d22f751abdfef39523b86bfa7736e6cbc7f580cf6a9b8df0ec2080b982`.
This final finite run has no runtime error; previous operator RO failures and
whole-app blocker remain. No full ordinary60 comparison has been claimed.
Aquinas receives a conditional browser resource for actual operator PG12 only
after fresh Noether READY named FE06-operator-PG12; no fixture before both. Lead
holds shared source and starts no competing heavy work. Public unsupported
ngNoCva remains unused; strict504.04/500kB budget remains unresolved.

Bounded import-graph attribution is complete, not a production fix. Under the same
public Architect diagnostic context, full initial505.39kB versus501.95 without
operator and504.82 without Chats. Operator contribution concentrates in shared
Angular forms (~2105B) and common (~1574B); Chats contributes about570B. Temporary
fileReplacements and outputs remain under /tmp; actual routes/config/features were
not removed. These diagnostic sizes differ from strict CLI504.04 and cannot be
used as a passing500kB production gate. ngNoCva was never added; no documented
supported Taiga custom-CVA pattern established. No budget waiver, widget swap or
private workaround is justified; budget remains an explicit unresolved blocker.

Operator fixes12 passed assertions but CLI1 RO, reviewed10 accepted with desktop2
requiring normal owned grid alignment. Subsequent desktop2 passed assertions,
CLI1 RO; both screenshots now reviewed/accepted, manifest SHA256
`5b3983d722d66d47b938aa90ab6edd9274f88eeff566f355646e2be776aa5970`.
Current final87 inventory records12 accepted current checkpoints,18 unaffected
SHA-preserved references and57 affected images pending. Aquinas now owns a bounded
remaining36 browser lease from the exact report mapping (57 affected PNGs plus3
unchanged checkpoints in mixed scenarios), no full60/PG/global repeat. Lead shared
source stays frozen; no diagnostic/browser concurrency or observer patch.

Parent public-API constraint supersedes the proposed ngNoCva experiment. Presence
in Angular's internal selector/source is insufficient proof of supported custom
Taiga CVA application usage. Official searches found an Angular-member discussion
for different FormValueControl interoperability, not a documented Taiga native
select/CVA pattern. Decision: SKIP the attribute; worker instructed to remove only
any provisional attribute/tests while preserving verified UI/nullability fixes.
No undocumented attribute, dependency patch or escape hatch is accepted. Budget
attribution continues independently; current strict gate remains504.04/500kB.

Production quality blocker is now separately recorded: strict build504.04kB initial
exceeds unchanged500kB budget (`/tmp/peerly-operator-production-build2.log`). A public
SSE lazy-load experiment changed only about30B and was fully reverted, including
its provisional test; original root startup barrier remains. Strict --stats-json
also fails without emitting files. A separate public Architect diagnostic-only
compile emitted `/tmp/peerly-operator-diagnostic-output/browser-stats.json`; it is
NOT production acceptance, leaves workspace budgets unchanged and exits1. Its
505.39kB differs from CLI context and is not an exact byte comparison. Module
weights implicate shared Angular forms/common, not stream body. Operator imports
broad TuiSelect declaration array despite native-select-only usage; worker narrows
to exported public TuiNativeSelect in its current fix batch, then strict build must
prove any gain. No budget waiver or dependency-source modification.

Operator87 review is complete but images are not accepted as clean goldens:
320px/200% labels and Search text clip; desktop CardLarge leaves excessive gaps;
three complete-filter HTTP doubles contradict actual filters. Worker fixes real
layout with public labels/owned responsive layout and corrects fixture projections.
Original87 images archived; reviewed manifest SHA256
`1160c57c8ee15abd1c475c1978976e596c61af5128a692cb1a2fcaaf0c439208`.
Native select defect is also genuinely reproduced: public cleaner emits null
through Angular CVA despite nonNullable control, causing search value.trim failure.
Raw red `/tmp/peerly-operator-select-null-red2.log`; no false production claim from
the earlier no-match command. Typed nullable controls/actual default filter mapping
are being implemented with meaningful regression coverage. No new browser/PG or
whole gate is running. Global native RO skipped target remains unknown.

One bounded concrete native input experiment completed after operator HTTP END:
standalone installed watcher/textfield companion plus explicit1×1→1440×900
viewport cycle and actual matcher,1 case/1.5s CLI0. Metric16 and offset0 writes
remained unchanged, style mutations0, companion1×56 restored, real28→17 font
control passed. Raw `/tmp/peerly-font-minimal-explicit-viewport1.log` SHA256
`dc91ee37772bd1ecf4bbcce225c6474695fba3be80889e5b25ec6a38a49ca88d`.
No native RO, no extra dependency patch or repeated full-app variant. This
simplified standalone fixture still lacks Angular render ownership; exact skipped
target/cause remain unknown. Owned browser/server closed. Aquinas's operator60
candidate stopped10 pass/1 fixture assertion fail/49 not run with native RO;
nullable fixture had7 absent records, not8 because account identity remains.
Worker gets a fresh browser lease only after fixing that semantic assertion and
checking remaining cases offline/static. No production defect claimed.

FE06 source4 real API probe passed CLI0 on actual72/head43. Actual live Google
operator without student membership/activation gets `/me`200/student capability
false; protected search/detail reads4 retained states, nullable data and authorized
missing404. Seven successful/missing inspections have7 matching canonical events.
Grant revoke403, restore200 and replacement actor200 are real protected responses.
Raw `/tmp/peerly-operator-source4.log` SHA256
`5ad33f490a669b633930d888dda634dbad73f40e0f48d5124c0422a6f70fc544`.
Deterministic past source IDs/dates keep visible metadata stable without clock or
UUID patches, masks or production auth changes. This is retained-read fixture/API
acceptance, not student writes, storage binaries or browser acceptance. PID995923
ended gracefully; schema/other DB sessions empty,3 pools disposed,TLS gone and
listeners closed. Explicit END Noether recorded. Aquinas's scoped unit count is
corrected to17 (not initial18 estimate); aggregate95 thresholds pass. The apparent missing operator-search.ts table row is
resolved: actual LCOV includes the file at SF line345 with all its statements,
functions and branches covered; the text reporter hides fully covered files.
No exclusion/configuration change or additional run was needed. Aquinas now owns
the operator HTTP-boundary browser lease, with exact collection count before its
first candidate run. Actual PG UI still requires a fresh backend lease.

FE06 actual Operator consumer is now lazy-mounted at `/operator/accounts` inside
existing content QueryClient; route formatting/typed ESLint/ngc--noEmit pass.
Aquinas owns exact operator unit18 run after source-probe cleanup; lead performs
no competing heavy checks. New deterministic retained ORM graph has fixed past
source IDs/dates and all FK constraints intact; live sessions/grants/audits still
use actual database time. Two helper Python files pass strict mypy and fixture
Ruff. Real source2 seed returned201 (graph inserts successfully), but subsequent
`/me` assertion failed before its sanitized status/code was captured; the cause is now proven to be the temporary runner's wrong service origin:
backend_fixture.py serves storage_app on TLS8769 and API app on8768. This was a
storage404, not a product/session defect. No real operator API acceptance yet. Owned process
stopped gracefully, schema/DB sessions/listeners/TLS cleaned, explicit END sent.
Earlier source1 failed before assertions due wrong temp-runner readiness route,
now corrected from actual Playwright configuration. No production auth change,
role fabrication, masks or clock/UUID monkeypatch is justified by these results.

FE06 operator account workspace is activated for Aquinas: exclusive
`frontend/src/app/screens/operator/**` plus `operator-frontend-progress.md`.
Concrete handoff `frontend/OPERATOR-HANDOFF.md` binds approved M03/M04/MX to actual
public72 search/detail GETs. No role endpoint or /me capability exists; Noether
confirmed live Google session/current explicit grant authority on each request,
403 `operator_access_denied`, no student activation requirement. Lead retains
shared composition/routes/session/transport/fixtures/theme. No fake counts,
moderation controls, unsupported tabs or binary photo permissions.

Lead added actual source preparation in `testing/operator_fixture.py`, bounded
loopback seed/grant/audit hooks in `testing/backend_fixture.py`, and typed
`testing/operator-fixture.ts`. Exact scenarios authorized/denied/revocation/
replacement; helper returns operator/replacement IDs and active/hidden/banned/
deleted/nullable target IDs. HTTP-only synthetic cookies stay in Node, not page JS.
Targets use real profile/media/registration setup and visibility command; operator
is deliberately unverified/unactivated. Grant revisions use actual DB clock and
models; audit hook compares metadata audit count with linked canonical events.
Frontend helper ESLint/e2e types pass, standalone driver strict mypy passes,
root-context fixture Ruff/format pass. No PG or browser acceptance of this new driver
is claimed. Its current real setup generates random source IDs/times; deterministic
operator visuals (where actual IDs are visible) remain a concrete fixture task,
not grounds for masks, fabricated UI or server-clock patching. Aquinas can proceed
with typed guards/forms/queries/unit checks independently. Global RO skipped target
and causal mechanism remain unknown; no blind diagnostic or dependency patch added.

Focused corrected Chats HTTP30 candidate2 completed30/30 behavioral assertions
in1.4m. Overall CLI1 retained native RO; no complete runtime acceptance. Raw
`/tmp/peerly-chats-http-canonical30-candidate2.log` SHA256
`2010a1f83c0988cd35c269120a38947f7c03761576f978b85d06e433b3839091`.
Actual fixture GET projections after confirmed send/share/ACK now agree with their
receipts; these are test-double corrections, with no production change. Browser
and38385 are closed, no PG lease remains. Worker completed63/63 screenshot review:30 changed and33 identical; untouched90
hashes verified against preserved original153. Manifest
`/tmp/peerly-chats-http-canonical30-candidate2-review/manifest.json` SHA256
`f5e4c3407533fd07ad7dfb9d6e23d7afc7045364d40c468abc6417324af9e8b0`.
All22 old HTTP mock inconsistencies are resolved;195 current references
(153 HTTP+42 PG) reviewed. Three desktop RO contexts are exactly mapped in
`/tmp/peerly-chats-http-canonical30-candidate2-ro-mapping.json`. No full84,
PG repeat or normal comparison solely to seek a clean RO outcome is scheduled.

Latest real SSE candidate3:3/3 assertions pass29.2s,3 PNGs reviewed,
but CLI1 retained one desktop native ResizeObserver plus Vite/Angular wrappers.
Raw `/tmp/peerly-changes-pg3-candidate3.log` SHA256
`2c7c53417f8bb06c34aa1e9bd87c7a0149ebddc8a7bf63b6610781d095c66dee`.
Actual publisher/authorized SSE delivered a real incoming message, exact source
sequence/timestamp/author, canonical preview/history and unread1/read-positionnull;
no automatic send/ACK. No backend cancellation traceback in this run. Explicit
FE05-SSE-PG3-preview72 END cleanup proves schemas[]/otherDB0/three pools disposed,
ports closed and own empty TLS removed. No normal retry or global runtime claim.
Aquinas's first corrected-fixture HTTP30 candidate ended5 pass/1 test failure/
24 not run, CLI1 with one native RO context. Server reread unread0 passed; the new
ACK assertion incorrectly used an accessibility locator for the CSS-hidden mobile
Conversations region. Raw `/tmp/peerly-chats-http-canonical30-candidate1.log` SHA256
`677203b5172abc53fea273f15763094445085dea1c67623abd3903c82c06da25`.
Worker corrects the retained DOM locator using the proven labelled-region pattern,
checks all new assertions offline, then owns a fresh affected30 browser lease after
static checks. No production change or full84 rerun. Original153 PNGs preserved;
lead shared source stays frozen during the worker's browser run.

Shared SSE HTTP integration found and fixed a real transport-ordering defect:
Angular delivers error-response headers/progress before HttpErrorResponse. JSON503
was incorrectly treated as invalid SSE, permanently pausing safe retry. Error bodies
now wait for the actual status policy;408/429/503 regression events preserve the
last validated cursor.51 scoped units pass,98.14/95.27/100/100 coverage,
`/tmp/peerly-changes-http-header-green2.log` SHA256
`7530fb3cc375883bd2cfd540befd039326d8ccdaee29d61f21a60cce64856bb3`.
HTTP candidate3 passed9/9 across three projects, CLI0/38.7s;9 PNGs reviewed,
manifest `/tmp/peerly-changes-http-candidate3-review.json`. Raw
`/tmp/peerly-changes-http-candidate3.log` SHA256
`177f85eea0e86f4147f9fcf0623da9d8524659b75303b073d6a63847db3e089a`.
Ordinary no-update comparison passed9/9 CLI0/35s, raw
`/tmp/peerly-changes-http-normal1.log` SHA256
`6711e9fe63b6e7ce0694159a45f44ee5dcd21874e4b9069b23189c0e50f55533`.
First real publisher/incoming candidate on fresh FE05-SSE-PG3-public72 reached
actual delivery but failed the global text locator: list preview and confirmed
bubble both correctly matched.1 failed/2 not run; no RO/cancellation in its raw
`/tmp/peerly-changes-pg3-candidate1.log`. Cleanup proves schemas[]/otherDB0/three
pools disposed/listeners closed/own empty TLS removed; explicit END sent. The test
now scopes both history and preview separately; fresh FE05-SSE-PG3-locator72 READY
requested before another fixture. This is not real-SSE or global acceptance yet.

Latest bounded diagnostic: native minimal watcher fixture baseline completed CLI0
with no observed error, not a reproduction or runtime fix. Width-only metric16→16
repeated offset0 with zero style mutations and unchanged1×56 companion; real
metric28→17 preserved font scaling with two actual style mutations. Plain screenshot
did not produce the application's1×1 capture/restore transition. Source hashes,
limitations and artifacts are in `frontend/FONT-WATCHER-REPRO.md`; no extra dependency
patch or full-app instrumentation variant was applied.

FE05 HTTP candidate3 passed84 assertions but CLI1 (nine owned Chromium RO contexts).
All153 PNGs reviewed;22 reveal stale/inconsistent HTTP fixture projections, not
accepted production regressions. PG attempt1 failed before collection on missing
Node Angular compiler bootstrap (centralized fixture import fixed); attempt2 failed
on lost-reply test Route handling after the actual send succeeded (fulfill before
unroute corrected). Neither is PG9 acceptance. Fresh named
`FE05-chats-PG9-lossorder72` READY granted by Noether on HEAD43/public72; browser
lease transferred to Aquinas for the exact corrected nine scenarios.
The candidate3 lease has now ended with cleanup confirmed:9 assertions passed,
but CLI1 retained four RO contexts and backend cancellation tracebacks;42 candidate
PNGs await review. Raw `/tmp/peerly-chats-pg9-candidate3.log`, SHA256
`4d3df532fcbd71a396a3c75de15d31772f9b73383b4e8ca6cb46af03326a0dc9`.
No PG9 runtime acceptance is claimed. Nash's bounded isolated PG is released.
No shared DB reset.

After that END, the standalone public screenshot-matcher comparison completed
1 test/1.4s CLI0 with no observed error. It still lacks the application's1×1
transition, so causal reproduction remains incomplete. Actual artifacts:
`/tmp/peerly-font-watcher-minimal-baseline-1794134871357/`; raw
`/tmp/peerly-font-minimal-matcher1.log`. No extra source patch, global gate rerun,
font-scaling disablement or error filtering. All diagnostic browser/server resources
closed before releasing the next worker.

Current generated contract: tested72/head43, SHA256
`bba903269460f15f8635c725fb00695cca51d5895a20b4d7dafbe5628ba229a4`.
Operator AI inspection adds two GETs; previous70 paths/components are unchanged.
Generation and drift pass (`/tmp/peerly-fe72-contract-{generate,drift}.log`).
Previous70 generator8 and app types passed; new shared SSE source has separate
spec/e2e type and typed ESLint evidence below. No full72 backend/frontend gate is
claimed: accepted backend full2928 is green; frontend aggregate runtime remains
blocked separately by native ResizeObserver diagnostics.

Latest completed full application verification (before FE05 additions):851 unit tests/30 files, coverage
96.27/95.79/98.02/98.73%, all95% thresholds unchanged. Production stats build499.91kB,
CLI0. Full formatting, typed ESLint, styles, Knip and e2e types pass. Tooling49 passes,
including the new compiler-emission guard. Unit raw `/tmp/peerly-photo-observer-full-unit.log`
SHA256 `6013bd0437f28561b060705a1d92e38a0be0743b48307c7ac0015c601518e4b4`;
build `/tmp/peerly-photo-observer-build.log` SHA256
`760f859f9163a51f62c96f746d5cfefc70db97330924cc672c52c8d88a0d4382`;
tooling `/tmp/peerly-emission-guard-tooling.log` SHA256
`599132e42da89fe3de815788dce0a58b066873c4b1db71550893e04bfcad4d1a`.

Composer HTTP boundary is accepted:87/87 normal across three projects,198 current
reviewed PNGs compared with NO updates, runtimeCLI0/2.1m. Raw
`/tmp/peerly-compose-boundary-normal1.log`, SHA256
`4540b58ad177dcb1486ca2b5da691bc421c5effc1b4e5ef80f23a79c40497b19`.
The scrolling body/stable footer uses public fullscreen Taiga, a single public-context
labelled heading and owned layout containment. No pointer choreography or hidden
error sizing controls. Every denial's actual recovery link/date is captured.

Current real Discovery is accepted:9/9 normal on coherent67/head42,33 reviewed PNGs,
NO updates, runtimeCLI0/40s. Raw `/tmp/peerly-discovery-pg9-head42-normal1.log`, SHA256
`de685cf519e755690006f840f0ac46c1f6968b9107bcf52d8225f13f06f1ec9e`.
Fixture890517/schema/three pools/TLS/listeners cleaned; matching END acknowledged.
The native image resource fix preserves its URL during revalidation, retires after
DOM update/removal and clears across actor replacement. Query state stays canonical;
only a native Blob identity/ObjectURL handle is retained, explicitly authorised.
No TanStack fork/deep import or budget waiver; established QueryObserver restores
499.91kB instead of injectQuery's measured679.02kB namespace-retention path.

D03 is accepted complete_scoped: final real composer27/27 normal,75 reviewed
references, runtimeCLI0/1.4m on coherent67/head42. Raw
`/tmp/peerly-compose-pg27-footer-normal1.log`, SHA256
`5c8e657084605b579715c1291e409d1960f1340e0e86d3219dcf1f6c750e6deb`.
HTTP198 plus PG75 gives273 reviewed references. Fixture/schema/pools/TLS/listeners
were cleaned and matching END acknowledged. Production footer remains unchanged;
test captures center the complete public field rather than relaxing visibility.

FE05 Chats is activated for Aquinas, exclusive `screens/chats/**` and
`docs/planning/chats-progress.md`; precise actual-contract handoff is
`frontend/CHATS-HANDOFF.md`. Its genuine first list/detail consumer is mounted
at `/chats`; scoped Chromium unit resource granted, no concurrent lead heavy run.
Lead retains routes, session, transport, generated types, fixtures and browser leases.
Shared SSE integration is implemented but NOT feature-accepted: one actor-owned
HttpClient stream under the existing content QueryClient, canonical prefix
invalidation only, no stream store or automatic command/ACK replay. Root provider,
actor cancellation, precise cursor resume, capped buffers and /me revalidation have
40 passing scoped tests, coverage97.91/95.27/100/100%, unchanged95 thresholds.
Raw `/tmp/peerly-changes-unit5.log`, SHA256
`3d778efd20c1b2aaf951345a64f89177b4d797c726cd118020065485e085332b`.
Typed ESLint/spec/e2e types pass in `/tmp/peerly-changes-{shared-eslint4,shared-types4,e2e-types4}.log`.
HTTP-boundary auto fixture provides only explicit heartbeat wire; real FastAPI is
unmocked. Three actual-screen SSE browser scenarios are authored, not run/reviewed.
Retry policy is now corrected and scoped-green: malformed protocol/permanent4xx
pauses until independent /me authority read; one resource-owned auth confirmation
cannot spin same-owner stream/auth GETs. Transient socket/408/429/503 retries only
GET and preserves the last validated cursor. Latest51 tests CLI0, coverage
98.08/95.07/100/100%, unchanged95. Raw `/tmp/peerly-changes-retry-unit2.log`, SHA256
`442b44d6250342d0a038230ad5a75cdfbe15b5ee4c3f7f6e7fa2dad8a9cd2908`.
Scenario matrix is colocated `screens/changes.scenarios.md`; authored browser cases
and real publisher->stream->query integration remain unaccepted. Shared production
SSE source is frozen during Aquinas browser windows.

Backend coherent43 and actual70 export are accepted as a targeted contract handoff;
student contracts are unchanged. Shared source is not a new full frontend acceptance.
A fresh named PG fixture lease is still required, not inferred from coherence.

Lead's first shared FE05 slice: actual `/chats` lazy route and component-owned
`ImageResource` extracted from the proven Discovery implementation for the genuine
third avatar consumer. Blob identity/ObjectURL lifetime only; no query mirror.
App ngc--noEmit passes; existing11 Discovery photo regressions pass CLI0, including
unchanged-Blob URL stability, post-DOM retirement and structural actor cleanup.
Raw `/tmp/peerly-fe05-image-resource-unit.log`; this targeted run disables coverage
explicitly and does not replace the full95% acceptance gate. Worker first unit run
passes22 assertions but scoped coverage fails94.05/92.96/97/96.2%; no thresholds
changed. Subsequent worker unit3 is34/34 CLI0, scoped coverage
97.32/95.89/99.13/98.62%, thresholds unchanged; raw
`/tmp/peerly-chats-unit3.log`. This is scoped acceptance, not whole-app coverage.
Worker unit5 after ACK/share implementation passed49 assertions but exited1 on
94.24% branches (other metrics96.7/98.39/98.38); no threshold waiver. Its earlier
NG0950 required-input timing defect is fixed through ngOnInit subscriptions and
same-composition tests now pass. Worker unit6 subsequently passes53 assertions,
CLI0 with scoped97.22/95.8/98.39/98.58%, thresholds unchanged;
`/tmp/peerly-chats-unit6.log`. Worker unit7 adds Kuala Lumpur midnight/month/year
cases:56/56 CLI0, scoped97/95.85/97.42/98.27%, unchanged thresholds,
`/tmp/peerly-chats-unit7.log`. Browser acceptance is still open: finite3 Chromium
smoke1 stops1pass/1fail/1notrun because invalid submit renders an error without
focusing the textarea; native ResizeObserver also makes runtimeCLI fail, separately
from the product focus defect. Raw `/tmp/peerly-chats-http-smoke1.log`; no PNG or
runtime acceptance and no RO fix claimed. Worker fixes focus through supported
TuiAutoFocus/Angular lifecycle, without pointer choreography or forced events.

Initial real Chats driver now has isolated empty/messages namespaces, actual
Preview/Send/Accept-produced conversation IDs and two-author SendMessage records.
Lead owns `testing/chats_fixture.py`, `testing/chats-fixture.ts`, backend-fixture
route and known-subject integration. Ruff/strict helper mypy/e2e types/typed ESLint
pass. Initial source-only real PG acceptance is recorded below. A concrete future-time clock proposal was rejected
before PG execution: canonical request/message events also update freshness source
facts, making later real-clock GET observations invalid. The unaccepted clock helper
and wiring were removed; current cohorts keep real business time. Do not extend
sessions, bypass freshness, suppress canonical recorders or mask date UI to hide it.
Owner selected the smaller design-consistent alternative: no server clock override
and no dedicated fixed-clock command. Chat UI formats today HH:mm, yesterday
Yesterday and older dates per v2; exact absolute datetime/title remains inspectable.
`prepareChatsFixture` now reads actual details/history, returns those generated DTOs
for exact source timestamp/sequence assertions, asserts the yesterday scenario's
single KL source-day prerequisite, then fixes only Playwright browser wall time to
noon next KL calendar day. Real sessions, freshness, source events and SQL stay on
real time. Static boundary cases cover exact today's clock text and KL boundaries;
real PG yesterday screenshots now have PG9/42 and SSE3/3 reviewed image evidence,
with their runtime failures recorded above. Helper formatting
passes; e2e types encountered an unrelated worker in-progress unused context in
chats.visual.spec.ts, so no new whole-e2e green is claimed. Later peer lifecycle,
pagination/share/race cohorts remain ready-task dependencies, not implemented yet.

FE05 source-only PG probe accepted: `FE05-chat-source-smoke2`, coherent head43 /
actual70, CLI0. Fresh isolated migration HEAD and actual empty/two-author-message
cohorts passed real HTTP details/history. Actual timestamps are aware and ordered
from acceptance; sequences1/2 and author/conversation IDs are canonical. Repeated
GET preserves unread/read-position (no ACK), actual onboarding/session reads remain
coherent. Server/PostgreSQL/expiry/freshness clocks were never replaced. Raw
`/tmp/peerly-chat-source-smoke2.log`, SHA256
`6bd0f0fcef9bd586cd41c56b0158d250824143b521b34278b770867aa9049cbb`.
Owned PID917515 stopped gracefully; no new frontend schema remains, TLS removed,
8768/8769 listeners closed, matching END sent. This API fixture probe did not run
browser scenarios, change a browser clock, compare PNGs or validate SSE/AI/providers.
The later PG9 and SSE3 runs now cover Yesterday visuals and exact timestamp/title
assertions; this source-only probe itself never claimed that coverage.
A new independent goal-change cohort now performs real ReadOwnGoal/SaveOwnGoal CAS
after AcceptRequest, preserving original baseline and changing source version.
Ruff/strict helper mypy/typed helper ESLint pass; the later PG9 run exercises
this actual goal-change cohort with assertion/image evidence but runtime failure.
It is reserved for the real UI goal-sharing scenario, not a fabricated DTO/context.

Latest feature geometry: Aquinas unit11 has57 passing scoped assertions with all95
thresholds unchanged. Finite Chromium HTTP4 passed3/3 runtime-clean, including native
invalid-submit focus,320px/200% no horizontal overflow,420px keyboard viewport with
the entire public field/counter/Send visible and exact multiline value. Six PNGs
were reviewed, then compact public TuiCell/TuiTitle markup refined before the full
candidate. Full84 HTTP candidate1 stopped on a test-boundary unread fixture mistake:
1fail/83notrun, no runtime diagnostic. Empty conversation unread is corrected to0;
strict assertions remain. No full chat browser acceptance is claimed.

Backend quiet coordination: head43-targeted-AI-heavy2 completed2 GREEN; next
head43-full2-AI-heavy3 explicitly granted only after Aquinas unit/candidate natural
END, no active frontend runner interrupted. New heavy frontend checks stay held
until explicit initial-AI-phase END; full backend source hold is separate.

Shared real-SSE fixture preparation is source-only: known stream namespaces,
finite driver-owned synthetic peer credentials, actual SendMessage, bounded real
PublishChanges and one incoming->stream->query browser scenario. Real server clocks
are unchanged. No direct SQL messages, fake frames, private logs or external messages.
Static/runtime validation still pending; no fixture during AI quiet.

Accepted initial stream boot correctness: root content composition awaits public
ApplicationRef.whenStable exactly once without blocking environment initialization,
then checks DestroyRef and reads the latest canonical actor through watchChanges.
No private PendingTasks token/opt-out, interceptor bypass or readiness timer.
Reconnect never awaits application stability again. Four real root injector/public
PendingTasks lifecycle tests prove pending boot, destroy-before-ready, latest-actor
prefix isolation and reconnect during a later unstable task. Combined55/55 CLI0,
SSE scope98.08/95.07/100/100%, unchanged95 thresholds. Typed ESLint/spec types pass.
Raw `/tmp/peerly-stream-boot-unit3.log`, SHA256
`1f4370226c41d5f49c7336e7a25bd7c6468755dce40009a95211d0f4294e50e1`.
This is independent startup correctness, not native RO resolution or browser/PG
SSE acceptance. Shared production is frozen for Aquinas candidate3 after candidate2
stopped3pass/1incoherent-pagination-fixture-fail/80notrun with separate nativeRO.
Candidate fixture is corrected, strict actual response guard remains unchanged.

The former single native Blob loading error's precise sequence remains unproven;
subsequent full HTTP87 and current real Discovery9 are clean. This is not a claim
about the independent aggregate native ResizeObserver blocker, which remains open.
No full npm check/app acceptance, live provider/native OS validation or deployment
is claimed. No console filtering, broad blind probes or old-schema fixture reuse.
No owner input is needed. Source contains0 emitted JS; ngc checks require --noEmit.

## Lead review paths

- `frontend/src/app/screens/discovery/discovery-photo.ts` and `.spec.ts`: stable native image resource, after-DOM retirement, structural removal/actor isolation/duplicate retry regressions.
- `frontend/tooling/source-emission.test.mjs` and `frontend/AGENTS.md`: executable compiler-output guard, mandatory noEmit checks and the narrow native-resource ownership clarification.
- `frontend/tooling/openapi-model.mjs`, `.test.mjs`, `frontend/contracts/openapi.json`, `frontend/src/app/api.generated.ts`: constrained actual SSE wire mapping and actual67 readonly regeneration.
- `frontend/testing/backend_fixture.py`: actual separate named change-read pool, restored factory and owned lifecycle cleanup.
- `frontend/testing/verified-student.ts`, `frontend/src/app/screens/onboarding/setup/setup.fullstack.visual.spec.ts`: genuine visibility commit-loss/replay/restore actor and proof. `setup.visual.spec.ts` validates every relevant PUT without conditional assertions.
- `frontend/testing/requests-fixture.ts`: formatting only; no fixture behavior change.
- Discovery real-stack PNGs and setup visibility-replay PNGs:33 existing plus9 new, all reviewed and compared by normal12 at the recorded snapshot. Later photo source requires the queued renewed PG9.
- `frontend/RUNTIME-DIAGNOSTICS.md`, Discovery/setup scenario matrices and owned frontend planning documents: exact evidence, source qualifications and remaining acceptance dependencies.

Aquinas exclusively owns composer production/test/reference changes; its ledger
is `docs/planning/request-compose-progress.md`. No backend, shared root, Git index,
commit/push, deployment, secrets file or live provider was modified by Halley.

## Historical checkpoint evidence

<details>
<summary>Chronological evidence below is historical; the execution window above is authoritative.</summary>

## Execution window

Frontend generated snapshot: coherent67/head42, schema SHA256
`7cfe497e064fb4bc7fcc756b476fb9be60e134f70034f0202f261f6bfcf3c44a`.
All paths remain unchanged from67/head41; only two unused operator enums grow.
Regeneration/drift,7 generator tests and app/spec/e2e types pass for that snapshot;
runtime application source is unchanged by the pure type delta.
All old64 paths/schema entries are verified unchanged;3 operator-only paths and8
operator-history schemas are additive. Generation/drift,7 generator tests and types
pass. No operator UI or streaming client is invented by generating these contracts.

Latest full unit851/30 CLI0,96.27/95.79/98.02/98.73% coverage. Current production
stats build499.91kB CLI0, no threshold change. Raw
`/tmp/peerly-photo-observer-full-unit.log` SHA256
`6013bd0437f28561b060705a1d92e38a0be0743b48307c7ac0015c601518e4b4`,
`/tmp/peerly-photo-observer-build.log` SHA256
`760f859f9163a51f62c96f746d5cfefc70db97330924cc672c52c8d88a0d4382`.
Full format, typed ESLint, styles, Knip, e2e types and49 tooling checks now pass
CLI0. Two formatting files were corrected by their owners; two conditional fixture
assertions now validate every PUT, with no rule disable. Raw `/tmp/peerly-photo-final-*`
logs preserve each gate; tooling SHA256
`e4f77eded2d5ff98ec20daaa48dd6e80a7d2266c8debfb2df83ad90a4e4f05bb`.
The original uninstrumented WK unknown-send normal passed1/1 runtimeCLI0; lead
photo6/setup3 HTTP normal passed9/9 runtimeCLI0 with unchanged reviewed PNGs.
Aquinas completed full composer87 candidate10 and normal87 CLI0/runtimeclean;
all198 current references were reviewed and compared without updates. Fresh real Discovery
PG9 waits Noether coherent42 and its tested contract, with a new explicit lease.

Photo resource regression: a real canonical invalidation unnecessarily revoked and
replaced the displayed URL before new bytes arrived (RED unit preserved). The
established QueryObserver now keeps a single readonly owned Blob identity/ObjectURL
handle for native-resource lifetime only, explicitly allowed by parent; business
projections and query status stay only in TanStack. URLs retire after DOM update,
with structural removal/destroy cleanup.11 photo units cover stability, privacy,
resource release and duplicate retry. injectQuery was not retained: its installed
namespace compatibility path pushed initial bundle679.02kB; no dependency patch or
budget waiver was applied. Current observer source restores499.91kB.

Composer HTTP87 candidate9 stopped40pass/1runtimeFAIL/46notrun on WebKit unknown-send:
Failed to load resource for a new blob URL, not ResizeObserver. A passive one-case
probe passed and observed safe unbound retirement for its sole URL; that does not
prove the prior failed URL's cause. Its precise original cause remains unproven. Subsequent uninstrumented WK1,
photo/setup HTTP9 and full composer87 candidate10 are runtimeclean; normal87 image
comparison then passed, and that evidence is not a claim about the global RO cause.
No console filter or broad blind replay. Aquinas owns composer scenarios/source;
lead owns photo/shared gates. Full87 and renewed composer PG rendering remain pending.

Last accepted clean-source real PG12 is actual64/head41:12/12 CLI0/runtimeclean1.1m,
all42 reviewed PNG comparisons, fixture853287/schema/three pools/TLS/listeners clean.
Raw `/tmp/peerly-discovery-visibility-pg12-normal2.log`, SHA256
`2ea94be704e67c5b6424ff153253b442b29a5650d6de1597e58b8d9b36fd23b3`.
That scope covers Discovery9 and committed visibility ambiguity3; the later photo
source fix requires renewed relevant PG comparison. No active backend hold now.
Global native ResizeObserver remains separate/open; no whole aggregate rerun without
new concrete evidence/fix. Clean src contains0 emitted JS artifacts.

## Current boundary

Actual64/head40 tested enabled export SHA256
`239f40f03719f922906dbae3920c2a33b169f2d6f6011583f42a4df014ea34a5`.
Generation/drift and7 generator tests passed. Server owns suggested_text, quota
remaining/reset, can_send and typed block_reason. No frontend template, quota
arithmetic or inferred admission. Preview/context remains immutable; Send rechecks.

Finite WebKit passive pointer evidence identifies a concrete app layout failure:
Send rect top739.578→765.469 between pointerdown/up at y763 as textarea blur
reveals its actual TuiError. Pointerup/click hit FORM; submit0/invalid0. Raw
`/tmp/peerly-compose-webkit-focus-candidate-3.log`, SHA256
`7b2c336c590c77777ab5d313c4e6cb69a2027bb97669a5b7a20ffebe9b04f169`.
This explains the lost first click; it is separate from global native RO diagnostics.
Aquinas implemented a semantic scrolling content body and stable action footer
through public fullscreen Taiga dialog (documented desktop approximation);
errors retain actual field flow/association and natural wrapping. No pointer
handlers, preventDefault, native focus hacks, guessed height or hidden duplicate
error components. Next acceptance requires stable button geometry through blur,
real invalid submission/focus and keyboard/320px/200% checks before broader replay.
Full unit run for footer source passed848/30 CLI0,96.25/95.81/98.01/98.72% coverage; raw
`/tmp/peerly-compose-footer-full-unit1.log`. Finite two-case WebKit validation/reflow
candidate ended with preserved rect failure: reflow passes but validation still
shifts Send25.89px. No fix acceptance. A single passive containing-height probe
identified native auto-grid intrinsic row growth942→968 in viewport844. Own
size containment prevents that growth, but the next finite run failed because
200% fixed duplicate native heading/Close/footer left zero body height. No fix
acceptance. Next correction uses only the actual public dialog context ID to move
the single accessible heading into scrolling content; native Close remains. Lead authored an additional real
visibility-lost-reply setup scenario with its own actor scope, immutable body/key
replay and server read proving the hidden outcome before retry; its static/browser
format/lint/e2e types passed; real PostgreSQL/browser verification is queued,
not claimed green. It is a standalone real scenario, preserving the original
normal/lost-registration tests without conditional assertions in those tests.
Noether confirmed coherent additive head41. Lease
`halley-discovery-visibility-pg12-candidate1` received direct READY and matching
START: sole12 real PG cases (Discovery9 revised CTA plus visibility replay3),
fresh isolated schema upgrades to41 and uses three independent actual pools.
Raw `/tmp/peerly-discovery-visibility-pg12-candidate1.log`; candidate updates only
intentional PNGs. Backend runtime/DDL/schema hold lasts until matching END+cleanup.
No shared PostgreSQL reset. No new pass claim before runner and image review.

FE03.5 actual study setup, explicit registration, visibility/freshness and both
first tasks are implemented. D03 RequestComposer is integrated into Discovery and
owned by Aquinas under discovery/compose/**. Lead owns routes/session/URL/fixtures.
One component-owned typed form survives its own close/reopen, bounded to one draft
and feature lifetime. No global draft service, Map, browser storage or server mirrors.
Actor-keyed child remains mounted outside deck/loading/card branches; null/error/
ineligible/replacement destroys it. Source changes require explicit reconciliation;
successful send clears the draft and opens the real Requests selection.

## Current product correction under validation

D03 candidate3 stopped at10passed/1failed/76notrun, CLI1; raw
`/tmp/peerly-compose-boundary-candidate-3.log`. 401 recovery/reflow/keyboard passed.
Confirmed send remained in Discover because Taiga closes portals on Router
ActivationStart; its completion emitted closed and parent URL cleanup started a
reverse navigation, cancelling Requests. Lead closeComposer now uses the public
Router.currentNavigation guard and preserves an existing transition. Component
owns no duplicated Router state. A regression checks active navigation is retained
and ordinary idle close still clears only compose. Scoped lint/types pass; full unit-only run completed836/836 CLI0, all95% thresholds pass, raw `/tmp/peerly-composer-navigation-full-unit.log`.
No browser/PG concurrent. Worker also made URL checks semantic rather than assuming
query parameter order. Candidate4 HTTP87 lease is now granted after actual unit END; no browser acceptance claim yet.

## Current D03 browser verification

Candidate4 stopped9pass/1fail/77notrun: native textarea ratio1 viewport assertion
was the wrong footprint, not a production overflow finding. Installed Taiga
textarea intentionally uses clip-path:inset(.125rem) and its own scrollable native
area, producing ratio0.922 even when the complete public control is visible.
Reviewed actual320px/200% failure image shows the rounded textfield entirely in
viewport. Test now checks public tui-textfield host ratio1 plus native focus/value/
keyboard editing, Send geometry and root/section overflow. No ratio reduction,
style/font change, mask or clipped meaningful content. Raw
`/tmp/peerly-compose-boundary-candidate-4.log`; candidate5 granted87cases after
owned visual-only correction/static. Full836 unit checkpoint unchanged.

## Latest D03 candidate5 / focus correction

Candidate5:15passed/1failed/71notrun, CLI1, raw
`/tmp/peerly-compose-boundary-candidate-5.log`. Public control 320px/200% geometry,
confirmed edited send to actual Requests and immutable unknown-send replay pass.
Unicode validation exposes a real focus defect: dynamic tuiAutoFocus input is read
only at ngAfterViewInit, so marking an existing form invalid later does not move
focus. Aquinas is implementing public TuiAutoFocus.focus through readonly viewChild
and afterNextRender with actor/lifetime/open guards, plus meaningful regressions.
No native DOM focus/style workaround or reduced assertion.

A separate read-only cache reentrancy hypothesis was narrowed: the component's
QueryCache listener filters to session keys, so Requests/Discovery invalidation
cannot cause the alleged direct feedback loop. No proven defect or source change
from that premise; bounded actual-session observer unit only if useful. Do not
attribute runtime diagnostics or invent a scheduling fix from this hypothesis.
Candidate5 lease ended; ports38385/8768/8769 clear. No current browser/PG lease.

## Focus/error-accessibility implementation

Aquinas implemented public TuiAutoFocus.focus via readonly viewChild and guarded
afterNextRender; public TuiError uses the same FormControl and actual validation
message. Native aria-describedby points to the actual error ID, and aria-details
retains the counter hint. No duplicate form/state or DOM attribute workaround.
Scoped lint/spec types/Angular templates pass. Initial unit-only checks for own two files cover invalid text/note focus, linked error, close/actor/lock races
and a bounded session-refresh invalidation check. Results and subsequent bounded regressions are recorded below; no browser/PG runners. Last full836 checkpoint predates this accessibility change.

Backend repeat ended2393pass/1AI admission-burst test failure96.88; runtime/schema
actual60/head40 D03 unchanged. No backend full-green claim or auto PG lease.

## Focus/accessibility scoped result and bounded cache regression

Scoped unit run ended67pass/1fail of68, CLI1; raw
`/tmp/peerly-compose-focus-scoped-unit-1.log`. Focus/linked errors/hidden-note render
and lifetime guards pass. The new bounded test using real canonical QueryObservers
and same-actor session refresh observes6 invalidations instead of2 for a successful
existing-pair recovery. This proves redundant session-event finalization, not a
Requests/Discovery feedback loop. Aquinas is narrowing deferred settle to actual
sent outcomes; direct existing-pair onSuccess still invalidates canonical data once
and retains the unsent form. A real active-session/deferred-sent count regression
will establish whether any further correction is necessary before changing code.
No generic finishing store, event bus or server mirror. Resource released; no
browser/PG lease. Full836 checkpoint predates these focus/cache corrections.

## Deferred confirmation: second bounded regression

Scoped UNIT2 ended68pass/1fail of69, raw
`/tmp/peerly-compose-focus-scoped-unit-2.log`. Existing-pair correction passes.
Actual active-session QueryObserver demonstrates deferred sent confirmation causes
4 canonical invalidations rather than2. This is duplicate session-event finalization,
not an infinite Requests/Discovery feedback loop. Consuming/resetting the confirmed
intent/lifetime before canonical invalidation is now justified; Aquinas owns the
minimal correction and will verify one emission, cleared draft/payload and stale
actor safety. No extra finishing flag/store. Focus/error build passes499.91kB,
no warnings (`/tmp/peerly-compose-focus-a11y-build-1.log`), budgets unchanged.
No browser/PG lease; no new full-unit acceptance claimed yet.

## Latest completed evidence

| Check            | Result / limits                                                                                                                                                                                                             |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Full unit-only   | 847tests/30files CLI0;96.25 statements/95.74 branches/98.01 functions/98.72 lines. All95% thresholds unchanged. Native-close pending/settled and campus timezone regressions included.                                      |
| Unit raw         | `/tmp/peerly-discovery-reflow-full-unit.log`, SHA256`a5807fcd15614860e8f7812058def1c075836d611578b1c3b4562a629df4e78e`.                                                                                                     |
| Production       | 499.91kB/no warnings/CLI0, raw`/tmp/peerly-discovery-reflow-final-build.log`. Enforced500kB initial/4kB component style unchanged.                                                                                          |
| Static           | App/spec/E2E typing, Angular templates, scoped lint/styles passed for integration; identical JPEG test data extracted at third actual screen consumer to testing/image-fixture.ts.                                          |
| FE03.5 boundary  | 13scenarios accepted across24+15 normal project cases;39+30PNGs reviewed. Recovery normal15 CLI0 in`/tmp/peerly-fe035-recovery-normal.log`. Separate scoped evidence, not whole-app runtime acceptance.                     |
| FE03.5 real core | 6 normal cases passed56.9s HEAD39, runtimeCLI0/24reviewedPNGcomparisons, raw`/tmp/peerly-fe035-head39-pg-normal.log`.                                                                                                       |
| Offer-help real  | Fresh HEAD40 candidate3/3 passed42.2s, all9PNGs reviewed; normal3/3 passed41.4s, runtimeCLI0/nine comparisons. Real photo/help/first-task CAS/issued context/explicit atomic activation/reload without a goal.              |
| Requests         | Earlier HTTP candidate60 assertions passed but runtimeCLI1 (middle stdout lost; exact diagnostic unknown); no normal HTTP acceptance. Actual PG18 candidate+normal runtimeCLI0,39PNGs reviewed/compared on actual60/HEAD39. |
| Aggregate        | Historical actual54/HEAD37 assertions passed but runtimeCLI1; PG not started. Last fully accepted whole gate remains historical actual25. No new whole-gate run without concrete native-RO fix/evidence.                    |

Offer-help candidate raw `/tmp/peerly-fe035-offer-help3-candidate1.log`, SHA256
`656fb3b38d4730e17ef9f5174ac1a578a624a87a081d93ee67df3b39dddf479b`;
normal raw `/tmp/peerly-fe035-offer-help3-normal1.log`, SHA256
`2b65e830969aa2fba1afb876619b9719c328ad945b465fd1ffdf498fab76f428`.
Both fresh lease READY/START/END handshakes completed, owned servers794136/796513
closed, fixture finally disposed engines/dropped only its schema/removed TLS,
ports38385/8768/8769 verified clear. No current PG lease.

## D03 corrections and active work

The500.30kB build failure was measured, not waived. Removing only DatePipe timezone
argument saved141bytes but still failed. AOT identified new pipeBind3/pureFunction3
callers. Public component DATE_PIPE_DEFAULT_OPTIONS+0800 and readonly derived dialog
options restored499.83kB while preserving campus time and pending policy. Logs:
`/tmp/peerly-composer-datepipe-comparison-*`, options-timezone-build-1 and live-dismissal-build-1.

First browser candidate found a real Taiga lifecycle integration defect: portal
options are captured on open, so a pending boolean remains stale. Both public
closable/dismissible now use the same readonly defer/of current-pending Observable.
Native X remains visible and guarded while pending; explicit Close is disabled.
No manual subscription/store/style override. Candidate2 exercised corrected X and
Escape;8passed/1failed/72notrun, CLI1. That failure was the test returning invalid
/me200null instead of actual401; the boundary double is corrected, production
identity validation preserved. Raw`/tmp/peerly-compose-boundary-candidate-2.log`.

Aquinas now holds D03 HTTP-only candidate5 browser lease:29scenarios/87projectcases,
workers1/maxfail1, explicit baseline update. Raw
`/tmp/peerly-compose-boundary-candidate-5.log`; no result claimed yet. Production
sources frozen during the run. No concurrent unit/browser/PG. Review every PNG.

New composer real-PG driver is implemented but NOT runtime-accepted: isolated
canonical subjects separate from all nine Discovery namespaces; real setup/shared
learning/help and actual Preview/Send/Accept for existing pairs. Helper
prepareComposerFixture exposes readonly selectors, never product credentials.
Ruff and strict mypy pass composer/cohort helpers. Direct strict checking legacy
backend_fixture.py reports11 composition monkeypatch/config typing errors; no
root strict-green claim or ignores. D03 nine real scenarios await a fresh specific
PG READY after its browser boundary is stable. No shared PG reset.

## Open global runtime blocker

Native RO/forwarded diagnostics remain unresolved. Do not schedule another whole
gate without concrete fix/new causal evidence. No observer source scheduling,
realm/pagehide fix, error filtering, clipping or disabled font scaling. The only
library patch remains the reviewed font-watcher0.6 iframe border correction.
Supported Angular destruction disconnects native observers before removing the
watcher iframe(unit regression); browser pagehide is not Angular destruction.
Detailed source/probe limits are in`frontend/RUNTIME-DIAGNOSTICS.md`.

Full untouched ordinary aggregate log:
`/tmp/peerly-discovery-aggregate-check.log`,71624bytes,SHA256
`bf0b1bd5aeb17bb7e378e14c53def25080653fa06ff6188f0b4c23a9182eaf29`.
Exact report mappings are in`/tmp/peerly-discovery-aggregate-contexts.json`:
desktop9b674c… is onboarding callback account_unavailable(:62),a344c… is active
challenge reload(:87), not adjacent photo scenarios. Observer owner remains unknown.
Requests candidate middle stdout was lost to tool truncation; report has no runner
stdout. Never infer its exact diagnostic kind/owner from generic CLI failure.

First FE03.5 HEAD38 candidate raw log:
`/tmp/peerly-fe035-head38-pg-candidate.log`,19902bytes,SHA256
`7bd14eae407bc3c981acd849cfe3b40dc2951dd5570a7e094fd621e0d9ad99eb`.
It preserves late desktop native RO context646903cc…230f while the primary test
already timed out at photo selection. No causal attribution or runtime fix claimed.
Fixture/schema/TLS cleaned and backend hold released after actual END.

Every next justified command writes full raw stdout+stderr to an owned /tmp log,
preserves the original exit status(no masking pipeline), then inspects bounded
output separately. Never rerun solely to recapture a lost diagnostic.

## Concrete fixes / ownership

- Real task-readiness transition: preparing context while save was pending could
  be skipped forever. Actual account-owned readiness is rechecked when mutation
  settles. Immutable completion captures the reviewed saved task for navigation.
- Reflow: public TuiForm fieldset10rem track became320px at200% text; parent
  intrinsic track remained317px even after fieldset correction. Owned grids use
  minmax(0,1fr), public TuiLink actions wrap, Save task is concise, native radios
  share a name. No control CSS override, font reduction, pixel offset or RO claim.
- Budget: removing TuiForm or setup consumer left500.25kB; removing Requests route
  restored499.83. Compiled quota textInterpolate4 added379core bytes. Two logical
  quota metric spans remove that extra helper with all counts/text preserved.
  Comparison sources restored in finally; artifacts are not production acceptance.
- Shared test Requests seed uses fresh participants plus real profile/photo/
  registration/help/preview/send/event persistence. HEAD37 API-only proof passed
  owned received/sent lists/detail/unread/capabilities; own fixture cleaned. Common
  controlled actor guard extracted at the third test helper, preserving Person and
  Discovery public helper results. No fabricated lifecycle rows or DB reset.
- Changed owned paths:frontend/src/app/screens/onboarding/setup/**;onboarding
  composition/layout;shared policy-reference/session/policy guards;content.routes;
  testing actor/Requests helpers and driver;angular.json budgets;frontend handoff/
  README/runtime/scenario docs and this separate frontend roadmap/ledger. No backend
  or backend/shared coordination ledger edits.

## Next ready work

1. Finish D03 boundary candidate5, review every new PNG and run a normal comparison after the concrete corrections; preserve runtime diagnostics separately.
2. Run nine genuine composer scenarios in all three browsers through the real cohort driver after a fresh explicit backend READY and serialized browser lease. No fake provider calls or shared PG reset.
3. Review updated Discovery CTA baselines and final production build for the parent navigation guard. Existing FE03.5 recovery39 normal and activation core6+Offer-help3 real normal cases remain accepted locally.
4. Complete remaining actual frontend screens from the detailed roadmap; text Conversations has accepted actual contracts, while attachments/streaming and native/live providers remain explicit dependencies. No global runtime waiver.

## Corrected real activation candidate evidence

The omitted chooser prerequisite is proven in the preserved first trace: file action starts11047.977ms, while history GET starts11063.967ms and completes50.327ms later. The test bypassed a disabled UI control; source was not patched. After waiting for enabled Choose photo, a fresh HEAD38 candidate passed6/6 with runtimeCLI0 in1.1m. Actual local Google/OTP, name/goal save, native PNG transfer/photo worker, context issuance, atomic activation, lost completion reply with same immutable intent, hide and restore were exercised. All24new PNGs reviewed; fixture/schema/TLS cleaned and hold released. Raw log`/tmp/peerly-fe035-head38-pg-corrected-candidate.log`. Normal comparison subsequently passed6/6 in56.9s on coherent HEAD39,runtimeCLI0 with24reviewed PNG comparisons. Raw log`/tmp/peerly-fe035-head39-pg-normal.log`. This is actual feature acceptance, not global RO recapture/fix.

## Historical records

## Namespaced Discovery seed proof accepted

Fresh actual54/HEAD35 API-only fixture proof passed nine isolated canonical cohorts with22 genuinely activated actors: all27 mode reads returned exactly the cohort's own peer and no next cursor; nine authorized private JPEG reads passed; the legacy Databases alias still returns only SQL. This validates seed isolation and permissions, not the Discovery browser feature. Fixture stopped normally and Noether hold was released. No data reset, hidden foreign actors or custom production filter.

Aquinas reported normal boundary57/57 runtime CLI0 and102 PNGs reviewed, with public compact Taiga card layout and truthful context labels; source-only compiler artifact was removed by its owner after verified task-local copy. Actual54/61 declarations were regenerated/drift checked after that browser END. New HEAD36 is tables-only, old54 schema/runtime unchanged; the next short hold/browser lease was handed to Aquinas for9 real PG candidate cases, then backend release during image review. Shared UI/routes/types54 remain frozen through that active browser run. No additional native observer probes or source workaround.

## Discovery cohort isolation in progress

Aquinas correctly identified that SQL-only activated seeds could appear in another scenario's deck and affect pagination/screenshots. Namespaced driver setup now creates a distinct genuine canonical subject per scenario/browser (nine stable readable labels, UUID5 identity and actual domain subject_key normalization), then saves real goals/help through use cases. Legacy Person SQL setup remains unchanged. No production query filtering, hidden old actors, resetting data, fake normalized duplicate SQL rows or arbitrary topic noise.

The helper contract is now prepareDiscoveryFixture(page, namespace), with modes/pass/undo plus actual browser project; result includes public subjectId/subjectLabel. Fixture body accepts only the known namespace. Worker was informed before any PG usage; its boundary tests do not import the helper. Strict fixture mypy/Ruff and TS helper lint pass. The expanded multi-cohort proof is pending the current backend checkpoint; initial three-mode seed proof above validates the earlier unisolated setup only.

Worker reports full618 units green (95.47% global branches). Its actual source comparison isolated TuiSegmented's3.09kB initial shared-chunk increase. Lead approved public TaigaButton navigation as a clean supported approximation; no defer/control-style hack or budget waiver. Latest worker build499.83kB without warnings. Exact compiler-only artifact was copied to task-local /tmp/peerly-discovery-segmented-before.json (SHA256091213f8ec04ec5fd092caa30e4dabee5d71f598d3ae3256b132ffadc198a0c6); worker removes its own source copy. Shared UI/routes/types remain frozen while its serialized boundary lease runs.

## Discovery seed dependency cleared

Added lead-owned driver POST/__fixture/discovery and testing/discovery-fixture.ts. Synthetic identity/session facts use DB time; actual profile/goal/photo-worker/registration use cases activate both students, then actual CAS goal revisions opt into shared learning and actual help saves declare SQL. Existing Person scenario preserves its original unshared/no-help setup. No fabricated lifecycle rows/capabilities or provider calls.

Strict mypy and Ruff pass for people_fixture.py; Python fixture compilation and TypeScript helper lint/format pass. A fresh API-only HEAD33/actual53 probe verified live student capability, real canonical peer/context for find_help, offer_help, study_together, and authorized no-store JPEG in each mode. No frontend browser or screenshot acceptance is claimed from this fixture probe. Own fixture exited normally; Noether hold released and actual helper READY sent to Aquinas. Its next scoped unit browser lease is active; no lead browser/PG runs concurrently.

The first new fixture lint run exposed the pre-existing six-argument setup helper. The immutable fixture actor now owns its requested display name, reducing setup to five arguments without ignored rules or changing Person outcomes. No backend source/config was edited. Lead proceeds FE03.5; Discovery source/tests remain exclusively Aquinas-owned.

## Scoped PostgreSQL48 accepted; Discovery delegated

Normal real FastAPI/PostgreSQL48 comparison passed48/48, runtime CLI EXIT0,2.1minutes on fresh HEAD33 against actual51/58 (31ab54...). Auth18, policy6, profile3, goal3, helper3, photo6 and Person9 all used normal screenshot comparisons with no PNG updates. Fixture/TLS servers shut down and own schema cleaned; Noether hold released immediately. This scoped acceptance does not resolve the separate aggregate native observer error or complete FE03.

Parent accepted that distinction and assigned Aquinas Discovery exclusively under screens/discovery/** plus discovery-progress.md. Concrete frontend/DISCOVERY-HANDOFF.md was sent directly to worker/parent and implementation authorized immediately. Lead added real lazy /discover after importable Discovery export readiness, reusing the existing QueryClient. URL and actual read/pass/Undo contracts, design D01/D04/D05, shared helpers, no fake Requests CTA, fixture ownership and serialized browser lease are fixed in the handoff. Lead retains FE03.5, shared files/fixtures/theme/routes. Worker unit lease is active; lead runs no browser/PG concurrently.

Current generated baseline advanced to actual53/60 (962f50...), with every previous51 operation/component unchanged. Export/hash verified, strict generation/drift and application typing pass; no generator widening. Shared types/routes frozen before worker unit START. New Discovery driver/helper passed a fresh actual53/HEAD33 API-only fixture probe: actual activation, relevant peer/context and private JPEG in all three modes. This validates the seed, not the Discovery UI. The worker may now import prepareDiscoveryFixture; scoped UI/fullstack coverage remains its task. Further full frontend acceptance remains blocked by the recorded native teardown diagnostic.

## Actual50 messaging contracts regenerated without screen speculation

Verified deterministic enabled export50 paths/56 operations SHA2566b1dcfc9d7a87a7590cda990ad1b6982e26cdd835b4707fb3c5959816ee64c68; all previous45 paths/components structurally unchanged. Generated readonly DTOs and snapshot using the unchanged strict renderer. Drift, application/spec/e2e TypeScript and all6 contract/immutability tooling tests pass. New text messaging declarations are actual mounted APIs; no Chat/Requests UI, unread state, conversation list, image send or acceptance action was invented. Normal real PostgreSQL48 comparison awaits a fresh coherent backend runtime checkpoint; no fixture currently active.

## Supported lifecycle question closed; native target remains unknown

No more broad/ring repeats were started after the single diagnostic282 run. The compact3 Goal diagnostic did not reproduce an error; the original fixture was restored to7ab8... . Full pre-pagehide host rings were recovered into /tmp/peerly-native-ring-events/timeline-summary.json despite Vite truncating the late native-error payload. These identify active observers and the temporal gap, not the skipped post-pagehide target.

Installed Taiga DestroyRef/EventManager cleanup is present and ordered. Added a meaningful real Chromium root regression: actual helper editor observers disconnect on supported Router navigation to Help, root font watcher persists, then root fixture destruction disconnects its foreign-target observer before removing the iframe. All8 root tests pass after awaiting actual input rendering; focused ESLint/spec TypeScript pass. Normal supported Angular cleanup did not reproduce the browser-close failure. No source/pagehide/rAF/realm workaround, error filter or extra production cleanup was added.

Exact raw diagnostic categories, lifecycle/source references, limitations and task-local evidence paths are consolidated in frontend/RUNTIME-DIAGNOSTICS.md. The original aggregate remains EXIT1, actual target unknown. Following parent direction, continue independent actual50 contract regeneration and fresh PostgreSQL acceptance, then readiness/registration screens; do not loop through source hypotheses or claim whole-gate acceptance.

## Bounded native-observer diagnosis in progress

Safe exact original diagnostic excerpts are separate files under /tmp/peerly-aggregate-runtime-70605: native.txt, vite-unhandled.txt, angular-console.txt, plus metadata-only context.json and a README clarifying that these are excerpts from execution70605, not a complete stored runner log. No network payload/private trace copied. Original report metadata was extracted before later diagnostic runs replaced the HTML report.

Aquinas performed the parent-assigned read-only installed Playwright/Vite/Angular/Chromium-source analysis, no edits or browsers. Source evidence explains screenshot first-poll and native message-only event wrappers; Chromium main is mechanism reference, not exact installed browser revision proof.

One diagnostic pilot of the three desktop helper-recovery variants passed without native errors (not a fix). Instrumentation identified font-watcher's foreign BODY observer and Taiga ResizePlugin auxiliary SPAN observers; font callback wrote root --t-font-offset from absent to0, textfield onResize writes ancestor --t-side. Native entries changed SPAN24→0 then a replacement SPAN24 after explicit reload. No native-error event occurred, so neither observer is blamed. Production fixture was restored and SHA2567ab8... verified after the pilot.

A single finite instrumented boundary282 run now records a bounded primitive-only callback/size-write ring, native ErrorEvent structure and screenshot/drain/page-close/context order. No application changes, arbitrary rAF patch, error filtering or automatic retries. Temporary probe is task-local and will be removed/restored after the run. The aggregate remains failed until the actual underlying runtime issue is resolved and ordinary gates pass.

## Final aggregate runtime failure — priority root-cause task

One complete npmcheck attempt on actual45/c4fd HEAD31: drift/static/type gates,46 tooling,576 units (95.18% branches), production499.97kB without warnings and3 no-JS scenarios passed. All282 boundary behavior/screenshot assertions passed in4.9minutes, but the unchanged CLI lifetime gate returned1 on raw browser diagnostics. PostgreSQL phase never started. Backend hold released immediately; no automatic full rerun.

Exact report metadata maps owned context50c9d5fe313c4ca7f1d4-7318903ce7434091a835 to chromium-desktop help.visual.spec.ts:470, helper subject_unavailable preserves the draft and requires explicit recovery. It is not the neighboring Person block scenario. Native ResizeObserver message, Vite Unhandled error and Angular console error remain distinct diagnostic records. Installed Vite client374 constructs an Error from the native event message when event.error is absent; installed Angular global errorListener2770 creates the no-error ErrorEvent wrapper with cause:e. This explains the two wrapper stacks but does not establish the native event's layout/lifecycle cause or excuse the failure. Prior ordered cleanup and282 passing assertions do not establish aggregate acceptance.

Current priority: preserve exact safe raw records and correlate error lifecycle/observer ownership without suppressing listeners, weakening CLI checks, blind reruns or broad scheduling patches. Historical actual25 remains the last accepted whole gate.

## Narrow profile PostgreSQL baseline correction reviewed

After the failed ordinary matrix, only the three profile save/reload scenarios were rerun in candidate mode against unchanged actual45/c4fd HEAD31. All3 passed with runtime CLI EXIT0 in20.0s; owned SQL/TLS fixture shut down normally. All9 resulting PNGs reviewed across mobile Chromium/WebKit and desktop: the externally labeled name field, Add photo action, durable saved value and normal saved feedback match the implemented UI. No theme/font/tolerance/mask change. Remaining whole acceptance requires the ordinary aggregate, not another candidate run.

Current lifecycle source SHA256 testing/visual.ts=7ab8c7a95fd9a9926fbe7362f3cd2a6c5b88202c82cce23cd84b7339446e7b8e; helper=cf670b54d91fb0ab23059d304d5e9394759e57f277173a8ce87ca5bb5c4664ff. CLI gate remains a075aa3d86822c6ec0e85a0204e1e2da2326b69b15107ad950995d3f05953558. This records resource lifecycle correctness; the earlier native observer diagnostic remains unresolved causal evidence, not filtered or declared fixed.

## Ordinary real PostgreSQL matrix — not accepted

Current actual45/c4fd HEAD31 normal comparison finished45 passed/3 failed in2.1minutes, CLI EXIT1. All three failures are the profile empty checkpoint's stale baseline (old floating name label and no Add photo action); expected/actual/diff reviewed and before-images preserved. The other45 scenarios include all real photo6 and Person9, but this failed aggregate is not acceptance of the full matrix. A desktop native ResizeObserver diagnostic was retained for the failed profile snapshot's owned context; the CLI correctly failed. This recurrence confirms that all-status cleanup is not a proven observer fix. Fixture shut down fully and the active backend hold ended. Next: narrowly refresh/review nine profile PNGs, then aggregate ordinary comparison, keeping runtime checks strict.

## Fresh real-photo candidate review

Fresh isolated PostgreSQL fixture upgraded actual HEAD31 against actual45/c4fd. Both real photo scenarios across three projects passed6/6 with runtime CLI EXIT0 in40.8s: native crop/worker/private READY/reload and committed creation with lost202/reload/explicit same-file resume, no duplicate intent or automatic transfer. Reviewed all24 candidate PNGs in four task-local contact sheets; changes retain the approved external name label/photo actions. This update run is not ordinary comparison acceptance. Fixture shut down and backend hold was released promptly.

The cleanup finally now also encloses runtime-listener/bridge initialization, so setup failure receives the same owned-page cleanup as scenario/render failure. Focused ESLint/e2e TypeScript and all four resource regressions pass. No diagnostics were filtered; no observer fix is claimed. Next: ordinary48 real PostgreSQL cases and aggregate.

## Current clean-install preflight and owned-page lifecycle

Current actual45/c4fd source passed the full nonbrowser preflight after the second clean npmci: dependency patch/hash verification, contract drift, formatting, ESLint, Stylelint, Knip, all four TypeScript targets,46 tooling regressions, full unit coverage and production build. Coverage statements96.22/branches95.18/functions98.64/lines98.64%; initial bundle499.97kB, unchanged500kB warning threshold, zero build warnings. Fresh browser graph excludes deepmerge-ts/minimatch and their reviewed tooling consumers. Remaining26 moderate audit reports are tracked tooling debt; zero high/critical is not zero vulnerabilities.

Owned-page cleanup runs in finally for all scenario statuses before context disposal. Cleanup errors still fail an otherwise passing scenario; when an assertion already failed, cleanup/attachment failure cannot replace it. Original runtime diagnostics and the CLI lifetime gate remain active. Four dedicated resource regressions passed again. This is resource lifecycle correctness, not evidence of a ResizeObserver source fix. Ordinary93 affected profile/photo/goal cases passed with runtime EXIT0 after reviewed baselines. Fresh real PostgreSQL comparison and the aggregate gate remain pending; historical actual25 remains the latest accepted whole frontend gate.

## Scoped security triage after clean installation

Clean npmci succeeded with fail-on-error font-watcher patch plus all pre/post hashes. Audit exposed27 reports (25 moderate/2 high), rooted in deepmerge-ts7.1.6 cyclic-graph exhaustion and minimatch10.2.6 glob amplification; ancestor packages account for propagated reports. Reviewed upstream advisories/release notes and actual consumer imports. No npm auditfix/force or framework downgrade used.

Applied only eslint-plugin-functional@10.0.1→deepmerge-ts8.0.0 exact transitive override. Isolated comparison of actual ESLint rule-option records matches7.1.6; upstream Map merge change is not used in those calls. A second full clean npmci reproduced the patch/hashes, actual consumer resolution is8.0.0, audit now reports26 moderate/zero high. Remaining root is minimatch; isolated11.0.1 matches repository glob corpus but removes makeRe/AST, and installed import-x requires makeRe. Do not force an incompatible major or hide the remaining advisory. Fresh browser graph/full lint/tooling validation subsequently passed as recorded above; no browser runtime dependency uses these tool packages. README records links and removal criterion. No frontend/PG runner active during install; backend window not held.

Ordinary93 profile/photo/goal comparison and runtime gate passed before this dependency-only correction. That scoped UI acceptance remains distinct from the next clean whole gate and real PG acceptance.

## Corrected actual45 DTOs generated without changing the renderer

Received corrected closed-projection45/50 export SHA256c4fd4764d7f175863f48a8a08ee269446f3fea7cd969d5e70b2994bc6efc82f2. Verified old37 paths/components unchanged; the original strict renderer now accepts it without any generator widening. Regenerated actual DTO/snapshot, drift and application/spec/e2e TypeScript checks passed. Backend reports1477 full tests96.51% for pre-bounded-fix snapshot, followed by focused closed-response/schema/mapping/PG checks; do not describe those as a new full backend run. Current HEAD31/factory/settings unchanged. No Requests UI introduced.

Final neighboring label and for/id restore exact Display name independently of the clear button.60 profile/photo candidate scenarios passed with runtime EXIT0. Reviewed165 changed regions against preserved before-images; all top400px are identical, with changes confined to field layout, explicit photo actions and existing Back to setup. Contact panels are task-local review aids only; full test screenshots and zero tolerances remain unchanged. Enlarged/crop images inspected separately. Ordinary93 profile/photo/goal cases now running. Whole frontend acceptance still pending, and no ResizeObserver fix is claimed.

## Exact accessible label retained in final field layout

A subsequent60-case candidate run caught three new refresh scenarios timing out on the exact Display name accessible selector: wrapping the whole textfield in its label allowed nested clear-button content into the name. That57/60 run is not accepted. Kept the exact assertion and replaced nesting with a neighboring public tuiLabel connected through native for/id, grouped only by a small layout grid. No aria workaround/internal selector or font override.

Nine targeted candidate cases now pass all projects: exact accessible name, preserved draft after503, Add/Change captions at320px/200%, focus/no-write/overflow/native text bounds. Final candidate field images still need comparison/review; the full affected profile/photo baseline run is in progress. Current product unit evidence remains81 focused, with previous aggregate574 coverage historical until the next full run. Generator remains37 pending corrected closed45 export.

## Enlarged-profile accessibility correction verified

The regenerated legacy54-case baseline run passed its runtime gate, but image review caught a clipped long photo CTA at320px/200%; it was not accepted. Replaced it with server-derived Add photo/Change photo and the documented wrapping TuiLabel/textfield arrangement, which makes the complete name label visible. No custom control CSS/font reduction/theme change. Added native text-range bounds for both actual photo states and retained invalid-name no-write/focus/overflow checks.

Both states across all three projects passed six ordinary comparisons/runtime EXIT0; enlarged PNGs inspected (Add and Change readable, complete external label).81 focused profile/photo units passed after the template change. A new profile/photo candidate-baseline run is updating affected field-layout images; reviewed-before images are preserved task-locally for exact visual comparison. Final whole coverage, real PG and aggregate still pending. Strict generator remains unchanged while waiting for corrected closed actual45 metadata.

## Upcoming actual45 contract intentionally held, no generator widening

Backend handed off HEAD31 actual45/50 Requests schema with raw SHA256ff52323e5f94c9ba2792d14c448a8c8ae0eff3df1bc0ca361f1c423bfd80d5fe; hash and all previous37 paths/components verified unchanged. Strict DTO renderer rejects new fixed-property response objects whose additionalProperties is omitted (for example AcademicContextResponse/RequestSummaryResponse). A premature direct acknowledgement that rendering passed was corrected immediately; no generated/tooling mutation was made.

Noether/Nash confirmed these are fixed projections with no extension maps; frozen=True accidentally omitted extra='forbid'. They will deliberately close the response DTOs and test/export a new hash after the current backend gate. Do NOT widen the frontend generator to accommodate accidental openness. Snapshot/generated stay37 until the corrected tested45 export arrives. No speculative Requests/Chat UI, no PG fixture started.

Visual review of candidate enlarged profile images found the long Add or change photo CTA clipped at320px/200%. Those images are not accepted. Using truthful Add photo/Change photo from actual current-photo state and documented external TuiLabel layout for the name input; strict native text-bounds assertion added. Focused units/browser verification and affected baseline review continue before aggregate.

## Aggregate result and bounded lifecycle/product corrections

Latest aggregate (execution session37304) passed enabled37 drift, formatting, ESLint/stylelint, Knip, all type checks,42 tooling tests,574 units (95.18% branches), production499.97kB and3 no-JS scenarios. Boundary suite ended **222 passed/54 failed, CLI1**, with native ResizeObserver warnings retained. PG phase never started; backend window was released on the first boundary failure. Reviewed expected/actual samples confirm stale Back to setup footer and explicit Choose new photo labels, not a font change. No automatic blanket baseline acceptance.

Parent authorized deterministic owned-page cleanup for all statuses. The fixture now uses finally across the scenario/render phase and closes the owned page before context disposal even after failure. Four resource regressions cover pass/fail close ordering, already-closed pages and preserving the primary assertion when cleanup also fails; a cleanup failure on an otherwise successful test still throws. Best-effort safe attachment cannot replace the primary error; native/console/forwarded diagnostics and CLI gate remain unchanged. This is lifecycle correctness, **not a proven ResizeObserver fix**. The tiny helper is explicit native ESM TypeScript (.mts), with strict lint/Knip/type-check coverage expanded to that extension; no rule disabled.

Scoped product fixes: cached profile503 refresh now retains the actual child editor and dirty name, offers explicit refresh retry, while403 still hides the private editor. Photo finalize pending/unknown no longer simultaneously claims it is waiting for transfer or asks reselection despite selected local bytes.81 targeted profile/photo units pass, including503/403 and immutable-finalization regressions. Three-browser new refresh-failure/recovery baseline passed after correcting a test-native canvas context; six new images plus six finalize phase images reviewed. Ordinary comparison of these six cases passed6/6 with runtime gate EXIT0; all12 new/corrected images reviewed. This is scoped acceptance, not a ResizeObserver fix. The54 legacy navigation/terminal-label baseline cases are now being regenerated deliberately from preserved before-images; review and ordinary comparison remain due. Whole coverage/PG/fullgate still pending.

## Aggregate pre-browser failures corrected without weakening gates

First aggregate attempt stopped before units/browser/PG on formatting in shared api-jpeg.spec.ts; corrected formatting and whole frontend format check passed. The next Halley-owned attempt passed contracts/format/ESLint/stylelint, then stopped on Knip reporting the two actually consumed font packages as unused. Both backend windows were explicitly released on early END; no PG fixture started.

Installed Knip6 Less compiler collects @import references, not font src:url references. Added only exact @fontsource/inter and @fontsource/m-plus-rounded-1c asset exceptions alongside existing native/icon exceptions; config hints stay fatal. New tooling guard requires every font exception to have a real local stylesheet URL, an exactly pinned declared package and readable WOFF2 magic bytes, preventing an unused package from slipping through this exception. No dependency source patch, wildcard exclusion, budget waiver or UI change. Focused guard and Knip/static results recorded at this checkpoint; next aggregate window still requires fresh coordination.

## One aggregate frontend check reserved, awaiting backend READY

Aquinas final source checkpoint reports574 units GREEN: global96.22 statements/95.18 branches/98.63 functions/98.64 lines; Person98.01/95.40/98.70/99.12. Person source SHA256300d501ebb0497851746959fffdc57a0e1b44e84bbd2838ab96b185cfdc36976. No unit/browser/PG process active at handoff.

Reserved exclusive38385 browser lease for one mandatory npmruncheck after explicit Noether READY. Requested a bounded coherent actual37/HEAD29 window for public schema, active ORM/DDL/bootstrap/visibility/block; unmounted independent preparation can continue. All frontend production/fixture/generated/config files held through the gate; scripts run sequentially with existing worker configuration and no concurrent unit/browser runs. No baseline updates, runtime exemptions or skips. Release backend window on early failure or actual PG/full END. Known native ResizeObserver remains unresolved; a clean isolated run would be acceptance evidence, not proof of its cause or repair.

## Actual37 DTO regeneration complete

After Aquinas explicitly released the focused-browser lease (photo404 ordinary3/runtime GREEN), regenerated `contracts/openapi.json` and deeply readonly `src/app/api.generated.ts` from the actual deterministic exporter. Snapshot equals independently exported raw37 schema; drift check and application/spec/e2e TypeScript checks passed. All41 tooling tests, generated-file ESLint and formatting passed (`/tmp/peerly-actual37-frontend-tooling.log`). Existing35 paths/components remain unchanged; only generated Discovery contract added. No Discovery consumer/UI, mock Requests action or new production service introduced.

Shared source window is limited to generated files and contract documentation. Backend1317 combined acceptance applies; overall frontend gate and native ResizeObserver resolution remain pending. No browser/PG fixture started by Halley.

## Backend actual37 combined acceptance received

Noether reports full backend makecheck GREEN1317 tests (399 integration/918 unit),96.43% branch, HEAD29, actual37/41 exporter hash3fbc3939531ef818e8a5e71da4900156c12688052734b2750b99f738c0e3dfff unchanged. This supersedes historical backend1068, not the frontend whole-gate status. Backend source window released; no live provider/publication/deployment acceptance implied.

Read-only frontend DTO renderer accepts actual37; six generator/tooling regressions pass. Shared generated files still await Aquinas explicit focused-browser END; requested fresh lease status after the backend run to avoid a stale hold. No competing browser/PG or backend edits. Full frontend acceptance remains pending, including the recorded native runtime diagnostic.

## Actual37 Discovery handoff verified read-only

Verified raw exporter artifact `/tmp/peerly-actual37-discovery-openapi.json` SHA2563fbc3939531ef818e8a5e71da4900156c12688052734b2750b99f738c0e3dfff,37 unique paths/41 operations. Compared against the current frontend35 snapshot: every existing path and component schema is structurally identical. Added only actual GET/discovery and PUT/discovery/passes/{person_id}. Read-only DTO rendering accepts the schema without tooling changes.

Generated files remain35 until Aquinas releases the current shared-source/browser boundary; then regenerate using the actual deterministic backend exporter and verify drift. Combined backend acceptance/hold coordination is pending. No Discovery UI or invented Requests CTA introduced; next screen work waits for current Person/photo checkpoint. No fresh Halley PG fixture or competing browser.

## Real Person PG ordinary gate remains failed on native runtime diagnostic

Aquinas reports real HEAD29 PG update9/9 GREEN including activated projection/authorized JPEG, block→404→owned report, reload/unblock without a fresh context, and stored-report response loss with immutable receipt replay. Subsequent ordinary9 behavior and PNG assertions all passed, **but the browser CLI exited1** on native ResizeObserver at23:16:00 in an owned Chromium-mobile context. This is not normal-run acceptance; no error suppression or repeated bulk probe campaign is authorized from this result. Requested exact log/title/event order for a bounded causal follow-up.

Owned fixture584290 shut down gracefully; Aquinas sent PGEND directly to Noether, releasing the active-runtime window. No competing Halley browser/PG. A genuine photo404 retry fix now rereads canonical person/photo version while503 retries the same JPEG; focused units/boundary coverage still being completed by Aquinas. Reported transient person branch94.96 is below unchanged95 and must recover before acceptance. Whole frontend remains pending; historical actual25 is still latest accepted full gate.

## Person corrected-dialog boundary and actual PG restart

Aquinas reports54/54 ordinary boundary/runtime GREEN after the supported mobile fullscreen correction,126 PNGs reviewed including readable320px/200% title and visible actions/focus restoration. Latest reported full570 units remain95%+, production499.97kB zero warnings. No deferred report-child artifacts remain; native FormGroup/TuiRadio retained.

Noether completed the lifecycle window with33 visibility/block/Requests PG plus5 real parent-hook PG and static checks green, unchanged HEAD29/API35 hash/factories. Aquinas then announced actual fresh-fixture PGSTART29 for nine update plus nine ordinary Person cases, sequential on38385. Shared frontend sources/fixture/config held; Halley has no competing browser/PG. PG results/cleanup and aggregate acceptance are still pending. Previous failed pretest import attempt remains accurately recorded below.

## Person runtime/PG checkpoint limitations

Aquinas reports ordinary54 boundary scenarios/runtime clean and569 units95.15% global branch after the observer conversion and safe2xx parsing fix. Subsequent review of the added open-report320px/200% image found the title unreadably narrow despite geometry assertions passing. A bounded fix uses public Taiga breakpoint/fullscreen dialog mechanisms; actual images and readability must pass before accepting this case.

First real Person PG attempt ended gracefully before tests: Node visual imported a production guard that pulled Angular BrowserXhr JIT into the runner. Aquinas removed the runtime production import and uses Node-only observed-response assertions; actual UI runtime guards remain in production. No PG passing result claimed. The PG window was explicitly released; Noether is taking a visibility/block lifecycle runtime window at unchanged HEAD29/API35, and no new fixture may start before his next READY. Aquinas owns the current serialized boundary lease only; Halley has no running browser/PG fixture. Shared frontend production files held during that lease.

## Photo command visual review during Person browser lease

Reviewed all18 candidate Start/finalize pending/unknown/recovered-queued screenshots across Chromium mobile/WebKit mobile/desktop. No clipped labels/overlap found. Current ordinary comparison still pending, not accepted from baseline generation. Found an actionable semantic follow-up: generic uploading/reselection text remains alongside finalize-pending/unknown processing text; tighten phase explanation after the current shared-source freeze. Photo scenario document now records actual scoped evidence and remaining PG/recovery/fullgate work. No production source changed during Aquinas lease.

## Person bundle checkpoint recovered

Observer conversion removed the TanStack namespace retention. Finite route-composition comparison then isolated the remaining growth to necessary Angular native radio accessors (initial forms attribution+4583bytes), not Angular Core or the route adapter. No radio functionality was removed and no deferred-component extraction/budget waiver was adopted.

Removed only legacy WOFF fallback declarations from the same seven pinned local font faces; explicit WOFF2 faces preserve families, weights and swap behavior. SHA256 verification confirms all seven emitted WOFF2 binaries match the installed packages exactly; no WOFF artifacts remain. Final production stats build/prerender1 route **GREEN,499.99kB initial, zero warnings**, unchanged500kB budget (`/tmp/peerly-person-font-checkpoint.log`). Stylelint/Prettier passed. Headroom is very small and future features must recheck it; this is not full frontend acceptance.

Shared source checkpoint released to Aquinas for serialized boundary malformed201/replay verification and fresh HEAD29 PG scenarios. No Halley browser/PG fixture running; shared production files held during that lease. Prior proposed route/deferred-form hypotheses are diagnostic history, not claimed fixes.

## Successful-status JSON parse uncertainty regression

Shared transport now normalizes Angular HttpErrorResponse with2xx status to safe status0/invalid_response, discarding the decoding envelope. A committed command with malformed JSON therefore remains an unknown outcome and retains immutable retry semantics in consumers. GET200/POST201/PUT200 regression cases pass within15 JSON transport tests; targeted ESLint and spec TypeScript passed. Combined JSON/JPEG/session91tests passed. Aquinas is adding the real Person boundary malformed201/replay case; no browser acceptance claimed from transport units.

Person public QueryObserver conversion removed about179kB of initial code; subsequent stats build still warns at500.49kB,491bytes over unchanged500kB. Finite no-Person/with-Person stats comparison disproved the route-interop hypothesis: Angular Core chunk is identical170989bytes; initial Angular Forms attribution grows4583bytes with a second lazy ReactiveFormsModule consumer. The route was restored in finally after the diagnostic, with all outputs task-local. Proposed a genuine deferred optional report-form component boundary to Aquinas; no further speculative route optimization or code golfing. No budget change or dependency patch. Browser and PG suites are currently stopped for this source checkpoint.

## Current shared integration / fixture coordination

Shared session/uncertain helpers now live at the screens parent. Added abort-aware same-origin JPEG transport with MIME validation and bounded safe problem decoding; JPEG/JSON/session targeted checks passed88 tests. Person lazy route shares the existing QueryClient; Aquinas exclusively owns that screen.

Controlled real People seed/helper uses DB time for synthetic verified identity/session facts and actual application use cases for profile, goal, photo processing and registration activation. API-only fresh-fixture probe passed seed201, activated /me200, People200 and authorized JPEG200. Owned servers shut down gracefully and own schema/TLS were cleaned; shared PG untouched. This is not browser UI acceptance.

Noether confirms coherent HEAD29, unchanged public35: earlier26/28 window requests were stale and no active ORM/DDL change is pending. Halley has no running PG fixture. Aquinas completed51 ordinary boundary scenarios/runtime GREEN (reported114PNG), then reserved the lease for Person observer conversion and subsequent fresh HEAD29 PG checks with START/END notifications. No PG fixture is currently running. No concurrent browser suites.

Current quality blocker: production build initial679.31kB exceeds unchanged500kB warning budget (prior496.87kB). Exit0 with this warning is not acceptance. Stats identify newly reached TanStack create-base-query/pending-tasks compatibility; installed source imports the Angular namespace and accesses it with Reflect.get. Requested Aquinas convert Person to public QueryObserver/MutationObserver consistent with existing consumers after his browser checkpoint. No budget waiver/dependency patch. Latest global560-unit/95.14% branch evidence is Aquinas-reported, not a complete frontend gate. Photo comparison/recovery and global runtime acceptance remain pending; historical actual25 remains the latest accepted whole gate.

## Actual35 schema handoff —18:33UTC

Regenerated from the real deterministic exporter; locally confirmed35 unique paths/39 operations and raw SHA256b28a962720b86690c6345b0be67f2c282dcb4c7a247c3ead64bd1ad9b5375abf. Prior “actual31” was a handoff alias for30 unique paths (GET was added beside existing POST), not a schema rollback. Historical log aliases below remain unchanged. Existing photo/auth shapes retained; People/safety generated only, no speculative consumers. Backend combined head24 acceptance currently running; no new People PG/UI acceptance claimed.

Real photo expanded6-case baseline GREEN (`/tmp/peerly-fe03-photo-pg-resume-update.log`): actual server Start202 transaction committed then browser response deliberately aborted; reload loses all local file/intent RAM, own resume recovers the upload, explicit same-file selection verifies final bytes and transfers under the original ID, creation count remains1. Includes real HTTPS storage and durable processing/private display across all engines. No API response replaced with synthetic success.24PGPNG need current review/ordinary comparison. Previous3 ordinary evidence remains historical.

New terminal-during-crop race now preserves the selected upload context; completion cannot silently create a replacement. “Choose new photo” is an explicit new-draft action. Latest owner photo is derived from the higher real revision of parent/resume projections. Unknown creation replay resolves the immutable metadata even if local bytes changed; transfer still requires the recovered fingerprint. Fresh tests/full coverage pending for those refinements; earlier441-unit95.04 gate is a previous source boundary. Browser command6 baseline cases passed; expanded recovery comparison/image review continues. No hold needed/requested during independent feature work.

## Photo unit gate recovered —18:12UTC

Full **441 units GREEN**, coverage96.34 statements/95.04 branches/99.28 functions/98.68 lines (`/tmp/peerly-fe03-photo-owned-phase-units.log`), unchanged95 thresholds. New evidence covers native final-byte drift, stale decoder/hash/encoder completions, actor-replaced Start/finalize/cancel200/401/503, exact uncertain keys, abort/response races, failed status/access recovery and parent editor preservation. Native preparation and live transfer own only ephemeral state; Start/finalize loading derives directly from TanStack mutations. File selection prepares explicitly rather than adding a redundant FormControl subscription. Selected final bytes remain form-owned; no query mirror/persistence. Uncertain finalize intent is preserved even after an explicit same-file retransfer.

Latest completed browser matrix **30/30 ordinary EXIT0** and48PNG reviewed (`/tmp/peerly-fe03-photo-matrix-comparison.log`), before latest error/phase refinements.3 real PG ordinary transport scenarios passed as below, before intentional list spacing;12PGPNG reviewed. Current source still requires expanded recovery/multi-intent screenshots, refreshed PG layout baselines and complete gate. Do not call FE03/photo done from unit success. Remaining global ResizeObserver issue remains open; no scheduling patch/console filter or more bulk probes. Accepted actual31 unchanged; upcoming People36 is not exposed/consumed. No hold requested while this feature matrix continues.

## Photo transport milestone —17:52UTC, still in progress

Actual FastAPI/PostgreSQL photo roundtrip passed **3/3 baseline and3/3 ordinary comparison** (`/tmp/peerly-fe03-photo-pg-complete-{update,comparison}.log`), across all required engines. Real OAuth state/session, durable email verification, Start/access/direct native multipart/finalize, durable SQL photo worker, bounded real image codec, private display and reload projection are exercised. External storage is a separate fixture-only loopback TLS server8769 using ephemeral cert; Google/email/storage boundaries remain controlled, no live providers. Playwright WebKit does not expose the binary multipart through intercepted postDataBuffer, so the fixture uses **actual browser HTTPS transfer**, not replacement bytes or a skipped WebKit path. Storage rejects application cookie/CSRF headers. One worker-step lock keeps the fixture codec invocation serial. Both owned servers shut down gracefully; shared PG preserved.12 new PNGs reviewed, then a small list-spacing defect was corrected; those baselines need the intentional layout update before next normal acceptance.

Real integration caught a product bug: profile background refresh destroyed the active photo editor (conditional isFetching). Cached-data refresh now retains the real child/form and displays inline refresh status. Dedicated unit verifies child identity plus dirty name survive. READY status also refreshes the owner resume projection. No server state mirrored. Latest focused units97 GREEN before two additional cancellation/encoding regressions; latest complete unit run407 assertions GREEN but **coverage command FAILED92.42 statements/90.68 branches** (functions97.85/lines95.52). Continue meaningful async/uncertainty/cleanup tests;95 thresholds unchanged. Latest full accepted frontend check remains historical actual25; global intermittent RO still unresolved. Current photo feature/full acceptance is not complete.

Public Taiga fullscreen crop, viewport-owned open-editor top/action checkpoints and closed whole-form screenshot9 ordinary scenarios EXIT0 are targeted evidence; latest ordinal recent-upload labels/list spacing and new terminal/loading/session cases require updated images/normal comparison. No fullgate claim. Current static lint/styles/types/Knip passed before latest test additions; current head23 supported by fresh upgradehead fixture, accepted31 hash unchanged. Next: complete current boundary matrix, coverage and photo resume multi-tab/race integration, then server readiness/registration/freshness. Parent owns Git; no secrets/deploy operations.

## Active photo workflow — actual31, implementation in progress

Actual31 generated from accepted deterministic backend export SHA256649d28f450c8333d998df00cb7d6fe5179221723810578d29dd5ec515a5de4cf; backend full988/head22 accepted. Current photo code is **WIP, not acceptance**: native file choice/local crop plus Start/access/direct transfer/finalize/cancel/status consumers; owner resume projection now wired with explicit record selection and final-byte SHA/size/type comparison before an existing intent can be reused. No file/ticket persistence, signed ticket in Query/Mutation state, automatic transfer on reload, or live S3. New unit/visual/full-stack scenarios remain outstanding. Prior318-unit evidence does not cover this new source. Latest private-route build before resume wiring496.74kB with no warning; current source must be rechecked. No coverage/bundle thresholds changed.

Fresh photo evidence:82 focused native units GREEN before the next pan regression (exact resume bytes include actual access/transfer/finalize; no duplicate Start). First9 browser scenarios passed baseline generation then ordinary comparison under the strengthened runtime gate (`/tmp/peerly-fe03-photo-viewport-visual-comparison.log`);24PNG reviewed via three project contact sheets. Fullscreen crop remains scrollable; open-editor top and action-area viewport screenshots plus closed whole-form checkpoint retain behavior/content. Default dialog320/200 collapse and Chromium full-page capture instability were **not** accepted as baselines; official fullscreen appearance fixes usable width, viewport capture avoids resizing a viewport-owned scrollable editor. A previous full-page run reproduced ResizeObserver and remains failed; no causal claim that capture fixes the unrelated global issue.

Current full unit command executed392 assertions successfully but FAILED unchanged95% coverage thresholds:88.98 statements/87.24 branches/94.58 functions/91.96 lines (`/tmp/peerly-fe03-photo-current-units.log`). This diagnostic is not acceptance; new photo lifecycle branches require further meaningful tests. Latest full accepted gate remains historical actual25. New pointer behavior uses public TuiPan on the owned canvas; gesture/native camera acceptance remains in progress. No parent/backend hold; coherent23 announced for future fresh fixtures, actual31 unchanged.

G02 reviewed96 browser PNGs and48 changed PG PNGs; ordinary42 G02 scenarios passed strengthened runtime gate. Overall33 PG scenario assertions passed but CLI failed correlated native ResizeObserver, so latest full acceptance remains historical actual25. No claim that font readiness/border/lifecycle fixes eliminate that separate intermittent runtime issue. No more bulk diagnostic probes without a new mechanistic hypothesis. Continue photo tests and real controlled-storage fixture, then server readiness/registration/freshness. No current owner/backend-contract blocker.

## Active G02 implementation —16:46UTC

G02 helper-subject editor implemented against actual GET/PUT /me/help-subjects: canonical search/cursor in public Taiga dialog; ordered FormArray drafts/optional notes, explicit version/idempotency, safe uncertainty/conflict recovery and actor cancellation. Back to setup returns from each actual editor and destroys local drafts; no fake route or activation. Image review caught clipped long Save caption at320/200% and overlapping selected marker; short Save/Retry captions retain descriptive accessible names, selected state uses public Taiga iconEnd. New text-fit assertion covers the former clipping defect, no hidden overflow/style override.

Fresh318 units GREEN,95.86/95.45/99.49/98.42%; static/format/build GREEN496.74kB below unchanged500kB.41tooling GREEN now includes late native ErrorEvent marker regression: our correlation console.warn could survive detach without ViteUnhandled/error, so CLI also fails that precise marker. Ordinary warnings still allowed; no ResizeObserver exemption. Existing42-assertion update with such raw warning is not runtime-clean even though the old parser returned0. Current ordinary G02 comparison **42/42 EXIT0 with strengthened runtime gate**, log `/tmp/peerly-fe03-help-browser-comparison.log`;96PNG reviewed (picker/closed forms/all projects/320/200/old200/401 actor boundary).

Accepted actual30 generated/drift checked, source SHA2563cf82b8e0b1af2bf44e15b4f85b938cbe7c5f491b95bc34ca6492c5bc8f7b365; backend parent full944 accepted. No AI UI. Separate bounded AI/core fixture pools preserve the actual production topology inside a unique Alembic schema; Ruff passes. Coherent head20 announced; no runtime consumers/public schema changes from20.

Owned WebKit original768MiB fixture suffered Docker-confirmed isolated OOM (event1794069056), causing24/33 PG pass and9 remote-browser failures. Only that fixture was recreated at authorised1536MiB/512MiB shm after checking4103241728B Docker VM budget; no DB reset/user browsers/production limits touched. Restored33/33 PG baseline run passed (`/tmp/peerly-fe03-help-pg-restored-update.log`), including real helper version1 note save/reload and empty version2 save/reload. Latest short caption final33 baseline EXIT0; ordinary33 assertions passed but **CLI EXIT1** on correlated desktop ResizeObserver at guest bootstrap (`/tmp/peerly-fe03-help-pg-comparison.log`). No OOM under1536MiB. Server461482 gracefully stopped and END sent promptly for backend22 DDL/runtime window. This is not final PG/runtime acceptance; no retry while source/DDL window is active. New PG PNGs still need current image review.

**Latest full combined frontend gate is still historical actual25**. Current G02 feature evidence above does not resolve intermittent ResizeObserver globally; earlier new-source combined gate failed and remains open. Existing profile/goal boundary PNGs need the intentional Back-to-setup update before the next full gate. Do not repeatedly probe the known runtime issue or change source without causal evidence.

Next: finish current33 PG/image boundary, then actual photo lifecycle and server readiness/explicit registration/visibility/freshness. No source/UI bindings from proposed AI contracts, no live providers/secrets/Git/deploy operations.

## Fresh FE-03 status —16:20UTC

Implemented actual profile name drafts and goal/catalogue editing: actor-scoped readonly queries, closed versioned PUT requests, explicit canonical/custom subjects, server cursor pagination, exact uncertain-intent replay, conflict recovery and private draft cleanup on identity replacement. No draft save pretends activation. Generated the accepted actual27 freshness schema (source SHA2568ac8a238c40e15754587d3e6bf655d9220693cb6ade4907c245255d5c23d3aec); its runtime readiness/freshness consumer remains next, not implemented by type generation alone.

Fresh complete unit command GREEN269, coverage statements95.95/branches95.46/functions99.35/lines98.07%; production build/prerender GREEN491.96kB initial under unchanged500kB warning budget. Logs `/tmp/peerly-fe03-goal-{units,build}.log`. Latest option-layout/empty-message refinement included; contracts/format/ESLint/Stylelint/Knip/all TypeScript checks also pass. Previous269 coverage figures below are superseded for this source boundary.

Goal boundary baseline creation33/33 passed,69PNGs produced. Ordinary comparison then32/33: mobile first-page dropdown selected the opposite automatic vertical placement; not accepted or hidden. Image review also exposed cramped alias flex columns and misleading Taiga fallback Nothing found during loading/error. Current refinement groups our own option contents into a readable grid and uses public emptyContent template while retaining explicit loading/error/empty messages. No library CSS/internal selectors, forced dropdown direction or tolerance change. All69 initial PNGs plus18 refined catalogue checkpoints reviewed. Latest ordinary comparison30/33 still differs in adaptive popup placement; awaiting local fonts before interaction added as bounded starting-metrics stabilisation, not a claimed production fix. Focused6 behavioral/screenshot assertions pass after that adjustment, but CLI correctly fails on another correlated desktop ResizeObserver diagnostic. No accepted current browser gate.

First actual FastAPI/PostgreSQL goal roundtrip3/3 GREEN against coherent head19: real catalogue alias lookup, canonical choice, version1 immutable save and reload across required browsers. Controlled provider boundary only; actual Google state/session, durable delivery and membership are exercised.12 initial candidate PNGs reviewed. Expanded real test to custom version2 save/reload; all30-scenario regression28/30, with WebKit page crash and screenshot loss. Owned WebKit container reports OOMKilled=true under its768MiB cap during simultaneous independent browser runs; Sequential isolated baseline run30/30 GREEN, then ordinary comparison30/30 GREEN (`/tmp/peerly-fe03-goal-pg-comparison.log`); no memory-limit change/restart/skips/timeouts/retries.18 goal PNGs and3 revised email-verified entry PNGs inspected, including canonical version1 and custom version2 reload. Log `/tmp/peerly-fe03-goal-pg-update.log`. Shared fixture helper now serves three real consumers; fixture seeds real canonical subjects/aliases. No DB reset, ad-hoc table patch or live provider call.

Current task: deterministic catalogue-overlay response lifecycle, then normal visual comparison. Settled fonts alone did not resolve placement (latest30/33); no causal claim. Native Taiga anchor placement chooses its initial direction from element.clientHeight in ngAfterViewInit; immediate responses could race that creation (current hypothesis, not proven cause). Existing failure/pagination cases now deliberately open the actual loader before releasing the first server response, covering the intermediate UI rather than pinning popup direction. Focused6 update/normal comparison pending. Keep all browser suites sequential against the bounded WebKit fixture. Remaining FE03: helper-subject editor; photo lifecycle; actual server readiness, explicit registration context/completion, visibility/freshness confirmation; extended auth/accessibility. Discovery/requests/chats/safety/operator/AI/native screens remain later contract-backed work.

**Latest accepted combined frontend gate remains actual25** (`/tmp/peerly-actual25-check.log`). Current FE03 full gate is not accepted: prior102 passing boundary assertions ended in preserved late ResizeObserver CLI failure. Native error cause remains unresolved, no suppression/new scheduling patch/more mass probes. Earlier detailed bounded22-minute investigation remains below. No owner input is needed for the ready tasks; parent alone handles Git.

Goal overlay finite boundary: public viewport capture6/6 baseline then6/6 ordinary comparison GREEN; strengthened geometry run6/6 GREEN (`/tmp/peerly-goal-viewport-{comparison,geometry}.log`). Bounding rectangles remain exactly unchanged before/after each capture, popup fully inside actual viewport and no horizontal document overflow. Escape closes it; new full-page closed-form checkpoints retain all content.30 affected popup/closed images reviewed. Playwright1.65 full-page capture uses captureBeyondViewport when the document exceeds the viewport; Taiga uses native viewport anchor fallback. Results support a capture-path interaction, not proof of every underlying engine mechanism. No app direction/style changes, crops/masks/tolerance increases or runtime filters. Readiness/response gating alone did not solve it and is not described as a fix. Current40tooling/lint/typecheck GREEN. Do not repeat33 without new change; proceed G02. Overall FE03/ResizeObserver gate remains open.

## Active FE-03 name-draft slice

Actual27 generated and inspected (GET `/me/onboarding`, PUT `/me/visibility`; no inferred fields). Backend subsequently reported accepted626tests96.94%; final registration/visibility UI remains unfinished, not blocked on a fictitious endpoint. Name draft editor now consumes real own-profile GET/PUT under signed-in verified entry. Version/other profile fields preserved; safe explicit conflict reload, original idempotent payload replay after uncertainty, no mutation retry and actor/destroy callback guards. One client PUT transport extension is used by this actual consumer.

Latest completed checks:202 browser-backed units, coverage96.75/96.76/99.02/97.49%; lint/typecheck/styles/Knip pass;18 new three-project boundary cases with36 reviewed PNGs, including320px keyboard and200% layout. Unit actor-swap regression caught defaulted QueryObserver `queryHash` being retained by options spreading; fresh options now ensure correct account keys. New real FastAPI/PostgreSQL name-save/reload case added.

Real integration attempt exposed concurrent backend WIP: fixture had correctly upgraded then-current0015, while event runtime/migration0016 landed after boot. Confirmed schema head0015 and absent product_events, not a fixture pinned-head bug. No table patches/reset/skips applied. That attempt failed6 of27 and is not acceptance; its server shut down gracefully. Parent supplied explicit READY coherent0016 window; fresh-head all27 real visual cases passed, including draft roundtrip. Full gate then passed static checks/40tooling/202units/build/3no-JS/102boundary assertions but FAILED its CLI runtime gate: late forwarded ResizeObserver diagnostic, raw log `/tmp/peerly-fe03-profile27-check.log` lines266/269. No error was ignored; full PG phase was not reached. END sent to parent to release backend hold. Context-correlation diagnosis is active; screenshots otherwise reviewed. Prior accepted25 full gate remains historical evidence below. Photo/goals/completion/visibility UI still outstanding. No live providers or Git operations.

## Independent identity-boundary regression after runtime investigation

A new red unit proved old institutional-email draft survived an actual account-ID change. Fixed by comparing the prior actor-scoped query key with the new server actor and resetting forms, editing presentation and private mutation cache on replacement (no mirrored account store). Send/verify callbacks and handled errors now carry actual intent actor IDs and respect component cancellation, so a late old-account reply cannot refresh or sign out the replacement actor. Tests cover old-send200/401/503.

Latest units206 GREEN, coverage96.87/96.66/99.03/97.58%; lint/typecheck pass. New6 browser identity-isolation cases passed baseline creation and ordinary comparison,9 PNGs reviewed. No backend real-fixture run during announced0018 WIP; no inferred freshness fields. Full-gate runtime blocker remains open; earlier202-unit/27-PG results above are prior-slice evidence, not a full pass for these latest changes.

## Bounded runtime investigation — not acceptance

Full gate failed14:08UTC on late ResizeObserver error. The strengthened CLI gate preserved raw output and failed after102 scenario assertions passed; no full-gate pass claimed. Safe owned-context/native-observer diagnostics then reproduced the exact error in a90-case native batch: Chromium-mobile login_invalid, observer1 from tuiFontSizeWatcher observing foreign iframe BODY344×16. It remains unknown whether callback feedback, cross-document native delivery or teardown timing is the precise cause. The previously accepted page-before-context close mitigation does not prove elimination.

Controlled response-only source experiment80contexts each no-op/native/scheduled was nondifferential (zero ResizeObserver errors in all3, expected401 resource diagnostics retained), so it does not prove a fix. Raw `/tmp/peerly-watcher-comparison-{driver,server}.log`; temporary server59956 was stopped by its owned listener PID. Actual Playwright1.65 screenshot code prepares/restores caret/animations in all frames, waits fonts only in main frame, and performs RAF/poll stabilization; these call-order facts differ from the standalone raw screenshot driver but are not yet a causal conclusion.

Last finite hypothesis batch complete: exact-runner no-op90 and scheduled90 both passed with exact module-transform assertions and no runtime diagnostics. Controls remain nondifferential; known native90 earlier failed1 runtime diagnostic. There is insufficient mechanistic evidence to claim scheduled delivery fixes the intermittent native issue, so no additional dependency source patch was applied. Temporary ResizeObserver wrapper and response transforms have been removed; only safe cross-realm error/context reporting remains. Source responses are transformed only for the watcher in these temporary controlled experiments; production dependency remains the accepted border-only patch. After these controls no further hundreds of probes without a new mechanism. Diagnosis stopped14:30UTC after about22minutes from the failed gate; no more mass probes in this hypothesis. Runtime issue remains open while independent FE03 work continues. No suppressed diagnostics, disabled production scaling, ad-hoc schema fixes or accepted bad baselines.

## Current FE-02 checkpoint

Accepted FE-02 checkpoint contract: **21 enabled paths**, including six actual media endpoints. Generation now supports the real immutable JPEG binary response as `Readonly<Blob>` and rejects unsupported/mixed media; readonly signed-form fields are compile-tested. No media ticket request/cache/logging or photo UI was introduced. Profile activation remains an actual API dependency.

**Current complete gate: GREEN**, `npm run check` with Node24, isolated loopback38383 and official remote WebKit. Passed39tooling,163browser-backed unit tests, build/prerender,3no-JavaScript public checks,84HTTP-boundary visual cases and24real FastAPI/PostgreSQL visual cases. All three required browser projects pass. Coverage statements96.76/branches96.47/functions98.78/lines96.77%; initial488.94kB under unchanged500kB warning limit. Complete raw log `/tmp/peerly-fe02-final-check.log` has **zero** forwarded browser runtime diagnostics under the same parser that fails the CLI. All changed PNGs reviewed, including font restoration/reflow and real PostgreSQL documents. Zero leftover frontend fixture schemas verified. Clean npmci reproduced the tracked border-only patch and all entrypoint hashes.

Accepted schema21 SHA256 `a9cc5dd7a67608d043a49086f9443ae8cb5f2045e3e7aacc63b5d4db44b738c1`; generated types `11344f6d4c2b28da3499259a7ac80e59e8b1ba0eef2f5235ba3d87aee9c41660`. This records the accepted checkpoint before parent releases additional public mounts. Earlier gate/diagnostic records below are historical, not the latest result.

**FE-03.1 complete: actual25 contracts accepted locally.** Independent export is semantically identical to parent export SHA256 `d8cd171bb6b4fdb8fb3f9f5d42cba831c467529d5da82632c76ae234bd3024d9`. Formatted snapshot SHA256 `d4927b3dc2ed08eb88b9b05ba5a6f8055196f261e65e0f331dc6f1471a79e89c`; generated types SHA256 `a4ba0333ee528f44eb8f48b59a813d3cbd36332ed6bcad5bf267a6f675264f55`. Constrained discriminator mapping requires exact local oneOf coverage and matching literal tags; request required tags and actual optional response defaults are preserved, never injected. Negative mapping cases and readonly TypeScript narrowing pass.

New complete `npm run check` **EXIT0**, log `/tmp/peerly-actual25-check.log`:40tooling,163units,3no-JS,84boundary visuals,24real FastAPI/PostgreSQL visuals. Coverage96.76/96.47/98.78/96.77%, initial488.94kB. Zero forwarded runtime diagnostics using the CLI parser; zero leftover frontend fixture schemas. No screenshot baselines or production UI changed. Earlier21 hashes/evidence remain the accepted historical screen checkpoint. First attempt caught an unqualified tooling global in ESLint; corrected to globalThis before this full successful rerun. Profile/goals/photo draft slice is detailed in roadmap FE-03; final activation/visibility waits for its tested exported contract. Registration completion, remaining extended auth/staleness/keyboard matrix, native exchange/device builds/real OS fonts and live Google/SMTP/S3 remain explicitly separate work. No fake profile activation or media ticket cache introduced.

Docker survived the reported network interruption: owned WebKit run-server is available; shared postgres-test is healthy and was not reset. No shared source was discarded. Parent coordinates working-branch/staging/commits/push; this worker has performed none. `../secrets` was not read or used. Raw synthetic lifecycle reproduction remains `/tmp/peerly-lifecycle-vite.log` and `/tmp/peerly-lifecycle-probe.mjs`: one diagnostic followed context-only close20, none followed ordered page/context close20. This supports a teardown association; no production scheduling cause or broader source patch is claimed.

## Task ledger

| Task    | State | Evidence / remaining dependency                                                                                                                                               |
| ------- | ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FE-01.1 | done  | Rules, approved decisions, actual routes and original checks inspected; shell duplication fixed.                                                                              |
| FE-01.2 | done  | Current enabled exporter consumed: 25 actual paths, readonly tagged unions and JSON/JPEG contracts, deterministic drift check; no unused media services.                      |
| FE-01.3 | done  | Real lazy shell bootstrap through Angular HttpClient and QueryClient; cancellation, runtime validation, safe errors, no retries, no mirrored state.                           |
| FE-01.4 | done  | V2 supplied actual controls; real CSRF/email writes/logout/private-cache and draft cleanup are implemented and checked.                                                       |
| FE-01.5 | done  | Complete local frontend gate green for implemented scope, including actual FastAPI/PostgreSQL and all three browser projects. Unimplemented product scenarios are not waived. |

## Accepted FE-01 full gate (before v2 screen changes)

`npm run check` passed with Node 24, `PLAYWRIGHT_BROWSERS_PATH=/tmp/studymate-browsers` and `STUDYMATE_WEBKIT_WS_ENDPOINT=ws://127.0.0.1:8879/`. It ran contract drift, Prettier, typed ESLint, Stylelint, Knip, all TS checks, 19 tooling tests, 62 browser-backed unit tests, production build, 18 HTTP-boundary visual scenarios and 6 actual full-stack visual scenarios. All passed; no lint/coverage/bundle threshold was relaxed. Strict Ruff check/format of the Python frontend fixture also passed. The complete updated gate includes the graceful fixture-teardown fix, followed by a direct PostgreSQL assertion of zero remaining frontend fixture schemas.

Coverage: statements 98.66% (74/75), branches 99.21% (126/127), functions 100% (16/16), lines 100% (57/57). Initial production bundle 413.97 kB, below unchanged 500 kB warning budget. These are preparation/shell checks, not full MVP coverage.

Three new full-stack PNG baselines were visually inspected and keep the existing shell unchanged. Every scenario has behavioral assertions and a screenshot checkpoint. Existing baselines were not changed. A final formatting check covers subsequent documentation-only edits.

## Implemented behavior

Backend-owned `studymate.export_openapi` runs directly in the locked backend virtualenv with synthetic enabled-auth settings and no DB/provider I/O. Both `frontend/contracts/openapi.json` and `src/app/api.generated.ts` are reproducible; `contracts:check` fails on source/snapshot/type drift. The limited OpenAPI 3.1 generator rejects unsupported constructs, projects readonly nested objects/arrays/maps and preserves actual statuses/headers. Four tooling tests include TypeScript rejection of DTO mutations. No dependency was added: current openapi-typescript peers require TypeScript 5, conflicting with pinned TypeScript 6, so no forced install/downgrade was used.

The drift gate caught Noether's registration update; it was reviewed and regenerated. `/me.registration` is required nullable and its receipt/policy references are runtime-validated. Current snapshot includes actual registration/context/policy routes and GET email-challenge status, not future inferred endpoints. Latest backend handoff also adds required nullable `/me.email_challenge_id`; its runtime validation and existing browser fixtures were updated. Null, current ID, wrong type and missing field are covered; the updated full frontend gate passed with 62 units, 18 boundary visual scenarios and 6 full-stack visual scenarios. All generated contracts and existing consumers are synchronised with this 13-path export.

The lazy pre-design home boundary executes a public QueryClient query for `/api/v1/me`; the server response alone owns identity, capabilities, CSRF and registration state. Account-scoped cached/in-flight work is cancelled/removed before revalidation. HTTP cancellation works before and during subscription, malformed DTOs fail safely, 401 produces unauthenticated query data and other failures retain only bounded safe metadata. Unit tests cover replacement while old private work is pending. No credentials/private server data are persisted or rendered in the static shell.

There is no reactive session UI yet. An unused injectQuery observer pulled Angular namespace compatibility code into the initial bundle; using public QueryClient execution for this one-time bootstrap keeps the initial bundle within budget. Product consumers should evaluate injectQuery when they actually need signals. The known bootstrap failures remain in QueryClient without a second error store; unexpected failures are not swallowed.

Full-stack fixture migrates a unique schema in the disposable PostgreSQL database on port 5433, seeds synthetic sessions and uses actual FastAPI routes/use cases. Ephemeral loopback HTTPS enables genuine Secure HttpOnly host-only cookies in all browsers. Tests verify PostgreSQL readiness, unauthenticated/authenticated bootstrap, CSRF denial, logout and persisted session revocation. The browser receives real HTTP responses; no route.fulfill is used in these full-stack scenarios. Fixture data/TLS are cleaned afterward. Backend webServer uses explicit graceful SIGTERM shutdown; the fixture permits its final cleanup after Uvicorn re-emits the signal. This fixes the default forced-stop behavior that left a schema behind; zero remaining frontend schemas was verified after the corrected run. Real Google exchange, email delivery, native authentication and product screens remain unverified here.

## Runtime restoration and cleanup

Extracted task-local libs restored actual WebKit launch and individual checks, but PRoot repeatedly failed with native EFAULT/double-free during trace I/O. It is not the accepted runtime. No host library edits, trace suppression, browser patches or dependency-validation bypass was used.

The accepted full gate used official `mcr.microsoft.com/playwright:v1.65.0-noble` digest `sha256:6e3fb709361521eb27161606e6da6d2674e5e89fa16516cb37d6fdd91372273d` and its standard run-server, with a read-only frontend mount, loopback published port 8879 and memory cap 768 MiB. `exposeNetwork: '<loopback>'` forwards browser requests to the host test client. Docker Desktop briefly stopped; its user service and only the owned `postgres-test` service were restored. Cause was not established. All final tests ran after recovery.

Browser fixture is stopped after acceptance; matching image remains cached. PostgreSQL remains healthy for Noether. Reproduction commands and optional remote-WebKit configuration are in `frontend/README.md`; ordinary local Playwright launch remains unchanged when no endpoint variable is set.

## Parent handoff and remaining boundaries

Parent updated `.github/workflows/frontend.yml` locally with disposable PostgreSQL 16.15 on port 5433, setup-python from `backend/.python-version`, pinned setup-uv and backend `uv sync --locked` before npm checks. The updated file was inspected read-only by Halley; workflow formatting/diff checks passed according to parent. Remote CI has not run. No CI prerequisite blocker remains in the local plan. This worker did not edit the shared workflow; standard CI retains normal --with-deps browser setup without remote WebKit.

No owner credentials or additional local inputs are needed for this completed preparation. Next real frontend work needs revised reviewed designs and current implemented API contracts. Do not start product screens/theme, speculative guards, sign-in routes, social mutations, analytics collection or unused CSRF services while waiting. No commits, pushes, MRs, live Google/email/S3/Codex calls or deployment.

## Changed paths owned by Halley

- Three frontend planning documents: roadmap, FE-01 epic and this ledger.
- `frontend/README.md`, `package.json`, `playwright.config.ts`.
- `frontend/contracts/openapi.json`, `src/app/api.generated.ts`.
- `frontend/src/app/app.ts` (duplicate Taiga import removal) and `app.spec.ts`.
- `frontend/src/app/screens/home/home.ts`, `session.ts`, `session.spec.ts`, `home.visual.spec.ts`, `home.fullstack.visual.spec.ts`, `SCENARIOS.md` and three new full-stack PNGs.
- `frontend/tooling/contracts.mjs`, `openapi-model.mjs`, `openapi-model.test.mjs`.
- `frontend/testing/backend_fixture.py` and `proxy.json`.

All other pre-existing root/backend/frontend changes remain unrelated baseline. No backend or shared-ledger edits.

## Latest backend handoff integration

Backend's reported 278-test green run is separate from frontend evidence. The frontend consumed the actual 13-path enabled export, including ChallengeStatusResponse, ChallengeState, EmailDeliveryState and VerificationOutcome. No DTO was hand-authored. Future real verification UI must read server can_verify/can_resend and deadlines; consumed does not imply successful verification, support_required must survive reload, and sent means provider acceptance rather than inbox delivery. There is no genuine challenge-status UI consumer before revised designs, so no unused polling service, client timer policy or automatic resend was introduced.

## Latest status reconciliation

Fresh `npm run contracts:check` passed after the parent's latest backend/CI handoff; the 13-path generated schema is current. Parent accepted the recorded full frontend gate evidence. README and this ledger now reflect the parent-owned local CI prerequisite fix, without claiming a remote CI run. No new feature work or heavy test rerun was performed for this documentation-only reconciliation. Next dependent frontend work waits for parent-reviewed designs; there is no stale exporter blocker and no autonomous polling loop.

## V2 release — active FE-02

Parent released final theme and real screens on 7 November. Earlier bounded-only/design hold statements are historical and superseded for dependency-ready product work. FE-02 is detailed in the frontend roadmap under the existing document ownership. First active task: curated assets/theme and public landing, with static no-JS rendering evaluated narrowly. Auth and public policy work follows actual 13-path schemas and review exceptions; no source package AGENTS/runtime/CSS is adopted. Backend BE-02 profile work is a dependency, not permission to fake endpoints.

## Fresh v2 implementation status — parent status handoff

Implemented since v2 release, not yet full-gate accepted:

- Theme through installed Taiga tokens: washi/fuji/sakura palette; self-hosted Inter and M PLUS Rounded 1c; removed old Manrope. Curated original logo/favicon/Google mark/mascot SVGs with SHA-256 provenance; font source dependencies pinned.
- Narrow stylelint theme contract accepts only named semantic tokens/four public appearances in one theme file, rejects arbitrary tokens/selector overrides and component-level custom variables. Regression tests added; no blanket ignore or threshold change.
- Real W01 public landing, with duplicated data/retention summaries, owner placeholders/store buttons and unsupported timing claims omitted. Root landing makes no private bootstrap request.
- Build-time prerender of public `/`, static `index.html` plus `index.csr.html` for client routes; no live SSR server. Standard universal web-API providers are server-only. Last completed build prerendered one route and used 488.25 kB initial, below unchanged 500 kB warning budget. Nonlanding query providers are lazy-loaded.
- Actual Terms/Privacy document reader uses generated policy API/types, version query key, safe plain-text rendering, loading/failure/retry. Public Help is an honest FAQ without fake support submission/contact values.
- `/onboarding` now consumes actual QueryObserver/MutationObserver state: Google web navigation, email/code typed forms, exact-domain validation, actor-owned status/deadlines, CSRF, stable intent keys on uncertain retry, explicit resend/change, wrong/locked/expired/support-required states, session failure/retry, capability restrictions and logout/draft cleanup. No mirrored server signals. Native OAuth is not fabricated; browser entry is the implemented path.
- Registration receipt is not invented in callback. Final explicit registration remains tied to the actual profile/onboarding action once BE-02 endpoints permit it; no checkbox or dedicated legal step added.

Latest validation: build/prerender passed as above; lint fixes and new unit suites are actively running. Full FE-02 acceptance (95% coverage + all new visual/full-stack matrices and inspected baseline updates) is still pending. Existing FE-01 accepted evidence is retained above as historical, not falsely applied to new screens.

Concrete dependencies reported to parent: callback failures currently navigate to raw JSON, so themed cancellation/error recovery needs an actual safe backend redirect contract; current bootstrap supplies neither Google email nor a next field; profile/activation, real support submission and native exchange are separate endpoint/adaptor dependencies. Five wrong attempts lock rather than auto-replace a challenge, and local email editing does not silently cancel server state.

Current next task: finish unit and boundary validation, migrate old shell scenarios to actual public/auth consumers, add no-JS built-artifact checks, and verify real FastAPI/PostgreSQL UI mutations. Continue ready work without waiting for ordinary approval. No source export CSS/runtime copied, no backend/shared-ledger edits, no commits/deployment/live provider calls.

## FE-02 fresh verification and delegation boundary

Confirmed callback-recovery contract is now implemented, superseding the previous raw-JSON dependency note: six fixed allowlisted messages, UUID-only diagnostic reference, metadata stripped using router replaceUrl, identity still independently loaded from `/me`. Actual enabled schema regenerated successfully. Unknown query/provider text is not echoed or treated as authentication. No registration receipt is fabricated.

Fresh checks: **163 unit tests green**, coverage statements96.76/branches96.47/functions98.78/lines96.77%; **27 tooling tests green**; TypeScript application/spec/browser/native-config checks green. Last production build prerendered one route, **488.77kB** initial below unchanged500kB. New built-artifact/no-JavaScript visual suite passed **3/3** projects. Updated actual FastAPI/PostgreSQL guest/session/UI-logout visual suite passed **6/6** with real CSRF denial and session revocation. These screenshot-update runs establish candidate baselines, not final normal-run acceptance; image review and repeated comparison remain pending.

Current boundary suite **55/57 passed** across mobile Chromium/WebKit/desktop; two 320px/200% checks detect 4px horizontal overflow caused by Taiga's hidden font-watcher iframe (`width=320` plus native borders). Identified in installed `@taiga-ui/font-watcher`0.6.0 source; task-local inspection of current0.7.0 shows same code, so no unsupported override/update was installed. Do not hide overflow, exempt the scenario, disable accessibility scaling or manipulate library DOM. Parent coordination/upstream-compatible resolution remains required. Vite also reports ResizeObserver-loop diagnostics; investigate rather than claim zero runtime errors globally.

Static mascot derivatives remove exported animation styles/class hooks, retaining original vector paths; documented provenance distinguishes original hashes from derived output. Self-hosted font OFL license files included. Visual inspection found missing Taiga5 input directive: corrected to public `TuiInput`/`tuiInput`, rather than styling native inputs. Closing CTA uses supported primary-grayscale appearance to retain contrast on the primary panel. Updated baselines still need final all-image review.

Current work: add real browser Google-entry/callback flows against controlled provider boundary plus actual FastAPI state/PKCE/session/PostgreSQL; no live Google requests. Add policy/help visual recovery cases, then finish outstanding auth matrix and full gate. Native exchange/profile completion/support endpoints remain actual API dependencies. Full FE02 is **in_progress**, not accepted.

Future parent-managed split: operator screens become a disjoint implementation slice only once actual operator endpoints, role/capability contract and authorization checks exist; candidate ownership `screens/operator/**` plus colocated tests/ledger assigned by parent. Root routing/shared contracts stay coordinated by current frontend owner. Public landing/policy/help currently share FE02 routing/brand and active tests, so no independent worker is needed there now. No own subagents started; no speculative endpoints introduced to enable a split.

Additional fresh evidence: all **15 real FastAPI/PostgreSQL UI scenarios** passed in screenshot-update mode (three per-project Google success/cancellation/provider-unavailable plus existing guest/session/logout). Controlled Google boundary is fixture-only `provider.invalid`, intercepted before external networking; real state/browser validation and session use cases remain unchanged. Diagnostic request UUID generation is fixed only in the isolated fixture process for repeatable screenshots; production uniqueness is not tested by this substitution. Nine callback baselines regenerated after deterministic correlation was introduced; normal comparison is still required. Public policy/help suite now **12/12** green in update mode, including publication failure/retry and safe literal rendering. Loading/retry/uncertain-send checkpoints added; their nine cross-browser cases passed. Wrong-code status test is being corrected to include the actual server `verification_outcome: wrong` field; no production fallback inferred from HTTP failure alone.

Latest ordinary full-stack comparison: **18/18 passed** after baseline inspection, including real durable email worker/provider-boundary/verification/reload. Fixture sender never sends SMTP; driver-only loopback `/__fixture/deliver/{email}` is excluded from schema and exists only in testing composition, never production source/UI. Wrong-code browser case corrected to actual status outcome and **3/3 passed**. Image contact sheets inspected for all generated state variants; original shell baselines for the two failing reflow projects remain stale deliberately until the actual defect is fixed, not silently accepted. `npm run check` now running for a current complete-gate result; expected remaining quality dependency is upstream font-watcher overflow/ResizeObserver behavior, plus any newly detected baseline mismatch. No thresholds, host validation, tracing, viewport scaling or scenario requirements bypassed.

## Authorised dependency source correction and cause split

Parent authorised a minimal version-pinned source correction. Added `patch-package`8.0.1, explicit font-watcher0.6.0 override, tracked two-entrypoint patch, and pre/post SHA-256 verification for all five distributed entrypoints/types. Only source change is `border: '0'` in the watcher-owned iframe styles in ESM/CommonJS. No provider/API/font-scaling behavior changes. Three source/hash/resize/measurement/teardown regression tests pass. **Clean `npm ci` passed**, applying patch with fail-on-error plus pre/post hashes; no source downloads/latest version or ignored patch failure. README records upstream source, exact versions, hash manifest and removal criterion.

Separate application layout correction: the hero's implicit min-content grid plus large button also overflowed after iframe border was fixed. Explicit `minmax(0,1fr)`, consistent rem gutters and documented medium buttons fix it; content is not clipped/hidden and labels are unchanged. Closing CTA contrast uses built-in primary-grayscale appearance. Current 320px/200% screenshot-update checks **3/3 pass** across all required browsers.

Public theme heading overrides now retain Taiga's public `--tui-font-offset`, with unitless line-height ratios preserving the supplied baseline. Controlled real-observer/provider/theme input28→17 grows heading36→47 then restores36 on **3/3 projects**. WebKit's synthetic hidden-frame decrease needed a main rendering turn after full-page screenshot: diagnostic observer showed body17 while offset11 until next render, then callback updates0. The test awaits one requestAnimationFrame after the synthetic input; no timed delay, production DOM workaround, enlarged-text baseline acceptance or scheduling patch. Diagnostic instrumentation removed. This is controlled browser behavior, not acceptance of a real device OS font setting; native device checks remain external.

ResizeObserver-loop diagnostics remain a **separate investigation**, not claimed fixed by the border patch. Instrumentation observed the font BODY and input auxiliary SPAN width0→24; ten controlled input navigations did not reproduce the error. No causal scheduling patch is justified yet. Shared visual fixture now captures native ErrorEvent/unhandled rejection before framework/Vite prevention, plus pageerror, and fails scenarios on runtime errors. Expected HTTP/resource failure tests are not ErrorEvents; no known runtime-error filter or console suppression added. Fresh full boundary update/inspection is running after clean install; full FE02 gate is still pending.

## Accepted FE02 implemented slice and resource lifecycle

Implemented W01 public landing, W02/W03 policy reader, W04 FAQ, actual A01–A03 Google/mail verification/recovery/logout surfaces, supported Taiga theme/local fonts/curated static SVGs, static no-JS root, readonly actual contracts and strict tooling. The full gate above accepted this implemented slice; FE02 overall remains in progress for the named remaining tasks, not falsely complete.

Owned test pages now close before context disposal/final runtime assertions. Native/page/console/forwarded WebSocket errors are observed without a ResizeObserver exemption. A CLI lifetime gate preserves raw output and fails forwarded Vite runtime/application-console errors even after target detachment, with preserved failure/cancellation codes and bounded graceful timeout. Its eight subprocess regressions include fragmented/EOF error output, child success-with-runtime-error, exit7, cancellation and forced timeout; ordinary browser HTTP resource diagnostics are distinguished from JS errors only when the actual failed API URL is observed. The40-context probe supports a forced-context-teardown association; no broader production watcher patch was made. Only the reviewed iframe border correction remains in dependency source.

Actual consumer contracts are verified through real server/DB, including versioned published policy reads. Google and email providers are controlled test boundaries; the durable SQL delivery worker and verification remain real. Fixture settings explicitly disable media/observability providers and never read owner secrets. Browser/Python fixture shutdown cleans its own schema and TLS. Shared PostgreSQL was preserved. Official WebKit fixture remains available for parent-coordinated checks; no personal browser processes were inspected/closed.

Backend full-run END received:2385pass/6 migration-test-isolation failures; runtime
public60 D03/head40 unchanged. Heavy resource released, but no new frontend PG
lease exists. No backend full-green claim; explicit fresh READY still required.

Latest read-only WKfocus2 evidence: actual noValidate=true, native submit/invalid
event counts both0 and ng-submitted false even after5s; active element remains
button, document focused/user activation true, no iOS proxies. This rules out the
assumed callback-placement/gesture explanation. Next bounded question after PG is
passive pointer targets/button geometry during blur/error insertion; no forced
click, native DOM focus or detectChanges workaround without proof. Artifact
`/tmp/peerly-compose-webkit-focus-geometry-2.json` and isolated trace are preserved.

## Stable composer footer: finite behavior, visual completeness pending

Public fullscreen plus own layout size containment and a single scrolling heading
bound to the public context ID passed finite WebKit2/2 CLI0/runtimeclean15s.
Original real first click, exact Send rect through blur, invalid focus, Tab/Enter,
Unicode values and320px/200%/keyboard-height assertions passed. Raw
`/tmp/peerly-compose-footer-wk3.log`. This is a finite regression proof only.
Offline image review found note error text below the body viewport and a later
capture without the footer in view. Aquinas must add explicit actual error-region
visibility and footer reachability/geometry before accepting those checkpoints.
No screenshot masks, control CSS overrides or broad acceptance from assertion count.
No production changes during the lead PG12 source window.

## Current clean-source PostgreSQL comparison queue

Candidate lease halley-discovery-visibility-pg12-candidate1 completed12/12 CLI0,
runtimeclean1.2m on actual64/head41; raw log SHA256
`ed565379b2b4c1d51c5edadabc19f89ef3451bce5b00321d8155426ed0bab48f`.
Fixture850502, schema/three pools/TLS and all owned listeners cleaned;3 new empty
worker TLS directories removed,0 new nonempty directories. Matching END released
backend/browser holds before offline image review. All42 PNGs are reviewed;
`/tmp/peerly-pg12-review/manifest.json` records every original hash and17 review sheets.

Before normal comparison START, Aquinas detected ngc without --noEmit had emitted
50 sibling JavaScript files into src. Its3 owned and47 lead-owned emitted artifacts
were removed only after exact inventory mtime, sibling TS and source containment
validation; hashes are in `/tmp/peerly-ngc-artifact-cleanup.json`. No real TS removed,
no Git mutation. Source JS count is0. Installed builder resolves TS before JS, but
this does not waive fresh clean-source proof. Normal1 never started and its pending
lease was cancelled; renewed normal2 explicitly requires fresh READY. Clean-source
app/e2e tsc --noEmit both passed. Candidate evidence has this source-resolution
qualification until the clean-source comparison passes; no full-app acceptance.

## Clean-source real PG12 accepted

Fresh explicit READY/START/END normal2 completed12/12 in1.1m, runtimeCLI0 and all42
reviewed image comparisons passed without updates. This resolves the candidate's
emitted-JS source qualification for this exact scoped comparison. Original frontend
TypeScript was untouched; generated artifacts remain absent. Do not generalize
this scoped result into renewed whole-app unit/build/aggregate acceptance. Aquinas
has the next browser resource for composer87; backend source hold is released.

## Relevant normal browser checks and emission guard

After the current QueryObserver/native-resource fix, original uninstrumented
WebKit unknown-send passed1/1 CLI0/runtimeclean7.9s,3 reviewed PNG comparisons;
raw `/tmp/peerly-compose-photo-normal1.log`, SHA256
`056d79c25b2d780d8e173996ed0558523948fc677f2f73a0bbd35dafd6f9e219`.
Lead photo404/503 and strengthened unknown-task replay passed9/9 normal across all
three projects, runtimeCLI0/16.5s, no baseline changes. Raw
`/tmp/peerly-photo-setup-http9-normal1.log`, SHA256
`2d0788d825b570332bffd4295ee9fd304ee1965a877f670d15d6325f914eca91`.
These scoped passes do not establish exact causality of the earlier native blob
failure or resolve the separate aggregate ResizeObserver issue.

`tooling/source-emission.test.mjs` now detects compiler-emitted JS/maps beside TS
source, with an isolated positive/negative temporary fixture; all49 tooling tests
pass. Frontend AGENTS requires ngc --noEmit for template checks. No production
configuration or budget weakened. This tooling-only addition does not invalidate
current851-unit/499.91kB source proof; no redundant application run for it.
No source/browser changes during Aquinas full87 window. Fresh PostgreSQL work waits
coherent head42 because active canonical product-event columns are being integrated;
no old head41 fixture reuse or shared reset.

## Composer full candidate10 completed, image/normal acceptance next

Aquinas reports87/87 candidate cases CLI0/runtimeclean2.6m across all three browser
projects, original console guard and uninstrumented unknown-send scenario intact.
Raw `/tmp/peerly-compose-boundary-candidate-10.log`, SHA256
`b80bf078a7e8fac2fdd86bebec0c76eed24b1e04a0697af9ee8e0cd2d4ad635d`.
Owned listener38385 cleared, no PG fixture. All changed/new images require review
before normal87; the earlier partial56 reviewed files do not accept new desktop
images automatically. Aquinas owns that review. New-footer composer PG27 also
remains pending. This is a clean candidate boundary, not full frontend acceptance.

Lead is ready for relevant Discovery PG9 normal after the photo resource source
fix. It waits Noether's coherent42 runtime and tested67 enum/source-reference export,
then a fresh explicit lease. No backend hold is requested while that integration
is unfinished. No old-schema reuse, skips or shared database reset.

## Full candidate image review and final recovery captures

Aquinas reviewed all198 current HTTP composer PNGs. Five WebKit denial captures
showed the actual reason but not the actionable Requests recovery link/cooldown
date inside the scroll body. A bounded15-case(all three projects) test-only capture
refinement now scrolls the whole genuine recovery link and asserts both reason/link
and actual Kuala Lumpur cooldown date in viewport. No production/layout change,
mask, diff tolerance or scenario-count change. New images must be reviewed before
normal87. No second full candidate is needed for that bounded capture correction.
Lead additionally inspected representative desktop validation/unknown-send images:
public fullscreen45rem content, natural error wrapping and separate footer are clear.
Fresh PG9 continues to await Noether coherent42/tested contract; no backend hold.

## Composer reviewed198 references; normal87 next

The bounded denial capture run passed15/15 CLI0/runtimeclean26.1s. All6 changed
images(5 WebKit plus desktop cooldown) were individually re-reviewed; remaining9
hashes were unchanged. All198 current HTTP PNGs are reviewed in Aquinas's manifest.
Raw `/tmp/peerly-compose-denied-capture1.log`, SHA256
`f465380253e78b5990e2b50c292c14592241b55eff5a84b7ddea29e3db25d030`.
Normal87 is now granted with no snapshot updates and frozen production source;
no further capture changes planned. Real PG remains gated on coherent42 and an
explicit new source/resource lease. Unit failure-only diagnostics were archived
outside source by their owners with hashes; no visual reference was removed.

## Current HTTP composer accepted; real PG waits coherent42

Normal87 completed87/87 CLI0/runtimeclean2.1m across all three projects,198 reviewed
PNG comparisons with NO updates, original native console gate and uninstrumented
unknown-send scenario. Raw `/tmp/peerly-compose-boundary-normal1.log`, SHA256
`4540b58ad177dcb1486ca2b5da691bc421c5effc1b4e5ef80f23a79c40497b19`.
Aquinas reports owned listener38385 clear; no PG fixture or active browser resource.
Current UI/form/source reconciliation/quota/validation/recovery slice has complete
HTTP-boundary acceptance. Renewed real composerPG27 and lead DiscoveryPG9 still
require coherent42 plus tested schema handoff, fresh explicit leases and migrated
isolated fixtures. Last PG64/head41 evidence remains historical to the photo/footer
source changes; no fake current full-stack acceptance. No owner input is required.

Tooling49 raw log is `/tmp/peerly-emission-guard-tooling.log`; the earlier
`peerly-photo-final-tooling.log` contains47 before the two emission guard cases.
Application source/build are unchanged by those tooling/documentation additions.
No whole aggregate check is claimed; independent native ResizeObserver remains open.

## Current head42 real Discovery accepted

Fresh explicit lease halley-discovery-pg9-head42-normal1 completed9/9 CLI0,
runtimeclean40.0s,33 reviewed image comparisons with NO updates. Current image
resource lifecycle is now covered against actual coherent67/head42 FastAPI and
PostgreSQL: genuine modes/authorized JPEGs, persisted pass/reload/reconsideration,
server Undo and lost-response immutable replay. Raw
`/tmp/peerly-discovery-pg9-head42-normal1.log`, SHA256
`de685cf519e755690006f840f0ac46c1f6968b9107bcf52d8225f13f06f1ec9e`.
Owned fixture890517, isolated migration head42/schema/three pools/TLS and listeners
cleaned;3 new empty worker TLS dirs removed,0 new nonempty. Matching END released
the lead segment. Aquinas is granted the next browser resource but must obtain its
own fresh Noether READY for composerPG27 candidate, image review and fresh normal.

The schema hash was independently checked; all path definitions are unchanged and
only OperatorEventKind/OperatorSourceKind have additive literals. Existing851-unit,
49-tooling/499.91kB build proof remains applicable to unchanged runtime source;
no unnecessary heavy repeat for unused type-only enum additions. Current renewed
Discovery PG proof supersedes the old head41 limitation for this photo change.
Global aggregate ResizeObserver remains independent and unresolved.

## Real composer candidate27 behavior passed; bounded capture refinement

Candidate d03-composer-pg27-footer-candidate1 passed27/27 CLI0/runtimeclean1.5m on
coherent67/head42. Raw `/tmp/peerly-compose-pg27-footer-candidate1.log`, SHA256
`753fbabdf66d29866b0979c34f639589da6884dd745716c90d64edf36e8f34d5`.
Owned fixture892126/schema/three pools/TLS/listeners cleaned; matching END released
its lease before image review. Aquinas reviewed49 changed frames plus26 unchanged
hashes. Three-mode form/note and source-decision captures omitted some scroll-body
content despite passing behavior. A bounded4case×3project PG12 run will scroll the
whole public text/note fields and source decisions with viewport assertions, same75
reference paths and unchanged production source. No full candidate27 repeat.

Resource is granted for that bounded capture but its own new Noether READY/START is
required. After END+cleanup and changed-image review, normal27 is pregranted subject
to another fresh backend lease; no old hold inheritance. No snapshot masking,
geometry tolerance changes or production CSS adjustments. Final PG visual acceptance
is still pending; the prior candidate assertion count does not override capture gaps.

</details>

### Historical note: bounded PG12 capture1 strict failure

Lease d03-composer-pg12-footer-visibility1 ended CLI1 with3pass/1viewport failure/
8notrun; public field intersection ratio0.999011 after scrollIntoViewIfNeeded.
Raw `/tmp/peerly-compose-pg12-footer-visibility1.log`, SHA256
`9defe42c242512f0a770dd0a320f21259420ee19e9d9d64d5ffafb9d7365eab2`.
Raw reports the viewport assertion and fail-fast maximum-failure stop, not a new
Unhandled/ResizeObserver/Blob diagnostic. Fixture896543/schema/three pools/TLS and
listeners cleaned, own1 empty worker TLS removed. No failing baseline was accepted.
The next bounded12 test-only correction uses native block:center scrolling of the
whole public host, no offsets, ratio reduction or production change. Fresh named
Noether READY/START/END remains required. Normal27 follows only after image review.

## Real remote public staging smoke —10 November2026

Parent reports Portainer staging stack4 created and workers running. Independently,
Halley checked `https://peerly-staging.aleksei-orlov.dev` using fresh Chromium and
WebKit browsers at360×800, default HTTPS certificate validation, no mocks and no
private credentials. Root, sign-in, Terms/Privacy, Help, actual link navigation and
reload were exercised. Real `/api/health` and `/api/ready` each return200/statusok
in both engines; actual Terms/Privacy API reads return200 and render public content.
Guest `/api/v1/me` returns401 as expected, with all resource diagnostics retained.
No Google/OAuth navigation, OTP, registration, support send or message was performed;
433 actual network records contain zero mutating requests. No native error/RO or
JavaScript exception was observed in this bounded run; known RO is not resolved.

Initial execution preserves11/12 passed steps/exit1: WebKit synthetic hidden-frame
font input omitted the established bounding-rect measurement used by the existing
scaling test. One focused correction confirms actual frame28 then17 metrics and
visible title47px then36px, navigation back to sign-in and no horizontal overflow.
It passes exit0, without changing application/source. Early WebKit sign-in captures
also preceded mascot loading; a focused load/reload waits actual visible images'
complete/naturalWidth, passes exit0 and confirms the rendered mascot. Initial
canceled-on-navigation asset requests and all original captures remain preserved.
A decorative icon may still be transient in the reload artifact; no blocking
essential text/action issue was observed. No extra matrix or causal RO probe ran.

Evidence `/tmp/peerly-remote-public-smoke-20261110/manifest.json`, SHA256
`595e666a66bc9968e1a559e4a17b476df9a8ed63d7fdbd65a40702fe8ab31982`:
full network/status/native diagnostic metadata, original/focused exits and23 raw
public PNGs. These artifacts were visually reviewed (contact sheet plus settled
sign-in images natively); they are not golden comparisons or a single original
green execution. All owned browsers closed. Parent owns actual OAuth/mail/S3/AI
follow-up; public-read smoke does not establish any of those providers or private
student functionality. External-user acceptance remains separate.

## Operator completion resumed —10 November2026

Owner reports internal student stage and real typed AI smoke live; human team
student testing is the priority interrupt. FE06 completion now resumes, not further
RO investigation. Existing96/109 schema remains authoritative. Noether confirms
head52/exported527 unchanged and is preparing BE07 eight existing unmounted read
factories plus Plato inbox/history integration0053; no new DTO guessed/generated.

Aquinas is RELEASED for FE06.5 operator-profile-history* plus minimal current
operator.ts/html integration and his ledger. Fresh exact handoff is the10 November
header in frontend/OPERATOR-HANDOFF.md. Recover seven hash-checked isolated files,
not old parent copies/failure PNGs; fix the historical five saved authority/owner/
cursor regressions, preserve accepted operator siblings and write regression
coverage first. Source-complete boundary before consolidated relevant checks.

Halley implements finite new history fixture cohorts in
frontend/testing/operator_profile_history_fixture.py and existing controlled
operator fixture/TS union. Actual retained53 revisions leave current pointer1;
nullable viewer has no history. No new production endpoint, fake authorization,
DB reset, PG/browser/unit run, source deployment or Git. Cheap scoped lint/format
at this coherent helper boundary only. Exact remaining slices/backend gaps and
ownership are docs/planning/epic-fe-06-operator-completion.md. Actual support-case
reads/status are distinct from report moderation; missing queue/privileged chat
binary/relations/triage stay pending actual contracts. Parent owns publication.

FE06.5 lead fixture source boundary: scoped Ruff/import order and Python formatter
pass; strict mypy passes for the new retained-history helper using MYPYPATH to the
actual backend source. The initial PYTHONPATH-only invocation correctly reported
an untyped installed package import and is preserved; source-path correction did
not change checking rules. Prettier passes on touched handoff/planning/TS helper.
Logs `/tmp/peerly-operator-resume-{ruff,pyformat,mypy,mypy-sourcepath,format}.log`.
These are cheap static checks only, not fixture runtime, units, screenshot or PG
acceptance. No active fixture/lease. Noether shared0053 WIP explicitly holds NEW
fixtures until coherent handoff; Aquinas notified and continues production code.

## Urgent student verification/quarantine fix —10 November2026

Operator work PAUSED by owner live issue. Exact13-file FE06.5 source-only archive
387b remains immutable;10 new history files isolated outside TS discovery and
ONLY operator.ts/html restored from accepted student dc8d. Aquinas receipt
`/tmp/peerly-fe065-source-paused-20261110-gqyfudho/student-candidate-isolation.json`
SHA119cb26424cfe3fe78186962c6e76c20bc2ed12ec8b5e0465cba0b7e5e8f1f07.
No Git restore, operator data or source discarded. Urgent candidate excludes it.

Actual delivery enum drives a small readonly public-Taiga widget: sent means the
mail service accepted the email, never confirmed inbox delivery. Queued/sending
and failed/cancelled have distinct truthful uncertain copy. APU filtering may hold
mail; check Junk and the exact parent-verified Microsoft quarantine portal
https://security.microsoft.com/quarantine (official source
https://learn.microsoft.com/en-us/defender-office-365/quarantine-end-user).
Open-new-tab safety attributes, tenant-dependent view/request-release options and
access-denied→APU IT are explicit. No one-click release/instant delivery claim,
email-proof bypass, auto resend or extra legal UI. Real cooldown/can_verify remain
server-owned; actual support fallback and Help copy are connected.

First targeted39 capture36/3 preserved a real320/200 code form min-content overflow
and a WebKit synthetic font input needing its rendering turn. Supported fix:
form minmax(0,1fr) plus external public tuiLabel. Full caption bounds/input keyboard
focus/no overflow regression passes. Test-only font28 turn matches existing17
restoration, with no application scheduling or RO patch. Exact affected31 repaired
captures pass CLI0;42 intended text/layout refs reviewed in sheets and native active
screen. Ordinary39/39 then pass CLI0 in46.7s without updates/runtime diagnostics.
Only these changed verification/Help flows ran, no1080/228/PG/live mail.

Target initial30 unit behaviors pass but scoped coverage gave CLI1; original result
preserved, no95 chasing or lowered threshold. Final widget-link7 pass100% scoped.
Owner explicitly required ONE final whole-unit/static/build boundary:1500/1500 in
86files pass CLI0, coverage95.65 statements/95.03 branches/96.68 functions/98.11
lines. Format, full ESLint/styles/types, Knip, actual96 contract drift and dependency
hash verification pass. Production build CLI0, initial513.84kB under525; styles4kB
unchanged, zero warnings, one prerendered route. No active owned runner/listener.
CPU released to Noether urgent identity tests; RO internal known issue remains.

Frozen selective OTP evidence/source manifest is under
`/tmp/peerly-otp-quarantine-fix-20261110/`; exactly6 production paths plus4 test
files/42 changed refs, with explicit exclusion of operator WIP, generated DTOs,
configuration/lockfiles and fixtures. Parent alone resolves current production40bf
base and performs CI/publication/deployment. Fresh signup after deletion is a
separate same-DTO backend behavior change: Noether confirms new UUID/unverified/
no restored history and old-proof receipt-only semantics, tests still pending.
Keep old actor cache/credentials retired; do not block OTP deployment on that fix.
Old P05 cannot-sign-in-again copy is identified for coordinated change at READY.

## Fresh-account P05 handoff complete —10 November2026; operator HOLD

Noether confirmed tested SAME96/109 IdentityResponse/callback contract: deleted
unbanned returning Google identity creates a NEW UUID, unverified/no registration;
new student-email OTP required, old profile/chats/history never restored. Old
delete-proof cookie remains receipt-only and cannot authenticate or authorize the
new actor. Banned lineage protections remain server-owned. No new frontend DTO,
endpoint or TS business logic was needed.

Two production HTML files replace stale cannot-sign-in-again text with original
account cannot restore / new account requires student verification / no transfer.
Confirmed proof offers the genuine onboarding entry, not a restore/auth shortcut.
Public button-vertical layout preserves320/200 readable keyboard-reachable CTA.
Exact source freeze `/tmp/peerly-fresh-account-frontend-20261110/production-manifest.json`
SHAbfdff6ba4c4caecd1a371edd4bb6c1f2a7736a2856459df9bda3dfb85bf440d3
was unchanged through acceptance and parent checkpoint.

Targeted32/32 unit behaviors pass, including real HttpClient old-read cancellation,
old private cache retirement before fresh /me, new CSRF/challenge and unauthenticated
receipt data not granting identity. Scoped behavior runs disable coverage only as
explicitly owner-approved; global95 configuration unchanged. Existing OTP final
whole1500/95all/build proof is separate, not rerun. Initial19 failures were stale
shared text selectors; old result and19 unit diagnostic images remain hash-preserved
outside source, never promoted to references. Type-only new test Context annotation
was corrected under strict lint/e2e typing, no production/runtime change.

Bounded15 capture and15 ordinary browser comparisons pass CLI0; thirty changed
references reviewed. Cases cover actual client old-proof→Google-required entry,
backend-confirmed fresh unverified actor, deliberate deletion/confirmation,320/200
caption/actions and canonical proof. Native error guard unchanged; no RO/JS error
observed. These are controlled wire boundary tests, not real Google/inbox proof.
Angular noEmit, spec/e2e TypeScript and scoped ESLint pass. All owned runners ended;
port38385 free. No new whole matrix, PG, provider, credentials, Git or deploy work.

FINAL accepted receipt
`/tmp/peerly-fresh-account-frontend-20261110/accepted-manifest.json`, SHA256
`fa6cfadfbfb9a8bd938af827310e53e1587c65f82dcd300a9c90302e41439f58` pins2
production files,4 test files,30 refs and exact logs. Parent reports OTP57e990 live
and P05CI42807810466/image5aa270 deployed; parent records final actual digest/HTTPS
smoke. NO actual provider-inbox delivery proof is claimed. Operator remains HOLD
pending parent coordination; blind RO investigation remains frozen/internal-known.

## Operator checkpoint restored after live fixes —10 November2026

Owner resumed operator work while parent/Noether handle staging-only team membership
CLI. Read-only current code confirms verified /me takes setup before any old OTP
challenge branch; no frontend change/grant mechanism is needed. Legal/profile/
registration/activation remain distinct. Manual-verification UI deferred backlog
added to FE06 epic. Read-only151 student production-source comparison against the
accepted base plus shipped OTP/P05 overlays finds no additional unshipped bug delta.

Halley verified8 protected OTP/P05 hashes, all13 immutable387b archive hashes,
then restored ONLY10 absent profile-history files and2 operator parent files whose
current hashes matched the accepted student baseline. No broad restore, Git,
student source, generated DTO or archived ledger overwrite. All8 student hashes
still match after restoration; before-versions and exact receipt are preserved in
`/tmp/peerly-operator-resume-after-live-fixes-20261110/restoration-receipt.json`, SHA
`3e082c1dfeadba7e5d94270a9027ed328a73473ec4da3c19fd0a8cb270432827`.
This is code-complete restored FE06.5, still UNACCEPTED at runtime; historical67/5
was not rerun. No runner/fixture/build or staging private-data access occurred.

Aquinas is parent-reassigned the two backend pre54 historical-migration fixture
fixes, so Halley performed restoration directly without racing his task. Plato
reports13 inbox/history files code-complete/statics, NOT mounted/no new actual API
export; Noether owns shared audit53/composition/schema. Do not generate guessed
DTOs. Next is the bounded FE06.5 acceptance window after Noether urgent helper/CPU
handoff; no global matrix or blind RO work. Parent owns publication/deployment.

## FE06.5 bounded acceptance —10 November2026

Actual mounted106 paths119 operations/head54 reproduced raw export SHA4da93c87…,
canonical schema97b56fe8… and readonly DTOebc1d5ac… generated/drift checked. Existing
student contracts remain canonical-equivalent; support/notification event and
operator-action guard lists now accept actual mounted metadata, with a strict
unknown-enum rejection regression. No generator weakening or invented grant API.

History targeted13 units pass. Final flat operator group78 units/11files CLI0,
coverage97.60 statements/96.43 branches/99.37 functions/98.93 lines. This is scoped
operator coverage; previous1500 whole-unit student evidence remains historical.
HTTP21 behavior/ordinary comparisons pass48.1s but CLI1 preserves native RO errors.
Initial17/4 capture failures and6-case repair evidence remain in exact logs.
Three ambiguous loading statuses were scoped; WebKit32767px encoding limit uses
paired real viewport start/end captures only for50-record states, retaining all50
source/order/DOM assertions. No masks/cropping/tolerance/error suppression.

All54 HTTP/60 PG references reviewed. Genuine FastAPI/Postgres PG12 capture pass,
then normal12 PASS52.4s CLI0, source53 versions/current pointer1/audit links and
hidden/banned/deleted/empty/cursor/grant-revocation/actor-replacement/320text200
cases covered. Own fixture gracefulEND; read-only cleanup frontend_schemas[] and
other_sessions0; Noether106 hold released. No global matrix/runtime-green claim.
Exact raw logs/results/reference manifests/contact sheets:
/tmp/peerly-fe065-restored-acceptance-20261110.

Aquinas OPS02 complete, now returned to new operator/support/** source in /tmp
only until this candidate freeze; shared mutation403 authority integration remains
Halley's next support-candidate responsibility, not part of this history slice.
Parent owns selective publication. Protected OTP/P05 remain unchanged.

Final scoped static boundary: full ESLint, app/spec/e2e TypeScript, Angular noEmit,
styles and production build all CLI0. Initial513.86kB under unchanged525kB, style
budget4kB, no warnings. No whole-app unit/global-browser acceptance is implied.
Canonical106 schema/DTO freeze predates Noether's next additive107 mount, which
was explicitly released after PG END; no drift claim against that future export.

## Operator support integration source batch —10 November2026; NOT accepted yet

Prior FE06.5 selective receipt is frozen at
/tmp/peerly-fe065-restored-acceptance-20261110/accepted-manifest.json SHA
088ddabd7602d9f842f2688e3b51be68794a08fcef4b3aa4e32c354e37ad8c88;
its immutable frozen-source copy protects publication from subsequent working-tree
changes. Parent owns selective publication. HTTP known RO remains explicit.

Aquinas released from OPS followup into NEW operator/support/**; lead released
coherent application only after FE06.5 freeze. Next-candidate shared authority now
recognises actual actor-owned MutationCache403, cancels/retires sibling reads and
keeps denial canonical. Explicit successful same-actor session revalidation removes
only the denial captured before that check; concurrent new failures survive.
Existing three operator entrypoints use this same public helper. Four meaningful
regression definitions are authored; this batch is not unit/browser accepted.

Finite support/support-empty/support-revocation/support-replacement fixture source
is authored:53 cases/six topics/three statuses, registered/anonymous/deleted owner,
main53-revision history/null initial provenance, original literal body/details,
missing IDs, real grants/session replacement/audit hooks. Schema comes from actual
migrations, no providers or mail. Fixture source has not been booted. Cheap spec
compilation passed before final formatting; initial lint findings corrected in
source, final consolidated checks wait coherent widget/root integration.
No broad tests, live-data access, Git or deploy. Actual107 additive conversation
index is now backend-ready but not needed to invent any support DTO/UI.

## Operator support first coherent batch —10 November2026

Aquinas14-file sourcecomplete manifest1d53b2 accepted as source readiness, not runtime
acceptance. Applied real lazy support route with canDeactivate and public custom
runGuardsAndResolvers on selected case-query changes; component pre-confirmations
removed to keep one Router decision. Actual browser Back/Keep/Leave definitions
cover this source-lifetime boundary. Same-case history paging does not prompt.
Canonical107/head54 generated+drift checked; schema8510573e… DTO85a4ce89….

First coherent unit batch100/15files behavioral assertions PASS. CLI1 coverage
92.04/93.34/88.62/94.51 includes all content-route loaders in a scoped suite that
only exercises boot; operator-flat97.76/96.57/99.39/99.07, new support subset
88.17/83.94/92.72/91.52. Thresholds remain95 unchanged. Both the scope denominator
and genuine missing support UI/error/navigation behaviors are explicit, not hidden
by exclusions. Raw lcov preserved in coverage-first. Aquinas owns one meaningful
missing-behavior/test/static correction batch; no per-file95 loops authorised.

First static results retain concrete type/lint/style/unused-export errors in new
owned files; format, Angular noEmit, synthetic fixture Ruff and contracts pass.
Initial npm invocations without task-local wrapper exited1 with empty logs, so
those were preserved as static-first-environment-failure and corrected PATH used
for the actual checks. This is not an application failure or fabricated green.
No support browser/PG started; fresh Noether PG24 runtime lease is granted only at
explicit later START. Actual107 remains coherent; no source/runtime hold active.
Evidence: /tmp/peerly-operator-support-acceptance-20261110.

## Operator support bounded acceptance complete —10 November2026

Combined FE06.8/FE06.11: actual inbox filters/keyset, explicit private detail/history,
status CAS confirmation, immutable unknown replay, no membership/reply/moderation
claims. Actor-owned QueryCache and MutationCache403 share canonical denial; explicit
successful same-actor revalidation retires only captured denial identities, keeping
new concurrent failures. Root lazy route has real canLeave plus query-case guards.
Public Router canceledNavigationResolution=computed fixes the reproduced Back→Keep→
Back failure (three engines RED before / three PASS after). No private Router hooks.

HTTP39 ordinary behavior/zero-diff comparisons PASS; CLI1 retains native RO and its
Angular wrapper diagnostics. Essential linked-account reference is now an ordinary
paragraph before the action; affected320/text200 three-case capture/review/normal
passes CLI0. Other36 controlled cases use an unchanged null-linked inbox branch;
this is explicit partition evidence, not a second whole39 claim. All105 current
HTTP refs reviewed. PG24 ordinary behavior/zero-diff comparisons PASS1.1m CLI0;
all72 current refs reviewed. Genuine sources include53 cases/history, signed keyset,
nullable provenance, deleted retained actor link, exact committed54/55 receipts,
lost-response same-key replay, CAS409, grant revoke/restore and actor replacement.
Source-backed audit/event linkage asserted; no providers or real private accounts.

Native write timestamps remain actual database time. Full receipt/recovery/dialog
runtime images are preserved raw with exact API→DOM ID/status/version/time checks.
Stable complete status-choice forms are compared. Taiga's public dialog wrapper
also includes underlying native timestamps: three unaccepted candidate goldens were
hash-archived outside source; full deterministic controlled-HTTP dialogs still have
strict comparisons. Raw runtime artifacts are not called visual comparisons. No
masks, private DOM selectors, tolerances, process-clock patch or diagnostic filter.

Initial PG10/14 fixture/driver failures retained. Operator inbox is correctly global;
finite historical received-time buckets plus genuine date filters isolate cohorts,
and missing-case filtering gives a truthful empty result. Receipt locator matches
its actual named result section rather than concurrent loading status. Fifty-row
states compare actual first/last viewports while all50 source/order/DOM checks stay.
Initial43 unaccepted refs and later intentional27 row-layout/viewport deltas retain
hash manifests. Every fixture ended gracefully; final schema/session cleanup[]/0;
Noether runtime hold released. No database reset or global leak claim over others.

Final whole frontend1552 tests/93files PASS CLI0; coverage95.77 statements,
95.02 branches,96.79 functions,98.15 lines. Prior94.90/94.91/94.95 coverage exits and
all test failures remain in raw logs; no threshold/exclusion change. Added genuine
read-identity, unavailable-read/reconcile, trusted-session readiness and public
command lifetime races: before HTTP dispatch, after receipt, fresh-read and late
confirmation across actors. New test-driver readiness/semantic button fixes did
not change production authorization. Full static CLI0; final test deltas also pass
strict type/lint compilation. Production build CLI0, initial514.10kB under525,
styles4kB unchanged. Full global browser matrix was not rerun; RO remains an internal
known exception, not external acceptance.

Exact logs/reports/coverage/reference manifests are under
/tmp/peerly-operator-support-acceptance-20261110. Publication must include the prior
FE06.5 dependency088ddabd, not assume it already shipped; frozen union manifest
follows. All8 deployed OTP/P05 hashes remain unchanged. Current snapshot binds
actual107/head54; new tested110/head55 telemetry/delivery contract belongs to the
NEXT observability candidate, not a current drift-check claim. Aquinas owns only
staged /tmp observations until this handoff, parent owns Git/deploy. No new runner,
provider, credentials, real-message or staging mutation is authorised by this gate.

### Client observation integration candidate —10 November2026, after accepted operator union

The accepted operator/support union remains immutable at
`/tmp/peerly-operator-support-acceptance-20261110/accepted-union-manifest.json`
(SHA2567200aff485b387c7ab7b32e06ab79d2d7d1c86b20c314c33c067920dd9e55785).
The working tree now advances independently: canonical generation matches the actual
111path/head56 export (50c381e97422d6af6b1663dea952cff59571ef2d287ca5cf5e6e99e04724c0d0);
generation/drift logs are under `/tmp/peerly-client-observability-integration-20261110`.
The short generation hold ended; no frontend PG lease is active.

Aquinas applied the16 owned observation source/test files and returned from the
completed OPS follow-up. Root ErrorHandler delegation and the HTTP interceptor
are now connected, together with a lazy routed buffer owner using the existing
canonical session QueryClient. Pending/removed identity retires the old buffer;
routed destruction owns unsubscribe/performance/router/delivery cleanup. This is
an implementation checkpoint, NOT accepted runtime or coverage evidence.
Remaining code: semantic human-action consumers/context plumbing, public emitted
asset release-map production hookup, current111 audit-field compatibility and
root/session lifecycle regression definitions. Aquinas owns the new release-map
builder/tooling tests only; lead owns shared integration. Complete source first,
then one coherent acceptance batch. No broad browser matrix or renewed blind RO
investigation is scheduled; known native diagnostics remain unsuppressed.

### Owner-required deferred visual completion —10 November2026

Recorded mandatory post-infrastructure/current-feature design v2 review in
frontend-roadmap.md. All actual screens/states require an inventory, original-board
comparison, supported Taiga corrections and mobile usability validation. Existing
goldens are regression evidence only, not design compliance. Mascots require
separate real-build normal/reduced-motion diagnosis and proof. Phase not started;
current observability integration continues unchanged. Canonical DTO generation
has now advanced to actual112/head57, exact schema comparison passed; no PG lease.

### Environment relocation and resumed client observations —11 November2026

Current repository is `/home/aleksei/Desktop/Aleksei/Programming/apu/studymate/StudyMate-AI`.
Source, canonical112/head57 contracts, the16 native observation files and the two
release-map tooling files survived. Historical `/tmp` acceptance logs/manifests are
unavailable in this environment; their recorded results remain historical evidence,
not newly verified artifacts. Do not repeat suites solely to recreate those logs.
Node24.22.2 is available in the existing npm cache; default shell Node18 is unsuitable.

Implementation resumed: explicit Goal save intent now owns the observation action
handle; uncertain manual replay reuses that same immutable handle. Shared writeJson
accepts optional public HttpContext, preserving all current HTTP/auth semantics.
Current audit runtime allowlist includes actual head57 search_audits. Aquinas owns
only new observation-owner.spec.ts lifecycle regression definitions for this batch;
lead retains owner/root/session/transport/action integration. Formatting ran only,
no new unit/browser/build acceptance claim. Parent must coordinate the exact served
public release-map path and matching backend release configuration before numeric
frames are enabled; absent map remains frame-free. Current integration and source
regression definitions finish before one coherent acceptance batch. Mandatory
subsequent designv2 screen/state and real-build mascot review remains outstanding.

### Coherent acceptance findings —11 November2026

Persistent evidence lives in sibling `.peerly-ops/frontend-client-observations-20261111`.
Initial33file source snapshot SHA294a1ba2fe5dddc3ff2c350cc72bb502a7539e7120165b7735822c057c4f9761
is immutable; fixes advance the worktree and require a final whole-frontend inventory.
First static/tooling: types0/tooling0, format1/lint1; one concrete lint/source batch
subsequently passed lint0. First production build passed at522.69kB/525kB limit.
The first whole unit run FAILED (638pass953fail1591total), primarily because the new
global AppInitializer eagerly loaded metadata before TestBed configuration. This
is retained failure evidence, not an environment-only or RO dismissal.

Corrected the lifecycle: optional public build metadata loads on the actual root
App's supported afterNextRender lifecycle, not the global provider initializer.
The buffer reads the validated release getter when assembling new immutable
batches; pending retry payload/key remain unchanged. App unit tests control only
that external public configuration dependency; dedicated loader tests use real
HttpClientTesting. A bounded transport/owner/loader reproduction now has24passes
and3owner-test failures. Those three advance fake timers but leave the monotonic
performance clock real, preventing the genuine6.1s batch spacing from elapsing;
Aquinas owns that coherent test-clock correction. No production rate limit or
assertion timeout is relaxed. Whole-unit and final browser acceptance are pending.

### Unit/static accepted; bounded browser partitions —11 November2026

Final reliability batch:1634tests/100files PASS, CLI0. Coverage95.84 statements,
95.03 branches,96.87 functions,98.07 lines; no thresholds/exclusions changed.
Strict reliability compilation/lint0, Knip0, prior whole lint/e2e types/styles0,
tooling0. Latest production build0 at522.73kB within525kB. All earlier failures,
including the initial bootstrap regression, retained under persistent acceptance/.

New HTTP goal/action/intake scenario: Chromium mobile+desktop capture reviewed and
normal2 PASS/CLI0. Local WebKit launch was blocked by host ldconfig's libx264 check
(despite restored task-local actual DSOs resolving); no skip/spoof/source patch.
Parent authorised the supported official Playwright1.63-noble remote WebKit. Exact
registry digest6e3fb709361521eb27161606e6da6d2674e5e89fa16516cb37d6fdd91372273d,
owned read-only container, cap-drop/NNP,1GiB/1CPU/PID256, bounded tmp/shm, loopback WS,
only pinned node_modules mounted read-only, existing exposeNetwork<loopback> port.
WebKit actual scenario capture PASS/CLI0 and reviewed; normal comparison pending.
No host package installation, private credentials or live provider calls.

First selected realPG3 run is RED and preserved. Chromium2 completed real goal
writes, actual intake200/action-ID acceptance and existing screenshot comparisons,
but strict console guard caught missing dev-server public metadata404. Fix supplies
ONLY the public build-config port as200{} (explicit frame-free dev configuration),
never business/intake mocks or diagnostic filtering. Remote WebKit launched but
its compound30s deadline expired after two cold development page boots before
membership completed; actual API responses were all<254ms. Parent approved90s
ONLY for this extended multi-goal/real6.1s ACK case; per-action5s/global timeouts and
all assertions/guards remain unchanged. Full receipt-ID partition assertions are
now explicit. Affected realPG3 normal rerun awaits fresh named source lease.
Fixture cleanup after the first run: no frontend schemas,0other sessions in the
owned disposable database. Backend source hold released between browser batches.

Mascot source cause is separately established by Aquinas: six SVGs are static
derivatives with original animation style/class removed. Original native SVGs
already handle reduced motion. Sibling-only seven-file proposal is held until
this telemetry candidate freezes; then supported asset restoration and actual
production normal/reduced proof are required. No all-screen design compliance claim.

### Bounded browser/realPG acceptance END —11 November2026

New HTTP normals: Chromium2 CLI0 +remoteWebKit1 CLI0;3references reviewed. Actual
PG3 normal CLI0/2.3m, exact intake receipt partition/action-ID plus durable goal
writes/reloads and existing screenshots. The approved90s compound-case budget
allowed remoteWebKit1.1m; other/per-action limits and all guards stay unchanged.
Public frame-free dev metadata setup moved to the shared visual auto fixture to
avoid a new404 in all other local root scenarios. Business/intake APIs remain
untouched. Final shared-adapter Chrome normal1 CLI0 and e2e types/lint0. Whole
format0, actual contract drift0, font integrity0; no full unit rerun for test-only
adapter movement. See frontend/CLIENT-OBSERVABILITY-ACCEPTANCE.md.

OwnedPG schema[]/other sessions0, ownedPG+WebKit containers/network removed; named
backend hold END and browser/CPU END sent.475new unit-failure diagnostics were
moved with hashes to sibling unit-failure-artifacts/, not promoted as golden refs;
no visual integration reference was removed. Current snapshot freeze precedes
mascot asset restoration; the known globalRO and mandatory designv2 phase remain.
