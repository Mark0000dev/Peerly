import logging

import pytest

from studymate.infrastructure.ai.transaction_diagnostics import (
    AiTransactionDiagnostic,
    TransactionCause,
    TransactionOperation,
    TransactionPhase,
)
from tests.ai_saturation_diagnostics import failure_counts, stored_counts

STORED = 8
EXPECTED_STORED = 7
QUEUED = 2
EXPECTED_QUEUED = 5
CONTROLS = 3


def record(value: object) -> logging.LogRecord:
    result = logging.LogRecord("studymate.ai", logging.WARNING, "", 0, "PRIVATE", (), None)
    result.__dict__["ai_transaction_diagnostic"] = value
    return result


@pytest.mark.parametrize("phase", list(TransactionPhase))
def test_closed_phase_counts_preserve_commit_uncertainty(phase: TransactionPhase) -> None:
    diagnostic = AiTransactionDiagnostic(
        phase, TransactionOperation.ADMIT, TransactionCause.DEADLINE, deadline_expired=True
    )
    counts = failure_counts([record(diagnostic), record("PRIVATE"), record(None)])
    assert counts[f"burst_failure_{phase.value}"] == 1
    assert counts["burst_failure_deadline"] == 1
    assert sum(value for key, value in counts.items() if key != "burst_failure_deadline") == 1
    assert "PRIVATE" not in str(counts)


def test_stored_states_include_unknown_without_exporting_content() -> None:
    counts = stored_counts(
        iter(
            (
                "queued",
                "queued",
                "running",
                "cancelled",
                "expired",
                "failed",
                "succeeded",
                "PRIVATE",
            )
        ),
        4,
    )
    assert counts["post_burst_stored"] == STORED
    assert counts["post_burst_expected_stored"] == EXPECTED_STORED
    assert counts["post_burst_queued"] == QUEUED
    assert counts["post_burst_expected_queued"] == EXPECTED_QUEUED
    assert counts["post_burst_other"] == 1
    assert "PRIVATE" not in str(counts)


def test_empty_observations_have_explicit_zero_counts() -> None:
    assert all(value == 0 for value in failure_counts([]).values())
    counts = stored_counts([], 0)
    assert counts["post_burst_stored"] == 0
    assert counts["post_burst_expected_stored"] == CONTROLS
