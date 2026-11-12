import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { TuiRoot } from '@taiga-ui/core';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../app.config';
import type { Api } from '../../api.generated';
import { jpegBase64 } from '../../../../testing/image-fixture';
import { identity, message, peer } from './chats.fixtures';
import { ConfirmedMessage } from './confirmed-message';
@Component({
  selector: 'read-test-host',
  imports: [TuiRoot, ConfirmedMessage],
  template:
    '<tui-root><app-confirmed-chat-message [actor]="actor()" [peer]="peer" [message]="message()" [active]="active()" [readThrough]="through()" /></tui-root>',
})
class ReadHost {
  public readonly actor = signal(identity);
  public readonly peer = peer;
  public readonly message = signal<Api['schemas']['MessageResponse']>(message);
  public readonly active = signal(true);
  public readonly through = signal(0);
}
describe('C02 genuinely visible explicit private read position', () => {
  let fixture: ComponentFixture<ReadHost>;
  let backend: HttpTestingController;
  let client: QueryClient;
  const url = `/api/v1/conversations/${message.conversation_id}/read-position`;
  beforeEach(() => {
    client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    client.setQueryData(['session'], identity);
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideTanStackQuery(client)],
    });
    fixture = TestBed.createComponent(ReadHost);
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
  async function displayed(): Promise<HTMLButtonElement> {
    host().querySelector('p')?.scrollIntoView({ block: 'center' });
    return vi.waitFor(() => {
      fixture.detectChanges();
      const button = host().querySelector('button');
      if (button === null) throw new Error('Missing ACK');
      expect(button.disabled).toBe(false);
      return button;
    });
  }
  it('does not ACK render/background data, only the visible confirmed sequence after a click', async () => {
    const button = await displayed();
    backend.expectNone(url);
    expect(host().textContent).not.toContain('read receipt');
    button.click();
    const request = await vi.waitFor(() => backend.expectOne(url));
    expect(request.request.method).toBe('PUT');
    expect(request.request.body).toEqual({ through_sequence: 1 });
    expect(request.request.headers.get('X-CSRF-Token')).toBe(identity.csrf_token);
    request.flush({
      conversation_id: message.conversation_id,
      through_sequence: 1,
      acknowledged_at: message.sent_at,
      version: 1,
    });
    fixture.componentInstance.through.set(1);
    fixture.detectChanges();
    expect(host().querySelector('button')).toBeNull();
  });
  it.each([null, '<b>literal image caption</b>'] as const)(
    'renders a confirmed image as valid block content and never ACKs its authenticated read automatically: %s',
    async (caption) => {
      fixture.destroy();
      fixture = TestBed.createComponent(ReadHost);
      fixture.componentInstance.message.set({
        ...message,
        image_id: '00000000-0000-4000-8000-000000000040',
        text: caption,
      });
      fixture.detectChanges();
      const read = await vi.waitFor(() =>
        backend.expectOne(
          `/api/v1/conversations/${message.conversation_id}/messages/${message.message_id}/image`,
        ),
      );
      expect(read.request.method).toBe('GET');
      read.flush(
        new Blob([Uint8Array.from(atob(jpegBase64), (character) => character.charCodeAt(0))], {
          type: 'image/jpeg',
        }),
        { headers: { 'Content-Type': 'image/jpeg' } },
      );
      await vi.waitFor(() => {
        fixture.detectChanges();
        const image = host().querySelector('img');
        expect(image?.naturalWidth).toBeGreaterThan(0);
      });
      expect(host().querySelector('p figure')).toBeNull();
      expect(host().querySelector('span figure')).toBeNull();
      expect(host().querySelector('b')).toBeNull();
      if (caption !== null) expect(host().textContent).toContain(caption);
      backend.expectNone(url);
      host().querySelector('figure')?.scrollIntoView({ block: 'center' });
      const button = await vi.waitFor(() => {
        fixture.detectChanges();
        const action = host().querySelector('[aria-label="Mark read through this message"]');
        if (!(action instanceof HTMLButtonElement)) throw new Error('Missing explicit ACK action');
        expect(action.disabled).toBe(false);
        return action;
      });
      button.click();
      const acknowledgement = await vi.waitFor(() => backend.expectOne(url));
      expect(acknowledgement.request.method).toBe('PUT');
      expect(acknowledgement.request.body).toEqual({ through_sequence: message.sequence });
      acknowledgement.flush({
        conversation_id: message.conversation_id,
        through_sequence: message.sequence,
        acknowledged_at: message.sent_at,
        version: 1,
      });
      const refresh = await vi.waitFor(() =>
        backend.expectOne(
          `/api/v1/conversations/${message.conversation_id}/messages/${message.message_id}/image`,
        ),
      );
      await vi.waitFor(() => {
        fixture.detectChanges();
        expect(host().textContent).not.toContain('Updating your read position');
      });
      refresh.flush(
        new Blob([JSON.stringify({ code: 'unavailable' })], { type: 'application/problem+json' }),
        {
          status: 503,
          statusText: 'Unavailable',
          headers: { 'Content-Type': 'application/problem+json' },
        },
      );
    },
  );
  it('keeps the same receipt key for explicit retry after an unknown response', async () => {
    (await displayed()).click();
    const first = await vi.waitFor(() => backend.expectOne(url));
    const key = first.request.headers.get('Idempotency-Key');
    first.flush({}, { status: 503, statusText: 'Unavailable' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain('We couldn’t confirm your read position.');
    });
    (await displayed()).click();
    const retry = await vi.waitFor(() => backend.expectOne(url));
    expect(retry.request.headers.get('Idempotency-Key')).toBe(key);
    retry.flush({
      conversation_id: message.conversation_id,
      through_sequence: 1,
      acknowledged_at: message.sent_at,
      version: 1,
    });
  });
  it('rejects hidden document and inactive/current-session transitions without an ACK', async () => {
    const button = await displayed();
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    button.click();
    backend.expectNone(url);
    vi.restoreAllMocks();
    fixture.componentInstance.active.set(false);
    fixture.detectChanges();
    button.click();
    backend.expectNone(url);
    fixture.componentInstance.active.set(true);
    fixture.detectChanges();
    client.setQueryData(['session'], { ...identity, account_id: 'other' });
    button.click();
    backend.expectNone(url);
  });
  it('revalidates a current401 without a peer read receipt', async () => {
    (await displayed()).click();
    const request = await vi.waitFor(() => backend.expectOne(url));
    request.flush({}, { status: 401, statusText: 'Unauthorized' });
    await vi.waitFor(() => {
      expect(client.getQueryData(['session'])).toBeNull();
    });
  });
});
