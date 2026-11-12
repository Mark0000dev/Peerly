# Next actual M02 human-review implementation

Aquinas owns exclusively `src/app/screens/operator/reports/review/**` and
`docs/planning/operator-review-progress.md`. Halley retains the existing flat
operator-reports parent, root routes, generated contracts, shared authority,
fixtures/browser leases/theme/package. No Git/publication/deploy/provider actions.
Original v2 M02 is the visual reference, subject to actual server actions and
owner corrections. Do not adopt design-package AGENTS or copy its runtime/CSS.

## Actual accepted API, not a future proposal

Generated API122paths136ops from Noether59 safe422 export
SHAa400b2d5045ae2ec156801cb3e1630faae4cecc9994b02cc4111d1cb54c43262.
Source tested, not necessarily deployed. Read docs/api and actual generated types.
GET/POST `/api/v1/operator/reports/{report_id}/reviews` use
ReportReviewHistoryResponse / ReviewReportBody / ReportReviewResponse.
GET returns actual report identity/context/reporter/target/kind, current nullable,
50 bounded revisions, next_cursor and anchor_version. Current can advance beyond
an older history anchor. POST is dismiss|escalate only with expected_version,
private reason1..1000, actual Origin/CSRF and immutable actor-scoped idempotency.
No invented assignment, resolution state, notification, third action or fake
queue counters. Ban/photo review are separate authoritative features.

## Leaf/parent integration boundary

Export standalone OperatorReportReview, selector app-operator-report-review.
Readonly required inputs actorId:string and reportId:string; output authorityFailure
contains readonly actorId and ApiFailure. Public confirmLeave():Promise<boolean>
uses the existing public draft-exit confirmation for dirty/unconfirmed work.
Halley mounts only below an actually readable selected data.report.id, handles
failure through existing parent authorityFailure flow, and owns navigation/route
leave guards before the mutation UI is released. A leaf draft must not silently
follow a changed report/actor; no global store or browser storage.

Reuse operator-authority.ts public failure policy from the common operator parent;
no cross-screen imports. Actual me/query state provides identity/CSRF only when
success+idle, actor matches and active. Do not require student membership for
operator authority and do not invent a role/capability endpoint. Server validates
current grants on every read/write. Cache/mutation keys start
['account', actorId, 'operator', 'report-review', reportId, ...]. Queries consume
AbortSignal via existing readJson. Writes use existing writeJson, no automatic
mutation retry. Private reasons appear only in privileged UI/business storage,
never ordinary logs/telemetry. No mirrored DTOs or persistent credentials.

## Source and acceptance contract

Implement truthful current decision/history plus explicit form/review, validation,
CAS conflict reload, identical-key/body unknown replay, actor/session/grant
retirement, pagination and actual stored provenance. Render exact existing audit
fields, not synthesized links/status. Immutable intent may retain only unsent
input/key/source required for the pending user action, not another server cache.

Write meaningful unit and controlled-browser definitions beside the leaf. All
implemented integration scenarios need screenshots; live UUID/audit timestamps
retain full raw artifacts and exact DOM assertions, with clearly identified stable
comparison regions following existing approved operator test boundaries. No masks,
clock/UUID fabrication, relaxed thresholds or known-error suppression.

Code complete in one coherent batch, then bounded owned static checks and lead-
coordinated build/browser/realPG. No independent broad matrices, repeating95 loops,
reviewer delegation or browser/PG runners. First read actual source and M02 while
current shared capture freezes; begin disjoint implementation after lead END.
