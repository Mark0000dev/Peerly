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

## SSE

One authenticated change stream carries bounded source/version hints, reset and
reconnect semantics. Never send private chat bodies or pretend stream delivery is
a peer-read acknowledgement. On reset/gap refetch current REST projections;
monotonic conversation sequence orders messages. Preserve cancellation,
backpressure, bounded memory and proxy streaming behavior.
