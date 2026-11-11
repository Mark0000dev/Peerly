# Explicit staging-only manual membership command

Owner approved this temporary internal-team operation because institutional email
was quarantined. It is not a public endpoint, future-user auto-verifier, production
switch or a new attestation/role mechanism. It requires no DDL or core image change.
Existing production OTP, registration, profile and activation flows remain intact.

Parent alone executes it with staging credentials already inside the API container.
Developers do not read the private manifest/credentials, execute live grants or
send email. The only accepted database name is `peerly_staging`, checked in both
DSN configuration and the actual connection. Do not rename a production database
to evade this safeguard or turn this helper into application startup code.

## Explicit private input and execution

Input is a closed JSON object with `operation_id` (UUID), `performed_by`
(1..38 ASCII letters/digits/underscore/hyphen) and `entries` (1..20 explicit
account targets). Every entry contains `account_id`, `email`, `challenge_id`.

- Real address: use the exact canonical requested institutional email and UUID
  of that account's latest pending challenge. Never infer or replace an address.
- Owner-approved no-email staging case: `challenge_id` is null and email is
  exactly `peerly-stage-<accountUUID.hex>@mail.apu.edu.my`. The target must have
  **zero** historical email challenges. No address/challenge/outbox is invented
  or sent beyond this explicitly requested synthetic binding.
- Deleted, banned/known banned-lineage, revoked/retired/conflicting bindings,
  unlinked Google accounts, stale/mismatched challenges and live email claims
  fail closed. Targets are locked in UUID order; the entire apply is atomic.
- Existing matching verification is a no-op; replay of the same manual operation
  returns its durable event IDs. Changing an already recorded operation's targets
  or provenance is rejected. Use a new explicit reviewed operation for a later
  batch; no current-account enumeration or future auto-grant exists.

Run the reviewed public script with private JSON through stdin: parent may use
`docker exec -i <api-container> python -c <PUBLIC_SCRIPT> plan`, then the same
reviewed script/input with `apply` only after reviewing safe counts. Private JSON
must never appear in argv, chat, logs or Git. A local `--input <private-file>` is
also supported: regular root/self-owned file, NOFOLLOW leaf, mode0600/private
(no group/world permissions), bounded16KiB. Stdout contains operation/fingerprint,
counts and durable event IDs, never email, OTP, manifest body or DB URL. No
credential is embedded in this file or the script. Storage/input failures are
sanitised and return nonzero.

`plan` makes no business changes. `apply` creates only the selected institutional
bindings and actual manual canonical outcomes. Existing unused real challenges
are superseded and their queued/inflight delivery intents cancelled, not marked
OTP-consumed; already transmitted email cannot be physically recalled. Synthetic
cases create no challenge or delivery intent. No SMTP/model/provider call occurs.
No legal receipt, profile/photo, onboarding activation or application operator
privilege is granted; the user still completes those explicit flows.

## Durable manual provenance

The existing `auth.email_confirmed` canonical family records a manual staging
membership decision, **not proof of mailbox delivery or a consumed OTP**. Its
occurrence key is versioned `smv1:<operationUUID.hex>:<source>:<performed_by>`:
`source=p` means the exact owner-approved placeholder; `source=c<base64url UUID>`
references the actual requested challenge. The key remains within the existing
100-character CHECK. Account ID, actual DB timestamp and retained binding link
are preserved; no fake HTTP request/trace, student action, consent, verification
intent or foreground discovery activity is manufactured. Changes are staged to
the existing guarded invalidation outbox. The application schema and audit
permissions are unchanged. Parent retains the private execution receipt outside
Git with private permissions.

## Enforced source quality and evidence

From `backend/`, ordinary `make lint` explicitly checks the helper using
`--config pyproject.toml`; `make typecheck` includes it in strict mypy. Unit cases
live in `tests/unit/test_manual_stage_verification.py` and run with ordinary
`make test-unit`; actual DB guards live in the matching integration module.
The existing standard test assert rule applies, no new Ruff/typing/coverage
exemption. Pytest `pythonpath=['..']` and explicit mypy source/package bases make
the deployment namespace reproducible without ambient `PYTHONPATH`.

Executed four-account staging grants used immutable helper SHA256
`6ae9b5d3fdf8f8d5de48043d545fe6c9063927e62e4ad2a78eb9fd1aaf2681c2`.
That exact executed source and original8unit/5PG evidence remain unchanged under
`/tmp/peerly-manual-stage-verification-frozen`. Subsequent strict-quality cleanup
renamed the error class, extracted the identical requested-source guard, typed
imports/test doubles and converted unit cases to typed pytest. It is a separate
publication candidate, not a rewritten execution receipt. Strict Ruff/format and
mypy3 pass; one justified post-refactor8unit+5actualPG run passed13/13 in6.84s
without ambient PYTHONPATH. No further live grant or broad suite was executed.
