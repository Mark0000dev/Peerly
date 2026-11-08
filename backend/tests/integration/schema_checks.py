"""Normalize CHECK definitions through PostgreSQL, including same-name expression drift.

https://alembic.sqlalchemy.org/en/latest/autogenerate.html#detecting-check-constraints
Only temporary empty verification tables are created; product tables are untouched.
"""

from uuid import uuid4

from sqlalchemy import CheckConstraint, MetaData, Table, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.schema import AddConstraint


def normalized_model_checks(connection: Connection, table: Table) -> dict[str | None, str]:
    constraints = tuple(item for item in table.constraints if isinstance(item, CheckConstraint))
    if not constraints:
        return {}
    quote = connection.dialect.identifier_preparer.quote
    name = f"verify_checks_{uuid4().hex}"
    expected_table = Table(name, MetaData())
    qualified = f"{quote(table.schema)}.{quote(table.name)}" if table.schema else quote(table.name)
    with connection.begin_nested():
        connection.exec_driver_sql(
            f"CREATE TEMPORARY TABLE {quote(name)} "
            f"(LIKE {qualified} INCLUDING DEFAULTS INCLUDING GENERATED INCLUDING IDENTITY) "
            "ON COMMIT DROP"
        )
        for constraint in constraints:
            assert constraint.name is not None, f"Unnamed CHECK on {table.name}"
            expression = str(
                constraint.sqltext.compile(
                    dialect=connection.dialect,
                    compile_kwargs={"literal_binds": True, "include_table": False},
                )
            )
            expected = CheckConstraint(expression, name=constraint.name)
            expected_table.append_constraint(expected)
            connection.execute(AddConstraint(expected))
        schema = connection.scalar(
            text("SELECT nspname FROM pg_namespace WHERE oid=pg_my_temp_schema()")
        )
        assert isinstance(schema, str)
        normalized = {
            item["name"]: item["sqltext"]
            for item in inspect(connection).get_check_constraints(name, schema=schema)
        }
        connection.exec_driver_sql(f"DROP TABLE {quote(name)}")
        return normalized


def assert_check_constraints_match_metadata(connection: Connection, metadata: MetaData) -> None:
    inspector = inspect(connection)
    for table in metadata.tables.values():
        actual = {
            item["name"]: item["sqltext"]
            for item in inspector.get_check_constraints(table.name, schema=table.schema)
        }
        expected = normalized_model_checks(connection, table)
        assert actual == expected, (
            f"Migrated CHECK expressions differ from {table.name}: "
            f"actual={actual}; expected={expected}"
        )
