# Operator support inbox and history

State: code complete and accepted in the main-coordinated targeted BE07 batch; actual head54 export/hash handoff pending. Owner resumed work after the urgent identity-recreation interruption. No existing support/operator source, shared model, registration, bootstrap, identity/lifecycle, migration, pipeline or frontend file was edited by this slice.

Exclusive files are new `support/operator_inbox*` modules in each backend layer, matching new unit/integration definitions, and this ledger. Existing detail/status and student support endpoints are preserved. The new capability uses the existing explicit operator grant/session guard and same-transaction metadata audit, without a case restriction on global inspection.

## Exact internal implementation contract

GET `/api/v1/operator/cases`: optional exact case_id, actor_id, current status, topic, tri-state anonymous, aware half-open received_from/received_before, opaque cursor. Reject actor_id with anonymous=true. Metadata-only SQL selects case ID, nullable actual actor ID, topic, received_at and latest retained revision status/version/changed_at; private message/details/reply-address/proof columns never enter list results, including lookahead. Response `cases`, `next_cursor`, `metadata_anchor`, `status_semantics: current_at_each_request`. No totals, offsets, private content search, account inference or view state.

Page50 plus one lookahead, received_at/id descending. Inbox cursor binds actual operator/current grant, canonical query HMAC, first-page metadata time anchor and last key. The anchor is not a commit-order snapshot; refresh discovers late commits and status eligibility can change between requests. Actual row ordering, filters and bounds are validated before audit/return. Empty searches commit an honest SEARCH audit with no invented resource.

GET `/api/v1/operator/cases/{case_id}/history`: retained version/status/changed_at/changed_by_id/operator_access_version, version descending,50 plus lookahead. Root response case_id/anchor_version/revisions/next_cursor. Cursor binds actual operator/current grant/case and original anchor/before versions. Newly appended changes do not enter a resumed page; refresh sees the new head. Initial receipt has no fabricated operator; later revisions require the actual retained operator/grant. Existing READ_SUPPORT_CASE audit covers both returned history and missing roots, including exhausted empty pages. No intents, credential or private content fields are returned.

Both use cases require the existing operator guard and final-session check. SQL extends actual SqlOperatorTransaction, so the canonical audit and data read share one transaction; failure/cancellation cannot return data. No schema/model registration is introduced.

## Shared integration handoff

Noether owns migration0053, SEARCH_SUPPORT_CASES enum/search validation, immutable audit CHECK/canonical source mapping, registry/bootstrap/export and any new shared indexes. Parent confirms0053 is already LIVE and immutable on the operator branch; do not rewrite/reserve it anew. Current resumed tree retains that revision but lacks SEARCH_SUPPORT_CASES in domain/operator/audit.py; strict owned typing stops on that single missing shared symbol. This is an explicit dependency, not an invented fallback action.

Factories:

- `SqlOperatorSupportInboxUnitOfWork(sessions, record_operator_audit)` in infrastructure/support/operator_inbox_transactions.py.
- `FernetOperatorSupportInboxCursorCodec.from_key(existing_envelope_key)` in infrastructure/support/operator_inbox_cursors.py; separate inbox/history purposes, no new settings/key.
- `SearchOperatorSupportCases(uow, hasher, fingerprinter, codec)` and `ReadOperatorSupportHistory(uow, hasher, codec)` in application/support/operator_inbox.py.
- `OperatorSupportInboxHttpServices(search, history)` and `operator_support_inbox_router(services)` in presentation/support/operator_inbox_router.py.
- Explicit frozen DTOs/query parsing in presentation/support/operator_inbox_models.py use ordinary session-cookie reads and shared problem/no-store hooks. No write CSRF requirement is fabricated for reads.

Halley received these as authored internal contracts only: NOT mounted, NOT a validated public export, no new schema artifact SHA. Existing96/109 remains the frontend's stated consumed boundary until Noether provides an actual mounted/exported handoff. Existing support detail/status remains compatible. No frontend DTO or source was edited here.

## Regression definitions and verification

Definitions cover filter intervals/anonymous contradiction, finite metadata projection, actual revision/grant shape, cursor purpose/actor/grant/filter/case binding,50+1 boundary and UUID tie ordering, anchored history despite append, missing/empty audit, role/revoked/banned/expired denial before queries, audit and final-session rollback, source ordering/filter violations, and current status semantics. Real PostgreSQL definitions use actual head migrations and retained business fixtures,51 tied cases, deleted/banned retained actor,52 history versions plus actual status use case append, and real canonical-audit callback rollback. Root BrowserHarness definitions cover actual cookie authority, metadata/privacy projection and original audit/canonical refs. No ad-hoc schema or mocked SQL.

Resumed cheap coherent static boundary: Final Ruff check and format passed across all13 owned source/test files; the two known test issues (mutable-list narrowing and compound raises block) were corrected. Strict mypy checks all13 authored source/test files and reports only the missing shared SEARCH_SUPPORT_CASES symbol described above. No pytest/unit/coverage/PostgreSQL/browser run performed for this slice. Source is code complete pending shared dependency and coordinated targeted acceptance; no deployed/readiness/whole-suite green claim.


## Focused acceptance readiness

Parent requested one meaningful owned acceptance batch after Noether explicitly grants CPU/PostgreSQL and restores the shared source/mount boundary. The exact current shared symbol blocker is `application/support/operator_inbox.py:128`, referencing missing `OperatorAction.SEARCH_SUPPORT_CASES`; Noether has the precise enum/domain search-validation, immutable0053 ORM/audit/canonical mapping and root factory/export request. No independent bootstrap or schema mutation is authorised or performed. Current owned source and regression definitions remain complete.

Proposed single targeted invocation, from backend with Noether-provided disposable TEST_DATABASE_URL already configured: `.venv/bin/pytest tests/unit/support/operator_inbox_contracts_test.py tests/unit/support/operator_inbox_cursors_test.py tests/unit/support/operator_inbox_usecases_test.py tests/integration/support/operator_inbox_queries_test.py tests/integration/support/operator_inbox_composition_test.py --junitxml=/tmp/peerly-operator-support-targeted.xml`. No full suite, coverage gate, fixture capture or unrelated CI rerun is included. Unit helper operator_inbox_store.py is imported, not a test file. The existing engine fixture creates a fresh uniquely named schema per integration case, migrates actual head and drops only that schema at teardown; no shared database reset, create_all or ad-hoc product schema. No PostgreSQL run is started before the explicit lease.

Added regression definitions cover cancellation after audit admission and failure on unit-of-work exit/commit for both inbox and history, ensuring prepared data cannot escape and the fake transaction's audit rolls back. These complement actual PostgreSQL canonical-recorder rollback, not replace it. No test execution or passing-count claim accompanies these definitions.

After the targeted batch: retain command/status/JUnit/log evidence and any fixes truthfully, request Noether's actual mounted OpenAPI export/hash and hand Halley only the tested DTO boundary. Halley has already received the authored source contract and explicit NOT mounted/exported status. Manual verification remains a separate later capability; no public bypass or identity change is part of this slice.

Noether confirmed shared restoration is still paused while the urgent deployment-only manual helper is prepared;0055 is not reserved and053 remains immutable. No operator PostgreSQL/full checks are authorised yet. The cancellation/commit regression-definition addition is authored after the earlier Ruff pass and awaits the same coherent static/targeted boundary; the earlier pass is not claimed for these later edits.


## Restored shared source and frozen static boundary

Noether declared shared SOURCE_READY: SEARCH_SUPPORT_CASES enum/search validation and actual audit/timeline mappings restored, immutable0053 source constraints retained, and the new inbox/history plus eight existing reads mounted in bootstrap. This is code integration, not executed export/runtime acceptance; no migration or shared source was changed by this slice.

Authorised coherent static boundary completed: Ruff check/format pass and strict mypy with explicit backend config, `--follow-imports=silent`, and `MYPYPATH=backend/src:backend` passes all13 owned source/test files. The first resumed typing invocation supplied only backend/src and correctly rejected unresolved test-package imports; the explicit source+test roots resolved them without suppressions. Cancellation and commit-failure definitions are now included in the formatted/typed frozen boundary. No pytest/PostgreSQL execution was started.

Main will run one combined BE07 targeted batch after OPS02 releases CPU, including these five owned test files plus its shared schema/root/export regressions. Do not duplicate the owned batch separately. Actual tested DTO/export hash handoff to Halley follows that result. Owned source is frozen with a per-file hash manifest under `/tmp/peerly-operator-support-static-*`; the handoff records its exact path and combined source hash.


SQL boundary alignment requested by Noether: all three new adapter read methods now call the inherited `checked_access()` before any query. This reuses the exact existing actual-operator authority precondition, not a new permission path. A parameterized owned unit definition invokes each method with an unbound real AsyncSession and requires the authority error before any database/audit operation. Final scoped Ruff/format and strict13-file mypy pass after this change. No pytest/PG run occurred; the refreshed manifest supersedes the earlier853b source hash for the combined main batch.


## Coordinated BE07 targeted acceptance —10 November2026

Noether's single combined batch completed150/150 passing in37.65s, with zero failures/errors/skips in `/tmp/peerly-be07-combined-targeted.xml`; raw log `/tmp/peerly-be07-combined-targeted.log`. This includes all five owned inbox/history test files plus main's new retained-read root integration, actual canonical audit/search schema, pre-existing operator routes, timeline mapping, export and model-drift checks. Main reports no source drift and shared20-file static pass. The exact frozen owned manifest remains `/tmp/peerly-operator-support-static-4ub_rjaa/manifest.json`, combinedSHA `2d6cc6a596343f8db44be3b598c670251ee27b5f33790fd1a087a88dbaeaa475`.

Accepted boundary: actual root cookie/operator authority, discoverable metadata inbox/current-status filtering, stable keyset/anchored history sources, retained deleted/banned actors, original status grant provenance, mandatory audit/canonical rollback/privacy and finite DTO projection. Source-adapter preconditions and cancellation/commit failure definitions are included. This is targeted operator acceptance, not a new whole-backend/full-coverage green or live deployment claim. No duplicate pytest, database, provider or browser run was performed by this developer.

Source remains frozen while main captures artifacts. Noether is producing the actual enabled-auth head54 OpenAPI export and hash; Halley has the passing targeted result but must wait for that exact artifact before generating/consuming new DTOs.0053 remains immutable and no DDL or shared identity change was required by the new read capability.
