# API integration contract

The actual mounted OpenAPI schema is authoritative. Do not handwrite parallel
DTOs, copy prototype outcomes or infer UI capabilities from missing data.
Generate the enabled contract from backend without real credentials/network/DB:

```bash
uv run python -m studymate.export_openapi --output /tmp/peerly-openapi.json
```

The exporter uses synthetic configuration and deterministic app construction,
including configured routes. The health-only default schema is insufficient for
client generation. Generated clients must preserve closed/discriminated unions
and safe ProblemResponse errors; do not weaken schema checks to accommodate drift.

## Transport and intent

Serve client and `/api/v1` on the same HTTPS origin. Authentication uses a Secure,
HttpOnly session cookie. Browser writes also require trusted Origin and session
CSRF; idempotent commands require Idempotency-Key. Apply each operation's actual
body/content-type/time limits. Public/authenticated reads have deliberate cache
policies; private state and protected media use no-store.

A key binds an immutable actor/payload intent. Retrying an uncertain result keeps
the same key; changed resolved payload uses a new key. Versions/CAS come from real
server sources. Preserve conflict/current-state outcomes instead of silently
repeating a different command. Error bodies are sanitized and correlated; statuses
such as401/403/404/409/422/429/503 have operation-specific semantics.

Requests, chat text/images, deletion and uploads expose actual status/recovery
boundaries. Lost response is not failure; a cancelled operation can have already
completed. No frontend-generated receipt, quota, next-page tree or finality time.

## Capability surfaces

| Area               | Contract responsibility                                                                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Identity           | Google entry/callback/session, separate institutional challenge and completion, real registration context/receipt and policy status                                      |
| Profile/academic   | Own profile/photo/visibility, broad-area catalogue, goal/help revisions, activation and freshness confirmation                                                           |
| Discovery/Requests | Current relevance/eligibility, passes, exact profile disclosure, retained preview, reviewed send, participant lists/detail/explicit view acknowledgement and server Undo |
| Conversations      | Accepted context, current participant/avatar, ordered messages, explicit read position, goal sharing, image lifecycle and operation recovery                             |
| Safety/support     | Scoped block/report/deletion outcomes, owned support recovery, notification preference revision and truthful capabilities                                                |
| AI                 | Typed bounded student submissions/read/cancel plus distinct privileged report source/enqueue/read                                                                        |
| Operators          | Paginated retained sources/history/relationships/events/media with live role/session and atomic metadata audit                                                           |
| Observations       | Authenticated typed account-linked event batches with deduplication, bounded source frames and no arbitrary content                                                      |

Reads/polls do not acknowledge a human view or automatically confirm freshness.
Some reads intentionally retain audit/disclosure/expiry facts; do not assume GET
means a database read-only transaction. All current authority is revalidated.

## Operator retained identity links

`GET /api/v1/operator/accounts/{account_id}/identity-links` inspects one retained
account aggregate with the existing live operator role/session checks and atomic
`READ_ACCOUNT` audit. No student-facing identity access is granted. It returns
the target's stored Google and institutional claims, including retirement and
revocation facts, and at most50 distinct other accounts directly sharing its
stored Google issuer/subject or institutional email. Matching flags identify the
actual direct claim sources. Shared claims do not assert that accounts belong to
one person; no transitive identity graph or automatic merge is performed.

The opaque cursor binds the actual operator/grant, target, immutable target-claim
keys and fixed source-created cutoff. Accounts sort by created_at then UUID,
both descending. A newly added target claim invalidates the old continuation;
restart the read rather than silently changing its scope. Retirement, lifecycle
and returned claim metadata are current stored facts, not an historical database
snapshot at `as_of`. Deleted, banned and retired source records remain available
to the privileged operator. Empty existing accounts return200; absent accounts
are audited before404. Invalid cursors return422 and current authority failures
remain401/403. Private responses use no-store/no-referrer. No OTP, session/login
secrets, signed media ticket or inferred verification method is returned or logged.

## Photos and disclosure

A public Requests peer with a current photo_version may use existing
`GET /api/v1/people/{person_id}/photo/{photo_version}`. A retained request/disclosure
is not a photo grant. Both current actor/peer eligibility and block state are
checked before and after storage I/O; hidden/deleted/unavailable or changed peer
photo is not served. Do not recover masked identity from retained IDs.

Accepted chat uses its independent `/api/v1/conversations/{id}/participant` and
`/participant/avatar/{photo_version}` authority, including while hidden. This
supports current display only, not original/history/full-profile access. Private
JPEG responses use no-store/no-referrer/nosniff. Deleted peers remain neutral.

## Operator access history

`GET /api/v1/operator/accounts/{account_id}/operator-access-history` exposes the
actual saved operator-access revisions, including unused/revoked grants and
retained deleted-account sources. It never grants access or treats a historical
`active` field as current requester authority. Each page uses the existing fresh
operator/session checks and records one atomic `READ_ACCOUNT` inspection of the
target account aggregate. Existing unassigned accounts return an empty page with
anchor_version0; missing accounts are audited before404.

Pages contain at most50 revisions ordered by source version descending, not by
changed_at: historical timestamps may regress. A purpose-specific encrypted
cursor binds operator, current grant version, target account and fixed revision
anchor. Newer revisions do not enter an existing continuation. Invalid or
cross-scope cursors return422. Attribution and request/action/trace/span IDs are
returned exactly as stored; legacy nulls stay null. No grantor/session/action is
inferred. Audit failure, session expiry and cancellation never release the private
result; audit and canonical inspection writes share the read transaction.

## Operator email verification history

`GET /api/v1/operator/accounts/{account_id}/email-verification-history` returns
retained email challenges, optional stored delivery metadata and manual-verification
attribution through the current operator authority. Each read records an atomic
`READ_ACCOUNT` audit; deleted/banned target accounts remain inspectable. Missing
accounts return an audited404, existing accounts without challenges an empty page.
No verification, delivery or session mutation occurs. Codes, secret digests,
credentials and provider response bodies are excluded from the query and response.

Pages contain at most50 challenges ordered by created_at/id descending. Encrypted
cursors bind requester/grant, target and creation-time boundary. Later challenges
are excluded from continuation; mutable status fields are read fresh and are not
an historical status snapshot. Optional source relationships are returned only
when actually stored. A delivered status means SMTP acceptance, never proof of
inbox delivery. Origin request/action/trace/span IDs retain their stored nulls.

## Operator session history

`GET /api/v1/operator/accounts/{account_id}/session-history` exposes retained
session IDs, account IDs and issued/expires/revoked timestamps through current
operator authority with atomic `READ_ACCOUNT` auditing. Deleted/banned target
accounts remain inspectable; missing accounts return an audited404. No token,
secret digest or inferred active-session authority is returned, and no session is
created or revoked by inspection.

Pages contain at most50 sessions ordered by issued_at/id descending. Encrypted
cursors bind requester/grant, target and issuance-time boundary. Later sessions
are excluded from continuation; revocation metadata remains current, rather than
a historical snapshot. Logout/ban/account policies still determine actual access.

## SSE

One authenticated change stream carries bounded source/version hints, reset and
reconnect semantics. Never send private chat bodies or pretend stream delivery is
a peer-read acknowledgement. On reset/gap refetch current REST projections;
monotonic conversation sequence orders messages. Preserve cancellation,
backpressure, bounded memory and proxy streaming behavior.
