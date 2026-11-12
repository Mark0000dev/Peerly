import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { TestRequest } from '@angular/common/http/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { provideTanStackQuery, QueryClient } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../../app.config';
import { identity, message } from '../chats.fixtures';
import { ImageSender } from './image-sender';
import { By } from '@angular/platform-browser';
import { TuiInputFilesDirective } from '@taiga-ui/kit/components/files';
import type { Api } from '../../../api.generated';
import { imageSource } from './image-contract';
import { jpegBase64 } from '../../../../../testing/image-fixture';

const base = `/api/v1/conversations/${message.conversation_id}`;
describe('C03 sender caption ownership and native selection', () => {
  let fixture: ComponentFixture<ImageSender>;
  let backend: HttpTestingController;
  let client: QueryClient;
  beforeEach(() => {
    client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(['session'], identity);
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideTanStackQuery(client)],
    });
    backend = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(ImageSender);
    fixture.componentRef.setInput('actor', identity);
    fixture.componentRef.setInput('conversationId', message.conversation_id);
    fixture.componentRef.setInput('canSend', true);
    fixture.detectChanges();
    backend.expectOne(`${base}/image-preparations`).flush({ preparations: [] });
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
  function choose(file: Readonly<File>): void {
    const input = host().querySelector('input');
    if (!(input instanceof HTMLInputElement)) throw new Error('Missing file picker');
    const transfer = new DataTransfer();
    transfer.items.add(file);
    Reflect.set(input, 'files', transfer.files);
    input.dispatchEvent(new Event('change', { bubbles: true }));
    fixture.detectChanges();
  }
  function button(label: string): HTMLButtonElement {
    const button = Array.from(host().querySelectorAll('button')).find(
      (item: Readonly<HTMLButtonElement>) => item.textContent.trim() === label,
    );
    if (button === undefined) throw new Error(`Missing button ${label}`);
    return button;
  }
  async function recover(state: Api['schemas']['ChatImageState']) {
    const preparation: Api['schemas']['ImagePreparationResponse'] = {
      client_message_id: message.client_message_id,
      conversation_id: message.conversation_id,
      image_id: '00000000-0000-4000-8000-000000000040',
      created_at: '2026-11-08T09:00:00Z',
      updated_at: '2026-11-08T09:00:00Z',
      upload_expires_at: '2026-11-08T10:00:00Z',
      processing_expires_at: '2026-11-08T10:00:00Z',
      display: state === 'ready' ? { width: 1, height: 1, size: 3 } : null,
      expected_source: await imageSource(new Blob(['abc'], { type: 'image/png' })),
      state,
      source_state: state,
      source_version: 1,
      failure: null,
      message_outcome: null,
    };
    void client.invalidateQueries({
      queryKey: [
        'account',
        identity.account_id,
        'chats',
        message.conversation_id,
        'image-preparations',
      ],
    });
    (await vi.waitFor(() => backend.expectOne(`${base}/image-preparations`))).flush({
      preparations: [preparation],
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('summary')).not.toBeNull();
    });
    host().querySelector('summary')?.click();
    button('Select preparation').click();
    fixture.detectChanges();
    if (state === 'ready') {
      (
        await vi.waitFor(() =>
          backend.expectOne(`${base}/image-preparations/${preparation.image_id}/display`),
        )
      ).flush(
        new Blob([Uint8Array.from(atob(jpegBase64), (character) => character.charCodeAt(0))], {
          type: 'image/jpeg',
        }),
        { headers: { 'Content-Type': 'image/jpeg' } },
      );
      await vi.waitFor(() => {
        fixture.detectChanges();
        expect(host().querySelector('img')?.naturalWidth).toBeGreaterThan(0);
      });
    }
    return preparation;
  }
  it('loads owner recovery without automatic commands, requires missing bytes and confirms real cancellation before replacement', async () => {
    await recover('uploading');
    expect(fixture.componentInstance.hasSelection).toBe(true);
    fixture.componentInstance.requestSend('caption');
    fixture.detectChanges();
    expect(host().textContent).toContain('Reselect the original image');
    backend.expectNone((request) => request.method === 'POST');
    button('Cancel selected preparation').click();
    const cancel = await vi.waitFor(() =>
      backend.expectOne(`${base}/message-operations/${message.client_message_id}/cancel`),
    );
    cancel.flush({}, { status: 503, statusText: 'Unavailable' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain('Cancellation is not confirmed');
    });
    button('Retry cancellation').click();
    const retry = await vi.waitFor(() => backend.expectOne(cancel.request.url));
    expect(retry.request.headers.get('Idempotency-Key')).toBe(
      cancel.request.headers.get('Idempotency-Key'),
    );
    retry.flush({
      conversation_id: message.conversation_id,
      client_message_id: message.client_message_id,
      operation_id: crypto.randomUUID(),
      outcome: 'cancelled',
      cancelled_at: '2026-11-08T09:00:00Z',
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(fixture.componentInstance.hasSelection).toBe(false);
    });
    (await vi.waitFor(() => backend.expectOne(`${base}/image-preparations`))).flush({
      preparations: [],
    });
  });
  it('sends a recovered READY image only after explicit Send and emits stored only on actual confirmation', async () => {
    const preparation = await recover('ready');
    const stored = vi.fn();
    fixture.componentInstance.stored.subscribe(stored);
    choose(new File(['changed'], 'other.png', { type: 'image/png' }));
    expect(host().textContent).toContain('Resolve this preparation');
    backend.expectNone((request) => request.method === 'POST');
    fixture.componentInstance.requestSend('');
    const url = `${base}/image-preparations/${preparation.image_id}`;
    (await vi.waitFor(() => backend.expectOne(url))).flush(preparation);
    (await vi.waitFor(() => backend.expectOne(url))).flush(preparation);
    (
      await vi.waitFor(() =>
        backend.expectOne(`${base}/message-operations/${message.client_message_id}`),
      )
    ).flush({
      conversation_id: message.conversation_id,
      client_message_id: message.client_message_id,
      outcome: 'unobserved',
    });
    expect(stored).not.toHaveBeenCalled();
    const send = await vi.waitFor(() => backend.expectOne(`${base}/messages`));
    expect(send.request.body).toEqual({
      client_message_id: message.client_message_id,
      image_id: preparation.image_id,
      text: null,
    });
    send.flush({
      conversation_id: message.conversation_id,
      client_message_id: message.client_message_id,
      operation_id: crypto.randomUUID(),
      outcome: 'confirmed',
      message: {
        ...message,
        author_id: identity.account_id,
        image_id: preparation.image_id,
        text: null,
      },
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(stored).toHaveBeenCalledTimes(1);
    });
    expect(fixture.componentInstance.hasSelection).toBe(false);
    (await vi.waitFor(() => backend.expectOne(`${base}/image-preparations`))).flush({
      preparations: [],
    });
  });
  async function temporaryValidation(mode: 'fetching' | 'error'): Promise<() => Promise<void>> {
    if (mode === 'error') {
      await expect(
        client.query({
          queryKey: ['session'],
          staleTime: 0,
          retry: false,
          queryFn: () => Promise.reject(new Error('Controlled session failure')),
        }),
      ).rejects.toThrow('Controlled session failure');
      return async () => {
        await client.query({
          queryKey: ['session'],
          staleTime: 0,
          retry: false,
          queryFn: () => Promise.resolve(identity),
        });
      };
    }
    let resolveSession: ((value: typeof identity) => void) | undefined;
    const validation = client.query({
      queryKey: ['session'],
      staleTime: 0,
      retry: false,
      queryFn: () =>
        new Promise<typeof identity>((resolve) => {
          resolveSession = resolve;
        }),
    });
    await vi.waitFor(() => {
      expect(client.getQueryState(['session'])?.fetchStatus).toBe('fetching');
    });
    return async () => {
      if (resolveSession === undefined) throw new Error('Missing session validation');
      resolveSession(identity);
      await validation;
    };
  }
  function flushCurrentReads(): void {
    for (const request of backend.match((request) => request.method === 'GET')) {
      if (request.request.responseType === 'blob') {
        request.flush(
          new Blob([Uint8Array.from(atob(jpegBase64), (character) => character.charCodeAt(0))], {
            type: 'image/jpeg',
          }),
          { headers: { 'Content-Type': 'image/jpeg' } },
        );
      } else request.flush({ preparations: [] });
    }
  }
  it.each(['fetching', 'error'] as const)(
    'settles its actual in-flight confirmed receipt once during same-actor %s without a new Send',
    async (mode) => {
      const preparation = await recover('ready');
      const stored = vi.fn();
      fixture.componentInstance.stored.subscribe(stored);
      fixture.componentInstance.requestSend('Keep the confirmed caption');
      const url = `${base}/image-preparations/${preparation.image_id}`;
      (await vi.waitFor(() => backend.expectOne(url))).flush(preparation);
      (await vi.waitFor(() => backend.expectOne(url))).flush(preparation);
      (
        await vi.waitFor(() =>
          backend.expectOne(`${base}/message-operations/${message.client_message_id}`),
        )
      ).flush({
        conversation_id: message.conversation_id,
        client_message_id: message.client_message_id,
        outcome: 'unobserved',
      });
      const send = await vi.waitFor(() => backend.expectOne(`${base}/messages`));
      const restore = await temporaryValidation(mode);
      try {
        send.flush({
          conversation_id: message.conversation_id,
          client_message_id: message.client_message_id,
          operation_id: crypto.randomUUID(),
          outcome: 'confirmed',
          message: {
            ...message,
            author_id: identity.account_id,
            image_id: preparation.image_id,
            text: 'Keep the confirmed caption',
          },
        });
        await vi.waitFor(() => {
          fixture.detectChanges();
          expect(stored).toHaveBeenCalledTimes(1);
          expect(fixture.componentInstance.hasSelection).toBe(false);
        });
        fixture.componentInstance.requestSend('No duplicate');
        backend.expectNone((request) => request.method === 'POST');
      } finally {
        await restore();
        flushCurrentReads();
      }
      expect(stored).toHaveBeenCalledTimes(1);
      fixture.componentInstance.requestSend('No duplicate');
      backend.expectNone((request) => request.method === 'POST');
    },
  );
  it('retries an uncertain start with the identical body/key and retires on canonical authentication failure', async () => {
    choose(new File(['abc'], 'image.png', { type: 'image/png' }));
    fixture.componentInstance.requestSend('immutable');
    const first = await vi.waitFor(() => backend.expectOne(`${base}/image-preparations`));
    first.flush({}, { status: 503, statusText: 'Unavailable' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain('Sending stopped');
    });
    fixture.componentInstance.requestSend('replacement');
    button('Retry image send').click();
    const retry = await vi.waitFor(() => backend.expectOne(`${base}/image-preparations`));
    expect(retry.request.body).toEqual(first.request.body);
    expect(retry.request.headers.get('Idempotency-Key')).toBe(
      first.request.headers.get('Idempotency-Key'),
    );
    retry.flush({}, { status: 401, statusText: 'Unauthorized' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(client.getQueryData(['session'])).toBeNull();
    });
    expect(fixture.componentInstance.hasSelection).toBe(false);
  });
  it('allows cancellation after canSend is revoked and reports send-won from the actual terminal operation', async () => {
    const preparation = await recover('ready');
    const stored = vi.fn();
    fixture.componentInstance.stored.subscribe(stored);
    fixture.componentInstance.requestSend('caption');
    const pending = await vi.waitFor(() =>
      backend.expectOne(`${base}/image-preparations/${preparation.image_id}`),
    );
    fixture.componentRef.setInput('canSend', false);
    fixture.detectChanges();
    button('Cancel image send').click();
    const cancel = await vi.waitFor(() =>
      backend.expectOne(`${base}/message-operations/${message.client_message_id}/cancel`),
    );
    cancel.flush({
      conversation_id: message.conversation_id,
      client_message_id: message.client_message_id,
      operation_id: crypto.randomUUID(),
      outcome: 'confirmed',
      message: { ...message, image_id: preparation.image_id },
    });
    pending.flush(preparation);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(stored).toHaveBeenCalledTimes(1);
      expect(fixture.componentInstance.pending).toBe(false);
    });
    expect(host().textContent).toContain('already sent');
    (await vi.waitFor(() => backend.expectOne(`${base}/image-preparations`))).flush({
      preparations: [],
    });
    expect(stored).toHaveBeenCalledTimes(1);
  });
  it('chooses, replaces and removes locally without a caption control or write request', async () => {
    expect(fixture.componentInstance.hasSelection).toBe(false);
    choose(new File(['first'], 'first.png', { type: 'image/png' }));
    const nativeControl = host().querySelector('input');
    expect(fixture.componentInstance.hasSelection).toBe(true);
    const old = host().querySelector('img')?.src;
    const revoke = vi.spyOn(URL, 'revokeObjectURL');
    choose(new File(['second'], 'second.jpg', { type: 'image/jpeg' }));
    expect(host().querySelector('img')?.src).not.toBe(old);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(revoke).toHaveBeenCalledWith(old);
    });
    button('Remove image').click();
    fixture.detectChanges();
    expect(fixture.componentInstance.hasSelection).toBe(false);
    expect(host().querySelector('input')?.files?.length).toBe(0);
    expect(host().querySelector('input')).toBe(nativeControl);
    expect(host().querySelector('textarea')).toBeNull();
    backend.expectNone((request) => request.method !== 'GET');
    choose(new File(['first'], 'first.png', { type: 'image/png' }));
    expect(fixture.componentInstance.hasSelection).toBe(true);
  });
  it('rejects invalid native files and never starts upload during selection', async () => {
    const rejected = vi.fn();
    fixture.debugElement
      .query(By.directive(TuiInputFilesDirective))
      .injector.get(TuiInputFilesDirective)
      .reject.subscribe(rejected);
    const invalidFile = new File(['x'], 'fake.png', { type: 'image/gif' });
    choose(invalidFile);
    await vi.waitFor(() => {
      expect(rejected).toHaveBeenCalledWith([invalidFile]);
    });
    expect(host().textContent).toContain('JPEG or PNG');
    expect(fixture.componentInstance.hasSelection).toBe(true);
    fixture.componentInstance.requestSend('Do not silently publish this caption');
    expect(fixture.componentInstance.pending).toBe(false);
    backend.expectNone((request) => request.method !== 'GET');
    choose(new File([], 'empty.png', { type: 'image/png' }));
    expect(host().textContent).toContain('not empty');
    fixture.componentInstance.requestSend('Still an invalid attachment');
    backend.expectNone((request) => request.method !== 'GET');
    button('Remove image').click();
    fixture.detectChanges();
    expect(fixture.componentInstance.hasSelection).toBe(false);
  });
  it('blocks a send without attachment or with an invalid caption', () => {
    fixture.componentInstance.requestSend('caption');
    choose(new File(['abc'], 'image.png', { type: 'image/png' }));
    fixture.componentInstance.requestSend('x'.repeat(2001));
    fixture.detectChanges();
    expect(host().textContent).toContain('2000');
    expect(fixture.componentInstance.pending).toBe(false);
    backend.expectNone((request) => request.method !== 'GET');
  });
  it('captures immutable caption once, locks replacement and cancels only through the actual operation', async () => {
    choose(new File(['abc'], 'image.png', { type: 'image/png' }));
    fixture.componentInstance.requestSend('original caption');
    expect(fixture.componentInstance.pending).toBe(true);
    fixture.componentInstance.requestSend('changed caption');
    const start = await vi.waitFor(() => backend.expectOne(`${base}/image-preparations`));
    const body: unknown = start.request.body;
    if (
      typeof body !== 'object' ||
      body === null ||
      !('client_message_id' in body) ||
      typeof body.client_message_id !== 'string'
    )
      throw new Error('Missing command');
    fixture.detectChanges();
    expect(host().querySelector('input')?.disabled).toBe(true);
    button('Cancel image send').click();
    const clientMessageId = body.client_message_id;
    const cancel = await vi.waitFor(() =>
      backend.expectOne(`${base}/message-operations/${clientMessageId}/cancel`),
    );
    cancel.flush({
      conversation_id: message.conversation_id,
      client_message_id: body.client_message_id,
      operation_id: crypto.randomUUID(),
      outcome: 'cancelled',
      cancelled_at: '2026-11-08T09:00:00Z',
    });
    start.flush({
      conversation_id: message.conversation_id,
      client_message_id: body.client_message_id,
      image_id: crypto.randomUUID(),
      receipt_state: 'uploading',
      receipt_version: 1,
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(fixture.componentInstance.pending).toBe(false);
    });
    expect(host().textContent).toContain('operation was cancelled');
    backend
      .match((request) => request.method === 'GET')
      .forEach((request: Readonly<TestRequest>) => {
        request.flush({ preparations: [] });
      });
    backend.expectNone(`${base}/messages`);
  });
  it('retires selected native resources on actor replacement and never transfers the old selection', async () => {
    choose(new File(['abc'], 'image.png', { type: 'image/png' }));
    const source = host().querySelector('img')?.src;
    const revoke = vi.spyOn(URL, 'revokeObjectURL');
    fixture.componentRef.setInput('actor', { ...identity, account_id: crypto.randomUUID() });
    fixture.detectChanges();
    expect(fixture.componentInstance.hasSelection).toBe(false);
    expect(host().querySelector('img')).toBeNull();
    expect(host().querySelector('input')?.files?.length).toBe(0);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(revoke).toHaveBeenCalledWith(source);
    });
    fixture.componentInstance.requestSend('old');
    backend.expectNone((request) => request.method !== 'GET');
  });
  it('honors authoritative canSend and resets selection when session authority disappears', () => {
    fixture.componentRef.setInput('canSend', false);
    fixture.detectChanges();
    choose(new File(['abc'], 'image.png', { type: 'image/png' }));
    expect(fixture.componentInstance.hasSelection).toBe(false);
    fixture.componentRef.setInput('canSend', true);
    fixture.detectChanges();
    choose(new File(['abc'], 'image.png', { type: 'image/png' }));
    client.setQueryData(['session'], null);
    fixture.detectChanges();
    expect(fixture.componentInstance.hasSelection).toBe(false);
    expect(host().querySelector('input')?.disabled).toBe(true);
  });
  it('keeps the actual selected File through same-actor session revalidation while blocking Send', async () => {
    choose(new File(['abc'], 'image.png', { type: 'image/png' }));
    const preview = host().querySelector('img')?.src;
    let resolveSession: ((value: typeof identity) => void) | undefined;
    const validation = client.query({
      queryKey: ['session'],
      staleTime: 0,
      retry: false,
      queryFn: () =>
        new Promise<typeof identity>((resolve) => {
          resolveSession = resolve;
        }),
    });
    await vi.waitFor(() => {
      expect(client.getQueryState(['session'])?.fetchStatus).toBe('fetching');
    });
    fixture.detectChanges();
    expect(fixture.componentInstance.hasSelection).toBe(true);
    expect(host().querySelector('img')?.src).toBe(preview);
    fixture.componentInstance.requestSend('Preserve this image');
    backend.expectNone((request) => request.method === 'POST');
    if (resolveSession === undefined) throw new Error('Missing session revalidation');
    resolveSession(identity);
    await validation;
    backend
      .match((request) => request.method === 'GET')
      .forEach((request: Readonly<TestRequest>) => {
        request.flush({ preparations: [] });
      });
    fixture.detectChanges();
    expect(fixture.componentInstance.hasSelection).toBe(true);
    expect(host().querySelector('img')?.src).toBe(preview);
    fixture.componentInstance.requestSend('Preserve this image');
    const started = await vi.waitFor(() => backend.expectOne(`${base}/image-preparations`));
    expect(started.request.body).toEqual(
      expect.objectContaining({ size: 3, content_type: 'image/png' }),
    );
    started.flush({}, { status: 503, statusText: 'Unavailable' });
    await vi.waitFor(() => {
      expect(fixture.componentInstance.pending).toBe(false);
    });
  });
  it('requires explicit retry after temporary command ineligibility and keeps the original intent', async () => {
    choose(new File(['abc'], 'image.png', { type: 'image/png' }));
    fixture.componentInstance.requestSend('Original immutable caption');
    const first = await vi.waitFor(() => backend.expectOne(`${base}/image-preparations`));
    first.flush({}, { status: 503, statusText: 'Unavailable' });
    await vi.waitFor(() => {
      expect(fixture.componentInstance.pending).toBe(false);
    });
    fixture.componentRef.setInput('canSend', false);
    fixture.detectChanges();
    fixture.componentRef.setInput('canSend', true);
    fixture.detectChanges();
    backend.expectNone((request) => request.method === 'POST');
    button('Retry image send').click();
    const retry = await vi.waitFor(() => backend.expectOne(`${base}/image-preparations`));
    expect(retry.request.body).toEqual(first.request.body);
    expect(retry.request.headers.get('Idempotency-Key')).toBe(
      first.request.headers.get('Idempotency-Key'),
    );
    retry.flush({}, { status: 503, statusText: 'Unavailable' });
    await vi.waitFor(() => {
      expect(fixture.componentInstance.pending).toBe(false);
    });
    expect(fixture.componentInstance.hasSelection).toBe(true);
  });
  it('preserves the local File after failed same-actor validation without granting stale authority', async () => {
    choose(new File(['abc'], 'image.png', { type: 'image/png' }));
    const preview = host().querySelector('img')?.src;
    await expect(
      client.query({
        queryKey: ['session'],
        staleTime: 0,
        retry: false,
        queryFn: () => Promise.reject(new Error('Controlled session network failure')),
      }),
    ).rejects.toThrow('Controlled session network failure');
    fixture.detectChanges();
    expect(client.getQueryState(['session'])?.status).toBe('error');
    expect(fixture.componentInstance.hasSelection).toBe(true);
    expect(host().querySelector('img')?.src).toBe(preview);
    fixture.componentInstance.requestSend('Keep the attachment');
    backend.expectNone((request) => request.method === 'POST');
    await client.query({
      queryKey: ['session'],
      staleTime: 0,
      retry: false,
      queryFn: () => Promise.resolve(identity),
    });
    backend
      .match((request) => request.method === 'GET')
      .forEach((request: Readonly<TestRequest>) => {
        request.flush({ preparations: [] });
      });
    fixture.detectChanges();
    expect(fixture.componentInstance.hasSelection).toBe(true);
    expect(host().querySelector('img')?.src).toBe(preview);
    fixture.componentInstance.requestSend('Keep the attachment');
    const started = await vi.waitFor(() => backend.expectOne(`${base}/image-preparations`));
    expect(started.request.body).toEqual(
      expect.objectContaining({ size: 3, content_type: 'image/png' }),
    );
    started.flush({}, { status: 503, statusText: 'Unavailable' });
    await vi.waitFor(() => {
      expect(fixture.componentInstance.pending).toBe(false);
    });
  });
  it('offers explicit owner-collection retry and uses the canonical boundary for a later denied owner read', async () => {
    void client.invalidateQueries({
      queryKey: ['account', identity.account_id, 'chats', message.conversation_id],
    });
    (await vi.waitFor(() => backend.expectOne(`${base}/image-preparations`))).flush(
      {},
      { status: 503, statusText: 'Unavailable' },
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain('couldn’t be checked');
    });
    button('Retry image preparations').click();
    (await vi.waitFor(() => backend.expectOne(`${base}/image-preparations`))).flush(
      {},
      { status: 403, statusText: 'Forbidden' },
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(client.getQueryData(['session'])).toBeNull();
    });
    expect(fixture.componentInstance.hasSelection).toBe(false);
  });
  it('keeps recovery of queued and processing owner entries explicit and refuses a stale selection after it becomes terminal', async () => {
    const entry = await recover('queued');
    backend.expectNone((request) => request.method !== 'GET');
    void client.invalidateQueries({
      queryKey: ['account', identity.account_id, 'chats', message.conversation_id],
    });
    (await vi.waitFor(() => backend.expectOne(`${base}/image-preparations`))).flush({
      preparations: [{ ...entry, state: 'processing', source_state: 'processing' }],
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain('Last checked preparation: processing');
    });
    backend.expectNone((request) => request.method !== 'GET');
    button('Cancel selected preparation').click();
    const cancel = await vi.waitFor(() =>
      backend.expectOne(`${base}/message-operations/${message.client_message_id}/cancel`),
    );
    cancel.flush({
      conversation_id: message.conversation_id,
      client_message_id: message.client_message_id,
      operation_id: crypto.randomUUID(),
      cancelled_at: '2026-11-08T09:00:00Z',
    });
    (await vi.waitFor(() => backend.expectOne(`${base}/image-preparations`))).flush({
      preparations: [],
    });
  });
  it('retains a recovered operation across collection eviction and explicitly reselects missing bytes without replacing its caption', async () => {
    const entry = await recover('uploading');
    void client.invalidateQueries({
      queryKey: ['account', identity.account_id, 'chats', message.conversation_id],
    });
    (await vi.waitFor(() => backend.expectOne(`${base}/image-preparations`))).flush({
      preparations: [],
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain('Its current state will be checked');
    });
    fixture.componentInstance.requestSend('Original recovered caption');
    const url = `${base}/image-preparations/${entry.image_id}`;
    (await vi.waitFor(() => backend.expectOne(url))).flush(entry);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain('Reselect the original image, then retry');
    });
    expect(fixture.componentInstance.locked).toBe(true);
    expect(host().querySelector('input')?.disabled).toBe(false);
    choose(new File(['abc'], 'original.png', { type: 'image/png' }));
    fixture.componentInstance.requestSend('Must not replace original caption');
    button('Retry image send').click();
    (await vi.waitFor(() => backend.expectOne(url))).flush(entry);
    (await vi.waitFor(() => backend.expectOne(`${url}/upload-access`))).flush({
      url: 'https://storage.example.test/recovery',
      fields: {},
    });
    (await vi.waitFor(() => backend.expectOne('https://storage.example.test/recovery'))).flush('', {
      status: 204,
      statusText: 'No Content',
    });
    (await vi.waitFor(() => backend.expectOne(`${url}/finalize`))).flush({
      conversation_id: entry.conversation_id,
      client_message_id: entry.client_message_id,
      image_id: entry.image_id,
      receipt_state: 'queued',
      receipt_version: 2,
    });
    (await vi.waitFor(() => backend.expectOne(url))).flush({
      ...entry,
      state: 'ready',
      source_state: 'ready',
      display: { width: 1, height: 1, size: 1 },
    });
    (
      await vi.waitFor(() =>
        backend.expectOne(`${base}/message-operations/${entry.client_message_id}`),
      )
    ).flush({
      conversation_id: entry.conversation_id,
      client_message_id: entry.client_message_id,
      outcome: 'unobserved',
    });
    const send = await vi.waitFor(() => backend.expectOne(`${base}/messages`));
    expect(send.request.body).toEqual({
      client_message_id: entry.client_message_id,
      image_id: entry.image_id,
      text: 'Original recovered caption',
    });
    send.flush({
      conversation_id: entry.conversation_id,
      client_message_id: entry.client_message_id,
      operation_id: crypto.randomUUID(),
      outcome: 'confirmed',
      message: {
        ...message,
        image_id: entry.image_id,
        client_message_id: entry.client_message_id,
        text: 'Original recovered caption',
      },
    });
    (await vi.waitFor(() => backend.expectOne(`${base}/image-preparations`))).flush({
      preparations: [],
    });
  });
  it('uses the canonical session boundary when the selected owner preview is denied', async () => {
    const entry = await recover('ready');
    void client.invalidateQueries({
      queryKey: [
        'account',
        identity.account_id,
        'chats',
        message.conversation_id,
        'preparation-image',
      ],
    });
    (
      await vi.waitFor(() =>
        backend.expectOne(`${base}/image-preparations/${entry.image_id}/display`),
      )
    ).flush(new Blob(['{}'], { type: 'application/json' }), {
      status: 401,
      statusText: 'Unauthorized',
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(client.getQueryData(['session'])).toBeNull();
    });
    expect(fixture.componentInstance.hasSelection).toBe(false);
  });
});
