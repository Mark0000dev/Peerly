"""Explicit product model registry for migrations and schema drift checks."""

from studymate.infrastructure.ai.models import AI_MODELS
from studymate.infrastructure.bootstrap_data.models import BOOTSTRAP_DATA_MODELS
from studymate.infrastructure.changes.models import (
    ChangeHeadRecord,
    ChangeOutboxRecord,
    PublishedChangeRecord,
)
from studymate.infrastructure.chat_images.cleanup_models import ChatImageTransportCleanupRecord
from studymate.infrastructure.chat_images.models import CHAT_IMAGE_MODELS
from studymate.infrastructure.chat_images.origins import ChatImageQueueOriginRecord
from studymate.infrastructure.client_observations.models import (
    ClientObservationRecord,
    ObservationBatchRecord,
    ObservationFrameRecord,
)
from studymate.infrastructure.external_delivery.models import (
    DeliveryAttemptRecord,
    DeliveryDestinationRecord,
    DeliveryScheduleRecord,
    DeliverySourceRecord,
    ExternalDeliveryRecord,
)
from studymate.infrastructure.feedback.models import (
    FeedbackCommandIntentRecord,
    PeerFeedbackRecord,
    PeerFeedbackRemovalRecord,
    PeerFeedbackRevisionRecord,
    StudyOutcomeRecord,
    StudyOutcomeRevisionRecord,
    StudyPromptReceiptRecord,
)
from studymate.infrastructure.lifecycle.models import LIFECYCLE_MODELS
from studymate.infrastructure.lifecycle.workflow_models import AccountDeletionWorkflowRecord
from studymate.infrastructure.messaging.goal_share_models import (
    ConversationGoalShareHeadRecord,
    ConversationGoalShareIntentRecord,
    ConversationGoalShareRecord,
)
from studymate.infrastructure.notification_preferences.models import (
    PreferenceIntentRecord,
    PreferenceRevisionRecord,
)
from studymate.infrastructure.operator.membership_verification_models import (
    OperatorMembershipIntentRecord,
    OperatorMembershipVerificationRecord,
)
from studymate.infrastructure.operator.models import (
    OperatorAccessRecord,
    OperatorAccessRevisionRecord,
    OperatorAuditRecord,
)
from studymate.infrastructure.persistence.base import Base
from studymate.infrastructure.persistence.block_models import (
    BlockIntentRecord,
    BlockRecord,
    BlockRevisionRecord,
    RelationshipRecord,
)
from studymate.infrastructure.persistence.callback_models import CallbackAttemptRecord
from studymate.infrastructure.persistence.catalogue_models import SubjectAliasRecord, SubjectRecord
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.discovery_freshness_models import (
    DiscoveryExposureRecord,
    DiscoveryFreshnessPolicyRecord,
)
from studymate.infrastructure.persistence.discovery_pass_models import (
    DiscoveryContextRecord,
    DiscoveryDecisionHeadRecord,
    PrivatePassIntentRecord,
    PrivatePassRecord,
    PrivatePassRevisionRecord,
)
from studymate.infrastructure.persistence.email_models import (
    EmailChallengeRecord,
    EmailDeliveryRecord,
    EmailIntentRecord,
)
from studymate.infrastructure.persistence.goal_models import (
    GoalIntentRecord,
    GoalRecord,
    GoalRevisionRecord,
)
from studymate.infrastructure.persistence.help_models import (
    HelpIntentRecord,
    HelpRecord,
    HelpRevisionRecord,
    HelpSelectionRecord,
)
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    InstitutionalBindingRecord,
    LoginFlowRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.media_models import (
    MediaIntentRecord,
    PhotoRecord,
    PhotoRevisionRecord,
    PhotoUploadRecord,
    PhotoUploadRevisionRecord,
)
from studymate.infrastructure.persistence.media_origin_models import MediaOriginRecord
from studymate.infrastructure.persistence.message_models import (
    MessageCommandIntentRecord,
    MessageOperationRecord,
    MessageRecord,
)
from studymate.infrastructure.persistence.message_read_models import (
    ConversationReadIntentRecord,
    ConversationReadPositionRecord,
    ConversationReadRevisionRecord,
)
from studymate.infrastructure.persistence.message_report_models import MessageReportContextRecord
from studymate.infrastructure.persistence.onboarding_models import (
    ProfileActivationRecord,
    VisibilityIntentRecord,
    VisibilityRevisionRecord,
)
from studymate.infrastructure.persistence.photo_attempt_models import PhotoAttemptRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.profile_models import (
    ProfileIntentRecord,
    ProfileLanguageRecord,
    ProfileRecord,
    ProfileRevisionRecord,
)
from studymate.infrastructure.persistence.registration_models import (
    PolicyDocumentRecord,
    RegistrationContextRecord,
    RegistrationReceiptRecord,
)
from studymate.infrastructure.persistence.report_models import (
    ProfileAccessRecord,
    ProfileReportIntentRecord,
    ProfileReportRecord,
)
from studymate.infrastructure.persistence.transport_cleanup_models import TransportCleanupRecord
from studymate.infrastructure.requests.models import REQUEST_MODELS
from studymate.infrastructure.requests.view_models import (
    RequestDisclosureRecord,
    RequestViewAcknowledgementRecord,
)
from studymate.infrastructure.support.models import (
    SupportCaseRecord,
    SupportIntentRecord,
    SupportOperatorIntentRecord,
    SupportPreparationRecord,
    SupportProofRecord,
    SupportRevisionRecord,
)

MODELS: tuple[type[Base], ...] = (
    ObservationBatchRecord,
    ClientObservationRecord,
    ObservationFrameRecord,
    DeliveryDestinationRecord,
    DeliverySourceRecord,
    ExternalDeliveryRecord,
    DeliveryAttemptRecord,
    DeliveryScheduleRecord,
    *CHAT_IMAGE_MODELS,
    ChatImageTransportCleanupRecord,
    *LIFECYCLE_MODELS,
    AccountDeletionWorkflowRecord,
    ChatImageQueueOriginRecord,
    StudyOutcomeRecord,
    StudyOutcomeRevisionRecord,
    PeerFeedbackRecord,
    PeerFeedbackRevisionRecord,
    PeerFeedbackRemovalRecord,
    StudyPromptReceiptRecord,
    FeedbackCommandIntentRecord,
    ChangeHeadRecord,
    ChangeOutboxRecord,
    PublishedChangeRecord,
    OperatorAccessRecord,
    OperatorAccessRevisionRecord,
    OperatorAuditRecord,
    OperatorMembershipVerificationRecord,
    OperatorMembershipIntentRecord,
    *REQUEST_MODELS,
    RequestDisclosureRecord,
    RequestViewAcknowledgementRecord,
    ConversationRecord,
    MessageOperationRecord,
    MessageRecord,
    MessageCommandIntentRecord,
    ConversationReadRevisionRecord,
    ConversationReadPositionRecord,
    ConversationReadIntentRecord,
    ConversationGoalShareRecord,
    ConversationGoalShareHeadRecord,
    ConversationGoalShareIntentRecord,
    DiscoveryContextRecord,
    DiscoveryDecisionHeadRecord,
    PrivatePassRecord,
    PrivatePassRevisionRecord,
    PrivatePassIntentRecord,
    RelationshipRecord,
    BlockRevisionRecord,
    BlockRecord,
    BlockIntentRecord,
    ProfileAccessRecord,
    ProfileReportRecord,
    ProfileReportIntentRecord,
    MessageReportContextRecord,
    *AI_MODELS,
    *BOOTSTRAP_DATA_MODELS,
    PreferenceIntentRecord,
    PreferenceRevisionRecord,
    SupportCaseRecord,
    SupportIntentRecord,
    SupportOperatorIntentRecord,
    SupportPreparationRecord,
    SupportProofRecord,
    SupportRevisionRecord,
    AccountRecord,
    ExternalIdentityRecord,
    SessionRecord,
    InstitutionalBindingRecord,
    LoginFlowRecord,
    CallbackAttemptRecord,
    EmailChallengeRecord,
    EmailIntentRecord,
    EmailDeliveryRecord,
    PolicyDocumentRecord,
    RegistrationContextRecord,
    RegistrationReceiptRecord,
    ProfileRecord,
    ProfileRevisionRecord,
    ProfileLanguageRecord,
    ProfileIntentRecord,
    SubjectRecord,
    SubjectAliasRecord,
    GoalRecord,
    GoalRevisionRecord,
    GoalIntentRecord,
    HelpIntentRecord,
    HelpRecord,
    HelpRevisionRecord,
    HelpSelectionRecord,
    MediaIntentRecord,
    PhotoRecord,
    PhotoRevisionRecord,
    PhotoUploadRecord,
    PhotoUploadRevisionRecord,
    PhotoAttemptRecord,
    TransportCleanupRecord,
    MediaOriginRecord,
    ProductEventRecord,
    DiscoveryExposureRecord,
    DiscoveryFreshnessPolicyRecord,
    ProfileActivationRecord,
    VisibilityRevisionRecord,
    VisibilityIntentRecord,
)
metadata = Base.metadata
