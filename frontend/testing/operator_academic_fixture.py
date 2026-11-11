"""Retained academic records in NEW operator cohorts; live clocks remain untouched."""

from collections.abc import Mapping
from datetime import timedelta
from uuid import UUID

from operator_retained_fixture import SOURCE_TIME, retained_id
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from studymate.infrastructure.persistence.goal_models import (
    GoalRecord,
    GoalRevisionRecord,
)
from studymate.infrastructure.persistence.help_models import (
    HelpRecord,
    HelpRevisionRecord,
    HelpSelectionRecord,
)

PAGE_BOUNDARY_REVISIONS = 53
COMPLETED_ROOTS = 52


async def seed_academic_records(
    engine: AsyncEngine, namespace: str, targets: Mapping[str, str]
) -> None:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    for index, state in enumerate(("active", "hidden", "banned", "deleted")):
        owner = UUID(targets[state + "_id"])
        at = SOURCE_TIME + timedelta(days=index)
        async with sessions.begin() as session:
            roots = tuple(
                GoalRecord(
                    id=retained_id(namespace, f"{state}/completed-goal/{slot}"),
                    account_id=owner,
                    current_version=2,
                    created_at=at + timedelta(minutes=slot + 1),
                    completed_at=at + timedelta(minutes=slot + 1, seconds=30),
                )
                for slot in range(COMPLETED_ROOTS)
            )
            active = GoalRecord(
                id=retained_id(namespace, state + "/active-goal"),
                account_id=owner,
                current_version=PAGE_BOUNDARY_REVISIONS,
                created_at=at + timedelta(minutes=58),
                completed_at=None,
            )
            session.add_all((*roots, active))
            await session.flush()
            for root in roots:
                for version in (1, 2):
                    saved = root.created_at + timedelta(seconds=30 * (version - 1))
                    session.add(
                        GoalRevisionRecord(
                            goal_id=root.id,
                            version=version,
                            account_id=owner,
                            subject_id=None,
                            subject_label="Retained custom subject",
                            topic="Saved topic",
                            topic_match_key="saved-topic",
                            context="Saved literal <b>context</b>, not HTML.",
                            shared_learning=False,
                            saved_at=saved,
                            completed_at=saved if version == 2 else None,
                        )
                    )
            for version in range(1, PAGE_BOUNDARY_REVISIONS + 1):
                session.add(
                    GoalRevisionRecord(
                        goal_id=active.id,
                        version=version,
                        account_id=owner,
                        subject_id=UUID(int=31),
                        subject_label="Stored SQL before catalogue rename",
                        topic=f"Stored JOINs revision {version}",
                        topic_match_key=f"retained-joins-{version}",
                        context=f"Saved literal <b>revision {version}</b>\nOriginal spacing",
                        shared_learning=True,
                        saved_at=active.created_at + timedelta(seconds=version),
                        completed_at=None,
                    )
                )
            # Revision1 already exists in the historical base. Latest53 is an explicit
            # saved clear; preceding revisions preserve nonalphabetical stored slots.
            for version in range(2, PAGE_BOUNDARY_REVISIONS + 1):
                session.add(
                    HelpRevisionRecord(
                        account_id=owner,
                        version=version,
                        saved_at=at + timedelta(minutes=version),
                    )
                )
            await session.flush()
            for version in range(2, PAGE_BOUNDARY_REVISIONS):
                for slot, subject, label, topic in (
                    (0, 31, "Stored SQL before catalogue rename", "JOINs"),
                    (1, 30, "Stored Calculus", None),
                ):
                    session.add(
                        HelpSelectionRecord(
                            account_id=owner,
                            version=version,
                            slot=slot,
                            subject_id=UUID(int=subject),
                            subject_label=label,
                            topic_note=topic,
                            topic_match_key="retained-joins"
                            if topic is not None
                            else None,
                        )
                    )
            current = await session.get(HelpRecord, owner)
            if current is None:
                raise RuntimeError("Retained help pointer missing")
            current.current_version = PAGE_BOUNDARY_REVISIONS
