# Staging-only manual membership verification

[manual_stage_verification.py](manual_stage_verification.py) is an explicit
administrative operation for approved internal staging accounts when institutional
email delivery is unavailable. It is not a public endpoint, automatic verification
for future users, production setting or mailbox/OTP proof. It does not require DDL
or change normal Google sign-in, OTP, registration or activation behavior.

Only an explicitly authorized staging operator may execute it. `DATABASE_URL`
must use asyncpg and name `peerly_staging`; both configuration and actual connection
are checked. Never rename another database to bypass this guard or run the helper
at application startup. Keep credentials and execution input outside Git/logs.

## Private input and execution

Input is a closed JSON object containing `operation_id` (UUID), `performed_by`
(1–38 ASCII letters/digits/underscore/hyphen) and 1–20 explicit `entries`. Each
entry contains `account_id`, `email` and `challenge_id`.

- For an actual requested address, use its exact canonical institutional email
  and that account's latest pending challenge UUID. Do not infer/replace either.
- An explicitly approved staging account with no email challenge history may use
  `challenge_id: null` and exactly
  `peerly-stage-<accountUUID.hex>@mail.apu.edu.my`. This synthetic binding is not a
  delivered email, OTP challenge or public registration bypass.
- Deleted/banned accounts, banned identity/email lineages, missing active Google
  linkage, conflicting/retired bindings, stale challenges and conflicting active
  email claims fail closed. Accounts lock in UUID order; the batch is atomic.
- Matching existing verification is a no-op. Replay returns durable prior event
  IDs; changing an existing operation's targets/provenance is rejected. A later
  batch needs its own explicitly reviewed operation, never account enumeration.

With the intended staging `DATABASE_URL` already configured privately, from the
repository root:

```sh
backend/.venv/bin/python deployment/backend/manual_stage_verification.py plan --input /path/to/private-manifest.json
backend/.venv/bin/python deployment/backend/manual_stage_verification.py apply --input /path/to/private-manifest.json
```

Review the safe plan counts before applying the same reviewed input. The file
must be regular, root/self-owned, without group/world permissions; the helper
uses NOFOLLOW and accepts at most 16KiB. Stdin is supported with `--input -` for
controlled container execution. Never put JSON, emails, OTPs or a DB URL in argv,
terminal output or chat. Ensure the reviewed script/runtime are actually present
where executed; this document does not install them or grant deployment access.

Output contains only status, operation/fingerprint, counts and durable event IDs.
Rejected input/storage failures are sanitized and nonzero. Retain execution
receipts privately, not in the repository.

## Effects and provenance

`plan` makes no business changes. `apply` creates only selected institutional
bindings and manual canonical outcomes. Pending real challenges are superseded
and queued/inflight delivery intents cancelled, not marked OTP-consumed. Sent mail
cannot be recalled. Synthetic cases create no challenge or email-delivery intent.
There are no SMTP/model/provider calls or automatic future grants.

The operation grants no legal receipt, profile/photo, onboarding activation or
application-operator privilege. Users still complete those required flows.
Canonical `auth.email_confirmed` records represent manual membership decisions,
not mailbox delivery or OTP success. The occurrence key is
`smv1:<operationUUID.hex>:<source>:<performed_by>`: `p` identifies the approved
placeholder; `c<base64url UUID>` references the actual challenge. Actual account,
database timestamp and binding history remain. No HTTP trace, student action,
consent or foreground discovery activity is fabricated. Guarded invalidation
outbox changes remain part of the transaction.

## Checks

Backend `make lint` and `make typecheck` include the helper under ordinary strict
rules. Unit and real PostgreSQL regression definitions are in
`backend/tests/unit/test_manual_stage_verification.py` and the matching integration
module; standard backend tests include them. Test acceptance does not authorize
or prove any live grant. Preserve input, lineage, transaction and replay guards.
