import { HttpClient, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { QueryClient } from '@tanstack/angular-query-experimental';
import type { Query } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Api } from '../../../api.generated';
import { identity, message } from '../chats.fixtures';
import { imageSource } from './image-contract';
import { sendImage } from './image-send';
import type { ImageSendIntent } from './image-send';

const imageId = '00000000-0000-4000-8000-000000000040';
const stamp = '2026-11-08T09:00:00Z';
const base = `/api/v1/conversations/${message.conversation_id}`;
const preparationUrl = `${base}/image-preparations/${imageId}`;
const file = new File(['abc'], 'private-name.png', { type: 'image/png' });
const operation = {
  conversation_id: message.conversation_id,
  client_message_id: message.client_message_id,
  operation_id: '00000000-0000-4000-8000-000000000050',
  outcome: 'confirmed',
  message: { ...message, author_id: identity.account_id, image_id: imageId, text: 'caption' },
} as const;

describe('C03 explicit immutable Send pipeline', () => {
  let http: HttpClient;
  let backend: HttpTestingController;
  let client: QueryClient;
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
    client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(['session'], identity);
  });
  afterEach(() => {
    client.clear();
    backend.verify({ ignoreCancelled: true });
    TestBed.resetTestingModule();
  });
  function intent(patch: Partial<ImageSendIntent> = {}): ImageSendIntent {
    return {
      actorId: identity.account_id,
      conversationId: message.conversation_id,
      lifetime: {},
      controller: new AbortController(),
      file,
      imageId: null,
      clientMessageId: message.client_message_id,
      startKey: 'start-key',
      finalizeKey: 'finalize-key',
      sendKey: 'send-key',
      caption: 'caption',
      ...patch,
    };
  }
  async function canonical(state: Api['schemas']['ChatImageState'] = 'ready') {
    return {
      client_message_id: message.client_message_id,
      conversation_id: message.conversation_id,
      image_id: imageId,
      created_at: stamp,
      updated_at: stamp,
      processing_expires_at: stamp,
      upload_expires_at: stamp,
      source_version: 2,
      source_state: state,
      state,
      failure: null,
      display: state === 'ready' ? { width: 1, height: 1, size: 1 } : null,
      message_outcome: null,
      expected_source: await imageSource(file),
    } as const;
  }
  async function request(url: string) {
    return vi.waitFor(() => backend.expectOne(url));
  }
  async function start() {
    const request = await vi.waitFor(() => backend.expectOne(`${base}/image-preparations`));
    expect(request.request.headers.get('Idempotency-Key')).toBe('start-key');
    expect(request.request.body).toEqual({
      ...(await imageSource(file)),
      client_message_id: message.client_message_id,
    });
    request.flush({
      client_message_id: message.client_message_id,
      conversation_id: message.conversation_id,
      image_id: imageId,
      receipt_state: 'ready',
      receipt_version: 1,
    });
  }
  async function sendOutcome() {
    const lookup = await request(`${base}/message-operations/${message.client_message_id}`);
    lookup.flush({
      client_message_id: message.client_message_id,
      conversation_id: message.conversation_id,
      outcome: 'unobserved',
    });
    const send = await request(`${base}/messages`);
    expect(send.request.headers.get('Idempotency-Key')).toBe('send-key');
    expect(send.request.body).toEqual({
      client_message_id: message.client_message_id,
      image_id: imageId,
      text: 'caption',
    });
    send.flush(operation);
  }
  it('ignores receipt READY, transfers actual bytes, finalizes, then explicitly confirms storage', async () => {
    const promise = sendImage(http, client, intent(), () => identity);
    await start();
    (await request(preparationUrl)).flush(await canonical('uploading'));
    const access = await request(`${preparationUrl}/upload-access`);
    expect(access.request.body).toBeNull();
    access.flush({ url: 'https://storage.example.test/form', fields: { policy: 'private' } });
    (await request('https://storage.example.test/form')).flush('', {
      status: 204,
      statusText: 'No Content',
    });
    const finalize = await request(`${preparationUrl}/finalize`);
    expect(finalize.request.body).toBeNull();
    expect(finalize.request.headers.get('Idempotency-Key')).toBe('finalize-key');
    finalize.flush({
      client_message_id: message.client_message_id,
      conversation_id: message.conversation_id,
      image_id: imageId,
      receipt_state: 'queued',
      receipt_version: 2,
    });
    (await request(preparationUrl)).flush(await canonical());
    await sendOutcome();
    await expect(promise).resolves.toEqual(operation);
    expect(
      JSON.stringify(
        client
          .getQueryCache()
          .getAll()
          .map((query: Readonly<Query>) => query.state.data),
      ),
    ).not.toContain('private');
  });
  it('resumes READY only from explicit user intent and does not require old file bytes', async () => {
    const promise = sendImage(http, client, intent({ imageId, file: null }), () => identity);
    (await request(preparationUrl)).flush(await canonical());
    (await request(preparationUrl)).flush(await canonical());
    backend.expectNone(`${base}/image-preparations`);
    backend.expectNone(`${preparationUrl}/upload-access`);
    await sendOutcome();
    await expect(promise).resolves.toEqual(operation);
  });
  it('returns an existing cancel-won outcome and never posts another message', async () => {
    const promise = sendImage(http, client, intent({ imageId, file: null }), () => identity);
    (await request(preparationUrl)).flush(await canonical());
    (await request(preparationUrl)).flush(await canonical());
    const cancelled = {
      client_message_id: message.client_message_id,
      conversation_id: message.conversation_id,
      operation_id: operation.operation_id,
      outcome: 'cancelled',
      cancelled_at: stamp,
    };
    (await request(`${base}/message-operations/${message.client_message_id}`)).flush(cancelled);
    await expect(promise).resolves.toEqual(cancelled);
    backend.expectNone(`${base}/messages`);
  });
  it('returns send-won without replaying a new command', async () => {
    const promise = sendImage(http, client, intent({ imageId }), () => identity);
    (await request(preparationUrl)).flush(await canonical());
    (await request(preparationUrl)).flush(await canonical());
    (await request(`${base}/message-operations/${message.client_message_id}`)).flush(operation);
    await expect(promise).resolves.toEqual(operation);
    backend.expectNone(`${base}/messages`);
  });
  it('requires the original missing file and rejects changed actual bytes before requesting access', async () => {
    for (const selected of [null, new File(['abd'], 'same.png', { type: 'image/png' })]) {
      const promise = sendImage(http, client, intent({ imageId, file: selected }), () => identity);
      const checked = expect(promise).rejects.toMatchObject({
        code: selected === null ? 'image_reselect_required' : 'image_source_changed',
      });
      (await request(preparationUrl)).flush(await canonical('uploading'));
      await checked;
      backend.expectNone(`${preparationUrl}/upload-access`);
    }
  });
  it('requires an actual file to start and retires before any request if user intent is aborted', async () => {
    await expect(
      sendImage(http, client, intent({ file: null }), () => identity),
    ).rejects.toMatchObject({ code: 'image_reselect_required' });
    const selected = intent();
    selected.controller.abort();
    await expect(sendImage(http, client, selected, () => identity)).rejects.toMatchObject({
      name: 'AbortError',
    });
    backend.expectNone(`${base}/image-preparations`);
  });
  it('does not continue after late actor/route retirement despite an arriving canonical response', async () => {
    const selected = intent({ imageId });
    const promise = sendImage(http, client, selected, () => identity);
    const checked = expect(promise).rejects.toMatchObject({ name: 'AbortError' });
    const read = await request(preparationUrl);
    selected.controller.abort();
    read.flush(await canonical());
    await checked;
    backend.expectNone(`${base}/messages`);
  });
  it('rejects failed effective state even when the historical source is READY', async () => {
    const promise = sendImage(http, client, intent({ imageId }), () => identity);
    const checked = expect(promise).rejects.toMatchObject({ code: 'content_changed', status: 409 });
    const value = {
      ...(await canonical('rejected')),
      source_state: 'ready',
      failure: 'content_changed',
    };
    (await request(preparationUrl)).flush(value);
    (await request(preparationUrl)).flush(value);
    await checked;
    backend.expectNone(`${base}/messages`);
  });
  it('polls genuine queued/processing state without claiming storage, then uses explicit Send intent', async () => {
    const promise = sendImage(http, client, intent({ imageId }), () => identity);
    (await request(preparationUrl)).flush(await canonical('queued'));
    (await request(preparationUrl)).flush(await canonical('processing'));
    backend.expectNone(`${base}/messages`);
    (await vi.waitFor(() => backend.expectOne(preparationUrl), { timeout: 3000 })).flush(
      await canonical(),
    );
    await sendOutcome();
    await expect(promise).resolves.toEqual(operation);
  });
  it('cancels the pending poll timer when its explicit live intent is retired', async () => {
    const selected = intent({ imageId });
    const promise = sendImage(http, client, selected, () => identity);
    const checked = expect(promise).rejects.toMatchObject({ name: 'AbortError' });
    (await request(preparationUrl)).flush(await canonical('queued'));
    (await request(preparationUrl)).flush(await canonical('processing'));
    await vi.waitFor(() => {
      expect(
        client.getQueryState([
          'account',
          identity.account_id,
          'chats',
          message.conversation_id,
          'image-preparation',
          imageId,
        ])?.fetchStatus,
      ).toBe('idle');
    });
    selected.controller.abort();
    await checked;
    backend.expectNone(`${base}/messages`);
  });
  it('rejects a canonical preparation bound to a different message intent', async () => {
    const promise = sendImage(http, client, intent({ imageId }), () => identity);
    const checked = expect(promise).rejects.toMatchObject({ code: 'invalid_response' });
    (await request(preparationUrl)).flush({
      ...(await canonical()),
      client_message_id: crypto.randomUUID(),
    });
    await checked;
    backend.expectNone(`${base}/messages`);
  });
  it('resolves the operation for a consumed preparation without transferring or resending', async () => {
    const promise = sendImage(http, client, intent({ imageId }), () => identity);
    const value = {
      ...(await canonical('cancelled')),
      message_outcome: {
        attachment_confirmed: false,
        message_id: null,
        operation_id: operation.operation_id,
        outcome: 'cancelled',
      },
    };
    (await request(preparationUrl)).flush(value);
    (await request(preparationUrl)).flush(value);
    const cancelled = {
      conversation_id: message.conversation_id,
      client_message_id: message.client_message_id,
      operation_id: operation.operation_id,
      outcome: 'cancelled',
      cancelled_at: stamp,
    };
    (await request(`${base}/message-operations/${message.client_message_id}`)).flush(cancelled);
    await expect(promise).resolves.toEqual(cancelled);
  });
  it('does not claim image storage when an existing operation confirmed a different attachment', async () => {
    const promise = sendImage(http, client, intent({ imageId }), () => identity);
    const checked = expect(promise).rejects.toMatchObject({
      status: 409,
      code: 'image_not_attached',
    });
    (await request(preparationUrl)).flush(await canonical());
    (await request(preparationUrl)).flush(await canonical());
    (await request(`${base}/message-operations/${message.client_message_id}`)).flush({
      ...operation,
      message: { ...operation.message, image_id: null },
    });
    await checked;
    backend.expectNone(`${base}/messages`);
  });
});
