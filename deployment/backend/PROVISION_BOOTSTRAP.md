# Same-container provisioning hold

The existing `python -m studymate.ai_worker` constructs `AiWorkerSettings` before
`run_ai_worker`; all owner/account/model bindings are required immediately. The
existing receipt wait barrier is later in that worker and does not solve the
pre-binding provisioning hold. `prepare_ai_provisioning` intentionally accepts
only its narrower inputs. Neither is changed by this deployment-only helper.

Parent installs the exact hash-reviewed `provision_bootstrap.py` into the
already mounted acceptance **directory**, read-only inside the final AI
container. Do not recreate the container or mount a single config file inode.
Use the final published AI image, UID/GID10002, accepted named AppArmor/seccomp,
proc-only mount settings, original NPROC32/cgroup32 and restricted egress network.
No credentials, filled config or bindings are bundled into the image/helper.

Start that final container with this command instead of its ordinary worker CMD:

```text
python -u /var/lib/peerly-ai/acceptance/provision_bootstrap.py --wait-seconds 1800
```

The hold is bounded to1..3600seconds (default1800). While the file is absent the
wrapper waits without importing the application or opening credentials/network.
SIGINT/SIGTERM ends the hold. Expiry or invalid configuration exits nonzero,
without echoing configuration paths/entries/values or low-level errors. Do not
blindly restart after an uncertain auth/provisioning operation. No config file
means **no worker activation**, DB connection, model execution or readiness.

During this same-container hold parent performs accepted runtime/transport
proof, narrow provisioning, approved device authentication, actual private
account/model/provenance validation and final provider receipt procedure. Parent
owns those operations; this script does none of them. Proofs/receipts must be
bound to the actual final container PID/network/cgroup, not an earlier probe.

Only after all real bindings and provider receipt are accepted, parent writes
`/var/lib/peerly-ai/acceptance/worker-env.json` through the host acceptance
directory using an atomic sibling rename. Keep the directory controlled by
root/owner, never world/group writable; the directory bind must expose updates.
The file must be regular, have one hardlink, owner root or10002, no group/world
write, and be readable by10002. Prefer10002:10002 mode0600 (root-owned0600 would
be unreadable). Never put this filled file in Git, logs, Docker inspect dumps or
chat. Root-owned0440 with the dedicated readable group also meets the helper's
file checks. All ancestor components and the leaf are opened with O_NOFOLLOW;
FIFOs/devices/symlinks/duplicate keys and changed-during-read files are rejected.

JSON must be a nonempty flat object with string values only. Exact keys:

- `DATABASE_URL`;
- `MEDIA__ENDPOINT_ORIGIN`, `MEDIA__BUCKET`, `MEDIA__REGION`,
  `MEDIA__ACCESS_KEY_ID`, `MEDIA__SECRET_ACCESS_KEY`;
- `RUNTIME__EXECUTABLE`, `RUNTIME__EXPECTED_VERSION`, `RUNTIME__EXPECTED_SHA256`,
  `RUNTIME__MODEL`, `RUNTIME__CREDENTIAL_DIRECTORY`, `RUNTIME__EXPECTED_ACCOUNT`,
  `RUNTIME__EXPECTED_LOGIN_OWNER`, `RUNTIME__EXPECTED_OAUTH_ISSUER`,
  `RUNTIME__EXPECTED_OAUTH_CLIENT_ID`, `RUNTIME__ACCEPTANCE_ARTIFACT`,
  `RUNTIME__WORKSPACES_ROOT`, `RUNTIME__BUBBLEWRAP`, `RUNTIME__PRLIMIT`;
- optional actual settings names `OBSERVABILITY__COLLECTOR_ORIGIN`,
  `OBSERVABILITY__ENVIRONMENT`, `OBSERVABILITY__RELEASE`,
  `OBSERVABILITY__TRACE_QUEUE_CAPACITY` (not invented `OBS__` aliases).

Maximum32KiB total,8192characters per nonempty value; NUL/newlines/CR are
rejected. No `LD_*`, `PYTHON*`, `CODEX_HOME`, API keys, HTTP proxies, CLI endpoint
or config overrides are allowed. The helper replaces the inherited environment
with the explicit immutable image PATH/PYTHONPATH/HOME/TMPDIR baseline plus only
these entries. Full required-field/value validation remains in the existing
`AiWorkerSettings`; the helper cannot fabricate account facts or bypass the
existing receipt barrier. Supply complete real settings, not placeholder values.

After safe loading it calls `execve(sys.executable, [..., '-m',
'studymate.ai_worker'], environment)`. This replaces the process, retaining its
PID, network namespace and cgroup (and any existing tini parent). It does not
spawn a second container/worker or claim a readiness grant. Parent confirms the
existing worker's receipt checks/startup and durable readiness separately. The
JSON remains a retained private provisioning file, never a product credential
cache or logged artifact; parent owns its restricted storage/lifecycle.

Focused credential-free boundaries:

```sh
python3 -m unittest discover -s deployment/backend -p test_provision_bootstrap.py -v
```

These tests cover normal loading/missing file, file/ancestor symlinks,
FIFO/directory/hardlink, unsafe mode/owner/size, invalid JSON/duplicates/types,
env injection rejection, exact exec/environment replacement and bounded
expiry/rejection without secret-value output. They do not authenticate, contact
providers, run broad backend suites or prove actual same-container activation.
