# AI egress image publication

Status: code complete for parent review; actionlint passed. Task-owned files are only `.github/workflows/ai-egress-image.yml` and this document. No local image build, container execution, tests, credentials access, registry operation, Git operation or deployment was performed by this task.

This packages the already planned gateway configuration. It does not introduce product functionality or establish provider, transport-isolation or inference readiness.

## Trigger and build inputs

The only trigger is a push to `feature/peerly-staging-ai-egress`. The image job independently requires that exact branch. There is no manual/default-branch prerequisite, PR trigger or main change.

Checkout uses the repository-approved pinned checkout v6 commit and exact triggering `github.sha`, without persisted credentials. Permissions are `contents: read` plus job-level `packages: write`. Same-source runs are serialized without cancelling an active publication.

The exact build is `docker build --file deployment/ai-egress/Dockerfile --tag ghcr.io/mark0000dev/peerly-ai-egress:staging-$GITHUB_SHA deployment/ai-egress`, with OCI source/revision labels. No alternative context, Dockerfile or configuration is generated. Noether owns the Dockerfile and its deny-by-default `.dockerignore`, which includes only Dockerfile/config/ignore rules. The image pins the reviewed HAProxy 3.2 Alpine digest, copies `haproxy.cfg` read-only to `/usr/local/etc/haproxy/haproxy.cfg`, defaults to user `haproxy` and retains the normal gateway command. Noether’s packaged configuration SHA256 is `de69397f6b2ffd0c246ceae89da7ab88eededefe7ccc17f5b53a894da7604043`; CI records its checked-out config hash with the source SHA.

## Offline configuration smoke

CI builds one image and smokes that exact local image. The container uses its actual default nonroot image user, a read-only root filesystem, all capabilities dropped, no-new-privileges, network `none`, 32 PIDs, 64 MiB memory and 0.25 CPU. No host directories, credentials, ports, tmpfs or provider environment are mounted or supplied.

The only supplied config variable is synthetic `AI_DATABASE_FORWARD_IP=192.0.2.10`, a documentation address. The smoke replaces the entrypoint with a shell that checks/records its actual nonzero UID and executes `haproxy -c -f /usr/local/etc/haproxy/haproxy.cfg`. It does not start forwarding or require DNS/provider/PostgreSQL access. A 45-second host deadline bounds the process; zero exit and no OOM are required. Docker inspection confirms the actual built image ID and read-only/network/capability restrictions.

Both stdout and stderr are retained unfiltered. HAProxy config validation under `--network none` may emit DNS socket warnings; they remain visible, and any nonzero configuration exit fails publication. Configuration validation does not substitute for the existing dedicated transport proof or a real deployment check.

`smoke.json` records source SHA, local image ID, image user and actual UID, restrictions, config path and checked-out config SHA256, synthetic database address and actual successful config-exit outcome. No inference, provider or transport proof is claimed.

## Publish, verification and cleanup

After smoke, CI logs into GHCR with the ephemeral `GITHUB_TOKEN` through stdin into a dedicated temporary `DOCKER_CONFIG`. There are no PATs, build credentials or deployment credentials. The initial shell step derives paths from `RUNNER_TEMP` and exports them through `GITHUB_ENV`, using the supported pattern rather than job-env `runner.temp` expressions.

CI pushes only `ghcr.io/mark0000dev/peerly-ai-egress:staging-<full-40-character-source-SHA>`. No floating alias or preflight blocks first-package creation. It then reads the actual authenticated registry manifest, validates the returned SHA256 digest and verifies that the manifest’s configuration digest matches the exact image ID that passed smoke.

`published.json` records the actual registry digest, digest-qualified reference, full source tag, source SHA, smoked image/configuration ID, config path/hash, nonroot UID and synthetic address. It and `smoke.json` are retained for 14 days using the pinned upload-artifact action. Job outputs `image` and `digest`, plus the summary, carry the actual immutable digest reference.

SHA tags identify source but are not registry-enforced immutable. Parent must deploy the recorded `ghcr.io/mark0000dev/peerly-ai-egress@sha256:...` rather than assume a tag cannot move on rerun. Publication cannot claim success if manifest/configuration verification fails.

An always-run cleanup step emits owned-container logs, removes the container and removes temporary registry authentication via an exit trap even if diagnostic/container cleanup fails. Hard runner termination can prevent cleanup; the runner is disposable and its job token expires. No registry credentials enter artifacts or the build context.

## Handoff

`/tmp/peerly-ops01-actionlint .github/workflows/ai-egress-image.yml` passed with exit 0 on 10 November 2026. No build, smoke, publish or test suites were executed locally by this task. The workflow adds no backend/frontend test jobs or duplicate acceptance prerequisites.

Parent owns the isolated branch, reviewed Dockerfile/config inputs, Git/push, first GHCR package access and workflow run, receipt review and deployment by the returned digest. Noether’s exact Dockerfile/config/ignore handoff is `/tmp/peerly-ai-egress-packaged-handoff/manifest.json`. This workflow’s passing config smoke is a packaging fact only, not a new transport-security proof, credential/provider acceptance, inference result or deployment/readiness claim.
