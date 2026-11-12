import { describe, expect, it } from 'vitest';
import {
  isRecentSupport,
  isSupportPreparation,
  isSupportReceipt,
  isSupportTopic,
  supportStatus,
  validReplyAddress,
  validSupportText,
} from './support-contract';

const receipt = {
  case_id: '00000000-0000-4000-8000-000000000101',
  status: 'received',
  version: 1,
  received_at: '2026-11-09T08:00:00Z',
  changed_at: '2026-11-09T08:00:00Z',
};
describe('Actual support receipt and bounded private inputs', () => {
  it('accepts only actual topics/statuses and ordered receipt versions', () => {
    expect(isSupportTopic('deleted_account')).toBe(true);
    expect(isSupportTopic('report_message')).toBe(false);
    expect(isSupportReceipt(receipt)).toBe(true);
    for (const change of [
      { case_id: 'bad' },
      { status: 'replied' },
      { version: 0 },
      { version: 1.2 },
      { received_at: 'bad' },
      { changed_at: '2026-11-08T08:00:00Z' },
    ])
      expect(isSupportReceipt({ ...receipt, ...change })).toBe(false);
    expect(isSupportReceipt(null)).toBe(false);
    expect(
      ['received', 'in_review', 'resolved'].map((status) =>
        isSupportReceipt({ ...receipt, status }),
      ),
    ).toEqual([true, true, true]);
    expect(supportStatus('received')).toBe('Received');
    expect(supportStatus('in_review')).toBe('In review');
    expect(supportStatus('resolved')).toBe('Resolved');
  });
  it('requires a bounded recent projection and actual context response', () => {
    expect(isRecentSupport({ cases: [] })).toBe(true);
    expect(isRecentSupport({ cases: [receipt] })).toBe(true);
    for (const value of [
      null,
      {},
      { cases: [{}] },
      { cases: Array.from({ length: 21 }, () => receipt) },
    ])
      expect(isRecentSupport(value)).toBe(false);
    expect(
      isSupportPreparation({ csrf_token: 'proof-csrf', expires_at: '2026-11-10T08:00:00Z' }),
    ).toBe(true);
    for (const value of [
      null,
      {},
      { csrf_token: '', expires_at: '2026-11-10T08:00:00Z' },
      { csrf_token: 'token', expires_at: 'bad' },
    ])
      expect(isSupportPreparation(value)).toBe(false);
  });
  it('matches actual reply/text codepoint and control limits without university-only restrictions', () => {
    expect(validReplyAddress('student@example.org')).toBe(true);
    for (const value of [
      ' student@example.org',
      'student@example.org ',
      'a@@b.c',
      'a@b',
      '@b.c',
      'a @b.c',
      'a\u0000@b.c',
      'a'.repeat(255) + '@b.c',
    ])
      expect(validReplyAddress(value)).toBe(false);
    expect(validSupportText('🙂'.repeat(4000), 4000)).toBe(true);
    expect(validSupportText('a\nb\rc\td', 4000)).toBe(true);
    for (const value of ['', ' \t\n', '🙂'.repeat(4001), 'a\u0000b', 'a\u007fb', 'a\ud800b'])
      expect(validSupportText(value, 4000)).toBe(false);
  });
});
