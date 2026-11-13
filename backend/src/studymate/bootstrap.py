import asyncio
import ssl
from collections.abc import AsyncIterator, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import httpx2 as httpx
from aiobotocore.config import AioConfig
from aiobotocore.session import AioSession
from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from studymate.application.ai.policy import AdmissionPolicy
from studymate.application.ai.student import CancelStudentJob, ReadStudentJob, SubmitStudentJob
from studymate.application.catalogue import SearchSubjects
from studymate.application.changes.publication import PublishChanges
from studymate.application.changes.reads import ReadChanges
from studymate.application.changes.retention import PruneChanges
from studymate.application.chat_images.access import CreateChatImageUploadAccess
from studymate.application.chat_images.display import ReadMessageImageDisplay, ReadOwnedImageDisplay
from studymate.application.chat_images.finalize import FinalizeChatImage
from studymate.application.chat_images.reads import (
    ListOwnImagePreparations,
    ReadOwnedImagePreparation,
)
from studymate.application.chat_images.start import StartChatImage
from studymate.application.chat_images.worker import ProcessNextChatImage
from studymate.application.check_readiness import CheckReadiness
from studymate.application.client_observations.intake import AcceptClientObservations
from studymate.application.discovery.deck import ReadDiscoveryDeck
from studymate.application.discovery.passes import ChangePrivatePass
from studymate.application.discovery.photos import ReadDiscoveryPhoto
from studymate.application.discovery.profiles import ReadDiscoveryProfile
from studymate.application.errors import StorageUnavailableError
from studymate.application.external_delivery.inspection import (
    ReadDeliverySource,
    SearchDeliverySources,
)
from studymate.application.external_delivery.routing import MaterializeDeliverySources
from studymate.application.external_delivery.worker import DeliverNextExternalEvent
from studymate.application.feedback.assessments import SaveFeedback
from studymate.application.feedback.outcomes import SaveStudyOutcome
from studymate.application.feedback.prompts import OfferStudyPromptOnVisit
from studymate.application.feedback.reads import ReadOwnFeedbackContext, ReadOwnStudyOutcome
from studymate.application.feedback.summaries import (
    ReadOwnFeedbackSummary,
    ReadPublicFeedbackSummary,
)
from studymate.application.idempotency import IntentFingerprinter
from studymate.application.identity.bootstrap import ReadBootstrap
from studymate.application.identity.email_delivery import DeliverVerificationEmail
from studymate.application.identity.email_verification import (
    EmailPolicy,
    ReadEmailChallenge,
    StartEmailChallenge,
    VerifyStudentEmail,
)
from studymate.application.identity.login import (
    BeginGoogleLogin,
    CompleteGoogleLogin,
    HandleGoogleCallback,
)
from studymate.application.identity.native_login import (
    BeginNativeLogin,
    BindNativeCallback,
    CancelNativeAttempt,
    CompleteLoginForClient,
    ExchangeNativeAttempt,
    IdentifyNativeCallback,
    RegisterNativeAttempt,
)
from studymate.application.identity.registration import (
    BeginRegistration,
    CompleteRegistration,
    ReadPolicyStatus,
    ReadPublishedPolicy,
)
from studymate.application.identity.sessions import Logout, ReadIdentity
from studymate.application.lifecycle.bans import ChangeAccountBan
from studymate.application.lifecycle.deletions import DeleteOwnAccount
from studymate.application.lifecycle.recovery import PrepareOwnDeletion, ReadOwnDeletionStatus
from studymate.application.media.access import CreatePhotoUploadAccess, ReadOwnPhotoDisplay
from studymate.application.media.cleanup import CleanupMediaTransport
from studymate.application.media.resume import ReadOwnPhotoResume
from studymate.application.media.storage import MediaReader, MediaStorage
from studymate.application.media.uploads import (
    ChangePhotoUpload,
    ReadOwnPhotoUpload,
    StartPhotoUpload,
)
from studymate.application.media.worker import ProcessNextPhoto
from studymate.application.messaging.commands import CancelMessage, ReadMessageOutcome, SendMessage
from studymate.application.messaging.conversation_details import ReadConversationDetails
from studymate.application.messaging.conversation_list import ListConversations
from studymate.application.messaging.goal_shares import ReadGoalShares, ShareCurrentGoal
from studymate.application.messaging.history import ReadMessageHistory
from studymate.application.messaging.participants import ReadChatAvatar, ReadChatParticipant
from studymate.application.messaging.read_positions import AcknowledgeConversationRead
from studymate.application.notification_preferences.preferences import (
    ChooseOwnNotificationPreference,
    ReadOwnNotificationPreference,
)
from studymate.application.operator.access_history import ReadOperatorAccessHistory
from studymate.application.operator.accounts import ReadOperatorAccount, SearchOperatorAccounts
from studymate.application.operator.ai_jobs import ReadOperatorAiJob, ReadOperatorAiJobs
from studymate.application.operator.audit_search import SearchOperatorAudits
from studymate.application.operator.block_history import ReadOperatorBlockHistory
from studymate.application.operator.chat_image_uploads import (
    ReadOperatorChatImageHistory,
    ReadOperatorChatImageUploads,
)
from studymate.application.operator.chat_media import ReadOperatorChatMedia
from studymate.application.operator.connection_requests import (
    ReadOperatorRequestHistory,
    ReadOperatorRequests,
)
from studymate.application.operator.conversation_index import ReadOperatorConversations
from studymate.application.operator.email_history import ReadOperatorEmailHistory
from studymate.application.operator.goals import ReadOperatorGoalHistory, ReadOperatorGoals
from studymate.application.operator.help_history import ReadOperatorHelpHistory
from studymate.application.operator.identity_links import ReadOperatorIdentityLinks
from studymate.application.operator.lifecycle_history import ReadOperatorLifecycleHistory
from studymate.application.operator.media_read import ReadOperatorProfileMedia
from studymate.application.operator.membership_verification import (
    ManuallyVerifyMembership,
    ReadManualMembershipContext,
)
from studymate.application.operator.message_operations import (
    ReadOperatorMessageOperation,
    ReadOperatorMessageOperations,
)
from studymate.application.operator.messages import ReadOperatorConversationMessages
from studymate.application.operator.peer_feedback import (
    ReadOperatorFeedback,
    ReadOperatorFeedbackHistory,
    ReadOperatorFeedbackRemovals,
)
from studymate.application.operator.photo_review import ReadPhotoReviewContext, ReviewPhoto
from studymate.application.operator.photo_uploads import (
    ReadOperatorPhotoHistory,
    ReadOperatorPhotoUploads,
)
from studymate.application.operator.preference_history import ReadOperatorPreferenceHistory
from studymate.application.operator.profile_history import ReadOperatorProfileHistory
from studymate.application.operator.profile_reports import (
    ReadOperatorProfileReport,
    SearchOperatorProfileReports,
)
from studymate.application.operator.report_triage import (
    EnqueueReportTriage,
    ReadReportTriage,
    ReadReportTriageContext,
)
from studymate.application.operator.request_disclosures import ReadOperatorRequestDisclosures
from studymate.application.operator.session_history import ReadOperatorSessionHistory
from studymate.application.operator.timeline import (
    ReadOperatorAudit,
    ReadOperatorEvent,
    SearchOperatorEvents,
)
from studymate.application.operator.visibility_history import ReadOperatorVisibilityHistory
from studymate.application.policy_history.read import ReadPolicyHistory
from studymate.application.profiles.basics import ReadOwnProfile, SaveOwnProfile
from studymate.application.profiles.goals import CompleteOwnGoal, ReadOwnGoal, SaveOwnGoal
from studymate.application.profiles.help_subjects import ReadOwnHelpSubjects, SaveOwnHelpSubjects
from studymate.application.profiles.onboarding import ReadOnboardingStatus
from studymate.application.profiles.photo_review import ReadOwnPhotoReview
from studymate.application.profiles.reference_data import ReadProfileReferenceData
from studymate.application.profiles.visibility import ChangeOwnVisibility
from studymate.application.report_moderation.history import ReadReportReviewHistory
from studymate.application.report_moderation.review import ReviewReport
from studymate.application.requests.actions import (
    AcceptRequest,
    DeclineRequest,
    UndoDecline,
    WithdrawRequest,
)
from studymate.application.requests.expiry import ExpireRequests
from studymate.application.requests.queries import ListRequests, ReadRequest
from studymate.application.requests.send import PreviewRequest, SendRequest
from studymate.application.requests.viewing import AcknowledgeRequestViewed
from studymate.application.safety.block_list import ReadOwnBlocks
from studymate.application.safety.blocks import ChangeOwnBlock
from studymate.application.safety.message_reports import (
    IssueMessageImageReportContext,
    SubmitMessageImageReport,
)
from studymate.application.safety.profile_reports import SubmitProfileReport
from studymate.application.support.cases import (
    CreateSupportCase,
    PrepareSupport,
    ReadActorSupportCase,
    ReadRecentActorSupportCases,
    ReadRecentSupportCases,
    ReadSupportCase,
)
from studymate.application.support.operator import (
    ChangeOperatorSupportStatus,
    ReadOperatorSupportCase,
)
from studymate.application.support.operator_inbox import (
    ReadOperatorSupportHistory,
    SearchOperatorSupportCases,
)
from studymate.config import (
    AiHttpConfiguration,
    AiWorkerSettings,
    AuthenticationConfiguration,
    ChangesWorkerSettings,
    EmailWorkerSettings,
    ExternalDeliveryWorkerSettings,
    MediaConfiguration,
    MediaWorkerSettings,
    ObservabilityConfiguration,
    RequestsWorkerSettings,
    Settings,
)
from studymate.domain.external_delivery.delivery import DestinationRef
from studymate.domain.external_delivery.sources import Sink
from studymate.infrastructure.ai.persistence import SqlAiUnitOfWork
from studymate.infrastructure.changes.loop import ChangeMaintenance, run_change_loop
from studymate.infrastructure.changes.publication import SqlChangePublicationUnitOfWork
from studymate.infrastructure.changes.reads import SqlChangeReadUnitOfWork
from studymate.infrastructure.changes.retention import SqlChangeRetentionUnitOfWork
from studymate.infrastructure.chat_images.cleanup import SqlImageCleanupUnitOfWork
from studymate.infrastructure.chat_images.display import SqlImageDisplayUnitOfWork
from studymate.infrastructure.chat_images.finalize import SqlChatImageFinalizeUnitOfWork
from studymate.infrastructure.chat_images.reads import SqlImageReadUnitOfWork
from studymate.infrastructure.chat_images.start import SqlChatImageStartUnitOfWork
from studymate.infrastructure.chat_images.worker import SqlChatImageWorkerUnitOfWork
from studymate.infrastructure.client_observations.assets import (
    ApprovedPublicAssets,
    PublicReleaseAssets,
)
from studymate.infrastructure.client_observations.persistence import SqlObservationIntakeUnitOfWork
from studymate.infrastructure.email.smtp import SmtpConfiguration, SmtpEmailSender
from studymate.infrastructure.external_delivery.cursors import FernetSourceCursorCodec
from studymate.infrastructure.external_delivery.destinations import (
    DestinationRegistration,
    register_destinations,
)
from studymate.infrastructure.external_delivery.http_adapters import (
    ExternalHttpSender,
    TelegramConfig,
    UmamiConfig,
    target_fingerprint,
)
from studymate.infrastructure.external_delivery.http_adapters.configuration import DestinationConfig
from studymate.infrastructure.external_delivery.inspection import SqlSourceInspectionUnitOfWork
from studymate.infrastructure.external_delivery.materialization import SqlMaterializationUnitOfWork
from studymate.infrastructure.external_delivery.queue import SqlExternalDeliveryQueue
from studymate.infrastructure.external_delivery.runtime import ExternalDeliveryWorker
from studymate.infrastructure.feedback.summary_transactions import SqlFeedbackSummaryUnitOfWork
from studymate.infrastructure.feedback.transactions import FeedbackRecorders, SqlFeedbackUnitOfWork
from studymate.infrastructure.identity.google import GoogleConfiguration, GoogleOidcProvider
from studymate.infrastructure.lifecycle.ban_transactions import SqlBanUnitOfWork
from studymate.infrastructure.lifecycle.deletion_transactions import SqlDeletionUnitOfWork
from studymate.infrastructure.lifecycle.effects import apply_lifecycle_effects
from studymate.infrastructure.lifecycle.status_proofs import HmacDeletionStatusProofs
from studymate.infrastructure.lifecycle.workflows import (
    SqlDeletionStatusUnitOfWork,
    SqlPrepareDeletionUnitOfWork,
    authorize_deletion_workflow,
)
from studymate.infrastructure.media.images import BoundedImageProcessor
from studymate.infrastructure.media.runtime import MediaStorageHandle
from studymate.infrastructure.media.s3 import S3MediaStorage
from studymate.infrastructure.messaging.cursors import FernetMessageHistoryCursorCodec
from studymate.infrastructure.messaging.goal_share_cursors import FernetGoalShareCursorCodec
from studymate.infrastructure.messaging.goal_shares import SqlGoalShareUnitOfWork
from studymate.infrastructure.messaging.history import SqlMessageHistoryUnitOfWork
from studymate.infrastructure.notification_preferences.persistence import SqlPreferenceUnitOfWork
from studymate.infrastructure.observability.changes import ObservedChangeStep
from studymate.infrastructure.observability.database import DatabasePool, DatabaseTelemetry
from studymate.infrastructure.observability.delivery_queue import (
    DeliveryQueueSignals,
    SqlDeliveryQueueReader,
)
from studymate.infrastructure.observability.email import ObservedVerificationDelivery
from studymate.infrastructure.observability.external_delivery import ExternalDeliverySignals
from studymate.infrastructure.observability.http import JsonHttpObserver
from studymate.infrastructure.observability.logging import bind_log_release
from studymate.infrastructure.observability.media import ObservedMediaStep
from studymate.infrastructure.observability.requests import ObservedRequestExpiry
from studymate.infrastructure.observability.runtime import (
    TelemetryConfiguration,
    TelemetryRuntime,
    build_telemetry,
)
from studymate.infrastructure.observability.streams import StreamSignals
from studymate.infrastructure.observability.tracing import OtelHttpTracing
from studymate.infrastructure.operator.access_history_cursors import (
    FernetOperatorAccessHistoryCursorCodec,
)
from studymate.infrastructure.operator.access_history_transactions import (
    SqlOperatorAccessHistoryUnitOfWork,
)
from studymate.infrastructure.operator.ai_cursors import FernetOperatorAiCursorCodec
from studymate.infrastructure.operator.ai_transactions import SqlOperatorAiUnitOfWork
from studymate.infrastructure.operator.audit_search_cursors import FernetOperatorAuditCursorCodec
from studymate.infrastructure.operator.audit_search_transactions import (
    SqlOperatorAuditSearchUnitOfWork,
)
from studymate.infrastructure.operator.block_history_cursors import (
    FernetOperatorBlockHistoryCursorCodec,
)
from studymate.infrastructure.operator.block_history_transactions import (
    SqlOperatorBlockHistoryUnitOfWork,
)
from studymate.infrastructure.operator.chat_image_cursors import FernetOperatorChatImageCursorCodec
from studymate.infrastructure.operator.chat_image_transactions import SqlOperatorChatImageUnitOfWork
from studymate.infrastructure.operator.chat_media_transactions import SqlOperatorChatMediaUnitOfWork
from studymate.infrastructure.operator.conversation_index_cursors import (
    FernetOperatorConversationCursorCodec,
)
from studymate.infrastructure.operator.conversation_index_transactions import (
    SqlOperatorConversationIndexUnitOfWork,
)
from studymate.infrastructure.operator.cursors import FernetOperatorCursorCodec
from studymate.infrastructure.operator.disclosure_cursors import FernetOperatorDisclosureCursorCodec
from studymate.infrastructure.operator.disclosure_transactions import (
    SqlOperatorDisclosureUnitOfWork,
)
from studymate.infrastructure.operator.email_history_cursors import (
    FernetOperatorEmailHistoryCursorCodec,
)
from studymate.infrastructure.operator.email_history_transactions import (
    SqlOperatorEmailHistoryUnitOfWork,
)
from studymate.infrastructure.operator.feedback_cursors import FernetOperatorFeedbackCursorCodec
from studymate.infrastructure.operator.feedback_transactions import SqlOperatorFeedbackUnitOfWork
from studymate.infrastructure.operator.goal_cursors import FernetOperatorGoalCursorCodec
from studymate.infrastructure.operator.goal_transactions import SqlOperatorGoalUnitOfWork
from studymate.infrastructure.operator.help_history_cursors import (
    FernetOperatorHelpHistoryCursorCodec,
)
from studymate.infrastructure.operator.help_history_transactions import (
    SqlOperatorHelpHistoryUnitOfWork,
)
from studymate.infrastructure.operator.identity_links_cursors import (
    FernetOperatorIdentityLinksCursorCodec,
)
from studymate.infrastructure.operator.identity_links_transactions import (
    SqlOperatorIdentityLinksUnitOfWork,
)
from studymate.infrastructure.operator.lifecycle_history_cursors import (
    FernetOperatorLifecycleHistoryCursorCodec,
)
from studymate.infrastructure.operator.lifecycle_history_transactions import (
    SqlOperatorLifecycleHistoryUnitOfWork,
)
from studymate.infrastructure.operator.media_transactions import SqlOperatorProfileMediaUnitOfWork
from studymate.infrastructure.operator.membership_verification_transactions import (
    SqlManualMembershipUnitOfWork,
)
from studymate.infrastructure.operator.message_operations_cursors import (
    FernetOperatorMessageOperationCursorCodec,
)
from studymate.infrastructure.operator.message_operations_transactions import (
    SqlOperatorMessageOperationsUnitOfWork,
)
from studymate.infrastructure.operator.photo_cursors import FernetOperatorPhotoCursorCodec
from studymate.infrastructure.operator.photo_review_owner import SqlOwnPhotoReviewUnitOfWork
from studymate.infrastructure.operator.photo_review_transactions import SqlPhotoReviewUnitOfWork
from studymate.infrastructure.operator.photo_transactions import SqlOperatorPhotoUnitOfWork
from studymate.infrastructure.operator.preference_history_cursors import (
    FernetOperatorPreferenceHistoryCursorCodec,
)
from studymate.infrastructure.operator.preference_history_transactions import (
    SqlOperatorPreferenceHistoryUnitOfWork,
)
from studymate.infrastructure.operator.profile_history_cursors import (
    FernetOperatorProfileHistoryCursorCodec,
)
from studymate.infrastructure.operator.profile_history_transactions import (
    SqlOperatorProfileHistoryUnitOfWork,
)
from studymate.infrastructure.operator.report_cursors import FernetOperatorReportCursorCodec
from studymate.infrastructure.operator.report_transactions import SqlOperatorReportUnitOfWork
from studymate.infrastructure.operator.report_triage_cursors import FernetReportTriageSourceCodec
from studymate.infrastructure.operator.report_triage_guard import SqlReportTriageSourceGuard
from studymate.infrastructure.operator.report_triage_transactions import (
    SqlOperatorReportTriageUnitOfWork,
)
from studymate.infrastructure.operator.request_cursors import FernetOperatorRequestCursorCodec
from studymate.infrastructure.operator.request_transactions import SqlOperatorRequestUnitOfWork
from studymate.infrastructure.operator.session_history_cursors import (
    FernetOperatorSessionHistoryCursorCodec,
)
from studymate.infrastructure.operator.session_history_transactions import (
    SqlOperatorSessionHistoryUnitOfWork,
)
from studymate.infrastructure.operator.timeline_cursors import FernetOperatorEventCursorCodec
from studymate.infrastructure.operator.timeline_transactions import SqlOperatorTimelineUnitOfWork
from studymate.infrastructure.operator.transactions import SqlOperatorUnitOfWork
from studymate.infrastructure.operator.visibility_history_cursors import (
    FernetOperatorVisibilityHistoryCursorCodec,
)
from studymate.infrastructure.operator.visibility_history_transactions import (
    SqlOperatorVisibilityHistoryUnitOfWork,
)
from studymate.infrastructure.persistence.block_list import SqlOwnBlocksUnitOfWork
from studymate.infrastructure.persistence.blocks import SqlBlockUnitOfWork
from studymate.infrastructure.persistence.catalogue_search import SqlCatalogueUnitOfWork
from studymate.infrastructure.persistence.conversation_cursors import (
    FernetConversationListCursorCodec,
)
from studymate.infrastructure.persistence.conversation_details import (
    SqlConversationDetailsUnitOfWork,
)
from studymate.infrastructure.persistence.conversation_list import SqlConversationListUnitOfWork
from studymate.infrastructure.persistence.database import SqlDatabaseProbe
from studymate.infrastructure.persistence.discovery_deck import SqlDiscoveryDeckUnitOfWork
from studymate.infrastructure.persistence.discovery_passes import SqlPrivatePassUnitOfWork
from studymate.infrastructure.persistence.discovery_profiles import SqlDiscoveryProfileUnitOfWork
from studymate.infrastructure.persistence.email_delivery import SqlEmailWorkerUnitOfWork
from studymate.infrastructure.persistence.email_verification import SqlEmailUnitOfWork
from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
from studymate.infrastructure.persistence.google_login import SqlLoginUnitOfWork
from studymate.infrastructure.persistence.help_subjects import SqlHelpUnitOfWork
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityUnitOfWork
from studymate.infrastructure.persistence.media_resume import SqlPhotoResumeUnitOfWork
from studymate.infrastructure.persistence.media_uploads import SqlMediaUnitOfWork
from studymate.infrastructure.persistence.message_reads import SqlReadPositionUnitOfWork
from studymate.infrastructure.persistence.messaging import SqlMessageUnitOfWork
from studymate.infrastructure.persistence.native_login import SqlNativeUnitOfWork
from studymate.infrastructure.persistence.onboarding import SqlProfileSetupUnitOfWork
from studymate.infrastructure.persistence.photo_worker import SqlPhotoWorkerUnitOfWork
from studymate.infrastructure.persistence.product_events import (
    record_conversation_goal_share,
    record_conversation_read,
    record_manual_membership_event,
    record_message_outcome,
    record_message_report_event,
    record_notification_preference_event,
    record_operator_audit,
    record_peer_feedback,
    record_photo_review_event,
    record_report_review_event,
    record_report_triage_submission,
    record_request_outcome,
    record_request_viewed,
    record_study_outcome,
    record_study_prompt,
    record_support_event,
)
from studymate.infrastructure.persistence.profile_reports import SqlProfileReportUnitOfWork
from studymate.infrastructure.persistence.profiles import SqlProfileUnitOfWork
from studymate.infrastructure.persistence.registration import SqlRegistrationUnitOfWork
from studymate.infrastructure.persistence.transport_cleanup import SqlTransportCleanupUnitOfWork
from studymate.infrastructure.persistence.visibility import SqlVisibilityUnitOfWork
from studymate.infrastructure.policy_history.read import SqlPolicyHistoryUnitOfWork
from studymate.infrastructure.report_moderation.cursors import FernetReportReviewHistoryCursorCodec
from studymate.infrastructure.report_moderation.transactions import SqlReportModerationUnitOfWork
from studymate.infrastructure.requests.cursors import FernetRequestCursorCodec
from studymate.infrastructure.requests.expiry import SqlRequestExpiryUnitOfWork
from studymate.infrastructure.requests.expiry_loop import run_expiry_loop
from studymate.infrastructure.requests.queries import SqlRequestQueryUnitOfWork
from studymate.infrastructure.requests.transactions import SqlRequestUnitOfWork
from studymate.infrastructure.requests.viewing import SqlRequestViewUnitOfWork
from studymate.infrastructure.safety.message_reports import SqlMessageReportUnitOfWork
from studymate.infrastructure.security.browser_tokens import HmacBrowserTokenSigner
from studymate.infrastructure.security.discovery_cursor import FernetDiscoveryCursorCodec
from studymate.infrastructure.security.email_vault import AeadEmailVault
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.login_vault import AeadLoginVault
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from studymate.infrastructure.support.operator import SqlOperatorSupportUnitOfWork
from studymate.infrastructure.support.operator_inbox_cursors import (
    FernetOperatorSupportInboxCursorCodec,
)
from studymate.infrastructure.support.operator_inbox_transactions import (
    SqlOperatorSupportInboxUnitOfWork,
)
from studymate.infrastructure.support.persistence import SqlSupportUnitOfWork
from studymate.infrastructure.support.proofs import OpaqueSupportProofs
from studymate.infrastructure.workers.email_loop import run_email_loop
from studymate.infrastructure.workers.media_loop import run_media_loop
from studymate.presentation.ai import AiHttpServices, ai_router
from studymate.presentation.browser import BrowserConfiguration
from studymate.presentation.catalogue import CatalogueServices, catalogue_router
from studymate.presentation.changes.router import ChangeHttpServices, changes_router
from studymate.presentation.chat_images.router import ChatImageHttpServices, chat_image_router
from studymate.presentation.client_observations.router import (
    ClientObservationHttpServices,
    client_observations_router,
)
from studymate.presentation.command_body_limit import JsonCommandBodyLimit
from studymate.presentation.conversations import ConversationsHttpServices, conversations_router
from studymate.presentation.discovery import DiscoveryServices, discovery_router
from studymate.presentation.external_delivery.router import (
    ExternalDeliveryHttpServices,
    external_delivery_router,
)
from studymate.presentation.feedback.router import FeedbackHttpServices, feedback_router
from studymate.presentation.feedback.summaries import (
    FeedbackSummaryHttpServices,
    feedback_summary_router,
)
from studymate.presentation.health import health_router
from studymate.presentation.identity import AuthenticationServices, identity_router
from studymate.presentation.lifecycle.ban_router import BanHttpServices, ban_router
from studymate.presentation.lifecycle.deletion_router import DeletionHttpServices, deletion_router
from studymate.presentation.lifecycle.recovery import (
    DeletionRecoveryHttpServices,
    deletion_recovery_router,
)
from studymate.presentation.media import MediaServices, media_router
from studymate.presentation.messaging.goal_shares import GoalSharingHttpServices, goal_shares_router
from studymate.presentation.messaging.router import MessagingHttpServices, messaging_router
from studymate.presentation.native_login import NativeServices, native_router
from studymate.presentation.notification_preferences.router import (
    PreferenceHttpServices,
    notification_preferences_router,
)
from studymate.presentation.onboarding import OnboardingServices, onboarding_router
from studymate.presentation.operator.access_history_router import (
    OperatorAccessHistoryHttpServices,
    operator_access_history_router,
)
from studymate.presentation.operator.ai_router import OperatorAiHttpServices, operator_ai_router
from studymate.presentation.operator.audit_search_router import (
    OperatorAuditSearchHttpServices,
    operator_audit_search_router,
)
from studymate.presentation.operator.block_history_router import (
    OperatorBlockHistoryHttpServices,
    operator_block_history_router,
)
from studymate.presentation.operator.chat_image_router import (
    OperatorChatImageHttpServices,
    operator_chat_image_router,
)
from studymate.presentation.operator.chat_media_router import (
    OperatorChatMediaHttpServices,
    operator_chat_media_router,
)
from studymate.presentation.operator.conversation_index_router import (
    OperatorConversationIndexHttpServices,
    operator_conversation_index_router,
)
from studymate.presentation.operator.disclosure_router import (
    OperatorDisclosureHttpServices,
    operator_disclosure_router,
)
from studymate.presentation.operator.email_history_router import (
    OperatorEmailHistoryHttpServices,
    operator_email_history_router,
)
from studymate.presentation.operator.feedback_router import (
    OperatorFeedbackHttpServices,
    operator_feedback_router,
)
from studymate.presentation.operator.goal_router import (
    OperatorGoalHttpServices,
    operator_goal_router,
)
from studymate.presentation.operator.help_history_router import (
    OperatorHelpHistoryHttpServices,
    operator_help_history_router,
)
from studymate.presentation.operator.identity_links_router import (
    OperatorIdentityLinksHttpServices,
    operator_identity_links_router,
)
from studymate.presentation.operator.lifecycle_history_router import (
    OperatorLifecycleHistoryHttpServices,
    operator_lifecycle_history_router,
)
from studymate.presentation.operator.media_router import (
    OperatorProfileMediaHttpServices,
    operator_profile_media_router,
)
from studymate.presentation.operator.membership_verification_router import (
    ManualMembershipHttpServices,
    operator_membership_verification_router,
)
from studymate.presentation.operator.message_operations_router import (
    OperatorMessageOperationsHttpServices,
    operator_message_operations_router,
)
from studymate.presentation.operator.photo_review_router import (
    PhotoReviewHttpServices,
    operator_photo_review_router,
    own_photo_review_router,
)
from studymate.presentation.operator.photo_router import (
    OperatorPhotoHttpServices,
    operator_photo_router,
)
from studymate.presentation.operator.preference_history_router import (
    OperatorPreferenceHistoryHttpServices,
    operator_preference_history_router,
)
from studymate.presentation.operator.profile_history_router import (
    OperatorProfileHistoryHttpServices,
    operator_profile_history_router,
)
from studymate.presentation.operator.report_router import (
    OperatorReportHttpServices,
    operator_report_router,
)
from studymate.presentation.operator.report_triage_router import (
    OperatorReportTriageHttpServices,
    operator_report_triage_router,
)
from studymate.presentation.operator.request_router import (
    OperatorRequestHttpServices,
    operator_request_router,
)
from studymate.presentation.operator.router import OperatorHttpServices, operator_router
from studymate.presentation.operator.session_history_router import (
    OperatorSessionHistoryHttpServices,
    operator_session_history_router,
)
from studymate.presentation.operator.timeline_router import (
    OperatorTimelineHttpServices,
    operator_timeline_router,
)
from studymate.presentation.operator.visibility_history_router import (
    OperatorVisibilityHistoryHttpServices,
    operator_visibility_history_router,
)
from studymate.presentation.people import PeopleServices, people_router
from studymate.presentation.policy_history.router import policy_history_router
from studymate.presentation.problems import ProblemResponse
from studymate.presentation.profiles import ProfileServices, profile_router
from studymate.presentation.registration import RegistrationServices, registration_router
from studymate.presentation.report_moderation.router import (
    ReportModerationHttpServices,
    report_moderation_router,
)
from studymate.presentation.request_correlation import RequestCorrelation
from studymate.presentation.request_errors import validation_problem
from studymate.presentation.requests.router import RequestHttpServices, requests_router
from studymate.presentation.storage_errors import storage_problem
from studymate.presentation.study_context import StudyServices, study_router
from studymate.presentation.support.operator_inbox_router import (
    OperatorSupportInboxHttpServices,
    operator_support_inbox_router,
)
from studymate.presentation.support.operator_router import (
    OperatorSupportHttpServices,
    operator_support_router,
)
from studymate.presentation.support.router import SupportHttpServices, support_router
from studymate.presentation.unexpected_errors import unexpected_problem

if TYPE_CHECKING:
    from studymate.application.bootstrap_data.apply import BootstrapApplied
    from studymate.domain.bootstrap_data.inputs import BootstrapBatch


async def apply_bootstrap_reference_data(
    batch: "BootstrapBatch", database_url: str
) -> "BootstrapApplied":
    """Explicit CLI composition only; API startup never applies reference data."""
    from studymate.application.bootstrap_data.apply import ApplyBootstrapData
    from studymate.infrastructure.bootstrap_data.persistence import SqlBootstrapDataUnitOfWork
    from studymate.infrastructure.bootstrap_data.runtime import open_bootstrap_database

    async with open_bootstrap_database(database_url) as sessions:
        return await ApplyBootstrapData(SqlBootstrapDataUnitOfWork(sessions))(batch)


def _install_problem_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.add_exception_handler(StorageUnavailableError, storage_problem)
    app.add_exception_handler(Exception, unexpected_problem)


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings if settings is not None else Settings()
    telemetry = _telemetry(configuration.observability)
    engine = create_async_engine(
        configuration.database_url.get_secret_value(),
        pool_pre_ping=True,
        connect_args={"timeout": 5, "server_settings": {"lock_timeout": "1000"}},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    ai_engine = (
        create_ai_admission_engine(configuration.database_url.get_secret_value())
        if configuration.authentication is not None
        else None
    )

    change_engine = (
        create_change_read_engine(configuration.database_url.get_secret_value())
        if configuration.authentication is not None
        else None
    )

    http = httpx.AsyncClient(
        timeout=5.0,
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        follow_redirects=False,
    )

    stream_signals = (
        StreamSignals(telemetry.meter_provider.get_meter("studymate.sse")) if telemetry else None
    )
    media_storage = MediaStorageHandle()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as resources:
            if telemetry is not None:
                resources.push_async_callback(telemetry.shutdown)
            resources.push_async_callback(engine.dispose)
            if ai_engine is not None:
                resources.push_async_callback(ai_engine.dispose)
            if change_engine is not None:
                resources.push_async_callback(change_engine.dispose)
            resources.push_async_callback(http.aclose)
            database = _database_telemetry(telemetry)
            if database is not None:
                database.attach(engine, DatabasePool.CORE)
                if ai_engine is not None:
                    database.attach(ai_engine, DatabasePool.AI_ADMISSION)
                if change_engine is not None:
                    database.attach(change_engine, DatabasePool.CHANGE_READ)
                resources.callback(database.close)
            if stream_signals is not None:
                resources.callback(stream_signals.close)
            if configuration.media is not None:
                media_storage.bind(
                    await resources.enter_async_context(_open_media_storage(configuration.media))
                )
            try:
                yield
            finally:
                media_storage.unbind()

    # Disable automatic query/exception capture; export only allowlisted telemetry.
    app = FastAPI(
        title="Peerly API",
        lifespan=lifespan,
        telemetry={"tracing": False, "metrics": False, "logs": False, "auto_configure": False},
        responses={500: {"model": ProblemResponse}},
    )
    _install_problem_handlers(app)
    app.add_middleware(JsonCommandBodyLimit)
    app.add_middleware(
        RequestCorrelation,
        observer=JsonHttpObserver(),
        tracing=telemetry.tracing if telemetry is not None else OtelHttpTracing(),
    )
    app.include_router(health_router(CheckReadiness(SqlDatabaseProbe(sessions))))
    if (
        configuration.authentication is not None
        and ai_engine is not None
        and change_engine is not None
    ):
        auth_services = _authentication_services(configuration.authentication, sessions, http)
        auth_services = _mount_native_identity(app, auth_services, sessions)
        app.include_router(_observation_router(configuration, sessions, auth_services))
        app.include_router(
            changes_router(
                ChangeHttpServices(
                    ReadChanges(
                        SqlChangeReadUnitOfWork(
                            async_sessionmaker(
                                change_engine, expire_on_commit=False, autoflush=False
                            )
                        ),
                        Sha256SessionHasher(),
                    ),
                    observations=stream_signals,
                )
            )
        )
        app.include_router(
            _ai_router(
                configuration.authentication,
                configuration.ai,
                async_sessionmaker(ai_engine, expire_on_commit=False, autoflush=False),
                auth_services,
            )
        )
        for router in _student_routers(
            configuration.authentication, sessions, auth_services, media_storage
        ):
            app.include_router(router)
        for router in _registration_routers(sessions, auth_services):
            app.include_router(router)
    return app


def _registration_routers(
    sessions: async_sessionmaker[AsyncSession], auth_services: AuthenticationServices
) -> tuple[APIRouter, ...]:
    unit = SqlRegistrationUnitOfWork(sessions)
    public_history = APIRouter(prefix="/api/v1")
    public_history.include_router(
        policy_history_router(ReadPolicyHistory(SqlPolicyHistoryUnitOfWork(sessions)))
    )
    return (
        registration_router(
            RegistrationServices(
                BeginRegistration(unit, Sha256SessionHasher()),
                CompleteRegistration(unit, Sha256SessionHasher()),
                ReadPolicyStatus(unit, Sha256SessionHasher()),
                ReadPublishedPolicy(unit),
                auth_services.signer,
                auth_services.browser,
            )
        ),
        public_history,
    )


def _observation_router(
    configuration: Settings,
    sessions: async_sessionmaker[AsyncSession],
    auth: AuthenticationServices,
) -> APIRouter:
    authentication = configuration.authentication
    if authentication is None:
        raise ValueError("Observation routing requires configured authentication")
    assets = ApprovedPublicAssets(
        tuple(
            PublicReleaseAssets(release.release_id, release.asset_ids)
            for release in configuration.public_asset_releases
        )
    )
    return client_observations_router(
        ClientObservationHttpServices(
            AcceptClientObservations(
                SqlObservationIntakeUnitOfWork(sessions),
                Sha256SessionHasher(),
                HmacIntentFingerprinter(bytes.fromhex(authentication.code_key.get_secret_value())),
                assets,
            ),
            auth.signer,
            auth.browser,
        )
    )


def create_ai_admission_engine(
    database_url: str, *, server_settings: Mapping[str, str] | None = None
) -> AsyncEngine:
    """One bounded admission policy for application composition and controlled load tests."""
    connect_args: dict[str, object] = {
        "timeout": 2,
        "server_settings": {"lock_timeout": "1000", **(server_settings or {})},
    }
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=0,
        pool_timeout=0.25,
        connect_args=connect_args,
    )


def create_change_read_engine(
    database_url: str, *, server_settings: Mapping[str, str] | None = None
) -> AsyncEngine:
    """Transport reads have their own bounded pool, independent of core and AI."""
    connect_args: dict[str, object] = {
        "timeout": 2,
        "server_settings": {"lock_timeout": "1000", **(server_settings or {})},
    }
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=0,
        pool_timeout=0.25,
        connect_args=connect_args,
    )


def create_changes_worker_engine(
    database_url: str, *, server_settings: Mapping[str, str] | None = None
) -> AsyncEngine:
    """One maintenance connection; never share the stream-read admission pool."""
    connect_args: dict[str, object] = {
        "timeout": 5,
        "server_settings": {"lock_timeout": "1000", **(server_settings or {})},
    }
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        pool_timeout=2,
        connect_args=connect_args,
    )


def _database_telemetry(telemetry: TelemetryRuntime | None) -> DatabaseTelemetry | None:
    if telemetry is None:
        return None
    return DatabaseTelemetry(
        telemetry.tracer_provider.get_tracer("studymate.database"),
        telemetry.meter_provider.get_meter("studymate.database"),
    )


def _telemetry(
    configuration: ObservabilityConfiguration | None, service_name: str = "studymate-api"
) -> TelemetryRuntime | None:
    bind_log_release(configuration.release if configuration is not None else None)
    if configuration is None:
        return None
    return build_telemetry(
        TelemetryConfiguration(
            service_name,
            configuration.collector_origin,
            configuration.environment,
            configuration.release,
            configuration.trace_queue_capacity,
        )
    )


def _mount_native_identity(
    app: FastAPI, auth_services: AuthenticationServices, sessions: async_sessionmaker[AsyncSession]
) -> AuthenticationServices:
    native_uow = SqlNativeUnitOfWork(sessions)
    native_hasher = Sha256SessionHasher()
    native_services = NativeServices(
        signer=auth_services.signer,
        start=BeginNativeLogin(
            auth_services.begin, RegisterNativeAttempt(native_uow, native_hasher)
        ),
        exchange=ExchangeNativeAttempt(native_uow, native_hasher, auth_services.begin.vault),
        browser=auth_services.browser,
        wake_url=(
            "dev.alekseiorlov.peerly.staging://auth/complete"
            if auth_services.browser.public_origin == "https://peerly-staging.aleksei-orlov.dev"
            else "dev.alekseiorlov.peerly://auth/complete"
        ),
    )
    auth_services = replace(
        auth_services,
        native_complete=CompleteLoginForClient(
            IdentifyNativeCallback(native_uow, native_hasher),
            auth_services.complete,
            BindNativeCallback(native_uow, native_hasher),
            CancelNativeAttempt(native_uow, native_hasher),
        ),
    )
    app.include_router(identity_router(auth_services, native_services.finish))
    app.include_router(native_router(native_services))
    return auth_services


def _authentication_services(
    configuration: AuthenticationConfiguration,
    sessions: async_sessionmaker[AsyncSession],
    http: httpx.AsyncClient,
) -> AuthenticationServices:
    provider = GoogleOidcProvider(
        GoogleConfiguration(
            configuration.client_id,
            configuration.client_secret.get_secret_value(),
            configuration.public_origin + "/api/v1/auth/google/callback",
        ),
        http,
    )
    uow = SqlLoginUnitOfWork(sessions)
    vault = AeadLoginVault(bytes.fromhex(configuration.envelope_key.get_secret_value()))
    email_uow = SqlEmailUnitOfWork(sessions)
    email_vault = AeadEmailVault(
        bytes.fromhex(configuration.code_key.get_secret_value()),
        bytes.fromhex(configuration.envelope_key.get_secret_value()),
    )
    email_policy = EmailPolicy(
        deliveries_per_account=configuration.email_deliveries_per_account_hour,
        deliveries_per_address=configuration.email_deliveries_per_address_hour,
        starts_per_source=configuration.email_starts_per_source_hour,
    )
    return AuthenticationServices(
        begin=BeginGoogleLogin(uow, provider, vault, configuration.google_starts_per_hour),
        start_email=StartEmailChallenge(
            email_uow, Sha256SessionHasher(), email_vault, email_policy
        ),
        verify_email=VerifyStudentEmail(email_uow, Sha256SessionHasher(), email_vault),
        read_email=ReadEmailChallenge(email_uow, Sha256SessionHasher(), email_policy),
        complete=HandleGoogleCallback(
            uow,
            CompleteGoogleLogin(uow, provider, vault),
            configuration.callback_failures_per_hour,
        ),
        bootstrap=ReadBootstrap(
            ReadIdentity(
                SqlIdentityUnitOfWork(sessions, shared_identity_locks=True), Sha256SessionHasher()
            )
        ),
        logout=Logout(SqlIdentityUnitOfWork(sessions), Sha256SessionHasher()),
        signer=HmacBrowserTokenSigner(
            bytes.fromhex(configuration.browser_signing_key.get_secret_value())
        ),
        browser=BrowserConfiguration(
            configuration.public_origin, frozenset({configuration.public_origin})
        ),
    )


async def run_email_worker(configuration: EmailWorkerSettings, stop: asyncio.Event) -> None:
    telemetry = _telemetry(configuration.observability, "studymate-email-worker")
    engine = create_async_engine(
        configuration.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=0,
        pool_timeout=2,
        connect_args={"timeout": 5, "server_settings": {"lock_timeout": "1000"}},
    )
    database = _database_telemetry(telemetry)
    if database is not None:
        database.attach(engine, DatabasePool.EMAIL)
    try:
        smtp = configuration.smtp
        tls_context = await asyncio.to_thread(ssl.create_default_context)
        sender = SmtpEmailSender(
            SmtpConfiguration(
                smtp.hostname,
                smtp.port,
                smtp.username.get_secret_value(),
                smtp.password.get_secret_value(),
                smtp.sender,
                smtp.mode,
                reply_to=smtp.reply_to,
            ),
            tls_context,
        )
        vault = AeadEmailVault(
            bytes.fromhex(configuration.code_key.get_secret_value()),
            bytes.fromhex(configuration.envelope_key.get_secret_value()),
        )
        step = DeliverVerificationEmail(
            SqlEmailWorkerUnitOfWork(
                async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
            ),
            sender,
            vault,
        )
        observed = ObservedVerificationDelivery(
            step,
            tracer=telemetry.tracing.tracer if telemetry is not None else None,
            meter=telemetry.meter_provider.get_meter("studymate.email")
            if telemetry is not None
            else None,
        )
        await run_email_loop(observed, stop)
    finally:
        try:
            await engine.dispose()
        finally:
            if database is not None:
                database.close()
            if telemetry is not None:
                await telemetry.shutdown()


@runtime_checkable
class _S3CacheWarmup(Protocol):
    # aiobotocore3.10 exposes this public API; generated stubs omit it.
    # Narrow at runtime rather than adding Any, a cast or an unchecked ignore.
    def warm_up_loader_caches(self, service_name: str) -> None: ...


def _prepare_media_session() -> AioSession:
    session = AioSession(
        session_vars={
            "profile": (None, None, None, None),
            "config_file": (None, None, "/dev/null", None),
            "credentials_file": (None, None, "/dev/null", None),
        }
    )
    session.get_scoped_config()
    if not isinstance(session, _S3CacheWarmup):
        raise RuntimeError("Pinned S3 SDK cache warmup is unavailable")
    session.warm_up_loader_caches("s3")
    return session


@asynccontextmanager
async def _open_media_storage(configuration: MediaConfiguration) -> AsyncIterator[MediaStorage]:
    session = await asyncio.to_thread(_prepare_media_session)
    options = AioConfig(
        signature_version="s3v4",
        connect_timeout=5,
        read_timeout=15,
        max_pool_connections=2,
        retries={"total_max_attempts": 1},
        s3={"addressing_style": "path"},
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
    )
    async with session.create_client(
        "s3",
        region_name=configuration.region,
        endpoint_url=configuration.endpoint_origin,
        aws_access_key_id=configuration.access_key_id.get_secret_value(),
        aws_secret_access_key=configuration.secret_access_key.get_secret_value(),
        config=options,
    ) as client:
        yield S3MediaStorage(client, configuration.bucket)


async def run_media_worker(configuration: MediaWorkerSettings, stop: asyncio.Event) -> None:
    telemetry = _telemetry(configuration.observability, "studymate-media-worker")
    engine = create_async_engine(
        configuration.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=0,
        pool_timeout=2,
        connect_args={"timeout": 5, "server_settings": {"lock_timeout": "1000"}},
    )
    processor = BoundedImageProcessor()
    database = _database_telemetry(telemetry)
    if database is not None:
        database.attach(engine, DatabasePool.MEDIA)
    try:
        async with _open_media_storage(configuration.media) as storage:
            sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
            photo = ProcessNextPhoto(SqlPhotoWorkerUnitOfWork(sessions), storage, processor)
            cleanup = CleanupMediaTransport(SqlTransportCleanupUnitOfWork(sessions), storage)
            chat_image = ProcessNextChatImage(
                SqlChatImageWorkerUnitOfWork(sessions), storage, processor
            )
            chat_cleanup = CleanupMediaTransport(SqlImageCleanupUnitOfWork(sessions), storage)
            tracer = telemetry.tracing.tracer if telemetry is not None else None
            meter = (
                telemetry.meter_provider.get_meter("studymate.media")
                if telemetry is not None
                else None
            )
            await run_media_loop(
                ObservedMediaStep(photo, "photo", tracer, meter),
                ObservedMediaStep(chat_image, "chat_image", tracer, meter),
                ObservedMediaStep(cleanup, "cleanup", tracer, meter),
                ObservedMediaStep(chat_cleanup, "chat_cleanup", tracer, meter),
                stop,
            )
    finally:
        try:
            await processor.close()
        finally:
            try:
                await engine.dispose()
            finally:
                if database is not None:
                    database.close()
                if telemetry is not None:
                    await telemetry.shutdown()


def _student_routers(
    configuration: AuthenticationConfiguration,
    sessions: async_sessionmaker[AsyncSession],
    auth_services: AuthenticationServices,
    media_storage: MediaStorage,
) -> tuple[APIRouter, ...]:
    intent_fingerprinter = HmacIntentFingerprinter(
        bytes.fromhex(configuration.code_key.get_secret_value())
    )
    profile_uow = SqlProfileUnitOfWork(sessions)
    profile_hasher = Sha256SessionHasher()
    profile_routes = profile_router(
        ProfileServices(
            SaveOwnProfile(profile_uow, profile_hasher, intent_fingerprinter),
            ReadOwnProfile(
                SqlProfileUnitOfWork(sessions, shared_identity_locks=True), profile_hasher
            ),
            ReadProfileReferenceData(
                SqlProfileUnitOfWork(sessions, shared_identity_locks=True), profile_hasher
            ),
            auth_services.signer,
            auth_services.browser,
        )
    )
    goal_uow = SqlGoalUnitOfWork(sessions)
    help_uow = SqlHelpUnitOfWork(sessions)
    study_routes = study_router(
        StudyServices(
            save_goal=SaveOwnGoal(goal_uow, profile_hasher, intent_fingerprinter),
            complete_goal=CompleteOwnGoal(goal_uow, profile_hasher, intent_fingerprinter),
            read_goal=ReadOwnGoal(
                SqlGoalUnitOfWork(sessions, shared_identity_locks=True), profile_hasher
            ),
            save_help=SaveOwnHelpSubjects(help_uow, profile_hasher, intent_fingerprinter),
            read_help=ReadOwnHelpSubjects(
                SqlHelpUnitOfWork(sessions, shared_identity_locks=True), profile_hasher
            ),
            signer=auth_services.signer,
            browser=auth_services.browser,
        )
    )
    catalogue_routes = catalogue_router(
        CatalogueServices(SearchSubjects(SqlCatalogueUnitOfWork(sessions), profile_hasher))
    )
    media_uow = SqlMediaUnitOfWork(sessions)
    media_hasher = Sha256SessionHasher()
    media_routes = media_router(
        MediaServices(
            start=StartPhotoUpload(
                media_uow,
                media_hasher,
                intent_fingerprinter,
            ),
            change=ChangePhotoUpload(
                media_uow,
                media_hasher,
                intent_fingerprinter,
            ),
            read=ReadOwnPhotoUpload(
                SqlMediaUnitOfWork(sessions, shared_identity_locks=True), media_hasher
            ),
            resume=ReadOwnPhotoResume(SqlPhotoResumeUnitOfWork(sessions), media_hasher),
            access=CreatePhotoUploadAccess(media_uow, media_hasher, media_storage),
            display=ReadOwnPhotoDisplay(
                SqlMediaUnitOfWork(sessions, shared_identity_locks=True),
                media_hasher,
                media_storage,
            ),
            signer=auth_services.signer,
            browser=auth_services.browser,
        )
    )
    onboarding_routes = onboarding_router(
        OnboardingServices(
            ReadOnboardingStatus(SqlProfileSetupUnitOfWork(sessions), profile_hasher),
            ChangeOwnVisibility(
                SqlVisibilityUnitOfWork(sessions), profile_hasher, intent_fingerprinter
            ),
            auth_services.signer,
            auth_services.browser,
        )
    )
    people_routes = _people_router(sessions, auth_services, media_storage, intent_fingerprinter)
    discovery_routes = _discovery_router(
        configuration, sessions, auth_services, intent_fingerprinter
    )
    return (
        profile_routes,
        study_routes,
        catalogue_routes,
        media_routes,
        onboarding_routes,
        people_routes,
        discovery_routes,
        _requests_router(configuration, sessions, auth_services, intent_fingerprinter),
        _messaging_router(
            configuration, sessions, auth_services, media_storage, intent_fingerprinter
        ),
        _goal_sharing_router(configuration, sessions, auth_services, intent_fingerprinter),
        _conversations_router(configuration, sessions, auth_services, intent_fingerprinter),
        *_feedback_routers(sessions, auth_services, intent_fingerprinter),
        *_lifecycle_routers(configuration, sessions, auth_services, intent_fingerprinter),
        _chat_image_router(sessions, auth_services, intent_fingerprinter, media_storage),
        *_operator_routers(configuration, sessions, intent_fingerprinter, media_storage),
        _operator_membership_router(sessions, auth_services, intent_fingerprinter),
        *_human_review_routers(configuration, sessions, auth_services, intent_fingerprinter),
        *_student_support_routers(sessions, auth_services, intent_fingerprinter),
    )


def _ai_router(
    configuration: AuthenticationConfiguration,
    ai: AiHttpConfiguration,
    sessions: async_sessionmaker[AsyncSession],
    auth_services: AuthenticationServices,
) -> APIRouter:
    # Availability comes from the fresh, accepted singleton runtime fact, never an enable flag.
    uow = SqlAiUnitOfWork(
        sessions, AdmissionPolicy(request_budget_seconds=ai.request_budget_seconds)
    )
    hasher = Sha256SessionHasher()
    router = APIRouter()
    router.include_router(
        ai_router(
            AiHttpServices(
                SubmitStudentJob(
                    uow,
                    hasher,
                    HmacIntentFingerprinter(
                        bytes.fromhex(configuration.code_key.get_secret_value())
                    ),
                    versions=None,
                ),
                ReadStudentJob(uow, hasher),
                CancelStudentJob(uow, hasher),
                auth_services.signer,
                auth_services.browser,
                retry_after_seconds=ai.retry_after_seconds,
            )
        )
    )
    router.include_router(_report_triage_router(configuration, ai, sessions, auth_services))
    return router


def _people_router(
    sessions: async_sessionmaker[AsyncSession],
    auth_services: AuthenticationServices,
    media_reader: MediaReader,
    fingerprinter: IntentFingerprinter,
) -> APIRouter:
    hasher = Sha256SessionHasher()
    profiles = SqlDiscoveryProfileUnitOfWork(sessions)
    return people_router(
        PeopleServices(
            ReadDiscoveryProfile(profiles, hasher),
            ReadDiscoveryPhoto(profiles, hasher, media_reader),
            SubmitProfileReport(SqlProfileReportUnitOfWork(sessions), hasher, fingerprinter),
            SubmitMessageImageReport(
                SqlMessageReportUnitOfWork(sessions, record_message_report_event),
                hasher,
                fingerprinter,
            ),
            IssueMessageImageReportContext(
                SqlMessageReportUnitOfWork(sessions, record_message_report_event), hasher
            ),
            ChangeOwnBlock(SqlBlockUnitOfWork(sessions), hasher, fingerprinter),
            ReadOwnBlocks(SqlOwnBlocksUnitOfWork(sessions), hasher),
            auth_services.signer,
            auth_services.browser,
        )
    )


def _discovery_router(
    configuration: AuthenticationConfiguration,
    sessions: async_sessionmaker[AsyncSession],
    auth_services: AuthenticationServices,
    fingerprinter: IntentFingerprinter,
) -> APIRouter:
    hasher = Sha256SessionHasher()
    codec = FernetDiscoveryCursorCodec.from_key(
        bytes.fromhex(configuration.envelope_key.get_secret_value())
    )
    return discovery_router(
        DiscoveryServices(
            ReadDiscoveryDeck(SqlDiscoveryDeckUnitOfWork(sessions), hasher, codec),
            ChangePrivatePass(SqlPrivatePassUnitOfWork(sessions), hasher, fingerprinter),
            auth_services.signer,
            auth_services.browser,
        )
    )


def _requests_router(
    configuration: AuthenticationConfiguration,
    sessions: async_sessionmaker[AsyncSession],
    auth_services: AuthenticationServices,
    fingerprinter: IntentFingerprinter,
) -> APIRouter:
    hasher = Sha256SessionHasher()
    commands = SqlRequestUnitOfWork(sessions, record_request_outcome)
    queries = SqlRequestQueryUnitOfWork(sessions)
    codec = FernetRequestCursorCodec.from_key(
        bytes.fromhex(configuration.envelope_key.get_secret_value())
    )
    return requests_router(
        RequestHttpServices(
            PreviewRequest(commands, hasher, fingerprinter),
            SendRequest(commands, hasher, fingerprinter),
            AcceptRequest(commands, hasher, fingerprinter),
            DeclineRequest(commands, hasher, fingerprinter),
            UndoDecline(commands, hasher, fingerprinter),
            WithdrawRequest(commands, hasher, fingerprinter),
            ListRequests(
                SqlRequestQueryUnitOfWork(sessions, shared_identity_locks=True), hasher, codec
            ),
            ReadRequest(queries, hasher),
            AcknowledgeRequestViewed(
                SqlRequestViewUnitOfWork(sessions, record_request_viewed), hasher, fingerprinter
            ),
            auth_services.signer,
            auth_services.browser,
        )
    )


async def run_requests_worker(configuration: RequestsWorkerSettings, stop: asyncio.Event) -> None:
    telemetry = _telemetry(configuration.observability, "peerly-requests-worker")
    engine = create_async_engine(
        configuration.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        pool_timeout=2,
        connect_args={"timeout": 5, "server_settings": {"lock_timeout": "1000"}},
    )
    database = _database_telemetry(telemetry)
    if database is not None:
        database.attach(engine, DatabasePool.EXPIRY)
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        step = ExpireRequests(SqlRequestExpiryUnitOfWork(sessions, record_request_outcome))
        await run_expiry_loop(
            ObservedRequestExpiry(
                step,
                telemetry.tracing.tracer if telemetry is not None else None,
                telemetry.meter_provider.get_meter("studymate.requests")
                if telemetry is not None
                else None,
            ),
            stop,
        )
    finally:
        try:
            await engine.dispose()
        finally:
            if database is not None:
                database.close()
            if telemetry is not None:
                await telemetry.shutdown()


def _messaging_router(
    configuration: AuthenticationConfiguration,
    sessions: async_sessionmaker[AsyncSession],
    auth_services: AuthenticationServices,
    storage: MediaReader,
    fingerprinter: IntentFingerprinter,
) -> APIRouter:
    hasher = Sha256SessionHasher()
    commands = SqlMessageUnitOfWork(sessions, record_message_outcome)
    history = SqlMessageHistoryUnitOfWork(sessions, record_message_outcome)
    codec = FernetMessageHistoryCursorCodec.from_key(
        bytes.fromhex(configuration.envelope_key.get_secret_value())
    )
    return messaging_router(
        MessagingHttpServices(
            ReadMessageHistory(history, hasher, codec),
            SendMessage(commands, hasher, fingerprinter),
            CancelMessage(commands, hasher, fingerprinter),
            ReadMessageOutcome(commands, hasher),
            ReadChatParticipant(commands, hasher),
            ReadChatAvatar(commands, hasher, storage),
            auth_services.signer,
            auth_services.browser,
        )
    )


def _goal_sharing_router(
    configuration: AuthenticationConfiguration,
    sessions: async_sessionmaker[AsyncSession],
    auth_services: AuthenticationServices,
    fingerprinter: IntentFingerprinter,
) -> APIRouter:
    hasher = Sha256SessionHasher()
    uow = SqlGoalShareUnitOfWork(sessions, record_message_outcome, record_conversation_goal_share)
    codec = FernetGoalShareCursorCodec.from_key(
        bytes.fromhex(configuration.envelope_key.get_secret_value())
    )
    return goal_shares_router(
        GoalSharingHttpServices(
            ShareCurrentGoal(uow, hasher, fingerprinter),
            ReadGoalShares(uow, hasher, codec),
            auth_services.signer,
            auth_services.browser,
        )
    )


def _conversations_router(
    configuration: AuthenticationConfiguration,
    sessions: async_sessionmaker[AsyncSession],
    auth_services: AuthenticationServices,
    fingerprinter: IntentFingerprinter,
) -> APIRouter:
    hasher = Sha256SessionHasher()
    return conversations_router(
        ConversationsHttpServices(
            ListConversations(
                SqlConversationListUnitOfWork(sessions),
                hasher,
                FernetConversationListCursorCodec.from_key(
                    bytes.fromhex(configuration.envelope_key.get_secret_value())
                ),
            ),
            ReadConversationDetails(
                SqlConversationDetailsUnitOfWork(
                    sessions, record_message_outcome, record_conversation_read
                ),
                hasher,
            ),
            AcknowledgeConversationRead(
                SqlReadPositionUnitOfWork(
                    sessions, record_message_outcome, record_conversation_read
                ),
                hasher,
                fingerprinter,
            ),
            auth_services.signer,
            auth_services.browser,
        )
    )


def _feedback_routers(
    sessions: async_sessionmaker[AsyncSession],
    auth_services: AuthenticationServices,
    fingerprinter: IntentFingerprinter,
) -> tuple[APIRouter, ...]:
    hasher = Sha256SessionHasher()
    commands = SqlFeedbackUnitOfWork(
        sessions, FeedbackRecorders(record_study_outcome, record_peer_feedback, record_study_prompt)
    )
    summaries = SqlFeedbackSummaryUnitOfWork(sessions)
    return (
        feedback_router(
            FeedbackHttpServices(
                SaveStudyOutcome(commands, hasher, fingerprinter),
                ReadOwnStudyOutcome(commands, hasher),
                SaveFeedback(commands, hasher, fingerprinter),
                ReadOwnFeedbackContext(commands, hasher),
                OfferStudyPromptOnVisit(commands, hasher, fingerprinter),
                auth_services.signer,
                auth_services.browser,
            )
        ),
        feedback_summary_router(
            FeedbackSummaryHttpServices(
                ReadPublicFeedbackSummary(summaries, hasher),
                ReadOwnFeedbackSummary(summaries, hasher),
            )
        ),
    )


def _chat_image_router(
    sessions: async_sessionmaker[AsyncSession],
    auth_services: AuthenticationServices,
    fingerprinter: IntentFingerprinter,
    storage: MediaStorage,
) -> APIRouter:
    hasher = Sha256SessionHasher()
    reads = SqlImageReadUnitOfWork(sessions, record_message_outcome)
    display = SqlImageDisplayUnitOfWork(sessions, record_message_outcome)
    return chat_image_router(
        ChatImageHttpServices(
            start=StartChatImage(
                SqlChatImageStartUnitOfWork(sessions, record_message_outcome), hasher, fingerprinter
            ),
            finalize=FinalizeChatImage(
                SqlChatImageFinalizeUnitOfWork(sessions, record_message_outcome),
                hasher,
                fingerprinter,
            ),
            read=ReadOwnedImagePreparation(reads, hasher),
            recovery=ListOwnImagePreparations(reads, hasher),
            access=CreateChatImageUploadAccess(reads, hasher, storage),
            own_display=ReadOwnedImageDisplay(display, hasher, storage),
            message_display=ReadMessageImageDisplay(display, hasher, storage),
            signer=auth_services.signer,
            browser=auth_services.browser,
        )
    )


def _lifecycle_routers(
    configuration: AuthenticationConfiguration,
    sessions: async_sessionmaker[AsyncSession],
    auth_services: AuthenticationServices,
    fingerprinter: IntentFingerprinter,
) -> tuple[APIRouter, ...]:
    hasher = Sha256SessionHasher()
    proofs = HmacDeletionStatusProofs(
        bytes.fromhex(configuration.browser_signing_key.get_secret_value())
    )
    return (
        ban_router(
            BanHttpServices(
                ChangeAccountBan(
                    SqlBanUnitOfWork(sessions, apply_lifecycle_effects, record_operator_audit),
                    hasher,
                    fingerprinter,
                ),
                auth_services.signer,
                auth_services.browser,
            )
        ),
        deletion_router(
            DeletionHttpServices(
                DeleteOwnAccount(
                    SqlDeletionUnitOfWork(
                        sessions, apply_lifecycle_effects, authorize_deletion_workflow
                    ),
                    hasher,
                    fingerprinter,
                ),
                auth_services.signer,
                auth_services.browser,
            )
        ),
        deletion_recovery_router(
            DeletionRecoveryHttpServices(
                PrepareOwnDeletion(SqlPrepareDeletionUnitOfWork(sessions), hasher, proofs),
                ReadOwnDeletionStatus(SqlDeletionStatusUnitOfWork(sessions), proofs),
                auth_services.signer,
                auth_services.browser,
            )
        ),
    )


def _operator_membership_router(
    sessions: async_sessionmaker[AsyncSession],
    auth_services: AuthenticationServices,
    fingerprinter: IntentFingerprinter,
) -> APIRouter:
    hasher = Sha256SessionHasher()
    unit = SqlManualMembershipUnitOfWork(
        sessions, record_operator_audit, record_manual_membership_event
    )
    return operator_membership_verification_router(
        ManualMembershipHttpServices(
            ReadManualMembershipContext(unit, hasher),
            ManuallyVerifyMembership(unit, hasher, fingerprinter),
            auth_services.signer,
            auth_services.browser,
        )
    )


def _operator_routers(
    configuration: AuthenticationConfiguration,
    sessions: async_sessionmaker[AsyncSession],
    fingerprinter: IntentFingerprinter,
    storage: MediaReader,
) -> tuple[APIRouter, ...]:
    hasher = Sha256SessionHasher()
    key = bytes.fromhex(configuration.envelope_key.get_secret_value())
    cursor = FernetOperatorCursorCodec.from_key(key)
    unit = SqlOperatorUnitOfWork(sessions, record_operator_audit)
    timeline = SqlOperatorTimelineUnitOfWork(sessions, record_operator_audit)
    reports = SqlOperatorReportUnitOfWork(sessions, record_operator_audit)
    history = SqlOperatorProfileHistoryUnitOfWork(sessions, record_operator_audit)
    help_history = SqlOperatorHelpHistoryUnitOfWork(sessions, record_operator_audit)
    goals = SqlOperatorGoalUnitOfWork(sessions, record_operator_audit)
    photos = SqlOperatorPhotoUnitOfWork(sessions, record_operator_audit)
    media = SqlOperatorProfileMediaUnitOfWork(sessions, record_operator_audit)
    ai_jobs = SqlOperatorAiUnitOfWork(sessions, record_operator_audit)
    requests = SqlOperatorRequestUnitOfWork(sessions, record_operator_audit)
    disclosures = SqlOperatorDisclosureUnitOfWork(sessions, record_operator_audit)
    chat_images = SqlOperatorChatImageUnitOfWork(sessions, record_operator_audit)
    feedback = SqlOperatorFeedbackUnitOfWork(sessions, record_operator_audit)
    conversation_index = SqlOperatorConversationIndexUnitOfWork(sessions, record_operator_audit)
    delivery_sources = SqlSourceInspectionUnitOfWork(sessions, record_operator_audit)
    support_inbox = SqlOperatorSupportInboxUnitOfWork(sessions, record_operator_audit)
    support_cursor = FernetOperatorSupportInboxCursorCodec.from_key(key)
    return (
        operator_block_history_router(
            OperatorBlockHistoryHttpServices(
                ReadOperatorBlockHistory(
                    SqlOperatorBlockHistoryUnitOfWork(sessions, record_operator_audit),
                    hasher,
                    FernetOperatorBlockHistoryCursorCodec.from_key(key),
                ),
            )
        ),
        operator_preference_history_router(
            OperatorPreferenceHistoryHttpServices(
                ReadOperatorPreferenceHistory(
                    SqlOperatorPreferenceHistoryUnitOfWork(sessions, record_operator_audit),
                    hasher,
                    FernetOperatorPreferenceHistoryCursorCodec.from_key(key),
                ),
            )
        ),
        operator_visibility_history_router(
            OperatorVisibilityHistoryHttpServices(
                ReadOperatorVisibilityHistory(
                    SqlOperatorVisibilityHistoryUnitOfWork(sessions, record_operator_audit),
                    hasher,
                    FernetOperatorVisibilityHistoryCursorCodec.from_key(key),
                ),
            )
        ),
        operator_router(
            OperatorHttpServices(
                SearchOperatorAccounts(unit, hasher, fingerprinter, cursor),
                ReadOperatorAccount(unit, hasher),
                ReadOperatorConversationMessages(unit, hasher, cursor),
            )
        ),
        operator_message_operations_router(
            OperatorMessageOperationsHttpServices(
                ReadOperatorMessageOperations(
                    SqlOperatorMessageOperationsUnitOfWork(sessions, record_operator_audit),
                    hasher,
                    FernetOperatorMessageOperationCursorCodec.from_key(key),
                ),
                ReadOperatorMessageOperation(
                    SqlOperatorMessageOperationsUnitOfWork(sessions, record_operator_audit), hasher
                ),
            )
        ),
        operator_identity_links_router(
            OperatorIdentityLinksHttpServices(
                ReadOperatorIdentityLinks(
                    SqlOperatorIdentityLinksUnitOfWork(sessions, record_operator_audit),
                    hasher,
                    FernetOperatorIdentityLinksCursorCodec.from_key(key),
                )
            )
        ),
        operator_session_history_router(
            OperatorSessionHistoryHttpServices(
                ReadOperatorSessionHistory(
                    SqlOperatorSessionHistoryUnitOfWork(sessions, record_operator_audit),
                    hasher,
                    FernetOperatorSessionHistoryCursorCodec.from_key(key),
                )
            )
        ),
        operator_email_history_router(
            OperatorEmailHistoryHttpServices(
                ReadOperatorEmailHistory(
                    SqlOperatorEmailHistoryUnitOfWork(sessions, record_operator_audit),
                    hasher,
                    FernetOperatorEmailHistoryCursorCodec.from_key(key),
                )
            )
        ),
        operator_access_history_router(
            OperatorAccessHistoryHttpServices(
                ReadOperatorAccessHistory(
                    SqlOperatorAccessHistoryUnitOfWork(sessions, record_operator_audit),
                    hasher,
                    FernetOperatorAccessHistoryCursorCodec.from_key(key),
                )
            )
        ),
        operator_lifecycle_history_router(
            OperatorLifecycleHistoryHttpServices(
                ReadOperatorLifecycleHistory(
                    SqlOperatorLifecycleHistoryUnitOfWork(sessions, record_operator_audit),
                    hasher,
                    FernetOperatorLifecycleHistoryCursorCodec.from_key(key),
                )
            )
        ),
        operator_conversation_index_router(
            OperatorConversationIndexHttpServices(
                ReadOperatorConversations(
                    conversation_index, hasher, FernetOperatorConversationCursorCodec.from_key(key)
                )
            )
        ),
        external_delivery_router(
            ExternalDeliveryHttpServices(
                SearchDeliverySources(
                    delivery_sources, hasher, fingerprinter, FernetSourceCursorCodec.from_key(key)
                ),
                ReadDeliverySource(delivery_sources, hasher),
            )
        ),
        operator_audit_search_router(
            OperatorAuditSearchHttpServices(
                SearchOperatorAudits(
                    SqlOperatorAuditSearchUnitOfWork(sessions, record_operator_audit),
                    hasher,
                    fingerprinter,
                    FernetOperatorAuditCursorCodec.from_key(key),
                )
            )
        ),
        operator_request_router(
            OperatorRequestHttpServices(
                ReadOperatorRequests(
                    requests, hasher, fingerprinter, FernetOperatorRequestCursorCodec.from_key(key)
                ),
                ReadOperatorRequestHistory(
                    requests, hasher, FernetOperatorRequestCursorCodec.from_key(key)
                ),
            )
        ),
        operator_disclosure_router(
            OperatorDisclosureHttpServices(
                ReadOperatorRequestDisclosures(
                    disclosures,
                    hasher,
                    fingerprinter,
                    FernetOperatorDisclosureCursorCodec.from_key(key),
                ),
            )
        ),
        operator_chat_image_router(
            OperatorChatImageHttpServices(
                ReadOperatorChatImageUploads(
                    chat_images,
                    hasher,
                    fingerprinter,
                    FernetOperatorChatImageCursorCodec.from_key(key),
                ),
                ReadOperatorChatImageHistory(
                    chat_images, hasher, FernetOperatorChatImageCursorCodec.from_key(key)
                ),
            )
        ),
        operator_feedback_router(
            OperatorFeedbackHttpServices(
                ReadOperatorFeedback(
                    feedback, hasher, fingerprinter, FernetOperatorFeedbackCursorCodec.from_key(key)
                ),
                ReadOperatorFeedbackHistory(
                    feedback, hasher, FernetOperatorFeedbackCursorCodec.from_key(key)
                ),
                ReadOperatorFeedbackRemovals(
                    feedback, hasher, FernetOperatorFeedbackCursorCodec.from_key(key)
                ),
            )
        ),
        operator_support_inbox_router(
            OperatorSupportInboxHttpServices(
                SearchOperatorSupportCases(support_inbox, hasher, fingerprinter, support_cursor),
                ReadOperatorSupportHistory(support_inbox, hasher, support_cursor),
            )
        ),
        operator_timeline_router(
            OperatorTimelineHttpServices(
                SearchOperatorEvents(
                    timeline, hasher, fingerprinter, FernetOperatorEventCursorCodec.from_key(key)
                ),
                ReadOperatorEvent(timeline, hasher),
                ReadOperatorAudit(timeline, hasher),
            )
        ),
        operator_report_router(
            OperatorReportHttpServices(
                SearchOperatorProfileReports(
                    reports, hasher, fingerprinter, FernetOperatorReportCursorCodec.from_key(key)
                ),
                ReadOperatorProfileReport(reports, hasher),
            )
        ),
        operator_profile_history_router(
            OperatorProfileHistoryHttpServices(
                ReadOperatorProfileHistory(
                    history, hasher, FernetOperatorProfileHistoryCursorCodec.from_key(key)
                )
            )
        ),
        operator_help_history_router(
            OperatorHelpHistoryHttpServices(
                ReadOperatorHelpHistory(
                    help_history, hasher, FernetOperatorHelpHistoryCursorCodec.from_key(key)
                )
            )
        ),
        operator_ai_router(
            OperatorAiHttpServices(
                ReadOperatorAiJobs(
                    ai_jobs, hasher, fingerprinter, FernetOperatorAiCursorCodec.from_key(key)
                ),
                ReadOperatorAiJob(ai_jobs, hasher),
            )
        ),
        operator_photo_router(
            OperatorPhotoHttpServices(
                ReadOperatorPhotoUploads(
                    photos, hasher, fingerprinter, FernetOperatorPhotoCursorCodec.from_key(key)
                ),
                ReadOperatorPhotoHistory(
                    photos, hasher, FernetOperatorPhotoCursorCodec.from_key(key)
                ),
            )
        ),
        operator_chat_media_router(
            OperatorChatMediaHttpServices(
                ReadOperatorChatMedia(
                    SqlOperatorChatMediaUnitOfWork(sessions, record_operator_audit), hasher, storage
                )
            )
        ),
        operator_profile_media_router(
            OperatorProfileMediaHttpServices(ReadOperatorProfileMedia(media, hasher, storage))
        ),
        operator_goal_router(
            OperatorGoalHttpServices(
                ReadOperatorGoals(
                    goals, hasher, fingerprinter, FernetOperatorGoalCursorCodec.from_key(key)
                ),
                ReadOperatorGoalHistory(goals, hasher, FernetOperatorGoalCursorCodec.from_key(key)),
            )
        ),
    )


async def run_changes_worker(configuration: ChangesWorkerSettings, stop: asyncio.Event) -> None:
    telemetry = _telemetry(configuration.observability, "peerly-changes-worker")
    engine = create_changes_worker_engine(configuration.database_url.get_secret_value())
    database = _database_telemetry(telemetry)
    if database is not None:
        database.attach(engine, DatabasePool.CHANGES)
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        tracer = telemetry.tracing.tracer if telemetry is not None else None
        meter = telemetry.meter_provider.get_meter("studymate.changes") if telemetry else None
        publish = ObservedChangeStep(
            PublishChanges(SqlChangePublicationUnitOfWork(sessions)),
            ChangeMaintenance.PUBLICATION,
            tracer,
            meter,
        )
        prune = ObservedChangeStep(
            PruneChanges(SqlChangeRetentionUnitOfWork(sessions)),
            ChangeMaintenance.RETENTION,
            tracer,
            meter,
        )
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(run_change_loop(publish, stop, ChangeMaintenance.PUBLICATION))
            tasks.create_task(run_change_loop(prune, stop, ChangeMaintenance.RETENTION))
    finally:
        try:
            await engine.dispose()
        finally:
            if database is not None:
                database.close()
            if telemetry is not None:
                await telemetry.shutdown()


async def run_ai_worker(configuration: AiWorkerSettings, stop: asyncio.Event) -> None:
    """Own one worker/heartbeat connection; runtime must prove its activation contract."""
    from studymate.infrastructure.ai.runtime.factory import (
        AiRuntimeConfiguration,
        create_ai_worker_runtime,
    )

    telemetry = _telemetry(configuration.observability, "studymate-ai-worker")
    engine = create_async_engine(
        configuration.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        pool_timeout=2,
        connect_args={"timeout": 5, "server_settings": {"lock_timeout": "1000"}},
    )
    database = _database_telemetry(telemetry)
    if database is not None:
        database.attach(engine, DatabasePool.AI)
    try:
        async with _open_media_storage(configuration.media) as storage:
            inputs = configuration.runtime
            runtime_configuration = AiRuntimeConfiguration(
                max_processes=inputs.max_processes,
                executable=inputs.executable,
                expected_version=inputs.expected_version,
                expected_sha256=inputs.expected_sha256,
                model=inputs.model,
                credential_directory=inputs.credential_directory,
                expected_account=inputs.expected_account.get_secret_value(),
                expected_login_owner=inputs.expected_login_owner.get_secret_value(),
                expected_oauth_issuer=inputs.expected_oauth_issuer,
                expected_oauth_client_id=inputs.expected_oauth_client_id,
                acceptance_artifact=inputs.acceptance_artifact,
                workspaces_root=inputs.workspaces_root,
                bubblewrap=inputs.bubblewrap,
                prlimit=inputs.prlimit,
            )
            sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
            runtime = create_ai_worker_runtime(
                sessions,
                storage,
                runtime_configuration,
                tracer=telemetry.tracer_provider.get_tracer("studymate.ai") if telemetry else None,
                meter=telemetry.meter_provider.get_meter("studymate.ai") if telemetry else None,
                reports=SqlReportTriageSourceGuard(),
            )
            await runtime.run(stop)
    finally:
        try:
            await engine.dispose()
        finally:
            if database is not None:
                database.close()
            if telemetry is not None:
                await telemetry.shutdown()


def _student_support_routers(
    sessions: async_sessionmaker[AsyncSession],
    auth_services: AuthenticationServices,
    fingerprinter: IntentFingerprinter,
) -> tuple[APIRouter, ...]:
    hasher = Sha256SessionHasher()
    preferences = SqlPreferenceUnitOfWork(sessions, record_notification_preference_event)
    support = SqlSupportUnitOfWork(sessions, record_support_event)
    operator = SqlOperatorSupportUnitOfWork(sessions, record_support_event, record_operator_audit)
    proofs = OpaqueSupportProofs()
    return (
        notification_preferences_router(
            PreferenceHttpServices(
                ReadOwnNotificationPreference(
                    SqlPreferenceUnitOfWork(
                        sessions, record_notification_preference_event, shared_identity_locks=True
                    ),
                    hasher,
                ),
                ChooseOwnNotificationPreference(preferences, hasher, fingerprinter),
                auth_services.signer,
                auth_services.browser,
            )
        ),
        support_router(
            SupportHttpServices(
                PrepareSupport(support, proofs),
                CreateSupportCase(support, proofs, hasher, fingerprinter),
                ReadSupportCase(support, proofs),
                ReadActorSupportCase(support, hasher),
                auth_services.signer,
                auth_services.browser,
                ReadRecentSupportCases(support, proofs),
                ReadRecentActorSupportCases(support, hasher),
            )
        ),
        operator_support_router(
            OperatorSupportHttpServices(
                ReadOperatorSupportCase(operator, hasher),
                ChangeOperatorSupportStatus(operator, hasher, fingerprinter),
                auth_services.signer,
                auth_services.browser,
            )
        ),
    )


@dataclass(frozen=True, slots=True)
class _ConfiguredExternalDestinations:
    destinations: tuple[DestinationRef, ...]

    def destination(self, sink: Sink) -> DestinationRef | None:
        return next((item for item in self.destinations if item.sink == sink), None)


def _external_destination_configs(
    settings: ExternalDeliveryWorkerSettings,
) -> tuple[DestinationConfig, ...]:
    configurations: list[DestinationConfig] = []
    if settings.umami is not None:
        configuration = settings.umami
        configurations.append(
            UmamiConfig(
                DestinationRef(Sink.UMAMI, configuration.revision),
                configuration.origin,
                configuration.website_id,
                hostname=configuration.hostname,
            )
        )
    if settings.telegram_support is not None:
        support = settings.telegram_support
        configurations.append(
            TelegramConfig(
                DestinationRef(Sink.TELEGRAM_SUPPORT, support.revision),
                support.chat_id,
                support.operator_origin,
                support.token.get_secret_value(),
                support.topic_id,
            )
        )
    return tuple(configurations)


def _external_transport(tls_context: ssl.SSLContext) -> httpx.AsyncBaseTransport:
    return httpx.AsyncHTTPTransport(
        verify=tls_context,
        trust_env=False,
        retries=0,
        limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
    )


async def run_external_delivery_worker(
    configuration: ExternalDeliveryWorkerSettings,
    stop: asyncio.Event,
) -> None:
    if stop.is_set():
        return
    telemetry = _telemetry(configuration.observability, "peerly-external-delivery-worker")
    async with AsyncExitStack() as resources:
        if telemetry is not None:
            resources.push_async_callback(telemetry.shutdown)
        engine = create_async_engine(
            configuration.database_url.get_secret_value(),
            pool_size=1,
            max_overflow=0,
            pool_timeout=2,
            pool_pre_ping=True,
            connect_args={"timeout": 5, "server_settings": {"lock_timeout": "1000"}},
        )
        resources.push_async_callback(engine.dispose)
        database = _database_telemetry(telemetry)
        if database is not None:
            database.attach(engine, DatabasePool.EXTERNAL_DELIVERY)
            resources.callback(database.close)
        signals = ExternalDeliverySignals(
            telemetry.meter_provider.get_meter("studymate.external") if telemetry else None
        )
        resources.callback(signals.close)
        tls_context = await asyncio.to_thread(ssl.create_default_context)
        transport = await resources.enter_async_context(_external_transport(tls_context))
        configurations = _external_destination_configs(configuration)
        sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        await register_destinations(
            sessions,
            tuple(
                DestinationRegistration(value.destination, target_fingerprint(value))
                for value in configurations
            ),
        )
        worker = ExternalDeliveryWorker(
            MaterializeDeliverySources(SqlMaterializationUnitOfWork(sessions)),
            DeliverNextExternalEvent(
                SqlExternalDeliveryQueue(sessions),
                _ConfiguredExternalDestinations(
                    tuple(value.destination for value in configurations)
                ),
                ExternalHttpSender(configurations, transport),
            ),
            signals,
        )
        if telemetry is None:
            await worker.run(stop)
        else:
            queue_signals = DeliveryQueueSignals(
                telemetry.meter_provider.get_meter("studymate.external")
            )
            resources.callback(queue_signals.close)
            async with asyncio.TaskGroup() as tasks:
                tasks.create_task(queue_signals.run(SqlDeliveryQueueReader(sessions), stop))
                tasks.create_task(worker.run(stop))


def _human_review_routers(
    configuration: AuthenticationConfiguration,
    sessions: async_sessionmaker[AsyncSession],
    auth_services: AuthenticationServices,
    fingerprinter: IntentFingerprinter,
) -> tuple[APIRouter, ...]:
    hasher = Sha256SessionHasher()
    photo = SqlPhotoReviewUnitOfWork(sessions, record_operator_audit, record_photo_review_event)
    reports = SqlReportModerationUnitOfWork(
        sessions, record_operator_audit, record_report_review_event
    )
    key = bytes.fromhex(configuration.envelope_key.get_secret_value())
    return (
        operator_photo_review_router(
            PhotoReviewHttpServices(
                ReadPhotoReviewContext(photo, hasher),
                ReviewPhoto(photo, hasher, fingerprinter),
                auth_services.signer,
                auth_services.browser,
            )
        ),
        own_photo_review_router(ReadOwnPhotoReview(SqlOwnPhotoReviewUnitOfWork(sessions), hasher)),
        report_moderation_router(
            ReportModerationHttpServices(
                ReviewReport(reports, hasher, fingerprinter),
                ReadReportReviewHistory(
                    reports, hasher, FernetReportReviewHistoryCursorCodec.from_key(key)
                ),
                auth_services.signer,
                auth_services.browser,
            )
        ),
    )


def _report_triage_router(
    configuration: AuthenticationConfiguration,
    ai: AiHttpConfiguration,
    sessions: async_sessionmaker[AsyncSession],
    auth_services: AuthenticationServices,
) -> APIRouter:
    # SAME dedicated admission pool2 and bounded deadline as student AI; never the core pool.
    policy = AdmissionPolicy(request_budget_seconds=ai.request_budget_seconds)
    unit = SqlOperatorReportTriageUnitOfWork(
        sessions, record_operator_audit, record_report_triage_submission, policy
    )
    hasher = Sha256SessionHasher()
    codec = FernetReportTriageSourceCodec.from_key(
        bytes.fromhex(configuration.envelope_key.get_secret_value())
    )
    fingerprinter = HmacIntentFingerprinter(
        bytes.fromhex(configuration.code_key.get_secret_value())
    )
    return operator_report_triage_router(
        OperatorReportTriageHttpServices(
            ReadReportTriageContext(unit, hasher, codec),
            EnqueueReportTriage(unit, hasher, fingerprinter, codec),
            ReadReportTriage(unit, hasher),
            auth_services.signer,
            auth_services.browser,
        )
    )
