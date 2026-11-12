# Peerly repository rules

Read [backend/AGENTS.md](backend/AGENTS.md) before backend changes and
[frontend/AGENTS.md](frontend/AGENTS.md) before frontend changes. Their architecture,
typing, styling and testing rules are mandatory. Use [CONTRIBUTING.md](CONTRIBUTING.md)
for the contribution workflow and [docs/testing.md](docs/testing.md) for checks.

## Architecture and contracts

- Backend: Python, FastAPI, PostgreSQL, SQLAlchemy 2.x and asyncpg. Dependencies
  point inward from presentation through application to domain; infrastructure
  implements ports and the composition root wires adapters. Keep framework,
  persistence, HTTP and observability SDKs out of domain/application code.
- Frontend: standalone Angular, Taiga UI, TanStack Query and Capacitor. Server
  state belongs to TanStack Query, shareable navigation to the URL, editable
  drafts to typed forms. Follow the frontend rules for public component APIs,
  immutable data and local state. Do not introduce a competing UI or state system.
- Generate frontend API types from the actual backend OpenAPI contract. Do not
  maintain parallel handwritten DTOs or hide contract drift with casts/defaults.
  Keep [docs/api.md](docs/api.md) consistent with implemented behavior.
- Preserve the same-origin `/api/v1` browser contract, secure session cookies,
  Origin/CSRF protection, cancellation and actor-scoped authorization. Do not
  invent authentication, delivery capabilities or successful provider outcomes.
- Use async I/O with bounded timeouts and cancellation. Transactions, constraints,
  deliberate lock ordering and idempotency must protect concurrent writes; do not
  rely on a precheck alone or retry non-idempotent operations blindly.
- Schema changes use reviewed Alembic revisions and real PostgreSQL acceptance.
  Preserve released migration history and one coherent head. No application
  `create_all`, ad-hoc replacement schemas or duplicate identity registries.
- Implement concrete capabilities rather than speculative platforms or generic
  service layers. Keep changes scoped and coordinate shared contracts before
  changing their consumers.

## Identity, privacy and security

- Google OIDC identity is issuer/subject, not an email address. Institutional
  email verification is a separate membership proof, never a standalone login.
  Do not silently activate, merge or rebind accounts, fabricate OTP success, or
  bypass public authentication through an administrative path.
- Soft deletion revokes access and public visibility while retaining historical
  business records and analytics. Fresh registration creates a distinct account
  and requires fresh proofs; do not restore old sessions, content ownership or
  permissions. Preserve active-claim uniqueness and identity-lineage ban checks.
- Privileged operators may inspect all retained application records and
  relationships through authenticated, authorized and audited business-storage
  reads. Do not add a support-case gate or bypass ordinary student permissions.
  Record access metadata, not returned private content, in audit/telemetry.
- Keep student messages, drafts, support bodies, prompts, raw errors, passwords,
  tokens and verification codes out of ordinary logs, analytics and alerts.
  Canonical server-committed events and client observations have different trust;
  client-provided actor IDs never establish authority.
- External product delivery has two sinks: Umami analytics and metadata-only
  Telegram support notices. Technical alerts belong to Prometheus/Alertmanager.
  Provider failure must not block core product operations. Do not claim exactly
  once delivery where retries or ambiguous network outcomes prevent that claim.
- Never commit credentials, `.env` files, private keys, service-account data,
  developer environment exports or live user data. Use synthetic test fixtures;
  redact diagnostic output and inspect secrets only for an explicitly authorized
  operation. Repository access alone does not authorize live messages, provider
  calls, deployment or infrastructure changes.
- Keep supplied design/specification packages and private execution artifacts
  outside product source. Use approved assets and public UI APIs; do not copy
  external package instructions, credentials or developer tooling into the repo.

## Quality and truthful delivery

- Preserve strict lint, formatting, type and dependency-boundary checks. Use
  immutable domain/application DTOs and readonly frontend data. Do not silence
  warnings, weaken types or add broad exclusions to obtain a green result.
- Backend combined branch-aware coverage must remain at least 95%. Frontend unit
  statements, branches, functions and lines must each remain at least 95%,
  including application files without tests. Test meaningful behavior as well as
  permission, failure, cancellation, concurrency and replay boundaries.
- Persistence integration tests use real disposable PostgreSQL databases ending
  in `_test`, unique schemas and cleanup. Never reset shared/deployed data, use
  SQLite as a substitute, or skip required tests when the database is unavailable.
- Every frontend integration scenario needs behavioral assertions and a named
  screenshot checkpoint. Preserve required mobile Chromium, mobile WebKit and
  desktop Chromium projects, committed baselines and strict runtime diagnostics.
  Do not update baselines automatically in CI, filter ResizeObserver errors or
  mask meaningful content to pass a comparison.
- Keep dependencies and CI actions pinned. Dependency-source fixes need narrow
  provenance, reproducible evidence, installation verification and a removal
  condition; do not disable accessibility or native browser diagnostics.
- Complete coherent changes before their acceptance batch. A targeted check is
  not full coverage, a fixture is not a live provider, a build is not deployment,
  and matching old screenshots is not proof of design fidelity. Report material
  limitations and distinguish implemented, tested, published and deployed states.
