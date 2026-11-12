# Requests lifecycle scenarios

Status: implemented, acceptance blocked. Latest complete unit run770/770 CLI0,
Requests91 tests and own100/98.05/100/100 coverage, including final layout/quota markup.
Corrected HTTP candidate60/60 assertions and108 PNGs reviewed, but runtime guardCLI1.
Normal HTTP comparison is blocked. Real-PG candidate18/18 passed with runtime CLI0;
all39 PG PNGs reviewed and normal18/18 +39 comparisons passed with runtime CLI0. Several test-only
unread fixture corrections after review require later explicit candidate updates.
No whole-gate green claim. Exact evidence/limitations are in the progress ledger.

| ID                     | Behavior and checkpoints                                                                                                                           |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| R01 received           | Actual unread and retained request text, grounded mode/subject, genuine public profile link, no compose/chat CTA                                   |
| R03 detail / owned ACK | GET leaves unread; exact immutable academic context; explicit foreground ACK followed by canonical unread; unknown ACK exact disclosure/key replay |
| R01 loading/failure    | Pending read,503, explicit retry and loaded list                                                                                                   |
| R01 empty views        | Active/history/recently_declined remain distinct URL-owned empty states                                                                            |
| R01 decline            | Pending write, confirmed server Undo, recently-declined navigation, confirmed Undo reread                                                          |
| R01 deadline           | Observed server window expires; disable stale Undo and reread capabilities, no local finalization                                                  |
| R03 accepted / pair    | Genuine conversation reference with no first message; no new pair/request or invented Chats route                                                  |
| R02 sent               | Actual pending/daily counters; explicit withdrawal confirmation/cancel; retained snapshot after actual confirmation                                |
| R01 CAS / uncertainty  | Lost reply, exact body/key replay,409, explicit canonical refresh before new intent                                                                |
| R01 paging             | Opaque cursor in URL;422 continuation recovery clears cursor                                                                                       |
| R03 peer lifecycle     | Neutral unavailable/deleted identity and retained text; no private profile/photo grant                                                             |
| R01 authentication     | Current401 clears private content; failed account check and guest; replacement-actor late callbacks unit tested                                    |
| R01 accessibility      | 320px/200% text, long names/content, semantic controls, keyboard focus, reduced-motion project defaults and safe areas                             |

All boundary scenarios require behavior plus named screenshots on mobile Chromium,
mobile WebKit and desktop Chromium. Baselines will be created explicitly, reviewed
and compared normally under Halley's serialized lease. No tolerances/masks/skips.

Real-PG scenarios use only Halley's `prepareRequestsFixture`: genuine sender/recipient
actors and actual activation/profile/photo/help/preview/send, retained pending row
version1. UI proves disclosure/ACK, acceptance and empty conversation, decline/Undo,
withdrawal persistence and unrefunded daily count, actual ten-second server expiry, committed accept with deliberate
reply loss followed by exact immutable receipt replay. Deliberate network loss is
not a fabricated business result. Membership/provider/storage boundaries remain
controlled test infrastructure; no deployment/provider compatibility claim.

Supported approximations approved by Halley: text-only peer identity (no guessed
photo source), explicit Mark as viewed instead of implicit view detection; one
unresolved decision locks action/navigation until confirmed or explicitly recovered,
while canonical request text remains readable. Public Taiga wrapping links/buttons/card
express the layout without theme/control overrides or fake bottom navigation.

Compose/preview/send, alternate response and Chats navigation are excluded pending
their real lifecycle consumer. No editable forms here; validation applies to nested
unknown DTO guards, URL semantics and server CAS/capabilities. No photo decoder or
keyboard-open form scenario is applicable. No recipient reason/privacy inference,
automatic social retry, fabricated counts/expiry/Undo or automatic unread ACK.

Global ResizeObserver diagnosis belongs to Halley. No whole check, probes, observer
patch or suppression while the parent-imposed causal-evidence hold remains active.

Actual narrow-layout regression: first candidate root379–380px at320px/200%.
Public wrapping links, normal minmax grid tracks and concise primary button text
with full accessible names fixed all3 projects; controls fit the viewport and name
column remains at least160px. No control CSS/clipping/font override. Parent runtime
hold remains: no browser rerun merely to recapture truncated diagnostics. Future
justified commands must preserve complete raw stdout/stderr and original exit status.

Actual real-PG candidate acceptance:18/18, runtime CLI0,1.5m, coherent actual54/HEAD39.
Full raw log and SHA256 in the progress ledger. All39 PG PNGs reviewed. This proves
real list/detail/foreground ACK, acceptance with zero human messages, actual Undo,
actual10s final decline after reload, withdrawal without daily refund, committed
acceptance exact replay and same-revision ACK deduplication. It does not resolve
or override the earlier HTTP candidate runtime guard failure.

Normal real-PG comparison:18/18,39 PNG comparisons, runtime CLI0,1.4m on actual60 /
HEAD39. Explicit fresh lease requests-pg-normal18-2 followed the compatible old54
contract check; both fixture listeners and frontend listener were closed before END.
No source or baseline update in the ordinary run. Raw complete log/hash in ledger.
Old HTTP runtime guard failure remains independent and unresolved.

## Design v2 implementation batch · 12 November 2026

Targets: R01-Received/Decline, R02-Sent, R03-Detail/Pair and R04-AltResponse.
Native AppBar supplies detail/back and labelled refresh, Received/Sent remain real
URL filters, native BlockStatus supplies truthful empty views, request text remains
an immutable excerpt. Withdrawal now uses the public native Dialog with locked
close/dismiss during unresolved decisions. Accept still creates no first message.
Only actual open_conversation capability plus nonnull conversation_id exposes Open
chat, using the existing /chats?conversation contract. Regression definitions now
assert that concrete destination; older no-Chat-link evidence is historical.

R04 alternative response remains a backend contract dependency: RequestActionBody
contains expected_version/person_id only. No message endpoint, draft transport or
alternative-response capability is invented; accept/decline keep their real meaning.
Mark as viewed remains explicit foreground acknowledgement; opening detail alone
never changes unread. Original Undo/server deadlines, replay identity and private
unavailable-peer behavior remain intact. Matched reference/candidate captures and
current screenshot review/acceptance are PENDING; no old green count accepts this UI.

First matched-reference review: eight390×844 original frames plus eight actual
production states, all16PNG reviewed. Evidence outside source at
`../.peerly-ops/aquinas/design-v2-implementation-20261112/candidate/COMPARISON.md`.
Actual images precede the follow-up density/layout source corrections and retain
eight unattributed resource404 diagnostics; no runtime-clean/final-fidelity claim.
No screenshot baselines were updated. Current source needs coordinated affected
acceptance, including mobile/desktop,320/200%/focus and genuine fixture proof.
