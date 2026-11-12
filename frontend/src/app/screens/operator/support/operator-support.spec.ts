import type { HttpRequest } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import type { TestRequest } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { Router, provideRouter } from '@angular/router';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { TuiRoot, TuiDialogService } from '@taiga-ui/core';
import { of } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../../app.config';
import { OperatorSupport } from './operator-support';
import {
  supportActor,
  supportCase,
  supportHistory,
  supportInbox,
  supportReceipt,
  supportSummary,
} from './support.fixtures';
import type { Api } from '../../../api.generated';

@Component({
  selector: 'operator-support-host',
  imports: [TuiRoot, OperatorSupport],
  template: '<tui-root><app-operator-support /></tui-root>',
})
class Host {}
@Component({ template: '' })
class Empty {}
const listPath = '/api/v1/operator/cases';
const casePath = `${listPath}/${supportReceipt.case_id}`;
const historyPath = `${casePath}/history`;
const statusPath = `${casePath}/status`;

describe('operator support canonical reads and explicit status intent', () => {
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
        provideRouter([{ path: 'operator/support', component: Empty }]),
        provideHttpClientTesting(),
        provideTanStackQuery(client),
      ],
    });
    router = TestBed.inject(Router);
    await router.navigateByUrl('/operator/support');
    backend = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(Host);
    fixture.detectChanges();
  });
  afterEach(() => {
    fixture.destroy();
    client.clear();
    backend.verify();
    TestBed.resetTestingModule();
    vi.restoreAllMocks();
  });
  function host(): HTMLElement {
    const element: unknown = fixture.nativeElement;
    if (!(element instanceof HTMLElement)) throw new Error('Missing support host');
    return element;
  }
  async function shown(text: string): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent.replace(/\s+/g, ' ')).toContain(text);
    });
  }
  async function request(path: string, method = 'GET'): Promise<TestRequest> {
    let found: TestRequest | undefined;
    await vi.waitFor(() => {
      fixture.detectChanges();
      found = backend.expectOne(
        (value: Readonly<HttpRequest<unknown>>) =>
          value.url.split('?')[0] === path && value.method === method,
        `${method} ${path}`,
      );
    });
    if (found === undefined) throw new Error(`Missing ${method} ${path}`);
    return found;
  }
  function commandButton(label: string): HTMLButtonElement {
    const button = Array.from(host().querySelectorAll('button')).find(
      (value: Readonly<HTMLButtonElement>) =>
        value.getAttribute('aria-label') === label ||
        value.textContent.replace(/\s+/g, ' ').trim() === label,
    );
    if (button === undefined) throw new Error(`Missing ${label}`);
    return button;
  }
  function click(label: string): void {
    commandButton(label).click();
    fixture.detectChanges();
  }
  function select(id: string, label: string): void {
    const element = host().querySelector(`#${id}`);
    if (!(element instanceof HTMLSelectElement)) throw new Error('Missing select');
    const option = Array.from(element.options).find(
      (value: Readonly<HTMLOptionElement>) => value.textContent.trim() === label,
    );
    if (option === undefined) throw new Error(`Missing option ${label}`);
    const descriptor = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
    if (descriptor === undefined || typeof descriptor.set !== 'function')
      throw new Error('Missing native select value setter');
    descriptor.set.call(element, option.value);
    element.dispatchEvent(new Event('change', { bubbles: true }));
    fixture.detectChanges();
  }
  function choose(status: Api['schemas']['SupportStatus']): void {
    select('support-new-status', status);
  }
  function input(id: string, value: string): void {
    const element = host().querySelector(`#support-${id}`);
    if (!(element instanceof HTMLInputElement)) throw new Error('Missing support input');
    element.setRangeText(value, 0, element.value.length);
    element.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
  }
  function screen(): OperatorSupport {
    return fixture.debugElement.query(By.directive(OperatorSupport)).injector.get(OperatorSupport);
  }
  async function login(params: Readonly<Record<string, string>> = {}): Promise<void> {
    await router.navigateByUrl('/operator/support?' + new URLSearchParams(params).toString());
    fixture.detectChanges();
    (await request('/api/v1/me')).flush(supportActor);
    await shown('Find support cases');
  }
  async function ready(selected = true): Promise<void> {
    await login(selected ? { case: supportReceipt.case_id } : {});
    (await request(listPath)).flush(supportInbox);
    if (selected) (await request(casePath)).flush(supportCase);
    await shown(selected ? 'Literal <b>message</b>' : 'Open case');
  }
  async function prepare(): Promise<TestRequest> {
    choose('in_review');
    click('Review status change');
    backend.expectNone(statusPath);
    await shown('Confirm this status request');
    click('Confirm status change');
    return await request(statusPath, 'PUT');
  }
  function enableReconcile(): void {
    vi.spyOn(TestBed.inject(TuiDialogService), 'open').mockReturnValue(of(true));
  }
  async function refreshed(receipt: Api['schemas']['SupportReceiptResponse']): Promise<void> {
    (await request(listPath)).flush({
      ...supportInbox,
      cases: [{ ...supportSummary, ...receipt }],
    });
    (await request(casePath)).flush({ ...supportCase, receipt });
    await shown('Recorded result for your request');
  }
  it('opens metadata without private fanout, then literal detail and retained history explicitly', async () => {
    await ready(false);
    backend.expectNone(casePath);
    backend.expectNone(historyPath);
    backend.expectNone((value) => value.method !== 'GET');
    expect(host().textContent).not.toContain(supportCase.reply_address);
    click(`Open support case ${supportReceipt.case_id}`);
    (await request(casePath)).flush(supportCase);
    await shown('Literal <b>message</b>');
    expect(host().querySelector('dd b')).toBeNull();
    await shown('Not recorded');
    backend.expectNone(historyPath);
    click('Open retained status history');
    (await request(historyPath)).flush(supportHistory);
    await shown('Version 1');
    expect(host().textContent).toContain('Operator access version');
    expect(host().textContent).toContain('Not recorded');
    click('Close status history');
    await vi.waitFor(() => {
      expect(router.url).not.toContain('history=open');
    });
    backend.expectNone(historyPath);
  });
  it('keeps filter validation explicit and protects private content from metadata payloads', async () => {
    await login();
    (await request(listPath)).flush({
      ...supportInbox,
      cases: [{ ...supportSummary, message: 'private-body-in-inbox' }],
    });
    await shown('This support record could not be loaded');
    expect(host().textContent).not.toContain('private-body-in-inbox');
    await router.navigateByUrl(
      '/operator/support?anonymous=true&actor_id=' + supportActor.account_id,
    );
    await shown('An anonymous case filter cannot specify an account');
    backend.expectNone(listPath);
  });
  it('requires confirmation, exact CSRF/CAS and a genuine receipt before reporting success', async () => {
    await ready();
    const write = await prepare();
    expect(write.request.body).toEqual({ status: 'in_review', expected_version: 3 });
    expect(write.request.headers.get('x-csrf-token')).toBe(supportActor.csrf_token);
    expect(write.request.headers.get('idempotency-key')).not.toBeNull();
    const receipt = {
      ...supportReceipt,
      status: 'in_review' as const,
      version: 4,
      changed_at: '2026-11-02T07:00:00Z',
    };
    write.flush(receipt);
    await refreshed(receipt);
    expect(host().textContent).not.toContain('Email verified');
    backend.expectNone((value) => value.url.includes('/verification') || value.method === 'POST');
  });
  it('unknown replay retains key/body and a current matching status is not command proof', async () => {
    await ready();
    const write = await prepare();
    const body: unknown = write.request.body;
    const key = write.request.headers.get('idempotency-key');
    write.flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('We could not confirm the result');
    click('Check current case');
    (await request(casePath)).flush({
      ...supportCase,
      receipt: {
        ...supportReceipt,
        status: 'in_review',
        version: 4,
        changed_at: '2026-11-02T07:00:00Z',
      },
    });
    await shown('We could not confirm the result');
    expect(host().textContent).not.toContain('Recorded result for your request');
    click('Retry the same status change');
    const replay = await request(statusPath, 'PUT');
    expect(replay.request.body).toEqual(body);
    expect(replay.request.headers.get('idempotency-key')).toBe(key);
    replay.flush({
      ...supportReceipt,
      status: 'in_review',
      version: 4,
      changed_at: '2026-11-02T07:00:00Z',
    });
    await refreshed({
      ...supportReceipt,
      status: 'resolved',
      version: 5,
      changed_at: '2026-11-02T08:00:00Z',
    });
    expect(
      client.getQueryData<Api['schemas']['OperatorSupportResponse']>([
        'account',
        supportActor.account_id,
        'operator',
        'support',
        'case',
        supportReceipt.case_id,
      ])?.receipt.version,
    ).toBe(5);
    await shown('This receipt records the original result');
  });
  it('CAS conflict requires explicit fresh read/reconcile and a new immutable intent', async () => {
    await ready();
    const write = await prepare();
    const oldKey = write.request.headers.get('idempotency-key');
    write.flush({}, { status: 409, statusText: 'Conflict' });
    await shown('This request conflicts');
    enableReconcile();
    click('Use current case for a new change');
    (await request(casePath)).flush({
      ...supportCase,
      receipt: { ...supportReceipt, version: 5, changed_at: '2026-11-02T08:00:00Z' },
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      const button = Array.from(host().querySelectorAll('button')).find(
        (value: Readonly<HTMLButtonElement>) => value.textContent.trim() === 'Review status change',
      );
      expect(button?.disabled).toBe(false);
    });
    const fresh = await prepare();
    expect(fresh.request.body).toEqual({ status: 'in_review', expected_version: 5 });
    expect(fresh.request.headers.get('idempotency-key')).not.toBe(oldKey);
    fresh.flush({}, { status: 422, statusText: 'Invalid' });
    await shown('The earlier status request could not be completed');
  });
  it('a refreshed canonical version does not silently rebase an unsent status draft', async () => {
    await ready();
    choose('in_review');
    click('Check current case');
    (await request(casePath)).flush({
      ...supportCase,
      receipt: { ...supportReceipt, version: 4, changed_at: '2026-11-02T07:00:00Z' },
    });
    await shown('This case changed since the draft was prepared');
    click('Review status change');
    backend.expectNone(statusPath);
  });
  it('settled write403 cancels actual pending inbox/history siblings and explicit successful recheck restores reads', async () => {
    await ready();
    const write = await prepare();
    click('Refresh inbox');
    const lateInbox = await request(listPath);
    click('Open retained status history');
    const lateHistory = await request(historyPath);
    write.flush({ code: 'operator_access_denied' }, { status: 403, statusText: 'Forbidden' });
    await shown('Operator access denied');
    await vi.waitFor(() => {
      expect(lateInbox.cancelled).toBe(true);
      expect(lateHistory.cancelled).toBe(true);
    });
    expect(host().textContent).not.toContain(supportCase.reply_address);
    click('Check access again');
    (await request('/api/v1/me')).flush(supportActor);
    (await request(listPath)).flush(supportInbox);
    (await request(casePath)).flush(supportCase);
    (await request(historyPath)).flush(supportHistory);
    await shown('Literal <b>message</b>');
  });
  it('401 retires private siblings and canonical guest cannot send a status request', async () => {
    await ready();
    const write = await prepare();
    write.flush({ code: 'unauthenticated' }, { status: 401, statusText: 'Unauthorized' });
    (await request('/api/v1/me')).flush(
      { code: 'unauthenticated' },
      { status: 401, statusText: 'Unauthorized' },
    );
    await shown('Sign in with your operator Google account');
    expect(host().textContent).not.toContain(supportCase.reply_address);
    backend.expectNone(statusPath);
  });
  it('actor replacement retires the old pending command and never reveals its late receipt', async () => {
    await ready();
    const write = await prepare();
    const recheck = client.refetchQueries({ queryKey: ['session'] });
    (await request('/api/v1/me')).flush({
      ...supportActor,
      account_id: '00000000-0000-4000-8000-000000000079',
      csrf_token: 'synthetic-replacement-csrf',
    });
    await recheck;
    (await request(listPath)).flush(supportInbox);
    (await request(casePath)).flush({ ...supportCase, message: 'Replacement-authorized case' });
    await shown('Replacement-authorized case');
    write.flush({
      ...supportReceipt,
      status: 'in_review',
      version: 4,
      changed_at: '2026-11-02T07:00:00Z',
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).not.toContain('Recorded result for your request');
    });
    expect(
      client
        .getMutationCache()
        .findAll({ mutationKey: ['account', supportActor.account_id, 'operator', 'support'] }),
    ).toHaveLength(0);
  });
  it('keeps history503/404 local and first-page retry works even with an unchanged URL', async () => {
    await ready();
    click('Open retained status history');
    (await request(historyPath)).flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('This support record could not be loaded');
    expect(host().textContent).toContain(supportCase.reply_address);
    click('Retry status history');
    (await request(historyPath)).flush({}, { status: 404, statusText: 'Missing' });
    await shown('This support case or history is unavailable');
    click('Retry status history');
    (await request(historyPath)).flush({}, { status: 422, statusText: 'Invalid' });
    await shown('These filters or this page cursor could not be used');
    click('First history page');
    (await request(historyPath)).flush(supportHistory);
    await shown('Version 1');
  });
  it('submits filters only explicitly, rejects anonymous/account conflict and refreshes identical searches', async () => {
    await ready(false);
    input('actor_id', supportActor.account_id);
    select('support-anonymous', 'true');
    backend.expectNone(listPath);
    click('Search support cases');
    await shown('An anonymous case filter cannot specify an account');
    backend.expectNone(listPath);
    input('actor_id', '');
    select('support-topic', 'other');
    click('Search support cases');
    const filtered = await request(listPath);
    expect(new URL(filtered.request.url, 'https://example.test').searchParams.get('topic')).toBe(
      'other',
    );
    expect(
      new URL(filtered.request.url, 'https://example.test').searchParams.get('anonymous'),
    ).toBe('true');
    filtered.flush({ ...supportInbox, cases: [] });
    await shown('No support cases match these filters.');
    expect(router.url).toContain('topic=other');
    click('Search support cases');
    (await request(listPath)).flush(supportInbox);
    await shown('Open case');
    backend.expectNone(casePath);
  });
  it('explicit search closes selection and still refreshes the unchanged inbox query', async () => {
    await ready();
    click('Search support cases');
    (await request(listPath)).flush(supportInbox);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(router.url).not.toContain('case=');
      expect(host().textContent).not.toContain(supportCase.reply_address);
    });
    backend.expectNone(casePath);
  });
  it('uses real next-page cursor then explicitly resets an invalid inbox cursor to the first page', async () => {
    await login();
    (await request(listPath)).flush({ ...supportInbox, next_cursor: 'signed-next-inbox' });
    await shown('Next support cases');
    click('Next support cases');
    const next = await request(listPath);
    expect(new URL(next.request.url, 'https://example.test').searchParams.get('cursor')).toBe(
      'signed-next-inbox',
    );
    next.flush({}, { status: 422, statusText: 'Invalid cursor' });
    await shown('These filters or this page cursor could not be used');
    click('First inbox page');
    const first = await request(listPath);
    expect(new URL(first.request.url, 'https://example.test').searchParams.has('cursor')).toBe(
      false,
    );
    first.flush(supportInbox);
    await shown('Open case');
    click('Refresh inbox');
    (await request(listPath)).flush({}, { status: 422, statusText: 'Invalid' });
    await shown('These filters or this page cursor could not be used');
    click('First inbox page');
    (await request(listPath)).flush(supportInbox);
    await shown('Open case');
    expect(router.url).not.toContain('cursor=');
  });
  it('closing history cancels its transport and reopening explicitly loads a fresh retained page', async () => {
    await ready();
    click('Open retained status history');
    const pending = await request(historyPath);
    await shown('Loading status history');
    click('Close status history');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(pending.cancelled).toBe(true);
      expect(router.url).not.toContain('history=open');
      expect(
        Array.from(host().querySelectorAll('button')).some(
          (button: Readonly<HTMLButtonElement>) =>
            button.textContent.trim() === 'Open retained status history',
        ),
      ).toBe(true);
    });
    expect(host().textContent).toContain(supportCase.reply_address);
    click('Open retained status history');
    (await request(historyPath)).flush(supportHistory);
    await shown('Older status revisions');
    click('Older status revisions');
    const older = await request(historyPath);
    expect(new URL(older.request.url, 'https://example.test').searchParams.get('cursor')).toBe(
      supportHistory.next_cursor,
    );
    older.flush({
      ...supportHistory,
      revisions: supportHistory.revisions.filter((row) => row.version === 1),
      next_cursor: null,
    });
    await shown('Version 1');
    click('First history page');
    const first = await request(historyPath);
    expect(new URL(first.request.url, 'https://example.test').searchParams.has('cursor')).toBe(
      false,
    );
    first.flush(supportHistory);
    await shown('Version 3');
  });
  it('same-status NOOP receipt preserves server version without inventing a new revision', async () => {
    await ready();
    choose('resolved');
    click('Review status change');
    await shown('Confirm this status request');
    click('Confirm status change');
    const write = await request(statusPath, 'PUT');
    expect(write.request.body).toEqual({ status: 'resolved', expected_version: 3 });
    write.flush(supportReceipt);
    await refreshed(supportReceipt);
    expect(
      client.getQueryData<Api['schemas']['OperatorSupportResponse']>([
        'account',
        supportActor.account_id,
        'operator',
        'support',
        'case',
        supportReceipt.case_id,
      ])?.receipt.version,
    ).toBe(3);
    backend.expectNone(historyPath);
  });
  it('Keep editing and cancelled reconciliation retain the original unknown intent for explicit replay', async () => {
    await ready();
    expect(await screen().canLeave()).toBe(true);
    const write = await prepare();
    const key = write.request.headers.get('idempotency-key');
    write.flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('We could not confirm the result');
    const dialogs = vi.spyOn(TestBed.inject(TuiDialogService), 'open').mockReturnValue(of(false));
    expect(await screen().canLeave()).toBe(false);
    expect(dialogs).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ label: 'Leave before the save is confirmed?' }),
    );
    click('Use current case for a new change');
    (await request(casePath)).flush(supportCase);
    await vi.waitFor(() => {
      expect(dialogs).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({ label: 'Use the current case for a new change?' }),
      );
    });
    await shown('Retry the same status change');
    click('Retry the same status change');
    const replay = await request(statusPath, 'PUT');
    expect(replay.request.headers.get('idempotency-key')).toBe(key);
    expect(replay.request.body).toEqual(write.request.body);
    replay.flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('We could not confirm the result');
    dialogs.mockReturnValue(of(true));
    expect(await screen().canLeave()).toBe(true);
  });
  it('actor replacement resets both signed cursors before requesting the new owner pages', async () => {
    await login({
      case: supportReceipt.case_id,
      history: 'open',
      history_cursor: 'old-history',
      cursor: 'old-inbox',
    });
    (await request(listPath)).flush(supportInbox);
    (await request(casePath)).flush(supportCase);
    (await request(historyPath)).flush(supportHistory);
    await shown('Version 3');
    const recheck = client.refetchQueries({ queryKey: ['session'] });
    (await request('/api/v1/me')).flush({
      ...supportActor,
      account_id: '00000000-0000-4000-8000-000000000079',
      csrf_token: 'synthetic-replacement-csrf',
    });
    await recheck;
    const list = await request(listPath);
    const retained = await request(historyPath);
    expect(new URL(list.request.url, 'https://example.test').searchParams.has('cursor')).toBe(
      false,
    );
    expect(new URL(retained.request.url, 'https://example.test').searchParams.has('cursor')).toBe(
      false,
    );
    list.flush(supportInbox);
    (await request(casePath)).flush(supportCase);
    retained.flush(supportHistory);
    await shown('Version 3');
    expect(router.url).not.toContain('cursor=');
  });
  it('keeps an unavailable inbox local and blocks status writes until an unavailable case is explicitly recovered', async () => {
    await ready();
    click('Refresh inbox');
    (await request(listPath)).flush({}, { status: 404, statusText: 'Unavailable' });
    await shown('The support inbox is unavailable.');
    expect(host().textContent).toContain(supportCase.reply_address);
    click('Retry inbox');
    (await request(listPath)).flush(supportInbox);
    await shown('Open case');
    click('Check current case');
    (await request(casePath)).flush({}, { status: 404, statusText: 'Missing' });
    await shown('This support case or history is unavailable.');
    expect(commandButton('Review status change')).toHaveProperty('disabled', true);
    backend.expectNone(statusPath);
    click('Use current case for a new change');
    (await request(casePath)).flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('Other available records stay open.');
    expect(commandButton('Review status change')).toHaveProperty('disabled', true);
    expect(host().textContent).not.toContain('Confirm this status request');
    expect(host().textContent).not.toContain('Operator access denied');
    click('Retry case');
    (await request(casePath)).flush(supportCase);
    await shown('Literal <b>message</b>');
    expect(commandButton('Review status change')).toHaveProperty('disabled', false);
  });
  it('rejects valid-shaped case and history responses for a different selected identity without revealing or rebasing them', async () => {
    await login({ case: supportReceipt.case_id });
    (await request(listPath)).flush(supportInbox);
    (await request(casePath)).flush({
      ...supportCase,
      message: 'Wrong selected case must never render',
      receipt: { ...supportReceipt, case_id: '00000000-0000-4000-8000-000000000099' },
    });
    await shown('This support record could not be loaded.');
    expect(host().textContent).not.toContain('Wrong selected case must never render');
    expect(commandButton('Review status change')).toHaveProperty('disabled', true);
    backend.expectNone(statusPath);
    click('Retry case');
    (await request(casePath)).flush(supportCase);
    await shown('Literal <b>message</b>');
    click('Open retained status history');
    (await request(historyPath)).flush({
      ...supportHistory,
      case_id: '00000000-0000-4000-8000-000000000099',
    });
    await shown('This support record could not be loaded.');
    expect(host().textContent).not.toContain('Version 3');
    expect(host().textContent).toContain(supportCase.reply_address);
    click('Retry status history');
    (await request(historyPath)).flush(supportHistory);
    await shown('Version 3');
  });
  it('pauses a prepared status intent through uncertain session revalidation and requires explicit send after the same actor returns', async () => {
    await ready();
    choose('in_review');
    click('Review status change');
    await shown('Confirm this status request');
    const revalidation = client.refetchQueries({ queryKey: ['session'], exact: true });
    const pending = await request('/api/v1/me');
    backend.expectNone(statusPath);
    await shown('Checking your Google session');
    expect(host().textContent).not.toContain('Confirm this status request');
    pending.flush({}, { status: 503, statusText: 'Unavailable' });
    await revalidation;
    await shown('Your session could not be checked');
    backend.expectNone(statusPath);
    click('Try again');
    (await request('/api/v1/me')).flush(supportActor);
    (await request(listPath)).flush(supportInbox);
    (await request(casePath)).flush(supportCase);
    await shown('Confirm this status request');
    backend.expectNone(statusPath);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(commandButton('Confirm status change')).toHaveProperty('disabled', false);
    });
    click('Confirm status change');
    const command = await request(statusPath, 'PUT');
    expect(command.request.body).toEqual({ status: 'in_review', expected_version: 3 });
    const receipt = { ...supportReceipt, status: 'in_review', version: 4 } as const;
    command.flush(receipt);
    await refreshed(receipt);
  });
});
