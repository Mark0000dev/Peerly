import type { HttpClient } from '@angular/common/http';
import { CancelledError, queryOptions } from '@tanstack/angular-query-experimental';
import type { QueryClient, QueryFunctionContext } from '@tanstack/angular-query-experimental';
import type { Api } from '../../../api.generated';
import { readJson } from '../../../api-http';
import { trustedChatActor } from '../chats-session';
import { isImagePreparation, isImagePreparations } from './image-contract';

export function preparationsOptions(
  http: Readonly<HttpClient>,
  client: Readonly<QueryClient>,
  actorId: string | null,
  conversationId: string,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', actorId, 'chats', conversationId, 'image-preparations'] as const,
    enabled: enabled && actorId !== null,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) => {
      if (actorId === null || trustedChatActor(client, actorId) === null)
        throw new CancelledError();
      return readJson(
        http,
        `/api/v1/conversations/${encodeURIComponent(conversationId)}/image-preparations`,
        signal,
        (value): value is Api['schemas']['ImagePreparationsResponse'] =>
          isImagePreparations(value) &&
          value.preparations.every((entry) => entry.conversation_id === conversationId),
      );
    },
  });
}
export function preparationOptions(
  http: Readonly<HttpClient>,
  client: Readonly<QueryClient>,
  actorId: string | null,
  conversationId: string,
  imageId: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', actorId, 'chats', conversationId, 'image-preparation', imageId] as const,
    enabled: enabled && actorId !== null && imageId !== null,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) => {
      if (actorId === null || imageId === null || trustedChatActor(client, actorId) === null)
        throw new CancelledError();
      return readJson(
        http,
        `/api/v1/conversations/${encodeURIComponent(conversationId)}/image-preparations/${encodeURIComponent(imageId)}`,
        signal,
        (value): value is Api['schemas']['ImagePreparationResponse'] =>
          isImagePreparation(value) &&
          value.conversation_id === conversationId &&
          value.image_id === imageId,
      );
    },
  });
}
