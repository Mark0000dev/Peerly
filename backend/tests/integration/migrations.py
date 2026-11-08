from typing import Literal, Protocol, runtime_checkable

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection

from studymate.infrastructure.persistence.schema import metadata


def migrate(connection: Connection, revision: str) -> None:
    configuration = Config("alembic.ini")
    configuration.attributes["connection"] = connection
    if revision == "base":
        command.downgrade(configuration, revision)
    else:
        command.upgrade(configuration, revision)


@runtime_checkable
class RevisionSteps(Protocol):
    def upgrade(self) -> None: ...

    def downgrade(self) -> None: ...


def run_revision_step(
    connection: Connection, revision: str, direction: Literal["upgrade", "downgrade"]
) -> None:
    """Test one actual revision without unrelated newer guards or version-table changes.

    Callers of mutating steps use a rollback savepoint. Full-chain roundtrip and
    retained-delivery protection are tested independently, without bypassing them.
    """
    script = ScriptDirectory.from_config(Config("alembic.ini")).get_revision(revision)
    if not isinstance(script.module, RevisionSteps):
        raise ValueError("A concrete migration with both steps is required")
    context = MigrationContext.configure(connection, opts={"target_metadata": metadata})
    with Operations.context(context):
        if direction == "upgrade":
            script.module.upgrade()
        else:
            script.module.downgrade()
