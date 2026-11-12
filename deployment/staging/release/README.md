# Existing internal staging release

The executable entry point is `python -m deployment.staging.release.cli` from the
repository root. This tool can promote, reconcile or explicitly roll back only
existing Portainer Compose stack **4**, endpoint **1**, `peerly-staging`, origin
`https://peerly-staging.aleksei-orlov.dev`. It cannot target production, migrate,
activate external delivery or modify AI. Schema must already be
`0060_report_triage`. Signing/native and production release criteria are separate.

## Source and quality selection

The new `.github/workflows/staging-release.yml` reacts to completed successful
main push runs of Backend or Frontend image. Both exact main-SHA publication runs
must already have succeeded; a missing/still-running companion run fails before
any stack write, and its later completion triggers another attempt. No backend
48-minute gate or frontend full matrix is repeated by this workflow.

`Github.completed` queries the real workflow runs API with explicit head_sha,
main branch and push event, then fetches the exact run. Image validation also
checks workflow path/repository/status/conclusion/current attempt. Backend's
build-only workflow and PR/manual/fork checks cannot substitute for publication.
Multiple matching successful runs fail closed rather than selecting a random run.
Moving main is checked before baseline acquisition and again immediately before
each promotion PUT. Rollback executes current trusted main tool code but selects
the original accepted image SHA from its private recovery record.

Frontend uses the existing exact-run artifact
`frontend-image-{sha}-{attempt}`: expired/ambiguous artifacts fail, run/head SHA
metadata is checked, ZIP members and sizes are bounded. Backend uses one anchored
`PEERLY_BACKEND_PUBLICATION_V1=` compact JSON stdout line in the exact successful
`Publish backend image` job/current attempt and completed receipt step. This is
emitted after existing quality, build, smoke and push by the backend publication
receipt step. Script source echoes, duplicate markers and missing logs fail.
No extra upload action, Node pin or existing workflow quality change is needed.

Registry acquisition is pull-read-only HTTP: exact allowed GHCR repository and
manifest digest, config blob digest, linux/amd64, actual OCI revision/source and
smoked configuration ID must agree. Both manifest and config are hashed from raw
bytes. OCI indexes fail closed. Signed GitHub/CDN redirects are explicitly
validated and receive **no Authorization header**. HTTP has bounded bodies and
timeouts, no ambient proxies, no automatic redirect/retry and no body/error logs.

## Required environment (names only)

These are explicit runtime inputs; no existing credential file, home, SSH config,
private workspace client or developer account is searched/imported.

| Input | Contract |
| --- | --- |
| `PEERLY_GITHUB_TOKEN` | Read repository/actions metadata and selected frontend artifact/backend job logs; workflow supplies github.token |
| `PEERLY_GHCR_USERNAME`, `PEERLY_GHCR_TOKEN` | Read the two exact core GHCR repositories; workflow supplies actor/github.token |
| `PEERLY_PORTAINER_ORIGIN`, `PEERLY_PORTAINER_API_KEY` | Approved TLS Portainer origin and X-API-Key access to stack4/endpoint1 |
| `PEERLY_STAGING_METRICS_ORIGIN`, `PEERLY_STAGING_METRICS_PASSWORD` | Actual existing TLS reader gateway, fixed username peerly-read, `/peerly-observe/metrics/application` |
| `PEERLY_SMOKE_SESSION`, `PEERLY_SMOKE_ACCOUNT_ID` | Existing owner-controlled fixture session value and expected actor ID; GET-only smoke, no login or provider delivery |
| `PEERLY_STAGING_DATABASE_NAME` | Exact accepted staging database name; actual container DSN path and current_database() must match; provider defaults are rejected |
| `PEERLY_CANONICAL_AI_CONTAINER_ID` | Exact accepted canonical container; never selected by fuzzy name |
| `PEERLY_RELEASE_STATE_DIR` | Absolute existing private mode0700 directory owned by release-runner user; durable shared lock/journals/snapshots |

The workflow uses `internal-staging` environment secrets for six Portainer,
metrics and fixture inputs; GitHub/GHCR use the job's read-only token. Canonical AI
ID, database name and state directory are environment variables (`vars` in the workflow), not
credentials. Configure deployment-branch restrictions to main. The script also
checks `github.ref` and source metadata; it never executes PR source with secrets.

The dedicated self-hosted label `peerly-staging-release` denotes a trusted Linux
runner with Python3.12, uv0.13.7 and Docker Compose available. This source does not
install a runner, create secrets, enable traffic or grant host privileges. Local
Docker usage is **config rendering only**, without daemon mutation/authentication.
No JavaScript actions are used: a bounded standard-library bootstrap retrieves
only exact main release source and backend locked tool inputs via GitHub's tree/
blob API. Existing locked uv environment installs the tool dependencies. Bootstrap
checks each Git blob ID; there is no Git/index operation or whole repository build.

All manual operator deployments must take the **same** state-dir `stack4.lock` on
that runner host, preferably by invoking this CLI. Workflow concurrency does not
lock another host or an external writer. Portainer has no atomic conditional PUT;
fresh full-content/full-Env comparisons are conflict detection under this shared
exclusive lock, not a claim of distributed API CAS. Do not enable unattended use
until this writer-ownership prerequisite is true.

## Preconditions and actual I/O

The operator preloads the two already verified immutable images on endpoint1 with its
existing controlled preparation. This tool only inspects preloaded images. It
never calls Docker image pull, Portainer PullImage, Prune, restart, create/remove,
worker activation or host root operations. Missing images abort.

The existing full stack must already bind `PEERLY_BACKEND_IMAGE`,
`PEERLY_FRONTEND_IMAGE`, `PEERLY_RELEASE`, `PUBLIC_ASSET_RELEASES` and
`PEERLY_HOST`; `PEERLY_ENVIRONMENT` must be staging. The API alone must inject
PUBLIC_ASSET_RELEASES. Five backend roles must bind OBSERVABILITY__RELEASE through
PEERLY_RELEASE, as in the existing application observability overlay. Missing
plumbing fails closed; do not replace the live stack with an old repository
Compose template. Native Compose config runs with private temporary source,
complete preserved Env and no ambient .env/COMPOSE_*/DOCKER_* overrides.

Rendered comparison permits only core images, core OBSERVABILITY__RELEASE and
API asset-map changes. All other rendered fields and full original Env order/
values survive. Core replicas must remain one; build/always-pull are rejected.
The dormant migrate service may change image but must retain `[ops]`; it is never
run. AI/unknown core services are rejected. The only accepted extra core service
is external_delivery explicitly scaled to zero and otherwise unchanged; another
stop mechanism or a different historical shape requires operator baseline review.

## Promotion and actual postconditions

A single attempt directory and fsynced mode0600 journal are created before writes.
Snapshots/recovery inputs contain credentials, stay private, and are not artifacts.
Each PUT compares the fresh full stack identity/content/complete Env with its exact
expected prior state and sends identical StackFileContent, complete Env,
`Prune:false`, `PullImage:false`. A response is acceptance, not readiness.

1. Acquire and verify exact successful publication receipts and registry bytes.
2. Verify the baseline runtime, schema and canonical AI ownership; save actual
   previous image identities and recovery inputs. Recheck selected main source.
3. Append the actual CI frontend asset map without rebinding/removing any approved
   old release. Promote backend+map+core telemetry release while frontend stays old.
4. Wait boundedly for actual containers to converge, then verify API effective
   settings, current old UI and fresh successful worker-loop metrics.
5. Only after those postconditions pass, change frontend and repeat verification.
   If the selected images are already running, verify them and make no PUT.

Runtime uses endpoint1 Docker inventory/inspect, exact Compose labels and one
running instance per role, actual registry config IDs, OCI labels, nonroot users
and expected module commands. The four core workers must also be unique module
executors across endpoint1. Their existing collector counters (email/media/
requests expiry/changes) must increase for this source and staging during a fresh
bounded sample while container IDs/StartedAt remain stable. Idle successful loop
iterations count; storage errors/cancelled work do not. Missing/stale metrics
never become success. Collector intentionally drops service.instance.id, so this
is a source-specific singleton loop-liveness check combined with physical runtime
identity, not a per-job/PID telemetry claim or real provider acceptance.

A fixed nonroot read-only exec in the API reads actual database name and Alembic head, effective
public_asset_releases and durable AI slot identity/fresh heartbeat. PostgreSQL
uses read-only transactions/defaults and bounded statement/lock/connect timeouts.
No application bootstrap, worker/provider call, queue/lease write or migration is
invoked. The canonical AI holding/bootstrap Config.Cmd is not assumed to be the
worker module; its exact container config/ID/PID/StartedAt plus unchanged durable
worker/start/model/prompt/schema/adapter guard identity are compared. No exec,
credential/cache/receipt read or renewal/reanchor occurs inside AI.

Actual HTTPS `/api/ready` must succeed. Served release JSON must be no-cache JSON
and match the actual selected frontend container file byte-for-byte. Root and CSR
routes must match exact distinct baked documents obtained by read-only archive
GET; every emitted JS asset must be served as JavaScript. Anonymous `/api/v1/me`
must reject; the supplied fixture must match expected account_id and its profile
must be readable with no-store. These are real GET contracts in the executable,
not fixture-derived booleans. No full provider/native/user-journey acceptance is
implied. Asset-map retention preserves observation recognition; it does not retain
old lazy-loaded JS files in Nginx. Accept or separately retain those assets before
claiming complete old-client navigation continuity.

## Unknown outcomes, reconciliation and rollback

Any potentially attempted mutation has a durable root `unresolved.json` blocker.
Timeouts, errors and failed postconditions leave it in place; a new automatic run
ID cannot bypass it. Do not delete it or blindly rerun a failed attempt.

The operator may explicitly dispatch `reconcile` with original source SHA,
`recovery_attempt`, exact `reconcile_attempt` blocker ID and reviewed schema60
compatibility input. Under the same lock, the CLI reads fresh actual state and
accepts only the exact before/backend-map/final/retained-map rollback full-Env snapshots from that
attempt. It then proves actual matching runtime/ownership/readiness. Only a
verified known state clears the blocker. Unknown drift remains blocked.

For explicit `rollback`, provide the original recovery attempt/SHA and explicit
`compatible_schema=0060_report_triage`; if unresolved, also acknowledge its exact
attempt ID. CLI first accepts only a known original phase; arbitrary drift or an
unrelated newer deployment cannot be overwritten. It preserves the pending marker
and atomically installs a new one before rollback writes.

Rollback verifies live DB/schema/AI ownership using a fixed read-only probe in an
already-running core backend with the exact target image and DATABASE_URL. It
need not trust a healthy current UI, so a broken frontend/API can be repaired.
Then it returns frontend first, backend second, retaining all old/new maps and
using the prior core telemetry release. Previous binaries must support retained
schema/data/maps: the manual compatibility input is an owner-reviewed condition,
not an automatic downgrade proof. Final complete postconditions are mandatory.
A failed/ambiguous rollback remains blocked. Successful rollback (or verified reconciliation of its outcome) quarantines the rolled-back source SHA so a queued automatic completion event cannot redeploy it; deliver a checked forward-fix SHA. No SQL/data restore/downgrade occurs.

## Focused inherited gate

From the repository root, using the existing locked backend environment:

```sh
backend/.venv/bin/ruff check deployment/staging/release
backend/.venv/bin/ruff format --check deployment/staging/release
backend/.venv/bin/mypy --config-file backend/pyproject.toml deployment/staging/release
backend/.venv/bin/python -m pytest -c backend/pyproject.toml deployment/staging/release/tests -q
python3 -m deployment.staging.release.cli --help
```

The local pyproject extends every backend Ruff selector/settings, adding only the
normal S101 allowance for exact tests/*.py. All implementation and test modules
are included in inherited strict mypy; there are no broad exclusions/suppressions.
Validate the new workflow with actionlint and this directory's actionlint.yaml
(which declares only the dedicated self-hosted label). Synthetic transport, state
and ingress tests are fault checks, never actual readiness evidence. The operator owns
real secret creation, execution, deployment acceptance and release-state updates.
