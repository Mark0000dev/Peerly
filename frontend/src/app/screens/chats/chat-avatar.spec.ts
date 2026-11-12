import { jpegBase64 } from '../../../../testing/image-fixture';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../app.config';
import { conversation, identity, peer } from './chats.fixtures';
import { ChatAvatar } from './chat-avatar';

@Component({
  selector: 'chat-avatar-test-host',
  imports: [ChatAvatar],
  template:
    '@if (shown()) { <app-chat-avatar [actorId]="actor()" [conversationId]="conversation()" [peer]="peer()" /> }',
})
class AvatarHost {
  public readonly actor = signal(identity.account_id);
  public readonly conversation = signal(conversation.conversation_id);
  public readonly peer = signal({ ...peer, photo_version: 1 });
  public readonly shown = signal(true);
}
describe('Chat grant JPEG native resource ownership', () => {
  let fixture: ComponentFixture<AvatarHost>;
  let backend: HttpTestingController;
  let client: QueryClient;
  const url = `/api/v1/conversations/${conversation.conversation_id}/participant/avatar/1`;
  beforeEach(() => {
    TestBed.resetTestingModule();
    client = new QueryClient({
      defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
    });
    client.setQueryData(['session'], identity);
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideTanStackQuery(client)],
    });
    fixture = TestBed.createComponent(AvatarHost);
    backend = TestBed.inject(HttpTestingController);
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
    const node: unknown = fixture.nativeElement;
    if (!(node instanceof HTMLElement)) throw new Error('Missing host');
    return node;
  }
  function jpeg(): Blob {
    return new Blob([Uint8Array.from(atob(jpegBase64), (char) => char.charCodeAt(0))], {
      type: 'image/jpeg',
    });
  }
  async function loaded(): Promise<string> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('img')?.complete).toBe(true);
      expect(host().querySelector('img')?.naturalWidth).toBeGreaterThan(0);
    });
    const source = host().querySelector('img')?.src;
    if (source === undefined) throw new Error('Missing image');
    return source;
  }
  it('uses only the conversation grant and preserves URL until replacement bytes render', async () => {
    const create = vi.spyOn(URL, 'createObjectURL');
    const revoke = vi.spyOn(URL, 'revokeObjectURL');
    backend.expectOne(url).flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    const old = await loaded();
    backend.expectNone((request) => request.url.includes('/people/'));
    void client.invalidateQueries({ queryKey: ['account', identity.account_id, 'chats'] });
    const next = await vi.waitFor(() => backend.expectOne(url));
    fixture.detectChanges();
    expect(host().querySelector('img')?.src).toBe(old);
    expect(create).toHaveBeenCalledTimes(1);
    expect(revoke).not.toHaveBeenCalled();
    next.flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    const updated = await vi.waitFor(async () => {
      const source = await loaded();
      expect(source).not.toBe(old);
      return source;
    });
    expect(updated).not.toBe(old);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(revoke).toHaveBeenCalledWith(old);
    });
  });
  it('clears and revokes after structural removal and never renders a previous actor photo', async () => {
    const revoke = vi.spyOn(URL, 'revokeObjectURL');
    backend.expectOne(url).flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    const old = await loaded();
    fixture.componentInstance.shown.set(false);
    fixture.detectChanges();
    expect(host().querySelector('img')).toBeNull();
    await vi.waitFor(() => {
      expect(revoke).toHaveBeenCalledWith(old);
    });
  });
  it('offers explicit retry for read failure and native load failure without auto retries', async () => {
    backend.expectOne(url).flush(new Blob(['{}'], { type: 'application/json' }), {
      status: 503,
      statusText: 'Unavailable',
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain('Chat photo unavailable.');
    });
    backend.expectNone(url);
    host().querySelector('button')?.click();
    const retry = await vi.waitFor(() => backend.expectOne(url));
    retry.flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    await loaded();
    host().querySelector('img')?.dispatchEvent(new Event('error'));
    fixture.detectChanges();
    expect(host().querySelector('img')).toBeNull();
    expect(host().textContent).toContain('Chat photo unavailable.');
    host().querySelector('button')?.click();
    const again = await vi.waitFor(() => backend.expectOne(url));
    again.flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    await loaded();
  });
  it('clears actor replacement and revalidates only the current actor401', async () => {
    backend.expectOne(url).flush(new Blob(['{}'], { type: 'application/json' }), {
      status: 401,
      statusText: 'Unauthorized',
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(client.getQueryData(['session'])).toBeNull();
    });
    expect(host().querySelector('img')).toBeNull();
    fixture.componentInstance.actor.set('new-actor');
    fixture.detectChanges();
    backend.expectNone(url);
  });
});
