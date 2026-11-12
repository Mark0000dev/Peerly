import type { HttpClient } from '@angular/common/http';
import type { QueryClient } from '@tanstack/angular-query-experimental';
import type { Api } from '../../../api.generated';
import { ApiFailure, writeJson } from '../../../api-http';
import { isTerminalOperation, operationOptions } from '../message-contract';
import type { TerminalMessageOperation } from '../message-contract';
import { imageSource, isImageReceipt, sameImageSource } from './image-contract';
import { preparationOptions } from './image-queries';
import { transferImage } from './image-transfer';

export interface ImageSendIntent {
  readonly actorId: string;
  readonly conversationId: string;
  readonly lifetime: object;
  readonly controller: AbortController;
  readonly file: Readonly<File> | null;
  readonly imageId: string | null;
  readonly clientMessageId: string;
  readonly startKey: string;
  readonly finalizeKey: string;
  readonly sendKey: string;
  readonly caption: string;
}

// Only a live explicit Send invokes this pipeline. Canonical GETs alone never
// create a command. All reads live in the inherited QueryClient; receipts are
// historical acknowledgements, never READY/sent projections.
export async function sendImage(
  http: Readonly<HttpClient>,
  client: Readonly<QueryClient>,
  intent: ImageSendIntent,
  authority: (intent: ImageSendIntent) => Api['schemas']['IdentityResponse'],
): Promise<TerminalMessageOperation> {
  const signal = intent.controller.signal;
  function actor(): Api['schemas']['IdentityResponse'] {
    signal.throwIfAborted();
    return authority(intent);
  }
  async function start(): Promise<string> {
    if (intent.imageId !== null) return intent.imageId;
    if (intent.file === null) throw new ApiFailure(0, 'image_reselect_required', null);
    const source = await imageSource(intent.file);
    const identity = actor();
    const receipt = await writeJson(
      http,
      `/api/v1/conversations/${encodeURIComponent(intent.conversationId)}/image-preparations`,
      { ...source, client_message_id: intent.clientMessageId },
      { 'x-csrf-token': identity.csrf_token, 'Idempotency-Key': intent.startKey },
      (value): value is Api['schemas']['ImagePreparationReceipt'] =>
        isImageReceipt(value) &&
        value.conversation_id === intent.conversationId &&
        value.client_message_id === intent.clientMessageId,
    );
    actor();
    return receipt.image_id;
  }
  const imageId = await start();
  const options = preparationOptions(
    http,
    client,
    intent.actorId,
    intent.conversationId,
    imageId,
    false,
  );
  async function current(): Promise<Api['schemas']['ImagePreparationResponse']> {
    actor();
    const value = await client.query({ ...options, staleTime: 0 });
    actor();
    if (value.client_message_id !== intent.clientMessageId)
      throw new ApiFailure(0, 'invalid_response', null);
    return value;
  }
  const first = await current();
  if (first.state === 'uploading' && first.message_outcome === null) {
    if (intent.file === null) throw new ApiFailure(0, 'image_reselect_required', null);
    if (!sameImageSource(await imageSource(intent.file), first.expected_source))
      throw new ApiFailure(0, 'image_source_changed', null);
    const identity = actor();
    await transferImage(
      http,
      intent.conversationId,
      imageId,
      identity.csrf_token,
      intent.file,
      signal,
    );
    const latestActor = actor();
    await writeJson(
      http,
      `/api/v1/conversations/${encodeURIComponent(intent.conversationId)}/image-preparations/${encodeURIComponent(imageId)}/finalize`,
      undefined,
      { 'x-csrf-token': latestActor.csrf_token, 'Idempotency-Key': intent.finalizeKey },
      (value): value is Api['schemas']['ImagePreparationReceipt'] =>
        isImageReceipt(value) &&
        value.conversation_id === intent.conversationId &&
        value.client_message_id === intent.clientMessageId &&
        value.image_id === imageId,
    );
    actor();
  }
  async function ready(): Promise<void> {
    const value = await current();
    if (value.message_outcome !== null || value.state === 'ready') return;
    if (value.state !== 'queued' && value.state !== 'processing')
      throw new ApiFailure(409, value.failure ?? `image_${value.state}`, null);
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => {
        signal.removeEventListener('abort', abort);
        resolve();
      }, 1500);
      function abort(): void {
        clearTimeout(timer);
        reject(new DOMException('Send retired', 'AbortError'));
      }
      signal.addEventListener('abort', abort, { once: true });
      if (signal.aborted) abort();
    });
    actor();
    await ready();
  }
  await ready();
  actor();
  const operation = await client.query({
    ...operationOptions(http, intent.actorId, intent.conversationId, intent.clientMessageId),
    staleTime: 0,
  });
  const identity = actor();
  if (isTerminalOperation(operation)) {
    if ('message' in operation && operation.message.image_id !== imageId)
      throw new ApiFailure(409, 'image_not_attached', null);
    return operation;
  }
  return writeJson(
    http,
    `/api/v1/conversations/${encodeURIComponent(intent.conversationId)}/messages`,
    {
      client_message_id: intent.clientMessageId,
      image_id: imageId,
      text: intent.caption.trim().length === 0 ? null : intent.caption,
    },
    { 'x-csrf-token': identity.csrf_token, 'Idempotency-Key': intent.sendKey },
    (value): value is TerminalMessageOperation =>
      isTerminalOperation(value) &&
      value.conversation_id === intent.conversationId &&
      value.client_message_id === intent.clientMessageId &&
      (!('message' in value) || value.message.image_id === imageId),
  );
}
