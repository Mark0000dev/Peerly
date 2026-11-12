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

## Design v2 implementation batch · 12 November 2026

Original comparison targets: C01-ChatList all3 frames; C02-Conversation all7 and
C02-Delivery4; C03-Image4 and C03-Lifecycle15; C04-SharedGoal4; F01-CheckIn5;
F02-Feedback6. Existing scenario coverage is historical acceptance, not visual
fidelity proof for this new source cohort. Matched captures remain pending.

Current coherent source changes: bottom native student navigation, native empty
list and thread AppBar/back, real avatar directive and generic identity fallback,
compact list subject/preview/time/unread, author-derived native message alignment,
compact immutable accepted context and inline text+explicit Send composer. An actual
image-only last message says Image without fetching the attachment or advancing
read position. New unit/scenario definitions assert that privacy/ACK boundary.

C04 uses actual goal-share CAS/review protocol and separate context storage; it never
claims the share is a human message. Own current-goal management links use existing
/profile/goal and /profile routes; no cross-screen CompleteGoal import or duplicate
completion protocol. Direct inline completion remains shared integration-dependent.
No unsupported profile action, recipient capability, starter role, countdown or
pending-request consequence is invented. Read-only history and explicit ACK remain.

Automatic F01 eligibility/one-off presentation, typed draft ownership, F02 publication
and saved-answer review remain unchanged. Native inline check-in/feedback cards use
readable headings, touch targets and wrapping choices. This supported inline
presentation is a documented difference from the designer's dedicated feedback
phone; no modal automatically interrupts chat. Existing native image viewer,
owner-resume/explicit Send and message-image report lifecycles are unchanged.
No private-message mascot, heavy SDK, business DTO or mirrored server state added.

Acceptance remaining: exact reference-vs-production captures after a coordinated
lead build, batch offline review of current cohort, affected unit/scenario runs and
current real-fixture proof. Include320/360/desktop,200% text, keyboard/focus, normal/
reduced motion and native viewer scrolling. No baseline updates or green claim yet.

### Concrete first-cohort comparison correction

Lead completed16 original/actual artifacts in
`../.peerly-ops/aquinas/chats-design-v2-20261112/coherent-capture/`. First-cohort
resource diagnostics are retained (controlled fixture failures, not app-resolution
proof). Original F01 is a shorter context fragment, not an844px phone; compare its
recorded native bounding box and retain actual full-page/viewport artifacts.

Observed C02 extra top Chats heading and expanded six-line context pushed the composer
below the390×844 viewport. Approved source correction now uses one authoritative
thread H1, list-only navigation and public TuiAccordion with concise actual subject
summary; retained attributed fields expand explicitly. No request quote is fabricated
from AcademicContext. Context-detail scenarios explicitly open the real disclosure;
new regression checks a single heading and no implicit send/read on expansion.
Latest correction needs its new cohort review/acceptance; earlier beb88f44 remains
frozen historical evidence, not the latest source manifest.

### Current F01/F02 follow-up

The explicit lead-assigned correction supersedes the first-cohort placement/inline
feedback approximation: contextual nonmodal F01 now sits after the accepted context
and before history; explicit F02 uses a native dialog with the existing form and
lifetime. The child remains mounted across pending/error detail reads, so this does
not manufacture a new visit. Public native focus restoration is guarded by actor,
selection and current details. See study/SCENARIOS.md for regression and proof bounds.
Account/P02/discovery/requests remain frozen; no global capture/test matrix launched.
