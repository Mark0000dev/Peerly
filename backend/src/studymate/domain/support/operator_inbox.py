"""Metadata-only operator inbox and retained actual support status revisions."""

from dataclasses import dataclass
from uuid import UUID

from studymate.domain.support.cases import SupportReceipt, SupportTopic

OPERATOR_SUPPORT_PAGE_SIZE = 50


@dataclass(frozen=True, slots=True)
class OperatorSupportSummary:
    receipt: SupportReceipt
    topic: SupportTopic
    actor_id: UUID | None


@dataclass(frozen=True, slots=True)
class OperatorSupportRevision:
    receipt: SupportReceipt
    changed_by_id: UUID | None
    operator_access_version: int | None

    def __post_init__(self) -> None:
        if self.receipt.version == 1:
            if self.changed_by_id is not None or self.operator_access_version is not None:
                raise ValueError("Initial support receipt cannot invent an operator source")
        elif (
            self.changed_by_id is None
            or self.operator_access_version is None
            or isinstance(self.operator_access_version, bool)
            or self.operator_access_version < 1
        ):
            raise ValueError("Support history requires the actual operator and grant revision")
