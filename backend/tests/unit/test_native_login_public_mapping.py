"""The native adapter and notification schema must share one retained-lineage mapping."""

from studymate.infrastructure.persistence.base import Base
from studymate.infrastructure.persistence.native_login import NativeAttemptRecord
from studymate.infrastructure.persistence.native_login_models import (
    NativeAttemptRecord as SchemaNativeAttemptRecord,
)


def test_native_adapter_reexports_the_single_schema_mapping() -> None:
    assert NativeAttemptRecord is SchemaNativeAttemptRecord
    assert Base.metadata.tables["native_login_attempts"] is NativeAttemptRecord.__table__
    assert tuple(name for name in Base.metadata.tables if name == "native_login_attempts") == (
        "native_login_attempts",
    )


def test_native_source_session_retains_restrict_foreign_key() -> None:
    column = NativeAttemptRecord.__table__.c.source_digest
    assert column.nullable
    assert len(column.foreign_keys) == 1
    reference = next(iter(column.foreign_keys))
    assert reference.target_fullname == "sessions.secret_digest"
    assert reference.ondelete == "RESTRICT"
