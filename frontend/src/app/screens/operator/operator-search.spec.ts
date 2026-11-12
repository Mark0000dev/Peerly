import { convertToParamMap } from '@angular/router';
import { describe, expect, it } from 'vitest';
import { filterQuery } from './operator-contract';
import { readFilters } from './operator-search';
import { account } from './operator.fixtures';

describe('M03 actual account filters', () => {
  it('preserves exact opaque cursor, complete generated parameters and explicit false without numeric Google assumptions', () => {
    const input = {
      account_id: account.account_id,
      google_link_id: account.google_link?.id,
      google_issuer: 'https://accounts.google.com',
      google_subject: 'subject_alpha-01',
      institutional_email: 'Maya@mail.apu.edu.my',
      name: 'Maya Lee',
      lifecycle: 'deleted',
      hidden: 'false',
      created_from: '2026-10-01T00:00:00+08:00',
      created_before: '2026-11-01T00:00:00Z',
      cursor: 'opaque+/=😀',
    };
    const result = readFilters(convertToParamMap(input));
    expect(result.error).toBeNull();
    const url = new URLSearchParams(filterQuery(result.filters));
    expect(url.get('google_subject')).toBe('subject_alpha-01');
    expect(url.get('hidden')).toBe('false');
    expect(url.get('cursor')).toBe(input.cursor);
    expect(url.get('account_id')).toBe(account.account_id);
    expect(url.size).toBe(11);
    expect(
      readFilters(convertToParamMap({ hidden: 'true', lifecycle: 'active' })).filters.hidden,
    ).toBe(true);
    expect(readFilters(convertToParamMap({ lifecycle: 'banned' })).error).toBeNull();
    expect(filterQuery({})).toBe('');
    expect(readFilters(convertToParamMap({ name: '   ' })).error).not.toBeNull();
    expect(
      readFilters(convertToParamMap({ google_subject: ' subject ' })).filters.google_subject,
    ).toBe(' subject ');
  });
  it('rejects invalid deep-link values instead of silently broadening an inspection', () => {
    for (const query of [
      { account_id: 'not-a-uuid' },
      { google_link_id: 'bad' },
      { google_issuer: 'https://other.invalid' },
      { google_subject: '非ASCII' },
      { google_subject: '' },
      { name: '' },
      { google_subject: 'a'.repeat(256) },
      { institutional_email: 'maya@apu.edu.my' },
      { name: 'a'.repeat(51) },
      { name: 'bad\u0000name' },
      { lifecycle: 'restricted' },
      { hidden: 'yes' },
      { created_from: '2026-01-01T00:00:00' },
      { created_before: 'invalid' },
      { created_from: '2026-02-01T00:00:00Z', created_before: '2026-01-01T00:00:00Z' },
      { created_from: '2026-01-01T00:00:00Z', created_before: '2026-01-01T00:00:00Z' },
      { cursor: '' },
      { cursor: 'x'.repeat(1025) },
    ])
      expect(readFilters(convertToParamMap(query)).error).not.toBeNull();
    expect(readFilters(convertToParamMap({})).error).toBeNull();
  });
});
