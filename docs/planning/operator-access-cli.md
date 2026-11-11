# Explicit operator access provisioning

Locally accepted administrative tool:14unit cases passed1.39s and16actual
PostgreSQL cases passed77.81s, in separate bounded runs with no retries. Strict
Ruff/format/mypy pass for all3source/test files. Logs/XML use
`/tmp/peerly-operator-access-{unit,pg}`; static log ends `-static.log`. No public route,
new role, schema revision, automatic account selection or actual grant is implied.
Parent owns publication and real execution after identifying the owner's target.

`deployment/backend/operator_access.py` is run by a trusted deployment/DB owner,
not by a student session. Its OS/database authority is the administrative boundary.
`performed_by` is an explicit existing Google-linked account attribution asserted
by that administrator; it is not a claim of interactive authentication. Bootstrap
of the first operator intentionally does not require an existing operator grant.

Supply private JSON on stdin or a no-follow, owner/root-owned regular file with
no group/world permission bits. One exact target per command:

```json
{
  "database": "peerly_staging",
  "performed_by": "00000000-0000-4000-8000-000000000001",
  "account_id": "00000000-0000-4000-8000-000000000002",
  "expected_version": 0,
  "active": true
}
```

These UUIDs are examples, not targets to apply. `DATABASE_URL` is supplied only in
the private environment; its exact database and actual `current_database()` must
match the manifest. No fallback to default_db, mailbox/Google-sub lookup or shell
argument containing JSON is supported. Module execution from repository root with
backend installed: `python -m deployment.backend.operator_access plan --input -`,
then `apply` using the reviewed same manifest. Installed API images do not contain
this deployment module: parent must copy the exact reviewed helper into an owned
read-only location or use its exact source via private stdin execution. Do not
assume a new core image or startup hook is needed.

The tool locks administrator/target account rows in sorted UUID order, then the
actual current access source. Both must exist. Administrator must have a live
Google identity and no deletion/ban or retained-identity ban. A grant has the same
requirements for its target; institutional verification/profile activation is not
operator authority. Revocation can target a deleted/banned account. There is no
lifecycle change, session creation, mailbox verification or permission inheritance
from another generation of a deleted identity.

`expected_version=0` means no prior access record, not a revoked record. First
grant inserts version1. Revocation/regrant append immutable versions and advance
the existing current pointer. Old revisions and inspection references remain.
Each revision records actual DB time, active state and the asserted real
`changed_by_id`: this is the existing canonical role/audit source. No synthetic
`operator.inspected` event, HTTP request/trace, interactive session or human
inspection is fabricated. Initial grant cannot truthfully claim an already-active
operator inspection. No parallel audit table or new canonical event kind is added.

Plan validates the same eligibility/CAS under short locks without writing. It is
not a reservation. Apply revalidates and commits before printing success. Stale
versions or redundant same-state changes fail without appending history. No
idempotency operation is fabricated from a request ID: after timeout/lost output,
inspect the retained current revision and its provenance with the deployment DB
owner before another apply; do not blindly update expected_version/retry. There
is no exactly-once receipt claim. Output contains fixed status, UUIDs and versions,
never mail, tokens, connection strings, SQL/exception text or private content.

Core runtime/source, migrations55–57 and frontend contracts remain unchanged.
The new helper is enforced by backend Makefile Ruff/format and strict mypy, and
its pytest definitions run in ordinary unit/integration discovery.
