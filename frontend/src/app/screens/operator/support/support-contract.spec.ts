import { convertToParamMap } from '@angular/router';
import { describe, expect, it } from 'vitest';
import {
  isSupportCase,
  isSupportHistory,
  isSupportInbox,
  isSupportReceipt,
  statusText,
  topicText,
  supportStatuses,
  supportTopics,
} from './support-contract';
import { supportRoute } from './support-route';
import {
  supportCase,
  supportHistory,
  supportInbox,
  supportReceipt,
  supportSummary,
} from './support.fixtures';

describe('operator support actual metadata/private/history boundary', () => {
  it('accepts raw literal content/null details and current-page semantics without snapshot invention', () => {
    expect(isSupportCase(supportCase)).toBe(true);
    expect(isSupportCase({ ...supportCase, details: '' })).toBe(true);
    expect(isSupportCase({ ...supportCase, details: undefined })).toBe(true);
    expect(isSupportInbox(supportInbox)).toBe(true);
    expect(isSupportInbox({ ...supportInbox, status_semantics: undefined })).toBe(true);
    expect(
      isSupportInbox({
        ...supportInbox,
        cases: [{ ...supportSummary, changed_at: '2026-11-03T04:00:00Z' }],
      }),
    ).toBe(true);
    expect(isSupportInbox({ ...supportInbox, cases: [] })).toBe(true);
    expect(isSupportHistory(supportHistory)).toBe(true);
    expect(isSupportHistory({ ...supportHistory, revisions: [] })).toBe(true);
    for (const value of supportStatuses) expect(statusText(value)).not.toBe('');
    for (const value of supportTopics) expect(topicText(value)).not.toBe('');
  });
  it('rejects a private body smuggled into metadata and malformed actual records', () => {
    for (const value of [
      null,
      {},
      { ...supportInbox, metadata_anchor: 'bad' },
      { ...supportInbox, status_semantics: 'snapshot' },
      { ...supportInbox, cases: [{ ...supportSummary, message: 'private' }] },
      { ...supportInbox, cases: [supportSummary, supportSummary] },
      { ...supportInbox, cases: [{ ...supportSummary, actor_id: 'bad' }] },
      { ...supportInbox, cases: [{ ...supportSummary, received_at: '2026-11-04T04:00:00Z' }] },
      { ...supportInbox, cases: Array.from({ length: 51 }, () => supportSummary) },
      { ...supportInbox, next_cursor: '' },
    ])
      expect(isSupportInbox(value)).toBe(false);
    for (const value of [
      { ...supportCase, actor_id: 5 },
      { ...supportCase, message: 5 },
      { ...supportCase, reply_address: 5 },
      { ...supportCase, details: 5 },
      { ...supportCase, topic: 'priority' },
      { ...supportCase, receipt: { ...supportReceipt, version: 0 } },
      { ...supportCase, reply: 'invented' },
    ])
      expect(isSupportCase(value)).toBe(false);
    for (const value of [
      { ...supportReceipt, case_id: 'bad' },
      { ...supportReceipt, status: 'approved' },
      { ...supportReceipt, version: 1.5 },
      { ...supportReceipt, changed_at: '2026-10-01T04:00:00Z' },
    ])
      expect(isSupportReceipt(value)).toBe(false);
  });
  it('preserves raw null history provenance and enforces bounded descending versions', () => {
    const first = supportHistory.revisions.find((row) => row.version === 1);
    expect(first?.changed_by_id).toBeNull();
    expect(first?.operator_access_version).toBeNull();
    for (const value of [
      { ...supportHistory, anchor_version: 0 },
      { ...supportHistory, next_cursor: '' },
      {
        ...supportHistory,
        revisions: [
          {
            version: 4,
            status: 'received',
            changed_at: supportReceipt.changed_at,
            changed_by_id: null,
            operator_access_version: null,
          },
        ],
      },
      { ...supportHistory, revisions: [...supportHistory.revisions, ...supportHistory.revisions] },
      { ...supportHistory, revisions: [{ ...first, version: 1, changed_by_id: 'bad' }] },
      { ...supportHistory, revisions: Array.from({ length: 51 }, () => first) },
    ])
      expect(isSupportHistory(value)).toBe(false);
  });
  it('maps exact real filters and rejects incompatible owner/cursor/time/enum inputs', () => {
    const state = supportRoute(
      convertToParamMap({
        case: supportReceipt.case_id,
        case_id: supportReceipt.case_id,
        actor_id: '00000000-0000-4000-8000-000000000073',
        topic: 'other',
        status: 'resolved',
        anonymous: 'false',
        received_from: '2026-11-01T00:00:00Z',
        received_before: '2026-11-02T00:00:00Z',
        cursor: 'opaque',
        history: 'open',
        history_cursor: 'older',
      }),
    );
    expect(state.filterError).toBeNull();
    expect(state.caseError).toBeNull();
    expect(state.historyError).toBeNull();
    expect(state.filters.anonymous).toBe(false);
    expect(state.historyOpen).toBe(true);
    for (const params of [
      { actor_id: 'bad' },
      { case_id: 'bad' },
      { topic: 'urgent' },
      { status: 'approved' },
      { anonymous: 'yes' },
      { actor_id: supportReceipt.case_id, anonymous: 'true' },
      { received_from: '2026-11-01' },
      { received_from: '2026-11-02T00:00:00Z', received_before: '2026-11-01T00:00:00Z' },
      { cursor: '' },
      { cursor: 'x'.repeat(1025) },
    ])
      expect(supportRoute(convertToParamMap(params)).filterError).not.toBeNull();
    expect(supportRoute(convertToParamMap({ case: 'bad' })).caseError).not.toBeNull();
    expect(supportRoute(convertToParamMap({ history_cursor: '' })).historyError).not.toBeNull();
    expect(supportRoute(convertToParamMap({})).historyOpen).toBe(false);
  });
});
