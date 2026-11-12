import { describe, expect, it } from 'vitest';
import { absoluteChatTime, chatTime } from './chats-date';
describe('Actual C01/C02 Kuala Lumpur calendar labels', () => {
  it('keeps exact local HH:mm today, switching at KL midnight instead of UTC midnight', () => {
    const sent = '2026-11-08T15:59:00Z';
    expect(chatTime(sent, Date.parse('2026-11-08T15:59:59Z'))).toBe('23:59');
    expect(chatTime(sent, Date.parse('2026-11-08T16:00:00Z'))).toBe('Yesterday');
    expect(chatTime('2026-11-08T16:01:00Z', Date.parse('2026-11-08T16:02:00Z'))).toBe('00:01');
  });
  it('uses Yesterday across month/year boundaries and unambiguous older dates across years', () => {
    expect(chatTime('2026-10-31T15:00:00Z', Date.parse('2026-10-31T16:00:00Z'))).toBe('Yesterday');
    expect(chatTime('2025-12-31T15:00:00Z', Date.parse('2025-12-31T16:00:00Z'))).toBe('Yesterday');
    expect(chatTime('2025-12-30T00:00:00Z', Date.parse('2026-01-01T00:00:00Z'))).toBe(
      '30 Dec 2025',
    );
    expect(chatTime('2026-11-06T06:12:00Z', Date.parse('2026-11-08T00:00:00Z'))).toBe('Fri');
    expect(chatTime('2026-10-01T00:00:00Z', Date.parse('2026-11-08T00:00:00Z'))).toBe('1 Oct 2026');
  });
  it('preserves actual absolute timestamp presentation and treats future dates honestly', () => {
    expect(absoluteChatTime('2026-11-08T06:12:00Z')).toBe('8 Nov 2026, 2:12 pm');
    expect(chatTime('2026-11-10T06:12:00Z', Date.parse('2026-11-08T00:00:00Z'))).toBe(
      '10 Nov 2026',
    );
  });
});
