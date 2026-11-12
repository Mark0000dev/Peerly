# Hosted CI → restricted SSH → existing staging CLI

This transport replaces self-hosted runner admission with a single restricted SSH
command. No self-hosted runner is installed or required. It targets only the
existing internal stack4/endpoint1 through the SAME accepted v3 promotion,
rollback, reconciliation, journal, unresolved blocker and persistent flock code.
It is implementation source for review, not host/environment/deployment acceptance.
Current CLI policy is still stopped-external/schema0060 bootstrap. Accepted active
external delivery needs the separately reviewed lifecycle contract; this transport
cannot invent acceptance or override that guard. The known NEW0061 source is
conservatively fenced before execution until an actual image/schema/config barrier
replaces this interim policy. This is not a0061 compatibility allowlist.

## Authority and request boundary

The repository is public and owned by a personal user. A repo-level runner label
or workflow `if` would not prevent another repo workflow sharing its UID and
private Env state. Hosted jobs instead run on fresh ubuntu-24.04. Their only new
credential is one dedicated nonroot SSH key released by `internal-staging`, whose
**actual deployment branch policy Mark must restrict to branch main only**.
A workflow if/main check and the server's admission.json attestation do not replace
that rule. Keep the SSH key unavailable until Mark verifies the real policy.

The job checks out trusted main client code, never PR/image-source code. The
server accepts only original command `peerly-staging-release-v1`, no PTY, and one
bounded newline-terminated JSON request followed by EOF. Fields are closed:
protocol1, promote/rollback/reconcile, exact40-character SHA, numeric run/attempt,
closed numeric recovery/reconciliation IDs, explicit schema60 compatibility and
short-lived GitHub read token. No commands, paths, source bytes, environment map,
repository URL, SSH options or arbitrary arguments can be supplied. Missing,
unknown, duplicate, mistyped and out-of-scope values fail before execution.

SSH authentication and enforced GitHub environment key admission are the security
boundary. GitHub run metadata is public: server API checks corroborate exact main
source/workflow/status/current attempt, not cryptographic proof of token origin.
A stolen SSH key is a credential compromise, requiring revocation, not something
public run metadata can repair. Do not describe the read token as OIDC attestation.

## Trusted main and same v3 execution

The root-installed stdlib broker reads `/branches/main` itself, verifies the
currently active `staging-release.yml` run/attempt belongs to this repository/main,
then requires successful strict helper quality for that exact tool SHA. It accepts
either the standalone main-push quality run or the completed reusable quality job
inside this same deployment run. This handles unrelated commits where PR/main
path filters did not start a standalone helper check. It never accepts PR checks.

The server fetches only a closed list of16 existing production helper Python files
plus backend pyproject/uv.lock/python-version. It verifies Git blob identities and
SHA256 for EVERY byte against `approved-tool-files.json` from the same main tree,
rejects symlinks/missing/extra paths/truncated trees, and rechecks main before exec.
The caller cannot select tool SHA or manifest/hash. Image-source SHA can differ
only for explicit recovery. These are source integrity checks anchored in trusted
GitHub main/TLS; they are not artifact signing or protection from a malicious owner.

Generate the manifest after every covered source/dependency change:

```sh
python3 -m deployment.staging.release_ssh.manifest
python3 -m deployment.staging.release_ssh.manifest --check
```

The companion quality-gate patch checks this manifest along with full inherited
Ruff/format/mypy and all old/new offline tests. Regenerate against the operator's
exact combined tree if its bytes differ; don't blindly reuse a stale private pin.
Tests and broker source are not executed from the caller's tree. The broker itself
is root-installed reviewed source, upgraded only by operator host operations.

After verified source acquisition, the server syncs existing locked tools using
root-owned uv0.13.7/Python3.12 without installing the product. UV automatic Python
download is disabled: the operator provisions accepted native tools first. Only then are
staging inputs loaded from root-protected host storage into an explicit child
environment. No provider input reaches hosted CI. The short-lived GitHub token
arrives in stdin and stays in memory; it is not a systemd property, argv, env file
or persistent request file. The child is exactly
`python -m deployment.staging.release.cli` with generated closed args. No second
promotion implementation, deployment queue, migration or worker activation exists.

The broker requires a successful operation-specific v3 private receipt after
CLI exit0. A process/health response alone is insufficient. Remote stdout exposes
only protocol/outcome/attempt; raw CLI output, stderr, inputs and Env are suppressed.
V3's necessary private snapshots remain on the VPS for recovery, never artifacts.

## Mark's exact environment step (actual admin operation remains external)

An administrator must establish this environment before the route is enabled.
Mark must use repository-owner/admin access, without a
new account/plan/terms workaround:

1. Settings → Environments → create/review `internal-staging`.
2. Deployment branches/tags → selected branches/tags → ONLY branch `main`.
   Remove wildcard/other branch/tag rules. "Protected branches only" is broader
   than main-only if another protected branch appears later.
3. Verify the actual environment and deployment-branch-policy API/UI state: custom
   branch policies, exactly main/branch, no tags. Parent retains a redacted proof.
4. Only afterward store environment secrets `PEERLY_STAGING_SSH_PRIVATE_KEY` and
   `PEERLY_STAGING_SSH_KNOWN_HOSTS`, and variable `PEERLY_STAGING_SSH_HOST`.
   The job's built-in read-only token supplies contents/actions/packages access.
   No Portainer/SMTP/S3/session/durable-state secret goes into hosted CI.
5. Parent may set `environment_main_only_verified` and `host_key_pinned_verified`
   true in the root-owned local admission record only on actual evidence. The
   false example deliberately cannot enable deployment. If admin remains403,
   stay blocked; do not put the key in repository-wide secrets as a workaround.

Use one new staging-only Ed25519 client key, not an existing root/developer key.
Known-host input is one exact hostname and independently verified ssh-ed25519
public host key. Verify through existing trusted admin/provider access. No blind
ssh-keyscan, StrictHostKeyChecking=no, agent forwarding or password fallback.
Client loads the private key through stdin into a fresh foreground ssh-agent with
25-minute key TTL, owned process-group cleanup and agent forwarding disabled. It
writes only one temporary chmod0600 **public** known-host entry in a private0700
directory, then deletes it. No private key or Env snapshot file is written/uploaded;
no inherited-extra-FD behavior is assumed. HOME/config/agent selection is explicit,
with no ambient identities/password/agent fallback. Tests use disposable unregistered
local keys/agents and a dummy transport, not an actual SSH server connection.

## Parent-owned VPS preparation, not executed here

Create/review a dedicated peerly-release UID/group with locked password, no sudo,
no Docker/lxd/containerd groups and no other project jobs. Its shell must allow the
forced command; setting nologin can also prevent legitimate forced execution.
Install the reviewed `broker.py` as `/opt/peerly-release-ssh/broker.py`, and the
launcher as `/usr/local/libexec/peerly-release-ssh`, root-owned and not writable by
the deployment user, including every ancestor directory. No uploaded caller file
may replace this bootstrap. Ensure `/usr/bin/python3` supports3.12 and the exact
root-owned uv0.13.7 binary is `/usr/local/bin/uv`; the operator verifies native tool pins.
The transport never auto-installs/updates host software or opens a Docker socket.

Install ONE public key under root-owned `/etc/ssh/authorized_keys/peerly-release`,
using the supplied restrict/forced-command line, and narrowly merge the SSH Match
snippet. Verify effective sshd settings (`sshd -t`, `sshd -T -C...`) before reload:
no forwarding/agent/X11/tunnel/PTY/password/user-rc/user environment; no accepted
LD_*, PYTHON* or other loader environment overrides from global AcceptEnv policy.
The wrapper clears environment without evaluating SSH_ORIGINAL_COMMAND. SFTP,
SCP, empty shells and arbitrary commands fail the exact-command check. Do not
replace global SSH settings or unrelated users' keys to make this pass.

Provision `/var/lib/peerly-release-ssh` and tmp/cache children as dedicated-user
mode0700 state. Provision/reuse `/var/lib/peerly-release` mode0700 as the SAME v3
state directory, owned by that UID; preserve all existing private journals and
**stack4.lock inode**. All operator/manual deployments must acquire that same flock,
never a parallel lock or unlink/recreate bypass. If the accepted live path differs,
reconcile the source/config with the operator before use; do not create a new authority.

Host `/etc/peerly-release-ssh/{admission,inputs}.json` must be regular root-owned
files, group peerly-release, mode0640, in a root-owned non-writable directory. The
runtime rejects symlinks and other owners/modes/fields. Fill inputs privately from
already accepted provider values; examples have nulls and contain names only.
Staging DB/schema/AI/external-delivery checks and image preload ownership remain
v3's actual contracts. No blind migration, Prune/Pull, lease deletion or AI touch.

## Bounded host execution and disconnects

The fixed broker starts one nonroot **systemd user transient service**, unit name
only from verified numeric run/attempt. Root admission does not expose generic
systemd-run or sudo arguments. The request/token travels over its inherited stdin
pipe, not `--setenv` or an input file. RuntimeMaxSec1200, TimeoutStopSec5 and
KillMode=control-group contain the full tree, including v3's separately owned
native process sessions. It has no capabilities/new privileges, private users/tmp/
devices, readonly system/home, narrow writable state and inaccessible raw daemon
sockets. Output is null and core dumps are disabled. Resource ceiling1G/50%CPU is
an initial bound, not proof of available German-VPS headroom.

Parent must establish a functional dedicated-user systemd manager/runtime bus
(and deliberate linger if necessary) and verify the actual unit properties,
namespace support, cgroup deadlines and teardown with harmless owned processes.
Never enable broad unprivileged namespaces or relax the whole host blind just to
start a unit. If these properties are unsupported, stop and review the narrow
host integration; do not drop the containment flags to claim success. No shared
Docker daemon restart/socket proxy, actual AI or external worker is involved.

A client disconnect/SIGHUP is UNKNOWN, not cancellation/success/retry. The bounded
unit may finish with an authoritative private v3 receipt or stop with an unresolved
marker. SSH has ConnectionAttempts1 and no request retry. Consult actual unit,
private journal, stack/environment/schema/AI state first. Reconcile/rollback needs
a fresh explicit protected-main dispatch and exact original/pending CI attempt IDs
plus schema compatibility. Same-attempt replay and rolled-back SHA quarantine
remain v3 rules. Older manual attempt names outside this closed numeric RPC format
use the operator's direct reviewed v3 path under the same lock; don't widen SSH RPC.

## Review/acceptance limits

Offline tests use synthetic GitHub metadata and local dummy processes only; they
are not actual SSH, systemd, environment, provider or deployment acceptance. Parent
must verify actual host-key/key loading, forced-command rejection, main-only secret
admission, helper/publication receipts, service timeout/child containment, exact
lock ownership, capacity, forward/reconcile/rollback and runtime postconditions.
No self-hosted runner registration, production release, signing or native delivery
is implied.
