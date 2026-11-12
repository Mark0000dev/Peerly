import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import {
  QueryClient,
  QueryObserver,
  provideTanStackQuery,
} from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Api } from '../../api.generated';
import { appConfig } from '../../app.config';
import { jpegBase64 } from '../../../../testing/image-fixture';
import { identity, request, page as requestsPage } from './requests.fixtures';
import { RequestAvatar } from './request-avatar';

@Component({
  selector: 'request-avatar-test-host',
  imports: [RequestAvatar],
  template: `@if (visible()) {
    <app-request-avatar [actorId]="actor()" [peer]="peer()" />
  }`,
})
class AvatarHost {
  public readonly visible = signal(true);
  public readonly actor = signal<string | null>(identity.account_id);
  public readonly peer = signal<Api['schemas']['RequestPeerResponse']>(request.peer);
}
const photoUrl = `/api/v1/people/${request.peer.person_id}/photo/1`;
function jpeg(): Blob {
  return new Blob([Uint8Array.from(atob(jpegBase64), (value) => value.charCodeAt(0))], {
    type: 'image/jpeg',
  });
}

describe('Request current public photo ownership', () => {
  let fixture: ComponentFixture<AvatarHost>;
  let http: HttpTestingController;
  let client: QueryClient;
  beforeEach(() => {
    client = new QueryClient();
    client.setQueryData(['session'], identity);
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideTanStackQuery(client)],
    });
    fixture = TestBed.createComponent(AvatarHost);
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });
  afterEach(() => {
    fixture.destroy();
    client.clear();
    http.verify({ ignoreCancelled: true });
    vi.restoreAllMocks();
    TestBed.resetTestingModule();
  });
  function host(): HTMLElement {
    const node: unknown = fixture.nativeElement;
    if (!(node instanceof HTMLElement)) throw new Error('Missing avatar host');
    return node;
  }
  async function read(url = photoUrl) {
    return vi.waitFor(() => http.expectOne(url));
  }
  async function loaded(): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('img')).not.toBeNull();
    });
  }
  async function failed(): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain('Photo unavailable.');
    });
  }
  function retryControl(): HTMLButtonElement {
    const control = host().querySelector('button[aria-label="Retry request photo"]');
    if (!(control instanceof HTMLButtonElement)) throw new Error('Missing explicit photo retry');
    return control;
  }
  function retry(): void {
    retryControl().click();
    fixture.detectChanges();
  }
  it('reads only current private JPEG and keeps Blob in shared actor key, never an object URL', async () => {
    const image = await read();
    expect(image.request.method).toBe('GET');
    expect(image.request.headers.has('X-CSRF-Token')).toBe(false);
    expect(image.request.headers.has('Idempotency-Key')).toBe(false);
    image.flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    await loaded();
    expect(host().querySelector('img')?.getAttribute('src')).toMatch(/^blob:/);
    expect(
      client.getQueryData([
        'account',
        identity.account_id,
        'person-photo',
        request.peer.person_id,
        1,
      ]),
    ).toBeInstanceOf(Blob);
    http.expectNone(`/api/v1/people/${request.peer.person_id}`);
    http.expectNone((item) => item.method !== 'GET');
  });
  it('404 retires the old source and invalidates only canonical Request reads without retrying its photo', async () => {
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    (await read()).flush(new Blob(), { status: 404, statusText: 'Not Found' });
    await failed();
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: ['account', identity.account_id, 'requests'],
    });
    expect(host().querySelector('button')).toBeNull();
    expect(
      client.getQueryData([
        'account',
        identity.account_id,
        'person-photo',
        request.peer.person_id,
        1,
      ]),
    ).toBeUndefined();
    fixture.componentInstance.peer.set({ ...request.peer });
    fixture.detectChanges();
    http.expectNone(photoUrl);
    fixture.componentInstance.peer.set({ ...request.peer, photo_version: 2 });
    fixture.detectChanges();
    (await read(`/api/v1/people/${request.peer.person_id}/photo/2`)).flush(jpeg(), {
      headers: { 'Content-Type': 'image/jpeg' },
    });
    await loaded();
    http.expectNone((item) => item.method !== 'GET');
  });
  it('does not interrupt a canonical Requests read already in progress when a photo version retires', async () => {
    let finish: (() => void) | undefined;
    const pending = new Promise<void>((resolve) => {
      finish = resolve;
    });
    const requests = new QueryObserver(client, {
      queryKey: ['account', identity.account_id, 'requests', 'received'],
      queryFn: async () => {
        await pending;
        return requestsPage;
      },
      retry: false,
    });
    const stop = requests.subscribe(() => undefined);
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    try {
      expect(client.isFetching({ queryKey: ['account', identity.account_id, 'requests'] })).toBe(1);
      (await read()).flush(new Blob(), { status: 404, statusText: 'Not Found' });
      await failed();
      expect(invalidate).not.toHaveBeenCalled();
      expect(requests.getCurrentResult().isFetching).toBe(true);
      expect(host().querySelector('button')).toBeNull();
      http.expectNone(photoUrl);
    } finally {
      finish?.();
      await pending;
      stop();
      requests.destroy();
    }
  });
  it('503 stays local and retries only after the explicit image control, once while fetching', async () => {
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    (await read()).flush(new Blob(), { status: 503, statusText: 'Unavailable' });
    await failed();
    expect(invalidate).not.toHaveBeenCalled();
    http.expectNone(photoUrl);
    const control = retryControl();
    control.click();
    control.click();
    fixture.detectChanges();
    (await read()).flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    await loaded();
    http.expectNone((item) => item.url.startsWith('/api/v1/requests'));
  });
  it('a decode failure removes the image and waits for explicit retry', async () => {
    (await read()).flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    await loaded();
    host().querySelector('img')?.dispatchEvent(new Event('error'));
    await failed();
    expect(host().querySelector('img')).toBeNull();
    http.expectNone(photoUrl);
    retry();
    (await read()).flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    await loaded();
  });
  it('a changed actor cancels old JPEG and a stale retry control cannot refetch it', async () => {
    (await read()).flush(new Blob(), { status: 503, statusText: 'Unavailable' });
    await failed();
    const stale = host().querySelector('button');
    client.setQueryData(['session'], { ...identity, account_id: 'replacement-actor' });
    fixture.detectChanges();
    stale?.click();
    http.expectNone(photoUrl);
    expect(host().querySelector('img')).toBeNull();
    fixture.componentInstance.actor.set('replacement-actor');
    fixture.detectChanges();
    const pending = await read();
    client.setQueryData(['session'], null);
    fixture.detectChanges();
    expect(pending.cancelled).toBe(true);
  });
  it('clears loaded pixels on session validation error even if old identity data remains cached', async () => {
    (await read()).flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    await loaded();
    const session = new QueryObserver(client, {
      queryKey: ['session'],
      queryFn: () => Promise.reject(new Error('controlled session failure')),
      retry: false,
    });
    await session.refetch();
    fixture.detectChanges();
    expect(client.getQueryState(['session'])?.status).toBe('error');
    expect(host().querySelector('img')).toBeNull();
    http.expectNone(photoUrl);
    session.destroy();
  });
  it('cancels obsolete version and unavailable/deleted/absent-version projections never fetch private bytes', async () => {
    const old = await read();
    fixture.componentInstance.peer.set({ ...request.peer, photo_version: 2 });
    fixture.detectChanges();
    expect(old.cancelled).toBe(true);
    const next = await read(`/api/v1/people/${request.peer.person_id}/photo/2`);
    fixture.componentInstance.peer.set({
      ...request.peer,
      state: 'unavailable',
      display_name: null,
      photo_version: null,
    });
    fixture.detectChanges();
    expect(next.cancelled).toBe(true);
    for (const peer of [
      { ...request.peer, state: 'deleted', display_name: null, photo_version: null },
      { ...request.peer, photo_version: null },
    ] satisfies readonly Api['schemas']['RequestPeerResponse'][]) {
      fixture.componentInstance.peer.set(peer);
      fixture.detectChanges();
      http.expectNone((item) => item.url.includes('/photo/'));
    }
  });
  it('401 retires the authenticated actor using the shared session read boundary', async () => {
    (await read()).flush(new Blob(), { status: 401, statusText: 'Unauthorized' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(client.getQueryData(['session'])).toBeNull();
      http.expectOne('/api/v1/me').flush({}, { status: 401, statusText: 'Unauthorized' });
    });
    http.expectNone(photoUrl);
    expect(host().querySelector('img')).toBeNull();
  });
  it('403 revalidates actual own authority rather than inventing a peer-unavailable cause', async () => {
    (await read()).flush(new Blob(), { status: 403, statusText: 'Forbidden' });
    const session = await read('/api/v1/me');
    session.flush({
      ...identity,
      capabilities: { ...identity.capabilities, can_use_student_features: false },
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('img')).toBeNull();
    });
    http.expectNone(photoUrl);
  });
  it('releases loaded object URL on unmount, after the old image is detached', async () => {
    const original = URL.revokeObjectURL.bind(URL);
    const stillBound = vi.fn((url: string) =>
      Array.from(host().querySelectorAll('img')).some(
        (image: Readonly<HTMLImageElement>) =>
          image.isConnected && image.getAttribute('src') === url,
      ),
    );
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation((url) => {
      stillBound(url);
      original(url);
    });
    (await read()).flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    await loaded();
    const source = host().querySelector('img')?.getAttribute('src');
    fixture.componentInstance.visible.set(false);
    fixture.detectChanges();
    await vi.waitFor(() => {
      expect(revoke).toHaveBeenCalledWith(source);
    });
    expect(stillBound).not.toHaveReturnedWith(true);
    expect(host().querySelector('img')).toBeNull();
  });
});
