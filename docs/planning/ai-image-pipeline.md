# AI worker image pipeline

Status: workflow code complete for parent review. Local validation is actionlint only. This task has not built or run an image, accessed credentials, invoked inference, run test suites, performed Git operations, published or deployed anything. Parent owns the isolated AI packaging branch and actual workflow execution.

The task-owned files are `.github/workflows/ai-image.yml`, `backend/ai-base-image.txt` and this document. The existing `backend/Dockerfile.ai-worker`, backend source, configuration, deployment inputs and other workflows are unchanged.

## Dispatch and exact inputs

The workflow triggers on pushes only to `feature/peerly-staging-ai`, plus optional manual dispatch with string input `backend_image`. The image job also requires `refs/heads/feature/peerly-staging-ai`; dispatch from main or another branch cannot publish. The push trigger bootstraps the new nondefault branch without requiring the workflow on main.

Immediately after pinned checkout, the first run step selects the supplied manual input, or reads `backend/ai-base-image.txt` when the input is absent. The committed default is `ghcr.io/mark0000dev/peerly-backend@sha256:0366ee9239ae9475918d3a69fd703e71763a87fc454857c073bc873c57b481f3`. Before authentication or image pull, the workflow validates the selected reference against the full expression `ghcr\.io/mark0000dev/peerly-backend@sha256:[0-9a-f]{64}`. Tags, other registries/repositories, whitespace, uppercase/nonhex digests, extra arguments and partial references are rejected. It also requires the triggering full 40-character lowercase source SHA. Input is passed through `REQUESTED_BACKEND_IMAGE`, selected and validated in Python, then written to `GITHUB_ENV` as `BACKEND_IMAGE`. Subsequent uses are quoted process arguments; input is never interpolated as shell code.

Checkout uses the repository-approved pinned checkout v6 commit with exact `github.sha` and persisted credentials disabled. Permissions are only `contents: read` and job-level `packages: write`. Runs for the same source commit are serialized without cancelling an active publication. Parent must choose the accepted backend digest corresponding to the intended frozen application; the workflow records its existing source revision label separately rather than fabricating equality between independently committed packaging branches.

The build copies the current checked-out `backend/Dockerfile.ai-worker` to a dedicated temporary directory as its sole build-context file, then runs Docker with that Dockerfile and exactly `--build-arg BACKEND_IMAGE=<validated digest>`. The base is pulled by immutable digest. Backend source, env files, tokens, auth caches and deployment inputs never enter this minimal context. Image labels retain source SHA, repository URL and immutable base reference.

The current Dockerfile derives the application from that backend image, installs its existing packaging prerequisites and verifies the pinned native Linux x86_64 Codex 0.167.0 distribution and executable/resource hashes. This workflow does not replace that installation logic, run a Node wrapper, change dependencies or install developer credentials. Build-time apt/native downloads use the existing Dockerfile; the offline restriction applies to smoke, not package acquisition.

## Offline native smoke

The workflow checks that the built image defaults to UID/GID 10002:10002 and the actual command `python -m studymate.ai_worker`. It then overrides only the entrypoint to the packaged native executable and invokes `--version`.

The smoke container uses network `none`, explicit UID/GID 10002:10002, a read-only root filesystem, a private 64 MiB `/tmp` tmpfs, all capabilities dropped, no-new-privileges, 64 PIDs, 256 MiB RAM and one CPU. Its empty temporary `HOME` and `CODEX_HOME` are confined to tmpfs. It has no mounted host directories, credentials, app environment, database, provider connection or published ports.

The native process has a 45-second host deadline and must exit zero, avoid OOM and report exactly `codex-cli 0.167.0` after whitespace stripping. Both stdout and stderr remain visible; diagnostics are not filtered. Docker inspection verifies the actual user, network mode, read-only root and exact local image ID. The smoke does not start the worker, execute inference, authenticate, inspect developer homes, test model tools or establish sandbox/provider readiness.

`smoke.json` records source SHA, exact base reference, inspected base image ID, the base’s original revision label when present, local worker image ID, native version and runtime restrictions. Missing base source labels remain null, not invented provenance.

## Registry publication and receipt

An ephemeral `GITHUB_TOKEN` logs into GHCR using stdin and a dedicated temporary `DOCKER_CONFIG`. Authentication is available before pulling the potentially private backend base and again in the publish step. No PAT or separately stored registry credential is introduced, and no credential is supplied as a build argument or smoke environment variable.

Only the exact built and smoked image is pushed to `ghcr.io/mark0000dev/peerly-ai-worker:staging-<full-source-SHA>`. There is no latest/floating alias or registry preflight that could prevent first-package creation. A successful push is followed by authenticated manifest retrieval, strict SHA256 digest validation and verification that the published manifest’s configuration digest equals the actual smoked local image ID.

`published.json` retains the actual registry digest, digest-qualified image reference, full tag, source SHA, smoked configuration image ID, immutable backend base reference, inspected base image ID, base source revision when present and native version. It is uploaded with `smoke.json` through the pinned upload-artifact action for 14 days. Job outputs `image` and `digest` expose the immutable deployment reference and digest; the summary also records them. Receipts contain no authentication values.

The deployment identity is the recorded `ghcr.io/mark0000dev/peerly-ai-worker@sha256:...`. SHA tags identify source but are not registry-enforced immutable: a deliberate rebuild of the same source with a different base input or refreshed build-time apt packages can resolve the tag to a different digest. Parent must retain and deploy the recorded digest/base pair.

An always-run cleanup step preserves container logs, removes the owned smoke container, and removes temporary registry authentication and the Dockerfile-only build context with an exit trap. A hard runner termination can prevent cleanup; the runner is disposable and the job token expires. Temporary paths are derived from `RUNNER_TEMP` in an initial shell step and exported through `GITHUB_ENV`, avoiding unsupported job-env `runner.temp` expressions.

## Validation and parent handoff

`/tmp/peerly-ops01-actionlint .github/workflows/ai-image.yml` passed with exit 0 on 10 November 2026. No image build, native process, suite, registry operation or actual inference was executed locally for this task. Existing backend acceptance is not rerun by this packaging workflow.

Parent copies the workflow, committed base-image reference and this document alongside the authorised exact AI Dockerfile to the isolated `feature/peerly-staging-ai` branch. Publishing that branch triggers the pipeline with the committed accepted base digest without any main/default-branch edit. Parent reviews the workflow/native smoke receipt and selects the returned worker digest. Once available, manual dispatch may override the base with another validated exact digest from the same backend repository. Package access, actual CI publication and deployment remain parent-owned. A passing version smoke establishes packaging/execution under the stated container restrictions only; it does not establish model-tool secret isolation, native sandbox operation, authentication, provider compatibility or inference readiness.


Approved packaging follow-up: the AI worker uses dedicated UID/GID 10002:10002; the core backend retains 10001:10001. Noether owns the Dockerfile USER update. Workflow expected image user, smoke user and private tmpfs ownership all use 10002. Actionlint passed after this narrow change; no build, smoke or test rerun was performed.
