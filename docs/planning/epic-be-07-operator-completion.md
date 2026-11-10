# BE07-O1 — Complete retained inspection and discoverable support intake

State: implemented_pending_external_validation,10November2026. Coherent targeted150PASS37.65s (136unit14actualPG), scopedstatic/architecture pass; actual tested export106paths119operations. Parent publication/deployment and frontend consumption remain separate. This is development work, not a
review/audit-agent assignment. Owner has reopened operator completion while the
team manually enrols and tests the deployed student product. Preserve student
logic and Nash's accepted native AI runtime unless a concrete bug is reported.

## Authoritative starting point

Owner reports canonical backend CI951 successful and core a74 digest live,
frontend40bf/e03 live, AI policy95d2/5b9 live; all three actual typed native tasks
and managed refresh passed, durable runtime readiness is fresh and singleton
slot free. These are owner-reported external milestones, not newly run local
checks. That initial onboarding inventory is historical. The current parent-reported
manual staging receipt records four explicit memberships; see the progress ledger.
No new full suite is needed to describe or start this bounded epic.

Source inspection of `bootstrap._operator_routers` and
`_student_support_routers` is authoritative over old “unmounted” ledger entries.
Mounted: account search/detail, conversation messages (including retained image
IDs), canonical event search/detail, audit detail, reports list/detail, raw
profile/help/goal histories, profile-upload metadata/history/original/display
binary, retained AI jobs/detail; operator support detail and status mutation;
admin ban/unban remains in the lifecycle router. Authority is an explicit current
DB grant and live Google-linked session, independent of student activation.

Previously source-complete factories, now mounted and covered by O1 acceptance:

| Factory | Existing application/infrastructure boundary | GET count |
| --- | --- | --- |
| `operator_request_router` | `connection_requests.py`, `request_ports.py`, `request_transactions.py` |2|
| `operator_disclosure_router` | `request_disclosures.py`, `disclosure_ports.py`, `disclosure_transactions.py` |1|
| `operator_chat_image_router` | `chat_image_uploads.py`, `chat_image_ports.py`, `chat_image_transactions.py` |2|
| `operator_feedback_router` | `peer_feedback.py`, `feedback_ports.py`, `feedback_transactions.py` |3|

The O1 root composition and export tests now verify these eight public mounts. Reuse their
actual factory/service/cursor types; no replacement DTOs, renamed source tables
or extra business writes. The prior schema was96paths/109operations; the tested composition handoff is now106paths/119operations, SHA256 `4da93c8717724c4c4c8472c9ce6593e9fd2af3683f2c4e1e2968da2fa9a9e433`. No frontend guesses these routes.

## Concrete remaining backend capabilities

1. **Locally completed:** the eight existing retained reads above are mounted.
2. **Locally completed:** support inbox/search and raw paginated status history
   are mounted. Existing detail and status mutation remain unchanged.
3. **Missing:** participant/conversation lookup and typed reverse resource edges,
   exact message/operation/action lookup, paginated inspection-audit search. Event
   search/audit detail and account source links exist, but do not implement the
   planned `/resources/{type}/{id}/relations`, `/actions/{id}` or audit list.
   Define each finite source contract before implementing; no arbitrary SQL,
   eager universal graph, invented counts or content fulltext search.
4. **Missing:** privileged retained chat-image binary inspection. Existing
   operator chat-image metadata is not a binary grant; profile-media reader is
   deliberately profile-only. Existing student image readers retain their guards.
5. **Missing:** internal report-triage admission/permission/selected-evidence,
   operator-only result integration and runtime acceptance. Queue enum/reserved
   capacity and report reads exist; they do not implement this fourth AI scenario.
   Schedule separately with an exact source contract; do not edit the accepted
   student native runtime as part of this epic.
6. **Missing separate bounded contracts:** operator grant/revocation provisioning
   tooling and retained lifecycle/relationship/preferences/outcome detail beyond
   current projections. No default grant or role-management HTTP exists. No
   speculative suspension, account reactivation or email reassignment is allowed.
7. **Not implemented by current read APIs:** human report/photo-review workflow
   and required approval-after-replacement source facts. Ban/unban is implemented;
   a ban endpoint does not itself supply a photo review state machine. Clarify
   actual transitions/evidence before that later epic, never invent moderation
   case states by reusing support statuses.
8. **Operational/integration, parent-owned:** durable support-triggered Telegram
   notifications, telemetry/archive/dashboard navigation and actual operator role
   provisioning. The one team announcement is not a support-notification worker.
   External Grafana access never creates an application grant.

This is a source-based remaining list, not a declaration that every possible
business table needs an independent generic endpoint. New route families remain
bounded, justified by actual operator tasks and approved exhaustive access.

## Outcome and exclusions

An authorised operator can find a submitted support case without direct DB
access, inspect its retained status changes, and navigate the already implemented
retained Requests/disclosures/chat-image metadata/feedback through actual APIs.
Student/anonymous support creation, ownership, status mutations, AI execution,
chat policy and live credentials remain unchanged. No assignment/replies,
moderation case merge, Telegram send, AI triage or private media broadening.

## O1.1 — Mount the eight existing reads (Noether)

Compose each existing SQL UoW with core sessions and required
`record_operator_audit`, existing session hasher/fingerprinter and per-capability
Fernet cursor codecs from the existing envelope key. Add factories in shared
bootstrap; no dependency/config/model/DDL change is expected for these reads.
Existing bounded pages, actual account-container audit, retained source facts,
late-commit/keyset limitations and no fake attachment proof remain authoritative.

Write root integration/export regression definitions covering ordinary403,
current explicit grant200, retained deleted/hidden targets, real canonical audit,
foreign child404 after audited parent and failed audit/final-session rollback.
Publish the actual new OpenAPI only after the coherent batch. Do not claim the
old96-path export has these routes. Coordinate frontend fixture stability before
changing active composition; parent handles deployment.

## O1.2 — Support inbox query (Plato)

Implement NEW `operator_inbox*` modules only under existing
`domain/support`, `application/support`, `infrastructure/support`,
`presentation/support`, and NEW matching support tests. Keep existing support
source files untouched unless main explicitly requests a tiny shared adapter.

Proposed actual route to be implemented: GET `/api/v1/operator/cases`.
Frozen filters: optional exact `case_id`, `actor_id`, `topic`, `status`,
`anonymous` boolean, and aware half-open `received_from`/`received_before`.
Reject contradictory `actor_id` plus `anonymous=true`; no raw reply-address,
message/details search, arbitrary sort or client-supplied operator identity.

Read real `SupportCaseRecord` joined to MAX actual `SupportRevisionRecord.version`
per case. Root metadata only: case ID, nullable actual actor ID, topic, received
at, current status/version/changed_at. No message/details/reply-address/proof
bytes, tokens, private query terms or invented “viewed” state in the list. The
existing audited detail GET remains the deliberate private-content inspection.

Order `(received_at DESC,id DESC)`,50items plus one lookahead, opaque cursor bound
to actual operator/current grant, canonical filter fingerprint, first-page
metadata time anchor and last key. No total count, offsets, commit-order or exact
snapshot claim: late commits above the visited keyset require refresh; mutable
status filters describe current facts at each request. Use explicit public DTO
names reflecting those semantics. No status transition as a side effect of GET.

New use case `SearchOperatorSupportCases` uses a new narrow UoW/transaction port
extending existing `OperatorAuditTransaction`. Reuse `require_operator` and
`finish_operator`; `SqlOperatorTransaction` supplies actual account/session/role
locks and checks. Do not infer authority from proof/student activation/email.

## O1.3 — Support status history (Plato)

Proposed route: GET `/api/v1/operator/cases/{case_id}/history`.
Read only retained `SupportRevisionRecord`: version,status,changed_at, nullable
real changed_by_id/operator_access_version. Initial version1 is received with no
operator; later revisions retain their real grant source. Do not turn historical
grant provenance into current permission or infer message delivery.

50+lookahead descending version keyset, anchor first-page MAX stored version,
opaque cursor bound to actual operator/grant/case and anchor/before version.
Root must exist before calculating history; missing root commits an existing
READ_SUPPORT_CASE/NOT_FOUND audit before404. Existing case returns READ audit even
for an exhausted empty page. Never return raw intents/credential/proof metadata.
Use `ReadOperatorSupportHistory` with a narrow typed read port; do not reuse the
mutating status intent path or lock unrelated target accounts out of order.

## Shared audit/DDL dependency (Noether; shipped0053 is immutable)

Support search requires an honest SEARCH audit, including empty results; do not
fake READ of an arbitrary account/case or skip audit on zero results.
Add `OperatorAction.SEARCH_SUPPORT_CASES = 'search_support_cases'`, resource kind
already `SUPPORT_CASE`, max50 result refs, no requested ref, existing32-byte HMAC
query fingerprint. Extend domain search validation, immutable audit CHECK/model,
canonical source validation and operator timeline result mapping. Reuse the
single `operator.inspected` timeline; no second stream/journal/new role.

Migration `0053_operator_support_search` was shipped before the identity hotfix0054 and is immutable. It extends
only the real audited-search constraint(s) and justified indexes from actual
query shape. No source history purge/rewriting; downgrade refuses retained new
search audit facts rather than silently losing them. Main owns registry/shared
models/enums/canonical/bootstrap/export; Plato must not add an Alembic head or
register conflicting models. SQL runtime/PG tests wait a coherent0053 source+DDL
checkpoint; pure contracts/fakes/HTTP factory can be authored first. Do not wire
an enum/runtime writer before matching DDL exists in active fixtures.

Concrete reused files:
`application/operator/{authority,ports}.py`,
`infrastructure/operator/transactions.py`,
`domain/operator/audit.py`,
`infrastructure/support/{models,operator}.py`,
`presentation/browser.py` (`read_cookie`, `SESSION_COOKIE`), shared operator
problem/privacy hooks. Main composes the new narrow read UoW and mounts factories
with existing secrets/settings; no new settings or production defaults.

## Acceptance and batching

Write meaningful regressions alongside implementation, then one coherent scoped
static/unit/real-PG/root/export batch for this epic. No repeated whole backend,
per-file coverage chase or provider/browser loops during implementation. Preserve
strict95% overall gate, warnings, cancellation and existing timeouts. Read-only
operator commands need session cookie; no fake Origin/CSRF write requirement.

Required cases: anonymous authenticated and retained deleted/banned submitters;
50+1 pagination and exact boundary ordering/filters/cursor binding; all raw status
versions despite changed current state; live operator/no student prerequisites;
ordinary/revoked/expired/blocked-role denial; no returned data on audit/canonical/
commit/final-session failure, cancellation rollback, audited empty search/miss;
no private content in list/cursor/ordinary telemetry; schema drift and reversible
migration without discarding retained facts. Existing student support detail/
status/creation APIs remain compatible. No live messages, credentials, AI turns,
Git/publication/deploy actions by developers.

## Ownership and next action

Noether: O1.1, shared0053/audit integration, main progress, schema/composition.
Plato: O1.2/O1.3 NEW `operator_inbox*` source/test files and
`docs/planning/operator-support-progress.md`; no existing support/operator/root
files, shared source or migrations. Nash: runtime remains frozen; no assignment
as reviewer or speculative parallel feature. Halley: current accepted operator
frontend consumers; receives only actual tested export handoff, not this proposal
as a pretend live contract. Parent: source publication, staging/monitoring and
real team feedback.

Current: Plato authored inbox/history, Noether restored shared action/validation/maps
and mounted all ten reads in source. Existing immutable0053/currenthead54 need no
new DDL; the coordinated batch passed150cases and actual export was handed to Halley. Operator roadmap history is retained in the earlier BE07 epic;
this document is the current bounded execution contract.
