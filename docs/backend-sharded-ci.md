# Optional backend test shards

This candidate workflow runs only pushes to `work/backend-sharded-*`. It publishes
no image and does not replace the required serial Backend workflow. The existing
serial trigger also matches those branch names, allowing comparison on the same
application source. Keep serial acceptance required until real sharded CI completes
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
the accepted serial result for the same application bytes. Node counts may increase
because the new CI helper regression tests also belong to the inventory; do not
hardcode the old5377 count. Compare application hashes and test changes explicitly.
Record wall time per job and final critical path before claiming a speedup. Hash
partitioning spreads nodes deterministically but does not guarantee equal durations.
No timing claim or serial-workflow replacement follows from synthetic tests.

## Primary references

- [pytest public hooks](https://docs.pytest.org/en/stable/reference/reference.html)
- [pytest-cov reporting](https://pytest-cov.readthedocs.io/en/latest/reporting.html)
- [coverage data combination](https://coverage.readthedocs.io/en/latest/commands/cmd_combine.html)
- [pinned artifact download release](https://github.com/actions/download-artifact/releases/tag/v4.3.0)
