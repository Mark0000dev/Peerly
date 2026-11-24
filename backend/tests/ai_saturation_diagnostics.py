"""Closed aggregate facts only; commit labels do not prove durable outcomes."""

import logging
from collections.abc import Iterable

from studymate.infrastructure.ai.transaction_diagnostics import (
    AiTransactionDiagnostic,
    TransactionPhase,
)


def failure_counts(records: Iterable[logging.LogRecord]) -> dict[str, int]:
    counts = {f"burst_failure_{phase.value}": 0 for phase in TransactionPhase}
    counts["burst_failure_deadline"] = 0
    for record in records:
        diagnostic = record.__dict__.get("ai_transaction_diagnostic")
        if isinstance(diagnostic, AiTransactionDiagnostic):
            counts[f"burst_failure_{diagnostic.phase.value}"] += 1
            counts["burst_failure_deadline"] += int(diagnostic.deadline_expired)
    return counts


def stored_counts(states: Iterable[str], accepted: int) -> dict[str, int]:
    counts = {
        "post_burst_stored": 0,
        "post_burst_expected_stored": accepted + 3,
        "post_burst_expected_queued": accepted + 1,
    }
    known = ("queued", "running", "succeeded", "failed", "cancelled", "expired")
    counts.update((f"post_burst_{state}", 0) for state in (*known, "other"))
    for state in states:
        counts["post_burst_stored"] += 1
        counts[f"post_burst_{state if state in known else 'other'}"] += 1
    return counts
