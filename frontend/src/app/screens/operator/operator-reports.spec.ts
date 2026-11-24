import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import type { TestRequest } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { TuiRoot } from '@taiga-ui/core';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { userEvent } from 'vitest/browser';
import { appConfig } from '../../app.config';
import { OperatorReports } from './operator-reports';
import { emptyHistory } from './reports/review/review.fixtures';
import { operatorIdentity } from './operator.fixtures';
import {
  auditId,
  eventId,
  eventPage,
  reportDetail,
  reportId,
  reportPage,
  retainedAudit,
  retainedEvent,
  submissionEvent,
  submissionEventId,
} from './operator-reports.fixtures';

@Component({
  selector: 'operator-report-host',
  imports: [TuiRoot, OperatorReports],
  template: '<tui-root><app-operator-reports /></tui-root>',
})
class Host {}
@Component({ template: '' })
class Empty {}

describe('M02/M06/M07 real report investigation ownership', () => {
  let fixture: ComponentFixture<Host>;
  let backend: HttpTestingController;
  let client: QueryClient;
  let router: Router;
  beforeEach(async () => {
    client = new QueryClient({
      defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
    });
    TestBed.configureTestingModule({
      providers: [
        ...appConfig.providers,
        provideRouter([{ path: 'operator/reports', component: Empty }]),
        provideHttpClientTesting(),
        provideTanStackQuery(client),
      ],
    });
    router = TestBed.inject(Router);
    await router.navigateByUrl('/operator/reports');
    fixture = TestBed.createComponent(Host);
    backend = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });
  afterEach(() => {
    fixture.destroy();
    client.clear();
    backend.verify({ ignoreCancelled: true });
    TestBed.resetTestingModule();
    vi.restoreAllMocks();
  });
  function host(): HTMLElement {
    const value: unknown = fixture.nativeElement;
    if (!(value instanceof HTMLElement)) throw new Error('Missing report host');
    return value;
  }
  async function shown(text: string): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain(text);
    });
  }
  function click(label: string): void {
    const button = Array.from(host().querySelectorAll('button')).find(
      (value: Readonly<HTMLButtonElement>) =>
        value.getAttribute('aria-label') === label || value.textContent.trim() === label,
    );
    if (button === undefined) throw new Error(`Missing ${label}`);
    button.click();
    fixture.detectChanges();
  }
  async function buttonShown(label: string): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(
        Array.from(host().querySelectorAll('button')).some(
          (value: Readonly<HTMLButtonElement>) => value.getAttribute('aria-label') === label,
        ),
      ).toBe(true);
    });
  }
  function fill(id: string, value: string): void {
    const input = host().querySelector(`#${id}`);
    if (!(input instanceof HTMLInputElement)) throw new Error(`Missing ${id}`);
    input.setRangeText(value, 0, input.value.length);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
  }
  async function navigate(params: Readonly<Record<string, string>>): Promise<void> {
    await router.navigateByUrl(`/operator/reports?${new URLSearchParams(params).toString()}`);
    fixture.detectChanges();
  }
  async function request(path: string): Promise<TestRequest> {
    let found: TestRequest | undefined;
    await vi.waitFor(() => {
      fixture.detectChanges();
      found = backend.expectOne((value) => value.url.startsWith(`/api/v1/operator/${path}`));
    });
    if (found === undefined) throw new Error(`Missing request ${path}`);
    return found;
  }
  async function login(params: Readonly<Record<string, string>> = {}): Promise<void> {
    await navigate(params);
    backend.expectOne('/api/v1/me').flush(operatorIdentity);
    await shown('Find retained reports');
  }
  async function list(): Promise<void> {
    (await request('reports?')).flush(reportPage);
    await shown(reportId);
  }
  async function openEvent(): Promise<void> {
    click('Open canonical timeline');
    (await request('events?')).flush(eventPage);
    await buttonShown(`Inspect event ${eventId}`);
    click(`Inspect event ${eventId}`);
    (await request(`events/${eventId}`)).flush(retainedEvent);
    await shown('Stored facts');
  }
  it('keeps private comment absent from metadata until explicit detail, renders literal text and actual origins', async () => {
    backend.expectNone((value) => value.url.startsWith('/api/v1/operator'));
    await login();
    await list();
    expect(host().textContent).toContain('Anchored search');
    expect(host().textContent).not.toContain('Search anchor');
    expect(host().textContent).not.toContain(reportDetail.comment);
    backend.expectNone((value) => value.url.startsWith('/api/v1/operator/events'));
    click(`Inspect report ${reportId}`);
    (await request(`reports/${reportId}`)).flush(reportDetail);
    await shown(reportDetail.comment);
    expect(host().querySelector('script')).toBeNull();
    expect(host().textContent).toContain('Not recorded');
    click('Open submission event');
    (await request(`events/${submissionEventId}`)).flush(submissionEvent);
    await shown('Stored source references');
    backend.expectNone((value) => value.url.startsWith('/api/v1/operator/audits'));
    await openEvent();
    click(`Inspect audit ${auditId}`);
    (await request(`audits/${auditId}`)).flush(retainedAudit);
    await shown('Inspection of this audit is itself recorded');
    expect(router.url).toContain(`audit=${auditId}`);
    click('Close audit');
    click('Close event');
    click('Close report');
    await vi.waitFor(() => {
      expect(router.url).not.toContain('report=');
    });
  });
  it('shows missing legacy submission honestly and never fetches event details automatically', async () => {
    await login({ report: reportId });
    await list();
    (await request(`reports/${reportId}`)).flush({
      ...reportDetail,
      comment: null,
      submission: null,
    });
    await shown('Submission event and origin were not recorded');
    expect(host().textContent).toContain('No comment recorded');
    backend.expectNone((value) => value.url.startsWith('/api/v1/operator/events'));
  });
  it('rejects unrelated audit URL without a stored selected event source', async () => {
    await login({ audit: auditId });
    await list();
    await shown('Open an event with this stored operator-audit source reference');
    backend.expectNone((value) => value.url.startsWith('/api/v1/operator/audits'));
    await navigate({ event: eventId, audit: reportId });
    (await request(`events/${eventId}`)).flush(retainedEvent);
    await shown('Stored facts');
    backend.expectNone((value) => value.url.startsWith('/api/v1/operator/audits'));
  });
  it('keeps list and event cursors independent and resets report pagination on explicit filters', async () => {
    await login();
    await list();
    click('Next report page');
    const next = await request('reports?');
    expect(next.request.url).toContain('cursor=report-next');
    next.flush({ ...reportPage, reports: [], next_cursor: null });
    await shown('No retained reports');
    click('First page');
    await list();
    fill('report-target_id', 'bad');
    click('Search retained reports');
    await shown('IDs must be UUIDs');
    fill('report-target_id', reportDetail.report.target_id);
    click('Search retained reports');
    const filtered = await request('reports?');
    expect(filtered.request.url).toContain(reportDetail.report.target_id);
    filtered.flush(reportPage);
    await shown(reportId);
    expect(router.url).not.toContain('reports_cursor');
    await openEvent();
    click('Next event page');
    const events = await request('events?');
    expect(events.request.url).toContain('cursor=event-next');
    events.flush({ ...eventPage, events: [], next_cursor: null });
    await shown('No canonical events');
    click('First page');
    (await request('events?')).flush(eventPage);
    await buttonShown(`Inspect event ${eventId}`);
    fill('event-trace_id', 'bad');
    click('Search canonical events');
    await shown('32 lowercase');
    fill('event-trace_id', retainedEvent.origin.trace_id);
    click('Search canonical events');
    const filteredEvents = await request('events?');
    expect(filteredEvents.request.url).toContain(retainedEvent.origin.trace_id);
    filteredEvents.flush(eventPage);
    await buttonShown(`Inspect event ${eventId}`);
    click('Close canonical timeline');
  });
  it('keeps local 503 and404 detail failures separate from unrelated successful records and retries', async () => {
    await login({ report: reportId });
    (await request('reports?')).flush({}, { status: 503, statusText: 'Unavailable' });
    (await request(`reports/${reportId}`)).flush({}, { status: 404, statusText: 'Missing' });
    await shown('This retained report is unavailable');
    click('Retry report search');
    await list();
    click('Retry report record');
    (await request(`reports/${reportId}`)).flush(reportDetail);
    await shown(reportDetail.comment);
    await openEvent();
    click(`Inspect audit ${auditId}`);
    (await request(`audits/${auditId}`)).flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('This investigation record could not be loaded');
    click('Retry access audit');
    (await request(`audits/${auditId}`)).flush(retainedAudit);
    await shown('Stored result references');
    click('Refresh event page');
    (await request('events?')).flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('This investigation record could not be loaded');
    click('Retry event search');
    (await request('events?')).flush(eventPage);
    await buttonShown(`Inspect event ${eventId}`);
    await navigate({ event: reportId });
    (await request(`events/${reportId}`)).flush({}, { status: 404, statusText: 'Missing' });
    await shown('This stored investigation record is unavailable');
    click('Retry event record');
    (await request(`events/${reportId}`)).flush({ ...retainedEvent, id: reportId });
    await shown('Stored facts');
  });
  it('offers actual first-page recovery after signed cursor422 without hiding metadata errors', async () => {
    await login({ reports_cursor: 'old' });
    (await request('reports?')).flush({}, { status: 422, statusText: 'Bad cursor' });
    await shown('These filters or this cursor');
    click('First page');
    await list();
    click('Open canonical timeline');
    (await request('events?')).flush(eventPage);
    await buttonShown(`Inspect event ${eventId}`);
    click('Next event page');
    (await request('events?')).flush({}, { status: 422, statusText: 'Bad cursor' });
    await shown('These filters or this cursor');
    click('First page');
    (await request('events?')).flush(eventPage);
    await buttonShown(`Inspect event ${eventId}`);
    click('Refresh report page');
    await list();
  });
  it('retires pending siblings immediately after child403, and restores only with actual session/grant recheck', async () => {
    await login({ report: reportId, event: eventId });
    const pendingList = await request('reports?');
    const pendingReport = await request(`reports/${reportId}`);
    (await request(`events/${eventId}`)).flush(
      { code: 'operator_access_denied' },
      { status: 403, statusText: 'Denied' },
    );
    await shown('Operator access denied');
    expect(pendingList.cancelled).toBe(true);
    expect(pendingReport.cancelled).toBe(true);
    expect(host().textContent).not.toContain('Report record');
    click('Check operator access again');
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/me').flush(operatorIdentity);
    });
    await shown('Find retained reports');
    await list();
    (await request(`reports/${reportId}`)).flush(reportDetail);
    (await request(`events/${eventId}`)).flush(retainedEvent);
    await shown('Stored facts');
  });
  it('rechecks session on any child401 and prevents late private reveals', async () => {
    await login({ report: reportId });
    const sibling = await request('reports?');
    (await request(`reports/${reportId}`)).flush({}, { status: 401, statusText: 'Expired' });
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/me').flush({}, { status: 401, statusText: 'Expired' });
    });
    await shown('Sign in with your operator');
    expect(sibling.cancelled).toBe(true);
  });
  it('retains session error recovery and no private fetch before authenticated identity', async () => {
    backend.expectOne('/api/v1/me').flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('Your session could not be checked');
    click('Retry');
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/me').flush({}, { status: 401, statusText: 'Expired' });
    });
    await shown('Sign in with your operator');
    backend.expectNone((value) => value.url.startsWith('/api/v1/operator'));
  });
  it('validates selected IDs locally while preserving independent investigation state', async () => {
    await login({ report: 'bad', event: 'bad' });
    await shown('IDs must be UUIDs');
    backend.expectNone((value) => value.url.startsWith('/api/v1/operator'));
    const resets = host().querySelectorAll('button');
    const reset = Array.from(resets).find(
      (value: Readonly<HTMLButtonElement>) => value.textContent.trim() === 'Reset',
    );
    if (reset === undefined) throw new Error('Missing reset');
    reset.click();
    await list();
    await shown('Event, audit, account');
    click('Reset');
    await vi.waitFor(() => {
      expect(router.url).not.toContain('event=');
    });
  });
  it('resets actor-owned cursors before new actor queries and never carries previous private data', async () => {
    await login({ reports_cursor: 'signed-old', timeline: '1', events_cursor: 'events-old' });
    await list();
    (await request('events?')).flush(eventPage);
    await buttonShown(`Inspect event ${eventId}`);
    const checking = client.invalidateQueries({ queryKey: ['session'] });
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/me').flush({ ...operatorIdentity, account_id: auditId });
    });
    await checking;
    const freshReports = await request('reports?');
    expect(
      new URL(freshReports.request.url, 'https://peerly.test').searchParams.get('cursor'),
    ).toBeNull();
    freshReports.flush({ ...reportPage, reports: [], next_cursor: null });
    const freshEvents = await request('events?');
    expect(
      new URL(freshEvents.request.url, 'https://peerly.test').searchParams.get('cursor'),
    ).toBeNull();
    freshEvents.flush({ ...eventPage, events: [], next_cursor: null });
    await shown('No canonical events');
    expect(router.url).not.toContain('cursor');
    expect(host().textContent).not.toContain(reportId);
  });

  async function reviewWorkspace(): Promise<void> {
    await login({ report: reportId });
    await list();
    (await request(`reports/${reportId}`)).flush(reportDetail);
    await shown(reportDetail.comment);
    click('Human review');
    (await request(`reports/${reportId}/reviews`)).flush(emptyHistory);
    await shown('No dismiss or escalate decision is recorded.');
  }
  it('opens and closes the actual human review workspace without a write or extra inspection', async () => {
    await reviewWorkspace();
    click('Close human review');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('[aria-label="Human report review"]')).toBeNull();
    });
    expect(host().textContent).toContain(reportDetail.comment);
    backend.expectNone((value) => value.method !== 'GET');
    backend.expectNone((value) => value.url.startsWith('/api/v1/operator'));
  });
  it('keeps an unsaved private human decision until explicit discard when closing the workspace', async () => {
    await reviewWorkspace();
    const textarea = host().querySelector('textarea');
    if (!(textarea instanceof HTMLTextAreaElement)) throw new Error('Missing review reason');
    textarea.setRangeText('Unsent operator reason');
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
    click('Close human review');
    await shown('Discard unsaved changes?');
    click('Keep editing');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('[role="dialog"]')).toBeNull();
    });
    expect(host().querySelector('textarea')?.value).toBe('Unsent operator reason');
    click('Close human review');
    await shown('Discard unsaved changes?');
    click('Discard changes');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('[aria-label="Human report review"]')).toBeNull();
    });
    backend.expectNone((value) => value.method !== 'GET');
  });
  it('retires the old human review workspace when a different report is selected without sending a decision', async () => {
    await reviewWorkspace();
    await navigate({ report: auditId });
    const read = await request(`reports/${auditId}`);
    read.flush({ ...reportDetail, report: { ...reportDetail.report, id: auditId } });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('[aria-label="Human report review"]')).toBeNull();
    });
    backend.expectNone((value) => value.method !== 'GET');
  });
  it('applies an explicit category filter and removes all-category and page cursor from a new search', async () => {
    await login({ reports_cursor: 'old-page' });
    await list();
    const select = host().querySelector('#report-category');
    if (!(select instanceof HTMLSelectElement)) throw new Error('Missing category select');
    const category = Array.from(select.options).find(
      (option: Readonly<HTMLOptionElement>) =>
        option.textContent.trim() === reportDetail.report.category,
    );
    if (category === undefined) throw new Error('Missing stored report category');
    await userEvent.selectOptions(select, category.value);
    fixture.detectChanges();
    click('Search retained reports');
    const filtered = await request('reports?');
    const query = new URL(filtered.request.url, 'https://peerly.test').searchParams;
    expect(query.get('category')).toBe(reportDetail.report.category);
    expect(query.get('cursor')).toBeNull();
    filtered.flush(reportPage);
    await shown(reportId);
    const all = Array.from(select.options).find(
      (option: Readonly<HTMLOptionElement>) => option.textContent.trim() === 'all',
    );
    if (all === undefined) throw new Error('Missing all categories');
    await userEvent.selectOptions(select, all.value);
    fixture.detectChanges();
    click('Search retained reports');
    const unfiltered = await request('reports?');
    expect(
      new URL(unfiltered.request.url, 'https://peerly.test').searchParams.has('category'),
    ).toBe(false);
    expect(router.url).not.toContain('category=');
    expect(router.url).not.toContain('reports_cursor=');
    unfiltered.flush(reportPage);
    await shown(reportId);
    backend.expectNone((value) => value.method !== 'GET');
  });
  it('revalidates an actor replacement without rewriting cursor-free filters or revealing the old pending record', async () => {
    await login({ report: reportId, target_id: reportDetail.report.target_id });
    await list();
    const old = await request(`reports/${reportId}`);
    const url = router.url;
    const checking = client.invalidateQueries({ queryKey: ['session'] });
    (await vi.waitFor(() => backend.expectOne('/api/v1/me'))).flush({
      ...operatorIdentity,
      account_id: auditId,
    });
    await checking;
    const reports = await request('reports?');
    expect(new URL(reports.request.url, 'https://peerly.test').searchParams.get('target_id')).toBe(
      reportDetail.report.target_id,
    );
    expect(router.url).toBe(url);
    expect(old.cancelled).toBe(true);
    expect(host().textContent).not.toContain(reportDetail.comment);
    reports.flush(reportPage);
    (await request(`reports/${reportId}`)).flush(reportDetail);
    await shown(reportDetail.comment);
    backend.expectNone((value) => value.method !== 'GET');
    backend.expectNone((value) => value.url.startsWith('/api/v1/operator/events'));
  });
  it('drops a previous actor review cursor before opening a newly authorized human review', async () => {
    await login({ report: reportId, report_review_cursor: 'previous-actor-review-page' });
    await list();
    (await request(`reports/${reportId}`)).flush(reportDetail);
    await shown(reportDetail.comment);
    const checking = client.invalidateQueries({ queryKey: ['session'] });
    (await vi.waitFor(() => backend.expectOne('/api/v1/me'))).flush({
      ...operatorIdentity,
      account_id: auditId,
    });
    await checking;
    await list();
    (await request(`reports/${reportId}`)).flush(reportDetail);
    await shown(reportDetail.comment);
    expect(router.url).not.toContain('report_review_cursor');
    click('Human review');
    const history = await request(`reports/${reportId}/reviews`);
    expect(new URL(history.request.url, 'https://peerly.test').searchParams.has('cursor')).toBe(
      false,
    );
    history.flush(emptyHistory);
    await shown('No dismiss or escalate decision is recorded.');
    backend.expectNone((value) => value.method !== 'GET');
  });
  it('keeps a denied report private when an explicit grant recheck is denied again', async () => {
    await login({ report: reportId });
    const pending = await request('reports?');
    (await request(`reports/${reportId}`)).flush(
      { code: 'operator_access_denied', detail: 'PRIVATE GRANT DETAIL' },
      { status: 403, statusText: 'Denied' },
    );
    await shown('Operator access denied');
    expect(pending.cancelled).toBe(true);
    click('Check operator access again');
    (await vi.waitFor(() => backend.expectOne('/api/v1/me'))).flush(operatorIdentity);
    const recheckedList = await request('reports?');
    expect(recheckedList.request.method).toBe('GET');
    expect(recheckedList.request.url).toBe('/api/v1/operator/reports?');
    expect(recheckedList.cancelled).toBe(false);
    (await request(`reports/${reportId}`)).flush(
      { code: 'operator_access_denied', detail: 'PRIVATE GRANT DETAIL' },
      { status: 403, statusText: 'Denied' },
    );
    await shown('Operator access denied');
    await vi.waitFor(() => {
      expect(recheckedList.cancelled).toBe(true);
    });
    expect(host().textContent).not.toContain('PRIVATE GRANT DETAIL');
    expect(host().textContent).not.toContain(reportDetail.comment);
    expect(host().textContent).not.toContain('Human review');
    backend.expectNone((value) => value.method !== 'GET');
    backend.expectNone((value) => value.url.startsWith('/api/v1/operator'));
  });
  it('does not restart private report reads when a session recheck settles as the screen is retired', async () => {
    backend.expectOne('/api/v1/me').flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('Your session could not be checked');
    click('Retry');
    const session = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    session.flush(operatorIdentity);
    fixture.destroy();
    await fixture.whenStable();
    backend.expectNone((value) => value.url.startsWith('/api/v1/operator'));
    expect(
      client
        .getQueryCache()
        .findAll({ queryKey: ['account', operatorIdentity.account_id, 'operator'] }),
    ).toHaveLength(0);
  });
});
