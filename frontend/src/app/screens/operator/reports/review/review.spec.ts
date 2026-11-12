import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import type { TestRequest } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import type { Query } from '@tanstack/angular-query-experimental';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { TuiRoot } from '@taiga-ui/core';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../../../app.config';
import { operatorIdentity } from '../../operator.fixtures';
import { reportId } from '../../operator-reports.fixtures';
import { OperatorReportReview } from './review';
import { emptyHistory, revision } from './review.fixtures';

@Component({
  selector: 'report-review-test-host',
  imports: [TuiRoot, OperatorReportReview],
  template:
    '<tui-root><app-operator-report-review [actorId]="actor" [reportId]="report" /></tui-root>',
})
class Host {
  protected readonly actor = operatorIdentity.account_id;
  protected readonly report = reportId;
}
describe('M02 human decision intent ownership', () => {
  let fixture: ComponentFixture<Host>;
  let backend: HttpTestingController;
  let client: QueryClient;
  const path = `/api/v1/operator/reports/${reportId}/reviews`;
  beforeEach(() => {
    client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(['session'], operatorIdentity);
    TestBed.configureTestingModule({
      providers: [
        ...appConfig.providers,
        provideRouter([]),
        provideHttpClientTesting(),
        provideTanStackQuery(client),
      ],
    });
    backend = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(Host);
    fixture.detectChanges();
  });
  afterEach(() => {
    fixture.destroy();
    client.clear();
    backend.verify({ ignoreCancelled: true });
    TestBed.resetTestingModule();
  });
  function host(): HTMLElement {
    const value: unknown = fixture.nativeElement;
    if (!(value instanceof HTMLElement)) throw new Error('Missing review test host');
    return value;
  }
  async function shown(text: string): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain(text);
    });
  }
  function click(text: string): void {
    const button = Array.from(host().querySelectorAll('button')).find(
      (node: Readonly<HTMLButtonElement>) => node.textContent.trim() === text,
    );
    if (button === undefined) throw new Error(`Missing button ${text}`);
    button.click();
    fixture.detectChanges();
  }
  async function request(method: string): Promise<TestRequest> {
    let found: TestRequest | undefined;
    await vi.waitFor(() => {
      fixture.detectChanges();
      found = backend.expectOne((value) => value.url === path && value.method === method);
    });
    if (found === undefined) throw new Error('Missing review request');
    return found;
  }
  async function open(): Promise<void> {
    (await request('GET')).flush(emptyHistory);
    await shown('No dismiss or escalate decision is recorded.');
  }
  function draft(reason = '  Documented reason\nsecond line  '): void {
    const radio = host().querySelector('input[value="dismiss"]');
    const textarea = host().querySelector('textarea');
    if (!(radio instanceof HTMLInputElement) || !(textarea instanceof HTMLTextAreaElement))
      throw new Error('Missing real review controls');
    radio.click();
    textarea.setRangeText(reason, 0, textarea.value.length);
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
  }
  it('reads for an actual unverified operator; local review never posts, explicit confirmation preserves original reason', async () => {
    await open();
    draft();
    click('Review decision');
    await shown('Expected current version 0.');
    backend.expectNone((value) => value.method === 'POST');
    click('Record reviewed decision');
    const write = await request('POST');
    expect(write.request.body).toEqual({
      action: 'dismiss',
      expected_version: 0,
      reason: '  Documented reason\nsecond line  ',
    });
    expect(write.request.headers.get('X-CSRF-Token')).toBe('operator-test');
    expect(write.request.headers.get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/u);
    write.flush({ ...revision(1), reason: '  Documented reason\nsecond line  ' });
    (await request('GET')).flush({
      ...emptyHistory,
      current: revision(2),
      anchor_version: 2,
      revisions: [revision(2), revision(1)],
    });
    await shown('Decision stored');
    expect(host().textContent).toContain('Current recorded decision');
    expect(host().textContent).toContain('version 2');
  });
  it('requires actual action/reason and rejects overlong Unicode before any write', async () => {
    await open();
    click('Review decision');
    await shown('Choose Dismiss or Escalate.');
    draft('🦉'.repeat(1001));
    click('Review decision');
    await shown('Keep the reason within 1,000 characters.');
    backend.expectNone((value) => value.method === 'POST');
    expect(host().textContent).not.toContain('Expected current version');
  });
  it('replays unknown outcome with identical key/body and fresh canonical CSRF', async () => {
    await open();
    draft();
    click('Review decision');
    click('Record reviewed decision');
    const original = await request('POST');
    const key = original.request.headers.get('Idempotency-Key');
    const body: unknown = original.request.body;
    original.error(new ProgressEvent('error'));
    await shown('The decision outcome is unknown.');
    client.setQueryData(['session'], { ...operatorIdentity, csrf_token: 'renewed-csrf' });
    fixture.detectChanges();
    click('Retry identical decision');
    const replay = await request('POST');
    expect(replay.request.headers.get('Idempotency-Key')).toBe(key);
    expect(replay.request.headers.get('X-CSRF-Token')).toBe('renewed-csrf');
    expect(replay.request.body).toEqual(body);
    replay.flush({ ...revision(1), reason: '  Documented reason\nsecond line  ' });
    (await request('GET')).flush({
      ...emptyHistory,
      current: revision(1),
      anchor_version: 1,
      revisions: [revision(1)],
    });
    await shown('Decision stored');
  });
  it('requires fresh canonical state after CAS conflict while preserving the unsent form', async () => {
    await open();
    draft();
    click('Review decision');
    click('Record reviewed decision');
    (await request('POST')).flush(
      { code: 'report_review_version_conflict' },
      { status: 409, statusText: 'Conflict' },
    );
    await shown('Read the current state before reviewing a new decision.');
    backend.expectNone((value) => value.method === 'POST');
    click('Read current review state');
    (await request('GET')).flush({
      ...emptyHistory,
      current: revision(2),
      anchor_version: 2,
      revisions: [revision(2)],
    });
    await shown('Retained private reason.');
    click('Review decision');
    await shown('Expected current version 2.');
    expect(host().textContent).toContain('Documented reason');
  });
  it('retires private draft on actor replacement and cancels an outstanding canonical read', async () => {
    await open();
    draft();
    click('Review decision');
    client.setQueryData(['session'], {
      ...operatorIdentity,
      account_id: 'c1111111-1111-4111-8111-111111111111',
    });
    await shown('Operator access must be checked');
    expect(host().textContent).not.toContain('Documented reason');
    expect(
      client.getQueryCache().findAll({
        queryKey: ['account', operatorIdentity.account_id, 'operator', 'report-review'],
      }),
    ).toHaveLength(0);
    backend.expectNone((value) => value.method === 'POST');
  });
  it('uses native draft exit confirmation and refuses a stale accepted leave after actor retirement', async () => {
    await open();
    draft();
    const component: unknown = fixture.debugElement.query(
      By.directive(OperatorReportReview),
    ).componentInstance;
    if (!(component instanceof OperatorReportReview)) throw new Error('Missing actual review leaf');
    const keep = component.confirmLeave();
    await shown('Discard unsaved changes?');
    click('Keep editing');
    expect(await keep).toBe(false);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('[role="dialog"], [role="alertdialog"]')).toBeNull();
    });
    const stale = component.confirmLeave();
    await shown('Discard unsaved changes?');
    client.setQueryData(['session'], null);
    fixture.detectChanges();
    click('Discard changes');
    expect(await stale).toBe(false);
    await shown('Operator access must be checked');
  });
  for (const failure of [
    { status: 401, text: 'Operator access must be checked' },
    { status: 404, text: 'This report is unavailable for review.' },
    { status: 409, text: 'Read the current state before reviewing a new decision.' },
    { status: 422, text: 'The report, history cursor or decision could not be accepted.' },
    { status: 503, text: 'The report review could not be loaded or confirmed.' },
  ]) {
    it(`keeps an actual history ${String(failure.status)} read failure explicit without recording a decision`, async () => {
      (await request('GET')).flush(
        { code: 'report_review_unavailable' },
        { status: failure.status, statusText: 'Failure' },
      );
      await shown(failure.text);
      expect(host().textContent).not.toContain('Decision stored');
      backend.expectNone((value) => value.method === 'POST');
    });
  }
  for (const changed of [
    { field: 'report', patch: { report_id: 'b4444444-4444-4444-8444-444444444444' } },
    { field: 'operator', patch: { operator_id: 'b5555555-5555-4555-8555-555555555555' } },
    { field: 'action', patch: { action: 'escalate' } },
    { field: 'reason', patch: { reason: 'A different recorded reason' } },
    { field: 'version', patch: { version: 2, previous_version: 1 } },
  ] satisfies readonly Readonly<{
    readonly field: string;
    readonly patch: Readonly<Partial<ReturnType<typeof revision>>>;
  }>[]) {
    it(`cannot confirm a review receipt for a different ${changed.field} and recovers only the original intent`, async () => {
      await open();
      const reason = 'Reason under explicit review';
      draft(reason);
      click('Review decision');
      click('Record reviewed decision');
      const first = await request('POST');
      const key = first.request.headers.get('Idempotency-Key');
      expect(key).not.toBeNull();
      first.flush({ ...revision(1), reason, ...changed.patch });
      await shown('The decision outcome is unknown.');
      expect(host().textContent).toContain(reason);
      expect(host().textContent).not.toContain('Decision stored');
      backend.expectNone((value) => value.method === 'GET');
      click('Retry identical decision');
      const retry = await request('POST');
      expect(retry.request.body).toEqual(first.request.body);
      expect(retry.request.headers.get('Idempotency-Key')).toBe(key);
      retry.flush({ ...revision(1), reason });
      (await request('GET')).flush({
        ...emptyHistory,
        current: { ...revision(1), reason },
        revisions: [{ ...revision(1), reason }],
        anchor_version: 1,
      });
      await shown('Decision stored');
    });
  }
  it('retires a queued review before dispatch when operator authority disappears', async () => {
    await open();
    draft('Private reason before authority retirement');
    click('Review decision');
    click('Record reviewed decision');
    client.setQueryData(['session'], null);
    fixture.detectChanges();
    await shown('Operator access must be checked');
    expect(host().textContent).not.toContain('Private reason before authority retirement');
    backend.expectNone((value) => value.method === 'POST');
  });
  it('emits actual forbidden authority and preserves its query sentinel for parent resource revalidation', async () => {
    const component: unknown = fixture.debugElement.query(
      By.directive(OperatorReportReview),
    ).componentInstance;
    if (!(component instanceof OperatorReportReview)) throw new Error('Missing actual review leaf');
    let failures = 0;
    const subscription = component.authorityFailure.subscribe((failure) => {
      expect(failure.actorId).toBe(operatorIdentity.account_id);
      expect(failure.error.status).toBe(403);
      failures += 1;
    });
    (await request('GET')).flush(
      { code: 'operator_access_required' },
      { status: 403, statusText: 'Forbidden' },
    );
    await shown('Operator access must be checked');
    expect(failures).toBe(1);
    expect(
      client
        .getQueryCache()
        .findAll({
          queryKey: ['account', operatorIdentity.account_id, 'operator', 'report-review'],
        })
        .some((query: Readonly<Query>) => query.state.status === 'error'),
    ).toBe(true);
    subscription.unsubscribe();
  });
});
