from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from deployment.backend.umami_sink_recovery import (
    Target,
    build_plan,
    private_read,
    require_runtime,
    retain_journal,
    validate_plan,
)

from studymate.application.external_delivery.recovery import (
    RecoveryRejectedError,
    UmamiRecoveryState,
    UmamiRecoveryTarget,
    recover_umami_sink,
)
from studymate.domain.external_delivery.delivery import DestinationRef
from studymate.domain.external_delivery.sources import Sink
from studymate.infrastructure.external_delivery.http_adapters.configuration import (
    UmamiConfig,
    target_fingerprint,
)

PRIVATE_FILE_MODE = 0o600


def state() -> UmamiRecoveryState:
    now = datetime.now(UTC)
    return UmamiRecoveryState(
        now, now, 0, now, None, "destination_unavailable", uuid4(), 1, uuid4(), now, now, now
    )


def target() -> Target:
    configuration = UmamiConfig(
        DestinationRef(Sink.UMAMI, 1), "https://analytics.example.test", uuid4(), "app.example.test"
    )
    return Target(
        schema_version=1,
        operation_id=uuid4(),
        performed_by="operator",
        database="peerly_staging",
        database_schema="public",
        migration_revision="0060_report_triage",
        backend_image="ghcr.io/mark0000dev/peerly-backend@sha256:" + "a" * 64,
        revision=1,
        origin=configuration.origin,
        website_id=configuration.website_id,
        hostname="app.example.test",
        fingerprint=target_fingerprint(configuration).hex(),
        failed_delivery_id=uuid4(),
    )


@dataclass
class Transaction:
    observed: UmamiRecoveryState
    clear_result: bool = True
    mutations: int = 0

    async def inspect(self, target: UmamiRecoveryTarget, *, lock: bool) -> UmamiRecoveryState:
        assert lock
        assert target.revision == 1
        return self.observed

    async def clear_block(self, expected: UmamiRecoveryState) -> bool:
        assert expected == self.observed
        self.mutations += 1
        return self.clear_result


async def test_matching_approval_only_clears_once_and_caller_owns_commit() -> None:
    approved = state()
    transaction = Transaction(
        replace(approved, observed_at=approved.observed_at + timedelta(seconds=1))
    )
    assert (
        await recover_umami_sink(transaction, target().recovery_target(), approved)
        == transaction.observed
    )
    assert transaction.mutations == 1


@pytest.mark.parametrize("change", ["reason", "schedule", "attempt", "stale", "future"])
async def test_changed_or_expired_approval_never_mutates(change: str) -> None:
    approved = state()
    actual = approved
    if change == "reason":
        actual = replace(actual, blocked_reason="credentials_unavailable")
    elif change == "schedule":
        actual = replace(actual, next_claim_at=actual.next_claim_at + timedelta(seconds=1))
    elif change == "attempt":
        actual = replace(actual, lease_id=uuid4())
    elif change == "stale":
        actual = replace(actual, observed_at=actual.observed_at + timedelta(minutes=6))
    else:
        actual = replace(actual, observed_at=actual.observed_at - timedelta(seconds=1))
    transaction = Transaction(actual)
    with pytest.raises(RecoveryRejectedError):
        await recover_umami_sink(transaction, target().recovery_target(), approved)
    assert transaction.mutations == 0


async def test_failed_cas_is_not_success() -> None:
    approved = state()
    with pytest.raises(RecoveryRejectedError, match="compare_and_swap"):
        await recover_umami_sink(
            Transaction(approved, clear_result=False), target().recovery_target(), approved
        )


def test_plan_hash_binds_hostname_image_dead_evidence_and_source() -> None:
    plan = build_plan(target(), state(), "a" * 64)
    validate_plan(plan, "a" * 64)
    restored = type(plan).model_validate_json(plan.model_dump_json())
    assert restored == plan
    with pytest.raises(RecoveryRejectedError, match="hash_mismatch"):
        validate_plan(plan, "b" * 64)
    changed = plan.model_copy(
        update={"target": plan.target.model_copy(update={"hostname": "other.example.test"})}
    )
    with pytest.raises(RecoveryRejectedError, match="hash_mismatch"):
        validate_plan(changed, "a" * 64)


def test_runtime_image_and_real_configuration_are_required(monkeypatch: pytest.MonkeyPatch) -> None:
    selected = target()
    for key, value in {
        "REVISION": str(selected.revision),
        "ORIGIN": selected.origin,
        "WEBSITE_ID": str(selected.website_id),
        "HOSTNAME": selected.hostname,
    }.items():
        monkeypatch.setenv("UMAMI__" + key, value)
    require_runtime(selected, selected.backend_image)
    monkeypatch.setenv("UMAMI__HOSTNAME", "other.example.test")
    with pytest.raises(RecoveryRejectedError, match="configuration_mismatch"):
        require_runtime(selected, selected.backend_image)
    with pytest.raises(RecoveryRejectedError, match="image_pin_mismatch"):
        require_runtime(selected, "unapproved")


def test_private_journal_is_durable_replay_safe_and_rebind_rejected(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    retain_journal(tmp_path, "operation.intent.json", {"plan": "first"})
    retain_journal(tmp_path, "operation.intent.json", {"plan": "first"})
    with pytest.raises(RecoveryRejectedError, match="journal_rebind"):
        retain_journal(tmp_path, "operation.intent.json", {"plan": "second"})
    assert private_read(tmp_path / "operation.intent.json") == b'{"plan":"first"}\n'
    assert not tuple(tmp_path.glob("*.tmp"))
    assert (tmp_path / "operation.intent.json").stat().st_mode & 0o777 == PRIVATE_FILE_MODE


def test_journal_and_inputs_reject_public_permissions_and_symlinks(tmp_path: Path) -> None:
    selected = tmp_path / "input.json"
    selected.write_text("{}")
    selected.chmod(0o644)
    with pytest.raises(RecoveryRejectedError, match="unsafe_input"):
        private_read(selected)
    link = tmp_path / "link"
    link.symlink_to(selected)
    with pytest.raises(OSError, match="Too many levels"):
        private_read(link)
    tmp_path.chmod(0o755)
    with pytest.raises(ValueError, match="unsafe_journal"):
        retain_journal(tmp_path, "operation.intent.json", {})


@pytest.mark.parametrize("command", ["apply", "inspect"])
def test_unknown_apply_retains_intent_and_inspect_never_attributes_commit(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from deployment.backend import umami_sink_recovery as cli

    selected = target()
    approved = build_plan(selected, state(), "a" * 64)
    path = tmp_path / "approved.json"
    path.write_text(approved.model_dump_json())
    path.chmod(PRIVATE_FILE_MODE)
    tmp_path.chmod(0o700)
    monkeypatch.setattr(cli, "source_digest", lambda: "a" * 64)
    for key, value in {
        "REVISION": str(selected.revision),
        "ORIGIN": selected.origin,
        "WEBSITE_ID": str(selected.website_id),
        "HOSTNAME": selected.hostname,
    }.items():
        monkeypatch.setenv("UMAMI__" + key, value)

    async def bounded_run(
        action: str, value: cli.Target | cli.Plan, source_hash: str, runtime_image: str
    ) -> dict[str, object]:
        assert value == approved
        assert source_hash == "a" * 64
        assert runtime_image == selected.backend_image
        if action == "apply":
            assert (tmp_path / (selected.operation_id.hex + ".intent.json")).exists()
            raise TimeoutError("raw-secret-must-not-appear")
        return {"status": "state_observed", "blocked_reason": None, "commit_attribution": "unknown"}

    monkeypatch.setattr(cli, "run", bounded_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "recovery",
            command,
            "--input",
            str(path),
            "--runtime-image",
            selected.backend_image,
            "--journal",
            str(tmp_path),
        ],
    )
    assert cli.main() == (1 if command == "apply" else 0)
    result = capsys.readouterr().out
    assert "raw-secret" not in result
    assert not (tmp_path / (selected.operation_id.hex + ".receipt.json")).exists()
    if command == "apply":
        assert "unconfirmed" in result
        assert (tmp_path / (selected.operation_id.hex + ".intent.json")).exists()
    else:
        assert '"commit_attribution": "unknown"' in result
        assert not (tmp_path / (selected.operation_id.hex + ".intent.json")).exists()
