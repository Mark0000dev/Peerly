import { jpegBase64 } from '../../../../testing/image-fixture';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../app.config';
import { DiscoveryPhoto } from './discovery-photo';
import { identity, card } from './discovery.fixtures';

@Component({
  selector: 'photo-test-host',
  imports: [DiscoveryPhoto],
  template:
    '@if (visible()) { <app-discovery-photo [actorId]="actor()" [personId]="person()" [version]="version()" name="Aiko" (failure)="failure($event)" (refresh)="refresh()" /> }',
})
class PhotoHost {
  public readonly visible = signal(true);
  public readonly actor = signal<string | null>(identity.account_id);
  public readonly person = signal<string>(card.id);
  public readonly version = signal(1);
  public readonly failure = vi.fn();
  public readonly refresh = vi.fn();
}
describe('current authorized JPEG resource lifecycle', () => {
  let fixture: ComponentFixture<PhotoHost>;
  let backend: HttpTestingController;
  let client: QueryClient;
  beforeEach(() => {
    client = new QueryClient();
    client.setQueryData(['session'], identity);
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideTanStackQuery(client)],
    });
    fixture = TestBed.createComponent(PhotoHost);
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
    const node: unknown = fixture.nativeElement;
    if (!(node instanceof HTMLElement)) throw new Error('Missinghost');
    return node;
  }
  function request(version = 1) {
    return backend.expectOne(`/api/v1/people/${card.id}/photo/${String(version)}`);
  }
  function jpeg(): Blob {
    return new Blob([Uint8Array.from(atob(jpegBase64), (character) => character.charCodeAt(0))], {
      type: 'image/jpeg',
    });
  }
  async function loaded(): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('img')).not.toBeNull();
    });
  }
  function retry(): void {
    const button = host().querySelector('button');
    if (button === null) throw new Error('Missingretry');
    button.click();
    fixture.detectChanges();
  }
  it('keeps object URLs out of cache and revokes on target version replacement and destroy', async () => {
    const original = URL.revokeObjectURL.bind(URL);
    const boundAtRetirement = vi.fn((url: string) =>
      Array.from(host().querySelectorAll('img')).some(
        (image: Readonly<HTMLImageElement>) =>
          image.isConnected && image.getAttribute('src') === url,
      ),
    );
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation((url) => {
      boundAtRetirement(url);
      original(url);
    });
    request().flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    await loaded();
    const first = host().querySelector('img')?.getAttribute('src');
    expect(first).toMatch(/^blob:/);
    expect(
      client.getQueryData(['account', identity.account_id, 'person-photo', card.id, 1]),
    ).toBeInstanceOf(Blob);
    fixture.componentInstance.version.set(2);
    fixture.detectChanges();
    expect(revoke).toHaveBeenCalledWith(first);
    request(2).flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    await loaded();
    const second = host().querySelector('img')?.getAttribute('src');
    expect(second).not.toBe(first);
    expect(boundAtRetirement).not.toHaveReturnedWith(true);
    fixture.destroy();
    await Promise.resolve();
    expect(revoke).toHaveBeenCalledWith(second);
  });
  it('keeps the displayed resource stable while the same bytes are being revalidated', async () => {
    const create = vi.spyOn(URL, 'createObjectURL');
    const revoke = vi.spyOn(URL, 'revokeObjectURL');
    request().flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    await loaded();
    const displayed = host().querySelector('img')?.getAttribute('src');
    expect(displayed).toMatch(/^blob:/);
    const initialCreations = create.mock.calls.length;
    const refreshed = client.invalidateQueries({
      queryKey: ['account', identity.account_id, 'person-photo', card.id],
    });
    const transfer = request();
    fixture.detectChanges();
    expect(host().querySelector('img')?.getAttribute('src')).toBe(displayed);
    expect(create).toHaveBeenCalledTimes(initialCreations);
    expect(revoke).not.toHaveBeenCalledWith(displayed);
    transfer.flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    await refreshed;
    await loaded();
  });
  it('releases the last URL after structural removal detaches its image', async () => {
    const original = URL.revokeObjectURL.bind(URL);
    const boundAtRetirement = vi.fn((url: string) =>
      Array.from(host().querySelectorAll('img')).some(
        (image: Readonly<HTMLImageElement>) =>
          image.isConnected && image.getAttribute('src') === url,
      ),
    );
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation((url) => {
      boundAtRetirement(url);
      original(url);
    });
    request().flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    await loaded();
    const displayed = host().querySelector('img')?.getAttribute('src');
    fixture.componentInstance.visible.set(false);
    fixture.detectChanges();
    expect(host().querySelector('img')).toBeNull();
    await Promise.resolve();
    expect(revoke).toHaveBeenCalledWith(displayed);
    expect(boundAtRetirement).not.toHaveReturnedWith(true);
  });
  it('replaces the actor without showing its former private image during the next transfer', async () => {
    request().flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    await loaded();
    client.setQueryData(['session'], { ...identity, account_id: 'replacement-actor' });
    fixture.componentInstance.actor.set('replacement-actor');
    fixture.detectChanges();
    expect(host().querySelector('img')).toBeNull();
    request().flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    await loaded();
  });
  it('404 rereads canonical person through its owner instead of repeating obsolete version', async () => {
    request().flush(new Blob(), { status: 404, statusText: 'Unavailable' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain('Retry photo');
    });
    retry();
    expect(fixture.componentInstance.refresh).toHaveBeenCalledOnce();
    backend.expectNone((r) => r.url.includes('/photo/'));
  });
  it('503 retries current bytes without replacing the profile', async () => {
    request().flush(new Blob(), { status: 503, statusText: 'Unavailable' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain('Retry photo');
    });
    retry();
    request().flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    await loaded();
    expect(fixture.componentInstance.refresh).not.toHaveBeenCalled();
  });
  it('decoder failure has explicit retry and duplicate retry is disabled during transfer', async () => {
    request().flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    await loaded();
    host().querySelector('img')?.dispatchEvent(new Event('error'));
    fixture.detectChanges();
    retry();
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('button')?.disabled).toBe(true);
    });
    host().querySelector('button')?.click();
    request().flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    await loaded();
  });
  it('actor removal cancels private reads and stale retry cannot issue another', () => {
    const pending = request();
    fixture.componentInstance.actor.set(null);
    fixture.detectChanges();
    expect(pending.cancelled).toBe(true);
    backend.expectNone((r) => r.url.includes('/photo/'));
  });
  it('a stale retry control cannot send for a removed actor or duplicate a transfer', async () => {
    request().flush(new Blob(), { status: 503, statusText: 'Unavailable' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('button')).not.toBeNull();
    });
    const stale = host().querySelector('button');
    if (stale === null) throw new Error('Missingretry');
    stale.click();
    stale.click();
    const pending = request();
    backend.expectNone((r) => r.url.includes('/photo/'));
    pending.flush(new Blob(), { status: 503, statusText: 'Unavailable' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('button')).not.toBeNull();
    });
    const old = host().querySelector('button');
    client.setQueryData(['session'], null);
    fixture.componentInstance.actor.set(null);
    old?.click();
    backend.expectNone((r) => r.url.includes('/photo/'));
    fixture.detectChanges();
  });
  it('late previous-actor JPEG failure cannot reauthorize the replacement account', async () => {
    const pending = request();
    client.setQueryData(['session'], { ...identity, account_id: 'replacement-actor' });
    pending.flush(new Blob(), { status: 401, statusText: 'Unauthorized' });
    await Promise.resolve();
    await Promise.resolve();
    fixture.detectChanges();
    expect(fixture.componentInstance.failure).not.toHaveBeenCalled();
  });
  it('revokes a formerly loaded JPEG when canonical refetch denies its current version', async () => {
    const revoke = vi.spyOn(URL, 'revokeObjectURL');
    request().flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    await loaded();
    const old = host().querySelector('img')?.getAttribute('src');
    void client.invalidateQueries({
      queryKey: ['account', identity.account_id, 'person-photo', card.id],
    });
    request().flush(new Blob(), { status: 404, statusText: 'Unavailable' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('img')).toBeNull();
      expect(host().textContent).toContain('Retry photo');
    });
    expect(revoke).toHaveBeenCalledWith(old);
  });
});
