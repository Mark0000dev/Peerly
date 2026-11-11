import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import type { TestRequest } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import type { Query } from '@tanstack/angular-query-experimental';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { TuiRoot } from '@taiga-ui/core';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../app.config';
import { Operator } from './operator';
import { operatorIdentity, account, detail } from './operator.fixtures';
import { profilePage, storedProfile } from './operator-profile-history.fixtures';

@Component({
  selector: 'operator-history-host',
  imports: [TuiRoot, Operator],
  template: '<tui-root><app-operator /></tui-root>',
})
class Host {}
@Component({ template: '' })
class Empty {}

describe('M06 explicit retained profile history', () => {
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
  async function navigate(params: Readonly<Record<string, string>>): Promise<void> {
    await router.navigateByUrl(`/operator/accounts?${new URLSearchParams(params).toString()}`);
    fixture.detectChanges();
  }
  async function request(path: string): Promise<TestRequest> {
    let found: TestRequest | undefined;
    await vi.waitFor(() => {
      fixture.detectChanges();
      found = backend.expectOne((value) => value.url.split('?')[0] === `/api/v1/operator/${path}`);
    });
    if (found === undefined) throw new Error(`Missing request ${path}`);
    return found;
  }
  async function login(params: Readonly<Record<string, string>> = {}): Promise<void> {
    await navigate(params);
    backend.expectOne('/api/v1/me').flush(operatorIdentity);
    await shown('Find accounts');
  }
  const overview = `accounts/${account.account_id}`;
  const path = `${overview}/profile-history`;
  async function ready(): Promise<void> {
    await login({ account: account.account_id });
    (await request(overview)).flush(detail);
    await shown('Profile history');
  }
  it('does not prefetch, explicitly opens literal raw records and closes only history resource', async () => {
    await ready();
    backend.expectNone((r) => r.url.endsWith('/profile-history'));
    click('Open retained profile history');
    (await request(path)).flush(profilePage);
    await shown('Stored raw history');
    expect(host().querySelector('article b')).toBeNull();
    expect(host().textContent).toContain('Not recorded');
    expect(host().textContent).toContain('Empty string');
    expect(host().textContent).toContain('zz-Legacy');
    expect(router.url).toContain('profile_history=open');
    click('Close retained profile history');
    await shown('Profile history');
    expect(router.url).not.toContain('profile_history=');
    expect(host().textContent).not.toContain('Stored raw history');
    expect(
      client
        .getQueryCache()
        .findAll({
          queryKey: ['account', operatorIdentity.account_id, 'operator', 'profile-history'],
        })
        .every((q: Readonly<Query>) => q.state.data === undefined),
    ).toBe(true);
    expect(host().textContent).toContain('Account and identity');
  });
  it('preserves page cursor and first page, valid empty and refresh', async () => {
    await ready();
    click('Open retained profile history');
    (await request(path)).flush(profilePage);
    await shown('Version 53');
    click('Older revisions');
    const older = await request(path);
    expect(older.request.urlWithParams).toContain('cursor=signed-profile-page');
    older.flush({ ...profilePage, revisions: [], next_cursor: null });
    await shown('No retained profile revisions');
    click('First page');
    (await request(path)).flush(profilePage);
    await shown('Version 53');
    click('Refresh history');
    (await request(path)).flush({
      ...profilePage,
      revisions: [],
      anchor_version: 0,
      next_cursor: null,
    });
    await shown('No retained profile revisions');
  });
  it('keeps503 and404 local and resets422 or malformed cursor', async () => {
    await ready();
    click('Open retained profile history');
    (await request(path)).flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('Profile history could not be loaded');
    expect(host().textContent).toContain('Account and identity');
    click('Retry history');
    (await request(path)).flush({}, { status: 404, statusText: 'Missing' });
    await shown('This account profile history is unavailable');
    click('Retry history');
    (await request(path)).flush({}, { status: 422, statusText: 'Invalid' });
    await shown('This profile history cursor could not be used');
    click('First page');
    (await request(path)).flush(profilePage);
    await shown('Version 53');
    await navigate({ account: account.account_id, profile_history: 'open', profile_cursor: '' });
    await shown('The profile history cursor is invalid');
    click('First page');
    (await request(path)).flush(profilePage);
    await shown('Version 53');
  });
  it('child403 cancels pending overview and denies workspace without late private reveal', async () => {
    await login({ account: account.account_id, profile_history: 'open' });
    const sibling = await request(overview);
    (await request(path)).flush({}, { status: 403, statusText: 'Forbidden' });
    await shown('Operator access denied');
    await vi.waitFor(() => {
      expect(sibling.cancelled).toBe(true);
    });
    expect(host().textContent).not.toContain('Account and identity');
    expect(
      client
        .getQueryCache()
        .findAll({ queryKey: ['account', operatorIdentity.account_id, 'operator'] })
        .some((q: Readonly<Query>) => q.state.error !== null),
    ).toBe(true);
    backend.expectNone((r) => r.url.endsWith('/profile-history'));
    click('Check access again');
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/me').flush(operatorIdentity);
    });
    (await request(overview)).flush(detail);
    (await request(path)).flush(profilePage);
    await shown('Version 53');
  });
  it('child401 rechecks session and retires pending private siblings', async () => {
    await login({ account: account.account_id, profile_history: 'open' });
    const sibling = await request(overview);
    (await request(path)).flush({}, { status: 401, statusText: 'Unauthorized' });
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/me').flush({}, { status: 401, statusText: 'Unauthorized' });
    });
    await shown('Sign in with your operator');
    expect(sibling.cancelled).toBe(true);
  });
  it('switches account with pending history and incompatible signed cursor without old reveal', async () => {
    await login({ account: account.account_id, profile_history: 'open', profile_cursor: 'old' });
    (await request(overview)).flush(detail);
    const late = await request(path);
    const next = profilePage.account_id.replace('2', '3');
    await navigate({ account: next, profile_history: 'open', profile_cursor: 'old' });
    (await request(`accounts/${next}`)).flush({
      ...detail,
      account: { ...detail.account, account_id: next },
    });
    const fresh = await request(`accounts/${next}/profile-history`);
    expect(fresh.request.urlWithParams).not.toContain('cursor=');
    expect(late.cancelled).toBe(true);
    fresh.flush({ ...profilePage, account_id: next, revisions: [], next_cursor: null });
    await shown('No retained profile revisions');
    expect(router.url).not.toContain('profile_cursor=');
  });
  it('actor replacement clears profile cursor before new owner reads', async () => {
    await login({ account: account.account_id, profile_history: 'open', profile_cursor: 'old' });
    (await request(overview)).flush(detail);
    (await request(path)).flush(profilePage);
    await shown('Version 53');
    const pending = client.refetchQueries({ queryKey: ['session'] });
    await vi.waitFor(() => {
      backend
        .expectOne('/api/v1/me')
        .flush({ ...operatorIdentity, account_id: profilePage.account_id });
    });
    await pending;
    (await request(overview)).flush(detail);
    const fresh = await request(path);
    expect(fresh.request.urlWithParams).not.toContain('cursor=');
    fresh.flush({ ...profilePage, revisions: [], next_cursor: null });
    await shown('No retained profile revisions');
    expect(host().textContent).not.toContain('Version 53');
  });
  it('renders 50 source versions without a current-pointer projection and reopening makes a fresh read', async () => {
    await ready();
    click('Open retained profile history');
    const pending = await request(path);
    await shown('Loading profile history');
    pending.flush({
      ...profilePage,
      revisions: Array.from({ length: 50 }, (_, i) => storedProfile(53 - i)),
    });
    await shown('Version 4');
    expect(host().querySelectorAll('article')).toHaveLength(50);
    click('Close retained profile history');
    await vi.waitFor(() => {
      expect(router.url).not.toContain('profile_history=');
    });
    fixture.detectChanges();
    click('Open retained profile history');
    (await request(path)).flush(profilePage);
    await shown('Version 53');
    expect(host().querySelectorAll('article')).toHaveLength(2);
  });
  it('history stays independent when the overview is locally unavailable', async () => {
    await login({ account: account.account_id, profile_history: 'open' });
    (await request(overview)).flush({}, { status: 503, statusText: 'Unavailable' });
    (await request(path)).flush(profilePage);
    await shown('Version 53');
    expect(host().textContent).toContain('The inspection could not be completed');
    click('Close retained profile history');
    await vi.waitFor(() => {
      expect(router.url).not.toContain('profile_history=');
    });
    expect(host().textContent).toContain('The inspection could not be completed');
  });
  it('rejects wrong owner projection and closing a pending read cancels it', async () => {
    await ready();
    click('Open retained profile history');
    (await request(path)).flush({
      ...profilePage,
      account_id: operatorIdentity.account_id,
      revisions: [],
    });
    await shown('Profile history could not be loaded');
    click('Retry history');
    const late = await request(path);
    click('Close retained profile history');
    await vi.waitFor(() => {
      expect(late.cancelled).toBe(true);
    });
    expect(host().textContent).toContain('Account and identity');
  });
});
