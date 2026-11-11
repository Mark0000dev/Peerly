# Mandatory backend rules

## Architecture

- Python, FastAPI, PostgreSQL, SQLAlchemy 2.x, asyncpg. No synchronous I/O in request execution, workers, repositories, integrations, or use cases. Pure calculations, validation and object construction may stay ordinary `def`; adding `async` does not make blocking work safe.
- Depend inward: `presentation -> application -> domain`. Infrastructure implements application/domain ports. Only `bootstrap.py` composes concrete adapters. Domain and application must not import FastAPI, Pydantic, SQLAlchemy, asyncpg, settings, HTTP clients, or infrastructure.
- Keep observability SDKs out of domain/application code. Instrument use-case boundaries through adapters; persistence adapters attach execution correlation to durable events without making domain models depend on tracing.
- Domain holds framework-free entities, value objects, invariants and domain services. Application holds explicit use cases, immutable command/result DTOs and narrow async `Protocol` ports. Services have a specific business responsibility; do not create a generic service layer or CRUD base classes.
- HTTP adapters parse/validate Pydantic requests, invoke one use case and map its result/errors to HTTP. No business rules, queries, transactions or ORM objects in routes. ORM entities never escape persistence adapters.
- Keep related code by capability within each layer as real features appear. Do not create speculative abstractions. Domain and application tests must run without a database or web server.
- Import Linter checks these dependency boundaries. New modules must fit the contracts; do not solve violations with exclusions or dynamic imports.

## Async persistence and transactions

- URLs must use `postgresql+asyncpg://`. Only `create_async_engine`, `AsyncSession` and `async_sessionmaker`; SQLAlchemy expressions use `select`, typed `Mapped[T]` and `mapped_column`, with `DeclarativeBase`. No legacy `Column`, declarative_base, Session, Query or sync engine.
- One AsyncSession per transaction/task. Never share a session between concurrent tasks or run concurrent queries on the same session. Close sessions with async context managers and dispose the engine in application lifespan.
- A use case owns the transaction boundary through a narrow unit-of-work port when it writes. Repositories do not commit independently. Make atomic multi-write operations one transaction; propagate failures and roll back. Add a UoW implementation when the first writing use case exists.
- `expire_on_commit=False`; explicit flushes where needed. Prevent implicit relationship I/O with explicit eager loading or `lazy="raise"`. No N+1 queries, hidden lazy loads or serialization that touches expired attributes.
- Enforce uniqueness, foreign keys and invariants at the PostgreSQL boundary as well as validating commands. Use constraints and deliberate locking/isolation for races, not precheck-then-write alone. Social writes need idempotency keys and stable results before retries are enabled.
- Alembic revision DDL uses SQLAlchemy Core `Column` as required by `op.create_table`; the `mapped_column` requirement applies to ORM models. The narrow revision-only Ruff exception permits this schema API, not synchronous runtime adapters.
- Migrations use Alembic and an async engine. SQLAlchemy's documented `run_sync` bridge is allowed for migration metadata operations and isolated integration-test schema setup only; it is not a sync request adapter. No `create_all` at application startup.
- Use reviewed, reversible migrations where possible. Test upgrade from an empty database and migration effects on real PostgreSQL. Do not create dummy product tables or empty revisions to inflate the scaffold.
- Real external I/O must use async libraries, timeouts, explicit cancellation and bounded retries for transient idempotent operations. Never block the event loop with requests, file/network calls, CPU-heavy processing or time.sleep. Offload genuinely unavoidable blocking libraries at an explicit infrastructure boundary.

## Types, data and errors

- Strict mypy covers source, tests and migration environment. Type every function, including tests. No Any, casts hiding broken contracts, ignore_errors, blanket type ignores or untyped framework boundaries.
- Frozen, slotted dataclasses and immutable collections for domain/application data by default. Pydantic models are frozen by default. ORM objects and request-local sessions have intentionally controlled mutation inside infrastructure; never confuse ORM models with immutable domain models.
- Use aware timestamps, explicit timezone decisions, UUID identities and parameterized SQL. Do not concatenate values into SQL, log credentials or include private student content in ordinary logs/analytics.
- Translate expected infrastructure failures at the adapter boundary. Preserve cancellation. Never catch Exception broadly to return success or swallow programming errors. Use explicit domain/application errors with consistent HTTP mapping.
- Settings are validated at startup and credentials are secrets. No implicit SQLite fallback, production defaults for database credentials, global sessions, or module-import network calls.
- FastAPI lifespan owns resources. Factories and dependency injection keep app construction testable. Liveness is independent of PostgreSQL; readiness checks actual connectivity and returns 503 on expected unavailability.

## Tests and gates

- `uv sync --locked` installs pinned dependencies; `make check` runs Ruff, Ruff formatting, strict mypy, architectural contracts, unit tests and integration tests with branch coverage. No warnings, xfail/skip used to conceal required behavior, or relaxed thresholds.
- Maintain at least 95% combined branch-aware backend coverage. Coverage is a floor, not proof: test meaningful invariants, error paths, permissions, concurrency, idempotency, and transaction behavior for each implemented use case.
- Unit tests exercise domain/use cases with typed fakes. Test observable behavior rather than ORM internals or calls that mirror implementation. Adapter mapping tests may use ASGITransport; a real application integration test must enter its lifespan.
- Integration tests use real PostgreSQL through asyncpg. Never SQLite, mocked repositories, or mocked SQL execution as a substitute. Unit adapter error tests may mock failures explicitly.
- `TEST_DATABASE_URL` must point to a disposable database whose name ends in `_test`. Every persistence test uses a unique schema and cleans it afterward; no truncation of shared application databases. Missing PostgreSQL fails the integration run rather than skipping it.
- Migrations, constraints, commit/rollback, permission enforcement and races require integration coverage as their features are implemented. Test external services through controlled boundary doubles; do not call live AI/email from tests.
- CI runs the complete gate with a PostgreSQL service. Require its status for merging when remote branch protection can be configured. No commits/pushes until the user asks.

## Primary references

- https://fastapi.tiangolo.com/async/
- https://fastapi.tiangolo.com/advanced/async-tests/
- https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html
- https://docs.sqlalchemy.org/en/21/orm/declarative_tables.html
- https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic
- https://mypy.readthedocs.io/en/stable/existing_code.html
- https://docs.astral.sh/ruff/

## Current system design

Follow the proposed REST + SSE, transactional outbox, concurrency and deployment contracts in `../docs/architecture.md`, `../docs/api.md`, `../docs/database.md`, `../docs/observability.md` and `../docs/deployment.md`. Implement only the primitives required by actual use cases. The privileged operator interface can inspect every application record and relationship, including full chats/files, without a support-case restriction. Audit operator/target/time/correlation metadata; never the returned private content. Product endpoints still enforce their ordinary user permissions.
