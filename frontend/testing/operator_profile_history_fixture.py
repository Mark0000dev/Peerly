"""Finite retained profile history cohorts; current pointers/live clocks stay intact."""

from collections.abc import Mapping
from datetime import timedelta
from uuid import UUID

from operator_retained_fixture import SOURCE_TIME
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from studymate.infrastructure.persistence.profile_models import (
    ProfileLanguageRecord,
    ProfileRevisionRecord,
)

PROFILE_HISTORY_LAST_VERSION = 53


async def seed_profile_history_records(
    engine: AsyncEngine, namespace: str, targets: Mapping[str, str]
) -> None:
    if namespace.split("/")[1] == "history-empty":
        # The actual viewer/nullable owner has no profile/revision. Existing retained
        # targets still keep their base revision, as in every accepted cohort.
        return
    async with async_sessionmaker(engine).begin() as session:
        for index, state in enumerate(("active", "hidden", "banned", "deleted")):
            owner = UUID(targets[state + "_id"])
            for version in range(2, PROFILE_HISTORY_LAST_VERSION + 1):
                session.add(
                    ProfileRevisionRecord(
                        account_id=owner,
                        version=version,
                        display_name=None
                        if version % 3 == 0
                        else f"Retained {state} revision {version}",
                        about=None
                        if version % 2 == 0
                        else f"Literal <b>revision {version}</b>\nOriginal spacing",
                        programme="Stored programme label",
                        year_label=None if version % 2 == 0 else "Stored year label",
                        task="offer_help" if version % 2 else "find_help",
                        saved_at=SOURCE_TIME + timedelta(days=index, minutes=version),
                    )
                )
        await session.flush()
        for state in ("active", "hidden", "banned", "deleted"):
            owner = UUID(targets[state + "_id"])
            for version in range(2, PROFILE_HISTORY_LAST_VERSION + 1):
                if version % 3 != 0:
                    for slot, code in enumerate(("zh", "en")):
                        session.add(
                            ProfileLanguageRecord(
                                account_id=owner,
                                version=version,
                                slot=slot,
                                code=code,
                            )
                        )
        # No ProfileRecord update: original current_version=1 intentionally remains.
        # The operator endpoint must inspect retained revisions beyond that pointer.
