# Two-sink HTTP handoff

Caller constructs `ExternalHttpSender(tuple_of_configs, transport)` implementing
the actual `ExternalSender.send(DeliveryLease) -> DeliveryResult` protocol. Use an
owned `httpx2.AsyncHTTPTransport(retries=0, trust_env=False,
limits=httpx2.Limits(max_connections=1, max_keepalive_connections=1))`, retaining
normal TLS verification, then `await transport.aclose()` on worker shutdown.
Tests inject MockTransport only. No SQL/session, environment, credential file,
login or provider availability probe is used inside these adapters.

Configs are frozen UmamiConfig(destination, origin, website_id) and
TelegramConfig(destination, chat_id, operator_origin, token=None, topic_id=None).
Origins require HTTPS with no path/query/fragment/userinfo. Telegram is only the
support sink and the native API host is fixed. Token absence fails safely before
HTTP. Config repr omits tokens; immutable exact-revision lookup never substitutes
a newer target. Unknown revisions fail destination_unavailable.

Before a destination becomes eligible for a lease, main must register its exact
DestinationRef and `target_fingerprint(config)` bytes32. Reuse the actual helper,
not an independent serializer: SHA256 of sorted compact UTF-8 JSON, schema_version1,
sink plus origin/website_id for Umami, or chat_id/topic_id/operator_origin for
Telegram. Credentials are excluded; rotation to the same target does not imply
retargeting an immutable revision. No registration SQL/config mutation lives here.

One POST has a5s deadline, no redirects/cookies/client retry or ambient proxy,
16KiB UTF-8 request and raw-response bounds, and discarded provider bodies/cache.
Direct AsyncBaseTransport avoids AsyncClient's INFO full-URL logger (Telegram's
URL includes the token). There are no adapter logs or raw exceptions in results.
Maintain ordinary safe application logging and do not enable raw HTTP debug
capture. Cancellation propagates; the durable worker retains its uncertain lease.

Connect/pool failures before write are retryable; read/write/protocol/timeouts
and5xx are ambiguous, never exactly-once.429 retains header/body cooldown with
the larger valid wait; excessive waits are represented as above the application
maximum, causing its existing operator-review disposition rather than early retry.
401/403 are credentials_unavailable; redirects/404 destination_unavailable;
other4xx permanent. Accepted Telegram results contain actual positive message_id;
provider acceptance is not human acknowledgement. Plain support notices contain
case UUID, finite topic, server receipt time and constructed operator case link.
They omit actor, mailbox, private message/details and parse_mode; previews disabled.
No technical/PeerlyDev producer or unused delivery branch exists.

Umami3.3 sends named server/client events, explicit actual actorUUID where known,
original source/capture/delivery IDs and finite allowlisted facts. Native `id` is
identity, not dedup. Source time is used for canonical/backfill, server received_at
for client claims; observed_at stays explicitly untrusted metadata. URLs are
constant semantic paths, never captured browser URLs; no IP/browser/referrer or
fake browser User-Agent. Identified event metadata is not proof of accurate native
browser sessions/geography/device journeys.200 bot-ignore is not acceptance; the
native cache/sessionId/visitId response is checked then discarded.

Primary protocol references:
- https://github.com/umami-software/umami/blob/v3.3.0/src/app/api/send/route.ts
- https://docs.umami.is/docs/guides/send-server-side-events
- https://core.telegram.org/bots/api#sendmessage
- https://core.telegram.org/bots/api#responseparameters

No live provider acceptance or activation is claimed by source/mock validation.
