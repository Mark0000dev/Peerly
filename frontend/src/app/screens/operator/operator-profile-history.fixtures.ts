import type { Api } from '../../api.generated';
import { account } from './operator.fixtures';
export function storedProfile(
  version: number,
): Api['schemas']['OperatorProfileHistoryRevisionResponse'] {
  return {
    account_id: account.account_id,
    version,
    saved_at: '2026-01-08T04:00:00Z',
    display_name: null,
    about: '<b>Stored raw history</b>\n  Original spacing',
    programme: '',
    year_label: 'Legacy year',
    languages: ['zz-Legacy', '', 'zz-Legacy', 'EN'],
    task: 'offer_help',
  };
}
export const profilePage: Api['schemas']['OperatorProfileHistoryResponse'] = {
  account_id: account.account_id,
  anchor_version: 53,
  revisions: [
    storedProfile(53),
    {
      ...storedProfile(52),
      display_name: '',
      about: null,
      programme: null,
      year_label: null,
      languages: [],
      task: 'find_help',
    },
  ],
  next_cursor: 'signed-profile-page',
};
