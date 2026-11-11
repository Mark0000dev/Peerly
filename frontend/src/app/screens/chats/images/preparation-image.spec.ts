import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { provideTanStackQuery, QueryClient } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { jpegBase64 } from '../../../../../testing/image-fixture';
import type { Api } from '../../../api.generated';
import { appConfig } from '../../../app.config';
import { identity, message } from '../chats.fixtures';
import { PreparationImage } from './preparation-image';

const preparation: Api['schemas']['ImagePreparationResponse'] = {
  image_id: '00000000-0000-4000-8000-000000000040',
  conversation_id: message.conversation_id,
  client_message_id: message.client_message_id,
  created_at: '2026-11-08T09:00:00Z',
  updated_at: '2026-11-08T09:00:00Z',
  upload_expires_at: '2026-11-08T10:00:00Z',
  processing_expires_at: '2026-11-08T10:00:00Z',
  source_version: 1,
  source_state: 'ready',
  state: 'ready',
  expected_source: { content_type: 'image/jpeg', sha256: 'a'.repeat(64), size: 3 },
  display: { width: 2, height: 2, size: 3 },
  failure: null,
  message_outcome: null,
};
const base = `/api/v1/conversations/${preparation.conversation_id}/image-preparations`;
const url = `${base}/${preparation.image_id}/display`;
describe('C03 actual owner READY JPEG grant', () => {
  let fixture: ComponentFixture<PreparationImage>;
  let backend: HttpTestingController;
  let client: QueryClient;
  beforeEach(() => {
    client = new QueryClient();
    client.setQueryData(['session'], identity);
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideTanStackQuery(client)],
    });
    backend = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(PreparationImage);
    fixture.componentRef.setInput('actorId', identity.account_id);
    fixture.componentRef.setInput('preparation', preparation);
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
    if (!(node instanceof HTMLElement)) throw new Error('Missing owner image host');
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
      if (image === null) throw new Error('Missing owner JPEG');
      return image.src;
    });
  }
  it('uses only the selected owner display route and retains native URL across unrelated redraws', async () => {
    const create = vi.spyOn(URL, 'createObjectURL');
    backend.expectOne(url).flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    const source = await loaded();
    fixture.componentRef.setInput('preparation', { ...preparation });
    fixture.detectChanges();
    expect(host().querySelector('img')?.src).toBe(source);
    expect(create).toHaveBeenCalledTimes(1);
    backend.expectNone(
      (request) => request.url.includes('/messages/') || request.url.includes('/people/'),
    );
    expect(
      client.getQueryData([
        'account',
        identity.account_id,
        'chats',
        preparation.conversation_id,
        'preparation-image',
        preparation.image_id,
        1,
      ]),
    ).toBeInstanceOf(Blob);
  });
  it('binds Blob identity to actual source version and revokes the old handle after DOM replacement', async () => {
    const revoke = vi.spyOn(URL, 'revokeObjectURL');
    backend.expectOne(url).flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    const old = await loaded();
    fixture.componentRef.setInput('preparation', { ...preparation, source_version: 2 });
    fixture.detectChanges();
    expect(host().querySelector('img')).toBeNull();
    (await vi.waitFor(() => backend.expectOne(url))).flush(jpeg(), {
      headers: { 'Content-Type': 'image/jpeg' },
    });
    expect(await loaded()).not.toBe(old);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(revoke).toHaveBeenCalledWith(old);
    });
  });
  it('offers explicit retry for grant failure and actual image decoding failure', async () => {
    backend.expectOne(url).flush(new Blob(['{}'], { type: 'application/json' }), {
      status: 404,
      statusText: 'Not Found',
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain('couldn’t be displayed');
    });
    host().querySelector('button')?.click();
    (await vi.waitFor(() => backend.expectOne(url))).flush(
      new Blob(['bad jpeg'], { type: 'image/jpeg' }),
      { headers: { 'Content-Type': 'image/jpeg' } },
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('img')).toBeNull();
      expect(host().textContent).toContain('couldn’t be displayed');
    });
    host().querySelector('button')?.click();
    (await vi.waitFor(() => backend.expectOne(url))).flush(jpeg(), {
      headers: { 'Content-Type': 'image/jpeg' },
    });
    await loaded();
  });
  it('aborts an active owner read and clears native data on session/actor retirement', async () => {
    const pending = backend.expectOne(url);
    client.setQueryData(['session'], null);
    fixture.detectChanges();
    expect(pending.cancelled).toBe(true);
    expect(host().querySelector('img')).toBeNull();
    client.setQueryData(['session'], identity);
    fixture.detectChanges();
    (await vi.waitFor(() => backend.expectOne(url))).flush(jpeg(), {
      headers: { 'Content-Type': 'image/jpeg' },
    });
    const source = await loaded();
    const revoke = vi.spyOn(URL, 'revokeObjectURL');
    fixture.componentRef.setInput('actorId', crypto.randomUUID());
    fixture.detectChanges();
    expect(host().querySelector('img')).toBeNull();
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(revoke).toHaveBeenCalledWith(source);
    });
    backend.expectNone(url);
  });
  it('retires non-READY, image and conversation replacements without sharing an owner grant', async () => {
    const pending = backend.expectOne(url);
    fixture.componentRef.setInput('preparation', { ...preparation, state: 'processing' });
    fixture.detectChanges();
    expect(pending.cancelled).toBe(true);
    backend.expectNone(url);
    const next = { ...preparation, image_id: crypto.randomUUID() };
    fixture.componentRef.setInput('preparation', next);
    fixture.detectChanges();
    const read = await vi.waitFor(() => backend.expectOne(`${base}/${next.image_id}/display`));
    const other = { ...next, conversation_id: crypto.randomUUID() };
    fixture.componentRef.setInput('preparation', other);
    fixture.detectChanges();
    expect(read.cancelled).toBe(true);
    (
      await vi.waitFor(() =>
        backend.expectOne(
          `/api/v1/conversations/${other.conversation_id}/image-preparations/${other.image_id}/display`,
        ),
      )
    ).flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    await loaded();
  });
  it.each([401, 403])(
    'emits current authorization denial %i to the existing session boundary',
    async (status: number) => {
      const failure = vi.fn();
      fixture.componentInstance.sessionFailure.subscribe(failure);
      backend
        .expectOne(url)
        .flush(new Blob(['{}'], { type: 'application/json' }), { status, statusText: 'Denied' });
      await vi.waitFor(() => {
        expect(failure).toHaveBeenCalledTimes(1);
      });
      expect(host().querySelector('img')).toBeNull();
    },
  );
});
