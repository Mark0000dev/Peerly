# Operator support inbox, case and retained status history — Aquinas

START implementation now,10 November2026. This replaces completed OPS02/old FE065
assignments, not the lead's active FE065 acceptance. Parent owns Git/deploy; no
secrets, live private data/messages, subagents or staging mutations. Student bug
feedback preempts. Manual membership-verification UI is explicitly DEFERRED: no
public bypass or verification button, and changing a support status grants nothing.

## Exclusive files / current actual contract

Own ONLY NEW `src/app/screens/operator/support/**` and
`../docs/planning/operator-support-frontend-progress.md`. Halley owns every existing
operator file, shared routes/transport/session/authority/theme/generated contracts,
packages, `testing/**` and browser/PG leases. Do not edit student or FE065 files.
Export `OperatorSupport` from `support/operator-support.ts` once genuinely consumed;
lead will mount `/operator/support` lazily under the existing content QueryClient.

Actual TESTED backend head54:106paths119operations, raw enabled export
`/tmp/peerly-be07-head54-openapi.json`, SHA256
`4da93c8717724c4c4c8472c9ce6593e9fd2af3683f2c4e1e2968da2fa9a9e433`.
Lead reproduced exact bytes and generated `contracts/openapi.json` /
`src/app/api.generated.ts` canonically. Existing96path objects unchanged; only old
OperatorAction gains search_support_cases. Backend targeted150 passes, including
actual root/grant/audit/canonical/model/schema/export. Use generated DTOs directly,
no handwritten replicas, future endpoints, query weakening or production mocks.

## Product/design and actual operations

Use v2 M03 search/filter, M06 stored-record sections and MX responsive principles;
read their JSON and HTML under `/tmp/peerly-design-v2/peerly-design-package/`.
This is STUDENT SUPPORT intake, NOT M01 moderation triage or report cases. No
assignment, replies, severity, priority, AI, student-verification controls, totals,
photo approval or invented moderation workflow. No export CSS/internal selectors.

- GET `/api/v1/operator/cases`: OperatorSupportInboxResponse, metadata-only rows;
  actual optional query case_id, actor_id, topic, status, anonymous,
  received_from, received_before, cursor. Read exact generated bounds and model.
  max50 plus next_cursor; metadata_anchor is not a user-facing total or technical
  heading. Status semantics are current_at_each_request, not snapshot/commit order.
- GET `/api/v1/operator/cases/{case_id}`: OperatorSupportResponse; real topic,
  reply_address, literal message, optional details, nullable actor_id, receipt.
  Private content is not part of inbox rows; only explicit selection fetches it.
- GET `/api/v1/operator/cases/{case_id}/history`: OperatorSupportHistoryResponse;
  raw retained revisions/anchor_version/next_cursor. Preserve version/order/times,
  nullable changed_by_id/operator_access_version. No provenance reconstruction.
- PUT `/api/v1/operator/cases/{case_id}/status`: generated SupportStatusBody
  {status,expected_version}, CSRF/Origin/idempotency, returns SupportReceiptResponse.
  Actual SupportStatus values ONLY received/in_review/resolved. SupportTopic is
  cannot_sign_in/email_not_accepted/code_not_arriving/email_already_in_use/
  deleted_account/other. These are support status changes, never membership proof.

Implement the cohesive actual screen: bounded inbox + explicit detail/history +
explicit status form. Initially opening the inbox is one audited user intent;
search/filter submission is explicit (not per keystroke). No row/detail/history
fan-out, hover prefetch, auto polling or invented list endpoint. Link an actual
actor ID to existing `/operator/accounts?account=...`; missing actor is anonymous,
not a fabricated account. Other unknown references remain readable IDs.

## Authority, state and errors

Use the existing HttpClient/readJson/writeJson and public QueryObserver, one
inherited QueryClient. Canonical sessionOptions and current actual protected
responses are authority. No operator flag/student activation prerequisite/new
QueryClient. Reuse `../operator-authority` / `../operator-contract` if their real
interfaces fit; don't edit them, ask Halley for concrete shared changes.

All keys begin ['account',actor,'operator',...] with every actual query parameter.
URL owns filters/case selection/history-open and each separate cursor; forms own
only unsent drafts. Owner/filter/source changes reset incompatible cursor/intent.
401/403 from ANY child retires private operator siblings and prevents late reveal;
503 local,404 truthful,422 invalid cursor explicit reset. Avoid removal/refetch loops.
No mirrored response/role/error store or persistent private data. Render safe text.

Status change requires user confirmation and exact current receipt version. Never
retry automatically. Unknown outcome keeps original immutable body/key for explicit
same-intent replay or manual current-case check; current matching status alone is
not proof our mutation committed. Changed form/source requires explicit reconcile,
not silent overwrite. Actor change/logout/destroy retires private drafts/intents.
No content/reply addresses/signed data in ordinary logs, URLs or analytics.

## Code-first evidence boundary

Write production behavior + meaningful unit/integration definitions FIRST, then
report CODE COMPLETE with exact paths/known limitations. Cheap coherent compile/
lint allowed; no own unit/browser/PG runners until lead grants a resource lease.
No repeated95% loops, global matrices or RO investigation. Keep thresholds/guards.

Definitions cover metadata-only inbox, real filters/keyset reset, explicit lazy
content/history, empty/anonymous/registered/null provenance, literal raw text,
max50 continuation, local503/404/422, status CAS409/uncertain immutable replay,
401/403 sibling race/actor replacement,320/200 full labels/keyboard and no implicit
verification/reply/send. Every eventual browser scenario behavior AND screenshot.

Ask lead for finite local real-source cohorts before PG; no shared fixture edits
or real services. Lead owns seed/audit hooks and serialized browser/PG lease. Global
RO is a known internal exception, not fixed by scoped clean tests or suppression.

## Applied root integration —10 November2026

Actual lazy `/operator/support` uses public `canDeactivate` → `canLeave()` and
public custom `runGuardsAndResolvers` only when the selected `case` query changes.
This includes browser Back/Forward between cases without prompting for harmless
same-case history paging. Remove component pre-confirmation for the same navigation
so Router owns one decision, not two dialogs. Confirm actual Keep/Leave behavior
with Router/browser history, not configuration mirroring. Public source:
https://angular.dev/api/router/RunGuardsAndResolvers (stable, pinned22 router d.ts).

Shared `recheckOperatorAuthority(client,actor,currentActor,refetch)` takes actual
canonical session refetch; only successful unchanged-actor result removes captured
403 mutation identities/errors. New concurrent denials survive. Lead owns this
helper and existing entrypoints; status failures must be reported after canonical
MutationObserver settlement, not pre-state onError. No client operator flag.
