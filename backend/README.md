# Peerly backend

Async FastAPI, PostgreSQL/asyncpg, typed SQLAlchemy2 and Alembic. Framework-free
domain/application use cases and inward dependency contracts keep business rules
separate from HTTP/storage/SDK adapters. Read [coding rules](AGENTS.md),
[architecture](../docs/architecture.md) and [API](../docs/api.md).

Capabilities include Google login plus institutional verification/registration,
profiles/goals/help/catalogue/photos, Discovery/Requests, accepted chats/images/
SSE, safety/lifecycle/feedback/support/preferences, privileged inspection/human
review, typed AI jobs and transactional observation/delivery sources. Feature
implementation and internal staging are not final provider/design/native release
acceptance; see [testing](../docs/testing.md) and [deployment](../docs/deployment.md).

## Local setup

From repository root start development/test PostgreSQL:

```bash
docker compose up -d --wait postgres postgres-test
```

From backend:

```bash
uv sync --locked
cp .env.example .env
make run
```

Set DATABASE_URL to the explicit asyncpg database; there is no SQLite fallback.
Authentication/media/AI/provider/export configuration is explicit and secrets stay
outside source. Python is pinned by .python-version; dependencies by uv.lock.
Liveness `/api/health` is independent of DB; `/api/ready` checks connectivity.

## Contract and checks

```bash
uv run python -m studymate.export_openapi --output /tmp/peerly-openapi.json
export TEST_DATABASE_URL=postgresql+asyncpg://studymate:studymate@localhost:5433/studymate_test
make check
```

The exporter builds actual enabled routes with synthetic configuration and no
network/DB credentials; use it for generated frontend contracts. `make check`
enforces strict Ruff/format/mypy/import contracts and unit/realPG tests with95%
branch-aware coverage. `make test-unit` needs no DB; integration tests own unique
schemas in a disposable `_test` database. Do not reset another process's schemas.
Operational helpers under deployment/backend use the same enforced strict rules.

## Migrations, reference data and workers

```bash
uv run alembic upgrade head
uv run python -m studymate.bootstrap_data_cli schema
uv run python -m studymate.bootstrap_data_cli validate OWNER_INPUT.json
```

Only apply real versioned owner input with an explicitly configured target DB.
No startup table/account/role/policy seeds. Published migrations/documents are
immutable; retained source facts can correctly forbid downgrade. Back up, review
actual head/ownership and prefer forward fixes over deleting business history.

Separate entrypoints use their own explicit settings:
`studymate.email_worker`, `studymate.media_worker`, `studymate.requests_worker`,
`studymate.changes_worker`, `studymate.external_delivery_worker`,
`studymate.ai_worker`. See versioned env examples and deployment templates.
Workers have no invented --help parser; configured startup can perform real
work, so never use it as a harmless configuration probe against real providers.
No SQL connection remains held during inference/storage/network calls.

AI uses a dedicated isolated image/gateway/cache/receipt lifecycle, never the
developer's login or shared account. It is optional for the user and cannot block
core application flows. See [AI boundaries](../docs/ai.md). Logs/traces use explicit
privacy-safe schemas; business private content stays in its authorised store.
