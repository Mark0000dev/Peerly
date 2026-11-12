import { trustedChatActor } from './chats-session';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectorRef, Component, DestroyRef, inject, input, signal } from '@angular/core';
import type { OnChanges, OnInit } from '@angular/core';
import { TuiAvatar } from '@taiga-ui/kit/components/avatar';
import { TuiButton } from '@taiga-ui/core';
import { QueryClient, QueryObserver, queryOptions } from '@tanstack/angular-query-experimental';
import type {
  QueryFunctionContext,
  QueryCacheNotifyEvent,
} from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { ApiFailure, readJpeg } from '../../api-http';
import { ImageResource } from '../image-resource';

@Component({
  selector: 'app-chat-avatar',
  imports: [TuiButton, TuiAvatar],
  template: `
    @if (url(); as source) {
      <span tuiAvatar size="m" [round]="true">
        <img
          [src]="source"
          alt="Current chat participant photo"
          width="64"
          height="64"
          (error)="imageFailed()"
        />
      </span>
    }
    @if (failed() || query.isError) {
      <p role="status">Chat photo unavailable.</p>
      <button
        tuiButton
        type="button"
        size="s"
        [disabled]="query.isFetching"
        (click)="retry()"
        aria-label="Retry chat photo"
      >
        Retry
      </button>
    }
  `,
})
export class ChatAvatar implements OnChanges, OnInit {
  public readonly actorId = input.required<string>();
  public readonly conversationId = input.required<string>();
  public readonly peer = input.required<Api['schemas']['ChatParticipantResponse']>();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly destroy = inject(DestroyRef);
  private readonly change = inject(ChangeDetectorRef);
  private readonly resource = new ImageResource();
  protected readonly url = this.resource.url;
  protected readonly failed = signal(false);
  private readonly observer = new QueryObserver(this.client, this.options(null, '', null, false));
  protected get query() {
    return this.observer.getCurrentResult();
  }
  public ngOnInit(): void {
    const photo = this.observer.subscribe(() => {
      const bytes = this.query.data;
      if (this.trusted() && this.peer().state === 'available' && bytes !== undefined) {
        if (this.resource.replace(bytes)) this.failed.set(false);
      } else this.resource.clear();
      this.change.markForCheck();
      const error = this.query.error;
      if (error instanceof ApiFailure && error.status === 401 && this.trusted()) {
        this.client.setQueryData(['session'], null);
        this.client.removeQueries({ queryKey: ['account'] });
        void this.client.invalidateQueries({ queryKey: ['session'] });
      }
    });
    const session = this.client
      .getQueryCache()
      .subscribe((event: Readonly<QueryCacheNotifyEvent>) => {
        const key: unknown = event.query.queryKey;
        if (!Array.isArray(key) || key[0] !== 'session') return;
        this.sync();
      });
    this.destroy.onDestroy(() => {
      photo();
      session();
      this.observer.destroy();
    });
  }
  public ngOnChanges(): void {
    this.sync();
  }
  private trusted(): boolean {
    return trustedChatActor(this.client, this.actorId()) !== null;
  }

  private options(
    actorId: string | null,
    conversationId: string,
    version: number | null,
    enabled: boolean,
  ) {
    return queryOptions({
      queryKey: ['account', actorId, 'chats', conversationId, 'avatar', version] as const,
      enabled: enabled && actorId !== null && version !== null,
      retry: false,
      queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
        readJpeg(
          this.http,
          `/api/v1/conversations/${encodeURIComponent(conversationId)}/participant/avatar/${version?.toString() ?? ''}`,
          signal,
        ),
    });
  }
  private sync(): void {
    if (!this.trusted() || this.peer().state !== 'available') this.resource.clear();
    this.observer.setOptions(
      this.options(
        this.actorId(),
        this.conversationId(),
        this.peer().photo_version,
        this.trusted() && this.peer().state === 'available',
      ),
    );
  }
  protected imageFailed(): void {
    this.failed.set(true);
    this.resource.clear();
  }
  protected retry(): void {
    if (!this.trusted() || this.peer().state !== 'available' || this.peer().photo_version === null)
      return;
    this.failed.set(false);
    void this.observer.refetch();
  }
}
