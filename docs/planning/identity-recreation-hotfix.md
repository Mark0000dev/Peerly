# Urgent retained-identity recreation hotfix

Owner explicitly changed the former deletion rule: a person may use trusted
Google login to register a **new account** after soft deletion, then prove the
institutional mailbox again. This supersedes the old “never recreate” wording;
it does not restore the deleted actor. Operator work is paused.

## Source and data contract

`external_identities` and `institutional_bindings` keep their original primary
keys, account ownership, issuer/sub, canonical email, timestamps and all existing
FK references. Each gains nullable `retired_at`; its `(account_id,retired_at)` FK
must match `(accounts.id,accounts.deleted_at)`. A live account cannot fabricate
retirement or release a claim merely by revoking membership. Partial unique
indexes enforce one active issuer/sub and one active institutional address where
`retired_at IS NULL`. Nonunique history indexes support retained lookup. The
per-account Google-link uniqueness and institutional-binding PK remain unchanged.

Real deletion retires claims in the existing transaction with session/challenge/
delivery/request/AI effects and the actual retained lifecycle source. No old
content, role, analytics, registration, relationship or association row is moved,
anonymised or deleted. Migration backfills actual already-deleted accounts only.

Google callback serialises trusted issuer/sub resolution with the existing
advisory lock and locks retained accounts/previous-session scope in UUID order.
It rechecks deletion/ban after locks. Deleted/unbanned claims may yield a new
UUID plus a new limited session; an existing live claim yields that existing
actor. Two fresh callbacks cannot create two active accounts. Callback replay
still cannot issue another session. Old session and deletion-workflow receipts
never authorise the new actor. A genuinely fresh mailbox code is required to
claim a retired email; another live/revoked nondeleted owner remains a conflict.

Known retained Google/mailbox associations are consulted for current bans,
including chains across later verified credential changes. They only restrict,
never grant old permissions or merge accounts. No unknown-person inference or
email-as-login is added. Session/bootstrap sees actual restricting bans;
Google recreation and fresh email claim cannot clear them. Ban/unban retains its
actual source account; no invented duplicate lifecycle rows or copied grants.
Existing account lock order and product timeouts are unchanged. Already in-flight
external work is not claimed to be physically recalled.

## Public API and packaging boundary

No route, DTO, enum or cookie/proof shape changes are intended. Google still
returns the existing safe browser303; `/me` returns a distinct account UUID,
`membership_status=unverified`, no registration receipt and existing limited
capabilities. Client must retire the prior actor's queries as it already does.
Institutional OTP is membership proof only, never login. Fresh explicit
registration records the versions actually displayed; old receipts remain old.
An old deletion-status cookie remains a receipt-only capability for its original
workflow, never a fresh session or restore grant.

The eight unaccepted operator bootstrap mounts and new operator audit action
behaviour have been removed from the active hotfix source and preserved under
`/tmp/peerly-be07-paused`. Bootstrap is byte-identical to the accepted96-path
baseline. Paused operator factory/tests/new support files must not be selected
for the urgent image. Only shared schema constants/index metadata accompany the
0053 prerequisite; no operator search writer/route is activated.

## Migration and deployment receipt — parent only

One linear head: `0052_student_support` → `0053_operator_support_search` →
`0054_identity_recreation`. Do not rename/drop/reuse/fork0053. Once
published it is immutable.0053 is forward-compatible schema only: it preserves
all old audit/event constraint branches, adds a narrow unused support-search
branch and a read index; no business-row UPDATE/DELETE, active operator action or
public endpoint is introduced.0054 backfills retirement from actual deletion,
then replaces only global identity/email uniqueness with active uniqueness.

Parent must select the accepted core source plus the explicit identity delta,
the three schema-only model files, both migrations and meaningful regressions.
Do not include operator WIP or unrelated AI/frontend changes. Preserve the
existing runtime secrets/keys, database contents and separately accepted AI
worker. Run actual staging migrations **before** promoting the API image. Record
pre/post Alembic head, input/source/image hashes, affected retirement counts,
original/new association identifiers and that no business records were purged;
never include credentials/OTP/issuer subjects/email values in ordinary logs.

Before migration/promotion the owner controls traffic during the brief mixed
version interval. Once a new generation exists, the old global issuer/sub lookup
is unsafe: it expects one retained row and may fail or resolve the wrong actor.
**Do not roll back to an old API binary after new generations are admitted.**
Use an identity-aware forward fix/rollback image or a separately planned complete
DB restore with admission stopped; no silent history purge or active-claim
reassignment.0054 downgrade refuses any retained retirement source, even without
current duplicate identifiers, instead of losing those facts. No developer
runs actual migrations/deployments or reads secrets.

## Policy correction

Published v1 Terms section7 says normal sign-in does not recreate a deleted
account. That sentence now conflicts with the owner decision. Keep v1 immutable;
parent authors/publishes a new version and informational behaviour notice. State
that fresh Google authentication may create a separate new account requiring a
new APU mailbox proof, old chats/content/roles are not restored, all historical
business/analytics links remain internally retained, and bans cannot be evaded.
Do not rewrite prior registration receipts or introduce reacceptance/checkboxes.
A migration is not evidence that the new policy version has been published.

## Acceptance boundary

One scoped source/unit/real-PG/root batch: active partial uniqueness and actual
retirement-source FK, old52→53→54 with business identifiers retained, honest
downgrade refusal, duplicate fresh callbacks and prelock deletion/ban races,
retired-email proof/ban conflict, repeated actual browser delete/register/mail/
registration generations with old chat/data isolation, old sessions/OTP/workflow
replay denial, existing login/email/lifecycle regressions and model/schema drift.
No49-minute full loop or live provider email/Google/model calls. Parent owns the
real post-migration deployment receipt and smoke. Evidence/results will be linked
in the final immutable hotfix handoff; source-authored tests are not yet a pass.
