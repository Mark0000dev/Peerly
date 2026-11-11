"""Exact bounded topic ordering uses the same Unicode keys as the domain."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_discovery_topic_keys"
down_revision: str | Sequence[str] | None = "0028_request_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BATCH_SIZE = 250


def _backfill_goals() -> None:
    goal_id = sa.column("goal_id", sa.Uuid())
    version = sa.column("version", sa.Integer())
    topic = sa.column("topic", sa.String(80))
    key = sa.column("topic_match_key", sa.String(240))
    table = sa.table("goal_revisions", goal_id, version, topic, key)
    statement = (
        sa.select(goal_id, version, topic)
        .where(topic.is_not(None), key.is_(None))
        .limit(BATCH_SIZE)
    )
    connection = op.get_bind()
    while rows := connection.execute(statement).all():
        for source_id, source_version, value in rows:
            connection.execute(
                table.update()
                .where(goal_id == source_id, version == source_version)
                .values(topic_match_key=" ".join(value.casefold().split()))
            )


def _backfill_help() -> None:
    account_id = sa.column("account_id", sa.Uuid())
    version = sa.column("version", sa.Integer())
    slot = sa.column("slot", sa.Integer())
    topic = sa.column("topic_note", sa.String(80))
    key = sa.column("topic_match_key", sa.String(240))
    table = sa.table("help_selections", account_id, version, slot, topic, key)
    statement = (
        sa.select(account_id, version, slot, topic)
        .where(topic.is_not(None), key.is_(None))
        .limit(BATCH_SIZE)
    )
    connection = op.get_bind()
    while rows := connection.execute(statement).all():
        for owner, source_version, source_slot, value in rows:
            connection.execute(
                table.update()
                .where(account_id == owner, version == source_version, slot == source_slot)
                .values(topic_match_key=" ".join(value.casefold().split()))
            )


def upgrade() -> None:
    op.add_column("goal_revisions", sa.Column("topic_match_key", sa.String(240), nullable=True))
    op.add_column("help_selections", sa.Column("topic_match_key", sa.String(240), nullable=True))
    _backfill_goals()
    _backfill_help()
    op.create_check_constraint(
        op.f("ck_goal_revisions_topic_key_shape"),
        "goal_revisions",
        "(topic IS NULL AND topic_match_key IS NULL) OR "
        "(topic IS NOT NULL AND topic_match_key IS NOT NULL AND length(topic_match_key) > 0)",
    )
    op.create_check_constraint(
        op.f("ck_help_selections_topic_key_shape"),
        "help_selections",
        "(topic_note IS NULL AND topic_match_key IS NULL) OR "
        "(topic_note IS NOT NULL AND topic_match_key IS NOT NULL AND length(topic_match_key) > 0)",
    )
    op.create_index(
        "ix_goal_revisions_subject_topic",
        "goal_revisions",
        ["subject_id", "topic_match_key", "goal_id", "version"],
    )
    op.create_index(
        "ix_help_selections_subject_topic",
        "help_selections",
        ["subject_id", "topic_match_key", "account_id", "version"],
    )


def downgrade() -> None:
    op.drop_index("ix_help_selections_subject_topic", table_name="help_selections")
    op.drop_index("ix_goal_revisions_subject_topic", table_name="goal_revisions")
    op.drop_constraint(op.f("ck_help_selections_topic_key_shape"), "help_selections", type_="check")
    op.drop_constraint(op.f("ck_goal_revisions_topic_key_shape"), "goal_revisions", type_="check")
    # Only reproducible derived keys are dropped; all source text/history stays.
    op.drop_column("help_selections", "topic_match_key")
    op.drop_column("goal_revisions", "topic_match_key")
