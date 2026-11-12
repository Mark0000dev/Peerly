"""Actual latest human requirement, never inferred from missing review/history."""

from uuid import UUID

from sqlalchemy import SQLColumnExpression, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from studymate.infrastructure.operator.photo_review_models import OperatorPhotoReviewRecord


def photo_replacement_required(account_id: UUID | SQLColumnExpression[UUID]) -> ColumnElement[bool]:
    latest = (
        select(OperatorPhotoReviewRecord.action)
        .where(OperatorPhotoReviewRecord.account_id == account_id)
        .order_by(OperatorPhotoReviewRecord.version.desc())
        .limit(1)
        .scalar_subquery()
    )
    return func.coalesce(latest == "require_replacement", False)


async def read_photo_replacement_accounts(
    session: AsyncSession, account_ids: tuple[UUID, ...]
) -> frozenset[UUID]:
    if not account_ids:
        return frozenset()
    latest = (
        select(OperatorPhotoReviewRecord.account_id, OperatorPhotoReviewRecord.action)
        .where(OperatorPhotoReviewRecord.account_id.in_(account_ids))
        .distinct(OperatorPhotoReviewRecord.account_id)
        .order_by(OperatorPhotoReviewRecord.account_id, OperatorPhotoReviewRecord.version.desc())
        .subquery()
    )
    return frozenset(
        await session.scalars(
            select(latest.c.account_id).where(latest.c.action == "require_replacement")
        )
    )
