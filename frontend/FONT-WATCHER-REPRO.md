# Minimal native font-watcher fixture

This developer fixture is separate from the application. It imports the installed
public browser module of `@taiga-ui/font-watcher`0.6.0 without modifying it. Its
companion span uses the installed ResizePlugin's native observer/observe/disconnect
pattern. It does not load Angular or reproduce its signal/render scheduling, so a
non-reproduction cannot clear the application runtime blocker.

`npm run diagnose:font-watcher -- --variant=baseline` runs one metric-validation
page and one capture/close page. `idempotent` changes only the fixture caller's
same-value font-offset write; `owner-cleanup` explicitly invokes the returned
watcher cleanup and disconnects the span before close. Neither is a production fix.
There is no repeat loop. Run serially after the current browser/PG lease ends.
`--capture=matcher` is the prepared fidelity comparison: the public Playwright
runner performs ordinary zero-tolerance `toHaveScreenshot` comparisons against
locally captured expected images in the unique temporary directory. It runs only
after the metric browser closes. No production screenshots or configuration change.
The child has a60s runner limit and75s hard bound; interruption is forwarded, and
nonzero/signal exits fail the parent. One matcher run completed after the PG9 cleanup END:1 test passed in1.4s,
CLI0, no native error observed. Artifact directory
`/tmp/peerly-font-watcher-minimal-baseline-1794134871357/`, raw
`/tmp/peerly-font-minimal-matcher1.log`. Both unavailable/recovered comparisons
ran normally. The recorded resize events again stayed1440×900: the application's
1×1 transition is still absent. This negative result does not justify a dependency
patch or another broad run. Both browsers and the loopback server closed; the
browser resource was released to the next independent task.

Use the task's Node24 and `PLAYWRIGHT_BROWSERS_PATH=/tmp/studymate-browsers`.

The metric phase measures actual watcher callbacks during a width-only change,
records same-value writes and style mutation observations, then verifies physical
font metrics28->17 and computed text scaling. The caller reproduces the pinned
`tuiEnableFontScaling` clamp17..28 and DOM write; Angular signal effects are absent.
The lifecycle phase captures unavailable/recovered states with full-page screenshots
and the existing two-frame render drain, then closes normally. No app rAF/pagehide
patch, observer constructor monkeypatch, error preventDefault or console filtering.

Results, four screenshots and source fingerprints go to a unique `/tmp` directory.
Native error beacons and Playwright page errors make the command fail. Late beacon
delivery is not a guarantee of error absence: a clean run means only not observed,
not a dependency regression fix or whole-app acceptance. The normal strict browser
gate remains unchanged. No dependency patch may follow without actual causal
regression evidence, verified source hashes and preserved font scaling.

## First baseline: negative causal result

One baseline run completed with CLI0, no observed native error, and all owned
browser/server resources closed. Raw `/tmp/peerly-font-minimal-baseline1.log`;
result and four PNGs:
`/tmp/peerly-font-watcher-minimal-baseline-1794133932265/`.

A width-only callback repeated metric16 and offset0. The root style observer
recorded **zero mutations** and the companion span stayed1×56. Thus the same-value
write was already physically idempotent in this fixture; skipping it is not a
proven repair. Real metric28→17 produced two style mutations and computed font
sizes28→17, preserving the positive scaling control.

The capture/close phase did not reproduce the application's internal1×1 viewport
transition: recorded viewport events remained1440×900. Plain `page.screenshot`
is therefore not yet equivalent to the application's Playwright screenshot matcher
lifecycle. The companion uses the installed native observer pattern, not Angular's
render/signal scheduling. The skipped native observer target remains unknown.
Do not run the alternative modes merely to accumulate more clean results against
this non-reproducing baseline. The subsequent actual matcher comparison also lacked that transition; see its
recorded result above. No further variant is currently justified.
No dependency-source change follows from this result.

Installed inputs:

- watcher module `4d48aa37f6d589e9c4c157ea07041b2daf071e14c05abd5b8c49864f108bbcbf`
- provider `c01307462754618b244aa43ef227c654cd202c9f01dd3b442ad349170e247d05`
- ResizePlugin `de2d22f07c06d3da37d72f815daeb0a542d2e50a9e54416d5be6467c19cbbe8c`

## Prepared explicit viewport-input reproduction

`--capture=viewport-cycle` runs the same public matcher fixture, adding exactly
one top-level1×1→1440×900 viewport cycle after the companion observer attaches.
That input was directly observed in the application trace but absent from both
native baseline captures. This is a developer-controlled input, not a claim that
Playwright or the application caused the original transition. Both actual watcher
callbacks must arrive; their metrics, same-value root style mutations and companion
size are recorded/asserted. No observer scheduling, private browser API, app/style
workaround or dependency source patch. Executed once after the operator HTTP lease END:1 matcher case passed1.5s,
CLI0, no native error. Exact viewport transitions and watcher callbacks were
recorded; metric16 stayed fixed, both offset0 writes were same-value, style
mutation count0 and companion1×56 restored. Positive28→17 control also passed.
Raw `/tmp/peerly-font-minimal-explicit-viewport1.log` SHA256
`dc91ee37772bd1ecf4bbcce225c6474695fba3be80889e5b25ec6a38a49ca88d`;
result `/tmp/peerly-font-watcher-minimal-baseline-1794138332929/`.
The logged callback width is body.clientWidth, whereas the prior app trace used
ResizeObserver contentRect; these are different measurements, not evidence of a
new width defect. No extra observer/owner target was identified. Viewport cycle
and same-value write alone remain insufficient for this simplified reproduction;
Angular/Taiga render ownership is still absent. No dependency patch follows and
no repeated variant/full-app run is scheduled. Browser/server cleanup completed
before the worker's next lease.

## Source correction: companion observer ownership

The negative native fixtures above modeled a textarea mirror height writer. The
observed application `.t-content` span instead belongs to TuiTextfieldComponent:
its resize handler reads `clientWidth` and writes `--t-side` on its host. Installed
Taiga 5.31.0 module `taiga-ui-core-components-textfield.mjs` SHA256 is
`7e856f28bcb5088b2d6390b54f5368a3033c979962123c0dc92e6709595f6251`.
This is a source attribution, not proof that this observer caused the skipped
native observation. The earlier style-write trace matched font/width/height/size/
offset and related names, excluding `--t-side`; it therefore cannot establish
that root font writes were the only writes during the failing frame.

Next bounded causal work must model this actual width-to-host-variable geometry
path, or use a minimal public Taiga textfield fixture with its real observer owner.
Do not repeat the previous height-only variants or broad application runs. The
existing negative results remain valid only for their approximate model. No new
probe or dependency patch is justified as a fix by this source finding alone;
the skipped target and causal ordering remain unresolved.

## Current owned next action after FE06.2

Halley owns this unresolved aggregate runtime gate. The next experiment is one
minimal real public Taiga textfield fixture, using the installed pinned component
and font watcher, rather than the previous handwritten height companion. Record
resize target/callback phases, host `--t-side` writes (including same-value writes),
root font-offset writes, and observed geometry around the known 1×1-to-restored
viewport/capture teardown sequence. Preserve native ErrorEvents without filtering.
Include actual font28-to17 scaling and ordinary destruction controls. A reproduced
failure with target/write ordering is required before proposing a source correction.
If it does not reproduce, retain that negative result and report the remaining
ownership gap; do not branch into repeated full-app runs or claim resolution.
Run only after the worker's bounded accessibility-fix browser lease END, so browser
resources remain serialized. No additional dependency patch is authorized by this
plan alone. Product slices can carry scoped evidence; whole-gate readiness stays
blocked until the actual runtime failure is fixed and normal verification passes.

## Executed actual-owner isolation — 8 November

One temporary standalone Angular JIT fixture used the installed actual TuiRoot,
TuiTextfield/TuiTextarea, ReactiveFormsModule and public provideTaiga. No production
route, provider or dependency source changed. Build log
`/tmp/peerly-real-textfield-build1.log`; source `/tmp/peerly-real-textfield-source.mjs`.
The first launcher failed before creating a browser because its executable path
named an old task-local revision; the corrected runner used installed Chromium1254.
Actual run `/tmp/peerly-real-textfield-repro2.log` CLI0, diagnostics zero page errors
and zero console errors; artifacts `/tmp/peerly-real-textfield-repro2/`.

The single sequence attached the real field, filled text, captured full-page,
changed viewport1440×900 to1×1 and restored it, changed root font28 then17,
captured both sizes, retired the field through Angular, destroyed ApplicationRef,
and closed owned page before context. Transparent diagnostic wrappers recorded
native targets and writes without filtering errors.16 trace records:8 resize
deliveries and8 style writes. Actual foreign BODY1424→0→1424 and main-document
SPAN `.t-content`12→1→12 were observed; real host `--t-side`12px→1px→12px writes
occurred alongside unchanged root `--t-font-offset`0 writes. Root font changes
resized the actual span to21 then12.75. This establishes real component text
resizing, not native OS/browser font-setting coverage or proof of a watcher
callback for those inline root-font changes.

This is a negative reproduction with the actual previously missing observer
owner. It does NOT resolve the aggregate runtime failure or justify an idempotence,
rAF, dependency or cleanup patch. Exact skipped native target remains unknown.
No additional variant or broad suite rerun follows merely to seek failure. The
next actionable evidence gap is the actual failing frame's host `--t-side` write
ordering (excluded by the old trace regex), against all native observer targets.
Any future trace must be bounded to an existing failing scenario with raw native
errors retained; a new source correction still requires causal reproduction.
All owned server/browser resources were closed before returning the browser lease.

### Corrected global-style geometry control

Review of the repro2 PNG exposed missing global CSS: the actual component was
present but its span measured12×12, unlike the application's56px control. That
negative result was therefore not a representative layout control. One corrected
run loaded the existing production global stylesheet and its local font assets,
with no application/runtime source changes. It waited for document.fonts.ready
before interaction and recorded actual initial geometry24×56,font16px. During the
known viewport cycle the real span became1×56 then24×56; `--t-side`24→1→24 writes
and root offset0 same-value writes were observed. Root-font28→17 resized the span
to42×98 then25.5×59.5. Raw `/tmp/peerly-real-textfield-repro3.log` CLI0,16 trace
records, zero page/console errors; artifacts `/tmp/peerly-real-textfield-repro3/`.
The one styled control remains negative. No further standalone variant follows;
it neither closes the actual failure nor supports a dependency patch. Browser
lease END delivered. Halley's next action remains a bounded trace of the existing
failing frame including host --t-side writes that the previous regex omitted.

### One bounded actual-scenario owner trace

After the styled minimal control, Halley ran exactly one previously failing
Reports desktop child403 scenario using a temporary copied spec/config under
`/tmp/peerly-ro-side-trace`. Production source and the shared fixture were not
modified. Original two screenshot references were compared normally, NO updates;
strict existing browser/CLI diagnostics stayed enabled. A transparent preboot
ResizeObserver wrapper recorded constructor ownership stacks, targets, callback
begin/end and disconnect, plus layout style writes including the previously
missing --t-side. Target metadata includes only tags/classes/geometry, no content.

Actual run CLI0,1 case in8s, zero native/page/console errors. The new failure did
not reproduce.75 records:13 observers/observations/callback pairs,17 style writes
(including12 --t-side writes),6 explicit disconnects. Extracted trace
`/tmp/peerly-ro-side-trace/owner-trace-before-close.json`; raw
`/tmp/peerly-ro-side-trace/run1.log`. Native error capture array is empty. This
provides actual source/cleanup ownership on a clean execution, NOT ownership of
an unknown skipped target in a failing frame. No dependency/application fix is
proven; no second run or alternative probe follows this negative result. Browser
lease END delivered. The aggregate blocker stays open until a genuine failing
frame's target/write ordering is captured and a causal correction validated.
