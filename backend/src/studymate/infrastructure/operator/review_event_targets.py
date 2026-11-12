"""Source-backed account relation filtering; never infer actors from current names."""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.sql.elements import ColumnElement

from studymate.infrastructure.operator.photo_review_models import OperatorPhotoReviewRecord
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
            ProductEventRecord.report_review_id.is_not(None),
            ProfileReportRecord.id == ProductEventRecord.report_review_report_id,
            or_(
                ProfileAccessRecord.target_id == account_id,
                MessageReportContextRecord.target_id == account_id,
            ),
        )
        .correlate(ProductEventRecord)
        .exists()
    )
    return or_(photo, report)
