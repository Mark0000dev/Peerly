"""Retained student support and preferences; no fabricated anonymous accounts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0052_student_support"
down_revision: str | Sequence[str] | None = "0051_ai_runtime_health"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE_EVENT_SHAPE = (
    "((((((((((((((((((((((((kind != 'ai_job.completed' AND ai_job_id IS NULL AND ai_ki"
    "nd IS NULL AND ai_state IS NULL AND ai_reason IS NULL) AND ((kind IN ('goal.saved'"
    ", 'goal.completed') AND goal_id IS NOT NULL AND goal_version IS NOT NULL AND topic"
    "_present IS NOT NULL AND shared_learning IS NOT NULL AND profile_version IS NULL A"
    "ND visibility_version IS NULL AND onboarding_task IS NULL) OR (kind = 'profile.rea"
    "dy' AND profile_version IS NOT NULL AND onboarding_task IS NOT NULL AND onboarding"
    "_task IN ('find_help', 'offer_help') AND goal_id IS NULL AND goal_version IS NULL "
    "AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AN"
    "D shared_learning IS NULL) OR (kind IN ('profile.hidden', 'profile.restored', 'dis"
    "covery.exposure_confirmed') AND visibility_version IS NOT NULL AND goal_id IS NULL"
    " AND goal_version IS NULL AND profile_version IS NULL AND onboarding_task IS NULL "
    "AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL) OR ("
    "kind = 'auth.email_confirmed' AND goal_id IS NULL AND goal_version IS NULL AND pro"
    "file_version IS NULL AND visibility_version IS NULL AND onboarding_task IS NULL AN"
    "D subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL))) OR ("
    "kind = 'ai_job.completed' AND ai_job_id IS NOT NULL AND ai_kind IS NOT NULL AND ai"
    "_kind IN ('clarify_goal','suggest_subject','assess_photo','triage_report') AND ai_"
    "state IS NOT NULL AND ai_state IN ('succeeded','failed','cancelled','expired') AND"
    " (ai_reason IS NULL OR (ai_state IN ('failed','expired') AND ai_reason IN ('transi"
    "ent','invalid_output','invalid_input','timeout','auth_unavailable','rate_limited',"
    "'account_unavailable','stale_source','executor_lost'))) AND goal_id IS NULL AND go"
    "al_version IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND "
    "subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboa"
    "rding_task IS NULL)) AND report_id IS NULL AND block_relationship_id IS NULL AND b"
    "lock_version IS NULL AND blocked IS NULL) OR ((goal_id IS NULL AND goal_version IS"
    " NULL AND profile_version IS NULL AND visibility_version IS NULL AND subject_id IS"
    " NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS"
    " NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason"
    " IS NULL) AND ((kind = 'report.created' AND report_id IS NOT NULL AND block_relati"
    "onship_id IS NULL AND block_version IS NULL AND blocked IS NULL) OR (kind = 'block"
    ".changed' AND report_id IS NULL AND block_relationship_id IS NOT NULL AND block_ve"
    "rsion IS NOT NULL AND blocked IS NOT NULL)))) AND private_pass_id IS NULL AND priv"
    "ate_pass_version IS NULL AND private_passed IS NULL) OR (kind = 'discovery.pass_ch"
    "anged' AND private_pass_id IS NOT NULL AND private_pass_version IS NOT NULL AND pr"
    "ivate_passed IS NOT NULL AND goal_id IS NULL AND goal_version IS NULL AND profile_"
    "version IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_pr"
    "esent IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_i"
    "d IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND repor"
    "t_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AND block"
    "ed IS NULL)) AND connection_request_id IS NULL AND connection_request_version IS N"
    "ULL AND connection_request_state IS NULL AND connection_request_recipient_id IS NU"
    "LL AND request_initiator_id IS NULL) OR (kind = 'request.changed' AND connection_r"
    "equest_id IS NOT NULL AND connection_request_version IS NOT NULL AND connection_re"
    "quest_state IS NOT NULL AND connection_request_recipient_id IS NOT NULL AND (reque"
    "st_initiator_id IS NULL OR request_initiator_id IN (account_id, connection_request"
    "_recipient_id)) AND goal_id IS NULL AND goal_version IS NULL AND profile_version I"
    "S NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS "
    "NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL"
    " AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS N"
    "ULL AND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NUL"
    "L AND private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed "
    "IS NULL)) AND request_view_ack_id IS NULL) OR (kind = 'request.view_acknowledged' "
    "AND request_view_ack_id IS NOT NULL AND goal_id IS NULL AND goal_version IS NULL A"
    "ND profile_version IS NULL AND visibility_version IS NULL AND subject_id IS NULL A"
    "ND topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL A"
    "ND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NUL"
    "L AND report_id IS NULL AND block_relationship_id IS NULL AND block_version IS NUL"
    "L AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL"
    " AND private_passed IS NULL AND connection_request_id IS NULL AND connection_reque"
    "st_version IS NULL AND connection_request_state IS NULL AND connection_request_rec"
    "ipient_id IS NULL AND request_initiator_id IS NULL)) AND message_operation_id IS N"
    "ULL AND message_operation_state IS NULL) OR (message_operation_id IS NOT NULL AND "
    "message_operation_state IS NOT NULL AND ((kind='message.confirmed' AND message_ope"
    "ration_state='confirmed') OR (kind='message.cancelled' AND message_operation_state"
    "='cancelled')) AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS"
    " NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS N"
    "ULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL "
    "AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NU"
    "LL AND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL"
    " AND private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed I"
    "S NULL AND connection_request_id IS NULL AND connection_request_version IS NULL AN"
    "D connection_request_state IS NULL AND connection_request_recipient_id IS NULL AND"
    " request_view_ack_id IS NULL AND request_initiator_id IS NULL)) AND conversation_r"
    "ead_id IS NULL AND read_conversation_id IS NULL) OR (kind='conversation.read_ackno"
    "wledged' AND conversation_read_id IS NOT NULL AND read_conversation_id IS NOT NULL"
    " AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visi"
    "bility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared"
    "_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS"
    " NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_r"
    "elationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND private_p"
    "ass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL AND con"
    "nection_request_id IS NULL AND connection_request_version IS NULL AND connection_r"
    "equest_state IS NULL AND connection_request_recipient_id IS NULL AND message_opera"
    "tion_id IS NULL AND message_operation_state IS NULL AND request_view_ack_id IS NUL"
    "L AND request_initiator_id IS NULL)) AND goal_share_id IS NULL AND goal_share_cont"
    "ext_version IS NULL AND goal_share_conversation_id IS NULL) OR (kind='conversation"
    ".goal_shared' AND goal_share_id IS NOT NULL AND goal_share_context_version IS NOT "
    "NULL AND goal_share_conversation_id IS NOT NULL AND goal_id IS NULL AND goal_versi"
    "on IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND subject_"
    "id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_ta"
    "sk IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_r"
    "eason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND block_ve"
    "rsion IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_ver"
    "sion IS NULL AND private_passed IS NULL AND connection_request_id IS NULL AND conn"
    "ection_request_version IS NULL AND connection_request_state IS NULL AND connection"
    "_request_recipient_id IS NULL AND conversation_read_id IS NULL AND read_conversati"
    "on_id IS NULL AND message_operation_id IS NULL AND message_operation_state IS NULL"
    " AND request_view_ack_id IS NULL AND request_initiator_id IS NULL)) AND operator_a"
    "udit_id IS NULL AND operator_access_version IS NULL AND operator_action IS NULL) O"
    "R (kind='operator.inspected' AND operator_audit_id IS NOT NULL AND operator_access"
    "_version IS NOT NULL AND operator_action IS NOT NULL AND operator_action IN ('sear"
    "ch_accounts','read_account','read_conversation_messages','search_events','read_eve"
    "nt','read_audit','search_reports','read_report','read_media') AND goal_id IS NULL "
    "AND goal_version IS NULL AND profile_version IS NULL AND visibility_version IS NUL"
    "L AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND"
    " onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS"
    " NULL AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NUL"
    "L AND block_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND pr"
    "ivate_pass_version IS NULL AND private_passed IS NULL AND connection_request_id IS"
    " NULL AND connection_request_version IS NULL AND connection_request_state IS NULL "
    "AND connection_request_recipient_id IS NULL AND goal_share_id IS NULL AND goal_sha"
    "re_conversation_id IS NULL AND goal_share_context_version IS NULL AND conversation"
    "_read_id IS NULL AND read_conversation_id IS NULL AND message_operation_id IS NULL"
    " AND message_operation_state IS NULL AND request_view_ack_id IS NULL AND request_i"
    "nitiator_id IS NULL)) AND study_outcome_id IS NULL AND study_conversation_id IS NU"
    "LL AND study_outcome_version IS NULL AND study_answer IS NULL AND peer_feedback_id"
    " IS NULL AND peer_feedback_version IS NULL AND feedback_again IS NULL AND study_pr"
    "ompt_id IS NULL AND study_prompt_conversation_id IS NULL) OR (kind='study.reported"
    "' AND study_outcome_id IS NOT NULL AND study_conversation_id IS NOT NULL AND study"
    "_outcome_version IS NOT NULL AND study_answer IS NOT NULL AND peer_feedback_id IS "
    "NULL AND peer_feedback_version IS NULL AND feedback_again IS NULL AND study_prompt"
    "_id IS NULL AND study_prompt_conversation_id IS NULL AND study_answer IN ('yes','n"
    "ot_yet','did_not_work_out') AND goal_id IS NULL AND goal_version IS NULL AND profi"
    "le_version IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic"
    "_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_jo"
    "b_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND re"
    "port_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AND bl"
    "ocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND pri"
    "vate_passed IS NULL AND connection_request_id IS NULL AND connection_request_versi"
    "on IS NULL AND connection_request_state IS NULL AND connection_request_recipient_i"
    "d IS NULL AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND goa"
    "l_share_context_version IS NULL AND conversation_read_id IS NULL AND read_conversa"
    "tion_id IS NULL AND message_operation_id IS NULL AND message_operation_state IS NU"
    "LL AND request_view_ack_id IS NULL AND request_initiator_id IS NULL AND operator_a"
    "udit_id IS NULL AND operator_access_version IS NULL AND operator_action IS NULL) O"
    "R (kind='feedback.saved' AND study_outcome_id IS NULL AND study_conversation_id IS"
    " NULL AND study_outcome_version IS NULL AND study_answer IS NULL AND peer_feedback"
    "_id IS NOT NULL AND peer_feedback_version IS NOT NULL AND feedback_again IS NOT NU"
    "LL AND study_prompt_id IS NULL AND study_prompt_conversation_id IS NULL AND feedba"
    "ck_again IN ('yes','maybe','no') AND goal_id IS NULL AND goal_version IS NULL AND "
    "profile_version IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND "
    "topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND "
    "ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL A"
    "ND report_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL A"
    "ND blocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AN"
    "D private_passed IS NULL AND connection_request_id IS NULL AND connection_request_"
    "version IS NULL AND connection_request_state IS NULL AND connection_request_recipi"
    "ent_id IS NULL AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL AN"
    "D goal_share_context_version IS NULL AND conversation_read_id IS NULL AND read_con"
    "versation_id IS NULL AND message_operation_id IS NULL AND message_operation_state "
    "IS NULL AND request_view_ack_id IS NULL AND request_initiator_id IS NULL AND opera"
    "tor_audit_id IS NULL AND operator_access_version IS NULL AND operator_action IS NU"
    "LL) OR (kind='study.prompt_offered' AND study_outcome_id IS NULL AND study_convers"
    "ation_id IS NULL AND study_outcome_version IS NULL AND study_answer IS NULL AND pe"
    "er_feedback_id IS NULL AND peer_feedback_version IS NULL AND feedback_again IS NUL"
    "L AND study_prompt_id IS NOT NULL AND study_prompt_conversation_id IS NOT NULL AND"
    " TRUE AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND"
    " visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND s"
    "hared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_ki"
    "nd IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND bl"
    "ock_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND priv"
    "ate_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL AN"
    "D connection_request_id IS NULL AND connection_request_version IS NULL AND connect"
    "ion_request_state IS NULL AND connection_request_recipient_id IS NULL AND goal_sha"
    "re_id IS NULL AND goal_share_conversation_id IS NULL AND goal_share_context_versio"
    "n IS NULL AND conversation_read_id IS NULL AND read_conversation_id IS NULL AND me"
    "ssage_operation_id IS NULL AND message_operation_state IS NULL AND request_view_ac"
    "k_id IS NULL AND request_initiator_id IS NULL AND operator_audit_id IS NULL AND op"
    "erator_access_version IS NULL AND operator_action IS NULL)) AND help_version IS NU"
    "LL AND photo_version IS NULL) OR (kind='profile.saved' AND profile_version IS NOT "
    "NULL AND goal_id IS NULL AND goal_version IS NULL AND visibility_version IS NULL A"
    "ND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND on"
    "boarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NU"
    "LL AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL A"
    "ND block_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND priva"
    "te_pass_version IS NULL AND private_passed IS NULL AND connection_request_id IS NU"
    "LL AND connection_request_version IS NULL AND connection_request_state IS NULL AND"
    " connection_request_recipient_id IS NULL AND goal_share_id IS NULL AND goal_share_"
    "conversation_id IS NULL AND goal_share_context_version IS NULL AND conversation_re"
    "ad_id IS NULL AND read_conversation_id IS NULL AND message_operation_id IS NULL AN"
    "D message_operation_state IS NULL AND request_view_ack_id IS NULL AND request_init"
    "iator_id IS NULL AND operator_audit_id IS NULL AND operator_access_version IS NULL"
    " AND operator_action IS NULL AND study_outcome_id IS NULL AND study_conversation_i"
    "d IS NULL AND study_outcome_version IS NULL AND study_answer IS NULL AND peer_feed"
    "back_id IS NULL AND peer_feedback_version IS NULL AND feedback_again IS NULL AND s"
    "tudy_prompt_id IS NULL AND study_prompt_conversation_id IS NULL AND help_version I"
    "S NULL AND photo_version IS NULL) OR (kind='help.saved' AND help_version IS NOT NU"
    "LL AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND vi"
    "sibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shar"
    "ed_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind "
    "IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block"
    "_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND private"
    "_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL AND c"
    "onnection_request_id IS NULL AND connection_request_version IS NULL AND connection"
    "_request_state IS NULL AND connection_request_recipient_id IS NULL AND goal_share_"
    "id IS NULL AND goal_share_conversation_id IS NULL AND goal_share_context_version I"
    "S NULL AND conversation_read_id IS NULL AND read_conversation_id IS NULL AND messa"
    "ge_operation_id IS NULL AND message_operation_state IS NULL AND request_view_ack_i"
    "d IS NULL AND request_initiator_id IS NULL AND operator_audit_id IS NULL AND opera"
    "tor_access_version IS NULL AND operator_action IS NULL AND study_outcome_id IS NUL"
    "L AND study_conversation_id IS NULL AND study_outcome_version IS NULL AND study_an"
    "swer IS NULL AND peer_feedback_id IS NULL AND peer_feedback_version IS NULL AND fe"
    "edback_again IS NULL AND study_prompt_id IS NULL AND study_prompt_conversation_id "
    "IS NULL AND photo_version IS NULL) OR (kind='photo.published' AND photo_version IS"
    " NOT NULL AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL"
    " AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL A"
    "ND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND a"
    "i_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AN"
    "D block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND "
    "private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NUL"
    "L AND connection_request_id IS NULL AND connection_request_version IS NULL AND con"
    "nection_request_state IS NULL AND connection_request_recipient_id IS NULL AND goal"
    "_share_id IS NULL AND goal_share_conversation_id IS NULL AND goal_share_context_ve"
    "rsion IS NULL AND conversation_read_id IS NULL AND read_conversation_id IS NULL AN"
    "D message_operation_id IS NULL AND message_operation_state IS NULL AND request_vie"
    "w_ack_id IS NULL AND request_initiator_id IS NULL AND operator_audit_id IS NULL AN"
    "D operator_access_version IS NULL AND operator_action IS NULL AND study_outcome_id"
    " IS NULL AND study_conversation_id IS NULL AND study_outcome_version IS NULL AND s"
    "tudy_answer IS NULL AND peer_feedback_id IS NULL AND peer_feedback_version IS NULL"
    " AND feedback_again IS NULL AND study_prompt_id IS NULL AND study_prompt_conversat"
    "ion_id IS NULL AND help_version IS NULL)) AND lifecycle_revision_id IS NULL AND li"
    "fecycle_account_id IS NULL AND lifecycle_version IS NULL AND lifecycle_operation I"
    "S NULL) OR (kind='account.lifecycle_changed' AND lifecycle_revision_id IS NOT NULL"
    " AND lifecycle_account_id IS NOT NULL AND lifecycle_version IS NOT NULL AND lifecy"
    "cle_version>0 AND lifecycle_operation IS NOT NULL AND lifecycle_operation IN ('ban"
    "','unban','delete') AND goal_id IS NULL AND goal_version IS NULL AND profile_versi"
    "on IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present"
    " IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS "
    "NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id "
    "IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS"
    " NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND private_pas"
    "sed IS NULL AND connection_request_id IS NULL AND connection_request_version IS NU"
    "LL AND connection_request_state IS NULL AND connection_request_recipient_id IS NUL"
    "L AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND goal_share_"
    "context_version IS NULL AND conversation_read_id IS NULL AND read_conversation_id "
    "IS NULL AND message_operation_id IS NULL AND message_operation_state IS NULL AND r"
    "equest_view_ack_id IS NULL AND request_initiator_id IS NULL AND operator_audit_id "
    "IS NULL AND operator_access_version IS NULL AND operator_action IS NULL AND study_"
    "outcome_id IS NULL AND study_conversation_id IS NULL AND study_outcome_version IS "
    "NULL AND study_answer IS NULL AND peer_feedback_id IS NULL AND peer_feedback_versi"
    "on IS NULL AND feedback_again IS NULL AND study_prompt_id IS NULL AND study_prompt"
    "_conversation_id IS NULL AND help_version IS NULL AND photo_version IS NULL)"
)

EVENT_SHAPE = (
    "((((((((((((((((((((((((((kind != 'ai_job.completed' AND ai_job_id IS NULL AND ai_"
    "kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL) AND ((kind IN ('goal.save"
    "d', 'goal.completed') AND goal_id IS NOT NULL AND goal_version IS NOT NULL AND top"
    "ic_present IS NOT NULL AND shared_learning IS NOT NULL AND profile_version IS NULL"
    " AND visibility_version IS NULL AND onboarding_task IS NULL) OR (kind = 'profile.r"
    "eady' AND profile_version IS NOT NULL AND onboarding_task IS NOT NULL AND onboardi"
    "ng_task IN ('find_help', 'offer_help') AND goal_id IS NULL AND goal_version IS NUL"
    "L AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL "
    "AND shared_learning IS NULL) OR (kind IN ('profile.hidden', 'profile.restored', 'd"
    "iscovery.exposure_confirmed') AND visibility_version IS NOT NULL AND goal_id IS NU"
    "LL AND goal_version IS NULL AND profile_version IS NULL AND onboarding_task IS NUL"
    "L AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL) OR"
    " (kind = 'auth.email_confirmed' AND goal_id IS NULL AND goal_version IS NULL AND p"
    "rofile_version IS NULL AND visibility_version IS NULL AND onboarding_task IS NULL "
    "AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL))) OR"
    " (kind = 'ai_job.completed' AND ai_job_id IS NOT NULL AND ai_kind IS NOT NULL AND "
    "ai_kind IN ('clarify_goal','suggest_subject','assess_photo','triage_report') AND a"
    "i_state IS NOT NULL AND ai_state IN ('succeeded','failed','cancelled','expired') A"
    "ND (ai_reason IS NULL OR (ai_state IN ('failed','expired') AND ai_reason IN ('tran"
    "sient','invalid_output','invalid_input','timeout','auth_unavailable','rate_limited"
    "','account_unavailable','stale_source','executor_lost'))) AND goal_id IS NULL AND "
    "goal_version IS NULL AND profile_version IS NULL AND visibility_version IS NULL AN"
    "D subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND onb"
    "oarding_task IS NULL)) AND report_id IS NULL AND block_relationship_id IS NULL AND"
    " block_version IS NULL AND blocked IS NULL) OR ((goal_id IS NULL AND goal_version "
    "IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND subject_id "
    "IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_task "
    "IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reas"
    "on IS NULL) AND ((kind = 'report.created' AND report_id IS NOT NULL AND block_rela"
    "tionship_id IS NULL AND block_version IS NULL AND blocked IS NULL) OR (kind = 'blo"
    "ck.changed' AND report_id IS NULL AND block_relationship_id IS NOT NULL AND block_"
    "version IS NOT NULL AND blocked IS NOT NULL)))) AND private_pass_id IS NULL AND pr"
    "ivate_pass_version IS NULL AND private_passed IS NULL) OR (kind = 'discovery.pass_"
    "changed' AND private_pass_id IS NOT NULL AND private_pass_version IS NOT NULL AND "
    "private_passed IS NOT NULL AND goal_id IS NULL AND goal_version IS NULL AND profil"
    "e_version IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_"
    "present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job"
    "_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND rep"
    "ort_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AND blo"
    "cked IS NULL)) AND connection_request_id IS NULL AND connection_request_version IS"
    " NULL AND connection_request_state IS NULL AND connection_request_recipient_id IS "
    "NULL AND request_initiator_id IS NULL) OR (kind = 'request.changed' AND connection"
    "_request_id IS NOT NULL AND connection_request_version IS NOT NULL AND connection_"
    "request_state IS NOT NULL AND connection_request_recipient_id IS NOT NULL AND (req"
    "uest_initiator_id IS NULL OR request_initiator_id IN (account_id, connection_reque"
    "st_recipient_id)) AND goal_id IS NULL AND goal_version IS NULL AND profile_version"
    " IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present I"
    "S NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NU"
    "LL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS"
    " NULL AND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS N"
    "ULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND private_passe"
    "d IS NULL)) AND request_view_ack_id IS NULL) OR (kind = 'request.view_acknowledged"
    "' AND request_view_ack_id IS NOT NULL AND goal_id IS NULL AND goal_version IS NULL"
    " AND profile_version IS NULL AND visibility_version IS NULL AND subject_id IS NULL"
    " AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL"
    " AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS N"
    "ULL AND report_id IS NULL AND block_relationship_id IS NULL AND block_version IS N"
    "ULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NU"
    "LL AND private_passed IS NULL AND connection_request_id IS NULL AND connection_req"
    "uest_version IS NULL AND connection_request_state IS NULL AND connection_request_r"
    "ecipient_id IS NULL AND request_initiator_id IS NULL)) AND message_operation_id IS"
    " NULL AND message_operation_state IS NULL) OR (message_operation_id IS NOT NULL AN"
    "D message_operation_state IS NOT NULL AND ((kind='message.confirmed' AND message_o"
    "peration_state='confirmed') OR (kind='message.cancelled' AND message_operation_sta"
    "te='cancelled')) AND goal_id IS NULL AND goal_version IS NULL AND profile_version "
    "IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS"
    " NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NUL"
    "L AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS "
    "NULL AND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NU"
    "LL AND private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed"
    " IS NULL AND connection_request_id IS NULL AND connection_request_version IS NULL "
    "AND connection_request_state IS NULL AND connection_request_recipient_id IS NULL A"
    "ND request_view_ack_id IS NULL AND request_initiator_id IS NULL)) AND conversation"
    "_read_id IS NULL AND read_conversation_id IS NULL) OR (kind='conversation.read_ack"
    "nowledged' AND conversation_read_id IS NOT NULL AND read_conversation_id IS NOT NU"
    "LL AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND vi"
    "sibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shar"
    "ed_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind "
    "IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block"
    "_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND private"
    "_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL AND c"
    "onnection_request_id IS NULL AND connection_request_version IS NULL AND connection"
    "_request_state IS NULL AND connection_request_recipient_id IS NULL AND message_ope"
    "ration_id IS NULL AND message_operation_state IS NULL AND request_view_ack_id IS N"
    "ULL AND request_initiator_id IS NULL)) AND goal_share_id IS NULL AND goal_share_co"
    "ntext_version IS NULL AND goal_share_conversation_id IS NULL) OR (kind='conversati"
    "on.goal_shared' AND goal_share_id IS NOT NULL AND goal_share_context_version IS NO"
    "T NULL AND goal_share_conversation_id IS NOT NULL AND goal_id IS NULL AND goal_ver"
    "sion IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND subjec"
    "t_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_"
    "task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai"
    "_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND block_"
    "version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_v"
    "ersion IS NULL AND private_passed IS NULL AND connection_request_id IS NULL AND co"
    "nnection_request_version IS NULL AND connection_request_state IS NULL AND connecti"
    "on_request_recipient_id IS NULL AND conversation_read_id IS NULL AND read_conversa"
    "tion_id IS NULL AND message_operation_id IS NULL AND message_operation_state IS NU"
    "LL AND request_view_ack_id IS NULL AND request_initiator_id IS NULL)) AND operator"
    "_audit_id IS NULL AND operator_access_version IS NULL AND operator_action IS NULL)"
    " OR (kind='operator.inspected' AND operator_audit_id IS NOT NULL AND operator_acce"
    "ss_version IS NOT NULL AND operator_action IS NOT NULL AND operator_action IN ('se"
    "arch_accounts','read_account','read_conversation_messages','search_events','read_e"
    "vent','read_audit','search_reports','read_report','read_media','read_support_case'"
    ") AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND vis"
    "ibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND share"
    "d_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind I"
    "S NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_"
    "relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND private_"
    "pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL AND co"
    "nnection_request_id IS NULL AND connection_request_version IS NULL AND connection_"
    "request_state IS NULL AND connection_request_recipient_id IS NULL AND goal_share_i"
    "d IS NULL AND goal_share_conversation_id IS NULL AND goal_share_context_version IS"
    " NULL AND conversation_read_id IS NULL AND read_conversation_id IS NULL AND messag"
    "e_operation_id IS NULL AND message_operation_state IS NULL AND request_view_ack_id"
    " IS NULL AND request_initiator_id IS NULL)) AND study_outcome_id IS NULL AND study"
    "_conversation_id IS NULL AND study_outcome_version IS NULL AND study_answer IS NUL"
    "L AND peer_feedback_id IS NULL AND peer_feedback_version IS NULL AND feedback_agai"
    "n IS NULL AND study_prompt_id IS NULL AND study_prompt_conversation_id IS NULL) OR"
    " (kind='study.reported' AND study_outcome_id IS NOT NULL AND study_conversation_id"
    " IS NOT NULL AND study_outcome_version IS NOT NULL AND study_answer IS NOT NULL AN"
    "D peer_feedback_id IS NULL AND peer_feedback_version IS NULL AND feedback_again IS"
    " NULL AND study_prompt_id IS NULL AND study_prompt_conversation_id IS NULL AND stu"
    "dy_answer IN ('yes','not_yet','did_not_work_out') AND goal_id IS NULL AND goal_ver"
    "sion IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND subjec"
    "t_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_"
    "task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai"
    "_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND block_"
    "version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_v"
    "ersion IS NULL AND private_passed IS NULL AND connection_request_id IS NULL AND co"
    "nnection_request_version IS NULL AND connection_request_state IS NULL AND connecti"
    "on_request_recipient_id IS NULL AND goal_share_id IS NULL AND goal_share_conversat"
    "ion_id IS NULL AND goal_share_context_version IS NULL AND conversation_read_id IS "
    "NULL AND read_conversation_id IS NULL AND message_operation_id IS NULL AND message"
    "_operation_state IS NULL AND request_view_ack_id IS NULL AND request_initiator_id "
    "IS NULL AND operator_audit_id IS NULL AND operator_access_version IS NULL AND oper"
    "ator_action IS NULL) OR (kind='feedback.saved' AND study_outcome_id IS NULL AND st"
    "udy_conversation_id IS NULL AND study_outcome_version IS NULL AND study_answer IS "
    "NULL AND peer_feedback_id IS NOT NULL AND peer_feedback_version IS NOT NULL AND fe"
    "edback_again IS NOT NULL AND study_prompt_id IS NULL AND study_prompt_conversation"
    "_id IS NULL AND feedback_again IN ('yes','maybe','no') AND goal_id IS NULL AND goa"
    "l_version IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND s"
    "ubject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboar"
    "ding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL A"
    "ND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND b"
    "lock_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_p"
    "ass_version IS NULL AND private_passed IS NULL AND connection_request_id IS NULL A"
    "ND connection_request_version IS NULL AND connection_request_state IS NULL AND con"
    "nection_request_recipient_id IS NULL AND goal_share_id IS NULL AND goal_share_conv"
    "ersation_id IS NULL AND goal_share_context_version IS NULL AND conversation_read_i"
    "d IS NULL AND read_conversation_id IS NULL AND message_operation_id IS NULL AND me"
    "ssage_operation_state IS NULL AND request_view_ack_id IS NULL AND request_initiato"
    "r_id IS NULL AND operator_audit_id IS NULL AND operator_access_version IS NULL AND"
    " operator_action IS NULL) OR (kind='study.prompt_offered' AND study_outcome_id IS "
    "NULL AND study_conversation_id IS NULL AND study_outcome_version IS NULL AND study"
    "_answer IS NULL AND peer_feedback_id IS NULL AND peer_feedback_version IS NULL AND"
    " feedback_again IS NULL AND study_prompt_id IS NOT NULL AND study_prompt_conversat"
    "ion_id IS NOT NULL AND TRUE AND goal_id IS NULL AND goal_version IS NULL AND profi"
    "le_version IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic"
    "_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_jo"
    "b_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND re"
    "port_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AND bl"
    "ocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND pri"
    "vate_passed IS NULL AND connection_request_id IS NULL AND connection_request_versi"
    "on IS NULL AND connection_request_state IS NULL AND connection_request_recipient_i"
    "d IS NULL AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND goa"
    "l_share_context_version IS NULL AND conversation_read_id IS NULL AND read_conversa"
    "tion_id IS NULL AND message_operation_id IS NULL AND message_operation_state IS NU"
    "LL AND request_view_ack_id IS NULL AND request_initiator_id IS NULL AND operator_a"
    "udit_id IS NULL AND operator_access_version IS NULL AND operator_action IS NULL)) "
    "AND help_version IS NULL AND photo_version IS NULL) OR (kind='profile.saved' AND p"
    "rofile_version IS NOT NULL AND goal_id IS NULL AND goal_version IS NULL AND visibi"
    "lity_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_l"
    "earning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS N"
    "ULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_rel"
    "ationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND private_pas"
    "s_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL AND conne"
    "ction_request_id IS NULL AND connection_request_version IS NULL AND connection_req"
    "uest_state IS NULL AND connection_request_recipient_id IS NULL AND goal_share_id I"
    "S NULL AND goal_share_conversation_id IS NULL AND goal_share_context_version IS NU"
    "LL AND conversation_read_id IS NULL AND read_conversation_id IS NULL AND message_o"
    "peration_id IS NULL AND message_operation_state IS NULL AND request_view_ack_id IS"
    " NULL AND request_initiator_id IS NULL AND operator_audit_id IS NULL AND operator_"
    "access_version IS NULL AND operator_action IS NULL AND study_outcome_id IS NULL AN"
    "D study_conversation_id IS NULL AND study_outcome_version IS NULL AND study_answer"
    " IS NULL AND peer_feedback_id IS NULL AND peer_feedback_version IS NULL AND feedba"
    "ck_again IS NULL AND study_prompt_id IS NULL AND study_prompt_conversation_id IS N"
    "ULL AND help_version IS NULL AND photo_version IS NULL) OR (kind='help.saved' AND "
    "help_version IS NOT NULL AND goal_id IS NULL AND goal_version IS NULL AND profile_"
    "version IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND topic_pr"
    "esent IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_i"
    "d IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND repor"
    "t_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AND block"
    "ed IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND privat"
    "e_passed IS NULL AND connection_request_id IS NULL AND connection_request_version "
    "IS NULL AND connection_request_state IS NULL AND connection_request_recipient_id I"
    "S NULL AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND goal_s"
    "hare_context_version IS NULL AND conversation_read_id IS NULL AND read_conversatio"
    "n_id IS NULL AND message_operation_id IS NULL AND message_operation_state IS NULL "
    "AND request_view_ack_id IS NULL AND request_initiator_id IS NULL AND operator_audi"
    "t_id IS NULL AND operator_access_version IS NULL AND operator_action IS NULL AND s"
    "tudy_outcome_id IS NULL AND study_conversation_id IS NULL AND study_outcome_versio"
    "n IS NULL AND study_answer IS NULL AND peer_feedback_id IS NULL AND peer_feedback_"
    "version IS NULL AND feedback_again IS NULL AND study_prompt_id IS NULL AND study_p"
    "rompt_conversation_id IS NULL AND photo_version IS NULL) OR (kind='photo.published"
    "' AND photo_version IS NOT NULL AND goal_id IS NULL AND goal_version IS NULL AND p"
    "rofile_version IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND t"
    "opic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND a"
    "i_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AN"
    "D report_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AN"
    "D blocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND"
    " private_passed IS NULL AND connection_request_id IS NULL AND connection_request_v"
    "ersion IS NULL AND connection_request_state IS NULL AND connection_request_recipie"
    "nt_id IS NULL AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND"
    " goal_share_context_version IS NULL AND conversation_read_id IS NULL AND read_conv"
    "ersation_id IS NULL AND message_operation_id IS NULL AND message_operation_state I"
    "S NULL AND request_view_ack_id IS NULL AND request_initiator_id IS NULL AND operat"
    "or_audit_id IS NULL AND operator_access_version IS NULL AND operator_action IS NUL"
    "L AND study_outcome_id IS NULL AND study_conversation_id IS NULL AND study_outcome"
    "_version IS NULL AND study_answer IS NULL AND peer_feedback_id IS NULL AND peer_fe"
    "edback_version IS NULL AND feedback_again IS NULL AND study_prompt_id IS NULL AND "
    "study_prompt_conversation_id IS NULL AND help_version IS NULL)) AND lifecycle_revi"
    "sion_id IS NULL AND lifecycle_account_id IS NULL AND lifecycle_version IS NULL AND"
    " lifecycle_operation IS NULL) OR (kind='account.lifecycle_changed' AND lifecycle_r"
    "evision_id IS NOT NULL AND lifecycle_account_id IS NOT NULL AND lifecycle_version "
    "IS NOT NULL AND lifecycle_version>0 AND lifecycle_operation IS NOT NULL AND lifecy"
    "cle_operation IN ('ban','unban','delete') AND goal_id IS NULL AND goal_version IS "
    "NULL AND profile_version IS NULL AND visibility_version IS NULL AND subject_id IS "
    "NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS "
    "NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason "
    "IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND block_version "
    "IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_version I"
    "S NULL AND private_passed IS NULL AND connection_request_id IS NULL AND connection"
    "_request_version IS NULL AND connection_request_state IS NULL AND connection_reque"
    "st_recipient_id IS NULL AND goal_share_id IS NULL AND goal_share_conversation_id I"
    "S NULL AND goal_share_context_version IS NULL AND conversation_read_id IS NULL AND"
    " read_conversation_id IS NULL AND message_operation_id IS NULL AND message_operati"
    "on_state IS NULL AND request_view_ack_id IS NULL AND request_initiator_id IS NULL "
    "AND operator_audit_id IS NULL AND operator_access_version IS NULL AND operator_act"
    "ion IS NULL AND study_outcome_id IS NULL AND study_conversation_id IS NULL AND stu"
    "dy_outcome_version IS NULL AND study_answer IS NULL AND peer_feedback_id IS NULL A"
    "ND peer_feedback_version IS NULL AND feedback_again IS NULL AND study_prompt_id IS"
    " NULL AND study_prompt_conversation_id IS NULL AND help_version IS NULL AND photo_"
    "version IS NULL)) AND notification_preference_version IS NULL AND support_case_id "
    "IS NULL AND support_case_version IS NULL) OR (kind='notification_preference.change"
    "d' AND notification_preference_version IS NOT NULL AND notification_preference_ver"
    "sion>0 AND support_case_id IS NULL AND support_case_version IS NULL AND goal_id IS"
    " NULL AND goal_version IS NULL AND profile_version IS NULL AND visibility_version "
    "IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NU"
    "LL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_st"
    "ate IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id "
    "IS NULL AND block_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL "
    "AND private_pass_version IS NULL AND private_passed IS NULL AND connection_request"
    "_id IS NULL AND connection_request_version IS NULL AND connection_request_state IS"
    " NULL AND connection_request_recipient_id IS NULL AND goal_share_id IS NULL AND go"
    "al_share_conversation_id IS NULL AND goal_share_context_version IS NULL AND conver"
    "sation_read_id IS NULL AND read_conversation_id IS NULL AND message_operation_id I"
    "S NULL AND message_operation_state IS NULL AND request_view_ack_id IS NULL AND req"
    "uest_initiator_id IS NULL AND operator_audit_id IS NULL AND operator_access_versio"
    "n IS NULL AND operator_action IS NULL AND study_outcome_id IS NULL AND study_conve"
    "rsation_id IS NULL AND study_outcome_version IS NULL AND study_answer IS NULL AND "
    "peer_feedback_id IS NULL AND peer_feedback_version IS NULL AND feedback_again IS N"
    "ULL AND study_prompt_id IS NULL AND study_prompt_conversation_id IS NULL AND help_"
    "version IS NULL AND photo_version IS NULL AND lifecycle_revision_id IS NULL AND li"
    "fecycle_account_id IS NULL AND lifecycle_version IS NULL AND lifecycle_operation I"
    "S NULL) OR (kind IN ('support.received','support.status_changed') AND support_case"
    "_id IS NOT NULL AND support_case_version IS NOT NULL AND support_case_version>0 AN"
    "D notification_preference_version IS NULL AND goal_id IS NULL AND goal_version IS "
    "NULL AND profile_version IS NULL AND visibility_version IS NULL AND subject_id IS "
    "NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS "
    "NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason "
    "IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND block_version "
    "IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND private_pass_version I"
    "S NULL AND private_passed IS NULL AND connection_request_id IS NULL AND connection"
    "_request_version IS NULL AND connection_request_state IS NULL AND connection_reque"
    "st_recipient_id IS NULL AND goal_share_id IS NULL AND goal_share_conversation_id I"
    "S NULL AND goal_share_context_version IS NULL AND conversation_read_id IS NULL AND"
    " read_conversation_id IS NULL AND message_operation_id IS NULL AND message_operati"
    "on_state IS NULL AND request_view_ack_id IS NULL AND request_initiator_id IS NULL "
    "AND operator_audit_id IS NULL AND operator_access_version IS NULL AND operator_act"
    "ion IS NULL AND study_outcome_id IS NULL AND study_conversation_id IS NULL AND stu"
    "dy_outcome_version IS NULL AND study_answer IS NULL AND peer_feedback_id IS NULL A"
    "ND peer_feedback_version IS NULL AND feedback_again IS NULL AND study_prompt_id IS"
    " NULL AND study_prompt_conversation_id IS NULL AND help_version IS NULL AND photo_"
    "version IS NULL AND lifecycle_revision_id IS NULL AND lifecycle_account_id IS NULL"
    " AND lifecycle_version IS NULL AND lifecycle_operation IS NULL)"
)

BEFORE_AUDIT_SHAPE = (
    "(((((action='search_accounts' AND resource_kind='account' AND requested_id IS NULL"
    " AND outcome='search' AND query_fingerprint IS NOT NULL AND octet_length(query_fin"
    "gerprint)=32 AND cardinality(result_ids)<=20) OR (action='read_account' AND resour"
    "ce_kind='account' AND requested_id IS NOT NULL AND query_fingerprint IS NULL AND ("
    "(outcome='read' AND result_ids=ARRAY[requested_id]) OR (outcome='not_found' AND ca"
    "rdinality(result_ids)=0))) OR (action='read_conversation_messages' AND resource_ki"
    "nd='conversation' AND requested_id IS NOT NULL AND query_fingerprint IS NULL AND ("
    "(outcome='read' AND cardinality(result_ids)<=50) OR (outcome='not_found' AND cardi"
    "nality(result_ids)=0)))) OR (action='search_events' AND resource_kind='event' AND "
    "requested_id IS NULL AND outcome='search' AND query_fingerprint IS NOT NULL AND oc"
    "tet_length(query_fingerprint)=32 AND cardinality(result_ids)<=50) OR (action IN ('"
    "read_event','read_audit') AND resource_kind=CASE WHEN action='read_event' THEN 'ev"
    "ent' ELSE 'audit' END AND requested_id IS NOT NULL AND query_fingerprint IS NULL A"
    "ND ((outcome='read' AND result_ids=ARRAY[requested_id]) OR (outcome='not_found' AN"
    "D cardinality(result_ids)=0)))) OR (action='search_reports' AND resource_kind='rep"
    "ort' AND requested_id IS NULL AND outcome='search' AND query_fingerprint IS NOT NU"
    "LL AND octet_length(query_fingerprint)=32 AND cardinality(result_ids)<=50) OR (act"
    "ion='read_report' AND resource_kind='report' AND requested_id IS NOT NULL AND quer"
    "y_fingerprint IS NULL AND ((outcome='read' AND result_ids=ARRAY[requested_id]) OR "
    "(outcome='not_found' AND cardinality(result_ids)=0)))) AND requested_media_owner_i"
    "d IS NULL AND requested_media_attempt_id IS NULL AND requested_media_kind IS NULL "
    "AND actual_source_upload_id IS NULL) OR (action='read_media' AND resource_kind='pr"
    "ofile_media' AND requested_id IS NOT NULL AND query_fingerprint IS NULL AND reques"
    "ted_media_owner_id IS NOT NULL AND requested_media_attempt_id IS NOT NULL AND requ"
    "ested_media_kind IS NOT NULL AND requested_media_kind IN ('original','display') AN"
    "D ((outcome='read' AND result_ids=ARRAY[requested_id] AND actual_source_upload_id "
    "IS NOT NULL AND actual_source_upload_id=requested_id) OR (outcome='not_found' AND "
    "cardinality(result_ids)=0 AND (actual_source_upload_id IS NULL OR actual_source_up"
    "load_id=requested_id))))"
)

AUDIT_SHAPE = (
    "((((((action='search_accounts' AND resource_kind='account' AND requested_id IS NUL"
    "L AND outcome='search' AND query_fingerprint IS NOT NULL AND octet_length(query_fi"
    "ngerprint)=32 AND cardinality(result_ids)<=20) OR (action='read_account' AND resou"
    "rce_kind='account' AND requested_id IS NOT NULL AND query_fingerprint IS NULL AND "
    "((outcome='read' AND result_ids=ARRAY[requested_id]) OR (outcome='not_found' AND c"
    "ardinality(result_ids)=0))) OR (action='read_conversation_messages' AND resource_k"
    "ind='conversation' AND requested_id IS NOT NULL AND query_fingerprint IS NULL AND "
    "((outcome='read' AND cardinality(result_ids)<=50) OR (outcome='not_found' AND card"
    "inality(result_ids)=0)))) OR (action='search_events' AND resource_kind='event' AND"
    " requested_id IS NULL AND outcome='search' AND query_fingerprint IS NOT NULL AND o"
    "ctet_length(query_fingerprint)=32 AND cardinality(result_ids)<=50) OR (action IN ("
    "'read_event','read_audit') AND resource_kind=CASE WHEN action='read_event' THEN 'e"
    "vent' ELSE 'audit' END AND requested_id IS NOT NULL AND query_fingerprint IS NULL "
    "AND ((outcome='read' AND result_ids=ARRAY[requested_id]) OR (outcome='not_found' A"
    "ND cardinality(result_ids)=0)))) OR (action='search_reports' AND resource_kind='re"
    "port' AND requested_id IS NULL AND outcome='search' AND query_fingerprint IS NOT N"
    "ULL AND octet_length(query_fingerprint)=32 AND cardinality(result_ids)<=50) OR (ac"
    "tion='read_report' AND resource_kind='report' AND requested_id IS NOT NULL AND que"
    "ry_fingerprint IS NULL AND ((outcome='read' AND result_ids=ARRAY[requested_id]) OR"
    " (outcome='not_found' AND cardinality(result_ids)=0)))) AND requested_media_owner_"
    "id IS NULL AND requested_media_attempt_id IS NULL AND requested_media_kind IS NULL"
    " AND actual_source_upload_id IS NULL) OR (action='read_media' AND resource_kind='p"
    "rofile_media' AND requested_id IS NOT NULL AND query_fingerprint IS NULL AND reque"
    "sted_media_owner_id IS NOT NULL AND requested_media_attempt_id IS NOT NULL AND req"
    "uested_media_kind IS NOT NULL AND requested_media_kind IN ('original','display') A"
    "ND ((outcome='read' AND result_ids=ARRAY[requested_id] AND actual_source_upload_id"
    " IS NOT NULL AND actual_source_upload_id=requested_id) OR (outcome='not_found' AND"
    " cardinality(result_ids)=0 AND (actual_source_upload_id IS NULL OR actual_source_u"
    "pload_id=requested_id))))) OR (action='read_support_case' AND resource_kind='suppo"
    "rt_case' AND requested_id IS NOT NULL AND query_fingerprint IS NULL AND requested_"
    "media_owner_id IS NULL AND requested_media_attempt_id IS NULL AND requested_media_"
    "kind IS NULL AND actual_source_upload_id IS NULL AND ((outcome='read' AND result_i"
    "ds=ARRAY[requested_id]) OR (outcome='not_found' AND cardinality(result_ids)=0)))"
)


def upgrade() -> None:
    op.create_table(
        "notification_preference_revisions",
        sa.Column("account_id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("mode", sa.String(32), nullable=False, primary_key=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.CheckConstraint(
            "mode IN ('messages_and_requests', 'all_updates')",
            name=op.f("ck_notification_preference_revisions_known_mode"),
        ),
        sa.CheckConstraint(
            "version >= 1",
            name=op.f("ck_notification_preference_revisions_positive_version"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_notification_preference_revisions_account_id_accounts"),
        ),
    )
    op.create_table(
        "notification_preference_intents",
        sa.Column("account_id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("key", sa.String(128), nullable=False, primary_key=True),
        sa.Column("fingerprint", sa.LargeBinary(32), nullable=False, primary_key=False),
        sa.Column("result_version", sa.Integer(), nullable=True, primary_key=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.CheckConstraint(
            "octet_length(fingerprint) = 32",
            name=op.f("ck_notification_preference_intents_fingerprint_length"),
        ),
        sa.CheckConstraint(
            "key ~ '^[A-Za-z0-9_-]{8,128}$'",
            name=op.f("ck_notification_preference_intents_valid_key"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_notification_preference_intents_account_id_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "result_version"],
            [
                "notification_preference_revisions.account_id",
                "notification_preference_revisions.version",
            ],
            name=op.f(
                "fk_notification_preference_intents_account_id_notification_preference_revisions"
            ),
        ),
    )
    op.create_table(
        "support_proofs",
        sa.Column("digest", sa.LargeBinary(32), nullable=False, primary_key=True),
        sa.Column("source_digest", sa.LargeBinary(32), nullable=False, primary_key=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.CheckConstraint(
            "octet_length(digest) = 32 AND octet_length(source_digest) = 32",
            name=op.f("ck_support_proofs_digest_lengths"),
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name=op.f("ck_support_proofs_ordered_expiry"),
        ),
    )
    op.create_index("ix_support_proofs_source", "support_proofs", ["source_digest"])
    op.create_table(
        "support_preparations",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("source_digest", sa.LargeBinary(32), nullable=False, primary_key=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.CheckConstraint(
            "octet_length(source_digest) = 32",
            name=op.f("ck_support_preparations_digest_length"),
        ),
    )
    op.create_index(
        "ix_support_preparations_source_created",
        "support_preparations",
        ["source_digest", "created_at"],
    )
    op.create_table(
        "support_cases",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("proof_digest", sa.LargeBinary(32), nullable=False, primary_key=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True, primary_key=False),
        sa.Column("topic", sa.String(32), nullable=False, primary_key=False),
        sa.Column("reply_address", sa.String(254), nullable=False, primary_key=False),
        sa.Column("message", sa.String(4000), nullable=False, primary_key=False),
        sa.Column("details", sa.String(2000), nullable=True, primary_key=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column("http_request_id", sa.Uuid(), nullable=True, primary_key=False),
        sa.Column("action_id", sa.Uuid(), nullable=True, primary_key=False),
        sa.Column("trace_id", sa.String(32), nullable=True, primary_key=False),
        sa.Column("span_id", sa.String(16), nullable=True, primary_key=False),
        sa.CheckConstraint(
            "details IS NULL OR length(btrim(details)) BETWEEN 1 AND 2000",
            name=op.f("ck_support_cases_bounded_details"),
        ),
        sa.CheckConstraint(
            "length(btrim(message)) BETWEEN 1 AND 4000",
            name=op.f("ck_support_cases_bounded_message"),
        ),
        sa.CheckConstraint(
            "length(reply_address) BETWEEN 3 AND 254",
            name=op.f("ck_support_cases_bounded_reply"),
        ),
        sa.CheckConstraint(
            "topic IN ('cannot_sign_in','email_not_accepted','code_not_arriving','email_already"
            "_in_use','deleted_account','other')",
            name=op.f("ck_support_cases_known_topic"),
        ),
        sa.CheckConstraint(
            "http_request_id IS NOT NULL OR (action_id IS NULL AND trace_id IS NULL AND span_id"
            " IS NULL)",
            name=op.f("ck_support_cases_origin_request_context"),
        ),
        sa.CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR (trace_id IS NOT NULL AND span_id IS NOT"
            " NULL AND trace_id ~ '^[0-9a-f]{32}$' AND trace_id != repeat('0', 32) AND span_id "
            "~ '^[0-9a-f]{16}$' AND span_id != repeat('0', 16))",
            name=op.f("ck_support_cases_origin_trace_pair"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["accounts.id"], name=op.f("fk_support_cases_actor_id_accounts")
        ),
        sa.ForeignKeyConstraint(
            ["proof_digest"],
            ["support_proofs.digest"],
            name=op.f("fk_support_cases_proof_digest_support_proofs"),
        ),
    )
    op.create_index(
        "ix_support_cases_actor_received", "support_cases", ["actor_id", "received_at", "id"]
    )
    op.create_index(
        "ix_support_cases_proof_received", "support_cases", ["proof_digest", "received_at"]
    )
    op.create_table(
        "support_case_revisions",
        sa.Column("case_id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("status", sa.String(16), nullable=False, primary_key=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column("changed_by_id", sa.Uuid(), nullable=True, primary_key=False),
        sa.Column("operator_access_version", sa.Integer(), nullable=True, primary_key=False),
        sa.CheckConstraint(
            "(version = 1 AND status = 'received' AND changed_by_id IS NULL AND operator_access"
            "_version IS NULL) OR (version > 1 AND changed_by_id IS NOT NULL AND operator_acces"
            "s_version IS NOT NULL)",
            name=op.f("ck_support_case_revisions_actual_status_authority"),
        ),
        sa.CheckConstraint(
            "status IN ('received','in_review','resolved')",
            name=op.f("ck_support_case_revisions_known_status"),
        ),
        sa.CheckConstraint(
            "version >= 1",
            name=op.f("ck_support_case_revisions_positive_version"),
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["support_cases.id"],
            name=op.f("fk_support_case_revisions_case_id_support_cases"),
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_id", "operator_access_version"],
            ["operator_access_revisions.account_id", "operator_access_revisions.version"],
            name=op.f("fk_support_case_revisions_changed_by_id_operator_access_revisions"),
        ),
    )
    op.create_table(
        "support_case_intents",
        sa.Column("proof_digest", sa.LargeBinary(32), nullable=False, primary_key=True),
        sa.Column("key", sa.String(128), nullable=False, primary_key=True),
        sa.Column("fingerprint", sa.LargeBinary(32), nullable=False, primary_key=False),
        sa.Column("case_id", sa.Uuid(), nullable=False, primary_key=False),
        sa.Column("result_version", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.CheckConstraint(
            "octet_length(fingerprint) = 32",
            name=op.f("ck_support_case_intents_fingerprint_length"),
        ),
        sa.CheckConstraint(
            "key ~ '^[A-Za-z0-9_-]{8,128}$'",
            name=op.f("ck_support_case_intents_valid_key"),
        ),
        sa.ForeignKeyConstraint(
            ["case_id", "result_version"],
            ["support_case_revisions.case_id", "support_case_revisions.version"],
            name=op.f("fk_support_case_intents_case_id_support_case_revisions"),
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["support_cases.id"],
            name=op.f("fk_support_case_intents_case_id_support_cases"),
        ),
        sa.ForeignKeyConstraint(
            ["proof_digest"],
            ["support_proofs.digest"],
            name=op.f("fk_support_case_intents_proof_digest_support_proofs"),
        ),
    )
    op.create_table(
        "support_operator_intents",
        sa.Column("operator_id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("key", sa.String(128), nullable=False, primary_key=True),
        sa.Column("fingerprint", sa.LargeBinary(32), nullable=False, primary_key=False),
        sa.Column("case_id", sa.Uuid(), nullable=False, primary_key=False),
        sa.Column("result_version", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.CheckConstraint(
            "octet_length(fingerprint) = 32",
            name=op.f("ck_support_operator_intents_fingerprint_length"),
        ),
        sa.CheckConstraint(
            "key ~ '^[A-Za-z0-9_-]{8,128}$'",
            name=op.f("ck_support_operator_intents_valid_key"),
        ),
        sa.ForeignKeyConstraint(
            ["case_id", "result_version"],
            ["support_case_revisions.case_id", "support_case_revisions.version"],
            name=op.f("fk_support_operator_intents_case_id_support_case_revisions"),
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["support_cases.id"],
            name=op.f("fk_support_operator_intents_case_id_support_cases"),
        ),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            ["accounts.id"],
            name=op.f("fk_support_operator_intents_operator_id_accounts"),
        ),
    )
    op.add_column(
        "product_events", sa.Column("notification_preference_version", sa.Integer(), nullable=True)
    )
    op.add_column("product_events", sa.Column("support_case_id", sa.Uuid(), nullable=True))
    op.add_column("product_events", sa.Column("support_case_version", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_product_events_notification_preference_source",
        "product_events",
        "notification_preference_revisions",
        ["account_id", "notification_preference_version"],
        ["account_id", "version"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_product_events_support_revision_source",
        "product_events",
        "support_case_revisions",
        ["support_case_id", "support_case_version"],
        ["case_id", "version"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", type_="check"
    )
    op.create_check_constraint("event_reference_shape", "product_events", EVENT_SHAPE)
    op.drop_constraint(
        op.f("ck_operator_audits_fixed_inspection_shape"), "operator_audits", type_="check"
    )
    op.create_check_constraint("fixed_inspection_shape", "operator_audits", AUDIT_SHAPE)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM notification_preference_revisions)")
    ):
        raise RuntimeError("Refusing to discard retained support/preference records")
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM notification_preference_intents)")
    ):
        raise RuntimeError("Refusing to discard retained support/preference records")
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM support_proofs)")):
        raise RuntimeError("Refusing to discard retained support/preference records")
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM support_preparations)")):
        raise RuntimeError("Refusing to discard retained support/preference records")
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM support_cases)")):
        raise RuntimeError("Refusing to discard retained support/preference records")
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM support_case_revisions)")):
        raise RuntimeError("Refusing to discard retained support/preference records")
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM support_case_intents)")):
        raise RuntimeError("Refusing to discard retained support/preference records")
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM support_operator_intents)")):
        raise RuntimeError("Refusing to discard retained support/preference records")
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM operator_audits WHERE action='read_support_case')")
    ):
        raise RuntimeError("Refusing to remove retained support inspection sources")
    op.drop_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", type_="check"
    )
    op.drop_constraint(
        "fk_product_events_notification_preference_source", "product_events", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_product_events_support_revision_source", "product_events", type_="foreignkey"
    )
    for name in ("support_case_version", "support_case_id", "notification_preference_version"):
        op.drop_column("product_events", name)
    op.create_check_constraint("event_reference_shape", "product_events", BEFORE_EVENT_SHAPE)
    op.drop_constraint(
        op.f("ck_operator_audits_fixed_inspection_shape"), "operator_audits", type_="check"
    )
    op.create_check_constraint("fixed_inspection_shape", "operator_audits", BEFORE_AUDIT_SHAPE)
    op.drop_table("support_operator_intents")
    op.drop_table("support_case_intents")
    op.drop_table("support_case_revisions")
    op.drop_table("support_cases")
    op.drop_table("support_preparations")
    op.drop_table("support_proofs")
    op.drop_table("notification_preference_intents")
    op.drop_table("notification_preference_revisions")
