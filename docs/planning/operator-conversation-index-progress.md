# Retained account conversation index

State: locally mounted and targeted acceptance complete:23PASS14.74s (20unit+3actualPG). This is the next bounded developer slice after the accepted BE07 inbox/history batch. Main added the bounded bootstrap factory and root/export regressions. No migrations, schema registry, student logic, frontend, workflow, Git or deployment input changed.

## Contract

Factory route: GET `/api/v1/operator/accounts/{account_id}/conversations`, optional opaque `cursor` only. Root response is `account_id`, `conversations`, `next_cursor`. Each finite row contains exactly id, relationship_id, low_id, high_id, request_id and accepted_request_version. These are actual retained ConversationRecord participant/relationship/accepted-request references; no created_at exists and none is invented. No next_message_sequence, message count, body, identity/profile projection or delivery/view status is exposed.

UUID id DESC,50 visible plus one lookahead. Purpose-separated encrypted cursor binds current actual operator, grant version, requested account and last UUID. Ordering is not chronological or a commit snapshot; late inserts above a visited key require refresh. No offsets or totals. Both low/high participants are selected, independent of hidden, deleted, banned, membership or student activation state. Existing participant indexes suffice; no DDL requested.

Existing READ_ACCOUNT container audit records the actual requested account and that account only as the result, not a fabricated read action for each conversation. Missing account commits NOT_FOUND before404; known empty account commits READ. Use case checks explicit current operator/session first, verifies source membership/strict UUID order/bounds and performs final-session validation after mandatory audit. Both SQL read methods call inherited checked_access before database access. Audit/canonical/transaction failure prevents a result from escaping.

## Shared handoff

- `SqlOperatorConversationIndexUnitOfWork(sessions, record_operator_audit)` in infrastructure/operator/conversation_index_transactions.py.
- `FernetOperatorConversationCursorCodec.from_key(existing_envelope_key)` in infrastructure/operator/conversation_index_cursors.py; no additional settings/key.
- `ReadOperatorConversations(uow, hasher, codec)` in application/operator/conversation_index.py.
- `OperatorConversationIndexHttpServices(read)` and `operator_conversation_index_router(services)` in presentation/operator/conversation_index_router.py.
- Frozen finite DTO/query models in presentation/operator/conversation_index_models.py.

Noether mounted the factory after Halley explicitly ended the106-path fixture lease. Root lifespan tests and deterministic export regressions passed in the coherent23-case batch. Actual enabled-auth export is supplied by main; deployment is separate. No new role, search audit action or migration is needed. Manual verification UI/use case remains separate and deferred.

## Regression definitions and evidence

Owned unit definitions cover50+1 keyset, actual account-container audit, missing/empty source outcomes, cursor operator/grant/target/invalid-token binding, rejection of wrong-owner/unordered/oversized source results, ordinary/revoked/banned denial before queries, audit/final-session rollback and unguarded adapter rejection with an unbound real AsyncSession. Standalone ASGI unit adapter definition checks actual use-case cookie/grant gates, finite field projection and no-store; it does not claim root-bootstrap/lifespan integration.

Real PostgreSQL definitions use the existing actual request acceptance fixture and head migrations, then hide one participant through the existing visibility use case and retain a deleted counterpart. They inspect both actual low/high IDs, preserve request/accepted-version references and require real account-scoped audit/canonical records. A second real-PG definition checks audited missing/empty accounts and rollback after the real canonical audit recorder fails. No ad-hoc schema or mocked SQL is used.

Cheap coherent static boundary: Ruff check/format passed; strict mypy using explicit backend config, MYPYPATH=backend/src:backend and follow-imports=silent passed all11 new source/test files. No pytest, PostgreSQL, coverage, browser or provider run was performed. Main coordinates one targeted batch after reviewing the code-complete handoff; no per-file acceptance loop or repeated backend suite. No release/deployment or full-backend green claim.

Main acceptance receipt: `/tmp/peerly-operator-index-targeted.log` and matching XML record23PASS14.74s, including3actualPG cases. No full-suite/coverage/deployment claim. Canonical source static and actual export receipts follow in the main progress ledger.
