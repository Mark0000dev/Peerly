"""Bounded metadata-only roundtrip categories; never persist SQL/parameters/errors."""

from contextvars import ContextVar
from dataclasses import dataclass, field
from time import perf_counter

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

ACTIVE_OPERATION: ContextVar[str | None] = ContextVar("triage_test_operation", default=None)


def category(statement: str) -> str:
    candidates = (
        ("triage_job AS" in statement or "triage_proof AS" in statement, "atomic_write"),
        ("triage_admission_clock" in statement, "admission_capacity"),
        ("retained_identity_lineage" in statement, "lineage"),
        ("AS actor_id" in statement and "FOR NO KEY UPDATE" in statement, "ordered_account_scope"),
        ("FROM sessions" in statement and "FOR NO KEY UPDATE" in statement, "typed_session_facts"),
        ("FROM registration_receipts" in statement, "registration_facts"),
        ("FROM operator_access_revisions" in statement and "FOR UPDATE" in statement, "role_lock"),
        (
            "FROM profile_reports" in statement and "FOR UPDATE" in statement,
            "locked_selected_source",
        ),
        ("FROM ai_executor_slot" in statement and "FOR UPDATE" in statement, "canonical_slot_lock"),
        ("LEFT OUTER JOIN ai_intents" in statement, "intent_observation"),
        (
            "FROM report_triage_submissions" in statement and "clock_timestamp" in statement,
            "current_source_observation",
        ),
        ("FROM report_triage_submissions" in statement, "stored_submission"),
        ("report_triage_evidence_snapshots" in statement, "prepared_source"),
        (statement.startswith("INSERT INTO operator_audits"), "audit_write"),
        (statement.startswith("INSERT INTO product_events"), "canonical_write"),
        ("clock_timestamp" in statement, "fresh_clock"),
    )
    return next((label for matches, label in candidates if matches), "other")


@dataclass(slots=True)
class Measurements:
    started: float = field(default_factory=perf_counter)
    pending: dict[int, tuple[float, str]] = field(default_factory=dict)
    queries: list[dict[str, str | float]] = field(default_factory=list)
    checkout: list[float] = field(default_factory=list)
    held_since: float | None = None
    held: list[float] = field(default_factory=list)

    def install(self, engine: AsyncEngine) -> None:
        event.listen(engine.sync_engine, "before_cursor_execute", self.before)
        event.listen(engine.sync_engine, "after_cursor_execute", self.after)
        event.listen(engine.sync_engine.pool, "checkout", self.checked_out)
        event.listen(engine.sync_engine.pool, "checkin", self.checked_in)

    def close(self, engine: AsyncEngine) -> None:
        event.remove(engine.sync_engine, "before_cursor_execute", self.before)
        event.remove(engine.sync_engine, "after_cursor_execute", self.after)
        event.remove(engine.sync_engine.pool, "checkout", self.checked_out)
        event.remove(engine.sync_engine.pool, "checkin", self.checked_in)

    def before(self, *arguments: object) -> None:
        if ACTIVE_OPERATION.get() is None:
            return
        statement = arguments[2]
        if isinstance(statement, str):
            self.pending[id(arguments[4])] = perf_counter(), category(statement)

    def after(self, *arguments: object) -> None:
        value = self.pending.pop(id(arguments[4]), None)
        if value is not None:
            at, label = value
            self.queries.append({"phase": label, "seconds": perf_counter() - at})

    def checked_out(self, *_arguments: object) -> None:
        if ACTIVE_OPERATION.get() is not None:
            self.checkout.append(perf_counter() - self.started)
            self.held_since = perf_counter()

    def checked_in(self, *_arguments: object) -> None:
        if ACTIVE_OPERATION.get() is not None and self.held_since is not None:
            self.held.append(perf_counter() - self.held_since)
            self.held_since = None

    def reset(self) -> None:
        self.started = perf_counter()
        self.pending.clear()
        self.queries.clear()
        self.checkout.clear()
        self.held.clear()
        self.held_since = None
