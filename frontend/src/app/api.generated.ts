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
    readonly AiKind: 'clarify_goal' | 'suggest_subject' | 'assess_photo' | 'triage_report';
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
    readonly NoStudyPromptResponse: { readonly outcome?: 'no_offer' };
    readonly NotificationMode: 'messages_and_requests' | 'all_updates';
    readonly Observation: 'yes' | 'no' | 'uncertain';
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
      | 'search_reports'
      | 'read_support_case'
      | 'read_report'
      | 'read_media'
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
      readonly actual_source_upload_id: string | null;
      readonly id: string;
      readonly occurred_at: string;
      readonly operator_access_changed_at: string;
      readonly operator_access_version: number;
      readonly operator_id: string;
      readonly origin: Api['schemas']['OperatorEventOriginResponse'];
      readonly outcome: Api['schemas']['OperatorAuditOutcome'];
      readonly query_fingerprinted: boolean;
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
    readonly OperatorResourceKind:
      | 'account'
      | 'conversation'
      | 'message'
      | 'event'
      | 'audit'
      | 'report'
      | 'profile_media'
      | 'support_case';
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
    readonly OperatorSupportResponse: {
      readonly actor_id: string | null;
      readonly details?: string | null;
      readonly message: string;
      readonly receipt: Api['schemas']['SupportReceiptResponse'];
      readonly reply_address: string;
      readonly topic: Api['schemas']['SupportTopic'];
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
      readonly blurred: Api['schemas']['Observation'];
      readonly face_visible: Api['schemas']['Observation'];
      readonly multiple_people: Api['schemas']['Observation'];
    };
    readonly PhotoResumeItemResponse: {
      readonly source_sha256: string;
      readonly upload: Api['schemas']['PhotoUploadResponse'];
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
    readonly RestoreRequirement: 'photo' | 'study_context';
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
  };
}
