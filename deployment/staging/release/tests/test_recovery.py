"""Real journal/filesystem/orchestrator recovery with synthetic deployment I/O."""

from __future__ import annotations

import argparse
import copy
from dataclasses import asdict
from typing import TYPE_CHECKING

import httpx
import pytest
from deployment.staging.release.cli import private_write, recover
from deployment.staging.release.data import Object, RejectedError
from deployment.staging.release.journal import Journal
from deployment.staging.release.portainer import Portainer
from deployment.staging.release.providers import Package
from deployment.staging.release.release import ASSETS, BACKEND, SCHEMA
from deployment.staging.release.runtime import ObservationInputs, Runtime
from deployment.staging.release.tests.test_release import SELECTED_SHA, Fake, promotion, proof
from deployment.staging.release.transport import Http

if TYPE_CHECKING:
    from pathlib import Path

ROLLBACK_WRITE_COUNT = 4


def test_unknown_backend_rollback_reconciles_retained_maps_and_quarantines_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = Fake()
    before = copy.deepcopy(fake.snapshot)
    baseline = fake.evidence()
    p = promotion(fake)
    final = p.promote(fake.release, baseline, fake.previous)
    original = tmp_path / "original"
    original.mkdir()
    private_write(
        original / "before.private.json", {"stack": before.stack, "content": before.content}
    )
    private_write(
        original / "recovery.private.json",
        {
            "sha": SELECTED_SHA,
            "baseline": baseline,
            "previous": {role: asdict(img) for role, img in fake.previous.items()},
        },
    )
    packages = {
        role: Package(img, proof(img), fake.release) for role, img in fake.candidate.items()
    }
    journal = Journal(tmp_path / "journal")

    def no_network(_request: httpx.Request) -> httpx.Response:
        pytest.fail("recovery decision test must not access a provider")

    http = Http(httpx.MockTransport(no_network))
    inputs = ObservationInputs(
        "https://metrics.example.invalid",
        "synthetic",
        "synthetic",
        "fixture",
        "a" * 64,
        "peerly_staging",
        lambda: None,
    )
    runtime = Runtime(
        Portainer(http, "https://portainer.example.invalid", "synthetic"),
        http,
        journal,
        packages,
        inputs,
    )
    request = fake.request

    def ambiguous(path: str, data: Object | None = None, method: str | None = None) -> Object:
        response = request(path, data, method)
        if method == "PUT" and len(fake.writes) == ROLLBACK_WRITE_COUNT:
            raise TimeoutError("accepted on server, client did not receive response")
        return response

    monkeypatch.setattr(fake, "request", ambiguous)
    args = argparse.Namespace(
        sha=SELECTED_SHA,
        operation="rollback",
        reconcile_attempt="",
        recovery=str(original / "recovery.private.json"),
        compatible_schema=SCHEMA,
    )
    rollback = tmp_path / "rollback"
    rollback.mkdir()
    try:
        with pytest.raises(RejectedError, match="write_uncertain_reconcile_before_retry"):
            recover(args, p, runtime, final, rollback)
        assert (tmp_path / "unresolved.json").exists()
        assert fake.snapshot.env()[BACKEND] == fake.previous["backend"].reference
        assert fake.snapshot.env()[ASSETS] != before.env()[ASSETS]
        reconciliation = tmp_path / "reconcile"
        reconciliation.mkdir()
        args.operation = "reconcile"
        args.reconcile_attempt = "rollback"
        result = recover(args, p, runtime, p.read(), reconciliation)
        assert result.env()[ASSETS] == fake.snapshot.env()[ASSETS]
        assert len(fake.writes) == ROLLBACK_WRITE_COUNT
        assert p.phase == "reconcile_verified"
        assert not (tmp_path / "unresolved.json").exists()
        assert (tmp_path / ("rolled-back-" + SELECTED_SHA + ".json")).exists()
    finally:
        journal.close()
