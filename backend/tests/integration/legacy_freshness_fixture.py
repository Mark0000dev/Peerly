"""Copy synthetic legacy-compatible facts into an actual isolated revision18 schema."""

from uuid import uuid4

from sqlalchemy import MetaData, column, func, inspect, select, text
from sqlalchemy import table as core_table
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection
from sqlalchemy.schema import CreateSchema

from studymate.infrastructure.persistence.schema import metadata
from tests.integration.migrations import migrate


def prepare_legacy_freshness(connection: Connection) -> int:
    """Caller rolls back its savepoint, including schema and local search_path.

    Current canonical rows are never deleted or changed. Only families that
    existed at18 enter this separate historical fixture; newer tables/columns
    are absent because the real migration chain constructs the target schema.
    """
    source = connection.scalar(select(func.current_schema()))
    assert isinstance(source, str)
    target = f"legacy_freshness_{uuid4().hex}"
    quote = connection.dialect.identifier_preparer.quote
    connection.execute(CreateSchema(target))
    connection.execute(select(func.set_config("search_path", quote(target), True)))
    migrate(connection, "0018_ai_product_events")
    connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    inspector = inspect(connection)
    tables = frozenset(inspector.get_table_names(schema=target))
    for table in metadata.sorted_tables:
        if table.name not in tables:
            continue
        names = tuple(item["name"] for item in inspector.get_columns(table.name, schema=target))
        source_table = table.to_metadata(MetaData(), schema=source)
        target_table = core_table(table.name, *(column(name) for name in names), schema=target)
        source_rows = select(*(source_table.c[name] for name in names))
        if table.name == "product_events":
            source_rows = source_rows.where(
                source_table.c.kind.in_(
                    (
                        "auth.email_confirmed",
                        "profile.ready",
                        "goal.saved",
                        "goal.completed",
                        "profile.hidden",
                        "profile.restored",
                        "ai_job.completed",
                    )
                )
            )
        connection.execute(
            insert(target_table).from_select(names, source_rows).on_conflict_do_nothing()
        )
    connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    count = connection.scalar(text("SELECT count(*) FROM product_events"))
    assert isinstance(count, int)
    return count
