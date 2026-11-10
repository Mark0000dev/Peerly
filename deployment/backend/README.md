# Backend image preparation

Local delivery only. No registry login, image publication, server deployment or real provider call is part of these tools. AI admission/executor stay hardOFF. The same image supports API, email delivery worker, private media worker, Requests and change-transport maintenance workers, and one-shot migrations; it contains no Codex executable or authentication.

From the repository root:

```sh
docker build --tag peerly-backend:local-check backend/
python3 deployment/backend/smoke.py --build
```

`--build` fingerprints explicit backend inputs before/after build and fails if source changes during construction. The JSON result defaults to the system temporary directory (`peerly-backend-image-smoke.json`); `--output` chooses an artifact path. It records the actual image ID, platform, source fingerprint, migration head, checks and cleanup. A local image ID is not a pushed registry manifest digest or a committed release. The shared worktree must be frozen/committed by parent before publishing a revision.

The smoke uses unique `dev.peerly.ops01`-labelled names, an internal Docker network, no published ports and PostgreSQL16.15 on tmpfs in `peerly_image_test`. Its credentials/auth keys are generated synthetic values with no provider authority. It neither reads project env files nor connects to existing postgres-test, Google, S3, SMTP or a collector. Configuration-error worker tests use `--network=none`; the configured API/migration use the internal network. Normal failures clean owned containers/network in `finally`. An interrupted host/daemon can require later cleanup of the exact recorded task label; never use global Docker prune/reset commands.

The runtime image uses digest-pinned Python3.12.16-slim-bookworm and a builder-only pinned uv0.13.7. `uv sync --locked --no-dev --no-install-project --no-build --no-cache` installs production wheels; application source is copied explicitly and imported via `/app/src`. This avoids resolving the existing unpinned hatchling build backend. Source remains root-owned and immutable to UID/GID10001. No extra apt packages/compiler/browser toolchain are needed for the tested amd64 locked wheels. Other platforms must build/smoke before acceptance; missing wheels fail closed.

Actual entrypoints (override Docker CMD):

| Role | Command | Runtime configuration |
| --- | --- | --- |
| API | `python -m studymate.server --host 0.0.0.0 --port 8000` | DATABASE_URL, optional explicit authentication/media/observability fields from existing Settings |
| Email | `python -m studymate.email_worker` | DATABASE_URL, CODE_KEY, ENVELOPE_KEY, existing SMTP__ fields; optional observability |
| Media | `python -m studymate.media_worker` | DATABASE_URL, existing MEDIA__ fields; optional observability |
| Requests | `python -m studymate.requests_worker` | DATABASE_URL; optional observability |
| Changes | `python -m studymate.changes_worker` | DATABASE_URL; optional observability |
| Migration | `alembic upgrade head` | DATABASE_URL using the release migration role |
| Explicit firstboot | `python -m studymate.bootstrap_data_cli schema`, `validate FILE`, `apply FILE` | schema/validate offline; apply DATABASE_URL only, explicit owner file mounted read-only |

Only the API has a --help parser. Worker imports and genuine missing-config failures are tested; there is no invented worker --help switch. Do not start a configured worker merely to validate configuration against a real provider. The image default HTTP HEALTHCHECK is API liveness only. Worker and migration containers must override it with `--no-healthcheck`; real worker heartbeat/queue probes remain composition work. Migration is never an API startup side effect.

The smoke proves `--read-only`, bounded32MiB `/tmp` tmpfs, nonroot UID10001, dropped capabilities, no-new-privileges,64PIDs,512MiB/1CPU for application containers. Docker local logs are bounded1MiB/two files in the smoke. Those resource/log limits belong to runtime composition, not image metadata; deployment must explicitly supply appropriate measured limits and bounded logging. Worker production memory/CPU and photo-native cancellation behavior still require real workload sizing. Keep secrets only in protected runtime injection; never build args, COPY, image labels or artifacts. No app `.env`/dev/auth/design/test artifact is included by the context allowlist. The image can import/use Pillow and asyncpg without a writable app root. No blanket read-write-root workaround.

`.github/workflows/backend-image.yml` is build-only on pull requests or manual dispatch. Full existing backend quality semantics gate the image job. Actions and service/base images are pinned; token is contents:read, checkout credentials are not persisted. No secrets/package-write/login/push or deployment code exists. Actionlint/static/local Docker validation is not evidence of a remote Actions run. Future GHCR publication requires parent coordination of a trusted revision, external permissions, immutable tagging and quality/provenance/scanner policy; a registry push must not trigger deployment.

The head50 smoke supplement validates the real firstboot module in the production-only image. Its deliberately synthetic `fixtures/bootstrap-synthetic.json` lives outside the backend build context and is mounted read-only at `/run/peerly-bootstrap-synthetic.json` only for test commands. It is never copied into the image or used as production defaults. Offline schema/validate run with networknone and no DATABASE_URL; an additional fresh-process probe confirms no Settings/SQLAlchemy import. Against the smoke-owned empty migrated PostgreSQL, explicit apply/replay preserves current policy IDs/versions and catalogue provenance. Public policy GETs return the actual imported IDs/versions/body; catalogue still returns401 without a session, and actual SQL confirms the intended subject and zero seeded accounts/sessions/receipts. Authenticated catalogue behavior belongs to main's separate rootHTTP tests. No student authority is fabricated for image smoke. Real owner input and apply remain separately parent-owned.
