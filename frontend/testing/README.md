# Frontend testing

Use the pinned Node/npm/Playwright versions and install Chromium/WebKit system
libraries with `npx playwright install --with-deps chromium webkit`.

```bash
npm run test:tooling
npm run test:unit
npm run build
npm run test:public
npm run test:integration
npm run test:fullstack
```

`npm run check` combines these with contract drift, format, lint, unused-code and
type checks. Unit coverage requires95% across application code. A passing build or
scoped scenario set does not establish complete acceptance.

Browser cases import test/expect from `testing/visual`. Each implemented scenario
requires behavior checks and a named checkpoint. Golden PNGs/JPEGs live beside
`*.visual.spec.ts`; generated unit-failure images are diagnostic artifacts, not
baselines. Review intentional changes using `npm run test:integration:update` and
the report; normal runs and CI never approve new images automatically.

Use real screens and deterministic boundary responses for races/failures. Full-stack
fixtures additionally start real FastAPI, migrate/seed a uniquely named disposable
PostgreSQL schema and use same-origin loopback services. Prepare the locked backend
virtualenv and repository test database on5433. Do not use live credentials/providers
or reset shared databases. Owned servers/sessions/schemas must be cleaned up on every exit.

Run browser suites serially when sharing a memory-bounded fixture. The optional
`STUDYMATE_WEBKIT_WS_ENDPOINT` connects to an official matching Playwright run-server;
normal local browser launch remains the default. `STUDYMATE_TEST_PORT` isolates the
frontend fixture from an ordinary development server. Do not skip host validation.

The gate preserves cancellation/failure status and checks forwarded Vite/application
errors after page teardown as well as native JS/rejection/console diagnostics.
ResizeObserver is never exempted. Keep failed runs, diffs, traces and uncompleted
partitions visible in acceptance records; do not retry blindly or lower assertions.

For WebKit TuiPreview OPEN/ZOOM only, `webkit-preview-frame.mts` uses pinned public
Playwright screencast capture. Three fresh independently started full-viewport frames
must be byte/dimension identical before strict JPEG comparison. Preserve standard PNG
artifacts and source/viewport/keyboard/overflow checks. No stale frames, masks, scaling,
private protocol or relaxed pixel thresholds; other states/engines retain normal PNG.

Open scrollable dialogs may compare separate intact viewport checkpoints for their
heading/content and actions while retaining a full-document raw artifact. Assert actual
focus, scrolling, geometry and source content; raw artifacts are not visual comparisons.
Original design references remain a separate fidelity review, not project goldens.
