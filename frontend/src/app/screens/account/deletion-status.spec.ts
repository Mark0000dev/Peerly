import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../app.config';
import { DeletionStatus } from './deletion-status';
import { verifiedActor } from './account.fixtures';

const url = '/api/v1/me/deletion-status';
const pending = {
  workflow_id: '11111111-1111-4111-8111-111111111111',
  expires_at: '2026-11-09T10:00:00Z',
  state: 'pending',
} as const;
const deleted = {
  workflow_id: pending.workflow_id,
  deleted_at: '2026-11-09T09:00:00Z',
  source_version: 1,
  state: 'deleted',
} as const;

describe('P05 cookie-proof recovery without a live application session', () => {
  let fixture: ComponentFixture<DeletionStatus>;
  let backend: HttpTestingController;
  let client: QueryClient;
  beforeEach(() => {
    client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    TestBed.configureTestingModule({
      providers: [
        ...appConfig.providers,
        provideHttpClientTesting(),
        provideRouter([]),
        provideTanStackQuery(client),
      ],
    });
    backend = TestBed.inject(HttpTestingController);
  });
  afterEach(() => {
    fixture.destroy();
    client.clear();
    backend.verify({ ignoreCancelled: true });
    TestBed.resetTestingModule();
  });
  function start(): void {
    fixture = TestBed.createComponent(DeletionStatus);
    fixture.detectChanges();
  }
  function host(): HTMLElement {
    const element: unknown = fixture.nativeElement;
    if (!(element instanceof HTMLElement)) throw new Error('Missing recovery host');
    return element;
  }
  async function shows(text: string): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain(text);
    });
  }
  function recheck(): HTMLButtonElement {
    const button = host().querySelector('button');
    if (!(button instanceof HTMLButtonElement)) throw new Error('Missing retry');
    return button;
  }
  function check(): void {
    recheck().click();
  }
  it('recovers before ordinary authority checking and never exposes workflow/proof in its request URL', async () => {
    start();
    await shows('Checking your deletion request');
    expect(host().querySelector('peerly-mascot')).toBeNull();
    const request = await vi.waitFor(() => backend.expectOne(url));
    expect(request.request.method).toBe('GET');
    expect(request.request.params.keys()).toEqual([]);
    backend.expectNone('/api/v1/me');
    request.flush(deleted);
    await shows('Deletion confirmed');
    const art = host().querySelector('peerly-mascot[tuiSlot="top"]');
    const heading = host().querySelector('[aria-label="Confirmed account deletion"] h2');
    if (art === null || heading === null) throw new Error('Missing confirmed deletion top content');
    expect(art.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    expect(host().querySelector('peerly-mascot img')?.getAttribute('src')).toBe(
      'assets/brand/mascot-hello.svg',
    );
    expect(host().querySelector('peerly-mascot source')?.getAttribute('srcset')).toBe(
      'assets/brand/mascot-hello-still.svg',
    );
    (await vi.waitFor(() => backend.expectOne('/api/v1/me'))).flush(
      {},
      { status: 401, statusText: 'Unauthorized' },
    );
    expect(host().textContent).not.toContain(pending.workflow_id);
  });
  it('keeps pending ambiguous and checks again only on an explicit action', async () => {
    start();
    (await vi.waitFor(() => backend.expectOne(url))).flush(pending);
    await shows('Deletion hasn’t been confirmed');
    backend.expectNone(url);
    const button = recheck();
    button.focus();
    check();
    const retry = await vi.waitFor(() => backend.expectOne(url));
    await shows('Checking your deletion request');
    expect(recheck()).toBe(button);
    expect(document.activeElement).toBe(button);
    expect(button.disabled).toBe(false);
    expect(button.getAttribute('aria-disabled')).toBe('true');
    expect(button.getAttribute('aria-busy')).toBe('true');
    check();
    backend.expectNone(url);
    retry.flush(deleted);
    await shows('Deletion confirmed');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(document.activeElement).toBe(host().querySelector('h2'));
    });
    expect(host().querySelector('button')).toBeNull();
    backend.expectNone((request) => request.method === 'POST');
    (await vi.waitFor(() => backend.expectOne('/api/v1/me'))).flush(
      {},
      { status: 401, statusText: 'Unauthorized' },
    );
  });
  it('does not take focus from Help when a recheck confirms deletion', async () => {
    start();
    (await vi.waitFor(() => backend.expectOne(url))).flush(pending);
    await shows('Deletion hasn’t been confirmed');
    recheck().focus();
    check();
    const retry = await vi.waitFor(() => backend.expectOne(url));
    await shows('Checking your deletion request');
    const help = host().querySelector('main > a[href="/help"]');
    if (!(help instanceof HTMLAnchorElement)) throw new Error('Missing Help');
    help.focus();
    expect(document.activeElement).toBe(help);
    retry.flush(deleted);
    await shows('Deletion confirmed');
    expect(document.activeElement).toBe(help);
    (await vi.waitFor(() => backend.expectOne('/api/v1/me'))).flush(
      {},
      { status: 401, statusText: 'Unauthorized' },
    );
    backend.expectNone((request) => request.method === 'POST');
  });
  it('withholds cached success until current browser proof is checked', async () => {
    client.setQueryData(['account-deletion-status'], deleted);
    start();
    await shows('Checking your deletion request');
    expect(host().textContent).not.toContain('Deletion confirmed');
    (await vi.waitFor(() => backend.expectOne(url))).flush(
      {},
      { status: 404, statusText: 'Not found' },
    );
    await shows('The account may still have been deleted');
  });
  it('shows safe diagnostic reference and retries a transient failure', async () => {
    start();
    (await vi.waitFor(() => backend.expectOne(url))).flush(
      { code: 'unavailable', request_id: 'safe-reference' },
      { status: 503, statusText: 'Unavailable' },
    );
    await shows('Reference: safe-reference');
    const button = recheck();
    button.focus();
    check();
    const retry = await vi.waitFor(() => backend.expectOne(url));
    await shows('Checking your deletion request');
    expect(recheck()).toBe(button);
    expect(document.activeElement).toBe(button);
    check();
    backend.expectNone(url);
    retry.flush(pending);
    await shows('Deletion hasn’t been confirmed');
    expect(recheck()).toBe(button);
    expect(document.activeElement).toBe(button);
    expect(button.getAttribute('aria-busy')).toBe('false');
    expect(button.getAttribute('aria-disabled')).toBe('false');
    backend.expectNone((request) => request.method === 'POST');
  });
  it('rechecks ordinary authority after canonical deletion and clears stale private state without gating the proof result', async () => {
    client.setQueryData(['session'], verifiedActor);
    client.setQueryData(['account', verifiedActor.account_id, 'private'], { private: true });
    start();
    (await vi.waitFor(() => backend.expectOne(url))).flush(deleted);
    await shows('Deletion confirmed');
    const session = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    expect(client.getQueryData(['account', verifiedActor.account_id, 'private'])).toBeUndefined();
    session.flush({}, { status: 401, statusText: 'Unauthorized' });
    await vi.waitFor(() => {
      expect(client.getQueryData(['session'])).toBeNull();
    });
    await shows('Deletion confirmed');
  });
  it('does not hide canonical proof when ordinary session authority is unavailable', async () => {
    start();
    (await vi.waitFor(() => backend.expectOne(url))).flush(deleted);
    (await vi.waitFor(() => backend.expectOne('/api/v1/me'))).flush(
      {},
      { status: 503, statusText: 'Unavailable' },
    );
    await shows('Deletion confirmed');
    await vi.waitFor(() => {
      expect(client.getQueryState(['session'])?.status).toBe('error');
    });
  });
  it('preserves a different live account after authoritative recheck instead of assuming proof owns its session', async () => {
    const replacement = {
      ...verifiedActor,
      account_id: '22222222-2222-4222-8222-222222222222',
    } as const;
    client.setQueryData(['session'], replacement);
    start();
    (await vi.waitFor(() => backend.expectOne(url))).flush(deleted);
    (await vi.waitFor(() => backend.expectOne('/api/v1/me'))).flush(replacement);
    await vi.waitFor(() => {
      expect(client.getQueryData(['session'])).toEqual(replacement);
    });
    await shows('The account for this request is deleted');
  });
  it('keeps canonical proof visible when a pending ordinary authority read is cancelled', async () => {
    start();
    (await vi.waitFor(() => backend.expectOne(url))).flush(deleted);
    const session = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    await client.cancelQueries({ queryKey: ['session'] });
    expect(session.cancelled).toBe(true);
    await shows('Deletion confirmed');
    expect(client.getQueryData(['account-deletion-status'])).toEqual(deleted);
  });
  it('aborts its owned request and discards private recovery cache on destroy', async () => {
    start();
    const request = await vi.waitFor(() => backend.expectOne(url));
    fixture.destroy();
    expect(request.cancelled).toBe(true);
    expect(client.getQueryData(['account-deletion-status'])).toBeUndefined();
  });
});
