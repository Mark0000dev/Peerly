# Temporary staging verification

The owner explicitly authorises manually verifying the current internal staging
accounts while university Outlook quarantines mail. For accounts without a
submitted address the owner additionally authorises an intentional unique
placeholder: `peerly-stage-<account UUID without hyphens>@mail.apu.edu.my`.
These are synthetic staging identifiers, not evidence of mailbox possession.
Never send mail to them or copy these temporary claims into production.

`deployment/backend/manual_stage_verification.py` is an administrative command,
not an HTTP endpoint or new authentication mechanism. It runs against the
existing application image and rejects databases other than `peerly_staging`.
It accepts a private JSON manifest on stdin with `operation_id`, a bounded
`performed_by` reference and explicit `entries` containing `account_id`, `email`
and `challenge_id`. Use the actual latest submitted challenge/address where
present. Only an account with no email challenges may use its exact UUID-derived
placeholder and `challenge_id: null`. No challenge, OTP-consumption intent,
registration receipt or profile is fabricated.

Run `plan` first, inspect its counts, then `apply` with the same manifest and
reviewed script bytes. Do not pass private JSON, addresses or credentials on the
command line. Store private inputs and receipts outside Git with mode0600. The
command locks accounts in UUID order, rejects deleted/restricted/conflicting
claims and applies the batch atomically. Replays retain the original event IDs.
Canonical `auth.email_confirmed` events carry `smv1` manual provenance with the
operation, performer and actual-challenge/placeholder source. This administrative
action does not count as foreground user activity. Existing pending mail secrets
are cancelled/superseded rather than represented as successful OTP input.

## Applied internal batch — 10 November 2026

Parent executed reviewed script SHA256
`6ae9b5d3fdf8f8d5de48043d545fe6c9063927e62e4ad2a78eb9fd1aaf2681c2`
through the actual staging API container with private stdin. The actual plan
reported four eligible accounts, two using placeholders; apply confirmed four
new bindings and four durable manual-source events, with no OTP consumed.
Post-apply read-only inventory confirms five retained accounts, four active and
four verified. The deleted account is excluded. Two users retain their actual
submitted institutional addresses, two have intentional placeholders. No image,
schema or public API changed and no verification emails were sent by the command.
Actual PostgreSQL write/replay/rollback/restriction cases passed5/5; input/provenance
unit cases passed8/8. Full backend acceptance is a separate pipeline receipt.

Users should reload the application to refresh `/me`. Normal registration
acknowledgement and profile/goal/help setup still apply. This is a one-time
explicit batch, not automatic verification of new accounts. A real operator UI
for manual verification is deferred until the existing operator screens and
privileged backend are complete; it must use audited operator authority rather
than exposing this deployment command publicly.
