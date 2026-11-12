# Persistence and concurrency

PostgreSQL/asyncpg with async SQLAlchemy typed mappings is the sole business store;
private objects live in S3-compatible storage. Alembic revisions, not this prose,
are the exact schema contract. Application startup never runs create_all or seeds
implicit accounts/policies/roles. Review and explicitly apply migrations.

## Capability-owned data

| Records                | Durable facts                                                                                                                                              |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Identity               | Accounts, sessions, one-use Google transactions, institutional challenges/bindings, retained retired identity/mail associations and unique active claims   |
| Registration/reference | Immutable policy documents/display contexts/completion receipts and versioned broad knowledge-area catalogue                                               |
| Profile                | Profile/language/goal/help/photo revisions, current pointers, visibility/freshness/activation and owned immutable command results                          |
| Social                 | Canonical sorted account pairs, requests/previews/revisions/disclosures/view ACKs and acceptance-backed conversations                                      |
| Messaging/media        | Confirmed sequence, caller read position, goal shares, immutable operation results, upload/processing/display/retained image-report source facts           |
| Safety/support         | Blocks/reports, lifecycle revisions, manual membership provenance, human photo/report decisions, owned support/proof recovery and notification preferences |
| AI                     | Immutable typed job input/result/history, actor intents/budgets, attempts, singleton execution fences and report-evidence/submission sources               |
| Analytics/operations   | Canonical business events, typed client observations, metadata operator audits, delivery sources/outboxes/destinations/attempts                            |

## Transactions and constraints

Use one AsyncSession per task, explicit async transactions and expire_on_commit=False.
A writing use case owns atomic multi-source/state/event/outbox changes; repositories
do not commit independently. Keep external I/O outside SQL transactions and
recheck current permission/source after the wait. Read adapters must not mutate
through shared identity locks. Intentional read-route expiry/audit writes use a
writing unit, not a read-only workaround.

Database FKs, uniqueness and CHECKs enforce ownership, positive revisions, real
source references, active identity/mail claims and valid state. Cross-source
canonical pointers preserve original actor ownership rather than repurposing an
old FK. Deferrable source/event cycles are deliberate and tested on PostgreSQL.

Account-before-session locks and sorted social participants avoid inverse lock
orders. Pair/request/revision locks fence send/accept/withdraw/block/hide races.
DB clock supplies deadlines; effective finality does not wait for a cleanup job.
A retry key cannot change payload. An expired AI lease does not prove physical
executor death or permit another credential owner.

Cursor keys and hints are bounded and actor/purpose/filter/source-bound. Timestamp
and UUID pagination is not a commit-order snapshot. Refresh discovers late commits;
conversation sequence, not timestamps, orders confirmed messages. No N+1
projection or eagerly loaded unrestricted graph is required.

## Retention and operations

Soft deletion retains all business/media/analytics/audit history internally and
revokes old authority. A new registration creates a different account, preserves
retired associations and transfers no role/content/proof. No cascade purge,
anonymisation, fake-address rewrite or automatic mailbox reassignment.

Temporary auth secrets, OTP delivery envelopes, transport objects and native
workspaces have separate security cleanup. Hot telemetry expiry requires durable
archive handling and explicit loss evidence; retention is not an impossible
zero-loss guarantee.

Migrations are append-only once shipped. Test empty upgrade, real prior-head
upgrade, constraints/rollback and guarded downgrade in disposable schemas. Some
retained source/AI-guard facts deliberately forbid downgrade. Respect those guards:
prefer maintenance/forward fix, never purge/stamp or restore over newer history.
Back up and verify target database/head/ownership before explicit deployment.
