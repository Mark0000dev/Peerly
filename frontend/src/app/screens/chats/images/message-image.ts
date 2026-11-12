import { HttpClient } from '@angular/common/http';
import { ChangeDetectorRef, Component, DestroyRef, inject, input, signal } from '@angular/core';
import type { OnChanges, OnInit } from '@angular/core';
import { TuiButton } from '@taiga-ui/core';
import { TuiPreview } from '@taiga-ui/kit';
import {
  CancelledError,
  QueryClient,
  QueryObserver,
  queryOptions,
} from '@tanstack/angular-query-experimental';
import type {
  QueryCacheNotifyEvent,
  QueryFunctionContext,
} from '@tanstack/angular-query-experimental';
import type { Api } from '../../../api.generated';
import { ApiFailure, readJpeg } from '../../../api-http';
import { ImageResource } from '../../image-resource';
import { absoluteChatTime } from '../chats-date';
import { trustedChatActor } from '../chats-session';
import { ImageReport } from './image-report';

@Component({
  selector: 'app-chat-message-image',
  imports: [TuiButton, TuiPreview, ImageReport],
  templateUrl: './message-image.html',
  styleUrl: './message-image.less',
})
export class MessageImage implements OnInit, OnChanges {
  public readonly actorId = input.required<string>();
  public readonly message = input.required<Api['schemas']['MessageResponse']>();
  public readonly authorLabel = input.required<string>();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly resource = new ImageResource();
  private readonly viewing = signal(false);
  private readonly decodeError = signal(false);
  protected readonly open = this.viewing.asReadonly();
  protected readonly failed = this.decodeError.asReadonly();
  protected readonly url = this.resource.url;
  protected readonly absoluteChatTime = absoluteChatTime;
  private readonly observer = new QueryObserver(
    this.client,
    this.options(null, '', '', null, false),
  );
  protected get query() {
    return this.observer.getCurrentResult();
  }
  public ngOnInit(): void {
    const image = this.observer.subscribe(() => {
      this.renderImage();
      const result = this.query;
      const error = result.error;
      if (
        error instanceof ApiFailure &&
        (error.status === 401 || error.status === 403) &&
        this.trusted()
      ) {
        this.client.setQueryData(['session'], null);
        this.client.removeQueries({ queryKey: ['account', this.actorId()] });
        void this.client.invalidateQueries({ queryKey: ['session'] });
      }
      this.change.markForCheck();
    });
    const session = this.client
      .getQueryCache()
      .subscribe((event: Readonly<QueryCacheNotifyEvent>) => {
        const key: unknown = event.query.queryKey;
        if (Array.isArray(key) && key[0] === 'session') this.sync();
      });
    this.destroy.onDestroy(() => {
      image();
      session();
      this.observer.destroy();
    });
  }
  public ngOnChanges(): void {
    const key = this.observer.options.queryKey;
    const message = this.message();
    if (
      key[1] !== this.actorId() ||
      key[3] !== message.conversation_id ||
      key[5] !== message.message_id ||
      key[6] !== message.image_id
    ) {
      this.viewing.set(false);
      this.resource.clear();
      this.decodeError.set(false);
    }
    this.sync();
  }
  private trusted(): boolean {
    return trustedChatActor(this.client, this.actorId()) !== null;
  }
  private renderImage(): void {
    const result = this.query;
    if (
      this.trusted() &&
      this.message().image_id !== null &&
      result.isSuccess &&
      !this.failed() &&
      (!result.isFetching || this.url() !== null)
    ) {
      this.resource.replace(result.data);
    } else {
      this.resource.clear();
      this.viewing.set(false);
    }
  }
  private options(
    actorId: string | null,
    conversationId: string,
    messageId: string,
    imageId: string | null,
    enabled: boolean,
  ) {
    return queryOptions({
      queryKey: [
        'account',
        actorId,
        'chats',
        conversationId,
        'message-image',
        messageId,
        imageId,
      ] as const,
      enabled,
      retry: false,
      staleTime: Infinity,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      queryFn: ({ signal }: Readonly<QueryFunctionContext>) => {
        if (actorId === null || trustedChatActor(this.client, actorId) === null)
          throw new CancelledError();
        return readJpeg(
          this.http,
          `/api/v1/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}/image`,
          signal,
        );
      },
    });
  }
  private sync(): void {
    const trusted = this.trusted();
    if (!trusted || this.message().image_id === null) {
      this.resource.clear();
      this.viewing.set(false);
    }
    this.observer.setOptions(
      this.options(
        this.actorId(),
        this.message().conversation_id,
        this.message().message_id,
        this.message().image_id,
        trusted && this.message().image_id !== null,
      ),
    );
    this.renderImage();
  }
  protected show(): void {
    if (this.trusted() && this.url() !== null && !this.failed()) this.viewing.set(true);
  }
  protected close(): void {
    this.viewing.set(false);
  }
  protected imageFailed(event: Readonly<Event>): void {
    const image = event.target;
    if (!(image instanceof HTMLImageElement) || image.src !== this.url()) return;
    this.decodeError.set(true);
    this.resource.clear();
    this.viewing.set(false);
  }
  protected retry(): void {
    if (!this.trusted()) return;
    this.resource.clear();
    this.decodeError.set(false);
    void this.observer.refetch();
  }
  protected sessionFailed(): void {
    if (!this.trusted()) return;
    this.client.setQueryData(['session'], null);
    this.client.removeQueries({ queryKey: ['account', this.actorId()] });
    void this.client.invalidateQueries({ queryKey: ['session'] });
  }
}
