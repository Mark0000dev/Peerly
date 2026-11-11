# FE05 scenario matrix

Implementation behavior is covered; HTTP/PG runtime acceptance remains OPEN.
Scoped units60/60 CLI0, all95 thresholds pass. HTTP candidate84/84 assertions
PASS/153 PNGs reviewed, overall CLI1 native RO9 contexts. Real-PG candidate9/9
assertions PASS/42 PNGs reviewed on fresh actual72/head43, overall CLI1 native
RO4 contexts; normal screenshot comparison NOT run. No runtime suppression.
Observed HTTP GET fixture inconsistencies were corrected test-only and verified
by focused30/30 assertions plus63 reviewed checkpoint PNGs; overall CLI1 remains
native RO3 desktop contexts. Real canonical message/share/ACK projections are coherent. Full evidence and
cleanup are in docs/planning/chats-progress.md. No broader rerun is authorized.
References C01-ChatList, C02-Conversation/Delivery, C03-Lifecycle and C04-SharedGoal.
Actual generated contracts win over design placeholders. C03 image attachments
await an exposed tested API.

| ID              | Required behavioral and screenshot coverage                                                                                      |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| C01 list        | accepted empty thread, both-author last message, exact unread count, server order, opaque pagination                             |
| C01 read states | loading, empty, network/error retry, stale refresh, invalid cursor reset, current401 and actor isolation                         |
| C02 read        | actual selected URL, ordered confirmed sequences, original academic context, history paging, empty no invented message           |
| C02 lifecycle   | hidden retained chat, unavailable/deleted masking, can_send false, unauthorized/foreign404                                       |
| C02 text        | explicit Send, Unicode2000/raw preservation/unsafe controls, pending, confirmed clear and canonical refetch                      |
| C02 recovery    | lost reply immutable clientID/text/key, manual lookup/retry/cancel, unobserved not failure, cancel/commit race                   |
| C02 ACK         | active visible genuinely displayed confirmed message only, no GET/background ACK, monotonic private position                     |
| C04 shares      | explicit current goal/version/context review, immutable original, share history paging, stale source/conflict and unknown replay |
| Crosscut        | session revalidation blocks commands, logout/actor/destroy clears drafts/cache/resources, ignores late callbacks                 |
| Accessibility   | keyboard/focus,320px/200%, reduced motion, keyboard viewport, visible errors/actions, mobile Chromium/WebKit and desktop         |

One active-thread component form, cleared on selection/navigation/logout; no global
map or device storage. Shared SSE belongs to Halley. Avatar consumes Halley’s shared public ImageResource and actual conversation grant. No delivery/read receipts, typing/online status, fake profile
links, attachment buttons, study outcomes or automatic social replay.
