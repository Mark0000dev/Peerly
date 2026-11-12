// Generated from enabled-auth FastAPI OpenAPI. Run npm run contracts:generate.
// Do not edit. Constraints such as string lengths remain server-validated.
export interface Api {
  readonly schemas: {
    readonly AcademicContextResponse: {
      readonly mode: Api['schemas']['DiscoveryMode'];
      readonly recipient_goal: Api['schemas']['GoalContextResponse'] | null;
      readonly recipient_help: Api['schemas']['HelpContextResponse'] | null;
      readonly sender_goal: Api['schemas']['GoalContextResponse'] | null;
      readonly sender_help: Api['schemas']['HelpContextResponse'] | null;
    };
    readonly AccountLinkResponse: {
      readonly id: string;
      readonly kind: Api['schemas']['OperatorAccountLinkKind'];
      readonly version: number | null;
    };
    readonly Action:
      | 'navigate'
      | 'submit'
      | 'retry'
      | 'cancel'
      | 'apply'
      | 'dismiss'
      | 'load_more'
      | 'upload'
      | 'permission_request'
      | 'open_settings';
    readonly ActionObserved: {
      readonly action: Api['schemas']['Action'];
      readonly action_id?: string | null;
      readonly header: Api['schemas']['ObservationHeader'];
      readonly outcome: Api['schemas']['ObservedOutcome'];
    };
    readonly ActionObservedBody: {
      readonly action: Api['schemas']['Action'];
      readonly action_id?: string | null;
      readonly event_id: string;
      readonly kind: 'action.observed';
      readonly observed_at: string;
      readonly outcome: Api['schemas']['ObservedOutcome'];
      readonly screen: Api['schemas']['Screen'];
    };
    readonly AiKind: 'clarify_goal' | 'suggest_subject' | 'assess_photo' | 'triage_report';
    readonly ApiRoute:
      | 'identity'
      | 'verification'
      | 'registration'
      | 'profile'
      | 'study'
      | 'discovery'
      | 'requests'
      | 'conversations'
      | 'media'
      | 'support'
      | 'notifications'
      | 'ai'
      | 'operator'
      | 'other';
    readonly AttemptSummary: {
      readonly attempt_no: number;
      readonly ended_at: string | null;
      readonly failure: Api['schemas']['FailureCode'] | null;
      readonly http_status: number | null;
      readonly late_ack_at: string | null;
      readonly late_message_id: number | null;
      readonly lease_expired: boolean;
      readonly lease_id: string;
      readonly outcome: Api['schemas']['ResultKind'] | null;
      readonly provider_message_id: number | null;
      readonly retry_after_seconds: number | null;
      readonly started_at: string;
    };
    readonly AvailableFeedbackSummaryResponse: {
      readonly maybe: number;
      readonly no: number;
      readonly publicly_visible: boolean;
      readonly responses: number;
      readonly state?: 'available';
      readonly yes: number;
    };
    readonly BanChangeResponse: {
      readonly account: Api['schemas']['BanReceiptState'];
      readonly changed: boolean;
      readonly representation?: 'committed_command_receipt_not_current_account_read';
      readonly revision: Api['schemas']['BanReceiptSource'] | null;
    };
    readonly BanReceiptSource: {
      readonly account_id: string;
      readonly banned: boolean;
      readonly changed_at: string;
      readonly id: string;
      readonly version: number;
    };
    readonly BanReceiptState: {
      readonly account_id: string;
      readonly banned_at: string | null;
      readonly deleted_at: string | null;
      readonly source_version: number;
    };
    readonly BlockStateResponse: {
      readonly blocked: boolean;
      readonly changed_at: string | null;
      readonly person_id: string;
      readonly version: number;
    };
    readonly BlockedPersonResponse: {
      readonly block: Api['schemas']['BlockStateResponse'];
      readonly deleted: boolean;
      readonly display_name: string | null;
    };
    readonly BuildingFeedbackSummaryResponse: {
      readonly publicly_visible: boolean;
      readonly responses: number;
      readonly state?: 'building';
    };
    readonly CancelledOperationResponse: {
      readonly cancelled_at: string;
      readonly client_message_id: string;
      readonly conversation_id: string;
      readonly operation_id: string;
      readonly outcome?: 'cancelled';
    };
    readonly CanonicalSource: {
      readonly actor_id: string;
      readonly facts: Api['schemas']['OperatorEventFacts'];
      readonly id: string;
      readonly kind: Api['schemas']['OperatorEventKind'];
      readonly membership_evidence?: Api['schemas']['MembershipEvidence'];
      readonly notification_mode?: Api['schemas']['NotificationMode'] | null;
      readonly occurred_at: string;
    };
    readonly CanonicalSubjectRequest: { readonly id: string; readonly kind: 'canonical' };
    readonly CanonicalSubjectResponse: {
      readonly id: string;
      readonly kind?: 'canonical';
      readonly label: string;
    };
    readonly CapabilitiesResponse: {
      readonly can_begin_onboarding: boolean;
      readonly can_use_student_features: boolean;
      readonly can_verify_student_email: boolean;
    };
    readonly CaptureMode: 'live' | 'backfill_umami';
    readonly CapturedSource: {
      readonly captured_at: string;
      readonly id: string;
      readonly kind: Api['schemas']['SourceKind'];
      readonly mode: Api['schemas']['CaptureMode'];
      readonly routing_version?: number;
      readonly source: Api['schemas']['SelectedSource'];
    };
    readonly ChallengeResponse: {
      readonly expires_at: string;
      readonly id: string;
      readonly resend_at: string;
    };
    readonly ChallengeState: 'active' | 'expired' | 'locked' | 'superseded' | 'consumed';
    readonly ChallengeStatusResponse: {
      readonly attempts_remaining: number;
      readonly can_resend: boolean;
      readonly can_verify: boolean;
      readonly delivery: Api['schemas']['EmailDeliveryState'];
      readonly email: string;
      readonly expires_at: string;
      readonly id: string;
      readonly resend_at: string;
      readonly state: Api['schemas']['ChallengeState'];
      readonly verification_outcome: Api['schemas']['VerificationOutcome'] | null;
    };
    readonly ChangeBanBody: { readonly banned: boolean; readonly reason: string };
    readonly ChangeBlockRequest: {
      readonly blocked: boolean;
      readonly context_id?: string | null;
      readonly expected_version: number;
    };
    readonly ChangePassRequest: {
      readonly context: Api['schemas']['DiscoveryContextBody'];
      readonly expected_version: number;
      readonly passed: boolean;
      readonly undo?: boolean;
    };
    readonly ChangeVisibilityRequest: {
      readonly expected_version: number;
      readonly hidden: boolean;
    };
    readonly ChatImageFailure:
      | 'invalid_image'
      | 'unsupported_format'
      | 'too_large'
      | 'dimensions_exceeded'
      | 'animated_image'
      | 'content_changed'
      | 'account_unavailable'
      | 'contact_unavailable'
      | 'storage_unavailable'
      | 'processing_unavailable';
    readonly ChatImageState:
      'uploading' | 'queued' | 'processing' | 'ready' | 'rejected' | 'cancelled' | 'expired';
    readonly ChatParticipantResponse: {
      readonly display_name: string | null;
      readonly person_id: string;
      readonly photo_version: number | null;
      readonly state: Api['schemas']['ChatParticipantState'];
    };
    readonly ChatParticipantState: 'available' | 'unavailable' | 'deleted';
    readonly ClarifyRequest: {
      readonly kind: 'clarify_goal';
      readonly source:
        Api['schemas']['ResourceSourceRequest'] | Api['schemas']['DraftSourceRequest'];
      readonly target?: Api['schemas']['GoalTextTarget'];
      readonly text: string;
    };
    readonly ClarifyResultResponse: { readonly suggestion: string };
    readonly ClientObservationSource: {
      readonly actor_id: string;
      readonly event: Api['schemas']['studymate__domain__client_observations__events__Observation'];
      readonly id: string;
      readonly received_at: string;
      readonly release_id: string | null;
    };
    readonly CompleteGoalRequest: { readonly expected_version: number; readonly goal_id: string };
    readonly CompleteRegistrationRequest: { readonly context_id: string };
    readonly ConfirmedDeletionResponse: {
      readonly deleted_at: string;
      readonly source_version: number;
      readonly state?: 'deleted';
      readonly workflow_id: string;
    };
    readonly ConfirmedOperationResponse: {
      readonly client_message_id: string;
      readonly conversation_id: string;
      readonly message: Api['schemas']['MessageResponse'];
      readonly operation_id: string;
      readonly outcome?: 'confirmed';
    };
    readonly ConnectedResponse: {
      readonly conversation_id: string;
      readonly outcome?: 'connected';
      readonly request_id: string;
    };
    readonly ConversationDetailsResponse: {
      readonly accepted_at: string;
      readonly accepted_request_version: number;
      readonly can_send: boolean;
      readonly conversation_id: string;
      readonly last_confirmed_sequence: number;
      readonly original_context: Api['schemas']['AcademicContextResponse'];
      readonly peer: Api['schemas']['ChatParticipantResponse'];
      readonly read_position: Api['schemas']['ConversationReadPositionResponse'] | null;
      readonly request_id: string;
      readonly unread_count: number;
    };
    readonly ConversationGoalShareBaselineResponse: {
      readonly accepted_request_version: number;
      readonly context: Api['schemas']['AcademicContextResponse'];
      readonly context_version?: 0;
      readonly recipient_goal_can_complete: boolean;
      readonly request_id: string;
      readonly sender_goal_can_complete: boolean;
    };
    readonly ConversationGoalShareEntryResponse: {
      readonly can_complete: boolean;
      readonly context_version: number;
      readonly conversation_id: string;
      readonly owner_id: string;
      readonly share_id: string;
      readonly shared_at: string;
      readonly source: Api['schemas']['SharedGoalSourceResponse'];
    };
    readonly ConversationGoalSharePageResponse: {
      readonly anchor_version: number;
      readonly baseline: Api['schemas']['ConversationGoalShareBaselineResponse'];
      readonly current_context_version: number;
      readonly history: readonly Api['schemas']['ConversationGoalShareEntryResponse'][];
      readonly latest: Api['schemas']['ConversationGoalShareEntryResponse'] | null;
      readonly next_cursor: string | null;
    };
    readonly ConversationGoalShareReceiptResponse: {
      readonly context_version: number;
      readonly conversation_id: string;
      readonly owner_id: string;
      readonly share_id: string;
      readonly shared_at: string;
      readonly source: Api['schemas']['SharedGoalSourceResponse'];
    };
    readonly ConversationListResponse: {
      readonly conversations: readonly Api['schemas']['ConversationSummaryResponse'][];
      readonly next_cursor: string | null;
    };
    readonly ConversationReadPositionBody: { readonly through_sequence: number };
    readonly ConversationReadPositionResponse: {
      readonly acknowledged_at: string;
      readonly conversation_id: string;
      readonly through_sequence: number;
      readonly version: number;
    };
    readonly ConversationSummaryResponse: {
      readonly accepted_at: string;
      readonly activity_at: string;
      readonly can_send: boolean;
      readonly conversation_id: string;
      readonly last_message: Api['schemas']['MessageResponse'] | null;
      readonly original_context: Api['schemas']['AcademicContextResponse'];
      readonly peer: Api['schemas']['ChatParticipantResponse'];
      readonly request_id: string;
      readonly unread_count: number;
    };
    readonly CurrentPhotoResponse: {
      readonly display_url: string;
      readonly upload_id: string;
      readonly version: number;
    };
    readonly CustomSubjectRequest: { readonly kind: 'custom'; readonly label: string };
    readonly CustomSubjectResponse: { readonly kind?: 'custom'; readonly label: string };
    readonly DeleteAccountBody: { readonly workflow_id: string };
    readonly DeletionPreparationBody: Readonly<Record<string, never>>;
    readonly DeletionPreparationResponse: {
      readonly expires_at: string;
      readonly workflow_id: string;
    };
    readonly DeletionReceiptResponse: {
      readonly deleted_at: string;
      readonly source_version: number;
      readonly workflow_id: string;
    };
    readonly DeliveryState: 'pending' | 'leased' | 'retry' | 'succeeded' | 'dead';
    readonly DeliverySummary: {
      readonly attempts: readonly Api['schemas']['AttemptSummary'][];
      readonly created_at: string;
      readonly delivered_at: string | null;
      readonly destination_revision: number | null;
      readonly id: string;
      readonly last_failure: Api['schemas']['FailureCode'] | null;
      readonly lease_until: string | null;
      readonly next_attempt_at: string;
      readonly projection_version: number;
      readonly provider_message_id: number | null;
      readonly sink: Api['schemas']['Sink'];
      readonly state: Api['schemas']['DeliveryState'];
      readonly updated_at: string;
    };
    readonly DiscoveryCardResponse: {
      readonly about: string | null;
      readonly display_name: string;
      readonly id: string;
      readonly own_pass: Api['schemas']['PrivatePassResponse'];
      readonly photo: Api['schemas']['PublicPhotoResponse'];
      readonly relevance: Api['schemas']['DiscoveryRelevanceResponse'];
      readonly version: number;
    };
    readonly DiscoveryContextBody:
      | Api['schemas']['FindHelpContext']
      | Api['schemas']['OfferHelpContext']
      | Api['schemas']['StudyTogetherContext'];
    readonly DiscoveryEmptyReason:
      'context_required' | 'no_relevant_people' | 'exhausted' | 'no_available_passed_people';
    readonly DiscoveryExposureResponse: {
      readonly can_confirm: boolean;
      readonly paused: boolean;
      readonly requirements: readonly Api['schemas']['RestoreRequirement'][];
    };
    readonly DiscoveryMode: 'find_help' | 'offer_help' | 'study_together';
    readonly DiscoveryPageResponse: {
      readonly context: Api['schemas']['DiscoveryContextBody'] | null;
      readonly empty_reason: Api['schemas']['DiscoveryEmptyReason'] | null;
      readonly next_cursor: string | null;
      readonly people: readonly Api['schemas']['DiscoveryCardResponse'][];
      readonly undo_pass: Api['schemas']['PrivatePassResponse'] | null;
    };
    readonly DiscoveryRelevanceResponse: {
      readonly reason: Api['schemas']['RelevanceReason'];
      readonly reciprocal_subject_id: string | null;
      readonly reciprocal_subject_label: string | null;
      readonly same_topic: boolean;
      readonly subject_id: string;
      readonly subject_label: string;
      readonly topic: string | null;
    };
    readonly DiscoveryView: 'candidates' | 'passed';
    readonly DraftSourceRequest: {
      readonly id: string;
      readonly kind: 'draft';
      readonly version: number;
    };
    readonly DraftSourceResponse: {
      readonly content_hash: string;
      readonly id: string;
      readonly kind?: 'draft';
      readonly version: number;
    };
    readonly EmailDeliveryState: 'queued' | 'sending' | 'sent' | 'failed' | 'cancelled';
    readonly ErrorCategory:
      'network' | 'http' | 'timeout' | 'offline' | 'javascript' | 'render' | 'resource' | 'unknown';
    readonly ErrorObserved: {
      readonly category: Api['schemas']['ErrorCategory'];
      readonly frames?: readonly Api['schemas']['PublicFrame'][];
      readonly header: Api['schemas']['ObservationHeader'];
    };
    readonly ErrorObservedBody: {
      readonly category: Api['schemas']['ErrorCategory'];
      readonly event_id: string;
      readonly frames?: readonly Api['schemas']['PublicFrameBody'][];
      readonly kind: 'error.observed';
      readonly observed_at: string;
      readonly screen: Api['schemas']['Screen'];
    };
    readonly ExpectedImageSource: {
      readonly content_type: Api['schemas']['PhotoContentType'];
      readonly sha256: string;
      readonly size: number;
    };
    readonly ExposureResponse: {
      readonly confirmed_at: string;
      readonly inactivity_seconds: number;
      readonly last_activity_at: string;
      readonly paused_at: string | null;
    };
    readonly Failure:
      | 'transient'
      | 'invalid_output'
      | 'invalid_input'
      | 'timeout'
      | 'auth_unavailable'
      | 'rate_limited'
      | 'account_unavailable'
      | 'stale_source'
      | 'executor_lost';
    readonly FailureCode:
      | 'transient'
      | 'rate_limited'
      | 'credentials_unavailable'
      | 'destination_unavailable'
      | 'invalid_response'
      | 'timeout'
      | 'lease_expired'
      | 'cancelled'
      | 'permanent';
    readonly FeedbackBody: {
      readonly again: Api['schemas']['StudyAgain'];
      readonly descriptors?: readonly Api['schemas']['FeedbackDescriptor'][];
      readonly expected_version: number;
      readonly team_note?: string | null;
    };
    readonly FeedbackDescriptor: 'easy_to_communicate' | 'prepared' | 'supportive';
    readonly FeedbackPublication: 'private_only' | 'eligible' | 'removed';
    readonly FeedbackReceiptResponse: {
      readonly again: Api['schemas']['StudyAgain'];
      readonly captured_public_eligibility: boolean;
      readonly changed_at: string;
      readonly conversation_id: string;
      readonly descriptors: readonly Api['schemas']['FeedbackDescriptor'][];
      readonly id: string;
      readonly team_note: string | null;
      readonly version: number;
      readonly worked_outcome_id: string;
      readonly worked_outcome_version: number;
    };
    readonly FieldProblemResponse: { readonly code: string; readonly path: readonly string[] };
    readonly FindHelpContext: {
      readonly goal_id: string;
      readonly goal_version: number;
      readonly mode: 'find_help';
    };
    readonly GoalContextResponse: {
      readonly context: string | null;
      readonly goal_id: string;
      readonly owner_id: string;
      readonly shared_learning: boolean;
      readonly subject_id: string;
      readonly subject_label: string;
      readonly topic: string | null;
      readonly version: number;
    };
    readonly GoalResponse: {
      readonly completed_at: string | null;
      readonly context: string | null;
      readonly created_at: string;
      readonly id: string;
      readonly shared_learning: boolean;
      readonly subject:
        Api['schemas']['CanonicalSubjectResponse'] | Api['schemas']['CustomSubjectResponse'];
      readonly topic: string | null;
      readonly updated_at: string;
      readonly version: number;
    };
    readonly GoalTextTarget: 'context' | 'topic';
    readonly GoogleLinkResponse: {
      readonly created_at: string;
      readonly id: string;
      readonly issuer: string;
      readonly subject: string;
    };
    readonly HelpContextResponse: {
      readonly owner_id: string;
      readonly subject_id: string;
      readonly subject_label: string;
      readonly topic_note: string | null;
      readonly version: number;
    };
    readonly HelpResponse: {
      readonly saved_at: string;
      readonly subjects: readonly Api['schemas']['HelpSubjectResponse'][];
      readonly version: number;
    };
    readonly HelpSubjectRequest: {
      readonly subject_id: string;
      readonly topic_note?: string | null;
    };
    readonly HelpSubjectResponse: {
      readonly label: string;
      readonly subject_id: string;
      readonly topic_note: string | null;
    };
    readonly HttpMethod: 'GET' | 'HEAD' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'OPTIONS';
    readonly HttpObserved: {
      readonly action_id?: string | null;
      readonly duration_ms: number;
      readonly header: Api['schemas']['ObservationHeader'];
      readonly method: Api['schemas']['HttpMethod'];
      readonly request_id?: string | null;
      readonly route: Api['schemas']['ApiRoute'];
      readonly status_class: Api['schemas']['StatusClass'];
      readonly trace_id?: string | null;
    };
    readonly HttpObservedBody: {
      readonly action_id?: string | null;
      readonly duration_ms: number;
      readonly event_id: string;
      readonly kind: 'http.observed';
      readonly method: Api['schemas']['HttpMethod'];
      readonly observed_at: string;
      readonly request_id?: string | null;
      readonly route: Api['schemas']['ApiRoute'];
      readonly screen: Api['schemas']['Screen'];
      readonly status_class: Api['schemas']['StatusClass'];
      readonly trace_id?: string | null;
    };
    readonly IdentityResponse: {
      readonly account_id: string;
      readonly account_status: 'active' | 'banned';
      readonly capabilities: Api['schemas']['CapabilitiesResponse'];
      readonly csrf_token: string;
      readonly email_challenge_id: string | null;
      readonly membership_status: 'unverified' | 'verified' | 'revoked';
      readonly registration: Api['schemas']['RegistrationReceiptResponse'] | null;
      readonly verified_at: string | null;
    };
    readonly ImagePreparationReceipt: {
      readonly client_message_id: string;
      readonly conversation_id: string;
      readonly image_id: string;
      readonly receipt_state: Api['schemas']['ChatImageState'];
      readonly receipt_version: number;
    };
    readonly ImagePreparationResponse: {
      readonly client_message_id: string;
      readonly conversation_id: string;
      readonly created_at: string;
      readonly display: Api['schemas']['ReadyImageMetadata'] | null;
      readonly expected_source: Api['schemas']['ExpectedImageSource'];
      readonly failure: Api['schemas']['ChatImageFailure'] | null;
      readonly image_id: string;
      readonly message_outcome: Api['schemas']['PreparationMessageOutcome'] | null;
      readonly processing_expires_at: string;
      readonly source_state: Api['schemas']['ChatImageState'];
      readonly source_version: number;
      readonly state: Api['schemas']['ChatImageState'];
      readonly updated_at: string;
      readonly upload_expires_at: string;
    };
    readonly ImagePreparationsResponse: {
      readonly preparations: readonly Api['schemas']['ImagePreparationResponse'][];
    };
    readonly ImageUploadAccessResponse: {
      readonly fields: Readonly<Record<string, string>>;
      readonly url: string;
    };
    readonly JobResponse: {
      readonly created_at: string;
      readonly deadline: string;
      readonly failure: Api['schemas']['Failure'] | null;
      readonly id: string;
      readonly kind: 'clarify_goal' | 'suggest_subject' | 'assess_photo';
      readonly poll_after_ms: number | null;
      readonly result:
        | Api['schemas']['ClarifyResultResponse']
        | Api['schemas']['SubjectResultResponse']
        | Api['schemas']['PhotoResultResponse']
        | null;
      readonly source:
        Api['schemas']['ResourceSourceResponse'] | Api['schemas']['DraftSourceResponse'];
      readonly state: Api['schemas']['JobState'];
      readonly target: Api['schemas']['GoalTextTarget'] | null;
    };
    readonly JobState: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'expired';
    readonly LanguageOptionResponse: { readonly code: string; readonly label: string };
    readonly LifecycleOperation: 'ban' | 'unban' | 'delete';
    readonly LifecycleResponse: {
      readonly changed_at: string;
      readonly completed_at: string;
      readonly hidden_at: string | null;
      readonly visibility_version: number;
    };
    readonly ManualMembershipBody: {
      readonly expected_challenge_id: string;
      readonly expected_email: string;
      readonly expected_google_identity_id: string;
    };
    readonly ManualMembershipContextResponse: {
      readonly account_id: string;
      readonly block: Api['schemas']['ManualVerificationBlock'] | null;
      readonly google_identity_id: string | null;
      readonly manual_verification: Api['schemas']['ManualMembershipResponse'] | null;
      readonly submitted: Api['schemas']['SubmittedInstitutionalEmailResponse'] | null;
    };
    readonly ManualMembershipResponse: {
      readonly account_id: string;
      readonly activation_granted?: false;
      readonly actor_session_id: string;
      readonly challenge_id: string;
      readonly event_id: string;
      readonly google_identity_id: string;
      readonly id: string;
      readonly operator_access_version: number;
      readonly operator_id: string;
      readonly otp_consumed?: false;
      readonly proof?: 'manual_operator_attestation';
      readonly verified_at: string;
    };
    readonly ManualVerificationBlock:
      | 'account_unavailable'
      | 'account_restricted'
      | 'google_identity_required'
      | 'membership_already_bound'
      | 'no_submitted_email'
      | 'challenge_not_pending'
      | 'staging_placeholder_not_allowed';
    readonly MembershipEvidence:
      'not_applicable' | 'otp' | 'manual_placeholder' | 'manual_challenge' | 'unknown';
    readonly MembershipResponse: {
      readonly email: string;
      readonly revoked_at: string | null;
      readonly verified_at: string;
    };
    readonly MessageHistoryResponse: {
      readonly anchor_sequence: number;
      readonly messages: readonly Api['schemas']['MessageResponse'][];
      readonly next_cursor: string | null;
    };
    readonly MessageImageReportContextResponse: {
      readonly conversation_id: string;
      readonly id: string;
      readonly image_id: string;
      readonly issued_at: string;
      readonly kind?: 'message_image';
      readonly message_id: string;
    };
    readonly MessageImageReportReceipt: {
      readonly context_id: string;
      readonly id: string;
      readonly kind?: 'message_image';
      readonly submitted_at: string;
    };
    readonly MessageImageReportRequest: {
      readonly category: Api['schemas']['ReportCategory'];
      readonly comment?: string | null;
      readonly context_id: string;
      readonly kind: 'message_image';
    };
    readonly MessageOutcome: 'confirmed' | 'cancelled';
    readonly MessageResponse: {
      readonly author_id: string;
      readonly client_message_id: string;
      readonly conversation_id: string;
      readonly image_id: string | null;
      readonly message_id: string;
      readonly sent_at: string;
      readonly sequence: number;
      readonly text: string | null;
    };
    readonly Metric: 'route_ready' | 'lcp' | 'inp' | 'fcp' | 'ttfb' | 'cls';
    readonly NoStudyPromptResponse: { readonly outcome?: 'no_offer' };
    readonly NotificationMode: 'messages_and_requests' | 'all_updates';
    readonly ObservationBatchBody: {
      readonly events: readonly Api['schemas']['ObservationBody'][];
      readonly expected_actor_id?: string | null;
      readonly release_id?: string | null;
      readonly schema_version: 1;
    };
    readonly ObservationBatchResponse: {
      readonly accepted: readonly string[];
      readonly duplicates: readonly string[];
      readonly received_at: string;
      readonly schema_version?: 1;
    };
    readonly ObservationBody:
      | Api['schemas']['ScreenViewedBody']
      | Api['schemas']['ActionObservedBody']
      | Api['schemas']['PerformanceObservedBody']
      | Api['schemas']['ErrorObservedBody']
      | Api['schemas']['HttpObservedBody']
      | Api['schemas']['QualityObservedBody'];
    readonly ObservationHeader: {
      readonly event_id: string;
      readonly observed_at: string;
      readonly screen: Api['schemas']['Screen'];
    };
    readonly ObservedOutcome:
      | 'invoked'
      | 'succeeded_observed'
      | 'rejected_observed'
      | 'failed_observed'
      | 'cancelled_observed'
      | 'unknown';
    readonly OfferHelpContext: { readonly help_version: number; readonly mode: 'offer_help' };
    readonly OfferedStudyPromptResponse: {
      readonly conversation_id: string;
      readonly offered_at: string;
      readonly outcome?: 'offered';
      readonly receipt_id: string;
    };
    readonly OnboardingRequirement: 'display_name' | 'photo' | 'study_goal' | 'help_subjects';
    readonly OnboardingStatusResponse: {
      readonly capabilities: Api['schemas']['ProfileCapabilitiesResponse'];
      readonly discovery_exposure: Api['schemas']['DiscoveryExposureResponse'] | null;
      readonly registered: boolean;
      readonly restore_requirements: readonly Api['schemas']['RestoreRequirement'][];
      readonly setup_complete: boolean;
      readonly setup_requirements: readonly Api['schemas']['OnboardingRequirement'][];
      readonly visibility: Api['schemas']['ProfileVisibilityResponse'] | null;
    };
    readonly OnboardingTask: 'find_help' | 'offer_help';
    readonly OperatorAccountDetailResponse: {
      readonly account: Api['schemas']['OperatorAccountResponse'];
      readonly exposure: Api['schemas']['ExposureResponse'] | null;
      readonly goal: Api['schemas']['GoalResponse'] | null;
      readonly help_subjects: Api['schemas']['HelpResponse'] | null;
      readonly lifecycle: Api['schemas']['LifecycleResponse'] | null;
      readonly links: readonly Api['schemas']['AccountLinkResponse'][];
      readonly photo: Api['schemas']['PhotoReferenceResponse'] | null;
      readonly profile: Api['schemas']['ProfileRevisionResponse'] | null;
      readonly registration: Api['schemas']['RegistrationReceiptResponse'] | null;
    };
    readonly OperatorAccountLifecycle: 'all' | 'active' | 'banned' | 'deleted';
    readonly OperatorAccountLinkKind:
      | 'google_identity'
      | 'profile_revision'
      | 'photo_revision'
      | 'goal_revision'
      | 'help_revision'
      | 'registration_receipt';
    readonly OperatorAccountResponse: {
      readonly account_id: string;
      readonly banned_at: string | null;
      readonly created_at: string;
      readonly deleted_at: string | null;
      readonly display_name: string | null;
      readonly google_link: Api['schemas']['GoogleLinkResponse'] | null;
      readonly hidden_at: string | null;
      readonly membership: Api['schemas']['MembershipResponse'] | null;
      readonly profile_version: number | null;
    };
    readonly OperatorAccountsResponse: {
      readonly accounts: readonly Api['schemas']['OperatorAccountResponse'][];
      readonly next_cursor: string | null;
    };
    readonly OperatorAction:
      | 'search_accounts'
      | 'search_events'
      | 'search_audits'
      | 'search_reports'
      | 'search_support_cases'
      | 'search_delivery_sources'
      | 'read_delivery_source'
      | 'read_support_case'
      | 'read_report'
      | 'read_media'
      | 'read_chat_media'
      | 'read_event'
      | 'read_audit'
      | 'read_account'
      | 'read_conversation_messages';
    readonly OperatorAiAttemptOutcome:
      | 'succeeded'
      | 'failed'
      | 'cancelled'
      | 'expired'
      | 'transient'
      | 'invalid_output'
      | 'invalid_input'
      | 'timeout'
      | 'auth_unavailable'
      | 'rate_limited'
      | 'account_unavailable'
      | 'stale_source'
      | 'executor_lost';
    readonly OperatorAiAttemptResponse: {
      readonly ended_at: string | null;
      readonly job_id: string;
      readonly number: number;
      readonly outcome: Api['schemas']['OperatorAiAttemptOutcome'] | null;
      readonly started_at: string;
    };
    readonly OperatorAiJobResponse: {
      readonly attempt_observation?: 'current_recorded_not_job_snapshot';
      readonly attempts_current: readonly Api['schemas']['OperatorAiAttemptResponse'][];
      readonly input_digest_hex: string;
      readonly input_json_raw: string;
      readonly job: Api['schemas']['OperatorAiMetadataResponse'];
      readonly observed_at: string;
      readonly representation?: 'raw_stored_text_not_current_task_schema';
      readonly result_json_raw: string | null;
    };
    readonly OperatorAiJobsResponse: {
      readonly account_id: string;
      readonly anchor_created_at: string | null;
      readonly anchor_job_id: string | null;
      readonly jobs: readonly Api['schemas']['OperatorAiMetadataResponse'][];
      readonly next_cursor: string | null;
      readonly observed_at: string;
      readonly pagination?: 'anchored_search_not_commit_order';
    };
    readonly OperatorAiMetadataResponse: {
      readonly account_id: string;
      readonly attempts_count: number;
      readonly created_at: string;
      readonly deadline: string;
      readonly failure: Api['schemas']['Failure'] | null;
      readonly id: string;
      readonly kind: Api['schemas']['AiKind'];
      readonly not_before: string;
      readonly origin: Api['schemas']['OperatorEventOriginResponse'];
      readonly source_id: string;
      readonly source_version: number;
      readonly state: Api['schemas']['JobState'];
      readonly versions: Api['schemas']['OperatorAiVersionsResponse'];
    };
    readonly OperatorAiVersionsResponse: {
      readonly adapter: string;
      readonly model: string;
      readonly prompt_version: string;
      readonly schema_version: string;
    };
    readonly OperatorAuditDetailResponse: {
      readonly action: Api['schemas']['OperatorAction'];
      readonly actual_source_image_id: string | null;
      readonly actual_source_upload_id: string | null;
      readonly id: string;
      readonly occurred_at: string;
      readonly operator_access_changed_at: string;
      readonly operator_access_version: number;
      readonly operator_id: string;
      readonly origin: Api['schemas']['OperatorEventOriginResponse'];
      readonly outcome: Api['schemas']['OperatorAuditOutcome'];
      readonly query_fingerprinted: boolean;
      readonly requested_chat_attempt_id: string | null;
      readonly requested_chat_kind: Api['schemas']['OperatorChatMediaKind'] | null;
      readonly requested_chat_owner_id: string | null;
      readonly requested_id: string | null;
      readonly requested_kind: Api['schemas']['OperatorResourceKind'] | null;
      readonly requested_media_attempt_id: string | null;
      readonly requested_media_kind: Api['schemas']['OperatorProfileMediaKind'] | null;
      readonly requested_media_owner_id: string | null;
      readonly results: readonly Api['schemas']['OperatorAuditResultRefResponse'][];
    };
    readonly OperatorAuditOutcome: 'search' | 'read' | 'not_found';
    readonly OperatorAuditResultRefResponse: {
      readonly id: string;
      readonly kind: Api['schemas']['OperatorResourceKind'];
    };
    readonly OperatorAuditsResponse: {
      readonly audits: readonly Api['schemas']['OperatorAuditDetailResponse'][];
      readonly next_cursor: string | null;
      readonly search_anchor_at: string;
    };
    readonly OperatorBlockHistoryAnchorsResponse: {
      readonly high_version: number;
      readonly low_version: number;
    };
    readonly OperatorBlockHistoryResponse: {
      readonly account_id: string;
      readonly anchors: Api['schemas']['OperatorBlockHistoryAnchorsResponse'];
      readonly current_heads: readonly Api['schemas']['OperatorBlockRevisionResponse'][];
      readonly high_id: string;
      readonly low_id: string;
      readonly next_cursor: string | null;
      readonly relationship_id: string;
      readonly revisions: readonly Api['schemas']['OperatorBlockRevisionResponse'][];
    };
    readonly OperatorBlockRevisionResponse: {
      readonly blocked: boolean;
      readonly blocker_id: string;
      readonly changed_at: string;
      readonly high_id: string;
      readonly low_id: string;
      readonly relationship_id: string;
      readonly target_id: string;
      readonly version: number;
    };
    readonly OperatorChatImageAttemptOutcome:
      'processing' | 'ready' | 'retry' | 'rejected' | 'stale' | 'interrupted';
    readonly OperatorChatImageAttemptResponse: {
      readonly display_height: number | null;
      readonly display_sha256: string | null;
      readonly display_size: number | null;
      readonly display_width: number | null;
      readonly failure: Api['schemas']['ChatImageFailure'] | null;
      readonly finished_at: string | null;
      readonly id: string;
      readonly image_id: string;
      readonly lease_until: string;
      readonly next_attempt_at: string | null;
      readonly number: number;
      readonly outcome: Api['schemas']['OperatorChatImageAttemptOutcome'];
      readonly started_at: string;
    };
    readonly OperatorChatImageHistoryResponse: {
      readonly anchor_version: number;
      readonly attempt_observation?: 'current_recorded_not_revision_time';
      readonly attempts_current: readonly Api['schemas']['OperatorChatImageAttemptResponse'][];
      readonly matching_client_operation:
        Api['schemas']['OperatorChatImageMatchingOperationResponse'] | null;
      readonly next_cursor: string | null;
      readonly observed_at: string;
      readonly operation_observation?: 'current_matching_client_id_no_attachment_proof';
      readonly revisions: readonly Api['schemas']['OperatorChatImageRevisionResponse'][];
      readonly root_observation?: 'current_recorded_not_revision_time';
      readonly upload: Api['schemas']['OperatorChatImageRootResponse'];
    };
    readonly OperatorChatImageMatchingOperationResponse: {
      readonly author_id: string;
      readonly cancelled_at: string | null;
      readonly client_message_id: string;
      readonly conversation_id: string;
      readonly id: string;
      readonly message_id: string | null;
      readonly state: Api['schemas']['MessageOutcome'];
    };
    readonly OperatorChatImageRevisionResponse: {
      readonly account_id: string;
      readonly attempt_id: string | null;
      readonly client_message_id: string;
      readonly conversation_id: string;
      readonly failure: Api['schemas']['ChatImageFailure'] | null;
      readonly image_id: string;
      readonly ready_attempt_outcome: Api['schemas']['OperatorChatImageAttemptOutcome'] | null;
      readonly state: Api['schemas']['ChatImageState'];
      readonly updated_at: string;
      readonly version: number;
    };
    readonly OperatorChatImageRootResponse: {
      readonly account_id: string;
      readonly client_message_id: string;
      readonly conversation_id: string;
      readonly created_at: string;
      readonly current_revision: Api['schemas']['OperatorChatImageRevisionResponse'];
      readonly current_version: number;
      readonly high_id: string;
      readonly id: string;
      readonly low_id: string;
      readonly processing_expires_at: string;
      readonly source_content_type: string;
      readonly source_metadata?: 'declared_not_object_verified';
      readonly source_sha256: string;
      readonly source_size: number;
      readonly upload_expires_at: string;
    };
    readonly OperatorChatImageUploadsResponse: {
      readonly account_id: string;
      readonly anchor_created_at: string | null;
      readonly anchor_image_id: string | null;
      readonly next_cursor: string | null;
      readonly observed_at: string;
      readonly pagination?: 'anchored_search_not_commit_order';
      readonly uploads: readonly Api['schemas']['OperatorChatImageRootResponse'][];
    };
    readonly OperatorChatMediaKind: 'original' | 'display';
    readonly OperatorConversationSummaryResponse: {
      readonly accepted_request_version: number;
      readonly high_id: string;
      readonly id: string;
      readonly low_id: string;
      readonly relationship_id: string;
      readonly request_id: string;
    };
    readonly OperatorConversationsResponse: {
      readonly account_id: string;
      readonly conversations: readonly Api['schemas']['OperatorConversationSummaryResponse'][];
      readonly next_cursor: string | null;
    };
    readonly OperatorDisclosuresResponse: {
      readonly account_id: string;
      readonly ack_scope?: 'CURRENT_ACK_ROWS_FOR_PAGE_ONLY';
      readonly acknowledgements: readonly Api['schemas']['OperatorRequestAcknowledgementResponse'][];
      readonly anchor_created_at: string | null;
      readonly anchor_disclosure_id: string | null;
      readonly disclosure_representation?: 'technical_disclosure_not_ack';
      readonly disclosures: readonly Api['schemas']['OperatorRetainedDisclosureResponse'][];
      readonly next_cursor: string | null;
      readonly observed_at: string;
      readonly pagination?: 'anchored_search_not_commit_order';
      readonly request: Api['schemas']['OperatorRequestRootResponse'];
      readonly root_observation?: 'current_recorded_not_revision_snapshot';
    };
    readonly OperatorEventFacts: {
      readonly ai_kind?: Api['schemas']['AiKind'] | null;
      readonly ai_reason?: Api['schemas']['Failure'] | null;
      readonly ai_state?: Api['schemas']['JobState'] | null;
      readonly blocked?: boolean | null;
      readonly feedback_again?: Api['schemas']['StudyAgain'] | null;
      readonly lifecycle_operation?: Api['schemas']['LifecycleOperation'] | null;
      readonly message_state?: Api['schemas']['MessageOutcome'] | null;
      readonly onboarding_task?: Api['schemas']['OnboardingTask'] | null;
      readonly operator_action?: Api['schemas']['OperatorAction'] | null;
      readonly passed?: boolean | null;
      readonly request_state?: Api['schemas']['RequestState'] | null;
      readonly shared_learning?: boolean | null;
      readonly study_answer?: Api['schemas']['StudyAnswer'] | null;
      readonly topic_present?: boolean | null;
    };
    readonly OperatorEventFactsResponse: {
      readonly ai_kind: Api['schemas']['AiKind'] | null;
      readonly ai_reason: Api['schemas']['Failure'] | null;
      readonly ai_state: Api['schemas']['JobState'] | null;
      readonly blocked: boolean | null;
      readonly feedback_again: Api['schemas']['StudyAgain'] | null;
      readonly lifecycle_operation: Api['schemas']['LifecycleOperation'] | null;
      readonly message_state: Api['schemas']['MessageOutcome'] | null;
      readonly onboarding_task: Api['schemas']['OnboardingTask'] | null;
      readonly operator_action: Api['schemas']['OperatorAction'] | null;
      readonly passed: boolean | null;
      readonly request_state: Api['schemas']['RequestState'] | null;
      readonly shared_learning: boolean | null;
      readonly study_answer: Api['schemas']['StudyAnswer'] | null;
      readonly topic_present: boolean | null;
    };
    readonly OperatorEventKind:
      | 'account.lifecycle_changed'
      | 'goal.saved'
      | 'goal.completed'
      | 'profile.saved'
      | 'help.saved'
      | 'photo.published'
      | 'profile.ready'
      | 'profile.hidden'
      | 'profile.restored'
      | 'auth.email_confirmed'
      | 'ai_job.completed'
      | 'discovery.exposure_confirmed'
      | 'report.created'
      | 'report.reviewed'
      | 'triage.submitted'
      | 'photo.reviewed'
      | 'block.changed'
      | 'discovery.pass_changed'
      | 'request.changed'
      | 'request.view_acknowledged'
      | 'message.confirmed'
      | 'message.cancelled'
      | 'conversation.read_acknowledged'
      | 'conversation.goal_shared'
      | 'operator.inspected'
      | 'study.reported'
      | 'feedback.saved'
      | 'study.prompt_offered'
      | 'notification_preference.changed'
      | 'support.received'
      | 'support.status_changed';
    readonly OperatorEventOriginResponse: {
      readonly action_id: string | null;
      readonly http_request_id: string | null;
      readonly span_id: string | null;
      readonly trace_id: string | null;
    };
    readonly OperatorEventResponse: {
      readonly facts: Api['schemas']['OperatorEventFactsResponse'];
      readonly id: string;
      readonly initiator_account_id: string | null;
      readonly kind: Api['schemas']['OperatorEventKind'];
      readonly occurred_at: string;
      readonly origin: Api['schemas']['OperatorEventOriginResponse'];
      readonly schema_version?: 1;
      readonly sources: readonly Api['schemas']['OperatorEventSourceResponse'][];
      readonly subject_account_id: string;
    };
    readonly OperatorEventSourceResponse: {
      readonly conversation_id: string | null;
      readonly id: string;
      readonly kind: Api['schemas']['OperatorSourceKind'];
      readonly operator_access_version: number | null;
      readonly owner_id: string | null;
      readonly related_account_id: string | null;
      readonly version: number | null;
    };
    readonly OperatorEventsResponse: {
      readonly events: readonly Api['schemas']['OperatorEventResponse'][];
      readonly next_cursor: string | null;
      readonly pagination?: 'anchored_search_not_commit_order';
      readonly search_anchor_at: string;
    };
    readonly OperatorFeedbackDirection: 'given' | 'received';
    readonly OperatorFeedbackHistoryResponse: {
      readonly anchor_version: number;
      readonly feedback: Api['schemas']['OperatorFeedbackRootResponse'];
      readonly next_cursor: string | null;
      readonly observed_at: string;
      readonly revisions: readonly Api['schemas']['OperatorFeedbackRevisionResponse'][];
      readonly root_observation?: 'current_recorded_not_revision_snapshot';
    };
    readonly OperatorFeedbackRemovalResponse: {
      readonly feedback_id: string;
      readonly id: string;
      readonly kind: string;
      readonly operator_access_active: boolean;
      readonly operator_access_version: number;
      readonly operator_id: string;
      readonly origin: Api['schemas']['OperatorEventOriginResponse'];
      readonly reason: string;
      readonly removed_at: string;
      readonly source_version: number;
    };
    readonly OperatorFeedbackRemovalsResponse: {
      readonly anchor_removal_id: string | null;
      readonly anchor_removed_at: string | null;
      readonly feedback: Api['schemas']['OperatorFeedbackRootResponse'];
      readonly next_cursor: string | null;
      readonly observed_at: string;
      readonly pagination?: 'anchored_search_not_commit_order';
      readonly removals: readonly Api['schemas']['OperatorFeedbackRemovalResponse'][];
      readonly root_observation?: 'current_recorded_not_revision_snapshot';
    };
    readonly OperatorFeedbackRevisionResponse: {
      readonly again: string;
      readonly changed_at: string;
      readonly conversation_id: string;
      readonly descriptors: readonly string[];
      readonly feedback_id: string;
      readonly high_id: string;
      readonly high_message_id: string | null;
      readonly low_id: string;
      readonly low_message_id: string | null;
      readonly origin: Api['schemas']['OperatorEventOriginResponse'];
      readonly partner_id: string;
      readonly representation?: 'raw_recorded_feedback_not_current_content_decoder';
      readonly reviewer_id: string;
      readonly team_note: string | null;
      readonly version: number;
      readonly worked_answer: string;
      readonly worked_confirmation_id: string;
    };
    readonly OperatorFeedbackRootResponse: {
      readonly conversation_id: string;
      readonly current_changed_at: string;
      readonly current_removal_id: string | null;
      readonly current_version: number;
      readonly high_id: string;
      readonly id: string;
      readonly low_id: string;
      readonly partner_id: string;
      readonly removal_reference?: 'pointer_not_all_history';
      readonly reviewer_id: string;
    };
    readonly OperatorFeedbackRootsResponse: {
      readonly account_id: string;
      readonly anchor_changed_at: string | null;
      readonly anchor_feedback_id: string | null;
      readonly feedback: readonly Api['schemas']['OperatorFeedbackRootResponse'][];
      readonly next_cursor: string | null;
      readonly observed_at: string;
      readonly pagination?: 'current_pointer_anchored_search_not_creation_or_commit_snapshot';
    };
    readonly OperatorGoalHistoryResponse: {
      readonly anchor_version: number;
      readonly goal: Api['schemas']['OperatorGoalRootResponse'];
      readonly next_cursor: string | null;
      readonly observed_at: string;
      readonly revisions: readonly Api['schemas']['OperatorGoalRevisionResponse'][];
    };
    readonly OperatorGoalRevisionResponse: {
      readonly account_id: string;
      readonly completed_at: string | null;
      readonly context: string | null;
      readonly goal_id: string;
      readonly saved_at: string;
      readonly shared_learning: boolean;
      readonly subject_id: string | null;
      readonly subject_label: string;
      readonly topic: string | null;
      readonly topic_match_key: string | null;
      readonly version: number;
    };
    readonly OperatorGoalRootResponse: {
      readonly account_id: string;
      readonly completed_at: string | null;
      readonly created_at: string;
      readonly current_version: number;
      readonly id: string;
    };
    readonly OperatorGoalState: 'active' | 'completed';
    readonly OperatorGoalsResponse: {
      readonly account_id: string;
      readonly anchor_created_at: string | null;
      readonly anchor_goal_id: string | null;
      readonly goals: readonly Api['schemas']['OperatorGoalRootResponse'][];
      readonly next_cursor: string | null;
      readonly observed_at: string;
      readonly pagination?: 'anchored_search_not_commit_order';
    };
    readonly OperatorGoogleClaimResponse: {
      readonly created_at: string;
      readonly id: string;
      readonly issuer: string;
      readonly retired_at: string | null;
      readonly subject: string;
    };
    readonly OperatorHelpHistoryResponse: {
      readonly account_id: string;
      readonly anchor_version: number;
      readonly next_cursor: string | null;
      readonly revisions: readonly Api['schemas']['OperatorHelpHistoryRevisionResponse'][];
    };
    readonly OperatorHelpHistoryRevisionResponse: {
      readonly account_id: string;
      readonly saved_at: string;
      readonly selections: readonly Api['schemas']['OperatorHelpHistorySelectionResponse'][];
      readonly version: number;
    };
    readonly OperatorHelpHistorySelectionResponse: {
      readonly slot: number;
      readonly subject_id: string;
      readonly subject_label: string;
      readonly topic_match_key: string | null;
      readonly topic_note: string | null;
    };
    readonly OperatorIdentityAccountResponse: {
      readonly account_id: string;
      readonly banned_at: string | null;
      readonly created_at: string;
      readonly deleted_at: string | null;
      readonly google: Api['schemas']['OperatorGoogleClaimResponse'] | null;
      readonly institutional: Api['schemas']['OperatorInstitutionalClaimResponse'] | null;
    };
    readonly OperatorIdentityLinkResponse: {
      readonly account: Api['schemas']['OperatorIdentityAccountResponse'];
      readonly shared_google_claim: boolean;
      readonly shared_institutional_email: boolean;
    };
    readonly OperatorIdentityLinksResponse: {
      readonly as_of: string;
      readonly links: readonly Api['schemas']['OperatorIdentityLinkResponse'][];
      readonly next_cursor: string | null;
      readonly target: Api['schemas']['OperatorIdentityAccountResponse'];
    };
    readonly OperatorInstitutionalClaimResponse: {
      readonly email: string;
      readonly retired_at: string | null;
      readonly revoked_at: string | null;
      readonly verified_at: string;
    };
    readonly OperatorLifecycleHistoryResponse: {
      readonly account_id: string;
      readonly anchor_version: number;
      readonly next_cursor: string | null;
      readonly revisions: readonly Api['schemas']['OperatorLifecycleHistoryRevisionResponse'][];
    };
    readonly OperatorLifecycleHistoryRevisionResponse: {
      readonly account_id: string;
      readonly action_id: string | null;
      readonly actor_id: string;
      readonly actor_session_id: string;
      readonly after_banned_at: string | null;
      readonly after_deleted_at: string | null;
      readonly before_banned_at: string | null;
      readonly before_deleted_at: string | null;
      readonly changed_at: string;
      readonly http_request_id: string | null;
      readonly id: string;
      readonly operation: Api['schemas']['LifecycleOperation'];
      readonly operator_access_active: boolean | null;
      readonly operator_access_version: number | null;
      readonly previous_version: number | null;
      readonly reason: string | null;
      readonly span_id: string | null;
      readonly trace_id: string | null;
      readonly version: number;
      readonly workflow_id: string | null;
    };
    readonly OperatorMediaOriginPhase: 'created' | 'queued';
    readonly OperatorMediaOriginResponse: {
      readonly origin: Api['schemas']['OperatorEventOriginResponse'];
      readonly phase: Api['schemas']['OperatorMediaOriginPhase'];
      readonly recorded_at: string;
      readonly upload_id: string;
    };
    readonly OperatorMessageImageReportContextResponse: {
      readonly client_message_id: string;
      readonly conversation_id: string;
      readonly id: string;
      readonly image_attempt_id: string;
      readonly image_id: string;
      readonly image_version: number;
      readonly issued_at: string;
      readonly kind: 'message_image';
      readonly message_id: string;
      readonly message_sent_at: string;
      readonly origin: Api['schemas']['OperatorEventOriginResponse'];
      readonly reporter_id: string;
      readonly target_id: string;
    };
    readonly OperatorMessageOperationResponse: {
      readonly author_id: string;
      readonly cancelled_at: string | null;
      readonly client_message_id: string;
      readonly conversation_id: string;
      readonly high_id: string;
      readonly id: string;
      readonly low_id: string;
      readonly message: Api['schemas']['OperatorOperationMessageResponse'] | null;
      readonly message_id: string | null;
      readonly state: Api['schemas']['MessageOutcome'];
      readonly terminal_at: string;
    };
    readonly OperatorMessageOperationsResponse: {
      readonly account_id: string;
      readonly next_cursor: string | null;
      readonly operations: readonly Api['schemas']['OperatorMessageOperationResponse'][];
    };
    readonly OperatorMessagesResponse: {
      readonly accepted_request_version: number;
      readonly anchor_sequence: number;
      readonly conversation_id: string;
      readonly high_id: string;
      readonly low_id: string;
      readonly messages: readonly Api['schemas']['MessageResponse'][];
      readonly next_cursor: string | null;
      readonly relationship_id: string;
      readonly request_id: string;
    };
    readonly OperatorOperationMessageResponse: {
      readonly id: string;
      readonly image_attempt_id: string | null;
      readonly image_id: string | null;
      readonly image_version: number | null;
      readonly sent_at: string;
      readonly sequence: number;
      readonly text: string | null;
    };
    readonly OperatorPhotoAttemptOutcome:
      'processing' | 'ready' | 'retry' | 'rejected' | 'stale' | 'interrupted';
    readonly OperatorPhotoAttemptResponse: {
      readonly display_height: number | null;
      readonly display_sha256: string | null;
      readonly display_size: number | null;
      readonly display_width: number | null;
      readonly failure: Api['schemas']['PhotoFailure'] | null;
      readonly finished_at: string | null;
      readonly id: string;
      readonly lease_until: string;
      readonly next_attempt_at: string | null;
      readonly number: number;
      readonly outcome: Api['schemas']['OperatorPhotoAttemptOutcome'];
      readonly started_at: string;
      readonly upload_id: string;
    };
    readonly OperatorPhotoHistoryResponse: {
      readonly anchor_version: number;
      readonly attempt_observation?: 'current_recorded_not_revision_time';
      readonly attempts_current: readonly Api['schemas']['OperatorPhotoAttemptResponse'][];
      readonly latest_published_photo_ref:
        Api['schemas']['OperatorPublishedPhotoRefResponse'] | null;
      readonly next_cursor: string | null;
      readonly observed_at: string;
      readonly origins: readonly Api['schemas']['OperatorMediaOriginResponse'][];
      readonly publication_scope?: 'latest_recorded_ref_not_complete_history_or_object_grant';
      readonly revisions: readonly Api['schemas']['OperatorPhotoRevisionResponse'][];
      readonly upload: Api['schemas']['OperatorPhotoRootResponse'];
    };
    readonly OperatorPhotoRevisionResponse: {
      readonly account_id: string;
      readonly attempt_id: string | null;
      readonly failure: Api['schemas']['PhotoFailure'] | null;
      readonly state: Api['schemas']['PhotoUploadState'];
      readonly updated_at: string;
      readonly upload_id: string;
      readonly version: number;
    };
    readonly OperatorPhotoRootResponse: {
      readonly account_id: string;
      readonly created_at: string;
      readonly current_revision: Api['schemas']['OperatorPhotoRevisionResponse'];
      readonly current_version: number;
      readonly expected_photo_version: number;
      readonly id: string;
      readonly processing_expires_at: string;
      readonly source_content_type: string;
      readonly source_metadata?: 'declared_not_object_verified';
      readonly source_sha256: string;
      readonly source_size: number;
      readonly upload_expires_at: string;
    };
    readonly OperatorPhotoUploadsResponse: {
      readonly account_id: string;
      readonly anchor_created_at: string | null;
      readonly anchor_upload_id: string | null;
      readonly next_cursor: string | null;
      readonly observed_at: string;
      readonly pagination?: 'anchored_search_not_commit_order';
      readonly uploads: readonly Api['schemas']['OperatorPhotoRootResponse'][];
    };
    readonly OperatorPreferenceHistoryResponse: {
      readonly account_id: string;
      readonly anchor_version: number;
      readonly current: Api['schemas']['OperatorPreferenceHistoryRevisionResponse'] | null;
      readonly next_cursor: string | null;
      readonly revisions: readonly Api['schemas']['OperatorPreferenceHistoryRevisionResponse'][];
    };
    readonly OperatorPreferenceHistoryRevisionResponse: {
      readonly account_id: string;
      readonly changed_at: string;
      readonly mode: Api['schemas']['NotificationMode'];
      readonly version: number;
    };
    readonly OperatorProfileHistoryResponse: {
      readonly account_id: string;
      readonly anchor_version: number;
      readonly next_cursor: string | null;
      readonly revisions: readonly Api['schemas']['OperatorProfileHistoryRevisionResponse'][];
    };
    readonly OperatorProfileHistoryRevisionResponse: {
      readonly about: string | null;
      readonly account_id: string;
      readonly display_name: string | null;
      readonly languages: readonly string[];
      readonly programme: string | null;
      readonly saved_at: string;
      readonly task: Api['schemas']['OnboardingTask'];
      readonly version: number;
      readonly year_label: string | null;
    };
    readonly OperatorProfileMediaKind: 'original' | 'display';
    readonly OperatorPublishedPhotoRefResponse: {
      readonly account_id: string;
      readonly photo_version: number;
      readonly saved_at: string;
      readonly upload_id: string;
      readonly upload_version: number;
    };
    readonly OperatorReportContextResponse: {
      readonly goal_id: string | null;
      readonly goal_version: number | null;
      readonly help_version: number | null;
      readonly id: string;
      readonly issued_at: string;
      readonly kind: 'profile';
      readonly origin: Api['schemas']['OperatorEventOriginResponse'];
      readonly photo_version: number;
      readonly profile_version: number;
      readonly reporter_id: string;
      readonly target_id: string;
    };
    readonly OperatorReportDetailResponse: {
      readonly comment: string | null;
      readonly context:
        | Api['schemas']['OperatorReportContextResponse']
        | Api['schemas']['OperatorMessageImageReportContextResponse'];
      readonly report: Api['schemas']['OperatorReportSummaryResponse'];
      readonly submission: Api['schemas']['OperatorReportSubmissionResponse'] | null;
    };
    readonly OperatorReportKind: 'profile' | 'message_image';
    readonly OperatorReportSubmissionResponse: {
      readonly event_id: string;
      readonly occurred_at: string;
      readonly origin: Api['schemas']['OperatorEventOriginResponse'];
      readonly report_id: string;
      readonly reporter_id: string;
    };
    readonly OperatorReportSummaryResponse: {
      readonly category: Api['schemas']['ReportCategory'];
      readonly context_id: string;
      readonly has_comment: boolean;
      readonly id: string;
      readonly kind: Api['schemas']['OperatorReportKind'];
      readonly reporter_id: string;
      readonly submitted_at: string;
      readonly target_id: string;
    };
    readonly OperatorReportsResponse: {
      readonly next_cursor: string | null;
      readonly reports: readonly Api['schemas']['OperatorReportSummaryResponse'][];
      readonly search_anchor_at: string;
    };
    readonly OperatorRequestAcknowledgementResponse: {
      readonly acknowledged_at: string;
      readonly disclosure: Api['schemas']['OperatorRequestDisclosureResponse'];
      readonly id: string;
      readonly origin: Api['schemas']['OperatorRequestOriginResponse'];
      readonly request_id: string;
      readonly stored_version: number;
      readonly viewer_id: string;
    };
    readonly OperatorRequestDirection: 'sent' | 'received';
    readonly OperatorRequestDisclosureResponse: {
      readonly created_at: string;
      readonly id: string;
      readonly origin: Api['schemas']['OperatorRequestOriginResponse'];
      readonly request_id: string;
      readonly stored_version: number;
      readonly viewer_id: string;
    };
    readonly OperatorRequestHistoryResponse: {
      readonly ack_scope?: 'page_revisions_only';
      readonly acknowledgements: readonly Api['schemas']['OperatorRequestAcknowledgementResponse'][];
      readonly anchor_version: number;
      readonly disclosure_scope?: 'ack_linked_disclosures_not_all_views';
      readonly next_cursor: string | null;
      readonly note: string | null;
      readonly observed_at: string;
      readonly preview: Api['schemas']['OperatorRequestPreviewResponse'];
      readonly request: Api['schemas']['OperatorRequestRootResponse'];
      readonly request_text: string;
      readonly revisions: readonly Api['schemas']['OperatorRequestRevisionResponse'][];
      readonly root_observation?: 'current_recorded_not_revision_snapshot';
    };
    readonly OperatorRequestOriginResponse: {
      readonly action_id: string | null;
      readonly http_request_id: string | null;
      readonly representation?: 'raw_recorded_source_correlation';
      readonly span_id: string | null;
      readonly trace_id: string | null;
    };
    readonly OperatorRequestPreviewResponse: {
      readonly created_at: string;
      readonly id: string;
      readonly mode: Api['schemas']['DiscoveryMode'];
      readonly recipient_goal_id: string | null;
      readonly recipient_goal_version: number | null;
      readonly recipient_help_version: number | null;
      readonly recipient_id: string;
      readonly representation?: 'raw_stored_json_object_not_current_request_schema';
      readonly sender_goal_id: string | null;
      readonly sender_goal_version: number | null;
      readonly sender_help_version: number | null;
      readonly sender_id: string;
      readonly source_json_raw: string;
      readonly subject_id: string;
    };
    readonly OperatorRequestRevisionResponse: {
      readonly changed_at: string;
      readonly conversation_id: string | null;
      readonly decline_until: string | null;
      readonly request_id: string;
      readonly state: Api['schemas']['RequestState'];
      readonly version: number;
    };
    readonly OperatorRequestRootResponse: {
      readonly current_version: number;
      readonly expires_at: string;
      readonly id: string;
      readonly mode: Api['schemas']['DiscoveryMode'];
      readonly origin: Api['schemas']['OperatorRequestOriginResponse'];
      readonly preview_id: string;
      readonly recipient_id: string;
      readonly relationship_id: string;
      readonly sender_id: string;
      readonly sent_at: string;
      readonly state: Api['schemas']['RequestState'];
      readonly subject_id: string;
    };
    readonly OperatorRequestsResponse: {
      readonly account_id: string;
      readonly anchor_request_id: string | null;
      readonly anchor_sent_at: string | null;
      readonly next_cursor: string | null;
      readonly observed_at: string;
      readonly pagination?: 'anchored_search_not_commit_order';
      readonly requests: readonly Api['schemas']['OperatorRequestRootResponse'][];
    };
    readonly OperatorResourceKind:
      | 'account'
      | 'conversation'
      | 'message'
      | 'event'
      | 'audit'
      | 'report'
      | 'profile_media'
      | 'chat_media'
      | 'support_case'
      | 'delivery_source';
    readonly OperatorRetainedDisclosureResponse: {
      readonly created_at: string;
      readonly id: string;
      readonly origin: Api['schemas']['OperatorRequestOriginResponse'];
      readonly recipient_id: string;
      readonly request_id: string;
      readonly sender_id: string;
      readonly stored_version: number;
      readonly viewer_id: string;
    };
    readonly OperatorSourceKind:
      | 'account_lifecycle_revision'
      | 'account'
      | 'profile_revision'
      | 'help_revision'
      | 'photo_revision'
      | 'visibility_revision'
      | 'goal_revision'
      | 'subject'
      | 'ai_job'
      | 'profile_report'
      | 'report_review_revision'
      | 'report_triage_submission'
      | 'photo_review_revision'
      | 'block_revision'
      | 'private_pass_revision'
      | 'request_revision'
      | 'request_view_ack'
      | 'message_operation'
      | 'conversation_read'
      | 'goal_share'
      | 'operator_audit'
      | 'study_outcome'
      | 'feedback_revision'
      | 'study_prompt'
      | 'notification_preference_revision'
      | 'support_case_revision';
    readonly OperatorSupportHistoryResponse: {
      readonly anchor_version: number;
      readonly case_id: string;
      readonly next_cursor: string | null;
      readonly revisions: readonly Api['schemas']['OperatorSupportHistoryRevisionResponse'][];
    };
    readonly OperatorSupportHistoryRevisionResponse: {
      readonly changed_at: string;
      readonly changed_by_id: string | null;
      readonly operator_access_version: number | null;
      readonly status: Api['schemas']['SupportStatus'];
      readonly version: number;
    };
    readonly OperatorSupportInboxResponse: {
      readonly cases: readonly Api['schemas']['OperatorSupportSummaryResponse'][];
      readonly metadata_anchor: string;
      readonly next_cursor: string | null;
      readonly status_semantics?: 'current_at_each_request';
    };
    readonly OperatorSupportResponse: {
      readonly actor_id: string | null;
      readonly details?: string | null;
      readonly message: string;
      readonly receipt: Api['schemas']['SupportReceiptResponse'];
      readonly reply_address: string;
      readonly topic: Api['schemas']['SupportTopic'];
    };
    readonly OperatorSupportSummaryResponse: {
      readonly actor_id: string | null;
      readonly case_id: string;
      readonly changed_at: string;
      readonly received_at: string;
      readonly status: Api['schemas']['SupportStatus'];
      readonly topic: Api['schemas']['SupportTopic'];
      readonly version: number;
    };
    readonly OperatorVisibilityHistoryResponse: {
      readonly account_id: string;
      readonly anchor_version: number;
      readonly current: Api['schemas']['OperatorVisibilityHistoryRevisionResponse'] | null;
      readonly next_cursor: string | null;
      readonly revisions: readonly Api['schemas']['OperatorVisibilityHistoryRevisionResponse'][];
    };
    readonly OperatorVisibilityHistoryRevisionResponse: {
      readonly account_id: string;
      readonly changed_at: string;
      readonly completed_at: string;
      readonly hidden_at: string | null;
      readonly version: number;
    };
    readonly OwnBlocksResponse: {
      readonly next_cursor: string | null;
      readonly people: readonly Api['schemas']['BlockedPersonResponse'][];
    };
    readonly OwnFeedbackResponse: {
      readonly can_submit: boolean;
      readonly current: Api['schemas']['FeedbackReceiptResponse'] | null;
      readonly current_publication: Api['schemas']['FeedbackPublication'] | null;
      readonly outcome: Api['schemas']['StudyOutcomeResponse'] | null;
      readonly submission_publication: Api['schemas']['FeedbackPublication'] | null;
    };
    readonly OwnGoalResponse: { readonly goal: Api['schemas']['GoalResponse'] | null };
    readonly OwnHelpResponse: { readonly selection: Api['schemas']['HelpResponse'] | null };
    readonly OwnPhotoResumeResponse: {
      readonly photo: Api['schemas']['CurrentPhotoResponse'] | null;
      readonly uploads: readonly Api['schemas']['PhotoResumeItemResponse'][];
    };
    readonly OwnPhotoReviewResponse: {
      readonly state: Api['schemas']['PhotoRecoveryState'];
      readonly version: number;
    };
    readonly OwnProfileResponse: {
      readonly photo: Api['schemas']['CurrentPhotoResponse'] | null;
      readonly profile: Api['schemas']['ProfileRevisionResponse'] | null;
    };
    readonly OwnStudyOutcomeResponse: {
      readonly outcome: Api['schemas']['StudyOutcomeResponse'] | null;
    };
    readonly PendingDeletionResponse: {
      readonly expires_at: string;
      readonly state?: 'pending';
      readonly workflow_id: string;
    };
    readonly PerformanceObserved: {
      readonly header: Api['schemas']['ObservationHeader'];
      readonly metric: Api['schemas']['Metric'];
      readonly value: number;
    };
    readonly PerformanceObservedBody: {
      readonly event_id: string;
      readonly kind: 'performance.observed';
      readonly metric: Api['schemas']['Metric'];
      readonly observed_at: string;
      readonly screen: Api['schemas']['Screen'];
      readonly value: number;
    };
    readonly PhotoContentType: 'image/jpeg' | 'image/png';
    readonly PhotoFailure:
      | 'invalid_image'
      | 'unsupported_format'
      | 'too_large'
      | 'dimensions_exceeded'
      | 'animated_image'
      | 'content_changed'
      | 'photo_changed'
      | 'account_unavailable'
      | 'storage_unavailable'
      | 'processing_unavailable';
    readonly PhotoRecoveryState: 'not_required' | 'replacement_required' | 'awaiting_human_review';
    readonly PhotoReferenceResponse: {
      readonly saved_at: string;
      readonly upload_id: string;
      readonly version: number;
    };
    readonly PhotoRequest: {
      readonly kind: 'assess_photo';
      readonly source: Api['schemas']['ResourceSourceRequest'];
    };
    readonly PhotoResultResponse: {
      readonly blurred: Api['schemas']['studymate__domain__ai__tasks__Observation'];
      readonly face_visible: Api['schemas']['studymate__domain__ai__tasks__Observation'];
      readonly multiple_people: Api['schemas']['studymate__domain__ai__tasks__Observation'];
    };
    readonly PhotoResumeItemResponse: {
      readonly source_sha256: string;
      readonly upload: Api['schemas']['PhotoUploadResponse'];
    };
    readonly PhotoReviewAction: 'require_replacement' | 'approve_replacement';
    readonly PhotoReviewBody: {
      readonly action: Api['schemas']['PhotoReviewAction'];
      readonly expected_photo_version: number;
      readonly expected_upload_id: string;
      readonly expected_version: number;
      readonly reason: string;
    };
    readonly PhotoReviewContextResponse: {
      readonly account_id: string;
      readonly current_photo: Api['schemas']['PhotoReviewPhotoResponse'] | null;
      readonly current_review: Api['schemas']['PhotoReviewResponse'] | null;
    };
    readonly PhotoReviewPhotoResponse: {
      readonly saved_at: string;
      readonly upload_id: string;
      readonly version: number;
    };
    readonly PhotoReviewResponse: {
      readonly account_id: string;
      readonly action: Api['schemas']['PhotoReviewAction'];
      readonly action_id: string | null;
      readonly decided_at: string;
      readonly grant_version: number;
      readonly http_request_id: string | null;
      readonly id: string;
      readonly operator_id: string;
      readonly photo: Api['schemas']['PhotoReviewPhotoResponse'];
      readonly previous_revision_id: string | null;
      readonly reason: string;
      readonly session_id: string;
      readonly span_id: string | null;
      readonly trace_id: string | null;
      readonly version: number;
    };
    readonly PhotoUploadResponse: {
      readonly content_type: Api['schemas']['PhotoContentType'];
      readonly display_url: string | null;
      readonly expected_photo_version: number;
      readonly failure: Api['schemas']['PhotoFailure'] | null;
      readonly id: string;
      readonly poll_after_ms: number | null;
      readonly processing_expires_at: string;
      readonly size_bytes: number;
      readonly state: Api['schemas']['PhotoUploadState'];
      readonly updated_at: string;
      readonly upload_expires_at: string;
      readonly version: number;
    };
    readonly PhotoUploadState:
      'uploading' | 'queued' | 'processing' | 'ready' | 'rejected' | 'cancelled' | 'expired';
    readonly PolicyHistoryItemResponse: {
      readonly reference: Api['schemas']['PolicyReferenceResponse'];
      readonly title: string;
    };
    readonly PolicyHistoryResponse: {
      readonly items: readonly Api['schemas']['PolicyHistoryItemResponse'][];
      readonly next_cursor: string | null;
    };
    readonly PolicyKind: 'terms' | 'privacy';
    readonly PolicyReferenceResponse: {
      readonly id: string;
      readonly kind: Api['schemas']['PolicyKind'];
      readonly published_at: string;
      readonly version: string;
    };
    readonly PolicyStatusResponse: {
      readonly current_privacy: Api['schemas']['PolicyReferenceResponse'] | null;
      readonly current_terms: Api['schemas']['PolicyReferenceResponse'] | null;
      readonly receipt: Api['schemas']['RegistrationReceiptResponse'] | null;
    };
    readonly PreferenceBody: {
      readonly expected_version: number;
      readonly mode: Api['schemas']['NotificationMode'];
    };
    readonly PreferenceResponse: {
      readonly changed_at: string | null;
      readonly mode: Api['schemas']['NotificationMode'];
      readonly version: number;
    };
    readonly PreparationMessageOutcome: {
      readonly attachment_confirmed: boolean;
      readonly message_id: string | null;
      readonly operation_id: string;
      readonly outcome: Api['schemas']['MessageOutcome'];
    };
    readonly PreviewBlockReason:
      | 'existing_outgoing'
      | 'incoming'
      | 'connected'
      | 'cooldown'
      | 'source_changed'
      | 'unavailable'
      | 'outgoing_pending_limit'
      | 'daily_send_limit';
    readonly PreviewQuotaResponse: {
      readonly daily_send_limit: number;
      readonly daily_sends_remaining: number;
      readonly outgoing_pending: number;
      readonly outgoing_pending_limit: number;
      readonly outgoing_pending_remaining: number;
      readonly reset_at: string;
      readonly successful_today: number;
    };
    readonly PreviewRequestBody: {
      readonly mode: Api['schemas']['DiscoveryMode'];
      readonly person_id: string;
    };
    readonly PreviewResponse: {
      readonly block_reason: Api['schemas']['PreviewBlockReason'] | null;
      readonly can_send: boolean;
      readonly checked_at: string;
      readonly context: Api['schemas']['AcademicContextResponse'];
      readonly cooldown_until: string | null;
      readonly created_at: string;
      readonly outcome?: 'preview';
      readonly preview_id: string;
      readonly quota: Api['schemas']['PreviewQuotaResponse'];
      readonly suggested_text: string;
    };
    readonly Priority: 'low' | 'normal' | 'high';
    readonly PrivatePassResponse: {
      readonly changed_at: string | null;
      readonly passed: boolean;
      readonly person_id: string;
      readonly version: number;
    };
    readonly ProblemResponse: {
      readonly code: string;
      readonly errors: readonly Api['schemas']['FieldProblemResponse'][];
      readonly recovery: Readonly<Record<string, string | number | null>>;
      readonly request_id: string;
      readonly status: number;
      readonly title: string;
      readonly trace_id: string | null;
      readonly type: string;
    };
    readonly ProfileCapabilitiesResponse: {
      readonly can_access_existing_chats: boolean;
      readonly can_complete_registration: boolean;
      readonly can_complete_setup: boolean;
      readonly can_discover: boolean;
      readonly can_hide_profile: boolean;
      readonly can_make_new_contacts: boolean;
      readonly can_manage_profile: boolean;
      readonly can_restore_profile: boolean;
    };
    readonly ProfileReferenceResponse: {
      readonly languages: readonly Api['schemas']['LanguageOptionResponse'][];
      readonly max_display_name_length: number;
      readonly max_languages: number;
      readonly min_display_name_length: number;
      readonly university: string;
    };
    readonly ProfileReportReceipt: {
      readonly context_id: string;
      readonly id: string;
      readonly kind?: 'profile';
      readonly submitted_at: string;
    };
    readonly ProfileReportRequest: {
      readonly category: Api['schemas']['ReportCategory'];
      readonly comment?: string | null;
      readonly context_id: string;
      readonly kind: 'profile';
    };
    readonly ProfileRevisionResponse: {
      readonly about: string | null;
      readonly display_name: string | null;
      readonly languages: readonly string[];
      readonly programme: string | null;
      readonly saved_at: string;
      readonly task: Api['schemas']['OnboardingTask'];
      readonly version: number;
      readonly year_label: string | null;
    };
    readonly ProfileVisibilityResponse: {
      readonly changed_at: string;
      readonly completed_at: string;
      readonly hidden: boolean;
      readonly hidden_at: string | null;
      readonly version: number;
    };
    readonly PublicFrame: {
      readonly asset_id: number;
      readonly column: number;
      readonly line: number;
    };
    readonly PublicFrameBody: {
      readonly asset_id: number;
      readonly column: number;
      readonly line: number;
    };
    readonly PublicPhotoResponse: { readonly display_url: string; readonly version: number };
    readonly PublicProfileResponse: {
      readonly about: string | null;
      readonly access_context_id: string;
      readonly display_name: string;
      readonly goal: Api['schemas']['GoalResponse'] | null;
      readonly help_subjects: Api['schemas']['HelpResponse'] | null;
      readonly id: string;
      readonly languages: readonly string[];
      readonly own_block: Api['schemas']['BlockStateResponse'];
      readonly photo: Api['schemas']['PublicPhotoResponse'];
      readonly programme: string | null;
      readonly version: number;
      readonly year_label: string | null;
    };
    readonly PublishedPolicyResponse: {
      readonly content: string;
      readonly reference: Api['schemas']['PolicyReferenceResponse'];
      readonly title: string;
    };
    readonly QualityObserved: {
      readonly count: number;
      readonly header: Api['schemas']['ObservationHeader'];
      readonly reason: Api['schemas']['QualityReason'];
    };
    readonly QualityObservedBody: {
      readonly count: number;
      readonly event_id: string;
      readonly kind: 'quality.observed';
      readonly observed_at: string;
      readonly reason: Api['schemas']['QualityReason'];
      readonly screen: Api['schemas']['Screen'];
    };
    readonly QualityReason:
      'overflow' | 'invalid' | 'expired' | 'rejected' | 'exhausted' | 'unavailable';
    readonly ReadyImageMetadata: {
      readonly height: number;
      readonly size: number;
      readonly width: number;
    };
    readonly RecentSupportCasesResponse: {
      readonly cases: readonly Api['schemas']['SupportReceiptResponse'][];
    };
    readonly RegistrationContextResponse: {
      readonly expires_at: string;
      readonly id: string;
      readonly notice_text: string;
      readonly privacy: Api['schemas']['PolicyReferenceResponse'];
      readonly surface: Api['schemas']['RegistrationSurface'];
      readonly terms: Api['schemas']['PolicyReferenceResponse'];
    };
    readonly RegistrationReceiptResponse: {
      readonly context_id: string;
      readonly id: string;
      readonly notice_text: string;
      readonly privacy: Api['schemas']['PolicyReferenceResponse'];
      readonly registered_at: string;
      readonly surface: Api['schemas']['RegistrationSurface'];
      readonly terms: Api['schemas']['PolicyReferenceResponse'];
    };
    readonly RegistrationSurface: 'onboarding_completion';
    readonly RelevanceReason: 'can_help' | 'you_can_help' | 'shared_goal';
    readonly ReportCategory:
      'impersonation' | 'harassment' | 'inappropriate_content' | 'spam' | 'other';
    readonly ReportReceipt:
      Api['schemas']['ProfileReportReceipt'] | Api['schemas']['MessageImageReportReceipt'];
    readonly ReportReviewAction: 'dismiss' | 'escalate';
    readonly ReportReviewHistoryResponse: {
      readonly anchor_version: number;
      readonly context_id: string;
      readonly current: Api['schemas']['ReportReviewResponse'] | null;
      readonly kind: Api['schemas']['OperatorReportKind'];
      readonly next_cursor: string | null;
      readonly report_id: string;
      readonly reporter_id: string;
      readonly revisions: readonly Api['schemas']['ReportReviewResponse'][];
      readonly target_id: string;
    };
    readonly ReportReviewResponse: {
      readonly action: Api['schemas']['ReportReviewAction'];
      readonly action_id: string | null;
      readonly actor_session_id: string;
      readonly event_id: string;
      readonly http_request_id: string | null;
      readonly id: string;
      readonly operator_access_version: number;
      readonly operator_id: string;
      readonly previous_version: number | null;
      readonly reason: string;
      readonly report_id: string;
      readonly reviewed_at: string;
      readonly span_id: string | null;
      readonly trace_id: string | null;
      readonly version: number;
    };
    readonly ReportTriageBody: { readonly source_token: string };
    readonly ReportTriageContextResponse: {
      readonly available: boolean;
      readonly evidence: string | null;
      readonly kind: Api['schemas']['OperatorReportKind'];
      readonly report_id: string;
      readonly source_token: string | null;
    };
    readonly ReportTriageReadResponse: {
      readonly report_id: string;
      readonly triage: Api['schemas']['ReportTriageResponse'] | null;
    };
    readonly ReportTriageResponse: {
      readonly action_id: string | null;
      readonly actor_session_id: string;
      readonly event_id: string;
      readonly failure: Api['schemas']['Failure'] | null;
      readonly http_request_id: string | null;
      readonly job_id: string;
      readonly operator_access_version: number;
      readonly operator_id: string;
      readonly priority: Api['schemas']['Priority'] | null;
      readonly rationale: string | null;
      readonly report_id: string;
      readonly source_current: boolean;
      readonly source_version: number;
      readonly span_id: string | null;
      readonly state: Api['schemas']['JobState'];
      readonly submitted_at: string;
      readonly trace_id: string | null;
    };
    readonly RequestActionBody: { readonly expected_version: number; readonly person_id: string };
    readonly RequestBox: 'received' | 'sent';
    readonly RequestCapabilitiesResponse: {
      readonly accept: boolean;
      readonly decline: boolean;
      readonly open_conversation: boolean;
      readonly undo_decline: boolean;
      readonly view_profile: boolean;
      readonly withdraw: boolean;
    };
    readonly RequestDetailResponse: {
      readonly context: Api['schemas']['AcademicContextResponse'];
      readonly disclosed_at: string;
      readonly disclosed_version: number;
      readonly disclosure_id: string;
      readonly note: string | null;
      readonly request: Api['schemas']['RequestSummaryResponse'];
      readonly text: string;
    };
    readonly RequestListView: 'active' | 'history' | 'recently_declined';
    readonly RequestMutationResponse: {
      readonly changed_at: string;
      readonly conversation_id: string | null;
      readonly outcome:
        | 'sent'
        | 'existing_outgoing'
        | 'incoming'
        | 'accepted'
        | 'declined'
        | 'undo_decline'
        | 'withdrawn';
      readonly request_id: string;
      readonly undo_until: string | null;
      readonly version: number;
    };
    readonly RequestPageResponse: {
      readonly daily_send_limit: number;
      readonly next_cursor: string | null;
      readonly observed_at: string;
      readonly outgoing_pending: number;
      readonly outgoing_pending_limit: number;
      readonly requests: readonly Api['schemas']['RequestSummaryResponse'][];
      readonly successful_today: number;
      readonly unread_received: number;
    };
    readonly RequestPeerResponse: {
      readonly display_name: string | null;
      readonly person_id: string;
      readonly photo_version: number | null;
      readonly state: Api['schemas']['RequestPeerState'];
    };
    readonly RequestPeerState: 'public' | 'unavailable' | 'deleted';
    readonly RequestPublicState:
      'pending' | 'pending_decline' | 'accepted' | 'declined' | 'withdrawn' | 'expired' | 'closed';
    readonly RequestState:
      | 'pending'
      | 'pending_decline'
      | 'declined'
      | 'withdrawn'
      | 'expired'
      | 'unavailable'
      | 'accepted';
    readonly RequestSummaryResponse: {
      readonly capabilities: Api['schemas']['RequestCapabilitiesResponse'];
      readonly conversation_id: string | null;
      readonly cooldown_until: string | null;
      readonly expires_at: string;
      readonly mode: Api['schemas']['DiscoveryMode'];
      readonly note: string | null;
      readonly observed_at: string;
      readonly peer: Api['schemas']['RequestPeerResponse'];
      readonly request_id: string;
      readonly sent_at: string;
      readonly state: Api['schemas']['RequestPublicState'];
      readonly subject_id: string;
      readonly subject_label: string;
      readonly text: string;
      readonly topic: string | null;
      readonly undo_until: string | null;
      readonly unread: boolean;
      readonly version: number;
    };
    readonly ResourceSourceRequest: {
      readonly id: string;
      readonly kind: 'resource';
      readonly version: number;
    };
    readonly ResourceSourceResponse: {
      readonly id: string;
      readonly kind?: 'resource';
      readonly version: number;
    };
    readonly RestoreRequirement: 'photo' | 'photo_review' | 'study_context';
    readonly ResultKind: 'accepted' | 'retryable' | 'ambiguous' | 'permanent';
    readonly ReviewReportBody: {
      readonly action: Api['schemas']['ReportReviewAction'];
      readonly expected_version: number;
      readonly reason: string;
    };
    readonly SaveGoalRequest: {
      readonly context?: string | null;
      readonly expected_goal_id?: string | null;
      readonly expected_version: number;
      readonly shared_learning?: boolean;
      readonly subject:
        Api['schemas']['CanonicalSubjectRequest'] | Api['schemas']['CustomSubjectRequest'];
      readonly topic?: string | null;
    };
    readonly SaveHelpRequest: {
      readonly expected_version: number;
      readonly subjects: readonly Api['schemas']['HelpSubjectRequest'][];
    };
    readonly SaveProfileRequest: {
      readonly about?: string | null;
      readonly display_name?: string | null;
      readonly expected_version: number;
      readonly languages?: readonly string[];
      readonly programme?: string | null;
      readonly task?: Api['schemas']['OnboardingTask'];
      readonly year_label?: string | null;
    };
    readonly Screen:
      | 'welcome'
      | 'verification'
      | 'onboarding'
      | 'discover'
      | 'requests'
      | 'chats'
      | 'conversation'
      | 'profile'
      | 'study'
      | 'notifications'
      | 'support'
      | 'help'
      | 'terms'
      | 'privacy'
      | 'operator'
      | 'unknown';
    readonly ScreenViewed: { readonly header: Api['schemas']['ObservationHeader'] };
    readonly ScreenViewedBody: {
      readonly event_id: string;
      readonly kind: 'screen.viewed';
      readonly observed_at: string;
      readonly screen: Api['schemas']['Screen'];
    };
    readonly SelectedSource:
      | Api['schemas']['CanonicalSource']
      | Api['schemas']['ClientObservationSource']
      | Api['schemas']['SupportCaseSource'];
    readonly SendMessageBody: {
      readonly client_message_id: string;
      readonly image_id?: string | null;
      readonly text?: string | null;
    };
    readonly SendRequestBody: {
      readonly note?: string | null;
      readonly person_id: string;
      readonly preview_id: string;
      readonly text: string;
    };
    readonly ShareCurrentGoalBody: {
      readonly expected_context_version: number;
      readonly expected_goal_version: number;
      readonly goal_id: string;
    };
    readonly SharedCanonicalSubjectResponse: {
      readonly id: string;
      readonly kind?: 'canonical';
      readonly label: string;
    };
    readonly SharedCustomSubjectResponse: { readonly kind?: 'custom'; readonly label: string };
    readonly SharedGoalSourceResponse: {
      readonly context: string | null;
      readonly goal_created_at: string;
      readonly goal_id: string;
      readonly goal_updated_at: string;
      readonly owner_id: string;
      readonly shared_learning: boolean;
      readonly subject:
        | Api['schemas']['SharedCanonicalSubjectResponse']
        | Api['schemas']['SharedCustomSubjectResponse'];
      readonly topic: string | null;
      readonly version: number;
    };
    readonly Sink: 'umami' | 'telegram_support';
    readonly SourceDetailResponse: {
      readonly deliveries: readonly Api['schemas']['DeliverySummary'][];
      readonly source: Api['schemas']['CapturedSource'];
      readonly summary: Api['schemas']['SourceSummary'];
    };
    readonly SourceKind: 'canonical' | 'client_observation' | 'support_case';
    readonly SourceSummary: {
      readonly actor_id: string | null;
      readonly captured_at: string;
      readonly exclusion_reason: string | null;
      readonly id: string;
      readonly kind: Api['schemas']['SourceKind'];
      readonly materialized_at: string | null;
      readonly mode: Api['schemas']['CaptureMode'];
      readonly original_id: string;
      readonly routing_version: number;
    };
    readonly SourcesResponse: {
      readonly next_cursor: string | null;
      readonly sources: readonly Api['schemas']['SourceSummary'][];
    };
    readonly StartEmailRequest: { readonly email: string; readonly resend_of?: string | null };
    readonly StartImageBody: {
      readonly client_message_id: string;
      readonly content_type: Api['schemas']['PhotoContentType'];
      readonly sha256: string;
      readonly size: number;
    };
    readonly StartPhotoRequest: {
      readonly content_type: Api['schemas']['PhotoContentType'];
      readonly expected_photo_version: number;
      readonly sha256: string;
      readonly size_bytes: number;
    };
    readonly StatusClass: '1xx' | '2xx' | '3xx' | '4xx' | '5xx' | 'network' | 'cancelled';
    readonly StudyAgain: 'yes' | 'maybe' | 'no';
    readonly StudyAnswer: 'yes' | 'not_yet' | 'did_not_work_out';
    readonly StudyOutcomeBody: {
      readonly answer: Api['schemas']['StudyAnswer'];
      readonly expected_version: number;
    };
    readonly StudyOutcomeResponse: {
      readonly answer: Api['schemas']['StudyAnswer'];
      readonly changed_at: string;
      readonly conversation_id: string;
      readonly id: string;
      readonly version: number;
    };
    readonly StudyPromptVisitBody: Readonly<Record<string, never>>;
    readonly StudyTogetherContext: {
      readonly goal_id: string;
      readonly goal_version: number;
      readonly mode: 'study_together';
    };
    readonly SubjectResponse: {
      readonly aliases: readonly string[];
      readonly id: string;
      readonly name: string;
    };
    readonly SubjectResultResponse: { readonly ids: readonly string[] };
    readonly SubjectsResponse: {
      readonly items: readonly Api['schemas']['SubjectResponse'][];
      readonly next_cursor: string | null;
    };
    readonly SubmittedInstitutionalEmailResponse: {
      readonly consumed_at: string | null;
      readonly created_at: string;
      readonly email: string;
      readonly expires_at: string;
      readonly id: string;
      readonly superseded_at: string | null;
    };
    readonly SuggestRequest: {
      readonly candidate_ids: readonly string[];
      readonly kind: 'suggest_subject';
      readonly label?: string | null;
      readonly source:
        Api['schemas']['ResourceSourceRequest'] | Api['schemas']['DraftSourceRequest'];
    };
    readonly SupportBody: {
      readonly details?: string | null;
      readonly message: string;
      readonly reply_address: string;
      readonly topic: Api['schemas']['SupportTopic'];
    };
    readonly SupportCaseSource: {
      readonly actor_id: string | null;
      readonly id: string;
      readonly received_at: string;
      readonly topic: Api['schemas']['SupportTopic'];
    };
    readonly SupportPreparationBody: Readonly<Record<string, never>>;
    readonly SupportPreparationResponse: {
      readonly csrf_token: string;
      readonly expires_at: string;
    };
    readonly SupportReceiptResponse: {
      readonly case_id: string;
      readonly changed_at: string;
      readonly received_at: string;
      readonly status: Api['schemas']['SupportStatus'];
      readonly version: number;
    };
    readonly SupportStatus: 'received' | 'in_review' | 'resolved';
    readonly SupportStatusBody: {
      readonly expected_version: number;
      readonly status: Api['schemas']['SupportStatus'];
    };
    readonly SupportTopic:
      | 'cannot_sign_in'
      | 'email_not_accepted'
      | 'code_not_arriving'
      | 'email_already_in_use'
      | 'deleted_account'
      | 'other';
    readonly UnobservedOperationResponse: {
      readonly client_message_id: string;
      readonly conversation_id: string;
      readonly outcome?: 'unobserved';
    };
    readonly UploadAccessResponse: {
      readonly fields: Readonly<Record<string, string>>;
      readonly url: string;
    };
    readonly VerificationOutcome:
      'verified' | 'wrong' | 'locked' | 'expired' | 'unavailable' | 'support_required';
    readonly VerificationResponse: { readonly verified_at: string };
    readonly VerifyEmailRequest: { readonly code: string };
    readonly ViewRequestBody: { readonly disclosure_id: string };
    readonly ViewedResponse: {
      readonly acknowledged_at: string;
      readonly acknowledgement_id: string;
      readonly disclosure_id: string;
      readonly request_id: string;
      readonly stored_version: number;
    };
    readonly studymate__domain__ai__tasks__Observation: 'yes' | 'no' | 'uncertain';
    readonly studymate__domain__client_observations__events__Observation:
      | Api['schemas']['ScreenViewed']
      | Api['schemas']['ActionObserved']
      | Api['schemas']['PerformanceObserved']
      | Api['schemas']['ErrorObserved']
      | Api['schemas']['HttpObserved']
      | Api['schemas']['QualityObserved'];
  };
  readonly paths: {
    readonly '/api/health': {
      readonly get: {
        readonly parameters: Readonly<Record<string, never>>;
        readonly body: undefined;
        readonly responses: {
          readonly '200': Readonly<Record<string, 'ok'>>;
          readonly '500': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/ready': {
      readonly get: {
        readonly parameters: Readonly<Record<string, never>>;
        readonly body: undefined;
        readonly responses: {
          readonly '200': unknown;
          readonly '500': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/ai/jobs': {
      readonly post: {
        readonly parameters: {
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body:
          | Api['schemas']['ClarifyRequest']
          | Api['schemas']['SuggestRequest']
          | Api['schemas']['PhotoRequest'];
        readonly responses: {
          readonly '202': Api['schemas']['JobResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/ai/jobs/{job_id}': {
      readonly get: {
        readonly parameters: { readonly 'path:job_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['JobResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/ai/jobs/{job_id}/cancel': {
      readonly post: {
        readonly parameters: {
          readonly 'path:job_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['JobResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/auth/email-challenges': {
      readonly post: {
        readonly parameters: {
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['StartEmailRequest'];
        readonly responses: {
          readonly '202': Api['schemas']['ChallengeResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/auth/email-challenges/{challenge_id}': {
      readonly get: {
        readonly parameters: { readonly 'path:challenge_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['ChallengeStatusResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/auth/email-challenges/{challenge_id}/verify': {
      readonly post: {
        readonly parameters: {
          readonly 'path:challenge_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['VerifyEmailRequest'];
        readonly responses: {
          readonly '200': Api['schemas']['VerificationResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/auth/google/callback': {
      readonly get: {
        readonly parameters: Readonly<Record<string, never>>;
        readonly body: undefined;
        readonly responses: {
          readonly '303': unknown;
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/auth/google/start': {
      readonly get: {
        readonly parameters: Readonly<Record<string, never>>;
        readonly body: undefined;
        readonly responses: {
          readonly '303': unknown;
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/auth/logout': {
      readonly post: {
        readonly parameters: {
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '204': undefined;
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/conversations': {
      readonly get: {
        readonly parameters: { readonly 'query:cursor'?: string | null };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['ConversationListResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/conversations/{conversation_id}': {
      readonly get: {
        readonly parameters: { readonly 'path:conversation_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['ConversationDetailsResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/conversations/{conversation_id}/feedback': {
      readonly get: {
        readonly parameters: { readonly 'path:conversation_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OwnFeedbackResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
      readonly put: {
        readonly parameters: {
          readonly 'path:conversation_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['FeedbackBody'];
        readonly responses: {
          readonly '200': Api['schemas']['FeedbackReceiptResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/conversations/{conversation_id}/goal-shares': {
      readonly get: {
        readonly parameters: {
          readonly 'path:conversation_id': string;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['ConversationGoalSharePageResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
      readonly post: {
        readonly parameters: {
          readonly 'path:conversation_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['ShareCurrentGoalBody'];
        readonly responses: {
          readonly '200': Api['schemas']['ConversationGoalShareReceiptResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/conversations/{conversation_id}/image-preparations': {
      readonly get: {
        readonly parameters: { readonly 'path:conversation_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['ImagePreparationsResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
      readonly post: {
        readonly parameters: {
          readonly 'path:conversation_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['StartImageBody'];
        readonly responses: {
          readonly '202': Api['schemas']['ImagePreparationReceipt'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/conversations/{conversation_id}/image-preparations/{image_id}': {
      readonly get: {
        readonly parameters: {
          readonly 'path:conversation_id': string;
          readonly 'path:image_id': string;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['ImagePreparationResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/conversations/{conversation_id}/image-preparations/{image_id}/display': {
      readonly get: {
        readonly parameters: {
          readonly 'path:conversation_id': string;
          readonly 'path:image_id': string;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Readonly<Blob>;
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/conversations/{conversation_id}/image-preparations/{image_id}/finalize': {
      readonly post: {
        readonly parameters: {
          readonly 'path:conversation_id': string;
          readonly 'path:image_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '202': Api['schemas']['ImagePreparationReceipt'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/conversations/{conversation_id}/image-preparations/{image_id}/upload-access': {
      readonly post: {
        readonly parameters: {
          readonly 'path:conversation_id': string;
          readonly 'path:image_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['ImageUploadAccessResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/conversations/{conversation_id}/message-operations/{client_message_id}': {
      readonly get: {
        readonly parameters: {
          readonly 'path:conversation_id': string;
          readonly 'path:client_message_id': string;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200':
            | Api['schemas']['ConfirmedOperationResponse']
            | Api['schemas']['CancelledOperationResponse']
            | Api['schemas']['UnobservedOperationResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/conversations/{conversation_id}/message-operations/{client_message_id}/cancel': {
      readonly post: {
        readonly parameters: {
          readonly 'path:conversation_id': string;
          readonly 'path:client_message_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200':
            | Api['schemas']['ConfirmedOperationResponse']
            | Api['schemas']['CancelledOperationResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/conversations/{conversation_id}/messages': {
      readonly get: {
        readonly parameters: {
          readonly 'path:conversation_id': string;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['MessageHistoryResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
      readonly post: {
        readonly parameters: {
          readonly 'path:conversation_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['SendMessageBody'];
        readonly responses: {
          readonly '200':
            | Api['schemas']['ConfirmedOperationResponse']
            | Api['schemas']['CancelledOperationResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/conversations/{conversation_id}/messages/{message_id}/image': {
      readonly get: {
        readonly parameters: {
          readonly 'path:conversation_id': string;
          readonly 'path:message_id': string;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Readonly<Blob>;
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/conversations/{conversation_id}/messages/{message_id}/report-contexts': {
      readonly post: {
        readonly parameters: {
          readonly 'path:conversation_id': string;
          readonly 'path:message_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '201': Api['schemas']['MessageImageReportContextResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/conversations/{conversation_id}/participant': {
      readonly get: {
        readonly parameters: { readonly 'path:conversation_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['ChatParticipantResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/conversations/{conversation_id}/participant/avatar/{photo_version}': {
      readonly get: {
        readonly parameters: {
          readonly 'path:conversation_id': string;
          readonly 'path:photo_version': number;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Readonly<Blob>;
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/conversations/{conversation_id}/read-position': {
      readonly put: {
        readonly parameters: {
          readonly 'path:conversation_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['ConversationReadPositionBody'];
        readonly responses: {
          readonly '200': Api['schemas']['ConversationReadPositionResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/conversations/{conversation_id}/study-outcome': {
      readonly get: {
        readonly parameters: { readonly 'path:conversation_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OwnStudyOutcomeResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
      readonly put: {
        readonly parameters: {
          readonly 'path:conversation_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['StudyOutcomeBody'];
        readonly responses: {
          readonly '200': Api['schemas']['StudyOutcomeResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/conversations/{conversation_id}/study-prompt-visits': {
      readonly post: {
        readonly parameters: {
          readonly 'path:conversation_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['StudyPromptVisitBody'];
        readonly responses: {
          readonly '200':
            Api['schemas']['OfferedStudyPromptResponse'] | Api['schemas']['NoStudyPromptResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/discovery': {
      readonly get: {
        readonly parameters: {
          readonly 'query:mode': Api['schemas']['DiscoveryMode'];
          readonly 'query:view'?: Api['schemas']['DiscoveryView'];
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['DiscoveryPageResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/discovery/passes/{person_id}': {
      readonly put: {
        readonly parameters: {
          readonly 'path:person_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['ChangePassRequest'];
        readonly responses: {
          readonly '200': Api['schemas']['PrivatePassResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/events': {
      readonly get: {
        readonly parameters: { readonly 'header:Last-Event-ID'?: string | null };
        readonly body: undefined;
        readonly responses: {
          readonly '200': string;
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/me': {
      readonly get: {
        readonly parameters: Readonly<Record<string, never>>;
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['IdentityResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/me/blocks': {
      readonly get: {
        readonly parameters: { readonly 'query:cursor'?: string | null };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OwnBlocksResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/me/blocks/{person_id}': {
      readonly put: {
        readonly parameters: {
          readonly 'path:person_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['ChangeBlockRequest'];
        readonly responses: {
          readonly '200': Api['schemas']['BlockStateResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/me/deletion': {
      readonly post: {
        readonly parameters: {
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['DeleteAccountBody'];
        readonly responses: {
          readonly '200': Api['schemas']['DeletionReceiptResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/me/deletion-status': {
      readonly get: {
        readonly parameters: Readonly<Record<string, never>>;
        readonly body: undefined;
        readonly responses: {
          readonly '200':
            Api['schemas']['PendingDeletionResponse'] | Api['schemas']['ConfirmedDeletionResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/me/deletion-workflows': {
      readonly post: {
        readonly parameters: {
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
        };
        readonly body: Api['schemas']['DeletionPreparationBody'];
        readonly responses: {
          readonly '200': Api['schemas']['DeletionPreparationResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/me/feedback-summary': {
      readonly get: {
        readonly parameters: Readonly<Record<string, never>>;
        readonly body: undefined;
        readonly responses: {
          readonly '200':
            | Api['schemas']['BuildingFeedbackSummaryResponse']
            | Api['schemas']['AvailableFeedbackSummaryResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/me/goal': {
      readonly get: {
        readonly parameters: Readonly<Record<string, never>>;
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OwnGoalResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
      readonly put: {
        readonly parameters: {
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['SaveGoalRequest'];
        readonly responses: {
          readonly '200': Api['schemas']['GoalResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/me/goal/complete': {
      readonly post: {
        readonly parameters: {
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['CompleteGoalRequest'];
        readonly responses: {
          readonly '200': Api['schemas']['GoalResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/me/help-subjects': {
      readonly get: {
        readonly parameters: Readonly<Record<string, never>>;
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OwnHelpResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
      readonly put: {
        readonly parameters: {
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['SaveHelpRequest'];
        readonly responses: {
          readonly '200': Api['schemas']['HelpResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/me/notification-preference': {
      readonly get: {
        readonly parameters: Readonly<Record<string, never>>;
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['PreferenceResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
      readonly put: {
        readonly parameters: {
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['PreferenceBody'];
        readonly responses: {
          readonly '200': Api['schemas']['PreferenceResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/me/onboarding': {
      readonly get: {
        readonly parameters: Readonly<Record<string, never>>;
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OnboardingStatusResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/me/photo-review': {
      readonly get: {
        readonly parameters: Readonly<Record<string, never>>;
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OwnPhotoReviewResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/me/policy-status': {
      readonly get: {
        readonly parameters: Readonly<Record<string, never>>;
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['PolicyStatusResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/me/profile': {
      readonly get: {
        readonly parameters: Readonly<Record<string, never>>;
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OwnProfileResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
      readonly put: {
        readonly parameters: {
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['SaveProfileRequest'];
        readonly responses: {
          readonly '200': Api['schemas']['ProfileRevisionResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/me/registration': {
      readonly post: {
        readonly parameters: {
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['CompleteRegistrationRequest'];
        readonly responses: {
          readonly '200': Api['schemas']['RegistrationReceiptResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/me/registration-context': {
      readonly post: {
        readonly parameters: {
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '201': Api['schemas']['RegistrationContextResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/me/support-cases': {
      readonly get: {
        readonly parameters: Readonly<Record<string, never>>;
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['RecentSupportCasesResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
      readonly post: {
        readonly parameters: {
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['SupportBody'];
        readonly responses: {
          readonly '201': Api['schemas']['SupportReceiptResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/me/support-cases/{case_id}': {
      readonly get: {
        readonly parameters: { readonly 'path:case_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['SupportReceiptResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/me/visibility': {
      readonly put: {
        readonly parameters: {
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['ChangeVisibilityRequest'];
        readonly responses: {
          readonly '200': Api['schemas']['ProfileVisibilityResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/media/uploads': {
      readonly get: {
        readonly parameters: Readonly<Record<string, never>>;
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OwnPhotoResumeResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
      readonly post: {
        readonly parameters: {
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['StartPhotoRequest'];
        readonly responses: {
          readonly '202': Api['schemas']['PhotoUploadResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/media/uploads/{upload_id}/access': {
      readonly post: {
        readonly parameters: {
          readonly 'path:upload_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['UploadAccessResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/media/uploads/{upload_id}/cancel': {
      readonly post: {
        readonly parameters: {
          readonly 'path:upload_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['PhotoUploadResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/media/uploads/{upload_id}/finalize': {
      readonly post: {
        readonly parameters: {
          readonly 'path:upload_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '202': Api['schemas']['PhotoUploadResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/media/{upload_id}': {
      readonly get: {
        readonly parameters: { readonly 'path:upload_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['PhotoUploadResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/media/{upload_id}/display': {
      readonly get: {
        readonly parameters: { readonly 'path:upload_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Readonly<Blob>;
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts': {
      readonly get: {
        readonly parameters: {
          readonly 'query:account_id'?: string | null;
          readonly 'query:google_link_id'?: string | null;
          readonly 'query:google_issuer'?: string | null;
          readonly 'query:google_subject'?: string | null;
          readonly 'query:institutional_email'?: string | null;
          readonly 'query:name'?: string | null;
          readonly 'query:lifecycle'?: Api['schemas']['OperatorAccountLifecycle'];
          readonly 'query:hidden'?: boolean | null;
          readonly 'query:created_from'?: string | null;
          readonly 'query:created_before'?: string | null;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorAccountsResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}': {
      readonly get: {
        readonly parameters: { readonly 'path:account_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorAccountDetailResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/ai-jobs': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'query:kind'?: Api['schemas']['AiKind'] | null;
          readonly 'query:state'?: Api['schemas']['JobState'] | null;
          readonly 'query:created_from'?: string | null;
          readonly 'query:created_before'?: string | null;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorAiJobsResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/ai-jobs/{job_id}': {
      readonly get: {
        readonly parameters: { readonly 'path:account_id': string; readonly 'path:job_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorAiJobResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/ban': {
      readonly put: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['ChangeBanBody'];
        readonly responses: {
          readonly '200': Api['schemas']['BanChangeResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/chat-image-uploads': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'query:conversation_id'?: string | null;
          readonly 'query:state'?: Api['schemas']['ChatImageState'] | null;
          readonly 'query:created_from'?: string | null;
          readonly 'query:created_before'?: string | null;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorChatImageUploadsResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/chat-image-uploads/{image_id}/attempts/{attempt_id}/{kind}': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'path:image_id': string;
          readonly 'path:attempt_id': string;
          readonly 'path:kind': Api['schemas']['OperatorChatMediaKind'];
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Readonly<Blob>;
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/chat-image-uploads/{image_id}/history': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'path:image_id': string;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorChatImageHistoryResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/connection-requests': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'query:peer_id'?: string | null;
          readonly 'query:direction'?: Api['schemas']['OperatorRequestDirection'] | null;
          readonly 'query:mode'?: Api['schemas']['DiscoveryMode'] | null;
          readonly 'query:state'?: Api['schemas']['RequestState'] | null;
          readonly 'query:sent_from'?: string | null;
          readonly 'query:sent_before'?: string | null;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorRequestsResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/connection-requests/{request_id}/disclosures': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'path:request_id': string;
          readonly 'query:viewer_id'?: string | null;
          readonly 'query:stored_version'?: number | null;
          readonly 'query:created_from'?: string | null;
          readonly 'query:created_before'?: string | null;
          readonly 'query:disclosure_id'?: string | null;
          readonly 'query:acknowledgement_id'?: string | null;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorDisclosuresResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/connection-requests/{request_id}/history': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'path:request_id': string;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorRequestHistoryResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/conversations': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorConversationsResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/goals': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'query:state'?: Api['schemas']['OperatorGoalState'] | null;
          readonly 'query:created_from'?: string | null;
          readonly 'query:created_before'?: string | null;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorGoalsResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/goals/{goal_id}/history': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'path:goal_id': string;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorGoalHistoryResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/help-history': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorHelpHistoryResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/identity-links': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorIdentityLinksResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/lifecycle-history': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorLifecycleHistoryResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/membership-verification': {
      readonly get: {
        readonly parameters: { readonly 'path:account_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['ManualMembershipContextResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/membership-verifications': {
      readonly post: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['ManualMembershipBody'];
        readonly responses: {
          readonly '200': Api['schemas']['ManualMembershipResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/message-operations': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorMessageOperationsResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/message-operations/{operation_id}': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'path:operation_id': string;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorMessageOperationResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/notification-preference-history': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorPreferenceHistoryResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/peer-feedback': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'query:peer_id'?: string | null;
          readonly 'query:direction'?: Api['schemas']['OperatorFeedbackDirection'] | null;
          readonly 'query:removed'?: boolean | null;
          readonly 'query:changed_from'?: string | null;
          readonly 'query:changed_before'?: string | null;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorFeedbackRootsResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/peer-feedback/{feedback_id}/history': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'path:feedback_id': string;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorFeedbackHistoryResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/peer-feedback/{feedback_id}/removals': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'path:feedback_id': string;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorFeedbackRemovalsResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/photo-review': {
      readonly get: {
        readonly parameters: { readonly 'path:account_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['PhotoReviewContextResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/photo-reviews': {
      readonly post: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['PhotoReviewBody'];
        readonly responses: {
          readonly '200': Api['schemas']['PhotoReviewResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/photo-uploads': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'query:state'?: Api['schemas']['PhotoUploadState'] | null;
          readonly 'query:created_from'?: string | null;
          readonly 'query:created_before'?: string | null;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorPhotoUploadsResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/photo-uploads/{upload_id}/attempts/{attempt_id}/{kind}': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'path:upload_id': string;
          readonly 'path:attempt_id': string;
          readonly 'path:kind': Api['schemas']['OperatorProfileMediaKind'];
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Readonly<Blob>;
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/photo-uploads/{upload_id}/history': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'path:upload_id': string;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorPhotoHistoryResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/profile-history': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorProfileHistoryResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/relationships/{relationship_id}/block-history': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'path:relationship_id': string;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorBlockHistoryResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/accounts/{account_id}/visibility-history': {
      readonly get: {
        readonly parameters: {
          readonly 'path:account_id': string;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorVisibilityHistoryResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/audits': {
      readonly get: {
        readonly parameters: {
          readonly 'query:operator_id'?: string | null;
          readonly 'query:action'?: Api['schemas']['OperatorAction'] | null;
          readonly 'query:requested_kind'?: Api['schemas']['OperatorResourceKind'] | null;
          readonly 'query:requested_id'?: string | null;
          readonly 'query:http_request_id'?: string | null;
          readonly 'query:action_id'?: string | null;
          readonly 'query:trace_id'?: string | null;
          readonly 'query:occurred_from'?: string | null;
          readonly 'query:occurred_before'?: string | null;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorAuditsResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/audits/{audit_id}': {
      readonly get: {
        readonly parameters: { readonly 'path:audit_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorAuditDetailResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/cases': {
      readonly get: {
        readonly parameters: {
          readonly 'query:case_id'?: string | null;
          readonly 'query:actor_id'?: string | null;
          readonly 'query:topic'?: Api['schemas']['SupportTopic'] | null;
          readonly 'query:status'?: Api['schemas']['SupportStatus'] | null;
          readonly 'query:anonymous'?: boolean | null;
          readonly 'query:received_from'?: string | null;
          readonly 'query:received_before'?: string | null;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorSupportInboxResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/cases/{case_id}': {
      readonly get: {
        readonly parameters: { readonly 'path:case_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorSupportResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/cases/{case_id}/history': {
      readonly get: {
        readonly parameters: {
          readonly 'path:case_id': string;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorSupportHistoryResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/cases/{case_id}/status': {
      readonly put: {
        readonly parameters: {
          readonly 'path:case_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['SupportStatusBody'];
        readonly responses: {
          readonly '200': Api['schemas']['SupportReceiptResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/conversations/{conversation_id}/messages': {
      readonly get: {
        readonly parameters: {
          readonly 'path:conversation_id': string;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorMessagesResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/delivery-sources': {
      readonly get: {
        readonly parameters: {
          readonly 'query:actor_id'?: string | null;
          readonly 'query:kind'?: Api['schemas']['SourceKind'] | null;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['SourcesResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/delivery-sources/{source_id}': {
      readonly get: {
        readonly parameters: { readonly 'path:source_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['SourceDetailResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/events': {
      readonly get: {
        readonly parameters: {
          readonly 'query:subject_account_id'?: string | null;
          readonly 'query:http_request_id'?: string | null;
          readonly 'query:action_id'?: string | null;
          readonly 'query:trace_id'?: string | null;
          readonly 'query:kind'?: Api['schemas']['OperatorEventKind'] | null;
          readonly 'query:occurred_from'?: string | null;
          readonly 'query:occurred_before'?: string | null;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorEventsResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/events/{event_id}': {
      readonly get: {
        readonly parameters: { readonly 'path:event_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorEventResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/reports': {
      readonly get: {
        readonly parameters: {
          readonly 'query:reporter_id'?: string | null;
          readonly 'query:target_id'?: string | null;
          readonly 'query:context_id'?: string | null;
          readonly 'query:category'?: Api['schemas']['ReportCategory'] | null;
          readonly 'query:submitted_from'?: string | null;
          readonly 'query:submitted_before'?: string | null;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorReportsResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/reports/{report_id}': {
      readonly get: {
        readonly parameters: { readonly 'path:report_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['OperatorReportDetailResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/reports/{report_id}/reviews': {
      readonly get: {
        readonly parameters: {
          readonly 'path:report_id': string;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['ReportReviewHistoryResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
      readonly post: {
        readonly parameters: {
          readonly 'path:report_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['ReviewReportBody'];
        readonly responses: {
          readonly '200': Api['schemas']['ReportReviewResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/reports/{report_id}/triage': {
      readonly get: {
        readonly parameters: { readonly 'path:report_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['ReportTriageReadResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
      readonly post: {
        readonly parameters: {
          readonly 'path:report_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['ReportTriageBody'];
        readonly responses: {
          readonly '200': Api['schemas']['ReportTriageResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/operator/reports/{report_id}/triage-source': {
      readonly get: {
        readonly parameters: { readonly 'path:report_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['ReportTriageContextResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/people/{person_id}': {
      readonly get: {
        readonly parameters: { readonly 'path:person_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['PublicProfileResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/people/{person_id}/feedback-summary': {
      readonly get: {
        readonly parameters: { readonly 'path:person_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200':
            | Api['schemas']['BuildingFeedbackSummaryResponse']
            | Api['schemas']['AvailableFeedbackSummaryResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/people/{person_id}/photo/{photo_version}': {
      readonly get: {
        readonly parameters: {
          readonly 'path:person_id': string;
          readonly 'path:photo_version': number;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Readonly<Blob>;
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/policies/{kind}': {
      readonly get: {
        readonly parameters: {
          readonly 'path:kind': Api['schemas']['PolicyKind'];
          readonly 'query:version'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['PublishedPolicyResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/policies/{kind}/versions': {
      readonly get: {
        readonly parameters: {
          readonly 'path:kind': Api['schemas']['PolicyKind'];
          readonly 'query:limit'?: number;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['PolicyHistoryResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/profile-reference-data': {
      readonly get: {
        readonly parameters: Readonly<Record<string, never>>;
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['ProfileReferenceResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/reports': {
      readonly post: {
        readonly parameters: {
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body:
          Api['schemas']['ProfileReportRequest'] | Api['schemas']['MessageImageReportRequest'];
        readonly responses: {
          readonly '201': Api['schemas']['ReportReceipt'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '408': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/requests': {
      readonly get: {
        readonly parameters: {
          readonly 'query:box'?: Api['schemas']['RequestBox'];
          readonly 'query:view'?: Api['schemas']['RequestListView'];
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['RequestPageResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
      readonly post: {
        readonly parameters: {
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['SendRequestBody'];
        readonly responses: {
          readonly '200':
            Api['schemas']['RequestMutationResponse'] | Api['schemas']['ConnectedResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/requests/preview': {
      readonly post: {
        readonly parameters: {
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['PreviewRequestBody'];
        readonly responses: {
          readonly '200':
            | Api['schemas']['PreviewResponse']
            | Api['schemas']['RequestMutationResponse']
            | Api['schemas']['ConnectedResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/requests/{request_id}': {
      readonly get: {
        readonly parameters: { readonly 'path:request_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['RequestDetailResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/requests/{request_id}/accept': {
      readonly post: {
        readonly parameters: {
          readonly 'path:request_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['RequestActionBody'];
        readonly responses: {
          readonly '200': Api['schemas']['RequestMutationResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/requests/{request_id}/decline': {
      readonly post: {
        readonly parameters: {
          readonly 'path:request_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['RequestActionBody'];
        readonly responses: {
          readonly '200': Api['schemas']['RequestMutationResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/requests/{request_id}/undo-decline': {
      readonly post: {
        readonly parameters: {
          readonly 'path:request_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['RequestActionBody'];
        readonly responses: {
          readonly '200': Api['schemas']['RequestMutationResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/requests/{request_id}/viewed': {
      readonly post: {
        readonly parameters: {
          readonly 'path:request_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['ViewRequestBody'];
        readonly responses: {
          readonly '200': Api['schemas']['ViewedResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/requests/{request_id}/withdraw': {
      readonly post: {
        readonly parameters: {
          readonly 'path:request_id': string;
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['RequestActionBody'];
        readonly responses: {
          readonly '200': Api['schemas']['RequestMutationResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/subjects': {
      readonly get: {
        readonly parameters: {
          readonly 'query:query'?: string;
          readonly 'query:limit'?: number;
          readonly 'query:cursor'?: string | null;
        };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['SubjectsResponse'];
          readonly '400': Api['schemas']['ProblemResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/support-cases': {
      readonly get: {
        readonly parameters: Readonly<Record<string, never>>;
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['RecentSupportCasesResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
      readonly post: {
        readonly parameters: {
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['SupportBody'];
        readonly responses: {
          readonly '201': Api['schemas']['SupportReceiptResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/support-cases/{case_id}': {
      readonly get: {
        readonly parameters: { readonly 'path:case_id': string };
        readonly body: undefined;
        readonly responses: {
          readonly '200': Api['schemas']['SupportReceiptResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/support-context': {
      readonly post: {
        readonly parameters: {
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
        };
        readonly body: Api['schemas']['SupportPreparationBody'];
        readonly responses: {
          readonly '200': Api['schemas']['SupportPreparationResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '404': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
    readonly '/api/v1/telemetry/events': {
      readonly post: {
        readonly parameters: {
          readonly 'header:origin'?: string | null;
          readonly 'header:x-csrf-token'?: string | null;
          readonly 'header:idempotency-key': string;
        };
        readonly body: Api['schemas']['ObservationBatchBody'];
        readonly responses: {
          readonly '200': Api['schemas']['ObservationBatchResponse'];
          readonly '401': Api['schemas']['ProblemResponse'];
          readonly '403': Api['schemas']['ProblemResponse'];
          readonly '409': Api['schemas']['ProblemResponse'];
          readonly '413': Api['schemas']['ProblemResponse'];
          readonly '415': Api['schemas']['ProblemResponse'];
          readonly '422': Api['schemas']['ProblemResponse'];
          readonly '429': Api['schemas']['ProblemResponse'];
          readonly '500': Api['schemas']['ProblemResponse'];
          readonly '503': Api['schemas']['ProblemResponse'];
        };
      };
    };
  };
}
