# Bounded local admission and continuity measurements

This explicit harness reuses the existing saturation fixtures, actual root ASGI
application lifespan, PostgreSQL migrations, queue and ExecuteNextJob. It tests
HTTP admission/CSRF/serialization, finite interactive queue backpressure, retained
idempotent replay and core reads/profile writes with a slow or unavailable AI
executor. There are no provider calls, stage mutations, live credentials or fake
HTTP responses.

The fixed fixture population is 500 synthetic persisted account/binding/session/
goal records. It does not execute 500 Google registrations or prove completed
onboarding. The additional core HTTP actor uses the existing controlled Google
login fixture. Each student uses its actual stored synthetic session cookie and
obtains a CSRF token from the real `/me` endpoint.

`--active-users` selects 100, 250 or 500 distinct fixture accounts issuing one
measured AI command each. `--concurrency` caps AI requests in flight at 10 or 25;
one separate core traffic task overlaps them. Neither the population nor the
attempt count is a claim of 500 simultaneous requests. The driver is closed loop:
throughput is completed attempts divided by measured mixed-traffic wall time, not
a claimed external arrival rate.

Run only in a coordinated quiet resource window. Use the pinned backend virtual
environment on Linux and a caller-owned loopback PostgreSQL database ending in
`_test`, without URL query overrides. The fixture rejects remote URLs and uses a
unique schema with real Alembic migrations and normal teardown. No `create_all`,
shared reset, provider inference or application budget changes are used.

From `backend/`, with the authorized synthetic `TEST_DATABASE_URL` already set:

```sh
.venv/bin/python ../deployment/load/run.py \
  --active-users 100 --concurrency 10 --mode both \
  --output /absolute/private/load-receipts/step-100-10
```

The output directory must be new and outside the product repository. The runner
invokes only the two explicit scenario nodes, serially, with the same interpreter;
no broad suite, automatic retries or population/concurrency matrix runs. Choose a
later step explicitly after assessing the previous receipt. Heavy scenarios live
in `tests/load/scenario.py`, outside ordinary test filename discovery. The small
measurement regression definitions remain ordinary tests.

In slow mode, real HTTP positive controls occupy one running execution and all
90 interactive queued positions before measurement. Every measured new intent
must return503, core reads and one profile command/replay must remain successful,
then cancellation must free capacity for a new accepted command. In offline mode,
a real clean readiness revocation precedes measurement: new commands return503,
a retained original command replays without readiness, and a new readiness lease
permits recovery. Provider execution remains controlled in both cases.

Every reported positive admission must reconcile exactly to stored jobs and
actor-scoped immutable intents; rejects must leave neither hidden jobs nor
intents. Core command replay/readback must retain its original profile version.
A successful receipt also requires overlapping core samples, finite measured
latencies and the existing local bounds (core under2s, observed AI under3s).
These local component limits are not a production SLO agreement.

Each mode produces a JSON receipt and JUnit output; `run.json` records actual
exit codes and completed-receipt presence. Receipts contain counts, latency,
throughput, host CPU/memory, process CPU/high-water RSS and pool sizes, never
cookies, CSRF tokens, request bodies or returned private text. CPU includes queue
setup but excludes student seeding; RSS is the whole process high-water value,
not a phase-local peak or PostgreSQL resource measurement. Failure never creates
a successful capacity receipt. Cancellation requests pytest interruption, then
bounds child shutdown; a forced kill may require inspection/cleanup of the exact
owned disposable schema before another run.

This is in-process root-ASGI load with real business storage and controlled
executor boundaries. It does not prove production ingress/TLS/WAN capacity,
500 concurrent users, SSE/uploads/chat traffic, mobile behavior, actual provider
throughput or cost, full security acceptance, or production capacity. Those remain
separate release measurements. Artifacts always mark production capacity false.
