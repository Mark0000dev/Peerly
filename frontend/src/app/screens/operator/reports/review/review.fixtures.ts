import type { Api } from '../../../../api.generated';
import { operatorIdentity } from '../../operator.fixtures';
import { reportDetail, reportId, storedOrigin } from '../../operator-reports.fixtures';

export function revision(version: number): Api['schemas']['ReportReviewResponse'] {
  return {
    ...storedOrigin,
    id: `b1111111-1111-4111-8111-${String(version).padStart(12, '0')}`,
    report_id: reportId,
    version,
    previous_version: version === 1 ? null : version - 1,
    action: 'dismiss',
    reason: 'Retained private reason.\nSecond line.',
    operator_id: operatorIdentity.account_id,
    operator_access_version: 1,
    actor_session_id: 'b2222222-2222-4222-8222-222222222222',
    event_id: 'b3333333-3333-4333-8333-333333333333',
    reviewed_at: '2026-11-08T06:20:00Z',
  };
}
export const emptyHistory = {
  report_id: reportId,
  kind: reportDetail.report.kind,
  reporter_id: reportDetail.report.reporter_id,
  target_id: reportDetail.report.target_id,
  context_id: reportDetail.report.context_id,
  current: null,
  revisions: [],
  anchor_version: 0,
  next_cursor: null,
} as const satisfies Api['schemas']['ReportReviewHistoryResponse'];
export const anchoredHistory = {
  ...emptyHistory,
  current: revision(52),
  revisions: Array.from({ length: 50 }, (_, index) => revision(51 - index)),
  anchor_version: 51,
  next_cursor: 'anchored-review-page-two',
} as const satisfies Api['schemas']['ReportReviewHistoryResponse'];
export const earlierHistory = {
  ...anchoredHistory,
  revisions: [revision(1)],
  next_cursor: null,
} as const satisfies Api['schemas']['ReportReviewHistoryResponse'];
