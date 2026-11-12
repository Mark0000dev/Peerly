import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import type { TestRequest } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import type { Query } from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { TuiRoot } from '@taiga-ui/core';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../app.config';
import { Operator } from './operator';
import { account, accounts, detail, nullableDetail, operatorIdentity } from './operator.fixtures';

@Component({
  selector: 'operator-host',
  imports: [TuiRoot, Operator],
  template: '<tui-root><app-operator /></tui-root>',
})
class Host {}
@Component({ template: '' })
class Empty {}

describe('M03/M04 actual inspection authority and navigation', () => {
  let fixture: ComponentFixture<Host>;
  let backend: HttpTestingController;
  let client: QueryClient;
  let router: Router;
  const target = `/api/v1/operator/accounts/${account.account_id}`;
  beforeEach(async () => {
    client = new QueryClient({
      defaultOptions: {
        queries: { retry: false, refetchOnWindowFocus: false },
        mutations: { retry: false },
      },
    });
    TestBed.configureTestingModule({
      providers: [
        ...appConfig.providers,
        provideRouter([{ path: 'operator/accounts', component: Empty }]),
        provideHttpClientTesting(),
        provideTanStackQuery(client),
      ],
    });
    router = TestBed.inject(Router);
    await router.navigateByUrl('/operator/accounts');
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
    if (!(value instanceof HTMLElement)) throw new Error('Missing host');
    return value;
  }
  async function shown(text: string): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain(text);
    });
  }
  function button(text: string): void {
    const value = Array.from(host().querySelectorAll('button')).find(
      (item: Readonly<HTMLButtonElement>) =>
        item.textContent.trim() === text || item.getAttribute('aria-label') === text,
    );
    if (value === undefined) throw new Error('Missing button');
    value.click();
    fixture.detectChanges();
  }
  function fill(id: string, value: string): void {
    const input = host().querySelector(`#operator-${id}`);
    if (!(input instanceof HTMLInputElement)) throw new Error('Missing input');
    input.setRangeText(value, 0, input.value.length);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
  }
  function submit(): void {
    const form = host().querySelector('form');
    if (!(form instanceof HTMLFormElement)) throw new Error('Missing form');
    form.requestSubmit();
    fixture.detectChanges();
  }
  async function navigate(query: Readonly<Record<string, string>>): Promise<void> {
    await router.navigateByUrl(`/operator/accounts?${new URLSearchParams(query).toString()}`);
    fixture.detectChanges();
  }
  async function login(query: Readonly<Record<string, string>> = {}): Promise<void> {
    await navigate(query);
    backend.expectOne('/api/v1/me').flush(operatorIdentity);
    await shown('Find accounts');
  }
  async function flushList(
    body: Api['schemas']['OperatorAccountsResponse'] = accounts,
  ): Promise<void> {
    await vi.waitFor(() => {
      backend
        .expectOne((request) => request.url.startsWith('/api/v1/operator/accounts?'))
        .flush(body);
    });
  }
  async function flushDetail(
    body: Api['schemas']['OperatorAccountDetailResponse'] = detail,
  ): Promise<void> {
    await vi.waitFor(() => {
      backend.expectOne(target).flush(body);
    });
  }
  async function failList(status: number, code: string): Promise<void> {
    await vi.waitFor(() => {
      backend
        .expectOne((request) => request.url.startsWith('/api/v1/operator/accounts?'))
        .flush({ code }, { status, statusText: 'Controlled failure' });
    });
  }

  it('submits an explicit all lifecycle after native select cleaner interaction', async () => {
    await login();
    const select = host().querySelector('#operator-lifecycle');
    if (!(select instanceof HTMLSelectElement)) throw new Error('Missing lifecycle select');
    const cleaner = select.closest('tui-textfield')?.querySelector('button');
    if (!(cleaner instanceof HTMLButtonElement)) throw new Error('Missing native cleaner');
    cleaner.click();
    fixture.detectChanges();
    const visibility = host().querySelector('#operator-hidden');
    const visibilityCleaner = visibility?.closest('tui-textfield')?.querySelector('button');
    if (!(visibilityCleaner instanceof HTMLButtonElement))
      throw new Error('Missing visibility cleaner');
    visibilityCleaner.click();
    fixture.detectChanges();
    submit();
    await flushList();
    await shown('Maya Lee');
    expect(router.url).toContain('lifecycle=all');
    expect(router.url).not.toContain('hidden=');
  });

  it('requires explicit search, accepts incomplete student identity, renders actual account and embedded records', async () => {
    backend.expectNone((request) => request.url.startsWith('/api/v1/operator'));
    await login();
    backend.expectNone((request) => request.url.startsWith('/api/v1/operator'));
    fill('name', 'Maya');
    submit();
    await vi.waitFor(() => {
      expect(router.url).toContain('name=Maya');
    });
    await flushList();
    await shown('Maya Lee');
    expect(router.url).toContain('lifecycle=all');
    expect(host().textContent).toContain('stored-google-subject');
    await navigate({ lifecycle: 'all', account: account.account_id });
    await flushList();
    await flushDetail();
    await shown('Compare NULL rows.');
    for (const text of [
      'Python',
      'Information Technology',
      'Year 2',
      'English, Malay',
      'Google issuer',
      'Photo reference',
      '2592000',
      '2026-10',
    ])
      expect(host().textContent).toContain(text);
    expect(host().querySelector('img')).toBeNull();
    backend.expectNone((request) => request.method !== 'GET');
  });
  it('shows nullable records and preserved banned/deleted/hidden metadata honestly', async () => {
    await login({ account: account.account_id });
    await flushDetail({
      ...nullableDetail,
      account: {
        ...nullableDetail.account,
        banned_at: account.created_at,
        deleted_at: account.created_at,
        hidden_at: account.created_at,
      },
    });
    await shown('No stored record.');
    expect(host().textContent).toContain('Deleted account');
    expect(host().textContent).toContain('Banned account');
    expect(host().textContent).toContain('Hidden profile');
    expect(host().textContent).toContain('No stored references.');
    expect(host().textContent).not.toContain('Maya Lee');
    expect(host().querySelectorAll('a').length).toBeGreaterThan(0);
  });
  it('denies ordinary403 without requiring student capabilities or repeatedly probing', async () => {
    await login({ lifecycle: 'all' });
    await failList(403, 'operator_access_denied');
    await shown('Operator access denied');
    backend.expectNone((request) => request.url.startsWith('/api/v1/operator'));
    expect(host().querySelector('form')).toBeNull();
    expect(
      client
        .getQueryCache()
        .findAll({ queryKey: ['account', operatorIdentity.account_id, 'operator'] }),
    ).toHaveLength(1);
    button('Check access again');
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/me').flush(operatorIdentity);
    });
    await flushList();
    await shown('Maya Lee');
  });
  it('revocation retires existing source data and cancels a held sibling before it can render', async () => {
    await login({ lifecycle: 'all' });
    await flushList();
    await shown('Maya Lee');
    await navigate({ lifecycle: 'all', account: account.account_id });
    let held: Readonly<TestRequest> | undefined;
    await vi.waitFor(() => {
      held = backend.expectOne(target);
    });
    void client.invalidateQueries({
      queryKey: ['account', operatorIdentity.account_id, 'operator', 'accounts'],
    });
    await failList(403, 'operator_access_denied');
    await shown('Operator access denied');
    expect(held?.cancelled).toBe(true);
    await vi.waitFor(() => {
      const queries = client
        .getQueryCache()
        .findAll({ queryKey: ['account', operatorIdentity.account_id, 'operator'] });
      expect(queries).toHaveLength(1);
      expect(queries.every((query: Readonly<Query>) => query.state.data === undefined)).toBe(true);
    });
    expect(host().textContent).not.toContain('Maya Lee');
    expect(host().textContent).not.toContain('Comparing LEFT JOIN');
  });
  it('detail403 also retires a successful sibling list and current private response', async () => {
    await login({ lifecycle: 'all' });
    await flushList();
    await shown('Maya Lee');
    await navigate({ lifecycle: 'all', account: account.account_id });
    await vi.waitFor(() => {
      backend
        .expectOne(target)
        .flush({ code: 'operator_access_denied' }, { status: 403, statusText: 'Forbidden' });
    });
    await shown('Operator access denied');
    expect(host().textContent).not.toContain('Maya Lee');
    expect(
      client.getQueryData([
        'account',
        operatorIdentity.account_id,
        'operator',
        'account',
        account.account_id,
      ]),
    ).toBeUndefined();
  });
  it('401 retires operator data and rechecks canonical session; guests do not inspect', async () => {
    await login({ account: account.account_id });
    await vi.waitFor(() => {
      backend
        .expectOne(target)
        .flush({ code: 'unauthenticated' }, { status: 401, statusText: 'Unauthorized' });
    });
    await vi.waitFor(() => {
      backend
        .expectOne('/api/v1/me')
        .flush({ code: 'unauthenticated' }, { status: 401, statusText: 'Unauthorized' });
    });
    await shown('Sign in with your operator Google account');
    expect(
      client.getQueryCache().findAll({ queryKey: ['account', operatorIdentity.account_id] }),
    ).toHaveLength(0);
    expect(host().querySelector('a[href="/onboarding"]')).not.toBeNull();
  });
  it('does not trust retained identity after a failed session revalidation', async () => {
    backend
      .expectOne('/api/v1/me')
      .flush({ code: 'unavailable' }, { status: 503, statusText: 'Unavailable' });
    await shown('Your session could not be checked');
    backend.expectNone((request) => request.url.startsWith('/api/v1/operator'));
    button('Try again');
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/me').flush(operatorIdentity);
    });
    await shown('Find accounts');
    await navigate({ account: account.account_id });
    await flushDetail();
    await shown('Maya Lee');
    button('Close account');
    await vi.waitFor(() => {
      expect(router.url).not.toContain('account=');
    });
  });
  it('preserves URL after safe503 and404 and retries only explicit current inspection', async () => {
    await login({ lifecycle: 'all', account: account.account_id });
    await failList(503, 'unavailable');
    await vi.waitFor(() => {
      backend
        .expectOne(target)
        .flush({ code: 'operator_resource_unavailable' }, { status: 404, statusText: 'Not found' });
    });
    await shown('This account record is unavailable.');
    expect(router.url).toContain(account.account_id);
    button('Retry search');
    await flushList({ accounts: [], next_cursor: null });
    await shown('No accounts match');
    button('Retry account');
    await flushDetail();
    await shown('Compare NULL rows.');
  });
  it('uses opaque cursor, explicit first-page recovery and keeps filters', async () => {
    await login({ name: 'Maya', lifecycle: 'all' });
    await flushList({ ...accounts, next_cursor: 'opaque+/=' });
    await shown('Next results');
    button('Next results');
    await vi.waitFor(() => {
      expect(router.url).toContain('cursor=');
    });
    await failList(422, 'invalid_cursor');
    await shown('page cursor could not be used');
    button('First page');
    await vi.waitFor(() => {
      expect(router.url).not.toContain('cursor=');
    });
    await flushList();
    await shown('Maya Lee');
    expect(router.url).toContain('name=Maya');
    fill('name', 'Changed');
    submit();
    await vi.waitFor(() => {
      expect(router.url).toContain('name=Changed');
    });
    await flushList({ accounts: [], next_cursor: null });
    await shown('No accounts match');
  });
  it('rejects malformed URL and unsent form fields without a broadened private request', async () => {
    await login({ account: 'invalid' });
    await shown('selected account ID must be a UUID');
    backend.expectNone((request) => request.url.startsWith('/api/v1/operator'));
    button('Close account');
    await shown('Find accounts');
    fill('account_id', 'invalid');
    submit();
    await shown('must be UUIDs');
    backend.expectNone((request) => request.url.startsWith('/api/v1/operator'));
    expect(router.url).not.toContain('account_id=');
  });
  it('explicit identical-filter submission revalidates without another URL state store', async () => {
    await login({ lifecycle: 'all' });
    await flushList();
    await shown('Maya Lee');
    submit();
    await flushList({ accounts: [], next_cursor: null });
    await shown('No accounts match');
  });
  it('actor replacement cannot reuse cached authority or old details', async () => {
    await login({ account: account.account_id });
    await flushDetail();
    await shown('Maya Lee');
    const replacement = { ...operatorIdentity, account_id: '00000000-0000-4000-8000-000000000099' };
    void client.invalidateQueries({ queryKey: ['session'] });
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/me').flush(replacement);
    });
    await vi.waitFor(() => {
      backend
        .expectOne(target)
        .flush({ code: 'operator_access_denied' }, { status: 403, statusText: 'Forbidden' });
    });
    await shown('Operator access denied');
    expect(host().textContent).not.toContain('Maya Lee');
    expect(
      client
        .getQueryCache()
        .findAll({ queryKey: ['account', replacement.account_id, 'operator'] })
        .every((query: Readonly<Query>) => query.state.data === undefined),
    ).toBe(true);
  });
});
