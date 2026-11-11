# D02 Full profile / S01 local safety

Contract: actual35 public profile/current private JPEG, actor-owned paginated blocks,
block CAS and profile-only reports. Boundary scenarios use generated readonly DTO
fixtures at HTTP boundaries; they are not FastAPI/PostgreSQL verification.

| Design / case                               | Boundary scenario and named checkpoints                                                                                                                                         | Unit coverage                                                                      |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| D02 public projection / no unsupported CTA  | real public projection; full-profile, safety-menu                                                                                                                               | actual fields, optional sections, no request/chat                                  |
| D02 loading                                 | loading resolves; loading, loaded                                                                                                                                               | no private request before session ready                                            |
| D02 unavailable / empty                     | unavailable remains neutral; unavailable                                                                                                                                        | 404, no fabricated context or block reason                                         |
| D02 failure / retry / optional empty fields | read failure; read-failure, sparse-profile                                                                                                                                      | safe errors, retry, optional fields omitted                                        |
| D02 session / eligibility                   | session failure; session-failure, verification-required                                                                                                                         | 401, session revalidation, no private reads                                        |
| D02 current JPEG                            | photo failure retries only the current authorized JPEG; photo-failure, photo-retried; stale JPEG version refreshes canonical person; photo-version-stale, photo-version-current | helper owns cancellation; view owns URL cleanup                                    |
| S01 report form / Other / length / receipt  | report validation; report-reasons, other-required, length-validation, stored-receipt                                                                                            | 1000 Unicode codepoints including astral characters; no automatic block            |
| S01 report unknown                          | unknown outcome; report-unknown, report-replayed                                                                                                                                | unchanged original key/payload despite draft change                                |
| S01 malformed 201 / unknown outcome         | malformed successful report response; malformed-reply, malformed-reply-replayed                                                                                                 | shared transport parse regressions map 2xx parse failures to uncertain ApiFailure0 |
| S01 report 429                              | quota; report-rate-limit                                                                                                                                                        | safe retry metadata, no raw provider body                                          |
| S01 block / own unblock                     | block confirmation; block-confirmation, own-block-canonical, unblock-confirmation, unblocked-canonical                                                                          | original context/CAS, canonical reread after historical receipt                    |
| S01 block 409                               | block conflict; conflict, conflict-refreshed                                                                                                                                    | explicit refresh; no new intent before recovery                                    |
| D02 / S01 accessibility                     | 320px / 200% text / keyboard; narrow-large-text, narrow-large-text-report, narrow-large-text-actions, dialog-keyboard-return                                                    | URL identity and draft cleanup                                                     |
| D02 stale resource / account / mutation     | block confirmation post404 report; unavailable-owned-report; session-expiry; expired-session                                                                                    | late block/report success/failure, account switch, disclosed context survives 404  |
| S01 reload / own history                    | reload finds own block; reloaded-block-first-page, reloaded-own-block, reloaded-unblocked                                                                                       | own unblock needs no fabricated fresh context; report absent without context       |
| S01 own block pagination                    | paginated own blocks; blocks-first-page, blocks-target-page                                                                                                                     | opaque cursor encoding; absent first page is not absence proof                     |

All implemented browser scenarios require behavioral assertions and screenshots through
`testing/visual`; baselines must cover mobile Chromium/WebKit and desktop Chromium.
Reduced motion is configured by the shared runner; 320px/200% reflow is explicit.

Request/review/chat/feedback/relationship states and Discovery-position navigation are
not applicable: no actual contracts in this slice. The only existing return link is
Peerly's real root. No fabricated empty deck, academic verification or role is shown.

The supplied S01 sheet uses an addon not present in installed dependencies. This slice
uses the installed public Taiga Dialog with keyboard focus containment and restoration,
fullscreen at its public mobile breakpoint and centered on desktop;
no package changes, handbuilt modal or control styling overrides. Initial reason/comment
and confirmation remain local surfaces on D02, with no settings route.

Real FastAPI/PostgreSQL scenarios use Halley's `preparePersonFixture`: controlled session /
membership facts, real durable profile/goal/photo worker/codec/registration setup. They
check actual authorized JPEG bytes, own block → canonical404 → owned-context report,
reload → own unblock without fresh context, and a report stored before its reply is
lost, then replayed with the exact original payload/key. These are separate from the
HTTP boundary fixtures. Snapshot update passed9/9 including runtime wrapper on head29. Ordinary replay passed
all9 behavioral/PNG assertions but the unchanged wrapper exited1 for a native observer
diagnostic; see RUNTIME-DIAGNOSTICS.md. No clean ordinary PG gate or fixed observer
cause is claimed.27 actual PG PNGs have been visually reviewed.
