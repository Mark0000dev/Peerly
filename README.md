# Peerly

<img src="frontend/src/assets/brand/logo-mark.svg" alt="Peerly" width="72" />

**Find a study partner. Share what you know. Get unstuck together.**

Peerly helps students at Asia Pacific University of Technology & Innovation (APU), Malaysia find relevant study partners and start useful conversations. Students describe what they want to learn or can help with; the server handles discovery, connection requests and access rules.

[Staging demo](https://peerly-staging.aleksei-orlov.dev)

## What you can do

- Sign in with Google and verify an APU student mailbox (`mail.apu.edu.my`).
- Build a profile, upload a photo and describe a reusable study goal or areas you can help with.
- Discover people through shared knowledge areas, with optional course and task context.
- Send, accept, decline or undo connection requests, then chat and share images.
- Use optional AI assistance to clarify goals and suggest knowledge areas; AI also supports photo assessment and operator report triage.
- Manage profile visibility, notifications, support requests and account deletion.
- Use an audited operator interface to inspect retained records, handle reports and review accounts.

Core study and messaging flows remain independent of AI availability. AI work runs through a durable, bounded PostgreSQL queue and a dedicated executor.

## Architecture

```mermaid
flowchart LR
    Student[Angular / Taiga UI client] -->|REST + SSE| API[FastAPI application]
    API --> DB[(PostgreSQL)]
    API --> S3[S3-compatible media storage]
    DB --> Workers[Background workers]
    Workers --> AI[Isolated AI executor]
    Workers --> Delivery[Email / notifications / analytics]
    API --> OTEL[OpenTelemetry Collector]
    Workers --> OTEL
    OTEL --> Monitoring[Prometheus / Loki / Tempo / Grafana]
```

| Layer            | Technologies                                                                     |
| ---------------- | -------------------------------------------------------------------------------- |
| Frontend         | Angular 22, TypeScript, Taiga UI, TanStack Query, RxJS                           |
| Native packaging | Capacitor for Android and iOS                                                    |
| Backend          | Python, async FastAPI, clean architecture and application use cases              |
| Data             | PostgreSQL, asyncpg, SQLAlchemy typed mappings, Alembic                          |
| Media            | S3-compatible object storage                                                     |
| AI               | Dedicated Codex executor behind application ports and a PostgreSQL job queue     |
| Operations       | Docker, Portainer, GitHub Actions, GHCR                                          |
| Observability    | OpenTelemetry, Prometheus, Alertmanager, Grafana, Loki, Tempo, Umami             |
| Quality          | Ruff, strict mypy, pytest, ESLint, Stylelint, Prettier, Knip, Vitest, Playwright |

Server state belongs to TanStack Query. The backend owns permissions, matching, lifecycle transitions and persistence. Backend code separates domain, application, infrastructure and HTTP adapters. The frontend is organized by screen, with colocated behavior and tests.

## Run locally

Requirements: Docker Compose, Python/uv, and the Node version in [`frontend/.nvmrc`](frontend/.nvmrc).

```sh
docker compose up -d --wait postgres postgres-test
cd backend
uv sync --locked
cp .env.example .env
uv run alembic upgrade head
make run
```

In another terminal:

```sh
cd frontend
npm ci
npm start
```

The environment example documents the required settings. Google sign-in, email delivery, S3 and live AI require your own provider configuration; secrets are never included. See the [backend setup](backend/README.md) and [frontend setup](frontend/README.md) for configuration and worker commands.

## Tests and quality

```sh
export TEST_DATABASE_URL=postgresql+asyncpg://studymate:studymate@localhost:5433/studymate_test
sh scripts/check.sh
```

The backend includes unit and real PostgreSQL integration tests. Frontend scenarios combine behavior assertions with screenshot comparisons across desktop and mobile browsers. Both packages enforce a 95% coverage floor. See [testing](docs/testing.md) for commands and current validation limits; configured gates are not a claim that every release check has passed.

## Documentation

- [Product behavior](docs/product.md)
- [System architecture](docs/architecture.md)
- [API contracts](docs/api.md)
- [Database and concurrency](docs/database.md)
- [AI execution and reliability](docs/ai.md)
- [Monitoring, logs and traces](docs/observability.md)
- [Deployment and configuration](docs/deployment.md)
- [Contributing](CONTRIBUTING.md)

The web application is deployed to an internal staging environment. Native packaging is configured; Android and iOS distribution is not yet validated. Visual refinement and complete frontend release acceptance are still in progress.

## Team

| Contributor           | Role                                 |
| --------------------- | ------------------------------------ |
| Mark Bakulin          | Backend engineer                     |
| Vepa Garayev          | Backend engineer                     |
| Aleksei Orlov         | UX/UI designer and frontend engineer |
| Nursultan Abdimalikov | Matching & staging QA                |
| Maxim Kalinin         | Product, pitching and presentation   |

## License

[MIT](LICENSE)
