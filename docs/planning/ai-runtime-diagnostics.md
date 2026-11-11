# Bounded AI runtime failure diagnostics — 11 November 2026

Locally accepted:108 unit/controlled-runtime cases passed2.33s in one batch,
strict Ruff/format/mypy over5 changed source/test files and4 architecture contracts
passed. No provider call, auth/cache read, process containment proof, PostgreSQL
behavior change, real restart or deployment was performed. This is a diagnostic
patch, not a repair of an identified database outage.

Parent verified the stopped deployed transactions.py hash
`92fb4e45994a79b911d4882e13df698a0562c202c26aba20ffb1e2c76e6e1579`
and terminal open_transaction frame19. That source translates OperationalError,
InterfaceError, pool timeout or OSError into StorageUnavailableError. The terminal
category is confirmed; which underlying cause occurred cannot be reconstructed
from that old sanitized stack. Cleanup revoke failure could also mask a primary
failure. No extra causal claim or automatic recovery follows from this evidence.

The stdlib-only frozen AiRuntimeDiagnostic carries actual closed phase/code and
an actual boolean primary marker. The factory records a failure before reraising
the SAME exception; primary heartbeat/receipt evidence survives a later cleanup
error. Secondary revoke/worker-cleanup evidence remains separate. Normal quiesced
heartbeat cancellation is not reported as a primary failure. Existing await
order, lifecycle calls, exception propagation, gather(return_exceptions=True),
lease/receipt TTL, ownership/fencing and capacity retention remain unchanged.
No retry, replacement takeover, new deadline, process/thread or SDK is added.

The safe formatter exports only these additional finite fields:

- event: `ai_runtime_failure`;
- ai_runtime_phase: receipt_recheck, heartbeat, revoke, physical_cleanup, retire;
- ai_runtime_code: storage_unavailable, ownership_lost, receipt_rejected,
  physical_stop_uncertain, credential_uncertain, cancelled, unexpected;
- ai_runtime_failure_role: primary or cleanup.

No exception text/class names, SQL, credentials, URLs, account/job IDs, prompts or
private business content enter this packet. Arbitrary lookalike/forged packets
are rejected by the formatter. Existing sanitized stack behavior remains intact.
These are ordinary technical logs, not an application technical-alert producer.
Prometheus/Alertmanager owns alerts into the approved existing Peerly Dev group.

Collector compatibility is separately owned by Aquinas: admit this exact event
and three bounded body fields, retaining strict privacy checks. The old collector
would drop them; source-local tests do not prove deployed end-to-end log delivery.
Actual image publication, collector rollout, old-container/cgroup stop evidence,
cache handoff, fresh same-namespace receipt and controlled restart remain parent
operations. Receipt expiry alone never authorizes executor replacement.

Evidence: `/tmp/peerly-ai-diagnostics.log`, `.xml`, `-static.log`, and
`-architecture.log`; the accepted snapshot is also persisted under sibling
`.peerly-ops/noether` before publication. Historical stopped-worker evidence and
future real deployment receipts remain distinct from this local acceptance.
