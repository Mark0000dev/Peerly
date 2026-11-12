import type { Api } from '../../../api.generated';

export const revision = {
  version: 2,
  display_name: 'Maya Lee',
  about: 'Learning together',
  programme: 'Computing',
  year_label: 'Year 1',
  languages: ['en'],
  task: 'find_help',
  saved_at: '2026-11-07T12:00:00Z',
} as const satisfies Api['schemas']['ProfileRevisionResponse'];
export const ownProfile = {
  profile: revision,
  photo: null,
} as const satisfies Api['schemas']['OwnProfileResponse'];

export const profileReference = {
  university: 'APU Malaysia',
  min_display_name_length: 2,
  max_display_name_length: 50,
  max_languages: 5,
  languages: [
    { code: 'en', label: 'English' },
    { code: 'ms', label: 'Malay' },
    { code: 'zh', label: 'Mandarin' },
    { code: 'ta', label: 'Tamil' },
    { code: 'ar', label: 'Arabic' },
    { code: 'ru', label: 'Russian' },
  ],
} as const satisfies Api['schemas']['ProfileReferenceResponse'];
