import { describe, expect, it } from 'vitest';
import {
  isRequest,
  isRequestDetail,
  isRequestPage,
  isRequestReceipt,
  isViewedReceipt,
  peerName,
  requestBox,
  requestView,
  requestReason,
  undoRemaining,
  sentWhen,
  expiresWhen,
} from './requests-contract';
import { request, detail, page, receipt, viewed, declined } from './requests.fixtures';

describe('Requests actual nested boundaries', () => {
  for (const [label, accept, valid] of [
    ['summary', isRequest, request],
    ['detail', isRequestDetail, detail],
    ['page', isRequestPage, page],
    ['decision', isRequestReceipt, receipt],
    ['viewed', isViewedReceipt, viewed],
  ] as const) {
    it(`${label} accepts actual DTO and rejects non-record payloads`, () => {
      expect(accept(valid)).toBe(true);
      for (const invalid of [null, undefined, 0, '', [], {}]) expect(accept(invalid)).toBe(false);
    });
    for (const key of Object.keys(valid)) {
      it(`${label} rejects missing or malformed ${key}`, () => {
        const without = Object.fromEntries(
          Object.entries(valid).filter((entry: readonly [string, unknown]) => entry[0] !== key),
        );
        expect(accept(without)).toBe(false);
        expect(accept({ ...valid, [key]: { malformed: true } })).toBe(false);
      });
    }
  }
  it('rejects malformed peer masking and capabilities without guessing authority', () => {
    for (const value of [
      null,
      {},
      { ...request.peer, person_id: 3 },
      { ...request.peer, display_name: 2 },
      { ...request.peer, photo_version: -1 },
      { ...request.peer, state: 'hidden' },
      { ...request.peer, state: 'deleted' },
      { ...request.peer, state: 'unavailable', display_name: null },
    ])
      expect(isRequest({ ...request, peer: value })).toBe(false);
    expect(
      isRequest({
        ...request,
        peer: { ...request.peer, state: 'deleted', display_name: null, photo_version: null },
      }),
    ).toBe(true);
    for (const key of Object.keys(request.capabilities))
      expect(
        isRequest({ ...request, capabilities: { ...request.capabilities, [key]: null } }),
      ).toBe(false);
  });
  it('validates every retained goal/help field instead of treating context as a blob', () => {
    const goal = detail.context.sender_goal;
    const help = detail.context.recipient_help;
    if (goal === null || help === null) throw new Error('Missing synthetic academic context');
    for (const key of Object.keys(goal))
      expect(
        isRequestDetail({
          ...detail,
          context: { ...detail.context, sender_goal: { ...goal, [key]: [] } },
        }),
      ).toBe(false);
    for (const key of Object.keys(help))
      expect(
        isRequestDetail({
          ...detail,
          context: { ...detail.context, recipient_help: { ...help, [key]: [] } },
        }),
      ).toBe(false);
    expect(
      isRequestDetail({
        ...detail,
        context: { ...detail.context, sender_help: help, recipient_goal: goal },
      }),
    ).toBe(true);
    expect(isRequestDetail({ ...detail, context: { ...detail.context, mode: 'offer_help' } })).toBe(
      false,
    );
    expect(
      isRequestDetail({ ...detail, context: { ...detail.context, sender_goal: 'goal' } }),
    ).toBe(false);
    expect(
      isRequestDetail({ ...detail, context: { ...detail.context, recipient_help: 'help' } }),
    ).toBe(false);
  });
  it('rejects duplicate or oversized pages, noninteger counters and invalid dates', () => {
    expect(isRequest({ ...request, state: ['pending'] })).toBe(false);
    expect(isRequestReceipt({ ...receipt, outcome: ['accepted'] })).toBe(false);
    expect(isRequestPage({ ...page, requests: [request, request] })).toBe(false);
    expect(
      isRequestPage({
        ...page,
        requests: Array.from({ length: 21 }, (_, i) => ({ ...request, request_id: String(i) })),
      }),
    ).toBe(false);
    for (const value of [
      -1,
      1.1,
      Number.NaN,
      Number.POSITIVE_INFINITY,
      Number.MAX_SAFE_INTEGER + 1,
    ]) {
      expect(isRequest({ ...request, version: value })).toBe(false);
      expect(isRequestPage({ ...page, daily_send_limit: value })).toBe(false);
    }
    for (const field of ['sent_at', 'expires_at', 'observed_at', 'undo_until', 'cooldown_until'])
      expect(isRequest({ ...request, [field]: 'not-a-date' })).toBe(false);
    expect(isRequest({ ...request, version: 0 })).toBe(false);
    expect(isRequestDetail({ ...detail, disclosed_version: 0 })).toBe(false);
    expect(isRequestReceipt({ ...receipt, version: 0 })).toBe(false);
    expect(isViewedReceipt({ ...viewed, stored_version: 0 })).toBe(false);
  });
  it('uses URL semantics, honest masked names and grounded modes', () => {
    expect(requestBox(null)).toBe('received');
    expect(requestBox('sent')).toBe('sent');
    expect(requestBox('invalid')).toBe('received');
    expect(requestView('history', 'sent')).toBe('history');
    expect(requestView('recently_declined', 'received')).toBe('recently_declined');
    expect(requestView('recently_declined', 'sent')).toBe('active');
    expect(requestView(null, 'received')).toBe('active');
    expect(peerName(request)).toBe('Maya Lim');
    expect(peerName({ ...request, peer: { ...request.peer, state: 'deleted' } })).toBe(
      'Deleted account',
    );
    expect(peerName({ ...request, peer: { ...request.peer, state: 'unavailable' } })).toBe(
      'Profile unavailable',
    );
    expect(peerName({ ...request, peer: { ...request.peer, display_name: null } })).toBe(
      'Profile unavailable',
    );
    expect(requestReason(request)).toBe('Would like help with SQL');
    expect(requestReason({ ...request, mode: 'offer_help' })).toBe('Offers help with SQL');
    expect(requestReason({ ...request, mode: 'study_together' })).toBe(
      'Would like to study SQL together',
    );
  });
  it('computes only the remaining observed server window, never a fresh ten seconds', () => {
    expect(undoRemaining(request, 100, 100)).toBe(0);
    expect(undoRemaining({ ...declined, undo_until: null }, 100, 100)).toBe(0);
    expect(undoRemaining(declined, 100, 100)).toBe(10);
    expect(undoRemaining(declined, 100, 1100)).toBe(9);
    expect(undoRemaining(declined, 100, 10100)).toBe(0);
    expect(undoRemaining(declined, 100, 20100)).toBe(0);
    expect(undoRemaining(declined, 100, 0)).toBe(10);
  });
  it('formats observed human times without exposing opaque IDs or moving server deadlines', () => {
    expect(sentWhen(request)).toBe('14 h ago');
    expect(sentWhen({ ...request, sent_at: request.observed_at })).toBe('Just now');
    expect(sentWhen({ ...request, sent_at: '2026-11-07T23:59:00Z' })).toBe('1 min ago');
    expect(sentWhen({ ...request, sent_at: '2026-11-07T00:00:00Z' })).toBe('1 day ago');
    expect(sentWhen({ ...request, sent_at: '2026-11-06T00:00:00Z' })).toBe('2 days ago');
    expect(expiresWhen(request)).toBe('up to 7 more days');
    expect(expiresWhen({ ...request, expires_at: '2026-11-09T00:00:00Z' })).toBe(
      'up to 1 more day',
    );
    expect(expiresWhen({ ...request, expires_at: request.observed_at })).toBe(
      'Check current availability',
    );
  });
});
