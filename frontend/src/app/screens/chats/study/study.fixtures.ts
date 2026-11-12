import type { Api } from '../../../api.generated';
import { conversation } from '../chats.fixtures';

export const outcome: Api['schemas']['StudyOutcomeResponse'] = {
  id: '00000000-0000-4000-8000-000000000071',
  conversation_id: conversation.conversation_id,
  version: 3,
  answer: 'yes',
  changed_at: '2026-11-08T06:00:00Z',
};
export const receipt: Api['schemas']['FeedbackReceiptResponse'] = {
  id: '00000000-0000-4000-8000-000000000072',
  conversation_id: conversation.conversation_id,
  version: 7,
  again: 'maybe',
  descriptors: ['supportive'],
  team_note: 'We met at the library.',
  changed_at: '2026-11-08T06:10:00Z',
  worked_outcome_id: outcome.id,
  worked_outcome_version: outcome.version,
  captured_public_eligibility: true,
};
export const ownFeedback: Api['schemas']['OwnFeedbackResponse'] = {
  outcome,
  current: receipt,
  can_submit: true,
  current_publication: 'eligible',
  submission_publication: 'eligible',
};
export const offered: Api['schemas']['OfferedStudyPromptResponse'] = {
  outcome: 'offered',
  receipt_id: '00000000-0000-4000-8000-000000000073',
  conversation_id: conversation.conversation_id,
  offered_at: '2026-11-08T06:11:00Z',
};
