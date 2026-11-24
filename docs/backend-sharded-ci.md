# Optional backend test shards

This candidate workflow runs only pushes to `work/backend-sharded-*`. It publishes
no image and does not replace the required serial Backend workflow. The required
serial workflow still runs pull requests and pushes to `main`;
a shard-branch push alone does not trigger serial acceptance. For a future
coordinator-approved comparison, retain required serial PR evidence for the same
head SHA. Do not alter or restart the current live serial run for this offer.
Keep serial acceptance required until real sharded CI completes
and its inventory, artifacts and coverage have been reviewed. Local helper tests do
not establish performance, PostgreSQL isolation or full-suite equivalence.

The candidate uses the existing uv lock, pytest, pytest-cov and coverage.py. It adds
no dependencies or xdist. Existing `Makefile`, `pyproject.toml`, `uv.lock` and
`.github/workflows/backend.yml` remain unchanged.

## Execution and evidence

1. The inventory job uses actual pytest collection, including every parameterized
   node, in its original order. Collection errors/skips, empty or duplicate IDs fail.
   It records the commit, ordered inventory and hashes of all Git-tracked backend
   and deployment files plus the serial/candidate workflows. This includes fixtures,
   binaries and configuration, not only Python. A separate application hash binds
   tracked backend `src` and migration bytes for comparison with serial acceptance.
   No environment values or untracked files enter these hashes.
2. Four independent Ubuntu24.04 jobs each start their own PostgreSQL16.15 service.
   Every job recollects the complete ordered inventory and requires the same source
   hash before selecting `SHA256(nodeid)[0:8] mod4`. Selection preserves collection
   order. All collected nodes belong to exactly one partition; no marker/path test
   filters are used. Each selected test runs through normal pytest fixtures/lifecycle.
3. Each job records actual setup/call/teardown reports, selected IDs, pytest exit,
   commit/source/inventory identity and SHA256 of its real branch coverage database.
   Missing, duplicate, failed, skipped, xfailed or unexpectedly passing xfail phases
   reject. Unchanged source is checked again after tests. The JUnit report is retained.
4. The final job runs with `always()` but requires inventory/static/all shard jobs to
   have actually succeeded. It downloads only the four current-run shard artifacts,
   requires exact expected selections and disjoint complete executed-node union,
   checks every coverage SHA and requires actual branch measurements. It combines
   the four databases using coverage.py and produces `coverage.xml` plus a receipt.
   The unrounded combined branch-aware total MUST be at least95%; otherwise it fails.
   It also rejects a changed source/commit, disabled branches, changed coverage
   source or a modified global threshold. Individual shard green states and artifact
   existence alone cannot establish acceptance.

Per-shard `--cov-fail-under=0` defers the threshold because each partition alone has
partial coverage. It does not change the project configuration: the FINAL gate
requires the original95% setting and enforces it on the combined data. No per-shard
percentage averaging, XML merging, source exclusions or partial successful receipt
is used as the global coverage result.

A separate job runs the unchanged `make lint typecheck architecture`, explicitly
strict-types both new root CI helper modules, then runs the existing Alembic head
smoke check against its own disposable PostgreSQL. Existing warnings-as-errors,
markers, fixtures, migration history and test bodies remain intact.

## Commands and failure behavior

From a clean locked backend checkout on the candidate CI runner:

```sh
uv run python ci_shard.py inventory --commit "$GITHUB_SHA" --output shard-inventory.json
uv run python ci_shard.py run --commit "$GITHUB_SHA" \
  --inventory shard-inventory.json --shard 0 --output shard-output
uv run python ci_combine_coverage.py --commit "$GITHUB_SHA" \
  --inventory shard-inventory.json --artifacts shard-artifacts
```

Artifact names bind both GitHub run ID and run attempt; all four inputs must come
from that attempt. Rerun the complete candidate workflow, not selected jobs with
stale artifacts from a previous attempt.

The workflow supplies separate jobs/output artifacts for shards0 through3; do not
run them concurrently against one local database. Existing UUID schema fixtures
continue to isolate individual tests within each job. The helper refuses stale
coverage data and ambient `PYTEST_ADDOPTS`/alternate `COVERAGE_FILE` settings. The
hosted runner must already provide `/usr/bin/git`; the helper only reads tracked
path names and never changes Git state. Missing input or execution failure fails
closed; it is not permission to skip a shard or edit its receipt.

For candidate validation, preserve the optional final job URL, all four job results,
complete inventory, source/application hashes, counts and coverage receipts alongside
the accepted serial result for the same application bytes. The API132 source base
is `a30b41ca062632ff421a349f0952d9a106c692dd`
(1445 tracked backend/deployment-backend files). The source-only discovery contains
5298 original cases plus24 selected-evidence cases plus28 existing helper controls =5350 cases. These counts are
evidence, not hardcoded acceptance criteria: actual complete ordered inventory
and receipts remain authoritative. Historical5444-node drift runs are superseded.
The explicit IDs from `c768564` cover exactly the six randomized parameter IDs
demonstrated between fresh collections; the values and assertions stay unchanged.
Compare application hashes and test changes explicitly.
Record wall time per job and final critical path before claiming a speedup. Hash
partitioning spreads nodes deterministically but does not guarantee equal durations.
No timing claim or serial-workflow replacement follows from synthetic tests.

## Primary references

- [pytest public hooks](https://docs.pytest.org/en/stable/reference/reference.html)
- [pytest-cov reporting](https://pytest-cov.readthedocs.io/en/latest/reporting.html)
- [coverage data combination](https://coverage.readthedocs.io/en/latest/commands/cmd_combine.html)
- [pinned artifact download release](https://github.com/actions/download-artifact/releases/tag/v4.3.0)


## Current source-only status and resource bounds

This six-file source offer reuses `904ce667`; only the optional workflow's checkout
pin (matching the current required workflow), explicit same-SHA checkout, bounded
four-job matrix concurrency, static prerequisite and this documentation are
rebased. The two helpers and their two unit files are
unchanged donor bytes. Three operator test files receive only the demonstrated
explicit parameter IDs from `c768564`, with no value/body/assertion changes.
`Makefile`, `pyproject.toml`, `uv.lock`, application/migration bytes and the required
serial `.github/workflows/backend.yml` are unchanged. No dependency installation,
workflow dispatch, PG/full/shard execution, image publication or provider action
is part of source preparation.

The optional matrix has exactly four independent runner jobs, max-parallel4,
fail-fastfalse and60-minute per-job timeout. Shards wait for both inventory and
static success before allocating their jobs. All four checkouts explicitly pin
`${{ github.sha }}`; no moving branch reference enters the comparison.
Inventory/static/aggregate timeouts remain10/20/15minutes; artifacts retain7days.
Each Git manifest read is bounded30seconds; receipt reads cap8MiB, stale coverage
is refused, and only actual
three-PASS-phase results can enter the exact four-way aggregate. Each job owns
its separate PostgreSQL service. Hosted runner CPU/RAM and actual database/storage
usage have not been measured or accepted by source checks. Both optional static
and matrix PostgreSQL services now specify `--cpus=1 --memory=3072m
--memory-swap=3072m`: CPU1 and3GiB memory with no extra swap allowance, matching
the existing local controller flags. These are ceilings, not reserved capacity
or proof of host fit. Required serial stays unchanged and uncapped; resource
equivalence is unproven. No local maxconn20/maxlocks186/tmpfs/PID changes are
carried into the hosted service. Keep PGversion, health checks, database settings
and server defaults unchanged. Do not label this the full local locked-PG envelope
or claim native resource acceptance. CPU throttling/OOM remain real failures.
No pool/time/SLO or
required serial resource setting is increased. Four simultaneous isolated jobs
are a ceiling, not evidence of proportional speedup; actual wall-time and resource
receipts are required before any performance claim.

The existing per-shard coverage reporting deferral is NOT a global gate. Only
all four actual current-attempt result/coverage artifacts, same commit/source/
ordered-inventory hashes, exact nonoverlapping union and unrounded combined
branch coverage>=95 can establish future optional acceptance. Synthetic28 helper
controls and source-only collection are not those native reports. Missing/failed
shards, artifact drift, collection errors or partial coverage remain failures.
No ignore, hidden deselection or lowered project threshold is introduced.

The required serial workflow remains required and unchanged while this optional
implementation is unproven. Do not revive historical4336... runs, accept the old
5444 inventory, mix artifacts between attempts, or repeat a local full gate.
This source offer launches no hosted/native execution and alters no required gate.


### Optional PG cap amendment (source only)

The cap change touches only the optional static and matrix service options and
this documentation. It does not change Python helpers, stable IDs, test bodies,
required serial workflow, runner label, project thresholds or time budgets. Repo
sources contain no exact hosted CPU/RAM entitlement: no host capacity is assumed.
No dependency, observer or admission framework is added. Existing28 helper controls
and affected Python statics are reused by exact byte parity; no redundant runs.
The prior5326-case inventory predates selected-evidence source and is not an
actual inventory for the amended workflow hash. Future coordinator-approved CI
must freeze a new inventory on its own exact committed SHA, verify effective caps,
retain actual4reports/disjointcompleteunion, and enforce combined branch>=95.
No resource acceptance, capacity/speedup claim or execution follows from this edit.

### Current02 source discovery

The exact base is a30b41ca062632ff421a349f0952d9a106c692dd. Two fresh guarded
collections confirmed identical ordered5350-node inventories:5298 original cases,
24 selected-evidence cases (18 mapping units and6 PG regressions), and28 existing
CI helper controls. Prior5326 nodes remain in the same relative order. Deterministic
partition sizes are1336/1327/1340/1347; their union is complete and disjoint.
No fixtures or test bodies ran. These inventories describe the base plus this
uncommitted nine-path private offer, not a final published coherent SHA. Future
actual CI must recollect on its own committed SHA. Helper/runtime/workflow bytes
remain identical to the accepted PG-cap offer; prior28controls and Python statics
are reused by byte identity. No actual four-shard reports, combined95 result, hosted
resource admission or performance acceptance is established by these collections.
