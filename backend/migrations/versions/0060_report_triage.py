"""Actual privileged report triage evidence, bounded admission and runtime guard capability."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0060_report_triage"
down_revision: str | Sequence[str] | None = "0059_human_reviews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE_EVENT_SHAPE = (
    "((((((((((((((((((((((((((((kind != 'ai_job.completed' AND ai_job_id IS NULL AND ai_"
    "kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL) AND ((kind IN ('goal.saved'"
    ", 'goal.completed') AND goal_id IS NOT NULL AND goal_version IS NOT NULL AND topic_p"
    "resent IS NOT NULL AND shared_learning IS NOT NULL AND profile_version IS NULL AND v"
    "isibility_version IS NULL AND onboarding_task IS NULL) OR (kind = 'profile.ready' AN"
    "D profile_version IS NOT NULL AND onboarding_task IS NOT NULL AND onboarding_task IN"
    " ('find_help', 'offer_help') AND goal_id IS NULL AND goal_version IS NULL AND visibi"
    "lity_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_lea"
    "rning IS NULL) OR (kind IN ('profile.hidden', 'profile.restored', 'discovery.exposur"
    "e_confirmed') AND visibility_version IS NOT NULL AND goal_id IS NULL AND goal_versio"
    "n IS NULL AND profile_version IS NULL AND onboarding_task IS NULL AND subject_id IS "
    "NULL AND topic_present IS NULL AND shared_learning IS NULL) OR (kind = 'auth.email_c"
    "onfirmed' AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL A"
    "ND visibility_version IS NULL AND onboarding_task IS NULL AND subject_id IS NULL AND"
    " topic_present IS NULL AND shared_learning IS NULL))) OR (kind = 'ai_job.completed' "
    "AND ai_job_id IS NOT NULL AND ai_kind IS NOT NULL AND ai_kind IN ('clarify_goal','su"
    "ggest_subject','assess_photo','triage_report') AND ai_state IS NOT NULL AND ai_state"
    " IN ('succeeded','failed','cancelled','expired') AND (ai_reason IS NULL OR (ai_state"
    " IN ('failed','expired') AND ai_reason IN ('transient','invalid_output','invalid_inp"
    "ut','timeout','auth_unavailable','rate_limited','account_unavailable','stale_source'"
    ",'executor_lost'))) AND goal_id IS NULL AND goal_version IS NULL AND profile_version"
    " IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS "
    "NULL AND shared_learning IS NULL AND onboarding_task IS NULL)) AND report_id IS NULL"
    " AND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL) OR"
    " ((goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibili"
    "ty_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learn"
    "ing IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AN"
    "D ai_state IS NULL AND ai_reason IS NULL) AND ((kind = 'report.created' AND report_i"
    "d IS NOT NULL AND block_relationship_id IS NULL AND block_version IS NULL AND blocke"
    "d IS NULL) OR (kind = 'block.changed' AND report_id IS NULL AND block_relationship_i"
    "d IS NOT NULL AND block_version IS NOT NULL AND blocked IS NOT NULL)))) AND private_"
    "pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL) OR (kin"
    "d = 'discovery.pass_changed' AND private_pass_id IS NOT NULL AND private_pass_versio"
    "n IS NOT NULL AND private_passed IS NOT NULL AND goal_id IS NULL AND goal_version IS"
    " NULL AND profile_version IS NULL AND visibility_version IS NULL AND subject_id IS N"
    "ULL AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NUL"
    "L AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NU"
    "LL AND report_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL"
    " AND blocked IS NULL)) AND connection_request_id IS NULL AND connection_request_vers"
    "ion IS NULL AND connection_request_state IS NULL AND connection_request_recipient_id"
    " IS NULL AND request_initiator_id IS NULL) OR (kind = 'request.changed' AND connecti"
    "on_request_id IS NOT NULL AND connection_request_version IS NOT NULL AND connection_"
    "request_state IS NOT NULL AND connection_request_recipient_id IS NOT NULL AND (reque"
    "st_initiator_id IS NULL OR request_initiator_id IN (account_id, connection_request_r"
    "ecipient_id)) AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NU"
    "LL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL A"
    "ND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_"
    "kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND bl"
    "ock_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND privat"
    "e_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL)) AND "
    "request_view_ack_id IS NULL) OR (kind = 'request.view_acknowledged' AND request_view"
    "_ack_id IS NOT NULL AND goal_id IS NULL AND goal_version IS NULL AND profile_version"
    " IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS "
    "NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL A"
    "ND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL "
    "AND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND "
    "private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL "
    "AND connection_request_id IS NULL AND connection_request_version IS NULL AND connect"
    "ion_request_state IS NULL AND connection_request_recipient_id IS NULL AND request_in"
    "itiator_id IS NULL)) AND message_operation_id IS NULL AND message_operation_state IS"
    " NULL) OR (message_operation_id IS NOT NULL AND message_operation_state IS NOT NULL "
    "AND ((kind='message.confirmed' AND message_operation_state='confirmed') OR (kind='me"
    "ssage.cancelled' AND message_operation_state='cancelled')) AND goal_id IS NULL AND g"
    "oal_version IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND s"
    "ubject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboardi"
    "ng_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND a"
    "i_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND block_v"
    "ersion IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_vers"
    "ion IS NULL AND private_passed IS NULL AND connection_request_id IS NULL AND connect"
    "ion_request_version IS NULL AND connection_request_state IS NULL AND connection_requ"
    "est_recipient_id IS NULL AND request_view_ack_id IS NULL AND request_initiator_id IS"
    " NULL)) AND conversation_read_id IS NULL AND read_conversation_id IS NULL) OR (kind="
    "'conversation.read_acknowledged' AND conversation_read_id IS NOT NULL AND read_conve"
    "rsation_id IS NOT NULL AND goal_id IS NULL AND goal_version IS NULL AND profile_vers"
    "ion IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present "
    "IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NUL"
    "L AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NU"
    "LL AND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL A"
    "ND private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NU"
    "LL AND connection_request_id IS NULL AND connection_request_version IS NULL AND conn"
    "ection_request_state IS NULL AND connection_request_recipient_id IS NULL AND message"
    "_operation_id IS NULL AND message_operation_state IS NULL AND request_view_ack_id IS"
    " NULL AND request_initiator_id IS NULL)) AND goal_share_id IS NULL AND goal_share_co"
    "ntext_version IS NULL AND goal_share_conversation_id IS NULL) OR (kind='conversation"
    ".goal_shared' AND goal_share_id IS NOT NULL AND goal_share_context_version IS NOT NU"
    "LL AND goal_share_conversation_id IS NOT NULL AND goal_id IS NULL AND goal_version I"
    "S NULL AND profile_version IS NULL AND visibility_version IS NULL AND subject_id IS "
    "NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NU"
    "LL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS N"
    "ULL AND report_id IS NULL AND block_relationship_id IS NULL AND block_version IS NUL"
    "L AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL A"
    "ND private_passed IS NULL AND connection_request_id IS NULL AND connection_request_v"
    "ersion IS NULL AND connection_request_state IS NULL AND connection_request_recipient"
    "_id IS NULL AND conversation_read_id IS NULL AND read_conversation_id IS NULL AND me"
    "ssage_operation_id IS NULL AND message_operation_state IS NULL AND request_view_ack_"
    "id IS NULL AND request_initiator_id IS NULL)) AND operator_audit_id IS NULL AND oper"
    "ator_access_version IS NULL AND operator_action IS NULL) OR (kind='operator.inspecte"
    "d' AND operator_audit_id IS NOT NULL AND operator_access_version IS NOT NULL AND ope"
    "rator_action IS NOT NULL AND operator_action IN ('search_accounts','read_account','r"
    "ead_conversation_messages','search_events','read_event','read_audit','search_reports"
    "','read_report','read_media','read_support_case','search_support_cases','search_deli"
    "very_sources','read_delivery_source','read_chat_media','search_audits') AND goal_id "
    "IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibility_version "
    "IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL"
    " AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state "
    "IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NUL"
    "L AND block_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND priv"
    "ate_pass_version IS NULL AND private_passed IS NULL AND connection_request_id IS NUL"
    "L AND connection_request_version IS NULL AND connection_request_state IS NULL AND co"
    "nnection_request_recipient_id IS NULL AND goal_share_id IS NULL AND goal_share_conve"
    "rsation_id IS NULL AND goal_share_context_version IS NULL AND conversation_read_id I"
    "S NULL AND read_conversation_id IS NULL AND message_operation_id IS NULL AND message"
    "_operation_state IS NULL AND request_view_ack_id IS NULL AND request_initiator_id IS"
    " NULL)) AND study_outcome_id IS NULL AND study_conversation_id IS NULL AND study_out"
    "come_version IS NULL AND study_answer IS NULL AND peer_feedback_id IS NULL AND peer_"
    "feedback_version IS NULL AND feedback_again IS NULL AND study_prompt_id IS NULL AND "
    "study_prompt_conversation_id IS NULL) OR (kind='study.reported' AND study_outcome_id"
    " IS NOT NULL AND study_conversation_id IS NOT NULL AND study_outcome_version IS NOT "
    "NULL AND study_answer IS NOT NULL AND peer_feedback_id IS NULL AND peer_feedback_ver"
    "sion IS NULL AND feedback_again IS NULL AND study_prompt_id IS NULL AND study_prompt"
    "_conversation_id IS NULL AND study_answer IN ('yes','not_yet','did_not_work_out') AN"
    "D goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibilit"
    "y_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learni"
    "ng IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND"
    " ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_relationship"
    "_id IS NULL AND block_version IS NULL AND blocked IS NULL AND private_pass_id IS NUL"
    "L AND private_pass_version IS NULL AND private_passed IS NULL AND connection_request"
    "_id IS NULL AND connection_request_version IS NULL AND connection_request_state IS N"
    "ULL AND connection_request_recipient_id IS NULL AND goal_share_id IS NULL AND goal_s"
    "hare_conversation_id IS NULL AND goal_share_context_version IS NULL AND conversation"
    "_read_id IS NULL AND read_conversation_id IS NULL AND message_operation_id IS NULL A"
    "ND message_operation_state IS NULL AND request_view_ack_id IS NULL AND request_initi"
    "ator_id IS NULL AND operator_audit_id IS NULL AND operator_access_version IS NULL AN"
    "D operator_action IS NULL) OR (kind='feedback.saved' AND study_outcome_id IS NULL AN"
    "D study_conversation_id IS NULL AND study_outcome_version IS NULL AND study_answer I"
    "S NULL AND peer_feedback_id IS NOT NULL AND peer_feedback_version IS NOT NULL AND fe"
    "edback_again IS NOT NULL AND study_prompt_id IS NULL AND study_prompt_conversation_i"
    "d IS NULL AND feedback_again IN ('yes','maybe','no') AND goal_id IS NULL AND goal_ve"
    "rsion IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND subject"
    "_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_tas"
    "k IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reas"
    "on IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND block_version"
    " IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS"
    " NULL AND private_passed IS NULL AND connection_request_id IS NULL AND connection_re"
    "quest_version IS NULL AND connection_request_state IS NULL AND connection_request_re"
    "cipient_id IS NULL AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL "
    "AND goal_share_context_version IS NULL AND conversation_read_id IS NULL AND read_con"
    "versation_id IS NULL AND message_operation_id IS NULL AND message_operation_state IS"
    " NULL AND request_view_ack_id IS NULL AND request_initiator_id IS NULL AND operator_"
    "audit_id IS NULL AND operator_access_version IS NULL AND operator_action IS NULL) OR"
    " (kind='study.prompt_offered' AND study_outcome_id IS NULL AND study_conversation_id"
    " IS NULL AND study_outcome_version IS NULL AND study_answer IS NULL AND peer_feedbac"
    "k_id IS NULL AND peer_feedback_version IS NULL AND feedback_again IS NULL AND study_"
    "prompt_id IS NOT NULL AND study_prompt_conversation_id IS NOT NULL AND TRUE AND goal"
    "_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibility_vers"
    "ion IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS "
    "NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_st"
    "ate IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS"
    " NULL AND block_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND "
    "private_pass_version IS NULL AND private_passed IS NULL AND connection_request_id IS"
    " NULL AND connection_request_version IS NULL AND connection_request_state IS NULL AN"
    "D connection_request_recipient_id IS NULL AND goal_share_id IS NULL AND goal_share_c"
    "onversation_id IS NULL AND goal_share_context_version IS NULL AND conversation_read_"
    "id IS NULL AND read_conversation_id IS NULL AND message_operation_id IS NULL AND mes"
    "sage_operation_state IS NULL AND request_view_ack_id IS NULL AND request_initiator_i"
    "d IS NULL AND operator_audit_id IS NULL AND operator_access_version IS NULL AND oper"
    "ator_action IS NULL)) AND help_version IS NULL AND photo_version IS NULL) OR (kind='"
    "profile.saved' AND profile_version IS NOT NULL AND goal_id IS NULL AND goal_version "
    "IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS N"
    "ULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AN"
    "D ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL A"
    "ND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND p"
    "rivate_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL A"
    "ND connection_request_id IS NULL AND connection_request_version IS NULL AND connecti"
    "on_request_state IS NULL AND connection_request_recipient_id IS NULL AND goal_share_"
    "id IS NULL AND goal_share_conversation_id IS NULL AND goal_share_context_version IS "
    "NULL AND conversation_read_id IS NULL AND read_conversation_id IS NULL AND message_o"
    "peration_id IS NULL AND message_operation_state IS NULL AND request_view_ack_id IS N"
    "ULL AND request_initiator_id IS NULL AND operator_audit_id IS NULL AND operator_acce"
    "ss_version IS NULL AND operator_action IS NULL AND study_outcome_id IS NULL AND stud"
    "y_conversation_id IS NULL AND study_outcome_version IS NULL AND study_answer IS NULL"
    " AND peer_feedback_id IS NULL AND peer_feedback_version IS NULL AND feedback_again I"
    "S NULL AND study_prompt_id IS NULL AND study_prompt_conversation_id IS NULL AND help"
    "_version IS NULL AND photo_version IS NULL) OR (kind='help.saved' AND help_version I"
    "S NOT NULL AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL "
    "AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND "
    "shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kin"
    "d IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block"
    "_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND private_p"
    "ass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL AND conne"
    "ction_request_id IS NULL AND connection_request_version IS NULL AND connection_reque"
    "st_state IS NULL AND connection_request_recipient_id IS NULL AND goal_share_id IS NU"
    "LL AND goal_share_conversation_id IS NULL AND goal_share_context_version IS NULL AND"
    " conversation_read_id IS NULL AND read_conversation_id IS NULL AND message_operation"
    "_id IS NULL AND message_operation_state IS NULL AND request_view_ack_id IS NULL AND "
    "request_initiator_id IS NULL AND operator_audit_id IS NULL AND operator_access_versi"
    "on IS NULL AND operator_action IS NULL AND study_outcome_id IS NULL AND study_conver"
    "sation_id IS NULL AND study_outcome_version IS NULL AND study_answer IS NULL AND pee"
    "r_feedback_id IS NULL AND peer_feedback_version IS NULL AND feedback_again IS NULL A"
    "ND study_prompt_id IS NULL AND study_prompt_conversation_id IS NULL AND photo_versio"
    "n IS NULL) OR (kind='photo.published' AND photo_version IS NOT NULL AND goal_id IS N"
    "ULL AND goal_version IS NULL AND profile_version IS NULL AND visibility_version IS N"
    "ULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND"
    " onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS N"
    "ULL AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AN"
    "D block_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_"
    "pass_version IS NULL AND private_passed IS NULL AND connection_request_id IS NULL AN"
    "D connection_request_version IS NULL AND connection_request_state IS NULL AND connec"
    "tion_request_recipient_id IS NULL AND goal_share_id IS NULL AND goal_share_conversat"
    "ion_id IS NULL AND goal_share_context_version IS NULL AND conversation_read_id IS NU"
    "LL AND read_conversation_id IS NULL AND message_operation_id IS NULL AND message_ope"
    "ration_state IS NULL AND request_view_ack_id IS NULL AND request_initiator_id IS NUL"
    "L AND operator_audit_id IS NULL AND operator_access_version IS NULL AND operator_act"
    "ion IS NULL AND study_outcome_id IS NULL AND study_conversation_id IS NULL AND study"
    "_outcome_version IS NULL AND study_answer IS NULL AND peer_feedback_id IS NULL AND p"
    "eer_feedback_version IS NULL AND feedback_again IS NULL AND study_prompt_id IS NULL "
    "AND study_prompt_conversation_id IS NULL AND help_version IS NULL)) AND lifecycle_re"
    "vision_id IS NULL AND lifecycle_account_id IS NULL AND lifecycle_version IS NULL AND"
    " lifecycle_operation IS NULL) OR (kind='account.lifecycle_changed' AND lifecycle_rev"
    "ision_id IS NOT NULL AND lifecycle_account_id IS NOT NULL AND lifecycle_version IS N"
    "OT NULL AND lifecycle_version>0 AND lifecycle_operation IS NOT NULL AND lifecycle_op"
    "eration IN ('ban','unban','delete') AND goal_id IS NULL AND goal_version IS NULL AND"
    " profile_version IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND t"
    "opic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_"
    "job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND re"
    "port_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AND bloc"
    "ked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND private"
    "_passed IS NULL AND connection_request_id IS NULL AND connection_request_version IS "
    "NULL AND connection_request_state IS NULL AND connection_request_recipient_id IS NUL"
    "L AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND goal_share_co"
    "ntext_version IS NULL AND conversation_read_id IS NULL AND read_conversation_id IS N"
    "ULL AND message_operation_id IS NULL AND message_operation_state IS NULL AND request"
    "_view_ack_id IS NULL AND request_initiator_id IS NULL AND operator_audit_id IS NULL "
    "AND operator_access_version IS NULL AND operator_action IS NULL AND study_outcome_id"
    " IS NULL AND study_conversation_id IS NULL AND study_outcome_version IS NULL AND stu"
    "dy_answer IS NULL AND peer_feedback_id IS NULL AND peer_feedback_version IS NULL AND"
    " feedback_again IS NULL AND study_prompt_id IS NULL AND study_prompt_conversation_id"
    " IS NULL AND help_version IS NULL AND photo_version IS NULL)) AND notification_prefe"
    "rence_version IS NULL AND support_case_id IS NULL AND support_case_version IS NULL) "
    "OR (kind='notification_preference.changed' AND notification_preference_version IS NO"
    "T NULL AND notification_preference_version>0 AND support_case_id IS NULL AND support"
    "_case_version IS NULL AND goal_id IS NULL AND goal_version IS NULL AND profile_versi"
    "on IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present I"
    "S NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL"
    " AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NUL"
    "L AND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AN"
    "D private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NUL"
    "L AND connection_request_id IS NULL AND connection_request_version IS NULL AND conne"
    "ction_request_state IS NULL AND connection_request_recipient_id IS NULL AND goal_sha"
    "re_id IS NULL AND goal_share_conversation_id IS NULL AND goal_share_context_version "
    "IS NULL AND conversation_read_id IS NULL AND read_conversation_id IS NULL AND messag"
    "e_operation_id IS NULL AND message_operation_state IS NULL AND request_view_ack_id I"
    "S NULL AND request_initiator_id IS NULL AND operator_audit_id IS NULL AND operator_a"
    "ccess_version IS NULL AND operator_action IS NULL AND study_outcome_id IS NULL AND s"
    "tudy_conversation_id IS NULL AND study_outcome_version IS NULL AND study_answer IS N"
    "ULL AND peer_feedback_id IS NULL AND peer_feedback_version IS NULL AND feedback_agai"
    "n IS NULL AND study_prompt_id IS NULL AND study_prompt_conversation_id IS NULL AND h"
    "elp_version IS NULL AND photo_version IS NULL AND lifecycle_revision_id IS NULL AND "
    "lifecycle_account_id IS NULL AND lifecycle_version IS NULL AND lifecycle_operation I"
    "S NULL) OR (kind IN ('support.received','support.status_changed') AND support_case_i"
    "d IS NOT NULL AND support_case_version IS NOT NULL AND support_case_version>0 AND no"
    "tification_preference_version IS NULL AND goal_id IS NULL AND goal_version IS NULL A"
    "ND profile_version IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND"
    " topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND a"
    "i_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND "
    "report_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AND bl"
    "ocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND priva"
    "te_passed IS NULL AND connection_request_id IS NULL AND connection_request_version I"
    "S NULL AND connection_request_state IS NULL AND connection_request_recipient_id IS N"
    "ULL AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND goal_share_"
    "context_version IS NULL AND conversation_read_id IS NULL AND read_conversation_id IS"
    " NULL AND message_operation_id IS NULL AND message_operation_state IS NULL AND reque"
    "st_view_ack_id IS NULL AND request_initiator_id IS NULL AND operator_audit_id IS NUL"
    "L AND operator_access_version IS NULL AND operator_action IS NULL AND study_outcome_"
    "id IS NULL AND study_conversation_id IS NULL AND study_outcome_version IS NULL AND s"
    "tudy_answer IS NULL AND peer_feedback_id IS NULL AND peer_feedback_version IS NULL A"
    "ND feedback_again IS NULL AND study_prompt_id IS NULL AND study_prompt_conversation_"
    "id IS NULL AND help_version IS NULL AND photo_version IS NULL AND lifecycle_revision"
    "_id IS NULL AND lifecycle_account_id IS NULL AND lifecycle_version IS NULL AND lifec"
    "ycle_operation IS NULL)) AND report_review_id IS NULL AND report_review_report_id IS"
    " NULL AND report_review_version IS NULL AND report_review_action IS NULL AND photo_r"
    "eview_id IS NULL AND photo_review_version IS NULL AND photo_review_action IS NULL) O"
    "R (kind='report.reviewed' AND report_review_report_id IS NOT NULL AND report_review_"
    "id IS NOT NULL AND report_review_version IS NOT NULL AND report_review_version>0 AND"
    " report_review_action IS NOT NULL AND report_review_action IN ('dismiss','escalate')"
    " AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibi"
    "lity_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_lea"
    "rning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL "
    "AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_relations"
    "hip_id IS NULL AND block_version IS NULL AND blocked IS NULL AND private_pass_id IS "
    "NULL AND private_pass_version IS NULL AND private_passed IS NULL AND connection_requ"
    "est_id IS NULL AND connection_request_version IS NULL AND connection_request_state I"
    "S NULL AND connection_request_recipient_id IS NULL AND goal_share_id IS NULL AND goa"
    "l_share_conversation_id IS NULL AND goal_share_context_version IS NULL AND conversat"
    "ion_read_id IS NULL AND read_conversation_id IS NULL AND message_operation_id IS NUL"
    "L AND message_operation_state IS NULL AND request_view_ack_id IS NULL AND request_in"
    "itiator_id IS NULL AND operator_audit_id IS NULL AND operator_access_version IS NULL"
    " AND operator_action IS NULL AND study_outcome_id IS NULL AND study_conversation_id "
    "IS NULL AND study_outcome_version IS NULL AND study_answer IS NULL AND peer_feedback"
    "_id IS NULL AND peer_feedback_version IS NULL AND feedback_again IS NULL AND study_p"
    "rompt_id IS NULL AND study_prompt_conversation_id IS NULL AND help_version IS NULL A"
    "ND photo_version IS NULL AND lifecycle_revision_id IS NULL AND lifecycle_account_id "
    "IS NULL AND lifecycle_version IS NULL AND lifecycle_operation IS NULL AND notificati"
    "on_preference_version IS NULL AND support_case_id IS NULL AND support_case_version I"
    "S NULL AND photo_review_id IS NULL AND photo_review_version IS NULL AND photo_review"
    "_action IS NULL) OR (kind='photo.reviewed' AND photo_review_id IS NOT NULL AND photo"
    "_review_version IS NOT NULL AND photo_review_version>0 AND photo_review_action IS NO"
    "T NULL AND photo_review_action IN ('require_replacement','approve_replacement') AND "
    "goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibility_"
    "version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning"
    " IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND a"
    "i_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_i"
    "d IS NULL AND block_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL "
    "AND private_pass_version IS NULL AND private_passed IS NULL AND connection_request_i"
    "d IS NULL AND connection_request_version IS NULL AND connection_request_state IS NUL"
    "L AND connection_request_recipient_id IS NULL AND goal_share_id IS NULL AND goal_sha"
    "re_conversation_id IS NULL AND goal_share_context_version IS NULL AND conversation_r"
    "ead_id IS NULL AND read_conversation_id IS NULL AND message_operation_id IS NULL AND"
    " message_operation_state IS NULL AND request_view_ack_id IS NULL AND request_initiat"
    "or_id IS NULL AND operator_audit_id IS NULL AND operator_access_version IS NULL AND "
    "operator_action IS NULL AND study_outcome_id IS NULL AND study_conversation_id IS NU"
    "LL AND study_outcome_version IS NULL AND study_answer IS NULL AND peer_feedback_id I"
    "S NULL AND peer_feedback_version IS NULL AND feedback_again IS NULL AND study_prompt"
    "_id IS NULL AND study_prompt_conversation_id IS NULL AND help_version IS NULL AND ph"
    "oto_version IS NULL AND lifecycle_revision_id IS NULL AND lifecycle_account_id IS NU"
    "LL AND lifecycle_version IS NULL AND lifecycle_operation IS NULL AND notification_pr"
    "eference_version IS NULL AND support_case_id IS NULL AND support_case_version IS NUL"
    "L AND report_review_id IS NULL AND report_review_report_id IS NULL AND report_review"
    "_version IS NULL AND report_review_action IS NULL)"
)
EVENT_SHAPE = (
    "((((((((((((((((((((((((((((((kind != 'ai_job.completed' AND ai_job_id IS NULL AND a"
    "i_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL) AND ((kind IN ('goal.save"
    "d', 'goal.completed') AND goal_id IS NOT NULL AND goal_version IS NOT NULL AND topic"
    "_present IS NOT NULL AND shared_learning IS NOT NULL AND profile_version IS NULL AND"
    " visibility_version IS NULL AND onboarding_task IS NULL) OR (kind = 'profile.ready' "
    "AND profile_version IS NOT NULL AND onboarding_task IS NOT NULL AND onboarding_task "
    "IN ('find_help', 'offer_help') AND goal_id IS NULL AND goal_version IS NULL AND visi"
    "bility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_l"
    "earning IS NULL) OR (kind IN ('profile.hidden', 'profile.restored', 'discovery.expos"
    "ure_confirmed') AND visibility_version IS NOT NULL AND goal_id IS NULL AND goal_vers"
    "ion IS NULL AND profile_version IS NULL AND onboarding_task IS NULL AND subject_id I"
    "S NULL AND topic_present IS NULL AND shared_learning IS NULL) OR (kind = 'auth.email"
    "_confirmed' AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL"
    " AND visibility_version IS NULL AND onboarding_task IS NULL AND subject_id IS NULL A"
    "ND topic_present IS NULL AND shared_learning IS NULL))) OR (kind = 'ai_job.completed"
    "' AND ai_job_id IS NOT NULL AND ai_kind IS NOT NULL AND ai_kind IN ('clarify_goal','"
    "suggest_subject','assess_photo','triage_report') AND ai_state IS NOT NULL AND ai_sta"
    "te IN ('succeeded','failed','cancelled','expired') AND (ai_reason IS NULL OR (ai_sta"
    "te IN ('failed','expired') AND ai_reason IN ('transient','invalid_output','invalid_i"
    "nput','timeout','auth_unavailable','rate_limited','account_unavailable','stale_sourc"
    "e','executor_lost'))) AND goal_id IS NULL AND goal_version IS NULL AND profile_versi"
    "on IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present I"
    "S NULL AND shared_learning IS NULL AND onboarding_task IS NULL)) AND report_id IS NU"
    "LL AND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL) "
    "OR ((goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibi"
    "lity_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_lea"
    "rning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL "
    "AND ai_state IS NULL AND ai_reason IS NULL) AND ((kind = 'report.created' AND report"
    "_id IS NOT NULL AND block_relationship_id IS NULL AND block_version IS NULL AND bloc"
    "ked IS NULL) OR (kind = 'block.changed' AND report_id IS NULL AND block_relationship"
    "_id IS NOT NULL AND block_version IS NOT NULL AND blocked IS NOT NULL)))) AND privat"
    "e_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL) OR (k"
    "ind = 'discovery.pass_changed' AND private_pass_id IS NOT NULL AND private_pass_vers"
    "ion IS NOT NULL AND private_passed IS NOT NULL AND goal_id IS NULL AND goal_version "
    "IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND subject_id IS"
    " NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS N"
    "ULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS "
    "NULL AND report_id IS NULL AND block_relationship_id IS NULL AND block_version IS NU"
    "LL AND blocked IS NULL)) AND connection_request_id IS NULL AND connection_request_ve"
    "rsion IS NULL AND connection_request_state IS NULL AND connection_request_recipient_"
    "id IS NULL AND request_initiator_id IS NULL) OR (kind = 'request.changed' AND connec"
    "tion_request_id IS NOT NULL AND connection_request_version IS NOT NULL AND connectio"
    "n_request_state IS NOT NULL AND connection_request_recipient_id IS NOT NULL AND (req"
    "uest_initiator_id IS NULL OR request_initiator_id IN (account_id, connection_request"
    "_recipient_id)) AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS "
    "NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL"
    " AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND a"
    "i_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND "
    "block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND priv"
    "ate_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL)) AN"
    "D request_view_ack_id IS NULL) OR (kind = 'request.view_acknowledged' AND request_vi"
    "ew_ack_id IS NOT NULL AND goal_id IS NULL AND goal_version IS NULL AND profile_versi"
    "on IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present I"
    "S NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL"
    " AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NUL"
    "L AND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AN"
    "D private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NUL"
    "L AND connection_request_id IS NULL AND connection_request_version IS NULL AND conne"
    "ction_request_state IS NULL AND connection_request_recipient_id IS NULL AND request_"
    "initiator_id IS NULL)) AND message_operation_id IS NULL AND message_operation_state "
    "IS NULL) OR (message_operation_id IS NOT NULL AND message_operation_state IS NOT NUL"
    "L AND ((kind='message.confirmed' AND message_operation_state='confirmed') OR (kind='"
    "message.cancelled' AND message_operation_state='cancelled')) AND goal_id IS NULL AND"
    " goal_version IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND"
    " subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboar"
    "ding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND"
    " ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND block"
    "_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_ve"
    "rsion IS NULL AND private_passed IS NULL AND connection_request_id IS NULL AND conne"
    "ction_request_version IS NULL AND connection_request_state IS NULL AND connection_re"
    "quest_recipient_id IS NULL AND request_view_ack_id IS NULL AND request_initiator_id "
    "IS NULL)) AND conversation_read_id IS NULL AND read_conversation_id IS NULL) OR (kin"
    "d='conversation.read_acknowledged' AND conversation_read_id IS NOT NULL AND read_con"
    "versation_id IS NOT NULL AND goal_id IS NULL AND goal_version IS NULL AND profile_ve"
    "rsion IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_presen"
    "t IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS N"
    "ULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS "
    "NULL AND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL"
    " AND private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS "
    "NULL AND connection_request_id IS NULL AND connection_request_version IS NULL AND co"
    "nnection_request_state IS NULL AND connection_request_recipient_id IS NULL AND messa"
    "ge_operation_id IS NULL AND message_operation_state IS NULL AND request_view_ack_id "
    "IS NULL AND request_initiator_id IS NULL)) AND goal_share_id IS NULL AND goal_share_"
    "context_version IS NULL AND goal_share_conversation_id IS NULL) OR (kind='conversati"
    "on.goal_shared' AND goal_share_id IS NOT NULL AND goal_share_context_version IS NOT "
    "NULL AND goal_share_conversation_id IS NOT NULL AND goal_id IS NULL AND goal_version"
    " IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND subject_id I"
    "S NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS "
    "NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS"
    " NULL AND report_id IS NULL AND block_relationship_id IS NULL AND block_version IS N"
    "ULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL"
    " AND private_passed IS NULL AND connection_request_id IS NULL AND connection_request"
    "_version IS NULL AND connection_request_state IS NULL AND connection_request_recipie"
    "nt_id IS NULL AND conversation_read_id IS NULL AND read_conversation_id IS NULL AND "
    "message_operation_id IS NULL AND message_operation_state IS NULL AND request_view_ac"
    "k_id IS NULL AND request_initiator_id IS NULL)) AND operator_audit_id IS NULL AND op"
    "erator_access_version IS NULL AND operator_action IS NULL) OR (kind='operator.inspec"
    "ted' AND operator_audit_id IS NOT NULL AND operator_access_version IS NOT NULL AND o"
    "perator_action IS NOT NULL AND operator_action IN ('search_accounts','read_account',"
    "'read_conversation_messages','search_events','read_event','read_audit','search_repor"
    "ts','read_report','read_media','read_support_case','search_support_cases','search_de"
    "livery_sources','read_delivery_source','read_chat_media','search_audits') AND goal_i"
    "d IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibility_versio"
    "n IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NU"
    "LL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_stat"
    "e IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS N"
    "ULL AND block_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND pr"
    "ivate_pass_version IS NULL AND private_passed IS NULL AND connection_request_id IS N"
    "ULL AND connection_request_version IS NULL AND connection_request_state IS NULL AND "
    "connection_request_recipient_id IS NULL AND goal_share_id IS NULL AND goal_share_con"
    "versation_id IS NULL AND goal_share_context_version IS NULL AND conversation_read_id"
    " IS NULL AND read_conversation_id IS NULL AND message_operation_id IS NULL AND messa"
    "ge_operation_state IS NULL AND request_view_ack_id IS NULL AND request_initiator_id "
    "IS NULL)) AND study_outcome_id IS NULL AND study_conversation_id IS NULL AND study_o"
    "utcome_version IS NULL AND study_answer IS NULL AND peer_feedback_id IS NULL AND pee"
    "r_feedback_version IS NULL AND feedback_again IS NULL AND study_prompt_id IS NULL AN"
    "D study_prompt_conversation_id IS NULL) OR (kind='study.reported' AND study_outcome_"
    "id IS NOT NULL AND study_conversation_id IS NOT NULL AND study_outcome_version IS NO"
    "T NULL AND study_answer IS NOT NULL AND peer_feedback_id IS NULL AND peer_feedback_v"
    "ersion IS NULL AND feedback_again IS NULL AND study_prompt_id IS NULL AND study_prom"
    "pt_conversation_id IS NULL AND study_answer IN ('yes','not_yet','did_not_work_out') "
    "AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibil"
    "ity_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_lear"
    "ning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL A"
    "ND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_relationsh"
    "ip_id IS NULL AND block_version IS NULL AND blocked IS NULL AND private_pass_id IS N"
    "ULL AND private_pass_version IS NULL AND private_passed IS NULL AND connection_reque"
    "st_id IS NULL AND connection_request_version IS NULL AND connection_request_state IS"
    " NULL AND connection_request_recipient_id IS NULL AND goal_share_id IS NULL AND goal"
    "_share_conversation_id IS NULL AND goal_share_context_version IS NULL AND conversati"
    "on_read_id IS NULL AND read_conversation_id IS NULL AND message_operation_id IS NULL"
    " AND message_operation_state IS NULL AND request_view_ack_id IS NULL AND request_ini"
    "tiator_id IS NULL AND operator_audit_id IS NULL AND operator_access_version IS NULL "
    "AND operator_action IS NULL) OR (kind='feedback.saved' AND study_outcome_id IS NULL "
    "AND study_conversation_id IS NULL AND study_outcome_version IS NULL AND study_answer"
    " IS NULL AND peer_feedback_id IS NOT NULL AND peer_feedback_version IS NOT NULL AND "
    "feedback_again IS NOT NULL AND study_prompt_id IS NULL AND study_prompt_conversation"
    "_id IS NULL AND feedback_again IN ('yes','maybe','no') AND goal_id IS NULL AND goal_"
    "version IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND subje"
    "ct_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_t"
    "ask IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_re"
    "ason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND block_versi"
    "on IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_version "
    "IS NULL AND private_passed IS NULL AND connection_request_id IS NULL AND connection_"
    "request_version IS NULL AND connection_request_state IS NULL AND connection_request_"
    "recipient_id IS NULL AND goal_share_id IS NULL AND goal_share_conversation_id IS NUL"
    "L AND goal_share_context_version IS NULL AND conversation_read_id IS NULL AND read_c"
    "onversation_id IS NULL AND message_operation_id IS NULL AND message_operation_state "
    "IS NULL AND request_view_ack_id IS NULL AND request_initiator_id IS NULL AND operato"
    "r_audit_id IS NULL AND operator_access_version IS NULL AND operator_action IS NULL) "
    "OR (kind='study.prompt_offered' AND study_outcome_id IS NULL AND study_conversation_"
    "id IS NULL AND study_outcome_version IS NULL AND study_answer IS NULL AND peer_feedb"
    "ack_id IS NULL AND peer_feedback_version IS NULL AND feedback_again IS NULL AND stud"
    "y_prompt_id IS NOT NULL AND study_prompt_conversation_id IS NOT NULL AND TRUE AND go"
    "al_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibility_ve"
    "rsion IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning I"
    "S NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_"
    "state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id "
    "IS NULL AND block_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AN"
    "D private_pass_version IS NULL AND private_passed IS NULL AND connection_request_id "
    "IS NULL AND connection_request_version IS NULL AND connection_request_state IS NULL "
    "AND connection_request_recipient_id IS NULL AND goal_share_id IS NULL AND goal_share"
    "_conversation_id IS NULL AND goal_share_context_version IS NULL AND conversation_rea"
    "d_id IS NULL AND read_conversation_id IS NULL AND message_operation_id IS NULL AND m"
    "essage_operation_state IS NULL AND request_view_ack_id IS NULL AND request_initiator"
    "_id IS NULL AND operator_audit_id IS NULL AND operator_access_version IS NULL AND op"
    "erator_action IS NULL)) AND help_version IS NULL AND photo_version IS NULL) OR (kind"
    "='profile.saved' AND profile_version IS NOT NULL AND goal_id IS NULL AND goal_versio"
    "n IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS"
    " NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL "
    "AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL"
    " AND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND"
    " private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL"
    " AND connection_request_id IS NULL AND connection_request_version IS NULL AND connec"
    "tion_request_state IS NULL AND connection_request_recipient_id IS NULL AND goal_shar"
    "e_id IS NULL AND goal_share_conversation_id IS NULL AND goal_share_context_version I"
    "S NULL AND conversation_read_id IS NULL AND read_conversation_id IS NULL AND message"
    "_operation_id IS NULL AND message_operation_state IS NULL AND request_view_ack_id IS"
    " NULL AND request_initiator_id IS NULL AND operator_audit_id IS NULL AND operator_ac"
    "cess_version IS NULL AND operator_action IS NULL AND study_outcome_id IS NULL AND st"
    "udy_conversation_id IS NULL AND study_outcome_version IS NULL AND study_answer IS NU"
    "LL AND peer_feedback_id IS NULL AND peer_feedback_version IS NULL AND feedback_again"
    " IS NULL AND study_prompt_id IS NULL AND study_prompt_conversation_id IS NULL AND he"
    "lp_version IS NULL AND photo_version IS NULL) OR (kind='help.saved' AND help_version"
    " IS NOT NULL AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NUL"
    "L AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AN"
    "D shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_k"
    "ind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND blo"
    "ck_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND private"
    "_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL AND con"
    "nection_request_id IS NULL AND connection_request_version IS NULL AND connection_req"
    "uest_state IS NULL AND connection_request_recipient_id IS NULL AND goal_share_id IS "
    "NULL AND goal_share_conversation_id IS NULL AND goal_share_context_version IS NULL A"
    "ND conversation_read_id IS NULL AND read_conversation_id IS NULL AND message_operati"
    "on_id IS NULL AND message_operation_state IS NULL AND request_view_ack_id IS NULL AN"
    "D request_initiator_id IS NULL AND operator_audit_id IS NULL AND operator_access_ver"
    "sion IS NULL AND operator_action IS NULL AND study_outcome_id IS NULL AND study_conv"
    "ersation_id IS NULL AND study_outcome_version IS NULL AND study_answer IS NULL AND p"
    "eer_feedback_id IS NULL AND peer_feedback_version IS NULL AND feedback_again IS NULL"
    " AND study_prompt_id IS NULL AND study_prompt_conversation_id IS NULL AND photo_vers"
    "ion IS NULL) OR (kind='photo.published' AND photo_version IS NOT NULL AND goal_id IS"
    " NULL AND goal_version IS NULL AND profile_version IS NULL AND visibility_version IS"
    " NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL A"
    "ND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS"
    " NULL AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL "
    "AND block_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND privat"
    "e_pass_version IS NULL AND private_passed IS NULL AND connection_request_id IS NULL "
    "AND connection_request_version IS NULL AND connection_request_state IS NULL AND conn"
    "ection_request_recipient_id IS NULL AND goal_share_id IS NULL AND goal_share_convers"
    "ation_id IS NULL AND goal_share_context_version IS NULL AND conversation_read_id IS "
    "NULL AND read_conversation_id IS NULL AND message_operation_id IS NULL AND message_o"
    "peration_state IS NULL AND request_view_ack_id IS NULL AND request_initiator_id IS N"
    "ULL AND operator_audit_id IS NULL AND operator_access_version IS NULL AND operator_a"
    "ction IS NULL AND study_outcome_id IS NULL AND study_conversation_id IS NULL AND stu"
    "dy_outcome_version IS NULL AND study_answer IS NULL AND peer_feedback_id IS NULL AND"
    " peer_feedback_version IS NULL AND feedback_again IS NULL AND study_prompt_id IS NUL"
    "L AND study_prompt_conversation_id IS NULL AND help_version IS NULL)) AND lifecycle_"
    "revision_id IS NULL AND lifecycle_account_id IS NULL AND lifecycle_version IS NULL A"
    "ND lifecycle_operation IS NULL) OR (kind='account.lifecycle_changed' AND lifecycle_r"
    "evision_id IS NOT NULL AND lifecycle_account_id IS NOT NULL AND lifecycle_version IS"
    " NOT NULL AND lifecycle_version>0 AND lifecycle_operation IS NOT NULL AND lifecycle_"
    "operation IN ('ban','unban','delete') AND goal_id IS NULL AND goal_version IS NULL A"
    "ND profile_version IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND"
    " topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND a"
    "i_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND "
    "report_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AND bl"
    "ocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND priva"
    "te_passed IS NULL AND connection_request_id IS NULL AND connection_request_version I"
    "S NULL AND connection_request_state IS NULL AND connection_request_recipient_id IS N"
    "ULL AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND goal_share_"
    "context_version IS NULL AND conversation_read_id IS NULL AND read_conversation_id IS"
    " NULL AND message_operation_id IS NULL AND message_operation_state IS NULL AND reque"
    "st_view_ack_id IS NULL AND request_initiator_id IS NULL AND operator_audit_id IS NUL"
    "L AND operator_access_version IS NULL AND operator_action IS NULL AND study_outcome_"
    "id IS NULL AND study_conversation_id IS NULL AND study_outcome_version IS NULL AND s"
    "tudy_answer IS NULL AND peer_feedback_id IS NULL AND peer_feedback_version IS NULL A"
    "ND feedback_again IS NULL AND study_prompt_id IS NULL AND study_prompt_conversation_"
    "id IS NULL AND help_version IS NULL AND photo_version IS NULL)) AND notification_pre"
    "ference_version IS NULL AND support_case_id IS NULL AND support_case_version IS NULL"
    ") OR (kind='notification_preference.changed' AND notification_preference_version IS "
    "NOT NULL AND notification_preference_version>0 AND support_case_id IS NULL AND suppo"
    "rt_case_version IS NULL AND goal_id IS NULL AND goal_version IS NULL AND profile_ver"
    "sion IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present"
    " IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NU"
    "LL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS N"
    "ULL AND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL "
    "AND private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS N"
    "ULL AND connection_request_id IS NULL AND connection_request_version IS NULL AND con"
    "nection_request_state IS NULL AND connection_request_recipient_id IS NULL AND goal_s"
    "hare_id IS NULL AND goal_share_conversation_id IS NULL AND goal_share_context_versio"
    "n IS NULL AND conversation_read_id IS NULL AND read_conversation_id IS NULL AND mess"
    "age_operation_id IS NULL AND message_operation_state IS NULL AND request_view_ack_id"
    " IS NULL AND request_initiator_id IS NULL AND operator_audit_id IS NULL AND operator"
    "_access_version IS NULL AND operator_action IS NULL AND study_outcome_id IS NULL AND"
    " study_conversation_id IS NULL AND study_outcome_version IS NULL AND study_answer IS"
    " NULL AND peer_feedback_id IS NULL AND peer_feedback_version IS NULL AND feedback_ag"
    "ain IS NULL AND study_prompt_id IS NULL AND study_prompt_conversation_id IS NULL AND"
    " help_version IS NULL AND photo_version IS NULL AND lifecycle_revision_id IS NULL AN"
    "D lifecycle_account_id IS NULL AND lifecycle_version IS NULL AND lifecycle_operation"
    " IS NULL) OR (kind IN ('support.received','support.status_changed') AND support_case"
    "_id IS NOT NULL AND support_case_version IS NOT NULL AND support_case_version>0 AND "
    "notification_preference_version IS NULL AND goal_id IS NULL AND goal_version IS NULL"
    " AND profile_version IS NULL AND visibility_version IS NULL AND subject_id IS NULL A"
    "ND topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND"
    " ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AN"
    "D report_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AND "
    "blocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND pri"
    "vate_passed IS NULL AND connection_request_id IS NULL AND connection_request_version"
    " IS NULL AND connection_request_state IS NULL AND connection_request_recipient_id IS"
    " NULL AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND goal_shar"
    "e_context_version IS NULL AND conversation_read_id IS NULL AND read_conversation_id "
    "IS NULL AND message_operation_id IS NULL AND message_operation_state IS NULL AND req"
    "uest_view_ack_id IS NULL AND request_initiator_id IS NULL AND operator_audit_id IS N"
    "ULL AND operator_access_version IS NULL AND operator_action IS NULL AND study_outcom"
    "e_id IS NULL AND study_conversation_id IS NULL AND study_outcome_version IS NULL AND"
    " study_answer IS NULL AND peer_feedback_id IS NULL AND peer_feedback_version IS NULL"
    " AND feedback_again IS NULL AND study_prompt_id IS NULL AND study_prompt_conversatio"
    "n_id IS NULL AND help_version IS NULL AND photo_version IS NULL AND lifecycle_revisi"
    "on_id IS NULL AND lifecycle_account_id IS NULL AND lifecycle_version IS NULL AND lif"
    "ecycle_operation IS NULL)) AND report_review_id IS NULL AND report_review_report_id "
    "IS NULL AND report_review_version IS NULL AND report_review_action IS NULL AND photo"
    "_review_id IS NULL AND photo_review_version IS NULL AND photo_review_action IS NULL)"
    " OR (kind='report.reviewed' AND report_review_report_id IS NOT NULL AND report_revie"
    "w_id IS NOT NULL AND report_review_version IS NOT NULL AND report_review_version>0 A"
    "ND report_review_action IS NOT NULL AND report_review_action IN ('dismiss','escalate"
    "') AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visi"
    "bility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_l"
    "earning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NUL"
    "L AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_relatio"
    "nship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND private_pass_id I"
    "S NULL AND private_pass_version IS NULL AND private_passed IS NULL AND connection_re"
    "quest_id IS NULL AND connection_request_version IS NULL AND connection_request_state"
    " IS NULL AND connection_request_recipient_id IS NULL AND goal_share_id IS NULL AND g"
    "oal_share_conversation_id IS NULL AND goal_share_context_version IS NULL AND convers"
    "ation_read_id IS NULL AND read_conversation_id IS NULL AND message_operation_id IS N"
    "ULL AND message_operation_state IS NULL AND request_view_ack_id IS NULL AND request_"
    "initiator_id IS NULL AND operator_audit_id IS NULL AND operator_access_version IS NU"
    "LL AND operator_action IS NULL AND study_outcome_id IS NULL AND study_conversation_i"
    "d IS NULL AND study_outcome_version IS NULL AND study_answer IS NULL AND peer_feedba"
    "ck_id IS NULL AND peer_feedback_version IS NULL AND feedback_again IS NULL AND study"
    "_prompt_id IS NULL AND study_prompt_conversation_id IS NULL AND help_version IS NULL"
    " AND photo_version IS NULL AND lifecycle_revision_id IS NULL AND lifecycle_account_i"
    "d IS NULL AND lifecycle_version IS NULL AND lifecycle_operation IS NULL AND notifica"
    "tion_preference_version IS NULL AND support_case_id IS NULL AND support_case_version"
    " IS NULL AND photo_review_id IS NULL AND photo_review_version IS NULL AND photo_revi"
    "ew_action IS NULL) OR (kind='photo.reviewed' AND photo_review_id IS NOT NULL AND pho"
    "to_review_version IS NOT NULL AND photo_review_version>0 AND photo_review_action IS "
    "NOT NULL AND photo_review_action IN ('require_replacement','approve_replacement') AN"
    "D goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibilit"
    "y_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learni"
    "ng IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND"
    " ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_relationship"
    "_id IS NULL AND block_version IS NULL AND blocked IS NULL AND private_pass_id IS NUL"
    "L AND private_pass_version IS NULL AND private_passed IS NULL AND connection_request"
    "_id IS NULL AND connection_request_version IS NULL AND connection_request_state IS N"
    "ULL AND connection_request_recipient_id IS NULL AND goal_share_id IS NULL AND goal_s"
    "hare_conversation_id IS NULL AND goal_share_context_version IS NULL AND conversation"
    "_read_id IS NULL AND read_conversation_id IS NULL AND message_operation_id IS NULL A"
    "ND message_operation_state IS NULL AND request_view_ack_id IS NULL AND request_initi"
    "ator_id IS NULL AND operator_audit_id IS NULL AND operator_access_version IS NULL AN"
    "D operator_action IS NULL AND study_outcome_id IS NULL AND study_conversation_id IS "
    "NULL AND study_outcome_version IS NULL AND study_answer IS NULL AND peer_feedback_id"
    " IS NULL AND peer_feedback_version IS NULL AND feedback_again IS NULL AND study_prom"
    "pt_id IS NULL AND study_prompt_conversation_id IS NULL AND help_version IS NULL AND "
    "photo_version IS NULL AND lifecycle_revision_id IS NULL AND lifecycle_account_id IS "
    "NULL AND lifecycle_version IS NULL AND lifecycle_operation IS NULL AND notification_"
    "preference_version IS NULL AND support_case_id IS NULL AND support_case_version IS N"
    "ULL AND report_review_id IS NULL AND report_review_report_id IS NULL AND report_revi"
    "ew_version IS NULL AND report_review_action IS NULL)) AND triage_job_id IS NULL AND "
    "triage_report_id IS NULL AND triage_source_version IS NULL) OR (kind='triage.submitt"
    "ed' AND triage_job_id IS NOT NULL AND triage_report_id IS NOT NULL AND triage_source"
    "_version IS NOT NULL AND triage_source_version>0 AND goal_id IS NULL AND goal_versio"
    "n IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND subject_id "
    "IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS"
    " NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason I"
    "S NULL AND report_id IS NULL AND block_relationship_id IS NULL AND block_version IS "
    "NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NUL"
    "L AND private_passed IS NULL AND connection_request_id IS NULL AND connection_reques"
    "t_version IS NULL AND connection_request_state IS NULL AND connection_request_recipi"
    "ent_id IS NULL AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND "
    "goal_share_context_version IS NULL AND conversation_read_id IS NULL AND read_convers"
    "ation_id IS NULL AND message_operation_id IS NULL AND message_operation_state IS NUL"
    "L AND request_view_ack_id IS NULL AND request_initiator_id IS NULL AND operator_audi"
    "t_id IS NULL AND operator_access_version IS NULL AND operator_action IS NULL AND stu"
    "dy_outcome_id IS NULL AND study_conversation_id IS NULL AND study_outcome_version IS"
    " NULL AND study_answer IS NULL AND peer_feedback_id IS NULL AND peer_feedback_versio"
    "n IS NULL AND feedback_again IS NULL AND study_prompt_id IS NULL AND study_prompt_co"
    "nversation_id IS NULL AND help_version IS NULL AND photo_version IS NULL AND lifecyc"
    "le_revision_id IS NULL AND lifecycle_account_id IS NULL AND lifecycle_version IS NUL"
    "L AND lifecycle_operation IS NULL AND notification_preference_version IS NULL AND su"
    "pport_case_id IS NULL AND support_case_version IS NULL AND report_review_id IS NULL "
    "AND report_review_report_id IS NULL AND report_review_version IS NULL AND report_rev"
    "iew_action IS NULL AND photo_review_id IS NULL AND photo_review_version IS NULL AND "
    "photo_review_action IS NULL)"
)
RUNTIME_REPORT_GUARD_SHAPE = (
    "runtime_report_guard_version IS NULL OR (runtime_report_guard_version=1 AND runtime_"
    "worker_id IS NOT NULL AND runtime_state IN ('starting','ready','blocked'))"
)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_ai_jobs_triage_source",
        "ai_jobs",
        ["id", "actor_id", "kind", "source_id", "source_version"],
    )
    op.create_unique_constraint(
        "uq_profile_reports_triage_identity", "profile_reports", ["id", "kind", "reporter_id"]
    )
    op.create_unique_constraint(
        "uq_profile_reports_triage_profile_context", "profile_reports", ["id", "context_id"]
    )
    op.create_unique_constraint(
        "uq_profile_reports_triage_message_context", "profile_reports", ["id", "message_context_id"]
    )
    op.create_unique_constraint(
        "uq_profile_access_triage_evidence",
        "profile_access_contexts",
        ["id", "viewer_id", "target_id"],
    )
    op.create_unique_constraint(
        "uq_message_report_triage_evidence",
        "message_report_contexts",
        ["id", "viewer_id", "target_id"],
    )
    op.add_column(
        "ai_executor_slot", sa.Column("runtime_report_guard_version", sa.Integer(), nullable=True)
    )
    op.create_check_constraint(
        "runtime_report_guard", "ai_executor_slot", RUNTIME_REPORT_GUARD_SHAPE
    )
    _create_triage_sources()
    op.add_column("product_events", sa.Column("triage_job_id", sa.Uuid(), nullable=True))
    op.add_column("product_events", sa.Column("triage_report_id", sa.Uuid(), nullable=True))
    op.add_column("product_events", sa.Column("triage_source_version", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_product_events_triage_submission",
        "product_events",
        "report_triage_submissions",
        ["triage_job_id", "triage_report_id", "triage_source_version", "account_id"],
        ["job_id", "report_id", "source_version", "operator_id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", type_="check"
    )
    op.create_check_constraint("event_reference_shape", "product_events", EVENT_SHAPE)


def _create_triage_sources() -> None:
    op.create_table(
        "report_triage_evidence_snapshots",
        sa.Column(
            "report_id",
            sa.Uuid(),
            sa.ForeignKey("profile_reports.id", ondelete="RESTRICT"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("report_kind", sa.String(16), nullable=False),
        sa.Column("reporter_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("profile_context_id", sa.Uuid(), nullable=True),
        sa.Column("message_context_id", sa.Uuid(), nullable=True),
        sa.Column("previous_version", sa.Integer(), nullable=True),
        sa.Column("review_version", sa.Integer(), nullable=True),
        sa.Column("operator_id", sa.Uuid(), nullable=False),
        sa.Column("operator_access_version", sa.Integer(), nullable=False),
        sa.Column("operator_access_active", sa.Boolean(), nullable=False),
        sa.Column("actor_session_id", sa.Uuid(), nullable=False),
        sa.Column("evidence", sa.Text, nullable=False),
        sa.Column("evidence_digest", sa.LargeBinary(32), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "report_id",
            "version",
            "operator_id",
            "operator_access_version",
            "operator_access_active",
            "actor_session_id",
            name="uq_triage_snapshot_actor_source",
        ),
        sa.ForeignKeyConstraint(
            ["report_id", "previous_version"],
            [
                "report_triage_evidence_snapshots.report_id",
                "report_triage_evidence_snapshots.version",
            ],
            name="fk_triage_snapshot_previous",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["report_id", "review_version"],
            [
                "operator_report_review_revisions.report_id",
                "operator_report_review_revisions.version",
            ],
            name="fk_triage_snapshot_review",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["operator_id", "operator_access_version", "operator_access_active"],
            [
                "operator_access_revisions.account_id",
                "operator_access_revisions.version",
                "operator_access_revisions.active",
            ],
            name="fk_triage_snapshot_grant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_session_id", "operator_id"],
            ["sessions.id", "sessions.account_id"],
            name="fk_triage_snapshot_session",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["report_id", "report_kind", "reporter_id"],
            ["profile_reports.id", "profile_reports.kind", "profile_reports.reporter_id"],
            name="fk_triage_snapshot_report_source",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["report_id", "profile_context_id"],
            ["profile_reports.id", "profile_reports.context_id"],
            name="fk_triage_snapshot_report_profile",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["report_id", "message_context_id"],
            ["profile_reports.id", "profile_reports.message_context_id"],
            name="fk_triage_snapshot_report_message",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["profile_context_id", "reporter_id", "target_id"],
            [
                "profile_access_contexts.id",
                "profile_access_contexts.viewer_id",
                "profile_access_contexts.target_id",
            ],
            name="fk_triage_snapshot_profile_evidence",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["message_context_id", "reporter_id", "target_id"],
            [
                "message_report_contexts.id",
                "message_report_contexts.viewer_id",
                "message_report_contexts.target_id",
            ],
            name="fk_triage_snapshot_message_evidence",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "(report_kind='profile' AND profile_context_id IS NOT NULL AND message_co"
            "ntext_id IS NULL) OR (report_kind='message_image' AND profile_context_id"
            " IS NULL AND message_context_id IS NOT NULL)",
            name="actual_evidence_kind",
        ),
        sa.CheckConstraint(
            "version>0 AND ((version=1 AND previous_version IS NULL) OR (previous_ver"
            "sion IS NOT NULL AND previous_version>0 AND version=previous_version+1))",
            name="consecutive_versions",
        ),
        sa.CheckConstraint(
            "review_version IS NULL OR review_version>0", name="actual_review_version"
        ),
        sa.CheckConstraint(
            "operator_access_active=true AND operator_access_version>0",
            name="original_active_grant",
        ),
        sa.CheckConstraint(
            "length(evidence) BETWEEN 1 AND 4000 AND length(btrim(evidence))>0",
            name="bounded_actual_evidence",
        ),
        sa.CheckConstraint("octet_length(evidence_digest)=32", name="evidence_digest_length"),
    )

    op.create_table(
        "report_triage_submissions",
        sa.Column("job_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("operator_id", sa.Uuid(), nullable=False),
        sa.Column("operator_access_version", sa.Integer(), nullable=False),
        sa.Column("operator_access_active", sa.Boolean(), nullable=False),
        sa.Column("actor_session_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("event_kind", sa.String(32), nullable=False),
        sa.Column("http_request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(32), nullable=True),
        sa.Column("span_id", sa.String(16), nullable=True),
        sa.UniqueConstraint("event_id", name="uq_triage_submission_event"),
        sa.UniqueConstraint(
            "job_id",
            "report_id",
            "source_version",
            "operator_id",
            name="uq_triage_submission_canonical",
        ),
        sa.ForeignKeyConstraint(
            [
                "report_id",
                "source_version",
                "operator_id",
                "operator_access_version",
                "operator_access_active",
                "actor_session_id",
            ],
            [
                "report_triage_evidence_snapshots.report_id",
                "report_triage_evidence_snapshots.version",
                "report_triage_evidence_snapshots.operator_id",
                "report_triage_evidence_snapshots.operator_access_version",
                "report_triage_evidence_snapshots.operator_access_active",
                "report_triage_evidence_snapshots.actor_session_id",
            ],
            name="fk_triage_submission_source",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["job_id", "operator_id", "kind", "report_id", "source_version"],
            [
                "ai_jobs.id",
                "ai_jobs.actor_id",
                "ai_jobs.kind",
                "ai_jobs.source_id",
                "ai_jobs.source_version",
            ],
            name="fk_triage_submission_job",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "operator_id", "event_kind", "submitted_at"],
            [
                "product_events.id",
                "product_events.account_id",
                "product_events.kind",
                "product_events.occurred_at",
            ],
            name="fk_triage_submission_event",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.CheckConstraint(
            "kind='triage_report' AND event_kind='triage.submitted'",
            name="actual_internal_submission",
        ),
        sa.CheckConstraint(
            "http_request_id IS NOT NULL OR (action_id IS NULL AND trace_id IS NULL A"
            "ND span_id IS NULL)",
            name="origin_request",
        ),
        sa.CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR (trace_id IS NOT NULL AND span"
            "_id IS NOT NULL AND trace_id ~ '^[0-9a-f]{32}$' AND trace_id != repeat('"
            "0',32) AND span_id ~ '^[0-9a-f]{16}$' AND span_id != repeat('0',16))",
            name="origin_trace_pair",
        ),
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM report_triage_evidence_snapshots "
            "UNION ALL SELECT 1 FROM report_triage_submissions "
            "UNION ALL SELECT 1 FROM ai_executor_slot WHERE runtime_report_guard_vers"
            "ion IS NOT NULL)"
        )
    ):
        raise RuntimeError("Refusing to discard report triage proof or an active guard capability")
    op.drop_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", type_="check"
    )
    op.drop_constraint("fk_product_events_triage_submission", "product_events", type_="foreignkey")
    op.drop_column("product_events", "triage_source_version")
    op.drop_column("product_events", "triage_report_id")
    op.drop_column("product_events", "triage_job_id")
    op.create_check_constraint("event_reference_shape", "product_events", BEFORE_EVENT_SHAPE)
    op.drop_table("report_triage_submissions")
    op.drop_table("report_triage_evidence_snapshots")
    op.drop_constraint(
        op.f("ck_ai_executor_slot_runtime_report_guard"), "ai_executor_slot", type_="check"
    )
    op.drop_column("ai_executor_slot", "runtime_report_guard_version")
    op.drop_constraint(
        "uq_message_report_triage_evidence", "message_report_contexts", type_="unique"
    )
    op.drop_constraint(
        "uq_profile_access_triage_evidence", "profile_access_contexts", type_="unique"
    )
    op.drop_constraint(
        "uq_profile_reports_triage_message_context", "profile_reports", type_="unique"
    )
    op.drop_constraint(
        "uq_profile_reports_triage_profile_context", "profile_reports", type_="unique"
    )
    op.drop_constraint("uq_profile_reports_triage_identity", "profile_reports", type_="unique")
    op.drop_constraint("uq_ai_jobs_triage_source", "ai_jobs", type_="unique")
