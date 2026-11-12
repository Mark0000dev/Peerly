# Isolated MVP AI

Student AI is optional assistance: clarify goal text, suggest broad knowledge
areas, assess an owned profile photo. Internal report prioritisation is advisory;
humans decide every punitive action. AI never certifies enrolment/competence,
automatically saves goals or applies moderation. Core workflows remain usable
when AI is waiting, unavailable, rate-limited or failed.

## Typed jobs and durability

Use bounded server-defined task variants and actual owned source versions or
explicit immutable unsaved draft snapshots. No arbitrary prompt/provider flags,
course eligibility grant, whole-conversation extraction or automatic goal write.
Report input is selected retained evidence; its text task does not claim to see
image pixels. Account/session/operator grant/evidence checks repeat at claim and
finalisation; stale advice cannot become current authority.

A durable PostgreSQL queue stores immutable input, operation identity, attempts,
versions and outcomes. Actor quotas, bounded backlog/deadlines and scheduling keep
AI overload separate from the core API. Admission has a dedicated pool2 and a
short total budget; singleton worker/heartbeat has pool1. No SQL connection is
held during native inference. Polling is authoritative; no fictional completion.

## Bounded queue policy

The implemented policy caps global queued jobs at100, reserving10 for internal
triage and allowing at most2 outstanding student jobs. The actor bucket capacity
is5 with one token per minute. Student queue lifetime defaults5 minutes, internal
triage30; retry attempts and native execution remain bounded by the actual job
deadline. Scheduling serves no more than4 interactive claims before a due internal
claim, using actual actor/fairness sources. These are capacity limits, not provider
throughput or completion guarantees. Source policy validates configurable bounds.

Admission's total2s includes pool/lock waits; unavailable/full circuit returns a
truthful retryable outcome without a fake queued row. Actor quota is distinct.
Rate limits/circuit/cache/process uncertainty do not authorise account rotation,
login loops or lease-only takeover. Poll current result; no token streaming needed.

## Native execution and credentials

The MVP runs one isolated native Codex subscription executor; a future ordinary
API adapter may replace it behind the same typed ports. The developer's auth/home
is never a credential source. Use a dedicated managed cache and fresh per-job
workspace, explicit account/model binding and supported pinned CLI behavior.

The singleton has process/cgroup/namespace and bounded execution/output/resource
limits. Tools, filesystem/FD/proc/env/auth access and network egress are explicitly
restricted and proven, not inferred from a read-only flag. The child cannot use a
general proxy or direct internal telemetry path. Credentials and private content
never enter logs. Structured tasks do not load developer project instructions.

Cache flock/journal ownership, durable lease generations and physically confirmed
process cleanup fence successors. A timed-out process, expired SQL lease, stale
heartbeat or paused slot is not proof that native execution stopped. Uncertainty
stays blocked for explicit recovery; no manual ready/guard grant or credential
volume replacement. Receipt/renewal ownership binds actual container namespaces,
policy/binary/resource facts and provider identity. New CID needs fresh proof.

## Metrics and acceptance

Owned worker spans/metrics contain bounded dimensions; source/request/actor links
belong in traces, never high-cardinality metric labels. The queue sampler reads
asynchronously and callbacks only expose cached numbers. One aggregate query
observes depth/oldest/occupancy/circuit, with a bounded inclusive sample deadline.
Missing/stale samples are absent with explicit freshness health, not fake zeros.

Controlled tests cover queue races, quotas, source revocation, physical cleanup,
cache uncertainty, no held inference connection, cancellation and stale outputs.
Real namespace/transport/auth/provider/renewal acceptance remains separate from
unit/PG success. Proving the three student tasks does not prove internal triage.
A private synthetic schema/native case is not a public report or root-HTTP proof.
Never run a second model owner alongside the active main worker to close a test.
