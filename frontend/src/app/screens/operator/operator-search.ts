import type { ParamMap } from '@angular/router';
import type { AccountFilters } from './operator-contract';
import { instant, uuid } from './operator-contract';

export const searchFields = [
  { key: 'name', label: 'Name', hint: 'Up to 50 characters' },
  {
    key: 'institutional_email',
    label: 'Institutional email',
    hint: 'Exact mail.apu.edu.my address',
  },
  { key: 'account_id', label: 'Account ID', hint: 'Stored UUID' },
  { key: 'google_link_id', label: 'Google identity link ID', hint: 'Stored UUID' },
  { key: 'google_issuer', label: 'Google issuer', hint: 'https://accounts.google.com' },
  {
    key: 'google_subject',
    label: 'Google subject',
    hint: 'Stored subject, including nonnumeric values',
  },
  {
    key: 'created_from',
    label: 'Created from',
    hint: 'ISO date and time with timezone, inclusive',
  },
  {
    key: 'created_before',
    label: 'Created before',
    hint: 'ISO date and time with timezone, exclusive',
  },
] as const;
export const lifecycleFilters = ['all', 'active', 'banned', 'deleted'] as const;
export const hiddenFilters = ['any', 'hidden', 'visible'] as const;
export function readFilters(params: Readonly<ParamMap>): Readonly<{
  readonly filters: AccountFilters;
  readonly error: string | null;
}> {
  const text = (key: string): string | null => {
    const value = params.get(key);
    return value === null || value.trim() === '' ? null : value.trim();
  };
  const account = text('account_id');
  const link = text('google_link_id');
  const issuer = text('google_issuer');
  const subject = params.get('google_subject');
  const email = text('institutional_email');
  const rawName = params.get('name');
  const name = rawName === null ? null : rawName.trim().replace(/\s+/gu, ' ');
  const from = text('created_from');
  const before = text('created_before');
  const cursor = params.get('cursor');
  const lifecycle = text('lifecycle') ?? 'all';
  const hidden = text('hidden');
  const validLifecycle =
    lifecycle === 'all' ||
    lifecycle === 'active' ||
    lifecycle === 'banned' ||
    lifecycle === 'deleted';
  const filters: AccountFilters = {
    account_id: account,
    google_link_id: link,
    google_issuer: issuer,
    google_subject: subject,
    institutional_email: email,
    name,
    lifecycle: validLifecycle ? lifecycle : 'all',
    hidden: hidden === 'true' ? true : hidden === 'false' ? false : null,
    created_from: from,
    created_before: before,
    cursor,
  };
  let error: string | null = null;
  if ((account !== null && !uuid(account)) || (link !== null && !uuid(link)))
    error = 'Account and Google identity link IDs must be UUIDs.';
  else if (issuer !== null && issuer !== 'https://accounts.google.com')
    error = 'Use the stored Google issuer https://accounts.google.com.';
  else if (
    subject !== null &&
    (/[^\p{ASCII}]/u.test(subject) || subject.length === 0 || subject.length > 255)
  )
    error = 'Google subject must contain at most 255 ASCII characters.';
  else if (
    email !== null &&
    !/^(?=[^@]{1,64}@)[a-z\d!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z\d!#$%&'*+/=?^_`{|}~-]+)*@mail\.apu\.edu\.my$/i.test(
      email,
    )
  )
    error = 'Enter an institutional mail.apu.edu.my email address.';
  else if (
    name !== null &&
    (name.length === 0 || Array.from(name).length > 50 || /[\p{Cc}\p{Cs}]/u.test(name))
  )
    error = 'Name must contain at most 50 plain-text characters.';
  else if (!validLifecycle || (hidden !== null && hidden !== 'true' && hidden !== 'false'))
    error = 'Choose a valid lifecycle and visibility filter.';
  else if ((from !== null && !instant(from)) || (before !== null && !instant(before)))
    error = 'Created dates must include a valid time and timezone.';
  else if (from !== null && before !== null && Date.parse(from) >= Date.parse(before))
    error = 'Created before must be later than Created from.';
  else if (cursor !== null && (cursor.length === 0 || cursor.length > 1024))
    error = 'The page cursor is invalid. Return to the first page.';
  return { filters, error };
}
