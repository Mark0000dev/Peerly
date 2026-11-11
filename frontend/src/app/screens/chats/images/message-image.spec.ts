import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, input } from '@angular/core';
import { TuiRoot } from '@taiga-ui/core';
import type { Api } from '../../../api.generated';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { provideTanStackQuery, QueryClient } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { jpegBase64 } from '../../../../../testing/image-fixture';
import { appConfig } from '../../../app.config';
import { identity, message } from '../chats.fixtures';
import { MessageImage } from './message-image';

@Component({
  selector: 'image-test-root',
  imports: [TuiRoot, MessageImage],
  template:
    '<tui-root><app-chat-message-image [actorId]="actorId()" [message]="message()" [authorLabel]="authorLabel()" /></tui-root>',
})
class ImageHost {
  public readonly actorId = input.required<string>();
  public readonly message = input.required<Api['schemas']['MessageResponse']>();
  public readonly authorLabel = input.required<string>();
}

const imageMessage = { ...message, image_id: '00000000-0000-4000-8000-000000000040' };
const url = `/api/v1/conversations/${message.conversation_id}/messages/${message.message_id}/image`;
describe('C03 authenticated participant image resource', () => {
  let fixture: ComponentFixture<ImageHost>;
  let backend: HttpTestingController;
  let client: QueryClient;
  beforeEach(() => {
    client = new QueryClient();
    client.setQueryData(['session'], identity);
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideTanStackQuery(client)],
    });
    backend = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(ImageHost);
    fixture.componentRef.setInput('actorId', identity.account_id);
    fixture.componentRef.setInput('message', imageMessage);
    fixture.componentRef.setInput('authorLabel', 'Maya Lim');
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
    if (!(node instanceof HTMLElement)) throw new Error('Missing image host');
    return node;
  }
  function jpeg(): Blob {
    return new Blob([Uint8Array.from(atob(jpegBase64), (character) => character.charCodeAt(0))], {
      type: 'image/jpeg',
    });
  }
  async function loaded(): Promise<string> {
    return vi.waitFor(() => {
      fixture.detectChanges();
      const image = host().querySelector('img');
      expect(image?.naturalWidth).toBeGreaterThan(0);
      if (image === null) throw new Error('Missing image');
      return image.src;
    });
  }
  function retry(): void {
    const button = Array.from(host().querySelectorAll('button')).find(
      (item: Readonly<HTMLButtonElement>) => item.textContent.trim() === 'Retry image',
    );
    if (button === undefined) throw new Error('Missing retry');
    button.click();
    fixture.detectChanges();
  }
  it('reads only the confirmed-message grant and preserves native URL across unrelated message redraws', async () => {
    const create = vi.spyOn(URL, 'createObjectURL');
    backend.expectOne(url).flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    const source = await loaded();
    fixture.componentRef.setInput('message', { ...imageMessage });
    fixture.detectChanges();
    expect(host().querySelector('img')?.src).toBe(source);
    expect(create).toHaveBeenCalledTimes(1);
    backend.expectNone(url);
    backend.expectNone((request) => request.url.includes('/people/'));
  });
  it('offers an explicit retry for network failure, does not use a fake fallback photo', async () => {
    backend.expectOne(url).flush(new Blob(['{}'], { type: 'application/json' }), {
      status: 503,
      statusText: 'Unavailable',
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain('couldn’t be displayed');
    });
    backend.expectNone(url);
    retry();
    (await vi.waitFor(() => backend.expectOne(url))).flush(jpeg(), {
      headers: { 'Content-Type': 'image/jpeg' },
    });
    await loaded();
  });
  it('clears/revokes decode failures and retires resources after actor replacement', async () => {
    const revoke = vi.spyOn(URL, 'revokeObjectURL');
    backend.expectOne(url).flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    const source = await loaded();
    host().querySelector('img')?.dispatchEvent(new Event('error'));
    fixture.detectChanges();
    expect(host().querySelector('img')).toBeNull();
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(revoke).toHaveBeenCalledWith(source);
    });
    retry();
    (await vi.waitFor(() => backend.expectOne(url))).flush(jpeg(), {
      headers: { 'Content-Type': 'image/jpeg' },
    });
    const next = await loaded();
    fixture.componentRef.setInput('actorId', crypto.randomUUID());
    fixture.detectChanges();
    expect(host().querySelector('img')).toBeNull();
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(revoke).toHaveBeenCalledWith(next);
    });
    backend.expectNone(url);
  });
  it('aborts an in-flight retired message query and does not display the previous attachment', () => {
    const pending = backend.expectOne(url);
    fixture.componentRef.setInput('message', { ...message });
    fixture.detectChanges();
    expect(pending.cancelled).toBe(true);
    expect(host().querySelector('img')).toBeNull();
  });
  it.each([401, 403])(
    'uses the canonical session boundary for current grant denial %i',
    async (status: number) => {
      backend
        .expectOne(url)
        .flush(new Blob(['{}'], { type: 'application/json' }), { status, statusText: 'Denied' });
      await vi.waitFor(() => {
        expect(client.getQueryData(['session'])).toBeNull();
      });
      fixture.detectChanges();
      expect(host().querySelector('img')).toBeNull();
    },
  );
  it('opens and closes the genuine public Preview and uses child report failures at the canonical session boundary', async () => {
    backend.expectOne(url).flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    await loaded();
    const open = Array.from(host().querySelectorAll('button')).find(
      (item: Readonly<HTMLButtonElement>) => item.textContent.trim() === 'View image',
    );
    if (open === undefined) throw new Error('Missing Preview action');
    open.click();
    fixture.detectChanges();
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(document.querySelector('tui-preview')).not.toBeNull();
    });
    const close = Array.from(document.querySelectorAll('button')).find(
      (item: Readonly<HTMLButtonElement>) => item.textContent.trim() === 'Close image',
    );
    if (close === undefined) throw new Error('Missing Preview close');
    close.click();
    fixture.detectChanges();
    const report = Array.from(host().querySelectorAll('button')).find(
      (item: Readonly<HTMLButtonElement>) => item.textContent.trim() === 'Report image',
    );
    if (report === undefined) throw new Error('Missing report action');
    report.click();
    fixture.detectChanges();
    (await vi.waitFor(() => backend.expectOne(url.replace('/image', '/report-contexts')))).flush(
      {},
      { status: 401, statusText: 'Unauthorized' },
    );
    await vi.waitFor(() => {
      expect(client.getQueryData(['session'])).toBeNull();
    });
  });
});
