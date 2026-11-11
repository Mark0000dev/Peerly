# WebKit Preview capture boundary

Only the open and zoomed **TuiPreview** states may request
`checkpoint(name, {webkitPreview: 'open' | 'zoom'})`. WebKit uses the installed
Playwright1.65 public `page.screencast.start/stop` API. Chromium and every other
state keep the existing PNG screenshot path. This changes test capture only;
there is no application, CSS or dependency patch.

The initial bounded WebKit proof is retained in
`/tmp/peerly-public-screencast-proof/`: spec/config, raw logs, manifest, ordinary
before/after PNGs and three independent compositor JPEGs. Three fresh native
frames at390×844 matched exact bytes:
`676b4d3107cb2a391c979a2b5e11e6c6e0a8253807e4cdf6b8f23f8cd7b9527e`.
The full compositor image has the correct dim backdrop; ordinary same-state
snapshot PNGs omit that backdrop. Both paths were personally reviewed. This
establishes a capture discrepancy, not its precise WebKit implementation cause.
The initial temporary-config startup failed before any browser test because its
server cwd was incorrect; `run.log` is preserved alongside successful `run2.log`.

The adapter requires three independent public start/stop cycles after the caller
establishes public Preview readiness. Each first frame must have a fresh native
timestamp, callback viewport dimensions and JPEG-encoded dimensions identical to
the entire configured viewport. All three JPEG buffers must match **exact bytes**.
Missing/stale frames, scaled captures, unsupported APIs, start failures, different
content and cleanup failures fail the scenario. There are no masks, crops,
resizing, private protocol calls or tolerance changes.

The resulting reviewed baseline is **JPEG**, not PNG. The standard Playwright
snapshot matcher compares its decoded image at zero differing pixels and zero
pixel threshold. An ordinary full-viewport PNG is always preserved as a diagnostic
artifact and is not misrepresented as a successful visual comparison. Native
frame byte stability is a separate strict prerequisite before baseline comparison.

For only the tests containing these Preview states, bind a top-level public
`test.extend` variant with trace options `mode: 'retain-on-failure', screenshots: false, snapshots: true,
sources: true`. This prevents the trace's independently configured screencast
size taking precedence. DOM/source tracing remains. Any unexpected size precedence
still fails; the helper never rescales or accepts a smaller frame. Other tests
retain their existing trace options. Installed Playwright rejects changing this
worker option inside a describe; the failed discovery attempt is preserved and
no browser was launched for it. Console, page errors, forwarded Vite errors,
teardown diagnostics and CLI exit handling remain strict.

Each native JPEG and native timestamp/viewport metadata is attached before the
stability check, including a failing mismatched cycle. This preserves actual
diagnostic evidence rather than requiring a rerun to recover lost pixels.

Tooling regressions cover independent cycles, stale/no frame, wrong callback and
encoded dimensions, malformed content, byte instability, unavailable API,
start rejection even after a frame, and primary plus cleanup failures. The
adapter has no production runtime consumer. Current browser candidate/reference
acceptance is recorded separately in the frontend and image progress ledgers.
This is **not a ResizeObserver fix** and does not retire the global runtime gate.

Public references:

- [Playwright Screencast](https://playwright.dev/docs/api/class-screencast), public since1.59.
- [Playwright trace options](https://playwright.dev/docs/api/class-testoptions#test-options-trace).

The first product-scenario capture accepted WebKit OPEN's three stable frames
but rejected ZOOM's byte instability; its failure remains
`/tmp/peerly-c03-preview3-capture8.log`. No tolerance was relaxed. Existing trace
orders those zoom captures255/282ms after a click while the installed public
component transition is300ms; this is a concrete readiness hypothesis, not pixel
cause proof. The test must await the public Web Animations finite completion
before a single affected check. Strict native equality remains the acceptance
condition. OPEN alone is not acceptance of ZOOM or the whole viewer matrix.

The affected WebKit check then passed OPEN and ZOOM with the strict three-cycle
checks unchanged (`/tmp/peerly-c03-preview-wk1-capture9.log`). Saved public readiness
evidence observed ZOOM's finite running animation with endTime300, awaited its
finished promise, then captured fresh native frames. OPEN had loaded fonts and
two decoded640×480 images. These observations establish a genuine readiness wait;
they do not recover the missing old failing pixels or prove a global runtime fix.
Candidate references and the ordinary three-project run remain separate gates.

The scoped ordinary viewer run then passed all three projects with no baseline
updates: **3/3 CLI0,14.3s**, `/tmp/peerly-c03-preview3-normal4.log`. Two reviewed
WebKit JPEG baselines compare OPEN/ZOOM; four Chromium OPEN/ZOOM and three closed
state PNG baselines retain the standard path. This accepts this viewer scenario
only, not the remaining image scenarios or the global application/runtime gate.
