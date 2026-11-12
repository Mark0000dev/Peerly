"""Retained human report/photo decisions; no automatic sanctions or historical grants."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0059_human_reviews"
down_revision: str | Sequence[str] | None = "0058_manual_membership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE_EVENT_SHAPE = (
    "((((((((((((((((((((((((((kind != 'ai_job.completed' AND ai_job_id IS NULL AND ai_ki"
    "nd IS NULL AND ai_state IS NULL AND ai_reason IS NULL) AND ((kind IN ('goal.saved', "
    "'goal.completed') AND goal_id IS NOT NULL AND goal_version IS NOT NULL AND topic_pre"
    "sent IS NOT NULL AND shared_learning IS NOT NULL AND profile_version IS NULL AND vis"
    "ibility_version IS NULL AND onboarding_task IS NULL) OR (kind = 'profile.ready' AND "
    "profile_version IS NOT NULL AND onboarding_task IS NOT NULL AND onboarding_task IN ("
    "'find_help', 'offer_help') AND goal_id IS NULL AND goal_version IS NULL AND visibili"
    "ty_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learn"
    "ing IS NULL) OR (kind IN ('profile.hidden', 'profile.restored', 'discovery.exposure_"
    "confirmed') AND visibility_version IS NOT NULL AND goal_id IS NULL AND goal_version "
    "IS NULL AND profile_version IS NULL AND onboarding_task IS NULL AND subject_id IS NU"
    "LL AND topic_present IS NULL AND shared_learning IS NULL) OR (kind = 'auth.email_con"
    "firmed' AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND"
    " visibility_version IS NULL AND onboarding_task IS NULL AND subject_id IS NULL AND t"
    "opic_present IS NULL AND shared_learning IS NULL))) OR (kind = 'ai_job.completed' AN"
    "D ai_job_id IS NOT NULL AND ai_kind IS NOT NULL AND ai_kind IN ('clarify_goal','sugg"
    "est_subject','assess_photo','triage_report') AND ai_state IS NOT NULL AND ai_state I"
    "N ('succeeded','failed','cancelled','expired') AND (ai_reason IS NULL OR (ai_state I"
    "N ('failed','expired') AND ai_reason IN ('transient','invalid_output','invalid_input"
    "','timeout','auth_unavailable','rate_limited','account_unavailable','stale_source','"
    "executor_lost'))) AND goal_id IS NULL AND goal_version IS NULL AND profile_version I"
    "S NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NU"
    "LL AND shared_learning IS NULL AND onboarding_task IS NULL)) AND report_id IS NULL A"
    "ND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL) OR ("
    "(goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibility"
    "_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learnin"
    "g IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND "
    "ai_state IS NULL AND ai_reason IS NULL) AND ((kind = 'report.created' AND report_id "
    "IS NOT NULL AND block_relationship_id IS NULL AND block_version IS NULL AND blocked "
    "IS NULL) OR (kind = 'block.changed' AND report_id IS NULL AND block_relationship_id "
    "IS NOT NULL AND block_version IS NOT NULL AND blocked IS NOT NULL)))) AND private_pa"
    "ss_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL) OR (kind "
    "= 'discovery.pass_changed' AND private_pass_id IS NOT NULL AND private_pass_version "
    "IS NOT NULL AND private_passed IS NOT NULL AND goal_id IS NULL AND goal_version IS N"
    "ULL AND profile_version IS NULL AND visibility_version IS NULL AND subject_id IS NUL"
    "L AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL "
    "AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL"
    " AND report_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL A"
    "ND blocked IS NULL)) AND connection_request_id IS NULL AND connection_request_versio"
    "n IS NULL AND connection_request_state IS NULL AND connection_request_recipient_id I"
    "S NULL AND request_initiator_id IS NULL) OR (kind = 'request.changed' AND connection"
    "_request_id IS NOT NULL AND connection_request_version IS NOT NULL AND connection_re"
    "quest_state IS NOT NULL AND connection_request_recipient_id IS NOT NULL AND (request"
    "_initiator_id IS NULL OR request_initiator_id IN (account_id, connection_request_rec"
    "ipient_id)) AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL"
    " AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND"
    " shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_ki"
    "nd IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND bloc"
    "k_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND private_"
    "pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL)) AND re"
    "quest_view_ack_id IS NULL) OR (kind = 'request.view_acknowledged' AND request_view_a"
    "ck_id IS NOT NULL AND goal_id IS NULL AND goal_version IS NULL AND profile_version I"
    "S NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NU"
    "LL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND"
    " ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AN"
    "D block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND pr"
    "ivate_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL AN"
    "D connection_request_id IS NULL AND connection_request_version IS NULL AND connectio"
    "n_request_state IS NULL AND connection_request_recipient_id IS NULL AND request_init"
    "iator_id IS NULL)) AND message_operation_id IS NULL AND message_operation_state IS N"
    "ULL) OR (message_operation_id IS NOT NULL AND message_operation_state IS NOT NULL AN"
    "D ((kind='message.confirmed' AND message_operation_state='confirmed') OR (kind='mess"
    "age.cancelled' AND message_operation_state='cancelled')) AND goal_id IS NULL AND goa"
    "l_version IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND sub"
    "ject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboarding"
    "_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_"
    "reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND block_ver"
    "sion IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_versio"
    "n IS NULL AND private_passed IS NULL AND connection_request_id IS NULL AND connectio"
    "n_request_version IS NULL AND connection_request_state IS NULL AND connection_reques"
    "t_recipient_id IS NULL AND request_view_ack_id IS NULL AND request_initiator_id IS N"
    "ULL)) AND conversation_read_id IS NULL AND read_conversation_id IS NULL) OR (kind='c"
    "onversation.read_acknowledged' AND conversation_read_id IS NOT NULL AND read_convers"
    "ation_id IS NOT NULL AND goal_id IS NULL AND goal_version IS NULL AND profile_versio"
    "n IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS"
    " NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL "
    "AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL"
    " AND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND"
    " private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL"
    " AND connection_request_id IS NULL AND connection_request_version IS NULL AND connec"
    "tion_request_state IS NULL AND connection_request_recipient_id IS NULL AND message_o"
    "peration_id IS NULL AND message_operation_state IS NULL AND request_view_ack_id IS N"
    "ULL AND request_initiator_id IS NULL)) AND goal_share_id IS NULL AND goal_share_cont"
    "ext_version IS NULL AND goal_share_conversation_id IS NULL) OR (kind='conversation.g"
    "oal_shared' AND goal_share_id IS NOT NULL AND goal_share_context_version IS NOT NULL"
    " AND goal_share_conversation_id IS NOT NULL AND goal_id IS NULL AND goal_version IS "
    "NULL AND profile_version IS NULL AND visibility_version IS NULL AND subject_id IS NU"
    "LL AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL"
    " AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NUL"
    "L AND report_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL "
    "AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND"
    " private_passed IS NULL AND connection_request_id IS NULL AND connection_request_ver"
    "sion IS NULL AND connection_request_state IS NULL AND connection_request_recipient_i"
    "d IS NULL AND conversation_read_id IS NULL AND read_conversation_id IS NULL AND mess"
    "age_operation_id IS NULL AND message_operation_state IS NULL AND request_view_ack_id"
    " IS NULL AND request_initiator_id IS NULL)) AND operator_audit_id IS NULL AND operat"
    "or_access_version IS NULL AND operator_action IS NULL) OR (kind='operator.inspected'"
    " AND operator_audit_id IS NOT NULL AND operator_access_version IS NOT NULL AND opera"
    "tor_action IS NOT NULL AND operator_action IN ('search_accounts','read_account','rea"
    "d_conversation_messages','search_events','read_event','read_audit','search_reports',"
    "'read_report','read_media','read_support_case','search_support_cases','search_delive"
    "ry_sources','read_delivery_source','read_chat_media','search_audits') AND goal_id IS"
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
    "ULL)) AND study_outcome_id IS NULL AND study_conversation_id IS NULL AND study_outco"
    "me_version IS NULL AND study_answer IS NULL AND peer_feedback_id IS NULL AND peer_fe"
    "edback_version IS NULL AND feedback_again IS NULL AND study_prompt_id IS NULL AND st"
    "udy_prompt_conversation_id IS NULL) OR (kind='study.reported' AND study_outcome_id I"
    "S NOT NULL AND study_conversation_id IS NOT NULL AND study_outcome_version IS NOT NU"
    "LL AND study_answer IS NOT NULL AND peer_feedback_id IS NULL AND peer_feedback_versi"
    "on IS NULL AND feedback_again IS NULL AND study_prompt_id IS NULL AND study_prompt_c"
    "onversation_id IS NULL AND study_answer IN ('yes','not_yet','did_not_work_out') AND "
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
    "operator_action IS NULL) OR (kind='feedback.saved' AND study_outcome_id IS NULL AND "
    "study_conversation_id IS NULL AND study_outcome_version IS NULL AND study_answer IS "
    "NULL AND peer_feedback_id IS NOT NULL AND peer_feedback_version IS NOT NULL AND feed"
    "back_again IS NOT NULL AND study_prompt_id IS NULL AND study_prompt_conversation_id "
    "IS NULL AND feedback_again IN ('yes','maybe','no') AND goal_id IS NULL AND goal_vers"
    "ion IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND subject_i"
    "d IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_task "
    "IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason"
    " IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND block_version I"
    "S NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS N"
    "ULL AND private_passed IS NULL AND connection_request_id IS NULL AND connection_requ"
    "est_version IS NULL AND connection_request_state IS NULL AND connection_request_reci"
    "pient_id IS NULL AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL AN"
    "D goal_share_context_version IS NULL AND conversation_read_id IS NULL AND read_conve"
    "rsation_id IS NULL AND message_operation_id IS NULL AND message_operation_state IS N"
    "ULL AND request_view_ack_id IS NULL AND request_initiator_id IS NULL AND operator_au"
    "dit_id IS NULL AND operator_access_version IS NULL AND operator_action IS NULL) OR ("
    "kind='study.prompt_offered' AND study_outcome_id IS NULL AND study_conversation_id I"
    "S NULL AND study_outcome_version IS NULL AND study_answer IS NULL AND peer_feedback_"
    "id IS NULL AND peer_feedback_version IS NULL AND feedback_again IS NULL AND study_pr"
    "ompt_id IS NOT NULL AND study_prompt_conversation_id IS NOT NULL AND TRUE AND goal_i"
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
    "IS NULL AND operator_audit_id IS NULL AND operator_access_version IS NULL AND operat"
    "or_action IS NULL)) AND help_version IS NULL AND photo_version IS NULL) OR (kind='pr"
    "ofile.saved' AND profile_version IS NOT NULL AND goal_id IS NULL AND goal_version IS"
    " NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NUL"
    "L AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND "
    "ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND"
    " block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND pri"
    "vate_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL AND"
    " connection_request_id IS NULL AND connection_request_version IS NULL AND connection"
    "_request_state IS NULL AND connection_request_recipient_id IS NULL AND goal_share_id"
    " IS NULL AND goal_share_conversation_id IS NULL AND goal_share_context_version IS NU"
    "LL AND conversation_read_id IS NULL AND read_conversation_id IS NULL AND message_ope"
    "ration_id IS NULL AND message_operation_state IS NULL AND request_view_ack_id IS NUL"
    "L AND request_initiator_id IS NULL AND operator_audit_id IS NULL AND operator_access"
    "_version IS NULL AND operator_action IS NULL AND study_outcome_id IS NULL AND study_"
    "conversation_id IS NULL AND study_outcome_version IS NULL AND study_answer IS NULL A"
    "ND peer_feedback_id IS NULL AND peer_feedback_version IS NULL AND feedback_again IS "
    "NULL AND study_prompt_id IS NULL AND study_prompt_conversation_id IS NULL AND help_v"
    "ersion IS NULL AND photo_version IS NULL) OR (kind='help.saved' AND help_version IS "
    "NOT NULL AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AN"
    "D visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND sh"
    "ared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind "
    "IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_r"
    "elationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND private_pas"
    "s_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL AND connect"
    "ion_request_id IS NULL AND connection_request_version IS NULL AND connection_request"
    "_state IS NULL AND connection_request_recipient_id IS NULL AND goal_share_id IS NULL"
    " AND goal_share_conversation_id IS NULL AND goal_share_context_version IS NULL AND c"
    "onversation_read_id IS NULL AND read_conversation_id IS NULL AND message_operation_i"
    "d IS NULL AND message_operation_state IS NULL AND request_view_ack_id IS NULL AND re"
    "quest_initiator_id IS NULL AND operator_audit_id IS NULL AND operator_access_version"
    " IS NULL AND operator_action IS NULL AND study_outcome_id IS NULL AND study_conversa"
    "tion_id IS NULL AND study_outcome_version IS NULL AND study_answer IS NULL AND peer_"
    "feedback_id IS NULL AND peer_feedback_version IS NULL AND feedback_again IS NULL AND"
    " study_prompt_id IS NULL AND study_prompt_conversation_id IS NULL AND photo_version "
    "IS NULL) OR (kind='photo.published' AND photo_version IS NOT NULL AND goal_id IS NUL"
    "L AND goal_version IS NULL AND profile_version IS NULL AND visibility_version IS NUL"
    "L AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND o"
    "nboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NUL"
    "L AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND "
    "block_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pa"
    "ss_version IS NULL AND private_passed IS NULL AND connection_request_id IS NULL AND "
    "connection_request_version IS NULL AND connection_request_state IS NULL AND connecti"
    "on_request_recipient_id IS NULL AND goal_share_id IS NULL AND goal_share_conversatio"
    "n_id IS NULL AND goal_share_context_version IS NULL AND conversation_read_id IS NULL"
    " AND read_conversation_id IS NULL AND message_operation_id IS NULL AND message_opera"
    "tion_state IS NULL AND request_view_ack_id IS NULL AND request_initiator_id IS NULL "
    "AND operator_audit_id IS NULL AND operator_access_version IS NULL AND operator_actio"
    "n IS NULL AND study_outcome_id IS NULL AND study_conversation_id IS NULL AND study_o"
    "utcome_version IS NULL AND study_answer IS NULL AND peer_feedback_id IS NULL AND pee"
    "r_feedback_version IS NULL AND feedback_again IS NULL AND study_prompt_id IS NULL AN"
    "D study_prompt_conversation_id IS NULL AND help_version IS NULL)) AND lifecycle_revi"
    "sion_id IS NULL AND lifecycle_account_id IS NULL AND lifecycle_version IS NULL AND l"
    "ifecycle_operation IS NULL) OR (kind='account.lifecycle_changed' AND lifecycle_revis"
    "ion_id IS NOT NULL AND lifecycle_account_id IS NOT NULL AND lifecycle_version IS NOT"
    " NULL AND lifecycle_version>0 AND lifecycle_operation IS NOT NULL AND lifecycle_oper"
    "ation IN ('ban','unban','delete') AND goal_id IS NULL AND goal_version IS NULL AND p"
    "rofile_version IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND top"
    "ic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_jo"
    "b_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND repo"
    "rt_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AND blocke"
    "d IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND private_p"
    "assed IS NULL AND connection_request_id IS NULL AND connection_request_version IS NU"
    "LL AND connection_request_state IS NULL AND connection_request_recipient_id IS NULL "
    "AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND goal_share_cont"
    "ext_version IS NULL AND conversation_read_id IS NULL AND read_conversation_id IS NUL"
    "L AND message_operation_id IS NULL AND message_operation_state IS NULL AND request_v"
    "iew_ack_id IS NULL AND request_initiator_id IS NULL AND operator_audit_id IS NULL AN"
    "D operator_access_version IS NULL AND operator_action IS NULL AND study_outcome_id I"
    "S NULL AND study_conversation_id IS NULL AND study_outcome_version IS NULL AND study"
    "_answer IS NULL AND peer_feedback_id IS NULL AND peer_feedback_version IS NULL AND f"
    "eedback_again IS NULL AND study_prompt_id IS NULL AND study_prompt_conversation_id I"
    "S NULL AND help_version IS NULL AND photo_version IS NULL)) AND notification_prefere"
    "nce_version IS NULL AND support_case_id IS NULL AND support_case_version IS NULL) OR"
    " (kind='notification_preference.changed' AND notification_preference_version IS NOT "
    "NULL AND notification_preference_version>0 AND support_case_id IS NULL AND support_c"
    "ase_version IS NULL AND goal_id IS NULL AND goal_version IS NULL AND profile_version"
    " IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS "
    "NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL A"
    "ND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL "
    "AND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND "
    "private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL "
    "AND connection_request_id IS NULL AND connection_request_version IS NULL AND connect"
    "ion_request_state IS NULL AND connection_request_recipient_id IS NULL AND goal_share"
    "_id IS NULL AND goal_share_conversation_id IS NULL AND goal_share_context_version IS"
    " NULL AND conversation_read_id IS NULL AND read_conversation_id IS NULL AND message_"
    "operation_id IS NULL AND message_operation_state IS NULL AND request_view_ack_id IS "
    "NULL AND request_initiator_id IS NULL AND operator_audit_id IS NULL AND operator_acc"
    "ess_version IS NULL AND operator_action IS NULL AND study_outcome_id IS NULL AND stu"
    "dy_conversation_id IS NULL AND study_outcome_version IS NULL AND study_answer IS NUL"
    "L AND peer_feedback_id IS NULL AND peer_feedback_version IS NULL AND feedback_again "
    "IS NULL AND study_prompt_id IS NULL AND study_prompt_conversation_id IS NULL AND hel"
    "p_version IS NULL AND photo_version IS NULL AND lifecycle_revision_id IS NULL AND li"
    "fecycle_account_id IS NULL AND lifecycle_version IS NULL AND lifecycle_operation IS "
    "NULL) OR (kind IN ('support.received','support.status_changed') AND support_case_id "
    "IS NOT NULL AND support_case_version IS NOT NULL AND support_case_version>0 AND noti"
    "fication_preference_version IS NULL AND goal_id IS NULL AND goal_version IS NULL AND"
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
    " IS NULL AND help_version IS NULL AND photo_version IS NULL AND lifecycle_revision_i"
    "d IS NULL AND lifecycle_account_id IS NULL AND lifecycle_version IS NULL AND lifecyc"
    "le_operation IS NULL)"
)
EVENT_SHAPE = (
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


def upgrade() -> None:
    _create_review_sources()
    op.add_column("product_events", sa.Column("report_review_report_id", sa.Uuid(), nullable=True))
    op.add_column("product_events", sa.Column("report_review_id", sa.Uuid(), nullable=True))
    op.add_column("product_events", sa.Column("report_review_version", sa.Integer(), nullable=True))
    op.add_column("product_events", sa.Column("report_review_action", sa.String(32), nullable=True))
    op.add_column("product_events", sa.Column("photo_review_id", sa.Uuid(), nullable=True))
    op.add_column("product_events", sa.Column("photo_review_version", sa.Integer(), nullable=True))
    op.add_column("product_events", sa.Column("photo_review_action", sa.String(32), nullable=True))
    op.create_foreign_key(
        "fk_product_events_report_review_source",
        "product_events",
        "operator_report_review_revisions",
        [
            "report_review_id",
            "report_review_report_id",
            "report_review_version",
            "account_id",
            "report_review_action",
        ],
        ["id", "report_id", "version", "operator_id", "action"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_product_events_photo_review_source",
        "product_events",
        "operator_photo_review_revisions",
        ["photo_review_id", "photo_review_version", "account_id", "photo_review_action"],
        ["id", "version", "operator_id", "action"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", type_="check"
    )
    op.create_check_constraint("event_reference_shape", "product_events", EVENT_SHAPE)


def _create_review_sources() -> None:
    op.create_table(
        "operator_photo_review_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("previous_revision_id", sa.Uuid(), nullable=True),
        sa.Column("previous_version", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("photo_version", sa.Integer(), nullable=False),
        sa.Column("operator_id", sa.Uuid(), nullable=False),
        sa.Column("operator_access_version", sa.Integer(), nullable=False),
        sa.Column("operator_access_active", sa.Boolean(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("event_kind", sa.String(32), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("http_request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(32), nullable=True),
        sa.Column("span_id", sa.String(16), nullable=True),
        sa.UniqueConstraint("account_id", "version", name="uq_photo_review_version"),
        sa.UniqueConstraint("id", "account_id", "version", name="uq_photo_review_lineage"),
        sa.UniqueConstraint("id", "operator_id", name="uq_photo_review_actor_source"),
        sa.UniqueConstraint(
            "id", "version", "operator_id", "action", name="uq_photo_review_canonical_source"
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "photo_version"],
            ["photo_revisions.account_id", "photo_revisions.version"],
            ondelete="RESTRICT",
            name="fk_photo_review_publication",
        ),
        sa.ForeignKeyConstraint(
            ["previous_revision_id", "account_id", "previous_version"],
            [
                "operator_photo_review_revisions.id",
                "operator_photo_review_revisions.account_id",
                "operator_photo_review_revisions.version",
            ],
            ondelete="RESTRICT",
            name="fk_photo_review_previous",
        ),
        sa.ForeignKeyConstraint(
            ["operator_id", "operator_access_version", "operator_access_active"],
            [
                "operator_access_revisions.account_id",
                "operator_access_revisions.version",
                "operator_access_revisions.active",
            ],
            ondelete="RESTRICT",
            name="fk_photo_review_grant",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "operator_id"],
            ["sessions.id", "sessions.account_id"],
            ondelete="RESTRICT",
            name="fk_photo_review_session",
        ),
        sa.ForeignKeyConstraint(
            ["id", "operator_id", "event_kind", "decided_at"],
            [
                "product_events.id",
                "product_events.account_id",
                "product_events.kind",
                "product_events.occurred_at",
            ],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
            name="fk_photo_review_event",
        ),
        sa.CheckConstraint("version>0 AND photo_version>0", name="positive_versions"),
        sa.CheckConstraint(
            "(version=1 AND previous_version IS NULL AND previous_revision_id IS NULL"
            " AND action='require_replacement') OR (version>1 AND previous_version IS"
            " NOT NULL AND previous_version=version-1 AND previous_revision_id IS NOT"
            " NULL)",
            name="ordered_lineage",
        ),
        sa.CheckConstraint(
            "action IN ('require_replacement','approve_replacement')", name="human_action"
        ),
        sa.CheckConstraint(
            "operator_access_active=true AND operator_access_version>0", name="actual_active_grant"
        ),
        sa.CheckConstraint("event_kind='photo.reviewed'", name="actual_photo_review_event"),
        sa.CheckConstraint(
            "char_length(reason) BETWEEN 1 AND 1000 AND btrim(reason)<>''", name="bounded_reason"
        ),
        sa.CheckConstraint(
            "http_request_id IS NOT NULL OR (action_id IS NULL AND trace_id IS NULL A"
            "ND span_id IS NULL)",
            name="origin_requires_request",
        ),
        sa.CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR (trace_id IS NOT NULL AND span"
            "_id IS NOT NULL AND trace_id ~ '^[0-9a-f]{32}$' AND trace_id<>'000000000"
            "00000000000000000000000' AND span_id ~ '^[0-9a-f]{16}$' AND span_id<>'00"
            "00000000000000')",
            name="paired_trace",
        ),
    )

    op.create_table(
        "operator_photo_review_intents",
        sa.Column("operator_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("key", sa.String(128), primary_key=True, nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["revision_id", "operator_id"],
            ["operator_photo_review_revisions.id", "operator_photo_review_revisions.operator_id"],
            ondelete="RESTRICT",
            name="fk_photo_review_intent_source",
        ),
        sa.UniqueConstraint("revision_id", name="uq_photo_review_intent_source"),
        sa.CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="valid_key"),
        sa.CheckConstraint("octet_length(fingerprint)=32", name="fingerprint_length"),
    )

    op.create_table(
        "operator_report_review_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "report_id",
            sa.Uuid(),
            sa.ForeignKey("profile_reports.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("previous_version", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("operator_id", sa.Uuid(), nullable=False),
        sa.Column("operator_access_version", sa.Integer(), nullable=False),
        sa.Column("operator_access_active", sa.Boolean(), nullable=False),
        sa.Column("actor_session_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("event_kind", sa.String(32), nullable=False),
        sa.Column("http_request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(32), nullable=True),
        sa.Column("span_id", sa.String(16), nullable=True),
        sa.UniqueConstraint("report_id", "version", name="uq_report_review_version"),
        sa.UniqueConstraint("id", "operator_id", name="uq_report_review_actor_source"),
        sa.UniqueConstraint(
            "id",
            "report_id",
            "version",
            "operator_id",
            "action",
            name="uq_report_review_canonical_source",
        ),
        sa.UniqueConstraint("event_id", name="uq_report_review_event"),
        sa.ForeignKeyConstraint(
            ["report_id", "previous_version"],
            [
                "operator_report_review_revisions.report_id",
                "operator_report_review_revisions.version",
            ],
            name="fk_report_review_previous",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["operator_id", "operator_access_version", "operator_access_active"],
            [
                "operator_access_revisions.account_id",
                "operator_access_revisions.version",
                "operator_access_revisions.active",
            ],
            name="fk_report_review_grant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_session_id", "operator_id"],
            ["sessions.id", "sessions.account_id"],
            name="fk_report_review_session",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "operator_id", "event_kind", "reviewed_at"],
            [
                "product_events.id",
                "product_events.account_id",
                "product_events.kind",
                "product_events.occurred_at",
            ],
            name="fk_report_review_event",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.CheckConstraint(
            "version>0 AND ((version=1 AND previous_version IS NULL) OR (previous_ver"
            "sion IS NOT NULL AND previous_version>0 AND version=previous_version+1))",
            name="consecutive_versions",
        ),
        sa.CheckConstraint("action IN ('dismiss','escalate')", name="human_action"),
        sa.CheckConstraint(
            "length(reason) BETWEEN 1 AND 1000 AND length(btrim(reason))>0",
            name="documented_reason",
        ),
        sa.CheckConstraint(
            "operator_access_active=true AND operator_access_version>0",
            name="active_original_grant",
        ),
        sa.CheckConstraint("event_kind='report.reviewed'", name="actual_review_event"),
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

    op.create_table(
        "operator_report_review_intents",
        sa.Column("operator_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("key", sa.String(128), primary_key=True, nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["review_id", "operator_id"],
            ["operator_report_review_revisions.id", "operator_report_review_revisions.operator_id"],
            name="fk_report_review_intent_source",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("review_id", name="uq_report_review_intent_source"),
        sa.CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="valid_key"),
        sa.CheckConstraint("octet_length(fingerprint)=32", name="fingerprint_length"),
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM operator_report_review_revisions "
            "UNION ALL SELECT 1 FROM operator_photo_review_revisions "
            "UNION ALL SELECT 1 FROM operator_report_review_intents "
            "UNION ALL SELECT 1 FROM operator_photo_review_intents)"
        )
    ):
        raise RuntimeError("Refusing to remove retained human review evidence")
    op.drop_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", type_="check"
    )
    op.drop_constraint(
        "fk_product_events_report_review_source", "product_events", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_product_events_photo_review_source", "product_events", type_="foreignkey"
    )
    op.drop_column("product_events", "photo_review_action")
    op.drop_column("product_events", "photo_review_version")
    op.drop_column("product_events", "photo_review_id")
    op.drop_column("product_events", "report_review_action")
    op.drop_column("product_events", "report_review_version")
    op.drop_column("product_events", "report_review_id")
    op.drop_column("product_events", "report_review_report_id")

    op.create_check_constraint("event_reference_shape", "product_events", BEFORE_EVENT_SHAPE)
    op.drop_table("operator_report_review_intents")
    op.drop_table("operator_report_review_revisions")
    op.drop_table("operator_photo_review_intents")
    op.drop_table("operator_photo_review_revisions")
