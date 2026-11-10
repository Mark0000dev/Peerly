# Shared change-stream acceptance

Actual contract: same-origin authenticated GET `/api/v1/events`; cookie identity,
canonical decimal Last-Event-ID and resource.changed/reset_required frames. No
business DTO or event store is maintained. Only the actor/cursor/network lifetime
is retained. Hints invalidate existing private query keys; /me remains authority.

| Scenario                                                                                           | Behavioral evidence | Browser + screenshots                                               |
| -------------------------------------------------------------------------------------------------- | ------------------- | ------------------------------------------------------------------- |
| Verified/activated actor starts one stream; denied/unknown actor does not                          | scoped unit pass    | HTTP + real PG cases below; denied/unknown actor unit coverage      |
| Peer hint refreshes canonical visible data, exact 64-bit cursor resumes                            | scoped unit pass    | HTTP3projects normal pass; real PG3 pass, runtime RO open           |
| Own-account/reset hint rechecks /me; revocation retires private cache                              | scoped unit pass    | own-account HTTP3projects normal pass; reset visual variant pending |
| Heartbeat is inert; transient socket/408/429/503 retries GET only                                  | scoped unit pass    | HTTP3projects normal pass; zero automatic writes                    |
| Malformed protocol/permanent 4xx pauses until independent /me read                                 | scoped unit pass    | pending browser coverage; no success claim                          |
| Repeated auth denial cannot spin stream/auth GETs; identity stays canonical                        | scoped unit pass    | pending browser coverage                                            |
| Same-actor authority refresh aborts old transport; account replacement/logout retires actor cursor | scoped unit pass    | pending browser coverage                                            |
| Partial frame + cumulative connection are bounded; final response validates MIME                   | scoped unit pass    | transport boundary unit cases; no separate decorative UI            |
| Destroy cancels owned connection/timer                                                             | scoped unit pass    | normal owned page lifecycle still subject to unchanged runtime gate |
| Actual PostgreSQL publication -> authorized stream -> visible query refresh                        | 3 real cases pass   | 3 real PG assertions/screenshots pass; CLI1 native RO               |

Earlier scoped gate before HTTP header regression:51 tests, CLI0;98.08 statements /95.07 branches /100 functions /
100 lines. Thresholds95 unchanged. Raw `/tmp/peerly-changes-retry-unit2.log`, SHA256
`442b44d6250342d0a038230ad5a75cdfbe15b5ee4c3f7f6e7fa2dad8a9cd2908`.
This is not browser, real-SSE PostgreSQL or whole-frontend acceptance.

HTTP-boundary default fixture emits only heartbeat wire. Test-specific cases
replace that boundary with documented frames; full-stack leaves FastAPI unmocked.
No direct EventSource credentials, automatic sends/ACKs, console filtering or
persistent cursors. Independent global native ResizeObserver blocker remains open.

The real-stream fixture uses a finite registry of driver-owned synthetic peers,
real SendMessage and bounded PublishChanges batches. No fake frame/cursor, direct
SQL message insertion or server time override. The browser asserts the initial
reset/resume handshake, actual incoming message timestamps/sequence and unchanged
private read position before capturing Yesterday UI. Driver Ruff/e2e types pass;
actual three-browser results and runtime limitation are recorded below.

Initial boot barrier is now independently verified: public ApplicationRef.whenStable
one-shot in content composition, followed by DestroyRef and current actor guard.
Four actual root lifecycle tests cover pending boot, destroyed scope, latest actor
and reconnect while a later PendingTask remains. Combined55/55 CLI0 in
`/tmp/peerly-stream-boot-unit3.log`; SSE scoped coverage remains98.08/95.07/100/100.
No private token/opt-out, HttpClient interceptor bypass or manual readiness timer.
This does not claim Angular remains stable during an open HTTP stream or resolve
native ResizeObserver diagnostics. HTTP normal comparison is green; real publication
behavior is proven below with runtime acceptance still blocked.

Real HTTP header ordering regression: the first browser candidate with correct
checkpoint filenames passed hint refresh/revocation but failed transient503 retry.
Angular emits the non-SSE error ResponseHeader before HttpErrorResponse; MIME
validation was incorrectly classifying the JSON problem as invalid SSE and pausing.
The transport now ignores error-response body/progress until the actual HTTP error,
preserving the existing status policy. Three408/429/503 cases explicitly emit
problem headers plus non-SSE progress before flush. All51 scoped tests pass,
98.14/95.27/100/100 coverage, unchanged95 thresholds; raw
`/tmp/peerly-changes-http-header-green2.log`. Browser candidate3 passed9/9 CLI0, all9 PNGs reviewed. Ordinary comparison
passed9/9 CLI0/35s with no updates; raw `/tmp/peerly-changes-http-normal1.log`,
SHA256 `6711e9fe63b6e7ce0694159a45f44ee5dcd21874e4b9069b23189c0e50f55533`.
Actual real publication candidate3 passed3/3 assertions in29.2s;3 PNGs reviewed.
Source timestamp/sequence/author, Last-Event-ID resume, visible incoming bubble,
canonical list preview, unread1/read-positionnull and no browser commands verified.
Overall CLI1 retained one owned desktop native RO plus Vite/Angular wrappers; no
backend cancellation traceback. Raw `/tmp/peerly-changes-pg3-candidate3.log`, SHA256
`2c7c53417f8bb06c34aa1e9bd87c7a0149ebddc8a7bf63b6610781d095c66dee`.
No normal rerun or complete runtime acceptance. Explicit END cleanup proves
schemas[]/other DB sessions0/three pools disposed/listeners closed/own TLS removed.
Two earlier candidates failed only test locator mistakes (global duplicate text,
then desktop-only region role/visibility), retained separately.
Earlier failure logs are retained; native RO is independent and unfiltered.
