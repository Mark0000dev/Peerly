"""Source-backed account relation filtering; never infer actors from current names."""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.sql.elements import ColumnElement

from studymate.infrastructure.operator.photo_review_models import OperatorPhotoReviewRecord
from studymate.infrastructure.persistence.block_models import RelationshipRecord
from studymate.infrastructure.persistence.message_report_models import MessageReportContextRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.report_models import (
    ProfileAccessRecord,
    ProfileReportRecord,
)


def review_event_targets(account_id: UUID) -> ColumnElement[bool]:
    photo = (
        select(OperatorPhotoReviewRecord.id)
        .where(
            OperatorPhotoReviewRecord.id == ProductEventRecord.photo_review_id,
            OperatorPhotoReviewRecord.account_id == account_id,
        )
        .correlate(ProductEventRecord)
        .exists()
    )
    report = (
        select(ProfileReportRecord.id)
        .outerjoin(ProfileAccessRecord, ProfileAccessRecord.id == ProfileReportRecord.context_id)
        .outerjoin(
            MessageReportContextRecord,
            MessageReportContextRecord.id == ProfileReportRecord.message_context_id,
        )
        .where(
            or_(
                ProductEventRecord.report_review_id.is_not(None),
                ProductEventRecord.triage_job_id.is_not(None),
            ),
            or_(
                ProfileReportRecord.id == ProductEventRecord.report_review_report_id,
                ProfileReportRecord.id == ProductEventRecord.triage_report_id,
            ),
            or_(
                ProfileAccessRecord.target_id == account_id,
                MessageReportContextRecord.target_id == account_id,
            ),
        )
        .correlate(ProductEventRecord)
        .exists()
    )
    return or_(photo, report)


def block_event_targets(account_id: UUID) -> ColumnElement[bool]:
    pairs = select(RelationshipRecord.id).where(
        or_(RelationshipRecord.low_id == account_id, RelationshipRecord.high_id == account_id)
    )
    return ProductEventRecord.block_relationship_id.in_(pairs)
