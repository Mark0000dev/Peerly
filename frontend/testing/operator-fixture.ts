import type { Page } from '@playwright/test';
import { expect } from './visual';

export type OperatorCohort = Readonly<{
  readonly operatorId: string;
  readonly replacementId: string;
  readonly targets: Readonly<{
    readonly active: string;
    readonly hidden: string;
    readonly banned: string;
    readonly deleted: string;
    readonly nullable: string;
  }>;
  readonly conversation: Readonly<{
    readonly id: string;
    readonly requestId: string;
    readonly relationshipId: string;
    readonly lowId: string;
    readonly highId: string;
  }> | null;
  readonly reports: Readonly<{
    readonly reportId: string;
    readonly legacyReportId: string;
    readonly reportEventId: string;
    readonly reporterId: string;
    readonly targetId: string;
    readonly contextId: string;
  }> | null;
  readonly support: Readonly<{
    readonly caseId: string;
    readonly anonymousId: string;
    readonly retainedId: string;
    readonly missingId: string;
    readonly receivedFrom: string;
    readonly receivedBefore: string;
  }> | null;
  readonly replaceActor: () => Promise<void>;
}>;

export async function prepareOperatorFixture(
  page: Readonly<Page>,
  scenario:
    | 'support'
    | 'support-references'
    | 'support-status'
    | 'support-unknown'
    | 'support-conflict'
    | 'support-empty'
    | 'support-revocation'
    | 'support-replacement'
    | 'authorized'
    | 'denied'
    | 'revocation'
    | 'replacement'
    | 'history'
    | 'history-empty'
    | 'history-revocation'
    | 'history-replacement'
    | 'academic'
    | 'academic-empty'
    | 'academic-revocation'
    | 'academic-replacement'
    | 'reports'
    | 'reports-review'
    | 'reports-empty'
    | 'reports-revocation'
    | 'reports-replacement'
    | 'reports-events'
    | 'reports-reflow'
    | 'conversations'
    | 'conversations-empty'
    | 'conversations-revocation'
    | 'conversations-replacement',
  project: string,
): Promise<OperatorCohort> {
  if (!/^(chromium-mobile|webkit-mobile|chromium-desktop)$/.test(project))
    throw new Error('Invalid controlled operator project');
  const response = await page.request.post('http://127.0.0.1:8768/__fixture/operator', {
    data: { namespace: `operator/${scenario}/${project}` },
  });
  expect(response.status()).toBe(201);
  const value: unknown = await response.json();
  if (
    typeof value !== 'object' ||
    value === null ||
    !('origin' in value) ||
    typeof value.origin !== 'string' ||
    !/^https:\/\/127\.0\.0\.1:[0-9]{4,5}$/.test(value.origin) ||
    !('cookie_name' in value) ||
    typeof value.cookie_name !== 'string' ||
    !/^__Host-[A-Za-z0-9_-]{1,48}$/.test(value.cookie_name) ||
    !('viewer_session' in value) ||
    typeof value.viewer_session !== 'string' ||
    !/^[A-Za-z0-9_-]{43}$/.test(value.viewer_session) ||
    !('replacement_session' in value) ||
    typeof value.replacement_session !== 'string' ||
    !/^[A-Za-z0-9_-]{43}$/.test(value.replacement_session) ||
    !('viewer_id' in value) ||
    !id(value.viewer_id) ||
    !('replacement_id' in value) ||
    !id(value.replacement_id) ||
    !('active_id' in value) ||
    !id(value.active_id) ||
    !('hidden_id' in value) ||
    !id(value.hidden_id) ||
    !('banned_id' in value) ||
    !id(value.banned_id) ||
    !('deleted_id' in value) ||
    !id(value.deleted_id) ||
    !('nullable_id' in value) ||
    !id(value.nullable_id)
  )
    throw new Error('Invalid controlled operator cohort');
  const support = readSupportSources(value);
  if (scenario.startsWith('support') && support === null)
    throw new Error('Missing controlled support sources');
  const conversation = readConversationSources(value);
  if (scenario.startsWith('conversations') && conversation === null)
    throw new Error('Missing controlled conversation sources');
  const reports = readReportSources(value);
  if (scenario.startsWith('reports') && scenario !== 'reports-empty' && reports === null)
    throw new Error('Missing controlled report sources');
  const cookie = {
    name: value.cookie_name,
    url: value.origin,
    httpOnly: true,
    secure: true,
    sameSite: 'Lax',
  } as const;
  await page.context().addCookies([{ ...cookie, value: value.viewer_session }]);
  const replacement = value.replacement_session;
  return {
    operatorId: value.viewer_id,
    replacementId: value.replacement_id,
    targets: {
      active: value.active_id,
      hidden: value.hidden_id,
      banned: value.banned_id,
      deleted: value.deleted_id,
      nullable: value.nullable_id,
    },
    reports,
    conversation,
    support,
    replaceActor: async () => {
      // Synthetic credential remains in Node only; never page JS, logs or browser storage.
      await page.context().addCookies([{ ...cookie, value: replacement }]);
    },
  };
}
function id(value: unknown): value is string {
  return typeof value === 'string' && /^[a-f0-9-]{36}$/.test(value);
}

export async function changeOperatorFixtureGrant(
  page: Readonly<Page>,
  operatorId: string,
  active: boolean,
): Promise<void> {
  if (!id(operatorId)) throw new Error('Invalid controlled operator');
  const response = await page.request.post(
    `http://127.0.0.1:8768/__fixture/operator/${operatorId}/grant/${String(active)}`,
  );
  expect(response.status()).toBe(204);
}

export async function readOperatorFixtureAudit(
  page: Readonly<Page>,
  operatorId: string,
): Promise<Readonly<{ readonly audits: number; readonly linkedEvents: number }>> {
  if (!id(operatorId)) throw new Error('Invalid controlled operator');
  const response = await page.request.get(
    `http://127.0.0.1:8768/__fixture/operator/${operatorId}/audit`,
  );
  expect(response.status()).toBe(200);
  const value: unknown = await response.json();
  if (
    typeof value !== 'object' ||
    value === null ||
    !('audits' in value) ||
    typeof value.audits !== 'number' ||
    !Number.isInteger(value.audits) ||
    value.audits < 0 ||
    !('linked_events' in value) ||
    typeof value.linked_events !== 'number' ||
    value.linked_events !== value.audits
  )
    throw new Error('Controlled audit/source linkage invalid');
  return { audits: value.audits, linkedEvents: value.linked_events };
}

function readReportSources(value: Readonly<object>): OperatorCohort['reports'] {
  if (!('report_id' in value)) return null;
  if (
    !id(value.report_id) ||
    !('legacy_report_id' in value) ||
    !id(value.legacy_report_id) ||
    !('report_event_id' in value) ||
    !id(value.report_event_id) ||
    !('reporter_id' in value) ||
    !id(value.reporter_id) ||
    !('report_target_id' in value) ||
    !id(value.report_target_id) ||
    !('report_context_id' in value) ||
    !id(value.report_context_id)
  )
    throw new Error('Invalid controlled report sources');
  return {
    reportId: value.report_id,
    legacyReportId: value.legacy_report_id,
    reportEventId: value.report_event_id,
    reporterId: value.reporter_id,
    targetId: value.report_target_id,
    contextId: value.report_context_id,
  };
}

function readConversationSources(value: Readonly<object>): OperatorCohort['conversation'] {
  if (!('conversation_id' in value)) return null;
  if (
    !id(value.conversation_id) ||
    !('conversation_request_id' in value) ||
    !id(value.conversation_request_id) ||
    !('conversation_relationship_id' in value) ||
    !id(value.conversation_relationship_id) ||
    !('conversation_low_id' in value) ||
    !id(value.conversation_low_id) ||
    !('conversation_high_id' in value) ||
    !id(value.conversation_high_id)
  )
    throw new Error('Invalid controlled conversation sources');
  return {
    id: value.conversation_id,
    requestId: value.conversation_request_id,
    relationshipId: value.conversation_relationship_id,
    lowId: value.conversation_low_id,
    highId: value.conversation_high_id,
  };
}

export async function readOperatorStudentReadCounts(
  page: Readonly<Page>,
  operatorId: string,
): Promise<Readonly<{ readonly revisions: number; readonly positions: number }>> {
  if (!id(operatorId)) throw new Error('Invalid controlled operator');
  const response = await page.request.get(
    `http://127.0.0.1:8768/__fixture/operator/${operatorId}/audit`,
  );
  expect(response.status()).toBe(200);
  const value: unknown = await response.json();
  if (
    typeof value !== 'object' ||
    value === null ||
    !('student_reads' in value) ||
    typeof value.student_reads !== 'number' ||
    !Number.isInteger(value.student_reads) ||
    value.student_reads < 0 ||
    !('student_read_positions' in value) ||
    typeof value.student_read_positions !== 'number' ||
    !Number.isInteger(value.student_read_positions) ||
    value.student_read_positions < 0
  )
    throw new Error('Invalid controlled student read counters');
  return { revisions: value.student_reads, positions: value.student_read_positions };
}

function readSupportSources(value: Readonly<object>): OperatorCohort['support'] {
  if (!('support_case_id' in value)) return null;
  if (
    !id(value.support_case_id) ||
    !('support_anonymous_id' in value) ||
    !id(value.support_anonymous_id) ||
    !('support_retained_id' in value) ||
    !id(value.support_retained_id) ||
    !('support_missing_id' in value) ||
    !id(value.support_missing_id) ||
    !('support_received_from' in value) ||
    typeof value.support_received_from !== 'string' ||
    !Number.isFinite(Date.parse(value.support_received_from)) ||
    !('support_received_before' in value) ||
    typeof value.support_received_before !== 'string' ||
    !Number.isFinite(Date.parse(value.support_received_before)) ||
    Date.parse(value.support_received_from) >= Date.parse(value.support_received_before)
  )
    throw new Error('Invalid controlled support sources');
  return {
    caseId: value.support_case_id,
    anonymousId: value.support_anonymous_id,
    retainedId: value.support_retained_id,
    missingId: value.support_missing_id,
    receivedFrom: value.support_received_from,
    receivedBefore: value.support_received_before,
  };
}
