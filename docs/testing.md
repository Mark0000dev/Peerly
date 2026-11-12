# Testing

Peerly requires strict static checks, meaningful unit tests and integration tests.
Passing a build or a focused test file does not establish full application
acceptance. The component rules in [backend/AGENTS.md](../backend/AGENTS.md) and
[frontend/AGENTS.md](../frontend/AGENTS.md) define the detailed contracts.

## Run the gates

Follow [CONTRIBUTING.md](../CONTRIBUTING.md) to install locked dependencies,
Chromium/WebKit host libraries and the disposable PostgreSQL service. From the
repository root, with the local test database available:

```sh
export TEST_DATABASE_URL=postgresql+asyncpg://studymate:studymate@localhost:5433/studymate_test
sh scripts/check.sh
```

The script runs frontend `npm run check`, then backend `make check`, stopping on
failure. Run either component command directly to diagnose its gate. Unit and
integration subsets are useful during development but do not replace full gates.

## Backend

`make check` runs Ruff lint/format checks, strict mypy, import-boundary contracts,
and unit plus real PostgreSQL integration tests with combined branch-aware
coverage. The configured minimum is **95%**. Keep tests focused on observable
behavior, including authorization, concurrency, transaction rollback, idempotency
and failure paths; coverage alone does not prove those properties.

Integration tests use asyncpg and a disposable database whose name ends in
`_test`. Each owns a unique schema and removes it afterward. Tests fail when the
database is unavailable; SQLite, mocked SQL or shared-data resets cannot replace
real persistence acceptance. Exercise migrations and constraints against actual
PostgreSQL. External services use controlled test boundaries, not live credentials.

## Frontend

`npm run check` verifies the approved dependency patch, actual backend OpenAPI
contracts, formatting, TypeScript/template lint, styles, unused code/dependencies,
types, tooling tests, unit coverage, production build and browser scenarios.
Angular/Vitest units run in real headless Chromium. **Statements, branches,
functions and lines must each reach 95%**, including application files without
tests. Preserve strict types, zero-warning checks and committed build budgets.

Public/prerender, application integration and full-stack browser scenarios require
behavioral assertions plus named screenshot checkpoints. Required projects are
mobile Chromium, mobile WebKit and desktop Chromium. Compare committed baselines
in the supported pinned Linux/browser/font environment. Missing or changed images
fail normal runs; CI must not update references automatically. Review intentional
visual changes and their baselines together. Existing screenshot matches prove
regression consistency, not independent compliance with a design specification.

The full-stack matrix uses real FastAPI and PostgreSQL on loopback port 5433,
fresh migrated schemas, ephemeral TLS and genuine secure-session/browser rules.
Its six invocations isolate the three browser projects and two support cohorts
without changing production source quotas. Google, email, media and AI boundaries
are controlled fixtures, so these tests do not establish live provider delivery.

Use the existing browser runner and cancellation contract. Do not hide native
errors, disable host validation, skip an engine, add retries or lower screenshot
tolerances to obtain acceptance. Preserve raw command output, failure traces,
expected/actual/diff images and coverage reports. Keep evidence synthetic and free
of credentials or live private content.

## Current limitations

An aggregate browser ResizeObserver diagnostic remains unresolved; it must remain
visible and fail strict browser acceptance when encountered. The proposed complete
frontend quality gate before image publication has not yet been accepted. Current
image build/smoke success is therefore not evidence of full frontend acceptance.
Live provider and native-device checks remain separate from fixture-based gates.
