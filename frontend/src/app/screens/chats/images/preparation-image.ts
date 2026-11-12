import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectorRef,
  Component,
  DestroyRef,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import type { OnChanges, OnInit } from '@angular/core';
import { TuiButton } from '@taiga-ui/core';
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
import { trustedChatActor } from '../chats-session';

@Component({
  selector: 'app-chat-preparation-image',
  imports: [TuiButton],
  template: `
    @if (url(); as source) {
      <img
        [src]="source"
        alt="Preview of your selected prepared image"
        (error)="imageFailed($event)"
      />
    } @else if (query.isFetching) {
      <p role="status">Loading your prepared image…</p>
    }
    @if (query.isError || failed()) {
      <p role="status">Your prepared image couldn’t be displayed.</p>
      <button tuiButton type="button" size="s" [disabled]="query.isFetching" (click)="retry()">
        Retry prepared image
      </button>
    }
  `,
  styles:
    ':host { display: block; min-inline-size: 0; } img { max-inline-size: 100%; max-block-size: 16rem; object-fit: contain; }',
})
export class PreparationImage implements OnChanges, OnInit {
  public readonly actorId = input.required<string>();
  public readonly preparation = input.required<Api['schemas']['ImagePreparationResponse']>();
  public readonly sessionFailure = output<ApiFailure>();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly destroy = inject(DestroyRef);
  private readonly change = inject(ChangeDetectorRef);
  private readonly resource = new ImageResource();
  private readonly decodeError = signal(false);
  protected readonly failed = this.decodeError.asReadonly();
  protected readonly url = this.resource.url;
  private readonly observer = new QueryObserver(
    this.client,
    this.options(null, '', '', null, false),
  );
  protected get query() {
    return this.observer.getCurrentResult();
  }
  public ngOnInit(): void {
    const image = this.observer.subscribe(() => {
      this.render();
      const error = this.query.error;
      if (
        !this.destroy.destroyed &&
        this.trusted() &&
        error instanceof ApiFailure &&
        (error.status === 401 || error.status === 403)
      )
        this.sessionFailure.emit(error);
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
    const preparation = this.preparation();
    if (
      key[1] !== this.actorId() ||
      key[3] !== preparation.conversation_id ||
      key[5] !== preparation.image_id ||
      key[6] !== preparation.source_version
    ) {
      this.resource.clear();
      this.decodeError.set(false);
    }
    this.sync();
  }
  private trusted(): boolean {
    return trustedChatActor(this.client, this.actorId()) !== null;
  }
  private render(): void {
    const result = this.query;
    if (
      this.trusted() &&
      this.preparation().state === 'ready' &&
      result.isSuccess &&
      !this.failed()
    )
      this.resource.replace(result.data);
    else this.resource.clear();
  }
  private options(
    actorId: string | null,
    conversationId: string,
    imageId: string,
    version: number | null,
    enabled: boolean,
  ) {
    return queryOptions({
      queryKey: [
        'account',
        actorId,
        'chats',
        conversationId,
        'preparation-image',
        imageId,
        version,
      ] as const,
      enabled,
      retry: false,
      staleTime: Infinity,
      gcTime: 0,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      queryFn: ({ signal }: Readonly<QueryFunctionContext>) => {
        if (actorId === null || trustedChatActor(this.client, actorId) === null)
          throw new CancelledError();
        return readJpeg(
          this.http,
          `/api/v1/conversations/${encodeURIComponent(conversationId)}/image-preparations/${encodeURIComponent(imageId)}/display`,
          signal,
        );
      },
    });
  }
  private sync(): void {
    const preparation = this.preparation();
    const eligible = this.trusted() && preparation.state === 'ready';
    this.observer.setOptions(
      this.options(
        eligible ? this.actorId() : null,
        preparation.conversation_id,
        preparation.image_id,
        preparation.source_version,
        eligible,
      ),
    );
    this.render();
  }
  protected imageFailed(event: Readonly<Event>): void {
    if (!(event.target instanceof HTMLImageElement) || event.target.src !== this.url()) return;
    this.decodeError.set(true);
    this.resource.clear();
  }
  protected retry(): void {
    if (!this.trusted() || this.preparation().state !== 'ready') return;
    this.decodeError.set(false);
    this.resource.clear();
    void this.observer.refetch();
  }
}
