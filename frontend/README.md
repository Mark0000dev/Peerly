# Peerly frontend

Mobile-first Angular22 application for APU students in Malaysia, using Taiga UI5,
TanStack Query and Capacitor8. FastAPI owns business rules and persistence.

## Run locally

Use the pinned Node24 version and npm10.8.2:

```bash
nvm install
nvm use
npm ci
npm start
```

The development UI is at `http://localhost:4200`. API-backed screens require the
configured backend through a same-origin `/api/v1` proxy; Angular CLI supports
`--proxy-config` for local development. Backend setup is in
[the backend README](../backend/README.md). Never put provider credentials in the
frontend or point tests at live student data.

The production build prerenders the public landing and emits static files to
`dist/studymate/browser`. Other application routes must fall back to
`index.csr.html`. The [nginx configuration](deployment/nginx.conf) implements this;
API routing belongs to the same-origin reverse proxy. There is no production SSR
process. Fonts are served locally; artwork provenance and font licences are under
`src/assets/brand`.

## Architecture and contracts

Read [AGENTS.md](AGENTS.md) before changing code. Screens own their templates,
queries, forms and tests. Server data belongs to TanStack Query, shareable selection
belongs to URLs, and unsent inputs belong to typed forms. Signals hold necessary
presentation or native-resource state only. Credentials are never persisted in
browser storage.

Google sign-in and institutional-mail verification are separate steps. The server
controls membership, visibility, request/chat permissions and AI availability.
AI failures must leave manual study flows usable. Notification preferences do not
claim that native/background push delivery exists.

After a backend contract change, prepare its locked Python environment and run:

```bash
npm run contracts:generate
npm run contracts:check
```

The backend's deterministic enabled-feature OpenAPI exporter supplies
`contracts/openapi.json` and deeply readonly `src/app/api.generated.ts`. Do not
handwrite future endpoints or infer contracts from the default health-only app.
Private JPEGs use the shared authenticated transport and view-owned resource
cleanup. CSRF, idempotency and uncertain-write recovery remain explicit.

## Checks

```bash
npx playwright install --with-deps chromium webkit
npm run check
```

The gate includes formatting, strict TS/template lint, styles, Knip, contract drift,
type checks, tooling regressions, Chromium unit tests with95% coverage, production
build, browser screenshots and real FastAPI/PostgreSQL integration. Full-stack
checks require the repository's disposable PostgreSQL and locked backend
environment; they use unique schemas and controlled provider boundaries. See
[testing](testing/README.md). Run heavy browser suites serially.

Initial bundle warning/error limits are both550kB; component-style limits are both
4kB. Warnings and failing diagnostics are not waived by these budgets.

## Native packaging

```bash
npm run native:add:android
npm run native:add:ios
npm run native:sync
```

Add platforms once. Android needs its supported SDK/JDK; iOS needs macOS/Xcode.
Web output is not native-device acceptance. Device authentication, keyboard/media
behavior and background delivery require separate platform validation.

## Known acceptance limits

The complete design-v2 screen/state comparison and refreshed screenshot matrix
are unfinished. Existing goldens are regression evidence, not design compliance.
Native ResizeObserver diagnostics remain unresolved and their runtime guard is
retained. Current viewport-layout changes still require the remaining consumer,
chat-compatibility and normal-comparison acceptance. Do not present internal
preview readiness as full frontend, native or external-user acceptance.

The only dependency source correction is the pinned font-watcher border fix;
[provenance and removal criteria](patches/README.md) are part of its maintenance.
