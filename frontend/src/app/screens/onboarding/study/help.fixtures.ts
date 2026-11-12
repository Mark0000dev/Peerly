import type { Api } from '../../../api.generated';

export const helpSelection = {
  version: 2,
  saved_at: '2026-11-07T12:00:00Z',
  subjects: [
    { subject_id: '00000000-0000-0000-0000-000000000010', label: 'Calculus', topic_note: 'Limits' },
  ],
} as const satisfies Api['schemas']['HelpResponse'];
export const ownHelp = {
  selection: helpSelection,
} as const satisfies Api['schemas']['OwnHelpResponse'];
