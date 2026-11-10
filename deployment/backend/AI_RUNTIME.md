# Dedicated AI worker staging configuration

Code-first preparation, not deployed or security-accepted. Parent owns credentials, image publication, network/volume provisioning and deployment. Never reuse a developer Codex home or pass API keys into this process.

The application image and `Dockerfile.ai-worker` must come from the same frozen source candidate. Build the ordinary backend first; supply its immutable digest as `BACKEND_IMAGE` when building the worker image. The worker image installs the native0.167.0 executable and verifies SHA256 before making it executable; no Node wrapper is used. Only Linux x86_64 is currently reviewed. Build-time apt/native-package provenance and actual namespace compatibility must be retained in the final acceptance batch.

The outer launcher must use `/usr/local/lib/peerly-codex/vendor/x86_64-unknown-linux-musl/codex-resources/bwrap`, extracted from the same SHA512-verified pinned npm distribution as the CLI. Its SHA256 is `77360cb751ccedc5971391444ac86a8a33c15b04d6b4a6fe45f5d25496e62c4c`; the build verifies that digest, mode0555 and the adjacent resource layout. Do not install distro bubblewrap: its older interface lacks `--argv0`, causing the native helper fallback to execute an alias under the deliberately inaccessible credential home. Keeping the system binary absent lets the pinned CLI choose its bundled, internally digest-checked launcher. This packaging correction does not grant credential-home access or establish containment acceptance; the actual outer and nested helper controls must pass under the approved proc-only container configuration before authentication.

The singleton AI service exclusively reserves UID/GID `10002:10002`; core API and other workers remain `10001:10001`. Parent must provision the private credential directory and writable workspace/tmpfs for10002, with the existing0700 permissions. Keep both per-UID `RLIMIT_NPROC=32` and container `pids_limit:32`: the dedicated identity avoids counting the six core services against the same per-UID limit. This changes process ownership only, not namespace, AppArmor, credential-access or readiness policy. Existing UID10001 evidence remains historical; final remote proof must use10002 under the exact intended limits.

`python -m studymate.ai_worker` reads explicit environment only (`backend/.env.ai-worker.example` is a template, not automatically loaded). It needs the dedicated Peerly DB URL, retained DISPLAY S3 reader configuration, native binary pin/model, disjoint private credential/workspace roots, owner-provisioned account/login-owner/OAuth provenance bindings, and an accepted deployment artifact. Those bindings must come from controlled provisioning, never unverified JWT decoding or fabricated defaults.

`ai-worker.compose.yml` deliberately has no published ports, no Docker socket/developer mounts and no automatic restart. Its private external credential volume must already have correct10002:10002 ownership and0700 permissions. Its external network must implement the actual approved auth/model transport egress restrictions; the network name is not itself enforcement. The acceptance directory is mounted read-only as a directory, so a parent atomic file replacement becomes visible without pinning a stale single-file mount inode. Its receipt must be prepared from the final exact-image/runtime proof. It is not a manual boolean waiver. Do not add privileged mode, disable seccomp or weaken user namespaces merely to get a probe green. If the VPS/runtime denies the required namespace operations, fix the supported containment architecture before real credentials.

The worker owns one bounded PostgreSQL connection for short health/queue/heartbeat transactions. AI admission uses a separate pool2; core API stays independent. No SQL connection is held across model or S3 I/O. Runtime readiness resides on the existing `ai_executor_slot` row with fixed15-second freshness and exact model/prompt/schema/adapter versions. An expired readiness timestamp makes submission unavailable but never frees an occupied physical execution slot. Startup refuses predecessor ownership even after expiry; confirmed physical termination/cache recovery is a separate controlled operation. Uncertain process or credential state must block the supervisor and revoke readiness without automatically reclaiming execution capacity.

Final batch before phone authentication: exact frozen-image native pin/config/permissions, actual namespace/secret alias/FD/environment/network denial, supervisor/queue/uncertainty behavior, native CLI memory/PID/tmp fit and deliberate transport egress. Existing synthetic64MiB resource evidence proves mechanisms, not this process's resource budget or VPS fit. Only afterward does parent initiate supported device authentication in the dedicated credential destination and coordinate real codec/refresh/restart plus synthetic text/image model acceptance. No agent initiates login/inference or reads the resulting credentials.

Changing files or starting this worker does not complete MVP AI. API admission must derive availability from current accepted worker state rather than an environment enabled switch. Frontend keeps truthful503/manual flow until that fact exists. Publication/deployment and final backend/frontend/provider smoke remain separate recorded gates.

## Final-batch namespace compatibility prerequisite

The Compose security template is **not yet demonstrated to run nested bubblewrap on the actual image/host**. `cap_drop: ALL`, Docker default seccomp and the host AppArmor profile may deny user-namespace creation or subsequent namespace/mount operations. The earlier native-host namespace result does not establish container compatibility. This prerequisite must be resolved in the final credential-free batch before any phone authentication or private credential mount/use.

Run the exact reviewed outer launcher and nested pinned CLI sandbox-helper denial operation in the final worker image on the intended host, with its actual nonroot identity, read-only root, capability drops, seccomp/AppArmor, cgroups and tmpfs settings. Use synthetic marker files only. Record both the outer isolation result and the inner CLI helper result; `bwrap` availability/version, startup success or permission-denied output alone is not a successful isolation proof. All positive trusted-read controls and negative tool marker/FD/environment/network checks must still hold.

If startup fails, preserve bounded exit code/stderr and identify the precise failed operation: `clone`/`clone3` or `unshare` for user/PID/network namespaces, `mount`/remount, or an LSM denial. Distinguish executable/resource/loader ENOENT from security EPERM/EACCES. Record only filtered deployment facts (image digest, UID/GID, cap-drop, read-only state, selected SecurityOpt/AppArmor profile, rootless/userns mode and relevant kernel/Docker versions); do not dump full container inspection/environment or unrelated host workloads. A parent-approved tracing/host-audit diagnostic may identify the exact syscall/profile rule in that final batch; absence of a trace must remain an explicit uncertainty, not proof that seccomp or AppArmor caused the failure.

If the actual operation requires a different security profile, derive and document a minimal **per-service** seccomp/AppArmor profile from the observed failure and supported bubblewrap requirements, review its added authority and rerun the same positive/negative proof under that exact profile. Parent owns installation/deployment. Do not use privileged mode, blanket unconfined profiles, capability restoration, globally relaxed user-namespace sysctls or changes to shared host services as a shortcut. If a safe supported profile cannot be demonstrated, keep AI unavailable and resolve containment architecture; the template must not be described as working merely because it parses or an image builds.

No new probe was executed for this documentation update. The previously frozen head52 code snapshot remains immutable; this is a documentation-only prerequisite added afterward, not new runtime acceptance.

## Temporary AI-only lifecycle overlay

The AI build now copies exactly
`backend/src/studymate/infrastructure/ai/process.py` from its checked-out AI
working-branch checkpoint into `/app/src/studymate/infrastructure/ai/process.py`
above the immutable backend base. This is the narrowly approved physical
process-termination correction, not a claim that the running core API image
contains that patch. Nash owns the module/regression; parent selects and publishes
the exact non-main checkpoint. No other backend source is overlaid.

The workflow must record the exact checked-out source SHA and module SHA256 as
`runtime_patch_source_sha` and `runtime_patch_sha256`, label the image with
`dev.peerly.ai.runtime-patch.sha256`, and compare the actual packaged module bytes
with that SHA before publication. Module compile/import smoke is separate from
the owned lifecycle regression evidence. The branch commit and hash come from
the actual publication receipt, never a moving branch name or an invented hash.
The unchanged base digest retains its original API revision/provenance.

Remove this temporary COPY and its one-file context/receipt machinery when a
newly accepted immutable backend base already includes the same lifecycle fix;
verify the resulting image module hash before dropping the separate provenance.
This does not change namespace, AppArmor, UID10002, NPROC32/cgroup32, credential
recovery, provider acceptance or readiness requirements.
