"""Capture retained source references and bounded two-sink external delivery metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0055_external_delivery"
down_revision: str | Sequence[str] | None = "0054_identity_recreation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE_AUDIT_SHAPE = (
    "(((((((action='search_accounts' AND resource_kind='account' AND requested_id IS NULL AND"
    " outcome='search' AND query_fingerprint IS NOT NULL AND octet_length(query_fingerprint)="
    "32 AND cardinality(result_ids)<=20) OR (action='read_account' AND resource_kind='account"
    "' AND requested_id IS NOT NULL AND query_fingerprint IS NULL AND ((outcome='read' AND re"
    "sult_ids=ARRAY[requested_id]) OR (outcome='not_found' AND cardinality(result_ids)=0))) O"
    "R (action='read_conversation_messages' AND resource_kind='conversation' AND requested_id"
    " IS NOT NULL AND query_fingerprint IS NULL AND ((outcome='read' AND cardinality(result_i"
    "ds)<=50) OR (outcome='not_found' AND cardinality(result_ids)=0)))) OR (action='search_ev"
    "ents' AND resource_kind='event' AND requested_id IS NULL AND outcome='search' AND query_"
    "fingerprint IS NOT NULL AND octet_length(query_fingerprint)=32 AND cardinality(result_id"
    "s)<=50) OR (action IN ('read_event','read_audit') AND resource_kind=CASE WHEN action='re"
    "ad_event' THEN 'event' ELSE 'audit' END AND requested_id IS NOT NULL AND query_fingerpri"
    "nt IS NULL AND ((outcome='read' AND result_ids=ARRAY[requested_id]) OR (outcome='not_fou"
    "nd' AND cardinality(result_ids)=0)))) OR (action='search_reports' AND resource_kind='rep"
    "ort' AND requested_id IS NULL AND outcome='search' AND query_fingerprint IS NOT NULL AND"
    " octet_length(query_fingerprint)=32 AND cardinality(result_ids)<=50) OR (action='read_re"
    "port' AND resource_kind='report' AND requested_id IS NOT NULL AND query_fingerprint IS N"
    "ULL AND ((outcome='read' AND result_ids=ARRAY[requested_id]) OR (outcome='not_found' AND"
    " cardinality(result_ids)=0)))) AND requested_media_owner_id IS NULL AND requested_media_"
    "attempt_id IS NULL AND requested_media_kind IS NULL AND actual_source_upload_id IS NULL)"
    " OR (action='read_media' AND resource_kind='profile_media' AND requested_id IS NOT NULL "
    "AND query_fingerprint IS NULL AND requested_media_owner_id IS NOT NULL AND requested_med"
    "ia_attempt_id IS NOT NULL AND requested_media_kind IS NOT NULL AND requested_media_kind "
    "IN ('original','display') AND ((outcome='read' AND result_ids=ARRAY[requested_id] AND ac"
    "tual_source_upload_id IS NOT NULL AND actual_source_upload_id=requested_id) OR (outcome="
    "'not_found' AND cardinality(result_ids)=0 AND (actual_source_upload_id IS NULL OR actual"
    "_source_upload_id=requested_id))))) OR (action='read_support_case' AND resource_kind='su"
    "pport_case' AND requested_id IS NOT NULL AND query_fingerprint IS NULL AND requested_med"
    "ia_owner_id IS NULL AND requested_media_attempt_id IS NULL AND requested_media_kind IS N"
    "ULL AND actual_source_upload_id IS NULL AND ((outcome='read' AND result_ids=ARRAY[reques"
    "ted_id]) OR (outcome='not_found' AND cardinality(result_ids)=0)))) OR (action='search_su"
    "pport_cases' AND resource_kind='support_case' AND requested_id IS NULL AND outcome='sear"
    "ch' AND query_fingerprint IS NOT NULL AND octet_length(query_fingerprint)=32 AND cardina"
    "lity(result_ids)<=50 AND requested_media_owner_id IS NULL AND requested_media_attempt_id"
    " IS NULL AND requested_media_kind IS NULL AND actual_source_upload_id IS NULL)"
)

BEFORE_EVENT_SHAPE = (
    "((((((((((((((((((((((((((kind != 'ai_job.completed' AND ai_job_id IS NULL AND ai_kind I"
    "S NULL AND ai_state IS NULL AND ai_reason IS NULL) AND ((kind IN ('goal.saved', 'goal.co"
    "mpleted') AND goal_id IS NOT NULL AND goal_version IS NOT NULL AND topic_present IS NOT "
    "NULL AND shared_learning IS NOT NULL AND profile_version IS NULL AND visibility_version "
    "IS NULL AND onboarding_task IS NULL) OR (kind = 'profile.ready' AND profile_version IS N"
    "OT NULL AND onboarding_task IS NOT NULL AND onboarding_task IN ('find_help', 'offer_help"
    "') AND goal_id IS NULL AND goal_version IS NULL AND visibility_version IS NULL AND subje"
    "ct_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL) OR (kind IN ('profi"
    "le.hidden', 'profile.restored', 'discovery.exposure_confirmed') AND visibility_version I"
    "S NOT NULL AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND "
    "onboarding_task IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_lear"
    "ning IS NULL) OR (kind = 'auth.email_confirmed' AND goal_id IS NULL AND goal_version IS "
    "NULL AND profile_version IS NULL AND visibility_version IS NULL AND onboarding_task IS N"
    "ULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL))) OR ("
    "kind = 'ai_job.completed' AND ai_job_id IS NOT NULL AND ai_kind IS NOT NULL AND ai_kind "
    "IN ('clarify_goal','suggest_subject','assess_photo','triage_report') AND ai_state IS NOT"
    " NULL AND ai_state IN ('succeeded','failed','cancelled','expired') AND (ai_reason IS NUL"
    "L OR (ai_state IN ('failed','expired') AND ai_reason IN ('transient','invalid_output','i"
    "nvalid_input','timeout','auth_unavailable','rate_limited','account_unavailable','stale_s"
    "ource','executor_lost'))) AND goal_id IS NULL AND goal_version IS NULL AND profile_versi"
    "on IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NU"
    "LL AND shared_learning IS NULL AND onboarding_task IS NULL)) AND report_id IS NULL AND b"
    "lock_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL) OR ((goal_id"
    " IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibility_version IS "
    "NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND on"
    "boarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND"
    " ai_reason IS NULL) AND ((kind = 'report.created' AND report_id IS NOT NULL AND block_re"
    "lationship_id IS NULL AND block_version IS NULL AND blocked IS NULL) OR (kind = 'block.c"
    "hanged' AND report_id IS NULL AND block_relationship_id IS NOT NULL AND block_version IS"
    " NOT NULL AND blocked IS NOT NULL)))) AND private_pass_id IS NULL AND private_pass_versi"
    "on IS NULL AND private_passed IS NULL) OR (kind = 'discovery.pass_changed' AND private_p"
    "ass_id IS NOT NULL AND private_pass_version IS NOT NULL AND private_passed IS NOT NULL A"
    "ND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibility_v"
    "ersion IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS N"
    "ULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state I"
    "S NULL AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND"
    " block_version IS NULL AND blocked IS NULL)) AND connection_request_id IS NULL AND conne"
    "ction_request_version IS NULL AND connection_request_state IS NULL AND connection_reques"
    "t_recipient_id IS NULL AND request_initiator_id IS NULL) OR (kind = 'request.changed' AN"
    "D connection_request_id IS NOT NULL AND connection_request_version IS NOT NULL AND conne"
    "ction_request_state IS NOT NULL AND connection_request_recipient_id IS NOT NULL AND (req"
    "uest_initiator_id IS NULL OR request_initiator_id IN (account_id, connection_request_rec"
    "ipient_id)) AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND"
    " visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_"
    "learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL A"
    "ND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_i"
    "d IS NULL AND block_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND "
    "private_pass_version IS NULL AND private_passed IS NULL)) AND request_view_ack_id IS NUL"
    "L) OR (kind = 'request.view_acknowledged' AND request_view_ack_id IS NOT NULL AND goal_i"
    "d IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibility_version IS"
    " NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND o"
    "nboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AN"
    "D ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND block_ve"
    "rsion IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_version I"
    "S NULL AND private_passed IS NULL AND connection_request_id IS NULL AND connection_reque"
    "st_version IS NULL AND connection_request_state IS NULL AND connection_request_recipient"
    "_id IS NULL AND request_initiator_id IS NULL)) AND message_operation_id IS NULL AND mess"
    "age_operation_state IS NULL) OR (message_operation_id IS NOT NULL AND message_operation_"
    "state IS NOT NULL AND ((kind='message.confirmed' AND message_operation_state='confirmed'"
    ") OR (kind='message.cancelled' AND message_operation_state='cancelled')) AND goal_id IS "
    "NULL AND goal_version IS NULL AND profile_version IS NULL AND visibility_version IS NULL"
    " AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboar"
    "ding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_"
    "reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND block_version"
    " IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NUL"
    "L AND private_passed IS NULL AND connection_request_id IS NULL AND connection_request_ve"
    "rsion IS NULL AND connection_request_state IS NULL AND connection_request_recipient_id I"
    "S NULL AND request_view_ack_id IS NULL AND request_initiator_id IS NULL)) AND conversati"
    "on_read_id IS NULL AND read_conversation_id IS NULL) OR (kind='conversation.read_acknowl"
    "edged' AND conversation_read_id IS NOT NULL AND read_conversation_id IS NOT NULL AND goa"
    "l_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibility_version"
    " IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AN"
    "D onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL"
    " AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND block"
    "_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_versio"
    "n IS NULL AND private_passed IS NULL AND connection_request_id IS NULL AND connection_re"
    "quest_version IS NULL AND connection_request_state IS NULL AND connection_request_recipi"
    "ent_id IS NULL AND message_operation_id IS NULL AND message_operation_state IS NULL AND "
    "request_view_ack_id IS NULL AND request_initiator_id IS NULL)) AND goal_share_id IS NULL"
    " AND goal_share_context_version IS NULL AND goal_share_conversation_id IS NULL) OR (kind"
    "='conversation.goal_shared' AND goal_share_id IS NOT NULL AND goal_share_context_version"
    " IS NOT NULL AND goal_share_conversation_id IS NOT NULL AND goal_id IS NULL AND goal_ver"
    "sion IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND subject_id I"
    "S NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL"
    " AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AN"
    "D report_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AND bloc"
    "ked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND private_pas"
    "sed IS NULL AND connection_request_id IS NULL AND connection_request_version IS NULL AND"
    " connection_request_state IS NULL AND connection_request_recipient_id IS NULL AND conver"
    "sation_read_id IS NULL AND read_conversation_id IS NULL AND message_operation_id IS NULL"
    " AND message_operation_state IS NULL AND request_view_ack_id IS NULL AND request_initiat"
    "or_id IS NULL)) AND operator_audit_id IS NULL AND operator_access_version IS NULL AND op"
    "erator_action IS NULL) OR (kind='operator.inspected' AND operator_audit_id IS NOT NULL A"
    "ND operator_access_version IS NOT NULL AND operator_action IS NOT NULL AND operator_acti"
    "on IN ('search_accounts','read_account','read_conversation_messages','search_events','re"
    "ad_event','read_audit','search_reports','read_report','read_media','read_support_case','"
    "search_support_cases') AND goal_id IS NULL AND goal_version IS NULL AND profile_version "
    "IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL "
    "AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kin"
    "d IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_rel"
    "ationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND private_pass_id I"
    "S NULL AND private_pass_version IS NULL AND private_passed IS NULL AND connection_reques"
    "t_id IS NULL AND connection_request_version IS NULL AND connection_request_state IS NULL"
    " AND connection_request_recipient_id IS NULL AND goal_share_id IS NULL AND goal_share_co"
    "nversation_id IS NULL AND goal_share_context_version IS NULL AND conversation_read_id IS"
    " NULL AND read_conversation_id IS NULL AND message_operation_id IS NULL AND message_oper"
    "ation_state IS NULL AND request_view_ack_id IS NULL AND request_initiator_id IS NULL)) A"
    "ND study_outcome_id IS NULL AND study_conversation_id IS NULL AND study_outcome_version "
    "IS NULL AND study_answer IS NULL AND peer_feedback_id IS NULL AND peer_feedback_version "
    "IS NULL AND feedback_again IS NULL AND study_prompt_id IS NULL AND study_prompt_conversa"
    "tion_id IS NULL) OR (kind='study.reported' AND study_outcome_id IS NOT NULL AND study_co"
    "nversation_id IS NOT NULL AND study_outcome_version IS NOT NULL AND study_answer IS NOT "
    "NULL AND peer_feedback_id IS NULL AND peer_feedback_version IS NULL AND feedback_again I"
    "S NULL AND study_prompt_id IS NULL AND study_prompt_conversation_id IS NULL AND study_an"
    "swer IN ('yes','not_yet','did_not_work_out') AND goal_id IS NULL AND goal_version IS NUL"
    "L AND profile_version IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND "
    "topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job"
    "_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id"
    " IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL"
    " AND private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL"
    " AND connection_request_id IS NULL AND connection_request_version IS NULL AND connection"
    "_request_state IS NULL AND connection_request_recipient_id IS NULL AND goal_share_id IS "
    "NULL AND goal_share_conversation_id IS NULL AND goal_share_context_version IS NULL AND c"
    "onversation_read_id IS NULL AND read_conversation_id IS NULL AND message_operation_id IS"
    " NULL AND message_operation_state IS NULL AND request_view_ack_id IS NULL AND request_in"
    "itiator_id IS NULL AND operator_audit_id IS NULL AND operator_access_version IS NULL AND"
    " operator_action IS NULL) OR (kind='feedback.saved' AND study_outcome_id IS NULL AND stu"
    "dy_conversation_id IS NULL AND study_outcome_version IS NULL AND study_answer IS NULL AN"
    "D peer_feedback_id IS NOT NULL AND peer_feedback_version IS NOT NULL AND feedback_again "
    "IS NOT NULL AND study_prompt_id IS NULL AND study_prompt_conversation_id IS NULL AND fee"
    "dback_again IN ('yes','maybe','no') AND goal_id IS NULL AND goal_version IS NULL AND pro"
    "file_version IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_pre"
    "sent IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NU"
    "LL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL "
    "AND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND priv"
    "ate_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL AND conn"
    "ection_request_id IS NULL AND connection_request_version IS NULL AND connection_request_"
    "state IS NULL AND connection_request_recipient_id IS NULL AND goal_share_id IS NULL AND "
    "goal_share_conversation_id IS NULL AND goal_share_context_version IS NULL AND conversati"
    "on_read_id IS NULL AND read_conversation_id IS NULL AND message_operation_id IS NULL AND"
    " message_operation_state IS NULL AND request_view_ack_id IS NULL AND request_initiator_i"
    "d IS NULL AND operator_audit_id IS NULL AND operator_access_version IS NULL AND operator"
    "_action IS NULL) OR (kind='study.prompt_offered' AND study_outcome_id IS NULL AND study_"
    "conversation_id IS NULL AND study_outcome_version IS NULL AND study_answer IS NULL AND p"
    "eer_feedback_id IS NULL AND peer_feedback_version IS NULL AND feedback_again IS NULL AND"
    " study_prompt_id IS NOT NULL AND study_prompt_conversation_id IS NOT NULL AND TRUE AND g"
    "oal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibility_versi"
    "on IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL "
    "AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NU"
    "LL AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND blo"
    "ck_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_vers"
    "ion IS NULL AND private_passed IS NULL AND connection_request_id IS NULL AND connection_"
    "request_version IS NULL AND connection_request_state IS NULL AND connection_request_reci"
    "pient_id IS NULL AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND go"
    "al_share_context_version IS NULL AND conversation_read_id IS NULL AND read_conversation_"
    "id IS NULL AND message_operation_id IS NULL AND message_operation_state IS NULL AND requ"
    "est_view_ack_id IS NULL AND request_initiator_id IS NULL AND operator_audit_id IS NULL A"
    "ND operator_access_version IS NULL AND operator_action IS NULL)) AND help_version IS NUL"
    "L AND photo_version IS NULL) OR (kind='profile.saved' AND profile_version IS NOT NULL AN"
    "D goal_id IS NULL AND goal_version IS NULL AND visibility_version IS NULL AND subject_id"
    " IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NU"
    "LL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL "
    "AND report_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AND bl"
    "ocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND private_p"
    "assed IS NULL AND connection_request_id IS NULL AND connection_request_version IS NULL A"
    "ND connection_request_state IS NULL AND connection_request_recipient_id IS NULL AND goal"
    "_share_id IS NULL AND goal_share_conversation_id IS NULL AND goal_share_context_version "
    "IS NULL AND conversation_read_id IS NULL AND read_conversation_id IS NULL AND message_op"
    "eration_id IS NULL AND message_operation_state IS NULL AND request_view_ack_id IS NULL A"
    "ND request_initiator_id IS NULL AND operator_audit_id IS NULL AND operator_access_versio"
    "n IS NULL AND operator_action IS NULL AND study_outcome_id IS NULL AND study_conversatio"
    "n_id IS NULL AND study_outcome_version IS NULL AND study_answer IS NULL AND peer_feedbac"
    "k_id IS NULL AND peer_feedback_version IS NULL AND feedback_again IS NULL AND study_prom"
    "pt_id IS NULL AND study_prompt_conversation_id IS NULL AND help_version IS NULL AND phot"
    "o_version IS NULL) OR (kind='help.saved' AND help_version IS NOT NULL AND goal_id IS NUL"
    "L AND goal_version IS NULL AND profile_version IS NULL AND visibility_version IS NULL AN"
    "D subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboardin"
    "g_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_rea"
    "son IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND block_version IS"
    " NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL A"
    "ND private_passed IS NULL AND connection_request_id IS NULL AND connection_request_versi"
    "on IS NULL AND connection_request_state IS NULL AND connection_request_recipient_id IS N"
    "ULL AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND goal_share_cont"
    "ext_version IS NULL AND conversation_read_id IS NULL AND read_conversation_id IS NULL AN"
    "D message_operation_id IS NULL AND message_operation_state IS NULL AND request_view_ack_"
    "id IS NULL AND request_initiator_id IS NULL AND operator_audit_id IS NULL AND operator_a"
    "ccess_version IS NULL AND operator_action IS NULL AND study_outcome_id IS NULL AND study"
    "_conversation_id IS NULL AND study_outcome_version IS NULL AND study_answer IS NULL AND "
    "peer_feedback_id IS NULL AND peer_feedback_version IS NULL AND feedback_again IS NULL AN"
    "D study_prompt_id IS NULL AND study_prompt_conversation_id IS NULL AND photo_version IS "
    "NULL) OR (kind='photo.published' AND photo_version IS NOT NULL AND goal_id IS NULL AND g"
    "oal_version IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND subje"
    "ct_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_task "
    "IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS "
    "NULL AND report_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL A"
    "ND blocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND priv"
    "ate_passed IS NULL AND connection_request_id IS NULL AND connection_request_version IS N"
    "ULL AND connection_request_state IS NULL AND connection_request_recipient_id IS NULL AND"
    " goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND goal_share_context_ver"
    "sion IS NULL AND conversation_read_id IS NULL AND read_conversation_id IS NULL AND messa"
    "ge_operation_id IS NULL AND message_operation_state IS NULL AND request_view_ack_id IS N"
    "ULL AND request_initiator_id IS NULL AND operator_audit_id IS NULL AND operator_access_v"
    "ersion IS NULL AND operator_action IS NULL AND study_outcome_id IS NULL AND study_conver"
    "sation_id IS NULL AND study_outcome_version IS NULL AND study_answer IS NULL AND peer_fe"
    "edback_id IS NULL AND peer_feedback_version IS NULL AND feedback_again IS NULL AND study"
    "_prompt_id IS NULL AND study_prompt_conversation_id IS NULL AND help_version IS NULL)) A"
    "ND lifecycle_revision_id IS NULL AND lifecycle_account_id IS NULL AND lifecycle_version "
    "IS NULL AND lifecycle_operation IS NULL) OR (kind='account.lifecycle_changed' AND lifecy"
    "cle_revision_id IS NOT NULL AND lifecycle_account_id IS NOT NULL AND lifecycle_version I"
    "S NOT NULL AND lifecycle_version>0 AND lifecycle_operation IS NOT NULL AND lifecycle_ope"
    "ration IN ('ban','unban','delete') AND goal_id IS NULL AND goal_version IS NULL AND prof"
    "ile_version IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_pres"
    "ent IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NUL"
    "L AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL A"
    "ND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND priva"
    "te_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL AND conne"
    "ction_request_id IS NULL AND connection_request_version IS NULL AND connection_request_s"
    "tate IS NULL AND connection_request_recipient_id IS NULL AND goal_share_id IS NULL AND g"
    "oal_share_conversation_id IS NULL AND goal_share_context_version IS NULL AND conversatio"
    "n_read_id IS NULL AND read_conversation_id IS NULL AND message_operation_id IS NULL AND "
    "message_operation_state IS NULL AND request_view_ack_id IS NULL AND request_initiator_id"
    " IS NULL AND operator_audit_id IS NULL AND operator_access_version IS NULL AND operator_"
    "action IS NULL AND study_outcome_id IS NULL AND study_conversation_id IS NULL AND study_"
    "outcome_version IS NULL AND study_answer IS NULL AND peer_feedback_id IS NULL AND peer_f"
    "eedback_version IS NULL AND feedback_again IS NULL AND study_prompt_id IS NULL AND study"
    "_prompt_conversation_id IS NULL AND help_version IS NULL AND photo_version IS NULL)) AND"
    " notification_preference_version IS NULL AND support_case_id IS NULL AND support_case_ve"
    "rsion IS NULL) OR (kind='notification_preference.changed' AND notification_preference_ve"
    "rsion IS NOT NULL AND notification_preference_version>0 AND support_case_id IS NULL AND "
    "support_case_version IS NULL AND goal_id IS NULL AND goal_version IS NULL AND profile_ve"
    "rsion IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS"
    " NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND "
    "ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND blo"
    "ck_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND private_pas"
    "s_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL AND connection_"
    "request_id IS NULL AND connection_request_version IS NULL AND connection_request_state I"
    "S NULL AND connection_request_recipient_id IS NULL AND goal_share_id IS NULL AND goal_sh"
    "are_conversation_id IS NULL AND goal_share_context_version IS NULL AND conversation_read"
    "_id IS NULL AND read_conversation_id IS NULL AND message_operation_id IS NULL AND messag"
    "e_operation_state IS NULL AND request_view_ack_id IS NULL AND request_initiator_id IS NU"
    "LL AND operator_audit_id IS NULL AND operator_access_version IS NULL AND operator_action"
    " IS NULL AND study_outcome_id IS NULL AND study_conversation_id IS NULL AND study_outcom"
    "e_version IS NULL AND study_answer IS NULL AND peer_feedback_id IS NULL AND peer_feedbac"
    "k_version IS NULL AND feedback_again IS NULL AND study_prompt_id IS NULL AND study_promp"
    "t_conversation_id IS NULL AND help_version IS NULL AND photo_version IS NULL AND lifecyc"
    "le_revision_id IS NULL AND lifecycle_account_id IS NULL AND lifecycle_version IS NULL AN"
    "D lifecycle_operation IS NULL) OR (kind IN ('support.received','support.status_changed')"
    " AND support_case_id IS NOT NULL AND support_case_version IS NOT NULL AND support_case_v"
    "ersion>0 AND notification_preference_version IS NULL AND goal_id IS NULL AND goal_versio"
    "n IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND subject_id IS N"
    "ULL AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AN"
    "D ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND r"
    "eport_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AND blocked"
    " IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed"
    " IS NULL AND connection_request_id IS NULL AND connection_request_version IS NULL AND co"
    "nnection_request_state IS NULL AND connection_request_recipient_id IS NULL AND goal_shar"
    "e_id IS NULL AND goal_share_conversation_id IS NULL AND goal_share_context_version IS NU"
    "LL AND conversation_read_id IS NULL AND read_conversation_id IS NULL AND message_operati"
    "on_id IS NULL AND message_operation_state IS NULL AND request_view_ack_id IS NULL AND re"
    "quest_initiator_id IS NULL AND operator_audit_id IS NULL AND operator_access_version IS "
    "NULL AND operator_action IS NULL AND study_outcome_id IS NULL AND study_conversation_id "
    "IS NULL AND study_outcome_version IS NULL AND study_answer IS NULL AND peer_feedback_id "
    "IS NULL AND peer_feedback_version IS NULL AND feedback_again IS NULL AND study_prompt_id"
    " IS NULL AND study_prompt_conversation_id IS NULL AND help_version IS NULL AND photo_ver"
    "sion IS NULL AND lifecycle_revision_id IS NULL AND lifecycle_account_id IS NULL AND life"
    "cycle_version IS NULL AND lifecycle_operation IS NULL)"
)

AUDIT_SHAPE = (
    f"({BEFORE_AUDIT_SHAPE}) OR (resource_kind='delivery_source' AND "
    "requested_media_owner_id IS NULL AND requested_media_attempt_id IS NULL AND "
    "requested_media_kind IS NULL AND actual_source_upload_id IS NULL AND ("
    "(action='search_delivery_sources' AND requested_id IS NULL AND outcome='search' AND "
    "query_fingerprint IS NOT NULL AND octet_length(query_fingerprint)=32 AND "
    "cardinality(result_ids)<=50) OR (action='read_delivery_source' AND "
    "requested_id IS NOT NULL AND query_fingerprint IS NULL AND "
    "((outcome='read' AND result_ids=ARRAY[requested_id]) OR "
    "(outcome='not_found' AND cardinality(result_ids)=0)))))"
)
EVENT_SHAPE = BEFORE_EVENT_SHAPE.replace(
    "'read_support_case','search_support_cases')",
    "'read_support_case','search_support_cases','search_delivery_sources','read_delivery_source')",
)

CAPTURE_FUNCTION = """
CREATE FUNCTION peerly_capture_external_source() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $capture$
BEGIN
    IF TG_NARGS <> 2 OR NOT (
        (TG_TABLE_NAME = 'product_events' AND TG_ARGV[0] = 'canonical'
         AND TG_ARGV[1] = 'canonical_event_id') OR
        (TG_TABLE_NAME = 'support_cases' AND TG_ARGV[0] = 'support_case'
         AND TG_ARGV[1] = 'support_case_id') OR
        (TG_TABLE_NAME = 'client_observations' AND TG_ARGV[0] = 'client_observation'
         AND TG_ARGV[1] = 'observation_id')
    ) THEN
        RAISE EXCEPTION 'Unsupported external source capture';
    END IF;
    EXECUTE format(
        'INSERT INTO %I.external_delivery_sources (source_kind, %I) '
        'VALUES ($1, $2) ON CONFLICT (%I) DO NOTHING',
        TG_TABLE_SCHEMA, TG_ARGV[1], TG_ARGV[1]
    ) USING TG_ARGV[0], NEW.id;
    RETURN NEW;
END
$capture$;
"""


def _inspection_constraints(audit_shape: str, event_shape: str) -> None:
    op.drop_constraint(
        op.f("ck_operator_audits_fixed_inspection_shape"), "operator_audits", type_="check"
    )
    op.create_check_constraint("fixed_inspection_shape", "operator_audits", audit_shape)
    op.drop_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", type_="check"
    )
    op.create_check_constraint("event_reference_shape", "product_events", event_shape)


def upgrade() -> None:
    op.create_table(
        "external_delivery_destinations",
        sa.Column("sink", sa.String(length=32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(length=32), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "sink IN ('umami','telegram_support')",
            name=op.f("ck_external_delivery_destinations_known_sink"),
        ),
        sa.CheckConstraint(
            "octet_length(fingerprint)=32",
            name=op.f("ck_external_delivery_destinations_destination_fingerprint"),
        ),
        sa.CheckConstraint(
            "revision > 0", name=op.f("ck_external_delivery_destinations_positive_revision")
        ),
        sa.PrimaryKeyConstraint("sink", "revision", name=op.f("pk_external_delivery_destinations")),
    )
    op.create_table(
        "external_delivery_schedule",
        sa.Column("sink", sa.String(length=32), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=False),
        sa.Column("next_claim_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("blocked_reason", sa.String(length=32), nullable=True),
        sa.CheckConstraint(
            "blocked_reason IS NULL OR blocked_reason IN ('transient','rate_limited','cre"
            "dentials_unavailable','destination_unavailable','invalid_response','timeout'"
            ",'lease_expired','cancelled','permanent')",
            name=op.f("ck_external_delivery_schedule_known_block"),
        ),
        sa.CheckConstraint(
            "sink IN ('umami','telegram_support')",
            name=op.f("ck_external_delivery_schedule_known_sink"),
        ),
        sa.CheckConstraint(
            "turn BETWEEN 0 AND 1", name=op.f("ck_external_delivery_schedule_bounded_turn")
        ),
        sa.PrimaryKeyConstraint("sink", name=op.f("pk_external_delivery_schedule")),
        sa.UniqueConstraint("turn", name="uq_external_delivery_schedule_turn"),
    )
    op.create_table(
        "client_observation_batches",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(length=32), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("release_id", sa.String(length=40), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_ids", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("duplicate_ids", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.CheckConstraint(
            "key ~ '^[A-Za-z0-9_-]{8,128}$'", name=op.f("ck_client_observation_batches_valid_key")
        ),
        sa.CheckConstraint(
            "release_id IS NULL OR release_id ~ '^[0-9a-f]{40}$'",
            name=op.f("ck_client_observation_batches_release_shape"),
        ),
        sa.CheckConstraint(
            "NOT accepted_ids && duplicate_ids",
            name=op.f("ck_client_observation_batches_disjoint_receipt"),
        ),
        sa.CheckConstraint(
            "cardinality(accepted_ids)+cardinality(duplicate_ids) BETWEEN 1 AND 20",
            name=op.f("ck_client_observation_batches_bounded_receipt"),
        ),
        sa.CheckConstraint(
            "octet_length(fingerprint)=32",
            name=op.f("ck_client_observation_batches_fingerprint_length"),
        ),
        sa.CheckConstraint(
            "schema_version=1", name=op.f("ck_client_observation_batches_known_schema")
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_client_observation_batches_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("account_id", "key", name=op.f("pk_client_observation_batches")),
    )
    op.create_index(
        "ix_client_observation_batches_actor_received",
        "client_observation_batches",
        ["account_id", "received_at"],
        unique=False,
    )
    op.create_table(
        "client_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("batch_key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(length=32), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("release_id", sa.String(length=40), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("screen", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("metric", sa.String(length=16), nullable=True),
        sa.Column("value", sa.Double(), nullable=True),
        sa.Column("category", sa.String(length=16), nullable=True),
        sa.Column("method", sa.String(length=8), nullable=True),
        sa.Column("route", sa.String(length=32), nullable=True),
        sa.Column("status_class", sa.String(length=16), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("quality_reason", sa.String(length=16), nullable=True),
        sa.Column("quality_count", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "(kind='screen.viewed' AND action IS NULL AND outcome IS NULL AND metric IS N"
            "ULL AND value IS NULL AND category IS NULL AND method IS NULL AND route IS N"
            "ULL AND status_class IS NULL AND duration_ms IS NULL AND request_id IS NULL "
            "AND action_id IS NULL AND trace_id IS NULL AND quality_reason IS NULL AND qu"
            "ality_count IS NULL) OR (kind='quality.observed' AND quality_reason IS NOT N"
            "ULL AND quality_count IS NOT NULL AND action IS NULL AND outcome IS NULL AND"
            " metric IS NULL AND value IS NULL AND category IS NULL AND method IS NULL AN"
            "D route IS NULL AND status_class IS NULL AND duration_ms IS NULL AND request"
            "_id IS NULL AND action_id IS NULL AND trace_id IS NULL) OR (kind='action.obs"
            "erved' AND action IS NOT NULL AND outcome IS NOT NULL AND metric IS NULL AND"
            " value IS NULL AND category IS NULL AND method IS NULL AND route IS NULL AND"
            " status_class IS NULL AND duration_ms IS NULL AND request_id IS NULL AND tra"
            "ce_id IS NULL AND quality_reason IS NULL AND quality_count IS NULL) OR (kind"
            "='performance.observed' AND metric IS NOT NULL AND value IS NOT NULL AND act"
            "ion IS NULL AND outcome IS NULL AND category IS NULL AND method IS NULL AND "
            "route IS NULL AND status_class IS NULL AND duration_ms IS NULL AND request_i"
            "d IS NULL AND action_id IS NULL AND trace_id IS NULL AND quality_reason IS N"
            "ULL AND quality_count IS NULL) OR (kind='error.observed' AND category IS NOT"
            " NULL AND action IS NULL AND outcome IS NULL AND metric IS NULL AND value IS"
            " NULL AND method IS NULL AND route IS NULL AND status_class IS NULL AND dura"
            "tion_ms IS NULL AND request_id IS NULL AND action_id IS NULL AND trace_id IS"
            " NULL AND quality_reason IS NULL AND quality_count IS NULL) OR (kind='http.o"
            "bserved' AND method IS NOT NULL AND route IS NOT NULL AND status_class IS NO"
            "T NULL AND duration_ms IS NOT NULL AND action IS NULL AND outcome IS NULL AN"
            "D metric IS NULL AND value IS NULL AND category IS NULL AND quality_reason I"
            "S NULL AND quality_count IS NULL)",
            name=op.f("ck_client_observations_closed_event_shape"),
        ),
        sa.CheckConstraint(
            "action IS NULL OR action IN ('navigate','submit','retry','cancel','apply','d"
            "ismiss','load_more','upload','permission_request','open_settings')",
            name=op.f("ck_client_observations_known_action"),
        ),
        sa.CheckConstraint(
            "category IS NULL OR category IN ('network','http','timeout','offline','javas"
            "cript','render','resource','unknown')",
            name=op.f("ck_client_observations_known_category"),
        ),
        sa.CheckConstraint(
            "method IS NULL OR method IN ('GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS')",
            name=op.f("ck_client_observations_known_method"),
        ),
        sa.CheckConstraint(
            "metric IS NULL OR metric IN ('route_ready','lcp','inp','fcp','ttfb','cls')",
            name=op.f("ck_client_observations_known_metric"),
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('invoked','succeeded_observed','rejected_obse"
            "rved','failed_observed','cancelled_observed','unknown')",
            name=op.f("ck_client_observations_known_outcome"),
        ),
        sa.CheckConstraint(
            "quality_reason IS NULL OR quality_reason IN ('overflow','invalid','expired',"
            "'rejected','exhausted','unavailable')",
            name=op.f("ck_client_observations_known_quality_reason"),
        ),
        sa.CheckConstraint(
            "release_id IS NULL OR release_id ~ '^[0-9a-f]{40}$'",
            name=op.f("ck_client_observations_release_shape"),
        ),
        sa.CheckConstraint(
            "route IS NULL OR route IN ('identity','verification','registration','profile"
            "','study','discovery','requests','conversations','media','support','notifica"
            "tions','ai','operator','other')",
            name=op.f("ck_client_observations_known_route"),
        ),
        sa.CheckConstraint(
            "screen IN ('welcome','verification','onboarding','discover','requests','chat"
            "s','conversation','profile','study','notifications','support','help','terms'"
            ",'privacy','operator','unknown')",
            name=op.f("ck_client_observations_known_screen"),
        ),
        sa.CheckConstraint(
            "status_class IS NULL OR status_class IN ('1xx','2xx','3xx','4xx','5xx','netw"
            "ork','cancelled')",
            name=op.f("ck_client_observations_known_status_class"),
        ),
        sa.CheckConstraint(
            "trace_id IS NULL OR (trace_id ~ '^[0-9a-f]{32}$' AND trace_id!=repeat('0',32))",
            name=op.f("ck_client_observations_trace_shape"),
        ),
        sa.CheckConstraint(
            "value IS NULL OR (value >= 0 AND value <= CASE WHEN metric='cls' THEN 100 EL"
            "SE 60000 END)",
            name=op.f("ck_client_observations_bounded_metric"),
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms BETWEEN 0 AND 60000",
            name=op.f("ck_client_observations_bounded_duration"),
        ),
        sa.CheckConstraint(
            "octet_length(fingerprint)=32", name=op.f("ck_client_observations_fingerprint_length")
        ),
        sa.CheckConstraint(
            "quality_count IS NULL OR quality_count BETWEEN 1 AND 65535",
            name=op.f("ck_client_observations_bounded_quality_count"),
        ),
        sa.CheckConstraint("schema_version=1", name=op.f("ck_client_observations_known_schema")),
        sa.ForeignKeyConstraint(
            ["account_id", "batch_key"],
            ["client_observation_batches.account_id", "client_observation_batches.key"],
            name=op.f("fk_client_observations_account_id_client_observation_batches"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_client_observations_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client_observations")),
        sa.UniqueConstraint("account_id", "event_id", name="uq_client_observations_actor_event"),
        sa.UniqueConstraint("id", "kind", "release_id", name="uq_client_observations_frame_source"),
    )
    op.create_index(
        "ix_client_observations_actor_received",
        "client_observations",
        ["account_id", "received_at", "id"],
        unique=False,
    )
    op.create_table(
        "client_observation_frames",
        sa.Column("observation_id", sa.Uuid(), nullable=False),
        sa.Column("frame_index", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("release_id", sa.String(length=40), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("line", sa.Integer(), nullable=False),
        sa.Column("column_number", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "kind='error.observed'", name=op.f("ck_client_observation_frames_actual_error_source")
        ),
        sa.CheckConstraint(
            "asset_id BETWEEN 0 AND 4095", name=op.f("ck_client_observation_frames_bounded_asset")
        ),
        sa.CheckConstraint(
            "frame_index BETWEEN 0 AND 2", name=op.f("ck_client_observation_frames_bounded_index")
        ),
        sa.CheckConstraint(
            "line BETWEEN 1 AND 2147483647 AND column_number BETWEEN 0 AND 2147483647",
            name=op.f("ck_client_observation_frames_bounded_coordinates"),
        ),
        sa.ForeignKeyConstraint(
            ["observation_id", "kind", "release_id"],
            [
                "client_observations.id",
                "client_observations.kind",
                "client_observations.release_id",
            ],
            name=op.f("fk_client_observation_frames_observation_id_client_observations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "observation_id", "frame_index", name=op.f("pk_client_observation_frames")
        ),
    )
    op.create_table(
        "external_delivery_sources",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("canonical_event_id", sa.Uuid(), nullable=True),
        sa.Column("observation_id", sa.Uuid(), nullable=True),
        sa.Column("support_case_id", sa.Uuid(), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("mode", sa.String(length=24), server_default=sa.text("'live'"), nullable=False),
        sa.Column("routing_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("materialized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exclusion_reason", sa.String(length=32), nullable=True),
        sa.CheckConstraint(
            "(materialized_at IS NULL AND exclusion_reason IS NULL) OR (materialized_at I"
            "S NOT NULL AND materialized_at>=captured_at AND exclusion_reason IS NOT NULL"
            " AND exclusion_reason IN ('none','backfill_not_analytics'))",
            name=op.f("ck_external_delivery_sources_actual_materialization"),
        ),
        sa.CheckConstraint(
            "(source_kind='canonical' AND canonical_event_id IS NOT NULL AND observation_"
            "id IS NULL AND support_case_id IS NULL) OR (source_kind='client_observation'"
            " AND observation_id IS NOT NULL AND canonical_event_id IS NULL AND support_c"
            "ase_id IS NULL) OR (source_kind='support_case' AND support_case_id IS NOT NU"
            "LL AND canonical_event_id IS NULL AND observation_id IS NULL)",
            name=op.f("ck_external_delivery_sources_actual_source_shape"),
        ),
        sa.CheckConstraint(
            "mode IN ('live','backfill_umami')",
            name=op.f("ck_external_delivery_sources_known_mode"),
        ),
        sa.CheckConstraint(
            "routing_version=1", name=op.f("ck_external_delivery_sources_known_routing_version")
        ),
        sa.ForeignKeyConstraint(
            ["canonical_event_id"],
            ["product_events.id"],
            name=op.f("fk_external_delivery_sources_canonical_event_id_product_events"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["observation_id"],
            ["client_observations.id"],
            name=op.f("fk_external_delivery_sources_observation_id_client_observations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["support_case_id"],
            ["support_cases.id"],
            name=op.f("fk_external_delivery_sources_support_case_id_support_cases"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_delivery_sources")),
        sa.UniqueConstraint("canonical_event_id", name="uq_external_sources_canonical"),
        sa.UniqueConstraint("observation_id", name="uq_external_sources_observation"),
        sa.UniqueConstraint("support_case_id", name="uq_external_sources_support"),
    )
    op.create_index(
        "ix_external_sources_unrouted",
        "external_delivery_sources",
        ["captured_at", "id"],
        unique=False,
        postgresql_where=sa.text("materialized_at IS NULL"),
    )
    op.create_table(
        "external_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("sink", sa.String(length=32), nullable=False),
        sa.Column("destination_revision", sa.Integer(), nullable=True),
        sa.Column("projection_version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_id", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_message_id", sa.BigInteger(), nullable=True),
        sa.Column("last_failure", sa.String(length=32), nullable=True),
        sa.CheckConstraint(
            "(state='leased' AND lease_id IS NOT NULL AND lease_until IS NOT NULL AND des"
            "tination_revision IS NOT NULL AND attempt_count>0) OR (state!='leased' AND l"
            "ease_id IS NULL AND lease_until IS NULL)",
            name=op.f("ck_external_deliveries_actual_lease"),
        ),
        sa.CheckConstraint(
            "(state='pending' AND attempt_count=0) OR (state!='pending' AND attempt_count>0)",
            name=op.f("ck_external_deliveries_actual_attempt_count"),
        ),
        sa.CheckConstraint(
            "(state='succeeded' AND delivered_at IS NOT NULL) OR (state!='succeeded' AND "
            "delivered_at IS NULL)",
            name=op.f("ck_external_deliveries_actual_delivery"),
        ),
        sa.CheckConstraint(
            "destination_revision IS NOT NULL OR (state='pending' AND attempt_count=0)",
            name=op.f("ck_external_deliveries_durable_destination"),
        ),
        sa.CheckConstraint(
            "last_failure IS NULL OR last_failure IN ('transient','rate_limited','credent"
            "ials_unavailable','destination_unavailable','invalid_response','timeout','le"
            "ase_expired','cancelled','permanent')",
            name=op.f("ck_external_deliveries_known_failure"),
        ),
        sa.CheckConstraint(
            "provider_message_id IS NULL OR (sink='telegram_support' AND state='succeeded"
            "' AND provider_message_id>0)",
            name=op.f("ck_external_deliveries_actual_message_receipt"),
        ),
        sa.CheckConstraint(
            "sink IN ('umami','telegram_support')", name=op.f("ck_external_deliveries_known_sink")
        ),
        sa.CheckConstraint(
            "state IN ('pending','leased','retry','succeeded','dead')",
            name=op.f("ck_external_deliveries_known_state"),
        ),
        sa.CheckConstraint(
            "attempt_count BETWEEN 0 AND 8", name=op.f("ck_external_deliveries_bounded_attempts")
        ),
        sa.CheckConstraint(
            "delivered_at IS NULL OR (delivered_at>=created_at AND updated_at>=delivered_at)",
            name=op.f("ck_external_deliveries_ordered_delivery"),
        ),
        sa.CheckConstraint(
            "projection_version=1", name=op.f("ck_external_deliveries_known_projection_version")
        ),
        sa.CheckConstraint(
            "updated_at>=created_at", name=op.f("ck_external_deliveries_ordered_update")
        ),
        sa.ForeignKeyConstraint(
            ["sink", "destination_revision"],
            ["external_delivery_destinations.sink", "external_delivery_destinations.revision"],
            name=op.f("fk_external_deliveries_sink_external_delivery_destinations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["external_delivery_sources.id"],
            name=op.f("fk_external_deliveries_source_id_external_delivery_sources"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_deliveries")),
        sa.UniqueConstraint("source_id", "sink", name="uq_external_deliveries_source_sink"),
    )
    op.create_index(
        "ix_external_deliveries_due",
        "external_deliveries",
        ["sink", "next_attempt_at", "id"],
        unique=False,
        postgresql_where=sa.text("state IN ('pending','retry')"),
    )
    op.create_index(
        "ix_external_deliveries_lease",
        "external_deliveries",
        ["lease_until", "id"],
        unique=False,
        postgresql_where=sa.text("state='leased'"),
    )
    op.create_table(
        "external_delivery_attempts",
        sa.Column("delivery_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("lease_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=24), nullable=True),
        sa.Column("failure", sa.String(length=32), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("retry_after_seconds", sa.Integer(), nullable=True),
        sa.Column("provider_message_id", sa.BigInteger(), nullable=True),
        sa.Column("late_ack_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("late_message_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "(ended_at IS NULL AND failure IS NULL AND http_status IS NULL AND retry_afte"
            "r_seconds IS NULL AND provider_message_id IS NULL) OR (ended_at IS NOT NULL "
            "AND ((outcome='accepted' AND failure IS NULL) OR (outcome!='accepted' AND fa"
            "ilure IS NOT NULL)))",
            name=op.f("ck_external_delivery_attempts_closed_result_shape"),
        ),
        sa.CheckConstraint(
            "(ended_at IS NULL AND outcome IS NULL) OR (ended_at IS NOT NULL AND ended_at"
            ">=started_at AND outcome IS NOT NULL AND outcome IN ('accepted','retryable',"
            "'ambiguous','permanent','lease_expired'))",
            name=op.f("ck_external_delivery_attempts_actual_attempt_outcome"),
        ),
        sa.CheckConstraint(
            "failure IS NULL OR failure IN ('transient','rate_limited','credentials_unava"
            "ilable','destination_unavailable','invalid_response','timeout','lease_expire"
            "d','cancelled','permanent')",
            name=op.f("ck_external_delivery_attempts_known_failure"),
        ),
        sa.CheckConstraint(
            "attempt_no BETWEEN 1 AND 8", name=op.f("ck_external_delivery_attempts_bounded_attempt")
        ),
        sa.CheckConstraint(
            "http_status IS NULL OR http_status BETWEEN 100 AND 599",
            name=op.f("ck_external_delivery_attempts_bounded_status"),
        ),
        sa.CheckConstraint(
            "late_ack_at IS NULL OR (ended_at IS NOT NULL AND late_ack_at>=ended_at)",
            name=op.f("ck_external_delivery_attempts_actual_late_ack"),
        ),
        sa.CheckConstraint(
            "late_message_id IS NULL OR (late_message_id>0 AND late_ack_at IS NOT NULL)",
            name=op.f("ck_external_delivery_attempts_actual_late_message"),
        ),
        sa.CheckConstraint(
            "provider_message_id IS NULL OR provider_message_id>0",
            name=op.f("ck_external_delivery_attempts_actual_message_receipt"),
        ),
        sa.CheckConstraint(
            "retry_after_seconds IS NULL OR retry_after_seconds BETWEEN 1 AND 2147483647",
            name=op.f("ck_external_delivery_attempts_positive_retry"),
        ),
        sa.ForeignKeyConstraint(
            ["delivery_id"],
            ["external_deliveries.id"],
            name=op.f("fk_external_delivery_attempts_delivery_id_external_deliveries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "delivery_id", "attempt_no", name=op.f("pk_external_delivery_attempts")
        ),
        sa.UniqueConstraint("lease_id", name="uq_external_delivery_attempts_lease"),
    )
    op.create_index(
        "ix_external_delivery_attempts_source_time",
        "external_delivery_attempts",
        ["started_at", "delivery_id", "attempt_no"],
        unique=False,
    )
    _inspection_constraints(AUDIT_SHAPE, EVENT_SHAPE)
    op.execute(sa.text(CAPTURE_FUNCTION))
    op.execute(
        sa.text(
            "CREATE TRIGGER peerly_capture_product_events AFTER INSERT ON product_events "
            "FOR EACH ROW EXECUTE FUNCTION peerly_capture_external_source('canonical','ca"
            "nonical_event_id')"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER peerly_capture_support_cases AFTER INSERT ON support_cases "
            "FOR EACH ROW EXECUTE FUNCTION peerly_capture_external_source('support_case',"
            "'support_case_id')"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER peerly_capture_client_observations AFTER INSERT ON client_observations "
            "FOR EACH ROW EXECUTE FUNCTION peerly_capture_external_source('client_observa"
            "tion','observation_id')"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO external_delivery_schedule (sink,turn,next_claim_at) VALUES "
            "('umami',0,TIMESTAMPTZ '1970-01-01 00:00:00+00'),"
            "('telegram_support',1,TIMESTAMPTZ '1970-01-01 00:00:00+00')"
        )
    )


def downgrade() -> None:
    retained = op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM client_observation_batches UNION ALL "
            "SELECT 1 FROM client_observations UNION ALL SELECT 1 FROM client_observation_frames "
            "UNION ALL SELECT 1 FROM external_delivery_destinations UNION ALL "
            "SELECT 1 FROM external_delivery_sources UNION ALL SELECT 1 FROM external_deliveries "
            "UNION ALL SELECT 1 FROM external_delivery_attempts UNION ALL "
            "SELECT 1 FROM operator_audits WHERE action IN "
            "('search_delivery_sources','read_delivery_source') UNION ALL "
            "SELECT 1 FROM product_events WHERE operator_action IN "
            "('search_delivery_sources','read_delivery_source'))"
        )
    )
    if retained:
        raise RuntimeError("Refusing to remove retained observations or external delivery facts")
    op.execute(sa.text("DROP TRIGGER peerly_capture_product_events ON product_events"))
    op.execute(sa.text("DROP TRIGGER peerly_capture_support_cases ON support_cases"))
    op.execute(sa.text("DROP TRIGGER peerly_capture_client_observations ON client_observations"))
    op.execute(sa.text("DROP FUNCTION peerly_capture_external_source()"))
    _inspection_constraints(BEFORE_AUDIT_SHAPE, BEFORE_EVENT_SHAPE)
    op.drop_table("external_delivery_attempts")
    op.drop_table("external_deliveries")
    op.drop_table("external_delivery_sources")
    op.drop_table("client_observation_frames")
    op.drop_table("client_observations")
    op.drop_table("client_observation_batches")
    op.drop_table("external_delivery_schedule")
    op.drop_table("external_delivery_destinations")
