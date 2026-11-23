import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import type { TestRequest } from '@angular/common/http/testing';
import { Component, input } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { Router, provideRouter } from '@angular/router';
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
    '<tui-root><app-operator-report-review [actorId]="actor()" [reportId]="report()" /></tui-root>',
})
class Host {
  public readonly actor = input(operatorIdentity.account_id);
  public readonly report = input(reportId);
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

  for (const scenario of [
    { status: 401, message: 'Operator access must be checked before continuing.' },
    { status: 404, message: 'This report is unavailable for review.' },
    { status: 422, message: 'The report, history cursor or decision could not be accepted.' },
    { status: 503, message: 'The report review could not be loaded or confirmed.' },
  ] as const) {
    it(`recovers a history ${String(scenario.status)} only after an explicit read without recording a decision`, async () => {
      (await request('GET')).flush(
        { code: 'unavailable', detail: 'PRIVATE SERVER DETAIL' },
        { status: scenario.status, statusText: 'Unavailable' },
      );
      await shown(scenario.message);
      expect(host().textContent).not.toContain('PRIVATE SERVER DETAIL');
      backend.expectNone((value) => value.method !== 'GET');
      click('Read current review state');
      await open();
      backend.expectNone((value) => value.method !== 'GET');
    });
  }
  for (const status of [404, 422]) {
    it(`preserves an explicitly rejected decision ${String(status)} for review after canonical reload`, async () => {
      await open();
      draft('Keep my reason');
      click('Review decision');
      click('Record reviewed decision');
      (await request('POST')).flush(
        { code: 'unavailable', detail: 'PRIVATE SERVER DETAIL' },
        { status, statusText: 'Rejected' },
      );
      await shown(status === 404 ? 'This report is unavailable' : 'could not be accepted');
      expect(host().textContent).not.toContain('PRIVATE SERVER DETAIL');
      expect(host().querySelector('textarea')?.value).toBe('Keep my reason');
      backend.expectNone((value) => value.method === 'POST');
      click('Read current review state');
      await open();
      click('Review decision');
      await shown('Keep my reason');
      expect(host().querySelector<HTMLButtonElement>('button[type="submit"]')?.disabled).toBe(true);
      backend.expectNone((value) => value.method === 'POST');
    });
  }
  it('requires re-review when a background canonical revision advances after preparation', async () => {
    await open();
    draft();
    click('Review decision');
    const refresh = client.refetchQueries({
      queryKey: ['account', operatorIdentity.account_id, 'operator', 'report-review', reportId],
    });
    (await request('GET')).flush({
      ...emptyHistory,
      current: revision(2),
      anchor_version: 2,
      revisions: [revision(2)],
    });
    await refresh;
    await shown('The current version changed.');
    const apply = Array.from(host().querySelectorAll('button')).find(
      (button: Readonly<HTMLButtonElement>) =>
        button.textContent.trim() === 'Record reviewed decision',
    );
    expect(apply?.disabled).toBe(true);
    click('Edit decision');
    click('Review decision');
    await shown('Expected current version 2.');
    backend.expectNone((value) => value.method === 'POST');
  });
  it('cannot advance an exhausted revision and does not record a wrapped version', async () => {
    (await request('GET')).flush({
      ...emptyHistory,
      current: revision(2147483647),
      anchor_version: 2147483647,
      revisions: [revision(2147483647)],
    });
    await shown('This review version cannot be advanced further.');
    expect(host().querySelector<HTMLButtonElement>('button[type="submit"]')?.disabled).toBe(true);
    backend.expectNone((value) => value.method === 'POST');
  });
  it('retires a pending decision on logout and ignores its late successful receipt', async () => {
    await open();
    draft('Private retiring reason');
    click('Review decision');
    click('Record reviewed decision');
    const write = await request('POST');
    client.setQueryData(['session'], null);
    await shown('Operator access must be checked');
    expect(host().textContent).not.toContain('Private retiring reason');
    expect(client.getMutationCache().getAll()).toHaveLength(0);
    write.flush({ ...revision(1), reason: 'Private retiring reason' });
    await fixture.whenStable();
    expect(host().textContent).not.toContain('Decision stored');
    backend.expectNone((value) => value.url === path);
  });

  for (const field of ['actor', 'report']) {
    it(`cancels the previous history read when the ${field} URL identity is malformed`, async () => {
      const initial = await request('GET');
      fixture.componentRef.setInput(field, 'not-a-uuid');
      fixture.detectChanges();
      await shown('The operator or report ID is invalid.');
      expect(initial.cancelled).toBe(true);
      backend.expectNone((value) => value.url.startsWith('/api/v1/operator'));
    });
  }
  it('rechecks canonical authority before dispatching a queued review decision', async () => {
    await open();
    draft('Do not send after logout');
    click('Review decision');
    click('Record reviewed decision');
    client.setQueryData(['session'], null);
    await shown('Operator access must be checked');
    backend.expectNone((value) => value.method === 'POST');
    expect(host().textContent).not.toContain('Do not send after logout');
  });
  for (const status of [401, 403]) {
    it(`reports a current-owner decision authority failure ${String(status)} without automatic replay`, async () => {
      await open();
      draft();
      click('Review decision');
      click('Record reviewed decision');
      (await request('POST')).flush(
        { code: 'operator_access_denied' },
        { status, statusText: 'Denied' },
      );
      await shown('Operator access must be checked');
      backend.expectNone((value) => value.method === 'POST');
      expect(host().textContent).not.toContain('Decision stored');
    });
  }

  it('pages anchored history through the URL and returns to current history without a decision', async () => {
    (await request('GET')).flush({
      ...emptyHistory,
      current: revision(2),
      anchor_version: 2,
      revisions: [revision(2)],
      next_cursor: 'earlier-signed-page',
    });
    await shown('Earlier review revisions');
    click('Earlier review revisions');
    const earlier = await vi.waitFor(() => backend.expectOne(`${path}?cursor=earlier-signed-page`));
    expect(TestBed.inject(Router).url).toContain('report_review_cursor=earlier-signed-page');
    earlier.flush({
      ...emptyHistory,
      current: revision(2),
      anchor_version: 2,
      revisions: [revision(1)],
    });
    await shown('First review-history page');
    click('First review-history page');
    (await request('GET')).flush({
      ...emptyHistory,
      current: revision(2),
      anchor_version: 2,
      revisions: [revision(2)],
    });
    await shown('Current recorded decision');
    expect(TestBed.inject(Router).url).not.toContain('report_review_cursor');
    backend.expectNone((value) => value.method !== 'GET');
  });
  it('rejects an invalid history cursor locally and recovers only by explicit first page', async () => {
    const initial = await request('GET');
    await TestBed.inject(Router).navigateByUrl('/?report_review_cursor=' + 'a'.repeat(1025));
    await shown('The review-history cursor is invalid.');
    expect(initial.cancelled).toBe(true);
    backend.expectNone((value) => value.url.startsWith(path));
    click('First review-history page');
    await open();
    backend.expectNone((value) => value.method !== 'GET');
  });
  it('does not turn a successful history read into confirmation of an uncertain decision', async () => {
    await open();
    draft('Original uncertain reason');
    click('Review decision');
    click('Record reviewed decision');
    const original = await request('POST');
    const key = original.request.headers.get('Idempotency-Key');
    original.error(new ProgressEvent('error'));
    await shown('The decision outcome is unknown.');
    click('Read current review state');
    (await request('GET')).flush(emptyHistory);
    await fixture.whenStable();
    await shown('The decision outcome is unknown.');
    expect(host().querySelector('textarea')?.value).toBe('Original uncertain reason');
    backend.expectNone((value) => value.method === 'POST');
    click('Retry identical decision');
    const replay = await request('POST');
    expect(replay.request.headers.get('Idempotency-Key')).toBe(key);
    expect(replay.request.body).toEqual(original.request.body);
    replay.flush({ ...revision(1), reason: 'Original uncertain reason' });
    (await request('GET')).flush({
      ...emptyHistory,
      current: { ...revision(1), reason: 'Original uncertain reason' },
      anchor_version: 1,
      revisions: [{ ...revision(1), reason: 'Original uncertain reason' }],
    });
    await shown('Decision stored');
  });

  it('keeps an explicit identical retry pending when an older uncertain-history read completes', async () => {
    await open();
    draft('Exact original recovery reason');
    click('Review decision');
    click('Record reviewed decision');
    const original = await request('POST');
    const body: unknown = original.request.body;
    const key = original.request.headers.get('Idempotency-Key');
    original.error(new ProgressEvent('error'));
    await shown('The decision outcome is unknown.');
    click('Read current review state');
    const history = await request('GET');
    backend.expectNone((value) => value.method === 'POST');
    client.setQueryData(['session'], { ...operatorIdentity, csrf_token: 'fresh-recovery-csrf' });
    click('Retry identical decision');
    const replay = await request('POST');
    expect(replay.request.body).toEqual(body);
    expect(replay.request.headers.get('Idempotency-Key')).toBe(key);
    expect(replay.request.headers.get('X-CSRF-Token')).toBe('fresh-recovery-csrf');
    history.flush(emptyHistory);
    await shown('Recording the human decision…');
    expect(host().querySelector('textarea')?.value).toBe('Exact original recovery reason');
    backend.expectNone((value) => value.method === 'POST');
    const stored = { ...revision(1), reason: 'Exact original recovery reason' };
    replay.flush(stored);
    (await request('GET')).flush({
      ...emptyHistory,
      current: stored,
      anchor_version: 1,
      revisions: [stored],
    });
    await shown('Decision stored');
    expect(host().textContent).toContain('Exact original recovery reason');
    backend.expectNone((value) => value.method === 'POST');
  });
});
