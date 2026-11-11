# StudyMate frontend

Angular 22, strict TypeScript, Taiga UI 5, TanStack Query and Capacitor 8. Mobile first, English interface. Backend stays Python / FastAPI.

## Local development

Use the Node version in `.nvmrc` (Node 24 LTS). The system Node 18 cannot run this toolchain.

```bash
nvm install
nvm use
npm ci
npm start
```

Open http://localhost:4200. Peerly v2 includes the public landing, published Terms/Privacy reader, honest Help and actual Google/institutional-email onboarding. Only `/onboarding` bootstraps private session data into TanStack Query; the landing stays public. Verified actors can edit real profile-name and canonical/custom study-goal drafts and ordered helper-subject selections. Final registration, photo setup and visibility/freshness UI remain in progress against actual backend contracts. Current acceptance and limitations are recorded in `../docs/planning/frontend-progress.md`.

## Mandatory quality gate

Read [AGENTS.md](AGENTS.md) before editing code.

```bash
npm run format
npm run check
```

`check` runs Prettier, ESLint with typed TypeScript and Angular template/accessibility rules, Stylelint, Knip, TypeScript checking, quality gate regression tests, Vitest unit tests with a 95% coverage floor, a production Angular build, mandatory Playwright screenshot scenarios, generated-contract drift and full-stack FastAPI/PostgreSQL scenarios. ESLint checks readonly fields, readonly data types, mutation, unsafe code, import cycles and imports between screens. Stylelint rejects important, deep selectors, internal Taiga classes, hex colors and pixel units in application styles. `src/theme.less` defines the approved palette through public Taiga tokens and the narrowly enumerated semantic tokens/appearances. Automated checks do not prove accessibility or replace review of WET and design choices.

Husky installs repository hooks on `npm ci`; both commit and push run the complete gate. CI runs it on pull requests and pushes. Remote branch protection must require the CI job when repository administration becomes available. Hooks are bypassable, so enforcement ultimately depends on protected branches.

Knip's explicit dependency exceptions are Capacitor's core and platform packages (discovered by the native CLI) and Taiga's icons (copied through Angular's asset configuration). Angular-owned peer packages are accounted for by Knip's Angular plugin. Add no broad ignores.

## Native packaging

```bash
npm run native:add:android
npm run native:add:ios
npm run native:sync
npm run native:android
npm run native:ios
```

Add each platform once, then sync after web changes. `webDir` matches Angular's `dist/studymate/browser`. Application ID is a development default; confirm it before distribution. Native project generation is deferred until native work starts.

Android requires Android Studio and the Capacitor-supported JDK/SDK. iOS builds require macOS and Xcode. Web compilation does not verify native builds. Configure an HTTPS backend endpoint for devices when API integration is implemented; the development web origin is not a production backend URL.

## Scope and specification

The user-supplied `../Study_Partner_MVP_Design_Specification.docx` lives outside the repository (relative to the repository root) and must not be staged or committed. Latest owner decisions supersede older documents: personal Google login plus separate verification of `mail.apu.edu.my`, profile and study goal, Discover, explicit Requests, and one Chat per pair. No groups, sessions, streaks or percentage matching. AI assistance is required in the MVP but optional for users and cannot block core flows. Configured identity endpoints are implemented and tested locally; proposed API tables are not proof that every endpoint exists.

FE-01 preparation is complete; v2 theme and actual FE-02 screens follow the [design review](../docs/design-review-v2.md), with current evidence and remaining scope in the [frontend ledger](../docs/planning/frontend-progress.md). Generate contracts from the coordinated authentication/media-enabled exporter rather than the default health-only app. Do not add unused API services before their genuine consumers exist.

Screen code is colocated under `src/app/screens/<screen>/`. Keep duplication for one or two consumers; extract at the nearest common parent when a third real consumer appears. Query cache owns server data, router owns URL state, forms own drafts, and signals own only necessary local UI state.

TanStack's Angular adapter is experimental and pinned to an exact version. Automatic retries are disabled globally: queries may opt into bounded transient retries explicitly; social writes need idempotency and deliberate retries. No server state is copied into another store.

## Dependency audit

The current install reports upstream moderate tooling advisories rooted in `minimatch`. The reviewed, consumer-compatible scoped `deepmerge-ts` correction and remaining incompatible-major limitation are documented below. No audit exclusion or forced framework downgrade hides these findings; reassess upstream fixes before distribution. `npm run check` is a code quality gate, not a dependency security certification.

## Unit and screenshot integration tests

Install the pinned Chromium/WebKit builds and their system libraries before running the full gate:

```bash
npx playwright install --with-deps chromium webkit
npm run test:unit
npm run test:integration
```

Unit tests run through Angular CLI/Vitest in real headless Chromium. Browser integration runs the actual application on mobile Chromium, mobile WebKit, and desktop Chromium. Current suites cover public pages, published documents, auth bootstrap/OTP recovery and real FastAPI/PostgreSQL identity, delivery, logout and policy reads. Exact current counts and outstanding states are in the ledger. Every passing scenario must call the screenshot checkpoint fixture; behavioral assertions remain required. See the colocated [scenario matrix](src/app/screens/home/SCENARIOS.md).

Reference images are colocated under the screen's `__screenshots__` directory. Normal test runs fail on missing or changed references. Baselines were created on Ubuntu 24.04 with the exact locked Playwright/browser versions; CI uses the same OS release and browsers. Render changes across system/font updates require explicit review. Inter and M PLUS Rounded 1c are served locally from pinned font packages; no Google Fonts network request is required. The seven declared faces use the packages’ exact WOFF2 binaries; legacy WOFF fallbacks are omitted for the supported Angular/Capacitor browsers. Families, weights and swap behavior remain identical. Knip6’s Less compiler follows `@import` rather than font `src: url(...)`, so these two asset-only dependencies have exact named exceptions. `tooling/font-assets.test.mjs` rejects an exception without a real stylesheet consumer, a pinned package and readable WOFF2 bytes. Remove the exceptions when Knip recognizes these asset references; configuration hints remain fatal.

To deliberately create or update references:

```bash
npm run test:integration:update
npm run test:integration:report
```

Inspect every changed PNG and the report. CI never accepts new references automatically. Error screenshots, diffs and traces are uploaded as CI artifacts. Screenshots of the shell do not claim coverage for unimplemented pilot screens; each new screen must ship its complete scenario matrix and tests.

Repository hooks run both frontend and backend gates through `scripts/check.sh`. Have the disposable test PostgreSQL service running and `TEST_DATABASE_URL` configured before an authorized working-branch commit. Shared-checkout commits/staging/branch changes remain parent-coordinated; never commit or push main.

## Actual backend contracts and full-stack checks

Prepare the locked backend environment first (`uv sync --locked` from `../backend`). Contract tooling invokes that environment's Python directly and runs the backend-owned `studymate.export_openapi` module with synthetic enabled-auth/media configuration. No database or provider connection is made during export.

```bash
npm run contracts:generate
npm run contracts:check
```

Review both `contracts/openapi.json` and `src/app/api.generated.ts` after backend changes. The generator supports the current OpenAPI 3.1 subset and rejects unsupported keywords/references instead of silently weakening DTOs. It preserves nested readonly objects, arrays, maps, unions, optional request properties, actual paths/statuses and headers. Numeric/string validation constraints remain server-enforced and retained in the JSON snapshot. The empty readiness schema correctly generates `unknown`, not an invented response DTO. `openapi-typescript` was evaluated but its current TypeScript 5 peer constraint conflicts with the pinned TypeScript 6 toolchain; no forced resolution or dependency downgrade was used.

`npm run check` also requires the repository's disposable PostgreSQL service on port 5433 (`docker compose up -d --wait postgres-test` from the repository root). Full-stack fixtures use only its explicit synthetic credentials and a uniquely named schema. They migrate and seed synthetic sessions and published fixture documents, start real FastAPI and a same-origin Angular proxy with ephemeral loopback TLS, and clean up afterward. Existing application tables and live providers are untouched. The local TLS certificate is trusted only by the controlled Playwright contexts; production TLS settings are unaffected.

```bash
npm run test:fullstack
STUDYMATE_FULLSTACK=1 npm run test:integration:update
```

Full-stack screenshot references are separate from HTTP-boundary fixtures. Normal full-stack runs never update references. Real Google-entry/callback and durable email delivery/verification use controlled provider boundaries with actual FastAPI/PostgreSQL behavior. They do not establish live Google/SMTP compatibility or native credential exchange.

### Task-local WebKit runtime

The host's extracted libraries restored actual WebKit launch and individual scenarios, but the task-local PRoot workaround proved unstable during repeated Node trace-file writes. It is not the accepted combined-gate runtime. No system packages, browser code, traces or dependency checks were disabled.

Use a loopback Playwright run-server from the official matching Playwright image. The image contains the actual required browser libraries, so standard host validation runs inside it. From the frontend directory:

```bash
docker run --rm --name studymate-webkit-fixture \
  -p 127.0.0.1:8879:8879 --shm-size=512m --memory=1536m \
  --mount "type=bind,source=$PWD,target=/workspace,readonly" -w /workspace \
  mcr.microsoft.com/playwright:v1.65.0-noble@sha256:6e3fb709361521eb27161606e6da6d2674e5e89fa16516cb37d6fdd91372273d \
  node node_modules/playwright/cli.js run-server --host 0.0.0.0 --port 8879
```

Set `STUDYMATE_WEBKIT_WS_ENDPOINT=ws://127.0.0.1:8879/`, then run the normal gate on the host under Node 24. Only the WebKit browser runs in the container; `exposeNetwork: '<loopback>'` forwards its local application requests through the test client. Without that variable standard local Playwright launch is unchanged. This is an ephemeral test fixture with the application source mounted read-only, not an application deployment. Stop the owned container with `docker stop studymate-webkit-fixture` after validation. Run browser suites sequentially against this shared memory-bounded fixture: simultaneous runners exhausted the original768MiB limit. Isolated30-scenario runs initially passed, but a later isolated33-scenario run triggered a Docker-confirmed OOM, removing the owned container. After checking the3.821GiB Docker VM budget, its task-local limit was raised to1536MiB; production limits are unaffected. Fresh normal acceptance after restoration is recorded in the ledger. Keep assertions/timeouts/retries intact; a crashed/OOM run is a failure, not acceptance.

### CI coordination

The parent updated `.github/workflows/frontend.yml` locally: PostgreSQL 16.15 exposes the disposable test database on port 5433; setup-python uses `backend/.python-version`; pinned setup-uv prepares the locked backend virtualenv before the frontend gate. Standard CI retains `playwright install --with-deps` and local browser launch. The remote-container variable is only needed for this workstation's missing host packages. Workflow formatting/diff checks passed; remote GitHub Actions execution has not been verified. The frontend worker did not edit the shared workflow.

### V2 static public output

The production build prerenders `/` into `dist/studymate/browser/index.html`.
Non-prerendered application routes must fall back to `index.csr.html`, not the landing document.
There is no production SSR process. `npm run test:public` serves actual build artifacts and checks
landing content/navigation with JavaScript disabled, with screenshots in every browser project.
The build must run first; `npm run check` includes this sequence.

V2 uses local Inter and M PLUS Rounded 1c fonts; redistributed OFL files and curated static SVG
provenance live in `src/assets/brand/`. Auth queries/mutations use public TanStack observers,
Angular HttpClient and generated actual DTOs. Screen data and pending/error states remain in the
query/mutation cache; only form drafts and local presentation choices are client-owned.

### Temporary font-watcher source correction

`patches/@taiga-ui+font-watcher+0.6.0.patch` adds only `border: '0'` to the
watcher-owned iframe's source styles, in both distributed ESM and CommonJS implementations.
The wrapper exports and types stay unchanged. Taiga's public font scaling remains enabled.
The original iframe width equals the viewport width; native borders add four pixels of overflow
at narrow widths. This is a source defect, not a theme override.

Upstream reference: [font-watcher source](https://github.com/taiga-family/utils/blob/main/projects/font-watcher/index.ts).
Installed version is explicitly pinned by npm override. Original/patched SHA-256 hashes for every
distributed entrypoint are in `tooling/font-watcher-hashes.json`.
[patch-package](https://github.com/ds300/patch-package) is pinned to 8.0.1. `npm ci` applies the
tracked patch and fails on a version/hash mismatch or patch failure; `npm run check` also verifies
the installed result, so ignored install scripts cannot silently bypass the correction.
No install script downloads a replacement source or an unpinned package.

Remove the patch, override, verifier and regression fixtures together only after upgrading to an
upstream version that fixes border sizing and passes the same 320px/200%, font-scaling and teardown
checks. ResizeObserver diagnostics are investigated separately; this border-only patch does not
claim to fix unrelated observer feedback.

### Isolated browser-test origin

Playwright uses loopback port4317 by default, independently of the ordinary development server4200.
Set `STUDYMATE_TEST_PORT` to an available1024–65535 port for an isolated run. The same value controls
static/dev servers, browser base URL and the full-stack fixture's configured HTTPS callback origin.
The full-stack driver derives cookie/CSRF origins from that base URL; production `/api/v1` same-origin
behavior is unchanged. This avoids stale development HMR clients contaminating fixture logs.
The fixture backend itself remains loopback8768 and uses its unique disposable PostgreSQL schema.
No existing personal browser tabs/processes are inspected or closed by this workflow.

The shared browser gate records native JS errors, unhandled rejections and application console errors,
then drains rendering before acceptance. Browser resource diagnostics are classified separately only
when their exact API URL has an observed HTTP/request failure; runtime messages such as ResizeObserver
are never exempted. JavaScript-disabled static checks retain screenshots/content assertions and do
not await a JavaScript rendering callback.

Browser commands run through `tooling/browser-gate.mjs`, which preserves raw stdout/stderr and fails
forwarded Vite unhandled/application-console errors even if they occur after a target detaches and
Playwright itself exits0. It preserves runner failure codes, forwards cancellation only to its owned
process group, applies a 10 minute suite limit and allows 15 seconds for graceful termination, exceeding the backend fixture’s 10 second cleanup window. No private
log artifact is created by the gate. Regression tests exercise fragmented/EOF diagnostics, ordinary
resource output, runner failures, cancellation, failed spawn and timeout escalation.

Owned test pages are closed before final runtime assertions/context disposal. A task-local40-context
probe observed one late ResizeObserver diagnostic after context-only disposal and none after ordered
page/context disposal; this supports a teardown association, not a proven production scheduling bug.
Raw synthetic reproduction logs remain under `/tmp/peerly-lifecycle-*` for this task. The dependency
patch remains border-only; there is no console-error exemption for ResizeObserver.

The current enabled export includes35 unique paths (auth, media, profile, goals, help subjects, catalogue, onboarding status, visibility and hard-disabled AI job HTTP contracts). JSON DTOs remain deeply readonly; the actual private
JPEG response is represented as `Readonly<Blob>`. Unknown or mixed media types still fail generation.
Tagged subject unions require an exact local reference mapping and matching literal tags. Request
tags stay required; actual response defaults remain optional, without injected values. Unsupported
discriminator shapes fail generation. Compile-time tests verify readonly narrowing of both branches.

The photo workflow is in progress against actual31, including owner-only resume metadata. Signed
access fields are confined to an imperative transfer call, never Query/Mutation cache or persistent
storage. Native selected/cropped bytes must match the existing intent fingerprint before reuse.
Reload does not restore a file or silently send one. Current acceptance/remaining scenarios live in
`src/app/screens/onboarding/profile/photo/PHOTO-SCENARIOS.md` and the frontend progress ledger.

The full-stack fixture disables observability and replaces external Google/email/storage boundaries.
It upgrades a unique PostgreSQL schema to current Alembic head, keeps real auth/persistence/photo
worker/image processing, and runs task-owned loopback HTTP8768 plus HTTPS8769 storage with ephemeral
TLS. Real browser multipart reaches the controlled storage endpoint directly in every engine;
WebKit interception cannot reliably expose its binary post body. Fixture storage allows only the
frontend fixture origin, rejects application cookie/CSRF headers, and never contacts S3. Both owned
servers and the image processor close before schema/TLS cleanup; shared PostgreSQL is preserved.
The driver may trigger one serialized real photo-worker step; no fixture endpoint exists in production.
This proves local composition, not external S3/presigning/CORS or native OS camera compatibility.

FE03 includes actual profile/name, canonical/custom goal, help and owned photo upload/crop/resume
consumers. FE03.5 now adds an explicit Your study setup entry: server readiness, first-task CAS,
issued compact registration notice/versioned links, explicit completion and profile visibility.
These are incremental slices, not full product/native/provider acceptance. See the separate
frontend ledger and colocated scenario matrices for current tested snapshots and remaining cases.
Generating AI types does not implement an AI screen; the executor is still truthfully unavailable.

The current deterministic enabled export has54 unique paths/61 operations, source SHA256
`d85683a39dbf3e24b65f38f1a7d916a90de6cc06560ba36f3c4aa28ccc59c7cf`.
The earlier nickname actual31 represented30 unique paths: GET beside an existing POST does not
create another path. Historical labels remain beside their exact evidence. Person and Discovery
have separately recorded scoped browser/PostgreSQL acceptance. Requests is delegated under
REQUESTS-HANDOFF.md with the same shared transport/session/query infrastructure and real driver
seeds; it has not yet received browser/PG acceptance. No fake contact/chat destinations are added.

The last ordinary aggregate passed619 units and339 boundary assertions but failed the unchanged
runtime CLI guard on native ResizeObserver diagnostics; PG phase did not start. This remains open
in RUNTIME-DIAGNOSTICS.md. Later full-unit-only checkpoints and scoped visual/PG runs do not prove
that global runtime issue fixed. Do not repeat the aggregate without concrete fix/new causal evidence.

Production warning and error budgets are equal:525kB initial and4kB per component style. The owner explicitly approved the initial-budget increase from500kB after a measured504.04kB build and attribution to legitimate shared Angular forms/common dependencies. Exceeding either limit still fails the CLI; no warning exemption. Future increases require measured evidence and explicit user approval. See [bundle-budget evidence](BUNDLE-BUDGET.md).

### Tool dependency security notes

The functional lint plugin10.0.1 uses an exact scoped override of deepmerge-ts8.0.0 for
[GHSA-ggr8-5vv4-36mx](https://github.com/advisories/GHSA-ggr8-5vv4-36mx). Its plain-record rule-option
merges were compared against7.1.6 using this repository's ESLint rules. The upstream8.0.0 Map
merging change is not used by those option/schema calls. Keep strict lint and negative-rule tooling
checks enabled; remove this override when the pinned parent supports the fixed dependency itself.
A clean npmci must still apply and hash-verify the separate font-watcher correction.

The latest audit still reports the minimatch amplification advisory
[GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249) through lint/migration tooling.
Do not blindly force minimatch11: it removes makeRe/AST, and installed import-x still calls makeRe.
Track compatible upstream consumer updates; no audit exception or framework downgrade is applied.
This is not a zero-vulnerability claim. Browser build graph checks distinguish tooling dependencies
from shipped application inputs; repeat that check after dependency or entrypoint changes.
