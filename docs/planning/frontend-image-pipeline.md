# Frontend production image pipeline

Status: workflow code complete for parent review. Local validation is actionlint only; no local image build, registry login/publish, credentials read, Git operations or deployment was performed by this task. Aquinas owns the separate actual production image build/smoke. Internal diagnostic staging is authorised with the ResizeObserver defect still OPEN; this workflow neither suppresses that diagnostic nor establishes browser/runtime or external-user readiness.

The only task-owned files are `.github/workflows/frontend-image.yml` and this document. Existing frontend source, package files, Dockerfile, ignore rules, nginx configuration and other workflows remain with their owners.

## Inputs and triggers

- Push trigger: only `feature/peerly-staging-frontend`. Manual dispatch is available, but the image job also requires that exact branch, so dispatch from main or another ref cannot publish.
- Checkout is pinned to the existing repository-approved checkout v6 commit and explicitly selects the triggering full `github.sha`; checkout credentials are not persisted.
- Exact build: `docker build --file frontend/Dockerfile --tag ghcr.io/mark0000dev/peerly-frontend:staging-$GITHUB_SHA frontend`, with source/revision OCI labels. There is no alternate Dockerfile, context, generated deployment input or build argument override.
- `frontend/Dockerfile` already pins Node and unprivileged nginx base digests, installs the locked dependency graph with its approved patch lifecycle and runs the production Angular build. Its existing allowlisted `.dockerignore` controls the context. No credentials are build arguments or files in that context.
- Permissions are `contents: read` and, only for the image job, `packages: write`. Same-commit runs are serialized without cancelling an in-progress publication. No PR execution or deployment trigger is added.

Aquinas confirmed `frontend/` context, `frontend/Dockerfile`, UID 101:101, port 8080, `/tmp` tmpfs and the nginx document/health contract. Its initial handoff described an isolated 202-file input snapshot with manifest SHA256 `8700d595886faf8b97839b8470680d3b8eb839265d17c6176acf4feb0737c33c`; that is input provenance, not a passing image-build receipt. Actual smoke evidence remains Aquinas-owned.

## Build and runtime smoke

One runner builds one image; the workflow publishes that same local image after smoke, without a second rebuild. The container uses explicit UID/GID 101:101, a read-only root filesystem, `/tmp` tmpfs with 64 MiB and UID/GID 101 ownership, all capabilities dropped, no-new-privileges, 128 PIDs, 256 MiB RAM and one CPU. Port 8080 is bound to a Docker-assigned loopback host port. No volumes, providers, application secrets or backend/database are needed.

The bounded smoke requires:

1. `/healthz`: HTTP 200 and exact `ok\n`, within 45 seconds of startup.
2. `/`: HTTP 200, HTML media type and bytes equal to the image’s actual prerendered `index.html`.
3. `/profile` and `/index.csr.html`: HTTP 200 and bytes equal to the actual `index.csr.html`; the prerendered landing and client app documents must be distinct.
4. Missing JavaScript under `/assets/` and missing CSS: HTTP 404, with neither app document returned. `/api/v1/me` must also return 404: same-origin API forwarding belongs to the staging reverse proxy, not this static container.
5. Every script referenced by the client document: same-origin, nonempty JavaScript served with the correct media type, never an HTML fallback.
6. Actual container user/read-only settings and `nginx -t` success.

Each HTTP read has a three-second timeout. These are static-image/runtime checks, not screenshot, browser JavaScript, native push or provider acceptance. Existing static/unit/build receipts remain in [frontend-progress.md](frontend-progress.md); the image workflow does not rerun or depend on the 1080-case HTTP or 228-case PostgreSQL matrices or another unit/coverage gate. Existing workflows are unchanged.

## Publication, digest and cleanup

The publication step alone receives the job-scoped ephemeral `GITHUB_TOKEN`. `docker login ghcr.io` takes it through stdin into a dedicated temporary `DOCKER_CONFIG`; no PAT or deployment credential is required. A first step derives temporary paths from the runner’s `RUNNER_TEMP` and writes them to `GITHUB_ENV`, rather than using the unsupported job-env `runner.temp` expression.

The only tag is `ghcr.io/mark0000dev/peerly-frontend:staging-<full-40-character-SHA>`; no `latest`, branch or floating staging alias is written. There is no registry manifest preflight before the first push, avoiding nonexistent-package permission/404 ambiguities. After push, an authenticated GHCR manifest read records the actual `Docker-Content-Digest` and verifies that its configuration digest is the exact image ID that passed smoke. Unsuccessful publication or verification fails the job; it does not manufacture a digest.

The authoritative immutable deployment reference is `ghcr.io/mark0000dev/peerly-frontend@sha256:...`, emitted as job output `image`; output `digest` contains the digest alone. The SHA tag identifies source, but GHCR tags themselves are mutable: a deliberate rerun may resolve that source tag to a new digest. Parent must deploy the recorded digest, not rely on a tag being registry-enforced immutable. Concurrency prevents this workflow’s same-SHA runs from pushing simultaneously.

`smoke.json` records the source SHA, local image ID, runtime restrictions and route outcomes. `published.json` records the full tag, registry digest, digest-qualified reference and smoked image ID. Both are retained in the pinned upload-artifact step for 14 days; the digest-qualified reference also appears in the job summary. Neither receipt contains tokens or registry authentication data.

An always-run cleanup step emits container logs, removes the owned container and removes the temporary Docker authentication directory using an exit trap even if diagnostic/container cleanup fails. Hosted-runner termination can prevent cleanup execution; the runner is disposable and the GitHub token expires. No persistent credentials, account login, credentials cache upload or deployment is introduced.

## Validation and parent handoff

`/tmp/peerly-ops01-actionlint .github/workflows/frontend-image.yml` passed with exit 0 on 10 November 2026 after replacing job-env `runner.temp` references. No frontend build/test, image smoke, GitHub run, GHCR operation or staging deployment was executed by this task. Publish permissions, first-package access and actual CI smoke remain to be established by the parent-run pipeline.

Parent owns review, publication of the isolated staging branch, workflow dispatch, package access decisions and deployment by the recorded digest. Aquinas supplies actual production image evidence. Existing ResizeObserver failures remain visible and documented; stop internal admission if the diagnostic causes functional or visible failure. No student/external-user readiness or complete acceptance claim follows from a static nginx smoke.
