"""Actual retained chat-image source proof in the canonical operator audit."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0056_operator_chat_media"
down_revision: str | Sequence[str] | None = "0055_external_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE_AUDIT_SHAPE = (
    "((((((((action='search_accounts' AND resource_kind='account' AND requested_id IS NULL AN"
    "D outcome='search' AND query_fingerprint IS NOT NULL AND octet_length(query_fingerprint)"
    "=32 AND cardinality(result_ids)<=20) OR (action='read_account' AND resource_kind='accoun"
    "t' AND requested_id IS NOT NULL AND query_fingerprint IS NULL AND ((outcome='read' AND r"
    "esult_ids=ARRAY[requested_id]) OR (outcome='not_found' AND cardinality(result_ids)=0))) "
    "OR (action='read_conversation_messages' AND resource_kind='conversation' AND requested_i"
    "d IS NOT NULL AND query_fingerprint IS NULL AND ((outcome='read' AND cardinality(result_"
    "ids)<=50) OR (outcome='not_found' AND cardinality(result_ids)=0)))) OR (action='search_e"
    "vents' AND resource_kind='event' AND requested_id IS NULL AND outcome='search' AND query"
    "_fingerprint IS NOT NULL AND octet_length(query_fingerprint)=32 AND cardinality(result_i"
    "ds)<=50) OR (action IN ('read_event','read_audit') AND resource_kind=CASE WHEN action='r"
    "ead_event' THEN 'event' ELSE 'audit' END AND requested_id IS NOT NULL AND query_fingerpr"
    "int IS NULL AND ((outcome='read' AND result_ids=ARRAY[requested_id]) OR (outcome='not_fo"
    "und' AND cardinality(result_ids)=0)))) OR (action='search_reports' AND resource_kind='re"
    "port' AND requested_id IS NULL AND outcome='search' AND query_fingerprint IS NOT NULL AN"
    "D octet_length(query_fingerprint)=32 AND cardinality(result_ids)<=50) OR (action='read_r"
    "eport' AND resource_kind='report' AND requested_id IS NOT NULL AND query_fingerprint IS "
    "NULL AND ((outcome='read' AND result_ids=ARRAY[requested_id]) OR (outcome='not_found' AN"
    "D cardinality(result_ids)=0)))) AND requested_media_owner_id IS NULL AND requested_media"
    "_attempt_id IS NULL AND requested_media_kind IS NULL AND actual_source_upload_id IS NULL"
    ") OR (action='read_media' AND resource_kind='profile_media' AND requested_id IS NOT NULL"
    " AND query_fingerprint IS NULL AND requested_media_owner_id IS NOT NULL AND requested_me"
    "dia_attempt_id IS NOT NULL AND requested_media_kind IS NOT NULL AND requested_media_kind"
    " IN ('original','display') AND ((outcome='read' AND result_ids=ARRAY[requested_id] AND a"
    "ctual_source_upload_id IS NOT NULL AND actual_source_upload_id=requested_id) OR (outcome"
    "='not_found' AND cardinality(result_ids)=0 AND (actual_source_upload_id IS NULL OR actua"
    "l_source_upload_id=requested_id))))) OR (action='read_support_case' AND resource_kind='s"
    "upport_case' AND requested_id IS NOT NULL AND query_fingerprint IS NULL AND requested_me"
    "dia_owner_id IS NULL AND requested_media_attempt_id IS NULL AND requested_media_kind IS "
    "NULL AND actual_source_upload_id IS NULL AND ((outcome='read' AND result_ids=ARRAY[reque"
    "sted_id]) OR (outcome='not_found' AND cardinality(result_ids)=0)))) OR (action='search_s"
    "upport_cases' AND resource_kind='support_case' AND requested_id IS NULL AND outcome='sea"
    "rch' AND query_fingerprint IS NOT NULL AND octet_length(query_fingerprint)=32 AND cardin"
    "ality(result_ids)<=50 AND requested_media_owner_id IS NULL AND requested_media_attempt_i"
    "d IS NULL AND requested_media_kind IS NULL AND actual_source_upload_id IS NULL)) OR (res"
    "ource_kind='delivery_source' AND requested_media_owner_id IS NULL AND requested_media_at"
    "tempt_id IS NULL AND requested_media_kind IS NULL AND actual_source_upload_id IS NULL AN"
    "D ((action='search_delivery_sources' AND requested_id IS NULL AND outcome='search' AND q"
    "uery_fingerprint IS NOT NULL AND octet_length(query_fingerprint)=32 AND cardinality(resu"
    "lt_ids)<=50) OR (action='read_delivery_source' AND requested_id IS NOT NULL AND query_fi"
    "ngerprint IS NULL AND ((outcome='read' AND result_ids=ARRAY[requested_id]) OR (outcome='"
    "not_found' AND cardinality(result_ids)=0)))))"
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
    "search_support_cases','search_delivery_sources','read_delivery_source') AND goal_id IS N"
    "ULL AND goal_version IS NULL AND profile_version IS NULL AND visibility_version IS NULL "
    "AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboard"
    "ing_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_r"
    "eason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND block_version "
    "IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL"
    " AND private_passed IS NULL AND connection_request_id IS NULL AND connection_request_ver"
    "sion IS NULL AND connection_request_state IS NULL AND connection_request_recipient_id IS"
    " NULL AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND goal_share_co"
    "ntext_version IS NULL AND conversation_read_id IS NULL AND read_conversation_id IS NULL "
    "AND message_operation_id IS NULL AND message_operation_state IS NULL AND request_view_ac"
    "k_id IS NULL AND request_initiator_id IS NULL)) AND study_outcome_id IS NULL AND study_c"
    "onversation_id IS NULL AND study_outcome_version IS NULL AND study_answer IS NULL AND pe"
    "er_feedback_id IS NULL AND peer_feedback_version IS NULL AND feedback_again IS NULL AND "
    "study_prompt_id IS NULL AND study_prompt_conversation_id IS NULL) OR (kind='study.report"
    "ed' AND study_outcome_id IS NOT NULL AND study_conversation_id IS NOT NULL AND study_out"
    "come_version IS NOT NULL AND study_answer IS NOT NULL AND peer_feedback_id IS NULL AND p"
    "eer_feedback_version IS NULL AND feedback_again IS NULL AND study_prompt_id IS NULL AND "
    "study_prompt_conversation_id IS NULL AND study_answer IN ('yes','not_yet','did_not_work_"
    "out') AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visib"
    "ility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learni"
    "ng IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_"
    "state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS N"
    "ULL AND block_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND privat"
    "e_pass_version IS NULL AND private_passed IS NULL AND connection_request_id IS NULL AND "
    "connection_request_version IS NULL AND connection_request_state IS NULL AND connection_r"
    "equest_recipient_id IS NULL AND goal_share_id IS NULL AND goal_share_conversation_id IS "
    "NULL AND goal_share_context_version IS NULL AND conversation_read_id IS NULL AND read_co"
    "nversation_id IS NULL AND message_operation_id IS NULL AND message_operation_state IS NU"
    "LL AND request_view_ack_id IS NULL AND request_initiator_id IS NULL AND operator_audit_i"
    "d IS NULL AND operator_access_version IS NULL AND operator_action IS NULL) OR (kind='fee"
    "dback.saved' AND study_outcome_id IS NULL AND study_conversation_id IS NULL AND study_ou"
    "tcome_version IS NULL AND study_answer IS NULL AND peer_feedback_id IS NOT NULL AND peer"
    "_feedback_version IS NOT NULL AND feedback_again IS NOT NULL AND study_prompt_id IS NULL"
    " AND study_prompt_conversation_id IS NULL AND feedback_again IN ('yes','maybe','no') AND"
    " goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibility_ver"
    "sion IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NUL"
    "L AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS "
    "NULL AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND b"
    "lock_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_ve"
    "rsion IS NULL AND private_passed IS NULL AND connection_request_id IS NULL AND connectio"
    "n_request_version IS NULL AND connection_request_state IS NULL AND connection_request_re"
    "cipient_id IS NULL AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND "
    "goal_share_context_version IS NULL AND conversation_read_id IS NULL AND read_conversatio"
    "n_id IS NULL AND message_operation_id IS NULL AND message_operation_state IS NULL AND re"
    "quest_view_ack_id IS NULL AND request_initiator_id IS NULL AND operator_audit_id IS NULL"
    " AND operator_access_version IS NULL AND operator_action IS NULL) OR (kind='study.prompt"
    "_offered' AND study_outcome_id IS NULL AND study_conversation_id IS NULL AND study_outco"
    "me_version IS NULL AND study_answer IS NULL AND peer_feedback_id IS NULL AND peer_feedba"
    "ck_version IS NULL AND feedback_again IS NULL AND study_prompt_id IS NOT NULL AND study_"
    "prompt_conversation_id IS NOT NULL AND TRUE AND goal_id IS NULL AND goal_version IS NULL"
    " AND profile_version IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND t"
    "opic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_"
    "id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id "
    "IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL "
    "AND private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL "
    "AND connection_request_id IS NULL AND connection_request_version IS NULL AND connection_"
    "request_state IS NULL AND connection_request_recipient_id IS NULL AND goal_share_id IS N"
    "ULL AND goal_share_conversation_id IS NULL AND goal_share_context_version IS NULL AND co"
    "nversation_read_id IS NULL AND read_conversation_id IS NULL AND message_operation_id IS "
    "NULL AND message_operation_state IS NULL AND request_view_ack_id IS NULL AND request_ini"
    "tiator_id IS NULL AND operator_audit_id IS NULL AND operator_access_version IS NULL AND "
    "operator_action IS NULL)) AND help_version IS NULL AND photo_version IS NULL) OR (kind='"
    "profile.saved' AND profile_version IS NOT NULL AND goal_id IS NULL AND goal_version IS N"
    "ULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND "
    "shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS"
    " NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_relatio"
    "nship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND private_pass_id IS NU"
    "LL AND private_pass_version IS NULL AND private_passed IS NULL AND connection_request_id"
    " IS NULL AND connection_request_version IS NULL AND connection_request_state IS NULL AND"
    " connection_request_recipient_id IS NULL AND goal_share_id IS NULL AND goal_share_conver"
    "sation_id IS NULL AND goal_share_context_version IS NULL AND conversation_read_id IS NUL"
    "L AND read_conversation_id IS NULL AND message_operation_id IS NULL AND message_operatio"
    "n_state IS NULL AND request_view_ack_id IS NULL AND request_initiator_id IS NULL AND ope"
    "rator_audit_id IS NULL AND operator_access_version IS NULL AND operator_action IS NULL A"
    "ND study_outcome_id IS NULL AND study_conversation_id IS NULL AND study_outcome_version "
    "IS NULL AND study_answer IS NULL AND peer_feedback_id IS NULL AND peer_feedback_version "
    "IS NULL AND feedback_again IS NULL AND study_prompt_id IS NULL AND study_prompt_conversa"
    "tion_id IS NULL AND help_version IS NULL AND photo_version IS NULL) OR (kind='help.saved"
    "' AND help_version IS NOT NULL AND goal_id IS NULL AND goal_version IS NULL AND profile_"
    "version IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present "
    "IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AN"
    "D ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND b"
    "lock_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND private_p"
    "ass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL AND connectio"
    "n_request_id IS NULL AND connection_request_version IS NULL AND connection_request_state"
    " IS NULL AND connection_request_recipient_id IS NULL AND goal_share_id IS NULL AND goal_"
    "share_conversation_id IS NULL AND goal_share_context_version IS NULL AND conversation_re"
    "ad_id IS NULL AND read_conversation_id IS NULL AND message_operation_id IS NULL AND mess"
    "age_operation_state IS NULL AND request_view_ack_id IS NULL AND request_initiator_id IS "
    "NULL AND operator_audit_id IS NULL AND operator_access_version IS NULL AND operator_acti"
    "on IS NULL AND study_outcome_id IS NULL AND study_conversation_id IS NULL AND study_outc"
    "ome_version IS NULL AND study_answer IS NULL AND peer_feedback_id IS NULL AND peer_feedb"
    "ack_version IS NULL AND feedback_again IS NULL AND study_prompt_id IS NULL AND study_pro"
    "mpt_conversation_id IS NULL AND photo_version IS NULL) OR (kind='photo.published' AND ph"
    "oto_version IS NOT NULL AND goal_id IS NULL AND goal_version IS NULL AND profile_version"
    " IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL"
    " AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_ki"
    "nd IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_re"
    "lationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND private_pass_id "
    "IS NULL AND private_pass_version IS NULL AND private_passed IS NULL AND connection_reque"
    "st_id IS NULL AND connection_request_version IS NULL AND connection_request_state IS NUL"
    "L AND connection_request_recipient_id IS NULL AND goal_share_id IS NULL AND goal_share_c"
    "onversation_id IS NULL AND goal_share_context_version IS NULL AND conversation_read_id I"
    "S NULL AND read_conversation_id IS NULL AND message_operation_id IS NULL AND message_ope"
    "ration_state IS NULL AND request_view_ack_id IS NULL AND request_initiator_id IS NULL AN"
    "D operator_audit_id IS NULL AND operator_access_version IS NULL AND operator_action IS N"
    "ULL AND study_outcome_id IS NULL AND study_conversation_id IS NULL AND study_outcome_ver"
    "sion IS NULL AND study_answer IS NULL AND peer_feedback_id IS NULL AND peer_feedback_ver"
    "sion IS NULL AND feedback_again IS NULL AND study_prompt_id IS NULL AND study_prompt_con"
    "versation_id IS NULL AND help_version IS NULL)) AND lifecycle_revision_id IS NULL AND li"
    "fecycle_account_id IS NULL AND lifecycle_version IS NULL AND lifecycle_operation IS NULL"
    ") OR (kind='account.lifecycle_changed' AND lifecycle_revision_id IS NOT NULL AND lifecyc"
    "le_account_id IS NOT NULL AND lifecycle_version IS NOT NULL AND lifecycle_version>0 AND "
    "lifecycle_operation IS NOT NULL AND lifecycle_operation IN ('ban','unban','delete') AND "
    "goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibility_vers"
    "ion IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL"
    " AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS N"
    "ULL AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND bl"
    "ock_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_ver"
    "sion IS NULL AND private_passed IS NULL AND connection_request_id IS NULL AND connection"
    "_request_version IS NULL AND connection_request_state IS NULL AND connection_request_rec"
    "ipient_id IS NULL AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND g"
    "oal_share_context_version IS NULL AND conversation_read_id IS NULL AND read_conversation"
    "_id IS NULL AND message_operation_id IS NULL AND message_operation_state IS NULL AND req"
    "uest_view_ack_id IS NULL AND request_initiator_id IS NULL AND operator_audit_id IS NULL "
    "AND operator_access_version IS NULL AND operator_action IS NULL AND study_outcome_id IS "
    "NULL AND study_conversation_id IS NULL AND study_outcome_version IS NULL AND study_answe"
    "r IS NULL AND peer_feedback_id IS NULL AND peer_feedback_version IS NULL AND feedback_ag"
    "ain IS NULL AND study_prompt_id IS NULL AND study_prompt_conversation_id IS NULL AND hel"
    "p_version IS NULL AND photo_version IS NULL)) AND notification_preference_version IS NUL"
    "L AND support_case_id IS NULL AND support_case_version IS NULL) OR (kind='notification_p"
    "reference.changed' AND notification_preference_version IS NOT NULL AND notification_pref"
    "erence_version>0 AND support_case_id IS NULL AND support_case_version IS NULL AND goal_i"
    "d IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibility_version IS"
    " NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND o"
    "nboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AN"
    "D ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND block_ve"
    "rsion IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_version I"
    "S NULL AND private_passed IS NULL AND connection_request_id IS NULL AND connection_reque"
    "st_version IS NULL AND connection_request_state IS NULL AND connection_request_recipient"
    "_id IS NULL AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND goal_sh"
    "are_context_version IS NULL AND conversation_read_id IS NULL AND read_conversation_id IS"
    " NULL AND message_operation_id IS NULL AND message_operation_state IS NULL AND request_v"
    "iew_ack_id IS NULL AND request_initiator_id IS NULL AND operator_audit_id IS NULL AND op"
    "erator_access_version IS NULL AND operator_action IS NULL AND study_outcome_id IS NULL A"
    "ND study_conversation_id IS NULL AND study_outcome_version IS NULL AND study_answer IS N"
    "ULL AND peer_feedback_id IS NULL AND peer_feedback_version IS NULL AND feedback_again IS"
    " NULL AND study_prompt_id IS NULL AND study_prompt_conversation_id IS NULL AND help_vers"
    "ion IS NULL AND photo_version IS NULL AND lifecycle_revision_id IS NULL AND lifecycle_ac"
    "count_id IS NULL AND lifecycle_version IS NULL AND lifecycle_operation IS NULL) OR (kind"
    " IN ('support.received','support.status_changed') AND support_case_id IS NOT NULL AND su"
    "pport_case_version IS NOT NULL AND support_case_version>0 AND notification_preference_ve"
    "rsion IS NULL AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL A"
    "ND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND share"
    "d_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL"
    " AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_relationship"
    "_id IS NULL AND block_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AN"
    "D private_pass_version IS NULL AND private_passed IS NULL AND connection_request_id IS N"
    "ULL AND connection_request_version IS NULL AND connection_request_state IS NULL AND conn"
    "ection_request_recipient_id IS NULL AND goal_share_id IS NULL AND goal_share_conversatio"
    "n_id IS NULL AND goal_share_context_version IS NULL AND conversation_read_id IS NULL AND"
    " read_conversation_id IS NULL AND message_operation_id IS NULL AND message_operation_sta"
    "te IS NULL AND request_view_ack_id IS NULL AND request_initiator_id IS NULL AND operator"
    "_audit_id IS NULL AND operator_access_version IS NULL AND operator_action IS NULL AND st"
    "udy_outcome_id IS NULL AND study_conversation_id IS NULL AND study_outcome_version IS NU"
    "LL AND study_answer IS NULL AND peer_feedback_id IS NULL AND peer_feedback_version IS NU"
    "LL AND feedback_again IS NULL AND study_prompt_id IS NULL AND study_prompt_conversation_"
    "id IS NULL AND help_version IS NULL AND photo_version IS NULL AND lifecycle_revision_id "
    "IS NULL AND lifecycle_account_id IS NULL AND lifecycle_version IS NULL AND lifecycle_ope"
    "ration IS NULL)"
)

CHAT_NULL = (
    "requested_chat_owner_id IS NULL AND requested_chat_attempt_id IS NULL AND "
    "requested_chat_kind IS NULL AND actual_source_image_id IS NULL"
)
AUDIT_SHAPE = (
    f"(({BEFORE_AUDIT_SHAPE}) AND {CHAT_NULL}) OR (action='read_chat_media' AND "
    "resource_kind='chat_media' AND requested_id IS NOT NULL AND "
    "requested_chat_owner_id IS NOT NULL AND requested_chat_attempt_id IS NOT NULL AND "
    "requested_chat_kind IS NOT NULL AND requested_chat_kind IN ('original','display') AND "
    "query_fingerprint IS NULL AND requested_media_owner_id IS NULL AND "
    "requested_media_attempt_id IS NULL AND requested_media_kind IS NULL AND "
    "actual_source_upload_id IS NULL AND ((outcome='read' AND "
    "actual_source_image_id IS NOT NULL AND actual_source_image_id=requested_id AND "
    "result_ids=ARRAY[requested_id]) OR (outcome='not_found' AND cardinality(result_ids)=0 "
    "AND (actual_source_image_id IS NULL OR actual_source_image_id=requested_id))))"
)
EVENT_SHAPE = BEFORE_EVENT_SHAPE.replace(
    "'search_delivery_sources','read_delivery_source')",
    "'search_delivery_sources','read_delivery_source','read_chat_media')",
)


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
    op.create_unique_constraint(
        "uq_chat_images_id_owner", "chat_image_preparations", ["id", "account_id"]
    )
    for name, kind in (
        ("requested_chat_owner_id", sa.Uuid()),
        ("requested_chat_attempt_id", sa.Uuid()),
        ("requested_chat_kind", sa.String(16)),
        ("actual_source_image_id", sa.Uuid()),
    ):
        op.add_column("operator_audits", sa.Column(name, kind, nullable=True))
    op.create_foreign_key(
        "fk_operator_chat_media_owner_source",
        "operator_audits",
        "chat_image_preparations",
        ["actual_source_image_id", "requested_chat_owner_id"],
        ["id", "account_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_operator_chat_media_attempt_source",
        "operator_audits",
        "chat_image_attempts",
        ["actual_source_image_id", "requested_chat_attempt_id"],
        ["image_id", "id"],
        ondelete="RESTRICT",
    )
    _inspection_constraints(AUDIT_SHAPE, EVENT_SHAPE)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM operator_audits WHERE action='read_chat_media' "
            "OR requested_chat_owner_id IS NOT NULL OR requested_chat_attempt_id IS NOT NULL "
            "OR requested_chat_kind IS NOT NULL OR actual_source_image_id IS NOT NULL "
            "UNION ALL SELECT 1 FROM product_events WHERE operator_action='read_chat_media')"
        )
    ):
        raise RuntimeError("Refusing to remove retained chat-media inspection facts")
    _inspection_constraints(BEFORE_AUDIT_SHAPE, BEFORE_EVENT_SHAPE)
    op.drop_constraint(
        "fk_operator_chat_media_attempt_source", "operator_audits", type_="foreignkey"
    )
    op.drop_constraint("fk_operator_chat_media_owner_source", "operator_audits", type_="foreignkey")
    for name in (
        "actual_source_image_id",
        "requested_chat_kind",
        "requested_chat_attempt_id",
        "requested_chat_owner_id",
    ):
        op.drop_column("operator_audits", name)
    op.drop_constraint("uq_chat_images_id_owner", "chat_image_preparations", type_="unique")
