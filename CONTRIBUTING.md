# Contributing to Peerly

Create a focused feature or fix branch from `main`, then open a pull request back
to `main`. Keep the PR reviewable: describe the problem, resulting behavior,
relevant validation and remaining limitations. Link an issue when one exists.
Merge after review and the required checks; delete the merged working branch.

Read [AGENTS.md](AGENTS.md) and the rules for the component you change:
[backend](backend/AGENTS.md) or [frontend](frontend/AGENTS.md). Keep backend
contracts, generated frontend types and documentation consistent. Coordinate
schema changes and use Alembic migrations rather than editing deployed tables.

## Local setup and checks

Use Node from `frontend/.nvmrc`, npm from `frontend/package.json`, Python from
`backend/.python-version`, and the locked dependencies. Docker Compose supplies
the disposable PostgreSQL test service; uv prepares the Python environment.

From the repository root:

```sh
docker compose up -d --wait postgres-test
(cd backend && uv sync --locked)
(cd frontend && npm ci && npx playwright install --with-deps chromium webkit)
export TEST_DATABASE_URL=postgresql+asyncpg://studymate:studymate@localhost:5433/studymate_test
sh scripts/check.sh
```

The database credentials above are only for the local disposable test service.
Do not point tests at development, staging or production data. Browser installation
also installs required host libraries and may request local administrator access.

For a component-specific full gate:

```sh
(cd backend && make check)
(cd frontend && npm run check)
```

Use focused checks while implementing, then run the relevant complete gate before
handoff. Do not substitute a passing subset for full acceptance. See
[testing](docs/testing.md) for coverage floors, screenshot requirements, fixture
behavior and known limitations. Report failures plainly; do not relax checks or
regenerate baselines just to make them pass.

## Pull requests and data safety

- Use short imperative commit messages, such as `Add support status history`.
- Add meaningful regression coverage alongside behavior changes. Keep API and
  migration compatibility explicit in the PR.
- Commit reviewed source and approved assets, not local reports, private design
  packages, environment files, credentials, database dumps or live user data.
- Keep private content and credentials out of logs, screenshots and PR examples.
  Use synthetic fixtures for demonstrations and tests.
- Deployment, live provider calls and messages are separate operations; merging
  code does not authorize them or establish that a service is running correctly.
