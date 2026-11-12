import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { TuiRoot } from '@taiga-ui/core';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { MockInstance } from 'vitest';
import { appConfig } from '../../app.config';
import { verifiedActor } from './account.fixtures';
import { DeleteAccount } from './delete-account';

const preparation = {
  workflow_id: '11111111-1111-4111-8111-111111111111',
  expires_at: '2026-11-09T10:00:00Z',
} as const;
const receipt = {
  workflow_id: preparation.workflow_id,
  deleted_at: '2026-11-09T09:00:00Z',
  source_version: 1,
} as const;
@Component({
  selector: 'deletion-test-host',
  imports: [TuiRoot, DeleteAccount],
  template: '<tui-root><app-delete-account /></tui-root>',
})
class DeletionHost {}

describe('P05 explicit destructive command and actor lifetime', () => {
  let fixture: ComponentFixture<DeletionHost>;
  let backend: HttpTestingController;
  let client: QueryClient;
  let navigation: MockInstance<Router['navigateByUrl']>;
  beforeEach(() => {
    client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    TestBed.configureTestingModule({
      providers: [
        ...appConfig.providers,
        provideHttpClientTesting(),
        provideRouter([]),
        provideTanStackQuery(client),
      ],
    });
    backend = TestBed.inject(HttpTestingController);
    navigation = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    fixture = TestBed.createComponent(DeletionHost);
    fixture.detectChanges();
  });
  afterEach(() => {
    fixture.destroy();
    client.clear();
    backend.verify({ ignoreCancelled: true });
    vi.restoreAllMocks();
    TestBed.resetTestingModule();
  });
  function host(): HTMLElement {
    const element: unknown = fixture.nativeElement;
    if (!(element instanceof HTMLElement)) throw new Error('Missing deletion host');
    return element;
  }
  async function shown(text: string): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain(text);
    });
  }
  function click(label: string): void {
    fixture.detectChanges();
    const button = Array.from(host().querySelectorAll('button')).find(
      (item: Readonly<HTMLButtonElement>) => item.textContent.trim() === label,
    );
    if (button === undefined) throw new Error(`Missing action: ${label}`);
    button.click();
    fixture.detectChanges();
  }
  async function signedIn(): Promise<void> {
    (await vi.waitFor(() => backend.expectOne('/api/v1/me'))).flush(verifiedActor);
    await shown('Deleting this account signs you out');
  }
  async function prepared(): Promise<void> {
    await signedIn();
    click('Delete account');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me/deletion-workflows'));
    expect(request.request.body).toEqual({});
    expect(request.request.headers.get('X-CSRF-Token')).toBe(verifiedActor.csrf_token);
    request.flush(preparation);
    await shown('Delete account permanently');
  }
  it('does not prepare or delete just because the page is opened', async () => {
    await signedIn();
    backend.expectNone('/api/v1/me/deletion-workflows');
    backend.expectNone('/api/v1/me/deletion');
    expect(host().querySelector('input')).toBeNull();
  });
  it('cancel closes actual prepared confirmation without a destructive command', async () => {
    await prepared();
    click('Cancel');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).not.toContain('Delete account permanently');
    });
    backend.expectNone('/api/v1/me/deletion');
  });
  it('keeps the busy opener focusable but cannot prepare twice while its response is pending', async () => {
    await signedIn();
    click('Delete account');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me/deletion-workflows'));
    await shown('Preparing your request');
    const opener = Array.from(host().querySelectorAll('button')).find(
      (button: Readonly<HTMLButtonElement>) => button.textContent.trim() === 'Delete account',
    );
    expect(opener?.disabled).toBe(false);
    expect(opener?.getAttribute('aria-disabled')).toBe('true');
    expect(opener?.getAttribute('aria-busy')).toBe('true');
    click('Delete account');
    backend.expectNone('/api/v1/me/deletion-workflows');
    backend.expectNone('/api/v1/me/deletion');
    request.flush(preparation);
    await shown('Delete account permanently');
  });
  it('sends only on explicit confirmation, then clears private state and uses proof recovery', async () => {
    await prepared();
    client.setQueryData(['account', verifiedActor.account_id, 'private'], { private: true });
    click('Delete account permanently');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me/deletion'));
    expect(request.request.body).toEqual({ workflow_id: preparation.workflow_id });
    expect(request.request.headers.get('X-CSRF-Token')).toBe(verifiedActor.csrf_token);
    expect(request.request.headers.get('Idempotency-Key')).toMatch(/^[a-f0-9-]{36}$/u);
    await shown('Deleting account');
    const changes = host().querySelector('[aria-label="What this deletion request changes"]');
    expect(changes?.querySelectorAll('li')).toHaveLength(4);
    expect(changes?.textContent).toContain('the account in this deletion request');
    backend.expectNone('/api/v1/me/deletion');
    request.flush(receipt);
    await vi.waitFor(() => {
      expect(navigation).toHaveBeenCalledWith('/account/deletion-status');
    });
    expect(client.getQueryData(['session'])).toBeNull();
    expect(client.getQueryData(['account', verifiedActor.account_id, 'private'])).toBeUndefined();
    expect(client.getMutationCache().getAll()).toHaveLength(0);
  });
  it('routes a lost response to recovery without retrying or claiming failure', async () => {
    await prepared();
    click('Delete account permanently');
    (await vi.waitFor(() => backend.expectOne('/api/v1/me/deletion'))).error(
      new ProgressEvent('error'),
    );
    await vi.waitFor(() => {
      expect(navigation).toHaveBeenCalledWith('/account/deletion-status');
    });
    backend.expectNone('/api/v1/me/deletion');
    expect(host().textContent).not.toContain('Deletion failed');
  });
  it('rejects mismatched receipt identity rather than rendering false success', async () => {
    await prepared();
    click('Delete account permanently');
    (await vi.waitFor(() => backend.expectOne('/api/v1/me/deletion'))).flush({
      ...receipt,
      workflow_id: '22222222-2222-4222-8222-222222222222',
    });
    await vi.waitFor(() => {
      expect(navigation).toHaveBeenCalledWith('/account/deletion-status');
    });
    expect(client.getQueryData(['session'])).toEqual(verifiedActor);
  });
  it('ignores a late committed response after actual account replacement', async () => {
    await prepared();
    click('Delete account permanently');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me/deletion'));
    const replacement = {
      ...verifiedActor,
      account_id: '22222222-2222-4222-8222-222222222222',
    } as const;
    client.setQueryData(['session'], replacement);
    request.flush(receipt);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain('Deleting this account signs you out');
    });
    expect(navigation).not.toHaveBeenCalled();
    expect(client.getQueryData(['session'])).toEqual(replacement);
  });
  it('shows a preparation problem without inventing a confirmation and allows explicit retry', async () => {
    await signedIn();
    click('Delete account');
    (await vi.waitFor(() => backend.expectOne('/api/v1/me/deletion-workflows'))).flush(
      { code: 'unavailable', request_id: 'safe-reference' },
      { status: 503, statusText: 'Unavailable' },
    );
    await shown('Reference: safe-reference');
    expect(host().textContent).not.toContain('Delete account permanently');
    click('Delete account');
    (await vi.waitFor(() => backend.expectOne('/api/v1/me/deletion-workflows'))).flush(preparation);
    await shown('Delete account permanently');
  });
  it('retires a pending preparation when the actor changes before its response', async () => {
    await signedIn();
    click('Delete account');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me/deletion-workflows'));
    client.setQueryData(['session'], {
      ...verifiedActor,
      account_id: '22222222-2222-4222-8222-222222222222',
    });
    request.flush(preparation);
    await shown('Deleting this account signs you out');
    expect(host().textContent).not.toContain('Delete account permanently');
    backend.expectNone('/api/v1/me/deletion');
  });
  it('does not retire a replacement actor recovery query from a late old preparation', async () => {
    await signedIn();
    click('Delete account');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me/deletion-workflows'));
    client.setQueryData(['session'], {
      ...verifiedActor,
      account_id: '22222222-2222-4222-8222-222222222222',
    });
    const replacementProof = {
      ...preparation,
      workflow_id: '33333333-3333-4333-8333-333333333333',
    } as const;
    client.setQueryData(['account-deletion-status'], replacementProof);
    request.flush(preparation);
    await shown('Deleting this account signs you out');
    expect(client.getQueryData(['account-deletion-status'])).toEqual(replacementProof);
  });
  it('does not navigate from a late unknown outcome owned by an old actor', async () => {
    await prepared();
    click('Delete account permanently');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me/deletion'));
    client.setQueryData(['session'], {
      ...verifiedActor,
      account_id: '22222222-2222-4222-8222-222222222222',
    });
    request.error(new ProgressEvent('error'));
    await shown('Deleting this account signs you out');
    expect(navigation).not.toHaveBeenCalled();
  });
  it('does not clear a replacement account while private cancellation is settling', async () => {
    await prepared();
    click('Delete account permanently');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me/deletion'));
    const original = client.cancelQueries.bind(client);
    vi.spyOn(client, 'cancelQueries').mockImplementation(
      async (
        filters: Readonly<Parameters<QueryClient['cancelQueries']>[0]>,
        options: Readonly<Parameters<QueryClient['cancelQueries']>[1]>,
      ) => {
        await original(filters, options);
        client.setQueryData(['session'], {
          ...verifiedActor,
          account_id: '22222222-2222-4222-8222-222222222222',
        });
      },
    );
    request.flush(receipt);
    await shown('Deleting this account signs you out');
    expect(client.getQueryData(['session'])).not.toBeNull();
    expect(navigation).not.toHaveBeenCalled();
  });
  it('does not navigate after this view is destroyed during an in-flight command', async () => {
    await prepared();
    click('Delete account permanently');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me/deletion'));
    fixture.destroy();
    request.flush(receipt);
    await vi.waitFor(() => {
      expect(client.getMutationCache().getAll()).toHaveLength(0);
    });
    expect(navigation).not.toHaveBeenCalled();
  });
  it('prevents rapid duplicate preparation and preserves unrelated mutation ownership on teardown', async () => {
    await signedIn();
    const button = Array.from(host().querySelectorAll('button')).find(
      (item: Readonly<HTMLButtonElement>) => item.textContent.trim() === 'Delete account',
    );
    if (button === undefined) throw new Error('Missing prepare action');
    const unrelated = client
      .getMutationCache()
      .build(client, { mutationKey: ['unrelated'], mutationFn: () => Promise.resolve(null) });
    button.click();
    button.click();
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me/deletion-workflows'));
    request.flush(preparation);
    await shown('Delete account permanently');
    fixture.destroy();
    expect(client.getMutationCache().getAll()).toEqual([unrelated]);
  });
  it('withdraws prepared confirmation when current CSRF authority rotates', async () => {
    await prepared();
    client.setQueryData(['session'], { ...verifiedActor, csrf_token: 'replacement-csrf' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).not.toContain('Delete account permanently');
    });
    backend.expectNone('/api/v1/me/deletion');
  });
  it('retires expired authority on preparation401 without creating a destructive command', async () => {
    await signedIn();
    client.setQueryData(['account', verifiedActor.account_id, 'private'], { private: true });
    click('Delete account');
    (await vi.waitFor(() => backend.expectOne('/api/v1/me/deletion-workflows'))).flush(
      { code: 'unauthenticated' },
      { status: 401, statusText: 'Unauthorized' },
    );
    await shown('Sign in to start a deletion request');
    expect(client.getQueryData(['session'])).toBeNull();
    expect(client.getQueryData(['account', verifiedActor.account_id, 'private'])).toBeUndefined();
    backend.expectNone('/api/v1/me/deletion');
  });
  it('retires expired authority on destructive401 while keeping proof recovery reachable', async () => {
    await prepared();
    client.setQueryData(['account', verifiedActor.account_id, 'private'], { private: true });
    click('Delete account permanently');
    (await vi.waitFor(() => backend.expectOne('/api/v1/me/deletion'))).flush(
      { code: 'unauthenticated' },
      { status: 401, statusText: 'Unauthorized' },
    );
    await vi.waitFor(() => {
      expect(navigation).toHaveBeenCalledWith('/account/deletion-status');
    });
    expect(client.getQueryData(['session'])).toBeNull();
    expect(client.getQueryData(['account', verifiedActor.account_id, 'private'])).toBeUndefined();
  });
  it('keeps a replacement account when destructive401 retirement overlaps account replacement', async () => {
    await prepared();
    click('Delete account permanently');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me/deletion'));
    const replacement = {
      ...verifiedActor,
      account_id: '22222222-2222-4222-8222-222222222222',
      csrf_token: 'replacement-csrf',
    } as const;
    const original = client.cancelQueries.bind(client);
    vi.spyOn(client, 'cancelQueries').mockImplementation(
      async (
        filters: Readonly<Parameters<QueryClient['cancelQueries']>[0]>,
        options: Readonly<Parameters<QueryClient['cancelQueries']>[1]>,
      ) => {
        await original(filters, options);
        client.setQueryData(['session'], replacement);
      },
    );
    request.flush({ code: 'unauthenticated' }, { status: 401, statusText: 'Unauthorized' });
    await shown('Deleting this account signs you out');
    expect(client.getQueryData(['session'])).toEqual(replacement);
    expect(navigation).not.toHaveBeenCalled();
  });
  it('renders guest recovery links independently of sign in', async () => {
    (await vi.waitFor(() => backend.expectOne('/api/v1/me'))).flush(
      {},
      { status: 401, statusText: 'Unauthorized' },
    );
    await shown('Sign in to start a deletion request');
    expect(host().querySelector('a[href="/account/deletion-status"]')).not.toBeNull();
    expect(
      host().querySelector('[aria-label="Delete your Peerly account"]')?.textContent,
    ).toContain('Without the app');
    expect(host().querySelector('[aria-label="What deletion changes"]')?.textContent).toContain(
      'Your messages stay readable',
    );
    expect(host().querySelector('main a[href="/privacy"]')).not.toBeNull();
    expect(host().querySelector('main a[href="/help"]')).not.toBeNull();
    const web = host().querySelector('[aria-labelledby="delete-on-web"]');
    expect(web?.querySelector('a[href="/onboarding"]')?.textContent).toContain('Sign in');
    const help = host().querySelector('[aria-labelledby="delete-help"]');
    expect(help?.querySelector('a[href="/help"]')?.textContent).toContain('Help and contact');
    backend.expectNone((request) => request.method !== 'GET');
  });
  it('allows an explicit session retry and displays only the safe reference', async () => {
    (await vi.waitFor(() => backend.expectOne('/api/v1/me'))).flush(
      { code: 'unavailable', request_id: 'safe-reference' },
      { status: 503, statusText: 'Unavailable' },
    );
    await shown('Reference: safe-reference');
    click('Try again');
    (await vi.waitFor(() => backend.expectOne('/api/v1/me'))).flush(verifiedActor);
    await shown('Deleting this account signs you out');
  });
});
