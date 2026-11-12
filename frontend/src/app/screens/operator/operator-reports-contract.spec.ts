import { describe, expect, it } from 'vitest';
import { convertToParamMap } from '@angular/router';
import { eventRoute, reportRoute } from './operator-reports-route';
import { isAudit, isEvent, isEvents, isReport, isReports } from './operator-reports-contract';
import {
  absentOrigin,
  eventId,
  eventPage,
  reportDetail,
  reportId,
  reportPage,
  retainedAudit,
  retainedEvent,
  storedOrigin,
} from './operator-reports.fixtures';

describe('M02/M06/M07 retained records response and URL boundaries', () => {
  it('accepts actual support and notification metadata without inventing a verification action', () => {
    for (const [kind, sourceKind] of [
      ['report.reviewed', 'report_review_revision'],
      ['triage.submitted', 'report_triage_submission'],
      ['photo.reviewed', 'photo_review_revision'],
      ['support.received', 'support_case_revision'],
      ['support.status_changed', 'support_case_revision'],
      ['notification_preference.changed', 'notification_preference_revision'],
    ] as const) {
      const event = {
        ...retainedEvent,
        kind,
        sources: [{ ...retainedEvent.sources[0], kind: sourceKind, version: 1 }],
      };
      expect(isEvent(event)).toBe(true);
      expect(isEvent({ ...event, kind: 'support.invented' })).toBe(false);
    }
    for (const action of ['read_support_case', 'search_support_cases'] as const) {
      const audit = {
        ...retainedAudit,
        action,
        outcome: action === 'search_support_cases' ? 'search' : 'read',
        query_fingerprinted: action === 'search_support_cases',
        requested_kind: 'support_case',
        requested_id: action === 'search_support_cases' ? null : reportId,
        results: [{ kind: 'support_case', id: reportId }],
      };
      expect(isAudit(audit)).toBe(true);
      expect(isAudit({ ...audit, action: 'verify_membership' })).toBe(false);
    }
  });

  it('validates actual message-image context and rejects cross-kind or malformed references', () => {
    const context = {
      kind: 'message_image',
      id: reportDetail.context.id,
      reporter_id: reportDetail.report.reporter_id,
      target_id: reportDetail.report.target_id,
      conversation_id: reportId,
      message_id: eventId,
      client_message_id: retainedAudit.id,
      image_id: reportId,
      image_version: 1,
      image_attempt_id: eventId,
      message_sent_at: reportDetail.report.submitted_at,
      issued_at: reportDetail.context.issued_at,
      origin: storedOrigin,
    };
    const image = {
      ...reportDetail,
      report: { ...reportDetail.report, kind: 'message_image' },
      context,
    };
    expect(isReport(image)).toBe(true);
    expect(isReport({ ...image, report: reportDetail.report })).toBe(false);
    for (const field of [
      'conversation_id',
      'message_id',
      'client_message_id',
      'image_id',
      'image_attempt_id',
    ])
      expect(isReport({ ...image, context: { ...context, [field]: 'invalid' } })).toBe(false);
    expect(isReport({ ...image, context: { ...context, image_version: 0 } })).toBe(false);
    expect(isReport({ ...image, context: { ...context, message_sent_at: 'invalid' } })).toBe(false);
  });
  it('accepts retained comments literally and missing historical submission without reconstruction', () => {
    expect(isReport(reportDetail)).toBe(true);
    expect(isReport({ ...reportDetail, comment: null, submission: null })).toBe(true);
    expect(
      isReport({
        ...reportDetail,
        context: {
          ...reportDetail.context,
          goal_id: reportId,
          goal_version: 1,
          help_version: null,
        },
      }),
    ).toBe(true);
    expect(isReports(reportPage)).toBe(true);
    expect(isReports({ ...reportPage, reports: [], next_cursor: null })).toBe(true);
    expect(isEvents(eventPage)).toBe(true);
    expect(isEvents({ ...eventPage, events: [], next_cursor: null, pagination: undefined })).toBe(
      true,
    );
    expect(
      isEvent({
        ...retainedEvent,
        schema_version: undefined,
        origin: absentOrigin,
        initiator_account_id: reportId,
      }),
    ).toBe(true);
    expect(isAudit(retainedAudit)).toBe(true);
    expect(
      isAudit({
        ...retainedAudit,
        requested_kind: null,
        requested_id: null,
        requested_media_owner_id: reportId,
        requested_media_attempt_id: eventId,
        actual_source_upload_id: reportId,
        requested_media_kind: 'display',
      }),
    ).toBe(true);
    expect(isAudit({ ...retainedAudit, requested_media_kind: 'original' })).toBe(true);
  });
  it('rejects each missing required nested field and incompatible retained relationship', () => {
    for (const [guard, value] of [
      [isReports, reportPage],
      [isReport, reportDetail],
      [isEvent, retainedEvent],
      [isEvents, eventPage],
      [isAudit, retainedAudit],
    ] as const) {
      expect(guard(null)).toBe(false);
      for (const key of Object.keys(value)) {
        if (key !== 'schema_version' && key !== 'pagination')
          expect(guard({ ...value, [key]: undefined }), key).toBe(false);
      }
    }
    for (const key of Object.keys(reportDetail.report))
      expect(
        isReports({ ...reportPage, reports: [{ ...reportDetail.report, [key]: undefined }] }),
      ).toBe(false);
    for (const key of Object.keys(reportDetail.context))
      expect(
        isReport({ ...reportDetail, context: { ...reportDetail.context, [key]: undefined } }),
      ).toBe(false);
    for (const key of Object.keys(reportDetail.submission))
      expect(
        isReport({ ...reportDetail, submission: { ...reportDetail.submission, [key]: undefined } }),
      ).toBe(false);
    for (const key of ['id', 'reporter_id', 'target_id'])
      expect(
        isReport({ ...reportDetail, context: { ...reportDetail.context, [key]: eventId } }),
      ).toBe(false);
    for (const key of ['report_id', 'reporter_id'])
      expect(
        isReport({ ...reportDetail, submission: { ...reportDetail.submission, [key]: eventId } }),
      ).toBe(false);
    for (const key of Object.keys(storedOrigin))
      expect(isEvent({ ...retainedEvent, origin: { ...storedOrigin, [key]: undefined } })).toBe(
        false,
      );
    for (const key of Object.keys(retainedEvent.sources[0]))
      expect(
        isEvent({ ...retainedEvent, sources: [{ ...retainedEvent.sources[0], [key]: undefined }] }),
      ).toBe(false);
    for (const key of Object.keys(retainedEvent.facts))
      expect(
        isEvent({ ...retainedEvent, facts: { ...retainedEvent.facts, [key]: undefined } }),
      ).toBe(false);
    for (const key of ['kind', 'id'])
      expect(
        isAudit({ ...retainedAudit, results: [{ ...retainedAudit.results[0], [key]: undefined }] }),
      ).toBe(false);
    expect(
      isReports({ ...reportPage, reports: Array.from({ length: 51 }, () => reportDetail.report) }),
    ).toBe(false);
    expect(isEvent({ ...retainedEvent, sources: [] })).toBe(false);
    expect(
      isEvent({
        ...retainedEvent,
        sources: Array.from({ length: 3 }, () => retainedEvent.sources[0]),
      }),
    ).toBe(false);
    expect(isEvent({ ...retainedEvent, schema_version: 2 })).toBe(false);
    expect(isEvents({ ...eventPage, pagination: 'all_telemetry' })).toBe(false);
    expect(isEvent({ ...retainedEvent, origin: { ...storedOrigin, trace_id: 'BAD' } })).toBe(false);
    expect(isEvent({ ...retainedEvent, origin: { ...storedOrigin, span_id: 'BAD' } })).toBe(false);
    expect(
      isReport({ ...reportDetail, context: { ...reportDetail.context, photo_version: 0 } }),
    ).toBe(false);
    expect(
      isReport({ ...reportDetail, context: { ...reportDetail.context, profile_version: 1.5 } }),
    ).toBe(false);
  });
  it('validates report filters, independent cursors and actual selected IDs', () => {
    expect(reportRoute(convertToParamMap({})).error).toBeNull();
    expect(
      reportRoute(
        convertToParamMap({
          category: 'spam',
          reporter_id: reportId,
          target_id: eventId,
          context_id: reportId,
          report: reportId,
          submitted_from: '2026-01-01T00:00:00Z',
          submitted_before: '2026-02-01T00:00:00Z',
          reports_cursor: 'opaque',
        }),
      ).filters.cursor,
    ).toBe('opaque');
    for (const params of [
      { reporter_id: 'bad' },
      { category: 'invented' },
      { report: 'bad' },
      { submitted_from: '2026-01-01' },
      { submitted_before: 'bad' },
      { submitted_from: '2026-01-01T00:00:00Z', submitted_before: '2026-01-01T00:00:00Z' },
      { reports_cursor: '' },
      { reports_cursor: 'x'.repeat(1025) },
    ])
      expect(reportRoute(convertToParamMap(params)).error).not.toBeNull();
    expect(
      reportRoute(convertToParamMap({ events_cursor: 'unrelated', event: 'bad' })).error,
    ).toBeNull();
  });
  it('validates canonical event filters without granting URL-only audit access', () => {
    expect(eventRoute(convertToParamMap({})).error).toBeNull();
    expect(
      eventRoute(
        convertToParamMap({
          timeline: '1',
          event_kind: 'report.created',
          event_subject_account_id: reportId,
          event_http_request_id: eventId,
          event_action_id: reportId,
          event_trace_id: storedOrigin.trace_id,
          event_occurred_from: '2026-01-01T00:00:00Z',
          event_occurred_before: '2026-02-01T00:00:00Z',
          events_cursor: 'opaque',
          event: eventId,
          audit: reportId,
        }),
      ).opened,
    ).toBe(true);
    for (const params of [
      { event_subject_account_id: 'bad' },
      { audit: 'bad' },
      { event_kind: 'invented' },
      { event_trace_id: 'ABC' },
      { event_occurred_from: '2026-01-01' },
      { event_occurred_before: 'bad' },
      {
        event_occurred_from: '2026-01-01T00:00:00Z',
        event_occurred_before: '2026-01-01T00:00:00Z',
      },
      { events_cursor: '' },
      { events_cursor: 'x'.repeat(1025) },
    ])
      expect(eventRoute(convertToParamMap(params)).error).not.toBeNull();
    expect(
      eventRoute(convertToParamMap({ reports_cursor: 'unrelated', report: 'bad' })).error,
    ).toBeNull();
  });
  it('accepts actual head46 lifecycle source metadata without inventing a moderation action', () => {
    const event = {
      ...retainedEvent,
      kind: 'account.lifecycle_changed',
      sources: [
        {
          ...retainedEvent.sources[0],
          kind: 'account_lifecycle_revision',
          version: 1,
          operator_access_version: null,
        },
      ],
      facts: { ...retainedEvent.facts, operator_action: null, lifecycle_operation: 'ban' },
    };
    expect(isEvent(event)).toBe(true);
    expect(isEvent({ ...event, facts: { ...event.facts, lifecycle_operation: 'invented' } })).toBe(
      false,
    );
  });
});
