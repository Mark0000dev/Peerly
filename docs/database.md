# Pilot data model

## Knowledge-area semantics (approved 9 November 2026)

The MVP catalogue contains broad knowledge areas, not APU course enrolments or completed modules. Existing `subject`, `subject_id` and `help_subjects` names are stable wire/storage names for these areas. Selecting “can help” is self-declared; institutional email verification establishes membership, never expertise, course completion or grades.

A goal uses its chosen area plus optional `topic` (80 characters) and `context` (240 characters). A helper may select up to five canonical areas, each with an optional `topic_note` (80 characters). For example, choose Databases and describe SQL joins in the topic/note; IDB, SSCC or BMK2 may appear as optional task/module context. Helpers with workplace knowledge and students from other courses remain eligible under the same existing account/source/pair guards.

Discovery matches equal canonical area IDs. Different topics or module contexts do not prevent an area match; the literal same-topic hint does not certify competence. Different area IDs and free-form custom labels never become equal through matching text or AI advice. Custom goals remain supported but have no exact canonical match until explicitly changed by their owner. Aliases are true equivalent labels only, not course-to-area or technology-to-area mappings. Future course mappings/AI suggestions are advisory, never permission or verified qualification. No taxonomy graph, multi-tag expansion, API rename or migration is introduced.

Status: logical design, not migrations. Only the persistence base and isolated test model exist today. Product tables require reviewed SQLAlchemy `Mapped`/`mapped_column` models and Alembic migrations. This replaces the legacy group/session/streak model.

PostgreSQL is the only application database, accessed asynchronously through asyncpg. Use UUID resource identities, aware `timestamptz`, named constraints and explicit versions. Device timestamps are metadata, never ordering authority. Keep content relational; JSONB is for validated snapshots/event properties, not a substitute for constraints.

## Capability-owned records

| Records                                         | Key data and invariants                                                                                                                                        |
| ----------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `accounts`                                      | Stable account/analytics identity, separate institutional binding, visibility/restrictions, deleted_at and admin-ban metadata, version                         |
| `email_challenges`, `sessions`                  | Bounded attempts/expiry and revocation; keyed code verification and hashed high-entropy session/refresh secrets; no plaintext credentials                      |
| `registration_receipts`, `policy_notifications` | Actor, versions displayed at actual registration, registration action/time and update-notice history; no fictitious checkbox/optional opt-in                   |
| `profiles`, `media`                             | Required display name/photo; optional fields; file owner/purpose/processing state/object reference; no binary image blobs in account rows                      |
| `subjects`, `subject_aliases`                   | Owner-approved canonical catalogue and aliases; custom labels do not imply canonical equality                                                                  |
| `goals`                                         | Owner, stable ID, version, canonical/custom subject, optional topic/context, shared-learning choice, active/completed state; at most one active goal per owner |
| `help_subjects`                                 | Owner plus canonical subject and optional note, unique per owner/subject; configured maximum under account lock                                                |
| `discovery_passes`                              | Viewer, candidate, goal/context identity; private persistent pass and reconsideration state                                                                    |
| `relationships`                                 | Canonical ordered user pair, unique pair; stable serialization point for connection/request/block decisions                                                    |
| `requests`                                      | Relationship, direction/type, immutable goal snapshot/version, note, lifecycle timestamps and precise closed reason; at most one pending request per pair      |
| `conversations`                                 | Unique relationship, accepted request context, next message sequence; one persistent thread per pair                                                           |
| `messages`                                      | Conversation, monotonic sequence, sender, client message ID, text/processed media reference, stored timestamp; unique sender/thread/client ID                  |
| `read_positions`                                | Account/thread and monotonic acknowledged sequence; private unread state, not public read receipts                                                             |
| `blocks`                                        | Ordered blocker/blocked pair; unilateral removal only; effective permissions derive from both accounts and pair state                                          |
| `study_outcomes`                                | One current self-report per conversation/participant, plus revisions needed for windowed measurement                                                           |
| `feedback`                                      | One current record per reviewer/partner, eligibility evidence, Yes/Maybe/No, descriptors and private team note; history/moderation state retained              |
| `reports`, `support_cases`, `case_actions`      | Selected evidence references, private notes, status/ownership, decisions and audit history                                                                     |

Pending requests use a partial unique index on relationship where state is pending. Conversations use a normal unique relationship constraint. Goals use a partial unique owner index where active. Distinct partner feedback uses a reviewer/partner unique key and a no-self-assessment check. Foreign keys and checks complement use-case validation; cross-row limits need locking/transaction logic.

Snapshot text belongs to `requests`/conversation context. Editing/completing a goal cannot rewrite the original request. Share-current-goal creates an explicit context entry. Accepted connections remain stable through hiding/blocking; communication eligibility is derived rather than destructively deleting history.

Public reads exclude ineligible profiles. Privileged operator reads can inspect all stored application records, hidden/restricted records, conversations, attachments and links. Do not implement global ORM filters that unintentionally make privileged inspection impossible; authorization is explicit at each application query/command boundary.

## Transaction support and event records

| Records                              | Responsibility                                                                                                                                                                               |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `idempotency_results`                | Actor + operation + key unique, normalized payload hash, canonical outcome/resource references and completion metadata; prune cached response bodies without losing durable command identity |
| `domain_events`                      | Canonical committed business event ID/name/version, actor, resource references, bounded noncontent properties, action/trace context                                                          |
| `outbox_deliveries`                  | Event + destination unique, attempts, not-before, lease/expiry, terminal state and sanitized last error                                                                                      |
| `user_event_counters`, `user_events` | Per-recipient committed stream sequence and short-lived authorized change hints                                                                                                              |
| `analytics.events`                   | Canonical server events and separately marked client-observed events, event-ID deduplication, analytics identity, time, versioned allowlisted dimensions                                     |
| `audit_events`                       | Privileged reads/changes, actor, target references, timestamp, outcome and request/trace/action correlation; never inspected content                                                         |

These records have distinct purposes and retention: an SSE notification is not an audit record, an analytics row is not chat history, and a delivery lease is not business truth. Start with the primitives the first use cases actually require. Do not implement a generic enterprise event bus in advance.

A mutation stages its business updates, domain event, relevant per-user stream notifications and required outbox delivery tasks in the same transaction. Stage the canonical mandatory identified analytics record in that transaction too. External telemetry/exporter availability never controls business transaction completion. Purely diagnostic traces/logs use a bounded asynchronous exporter, not this transaction. No external provider acknowledgement is required to commit. Authentication delivery may require a short-lived encrypted code envelope; keep that separate from noncontent events, enforce expiry, and remove it after its delivery/retention window. Never persist plaintext OTPs in general outbox/analytics payloads.

Claim due delivery tasks in a short transaction using `FOR UPDATE SKIP LOCKED`, assign a lease and commit; perform network calls afterward. Persist delivery result in another short transaction. Expired leases are reclaimable; bounded exponential backoff and a terminal/dead-letter state make failures visible. Do not hold a SQL lock while waiting for Telegram/Umami/email. PostgreSQL documents SKIP LOCKED as useful for queue-like consumers. [PostgreSQL SELECT](https://www.postgresql.org/docs/current/sql-select.html).

Delivery is at least once. Consumers/destinations must deduplicate where possible. External services may not offer idempotency: an ambiguous Telegram send can duplicate an alert, and an Umami export retry can duplicate an event. Canonical conversion totals therefore come from deduplicated PostgreSQL events, not an assertion of exactly-once external delivery.

## Ordered cursors without commit races

Do not use an independently allocated global BIGSERIAL as a catch-up watermark and assume commit order: an earlier number can commit after a later one, causing a reader to skip it.

For stream notifications, stage a recipient-bound outbox reference to the canonical event in the business transaction. A short SQL-only publisher transaction claims committed references and assigns per-recipient delivery sequences under recipient-head locks acquired in stable UUID order; it commits journal entries and published outbox markers atomically. Delivery-head locks stay out of account/relationship business transactions. A source that commits late is picked up on a later publisher pass and receives a later delivery sequence, irrespective of its source timestamp/UUID. This follows the concrete BE-06 transport contract. The cursor `(recipient, sequence)` orders committed delivery-index entries, not business events. Retention pruning preserves the head and expired-through reset watermark; canonical outcomes and business history are never purged as transport hints.

For messages, increment a per-conversation sequence under the relationship/conversation transaction lock. Keyset pagination and unread positions use this ordering. Do not use device clocks or a globally allocated identity as conversation ordering.

Outbox task claims do not need this ordered cursor: they select currently visible due rows using state/lease indexes and can revisit delayed commits on the next pass.

## Critical concurrency cases

| Race                            | Database/application guarantee                                                                              |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Duplicate send                  | Idempotency result and client intent identity return the existing result                                    |
| Opposite sends                  | Unique canonical relationship and serialized pending-request check; second sender sees incoming interest    |
| Accept versus withdraw          | Pair lock decides one valid transition; losing action receives actual terminal state                        |
| Send versus hide/block/restrict | Stable account-then-pair lock order; eligibility rechecked within the write transaction                     |
| Concurrent sends near a quota   | Account/day counters or locked owner state updated atomically, not counted outside the transaction          |
| Duplicate message               | Sender/thread/client-message uniqueness, independent of temporary response-cache retention                  |
| Goal change during preview      | Referenced owner/version/active state checked before snapshot commit                                        |
| Feedback update/removal         | One latest eligible record per distinct reviewer; aggregate recalculated with full Yes/Maybe/No denominator |

Use database time for deadlines and one documented pilot timezone (`Asia/Kuala_Lumpur`) for calendar-day quotas. Lock ordering, deadlock retry policy and transaction isolation must be verified with concurrent integration tests, not just sequential examples. Retry only safe whole units of work with stable idempotency; never repeat external sends as part of a transaction retry.

## Read and analytics models

Start with indexed SQL projections in the same managed PostgreSQL cluster. No separate read database or graph database is needed for the pilot. Add workload isolation/replicas when measured.

Operational indexes follow actual access: pending incoming/outgoing requests, eligible discovery subject/visibility, recent conversations, thread sequence, unseen counters, due deliveries and analytics actor/time/event. Use EXPLAIN on representative data. Avoid caching access decisions that can outlive a block/hide/restriction.

A privileged resource explorer traverses explicit foreign-key/typed reference edges: account → goals/requests/relationships/conversations/messages/media/outcomes/feedback/cases/actions/events/audit, and reverse links. Bound and paginate traversal; do not eagerly join the entire graph into one giant response.

Grafana product dashboards query stable `analytics` views, not Umami's internal database schema or arbitrary joins over private messages. A read-only datasource credential prevents accidental writes and bounds dashboard workload; it does not introduce per-developer dashboard restrictions. Full business records remain available through the privileged operator interface.

## Data lifecycle and operations

Owner policy: retain all accumulated business/media/analytics/audit history. Self-service deletion is soft delete: revoke sessions, close pending contact and remove ordinary visibility; preserve internal identity/relationships and block automatic recreation. Hidden profiles keep existing chats working. See approved product decisions for lifecycle semantics. No automatic business-history purge or anonymous unlinking.

Telemetry/event retention proposals live in [observability](observability.md). Event/action IDs can remain as references after a trace expires; the operator UI must show the actual availability of each data source. Backups have their own retention and access policy.

Production app and migration credentials are separate. Use verified TLS and provider-supported connection settings. Account for API pools, worker pools, listener connections, migration jobs and dashboard queries in the managed connection budget. LISTEN needs a direct/session-pooled connection or polling fallback; do not assume transaction-pool support.

No application `create_all`, no automatic destructive migrations, no SQLite integration substitute. Validate migration upgrades and the race table on real PostgreSQL. Production backups/PITR, media backup and a tested restore procedure are required deployment work, not implied by the managed label.

## AI durability extension

Implement in BE-03: `ai_jobs` and bounded attempt records, an executor singleton/lease generation, atomic global/class/actor admission counters and persisted submission budgets. Job ownership, source version, prompt/schema/model versions, deadlines and conditional terminal writes are required. Private snapshots/results are retained business data, not outbox/log content; temporary execution files still require cleanup. No running inference holds a SQL transaction. See [AI queue and recovery contract](ai.md); queue implementation is not part of BE-01 beyond the separate minimal email outbox.

## Revised identity binding

Google login requires `external_identities` unique by issuer/subject and short-lived one-use browser login transactions. Accounts may exist before institutional verification. Store a separately unique institutional verification binding with verified time; Google email is provider metadata, not the account linkage key. Challenges are owned by the authenticated account and attach membership atomically, never create login sessions. No automatic email-based merging/reassignment. See [BE-01](planning/epic-be-01-identity.md); this supersedes earlier institutional-email-only account assumptions.

Deleted-account filtering is explicit at ordinary application boundaries, not a global ORM filter hiding data from operators. Keep issuer/sub and verified-address uniqueness across deletion. Account deletion/ban versus send, callback, verification, AI completion and stream emission requires stable account locks and concurrent integration tests. Retained content and analytics must remain byte/relationship-equivalent after deletion; no ON DELETE CASCADE or purge task may erase that history.

## Confirmed image-report evidence — head49

`message_report_contexts` retains a server-issued accepted-participant reference to one actual confirmed message and its exact image/version/processing attempt. The owned eight-field message FK and canonical conversation-pair FK prevent swapping another preparation, author or rendition into that evidence. Contexts retain only identifiers, timestamps and actual execution origin; they copy no private message body, media hash, storage key or signed capability. Issuance does not grant future authority: submission rechecks the current actor, accepted membership and actual unchanged source. Existing peer visibility or later peer lifecycle changes do not replace that historical participant authority.

The historical table name `profile_reports` now denotes the unified report root. An explicit `kind` CHECK selects either its existing owned profile-context FK or its new owned message-context FK, never both or neither. Existing rows are truthfully classified `profile` from the old structural schema. The existing actor/key intent registry, shared reporter10/hour budget and `report.created` canonical journal remain authoritative across kinds. No second report stream or fabricated profile/photo revision is introduced. The existing operator timeline's technical source label `profile_report` remains the historical unified root locator; actual report evidence kind/context must be read from the report itself.

All report/context/comment and source history remains retained after soft deletion. Downgrade refuses to discard retained message-report contexts or new-kind reports; it does not anonymize or purge them to make a migration pass. These statements describe local schema/source behavior, not an applied staging migration or deployed service.

## Post-head50 student runtime/support candidate

Revision0051 adds readiness facts to the existing `ai_executor_slot`: actual runtime owner/state, start/heartbeat/fixed15-second validity and exact model/prompt/schema/adapter. Default stopped/null facts do not enable old rows. Expired readiness never releases physical execution capacity or permits takeover; blocked uncertainty retains ownership until explicit confirmed-stop recovery.

Revision0052 adds retained `notification_preference_revisions`/`notification_preference_intents` and `support_proofs`, `support_preparations`, `support_cases`, `support_case_revisions`, `support_case_intents`, `support_operator_intents`. Preference versions use the actual account lock; support uses dedicated hashed proof/source budgets, private origin references and real operator/grant-bound status revisions. Canonical event source FKs/checks and existing operator inspection CHECK are extended in the same revision. Anonymous cases are retained business sources without invented accounts. Downgrade refuses to discard populated support/preference records or support inspection history.

These revisions pass local head52 schema roundtrip/normalized CHECK drift and affected historical retention tests in the final batch/follow-up; parent has applied only the earlier immutable head50 to real staging. No second journal, native push transport or account reassignment is introduced.
