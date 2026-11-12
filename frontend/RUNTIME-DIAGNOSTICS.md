# Native observer runtime investigation

Status: unresolved, 8 November 2026. Halley owns shared fixture/observer evidence;
Aquinas supplied a bounded read-only source analysis. No observer scheduling,
realm, pagehide, global style or error-filter workaround is implemented.

## Bounded owner trace and minimal native fixture

The selected-chat recovery trace observed two actual owners: font-watcher's
foreign iframe BODY and Taiga ResizePlugin's main-document textfield mirror SPAN.
Capture changed the viewport1×1→1440×900; BODY width0→1424 retained height16,
with root `--t-font-offset:0` writes. Both observers remained active at pagehide.
This instrumented case emitted no native error, so it does **not** identify the
skipped observer target. A separate ordinary same-case control did fail with RO.
Do not confuse wrapper ownership, correlation, and causal proof.

Preserved raw artifacts are `/tmp/peerly-native-ro-causal1.log`,
`/tmp/peerly-native-ro-causal2-{log,page.jsonl,summary.json}` and
`/tmp/peerly-native-ro-causal3-{log,page.jsonl}`. Quiet-ring instrumentation also
failed to reproduce. All temporary application probes were removed; subsequent
central Node Angular compiler import is an independent fixture collection fix.
No additional full-app instrumentation variants are scheduled.

The new standalone native fixture imports the installed watcher module and
models the textfield native observer without Angular. Its first baseline shows
same-value offset writes already produce zero style mutations, while real28→17
font scaling produces the expected two mutations. It did not reproduce RO or the
app's1×1 capture transition. Thus neither a same-value guard nor any dependency
source extension is justified. See `FONT-WATCHER-REPRO.md` for exact source hashes,
raw artifacts and the prepared public screenshot-matcher fidelity comparison.
The global blocker and unknown skipped target remain open.

## Latest ordinary aggregate: actual54/HEAD37

Final619 units,46 tooling checks, all static gates,499.83kB production build and3
public checks passed. All339 boundary assertions passed, then unchanged runtime
CLI returned1; PostgreSQL stage did not run. No repeat whole gate is scheduled
without a concrete fix or new causal evidence. Separate scoped PG48 and Discovery
PG9 evidence remains valid on its own recorded snapshots.

Full untouched log is /tmp/peerly-discovery-aggregate-check.log,71624 bytes,
SHA256bf0b1bd5aeb17bb7e378e14c53def25080653fa06ff6188f0b4c23a9182eaf29.
Exact HTML report metadata (not adjacent completion lines) maps both contexts:

- chromium-desktop:05b35ef7955fd228ac08-9b674c1bddf6505ad459:
  onboarding/onboarding.visual.spec.ts:62, callback account_unavailable.
- chromium-desktop:05b35ef7955fd228ac08-a344c2167c2e716a5250:
  onboarding/onboarding.visual.spec.ts:87, active challenge reload.

At03:18:22/03:18:25 these contexts emitted native RO plus Vite374 forwarding;
the latter also emitted Angular2770 no-error ErrorEvent. Safe exact metadata is
/tmp/peerly-discovery-aggregate-contexts.json. These are not the adjacent photo
scenarios. The skipped observer target and actual causal size write remain unknown.
No new instrumentation, observer scheduling or error filtering was introduced.

## Original ordinary aggregate

Execution70605 used actual45/c4fd, HEAD31. Static gates,46 tooling checks,576 units,
95.18% branch coverage,499.97kB production build and3 no-JavaScript checks passed.
All282 boundary behavior/screenshot assertions passed, but the CLI returned1.
The PostgreSQL stage did not start. Passing assertions do not override diagnostics.

The exact owned context was
`chromium-desktop:50c9d5fe313c4ca7f1d4-7318903ce7434091a835`, mapped from the
report metadata to `onboarding/study/help.visual.spec.ts:470`, the
`subject_unavailable` recovery scenario. The neighboring Person scenario is not
the emitting context.

These are separate exact diagnostic excerpts, not three independent proven causes:

```text
[WebServer] 1:33:13 AM [vite] (client) [console.warn] [peerly owned runtime context] chromium-desktop:50c9d5fe313c4ca7f1d4-7318903ce7434091a835 ResizeObserver loop completed with undelivered notifications.
```

```text
[WebServer] 1:33:13 AM [vite] (client) [Unhandled error] Error: ResizeObserver loop completed with undelivered notifications.
[WebServer]  > ../../../../../../../../../../../@vite/client:374:50
```

```text
[WebServer] 1:33:13 AM [vite] (client) [console.error] ERROR Error: An ErrorEvent with no error occurred. See Error.cause for details: ResizeObserver loop completed with undelivered notifications.
[WebServer]     at errorListener (http://127.0.0.1:38385/@fs/home/aleksei/Aleksei/Programming/apu/studymate/StudyMate-AI/frontend/.angular/cache/22.2.6/studymate/vite/deps/_resource-chunk-_hotzT1w.js?v=dcea56ac:2770:21)
```

Installed `vite/dist/client/client.mjs:374` constructs a fallback Error when the
native event has no error object. Installed Angular
`@angular/core/fesm2022/_pending_tasks-chunk.mjs:2761` constructs its own wrapper
with the event as cause, then prevents default reporting. These branches explain
the wrapper stacks, not the dirty observer target. There is no evidence here of
an independent business-code exception or of a harmless error that may be ignored.

Safe excerpt files and metadata are under
`/tmp/peerly-aggregate-runtime-70605/`; they are not a complete stored runner log.
No request bodies, provider tickets or private trace content were copied.

## Bounded diagnostic evidence

The exact desktop help-recovery pilot3 did not reproduce the error. It established
native JS observer owners: font-watcher observes a foreign iframe BODY; Taiga's
ResizePlugin observes auxiliary textfield SPANs and its callback writes ancestor
`--t-side`. A clean pilot is not fix evidence.

One instrumented282 boundary run returned1 with three native errors after
`pagehide` during owned `page.close`, in desktop Goal scenarios at lines94,286,327.
All282 behavior/screenshot assertions still passed. In the first context:

| Event                                | Epoch milliseconds |
| ------------------------------------ | -----------------: |
| Last observed application size write |    1794091519372.3 |
| Last screenshot returned             |      1794091519617 |
| Two-frame render drain began         |      1794091519617 |
| Owned page close began               |      1794091519646 |
| Browser pagehide                     |      1794091519648 |
| Native error                         |    1794091519656.1 |
| Owned page closed                    |      1794091519657 |
| Context closed                       |      1794091519668 |

The full pre-pagehide rings were recovered from the host console. Font BODY and
three textfield observers were active; popup observers had disconnected. The
native-event payload forwarded after detachment was truncated by Vite at9978
characters before its callback/write tail. Therefore the actual skipped target
and any write between pagehide and the error remain **unknown**. The last observed
pre-pagehide writes precede the three errors by approximately284,1501,1449ms.
Instrumentation can affect timing; this association does not prove a library fix.

Evidence is task-local:
`/tmp/peerly-native-ring-boundary-proof.log` and
`/tmp/peerly-native-ring-events/timeline-summary.json`.
A subsequent compact diagnostic run of only the three affected Goal cases passed
without reproducing an error; no larger repeat followed. Every temporary probe
was removed; shared fixture SHA256 restored to
`7ab8c7a95fd9a9926fbe7362f3cd2a6c5b88202c82cce23cd84b7339446e7b8e`.

## Supported Angular lifecycle

Installed source has explicit cleanup on Angular destruction:

- `@taiga-ui/cdk/fesm2022/taiga-ui-cdk-directives-font-size.mjs:15` registers the
  watcher cleanup with DestroyRef.
- `@taiga-ui/font-watcher/index.esm.js:28` disconnects its observer, removes the
  resize listener, then removes the owned iframe.
- `@taiga-ui/event-plugins/fesm2022/taiga-ui-event-plugins.mjs:239` returns the
  textfield observer's disconnect function to Angular's event manager.
- Angular `_debug_node-chunk.mjs:4945` executes destroy hooks and cleanup callbacks;
  ApplicationRef destruction at13437 destroys its attached views.

The real-browser root routing unit in `src/app/app.spec.ts` verifies that normal
navigation from the active helper editor to Help disconnects its actual native
observers while retaining the root font watcher. Destroying the root fixture then
disconnects that foreign-target observer **before** removing its iframe. All8 root
tests pass; focused lint/spec type checks pass. This supported lifecycle did not
reproduce the closure failure. The initial test was corrected to await the actual
input rendering before collecting native observations; no product code changed.

Browser pagehide is not Angular view destruction. Neither the application
bootstrap nor these Taiga cleanup owners registers a pagehide handler. That fact
does not justify adding an ad hoc handler or prove a missed application cleanup.
No further concrete causal test is currently established. Continue independent
contract-backed work/real PostgreSQL acceptance; keep aggregate runtime failure
open and preserve the strict CLI gate.

## Source mechanism references

Installed Playwright1.65 first screenshot poll can return without the later-poll
double-frame wait; a matching PNG alone is not layout quiescence. Its Chromium
capture path uses CDP captureBeyondViewport, without an explicit JS viewport call.

Pinned Chromium158.0.8127.18 sources show additional browser internals:

- [Screenshot handler](https://raw.githubusercontent.com/chromium/chromium/158.0.8127.18/content/browser/devtools/protocol/page_handler.cc),
  lines1444–1476 changes emulation/scrollbar preferences and view size during
  capture;1846–1883 restores these before replying, without a renderer lifecycle ack.
- [Emulation handler](https://raw.githubusercontent.com/chromium/chromium/158.0.8127.18/content/browser/devtools/protocol/emulation_handler.cc),
  lines1079–1105 documents the missing renderer acknowledgement.
- [Resize observer](https://raw.githubusercontent.com/chromium/chromium/158.0.8127.18/third_party/blink/renderer/core/resize_observer/resize_observer.cc)
  binds its controller to the constructor's window; observing a foreign target
  does not migrate it.
- [Observation depth](https://raw.githubusercontent.com/chromium/chromium/158.0.8127.18/third_party/blink/renderer/core/resize_observer/resize_observation.cc)
  counts the target's own flattened tree. A foreign BODY may compete with deeper
  parent-document targets. This is a hypothesis, not evidence for a realm patch;
  same-target re-dirtying can still fail in either realm.

These sources narrow possible mechanisms. Actual transient geometry and the
skipped target during the captured teardown errors are not proven by source alone.

## Separate Blob URL loading error,8 November

Composer HTTP87 candidate9 stopped after40 passing scenarios on the WebKit
unknown-send case: the original console gate caught Failed to load resource for
an image Blob URL. This is not the aggregate ResizeObserver error. Raw
`/tmp/peerly-compose-boundary-candidate-9.log` and its unique trace/report retain
full evidence; passing scenario assertions do not override CLI1.

One passive native URL/create/revoke and image-lifecycle probe passed standalone.
Its only URL had no bound document image at revocation. That does not establish
what happened to the earlier failed second URL; no recurrence-based fix claim.
Evidence `/tmp/peerly-compose-photo-diag1-events.json` and corresponding raw log.
Diagnostic wrappers were removed before normal checks; no console filtering.

A distinct deterministic unit exposed a real resource defect: QueryObserver fetch
status notifications revoked/recreated the displayed image URL before replacement
bytes arrived. The fixed component retains only its native Blob identity/ObjectURL
resource handle; query data/status remain canonical. Post-render retirement and
structural view removal are checked, along with actor replacement and duplicate
retry. A direct injectQuery implementation was not retained because its installed
namespace-compatibility path exceeded the500kB initial budget; established public
QueryObserver restores499.91kB without a dependency patch or budget waiver.

Current source passed851 unit tests, all95% thresholds, full statics/tooling and
production build. Original uninstrumented WebKit unknown-send normal1 and relevant
photo/setup HTTP normal9 passed with the unmodified runtime guard. This proves
those scoped runs are clean, not exact causality of the original native failure.
Full composer87 candidate10 then passed87/87 CLI0/runtimeclean2.6m. All198 current
images were reviewed; normal87 passed87/87 CLI0/runtimeclean2.1m without updates.
This is current scoped runtime evidence, not a reconstruction of the original failed
URL sequence. Renewed real PostgreSQL comparison awaits coherent backend42. The aggregate ResizeObserver blocker
remains independent; font-watcher patch and diagnostic policy were not broadened.

## Explicit viewport input in the isolated fixture

One supported1×1→1440×900 input was added after the companion observer attaches,
matching the observed top-level viewport transition rather than hoping screenshot
capture produces it. Both watcher callbacks arrived with unchanged metric16,
offset0 writes, zero style mutations and restored companion1×56. Positive28→17
font control passes. One matcher case/1.5s CLI0, no native error. This is another
negative causal result, not global runtime acceptance or a scheduling/realm fix.
Body.clientWidth in this fixture must not be equated with app contentRect width.
Raw `/tmp/peerly-font-minimal-explicit-viewport1.log`, source SHA remains4d48aa37…;
full provenance/results are in FONT-WATCHER-REPRO.md. Exact skipped target and
cause remain unknown. No source patch or further pass/fail variant was applied.

## Final bounded realm baseline —9 November2026

The owner approved at most ten cycles per realm variant, requiring positive native
baseline recurrence before running the comparison or changing a dependency.
An immutable task-local copy of the existing native fixture used the installed
font-watcher0.6.0 bytes (border-only patch), mobile360 viewport, error→recovered
textfield creation, ordinary full-page screenshot comparison, explicit1×1→360×800
resize/restore and owned page/context close. No application or installed source
was changed. Instrumentation records primitive callback/metric/write order and
native errors, without preventing or filtering native ErrorEvents.

Baseline10/10 passed in4.8s, CLI0, zero native errors. Real font28→17 controls passed;
owner disposal removed the iframe and a subsequent real resize produced no further
font callbacks (4before/4after). The ordinary baseline metric stayed16 across the
explicit viewport transition; its root offset0 writes alone did not reproduce an
error. These inputs approximate the recorded positive lifecycle, not an extracted
reproducer of the complete Angular aggregate failure.

As required, the owner-realm variant was NOT run: a clean baseline would make its
result nondifferential. No cross-realm causal conclusion or new dependency patch
is justified. Investigation stopped at the agreed bound, without another matrix.
The actual skipped target/native lifecycle cause remains unknown; the original
Chromium aggregate failure and strict CLI diagnostic guard remain unchanged.
Evidence: `/tmp/peerly-ro-realm-bounded/evidence.json`, full raw `baseline.log`,
immutable original/proof source and
`/tmp/peerly-ro-realm-minimal-baseline-1794242932914/result.json` with provenance,
per-cycle states and cleanup controls. No live provider, PG fixture or secret used.

## Production-build representative smoke and internal known issue

On10 November the owner explicitly permits internal-team staging with unresolved
RO and freezes blind investigation. Actual nginx image74ca40e1… runs the unchanged
frozen production application. A bounded9-case smoke (callback login_invalid,
font28->17 and explicit confirmed text Send across three projects) passed CLI0
in8.4s with15 ordinary strict golden comparisons and unchanged native guards.
No RO/JavaScript exception or visible/function failure was observed in these cases.
This limited negative production result is not proof of a fix or a Vite-only cause.

All raw traces and diagnostics remain in `/tmp/peerly-production-browser-smoke/`.
Six HTTP resource console errors are preserved: three intentional401 identity reads
and three ancillary study-prompt-visits404s because the standalone image has no API
proxy and that endpoint was not mocked. They are not ResizeObserver errors and do
not establish real backend/service readiness. No new error filtering, dependency
patch, application-source change or whole matrix was used. External acceptance is
still separate from the owner's explicit internal-staging known-issue decision.
