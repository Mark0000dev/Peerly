# FE03.5 setup completion and visibility scenarios

Actual generated API67 retains unchanged setup/registration/visibility contracts.
The core and recovery boundary13 scenarios passed39 normal project cases;69 PNGs
reviewed. Real activation core6 and Offer-help3 normal cases passed in fresh isolated
schemas,33 reviewed PNG comparisons. Current full frontend unit checkpoint is851
passing above all95% thresholds; this does not replace missing scenario coverage.
Four additional recovery cases passed candidate12 and normal12, with18 reviewed PNGs; see below. No global runtime waiver.
Every browser scenario needs behavior and named PNG assertions in all three projects.

| Scenario                     | Behavioral boundary                                                                         | Full-stack requirement                                       |
| ---------------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Explicit entry               | No extra background readiness/context calls until setup entry opened                        | Real incomplete student projection                           |
| Missing saved requirements   | Exact server requirement labels; genuine editor outputs; cannot complete                    | Name/photo/context branches derived by actual server         |
| First task                   | Draft survives transient refresh; save CAS preserves unrelated profile fields               | Find/offer save and reload                                   |
| Task save unknown            | Immutable body/key retry; no automatic retry; canonical reload discards only explicit draft | Server accepted response lost                                |
| Ready unregistered           | Issued notice/versioned Terms+Privacy links, no checkbox/modal; explicit completion         | Actual context issuance, receipt and durable activation      |
| Expired context              | Refresh actual context; no stale auto-completion or fake receipt                            | Server expiry/conflict where controlled clock permits        |
| Registered legacy incomplete | Existing receipt context completes durable setup; no reacceptance                           | Existing receipt + completed real prerequisites              |
| Receipt/network ambiguity    | Same immutable completion intent; destination session authoritative                         | Response lost after transaction then exact replay            |
| Concurrent readiness change  | 409 server requirements shown/refetched; no client activation                               | Photo/study context changed between readiness and completion |
| Manual hide                  | Server CAS/version+idem; canonical invalidation; existing-chat capability truthful          | Hide/read/restore; no chat freeze                            |
| Freshness pause              | Inline functional notice and explicit Show my profile again only when server allows         | Real inactive account; GET/callback/replay never confirms    |
| Missing restore requirements | Server requirements shown; no implied unhide/activation                                     | Photo/study context restoration requirements                 |
| Visibility unknown/conflict  | Same intent retry; explicit canonical reload for stale version                              | Lost committed response and stale CAS                        |
| Account/logout isolation     | Old drafts, contexts and owned mutation payloads cleared; stale callbacks ignored           | Two distinct real sessions where necessary                   |
| 401/403 recovery             | Parent exits setup before session refresh; no context remount loop                          | Revoked or no-longer-verified real session                   |
| Layout/accessibility         | 320px, 200% font increase/restore, keyboard radio/action traversal, no overflow             | Boundary visual assertions plus real route smoke             |

No requests CTA, analytics implementation, account deletion UI, AI executor UI or new API.
No screenshot tolerance/mask changes. No native observer patch. Fixtures use actual use cases,
DB time and isolated schemas; no guessed lifecycle rows or provider calls.

## Supported layout decisions

TuiForm supplies native fieldset appearance and control size. Its generic10rem
fieldset track became320px at200% text, exceeding the240px available inside320px
viewport padding. The owned one-column task-fields layout uses minmax(0,1fr) and
min-inline-size:0; no border or control styling override. The parent implicit auto
grid then measured317px from intrinsic controls, extending to357px; the owned
main/section tracks now explicitly shrink with minmax(0,1fr). Public TuiLink
actions wrap their labels; the submit label is concise Save task. No clipping,
font reduction, magic offsets or observer change. Native radio name enables real
keyboard grouping. Reflow and keyboard3 passed all projects after those fixes.

Registration intent captures the reviewed saved first task. Context preparation
checks actual account-owned readiness again after task mutation settles; readiness
becoming ready during the save must not leave Continue blocked forever. A real
HTTP-observer unit regression covers that transition without auto-registration.

## Accepted real Offer-help path

Explicit first-task change Find help to Offer help uses a fresh setup-offer actor:
actual photo/help save, task CAS, issued context after mutation settles, explicit
completion and durable reload without a goal. Fresh HEAD40/public60 D03 candidate
3/3 passed42.2s, all9 PNGs reviewed; normal3/3 passed41.4s/runtimeCLI0/nine comparisons.
Both lease-specific READY/START/END and fixture/schema/TLS cleanup completed.

## Accepted additional recovery scenarios

- Unknown task write keeps the exact body/key and unrelated profile fields on manual replay.
- Task CAS conflict keeps the choice until explicit canonical reload; no automatic overwrite.
- Readiness409 after issued context renders actual photo requirement, blocks local activation and does not issue a new context automatically.
- Registered incomplete setup presents its existing receipt without a new notice/reacceptance or automatic completion. Historical receipt completion command is covered by its real component unit; no fabricated legacy database state is claimed.

These actual-boundary additions passed candidate12/12 in28.4s and normal12/12 in22.9s, both runtimeCLI0; all18PNGs reviewed/compared. Raw logs /tmp/peerly-fe035-task-recovery-{candidate1,normal1}.log. Total boundary acceptance is17scenarios/51normal project cases across scoped runs, not a new whole-suite/global run. Browser resource remains
serialized with D03. Remaining matrix requirements must not be inferred complete
from aggregate coverage or screenshots of a different scenario. No ResizeObserver
or full-app gate acceptance follows from the accepted scoped runs.

## Accepted real visibility ambiguity recovery

A dedicated verified student completes real name/photo/goal/registration first.
The visibility command commits before its response is deliberately lost. An
independent real GET proves the hidden projection already equals the durable
receipt; manual retry retains the exact original body/key and returns that same
receipt. A separate explicit restore then succeeds. No automatic retry or optimistic
server mirror is used. Candidate3 and clean-source normal3 passed all three projects
inside the actual64/head41 lead12-case gates; all9 new PNGs were reviewed and normal
comparisons passed without updates. Raw `/tmp/peerly-discovery-visibility-pg12-normal2.log`.
Other pending matrix rows remain outstanding; no global/runtime waiver follows.
