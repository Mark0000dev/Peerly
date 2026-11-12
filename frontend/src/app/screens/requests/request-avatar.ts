import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectorRef,
  Component,
  DestroyRef,
  effect,
  inject,
  input,
  signal,
  untracked,
} from '@angular/core';
import { TuiButton } from '@taiga-ui/core';
import { TuiAvatar } from '@taiga-ui/kit/components/avatar';
import {
  CancelledError,
  QueryClient,
  QueryObserver,
  queryOptions,
} from '@tanstack/angular-query-experimental';
import type {
  QueryFunctionContext,
  QueryCacheNotifyEvent,
} from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { ApiFailure, readJpeg } from '../../api-http';
import { ImageResource } from '../image-resource';
import { sessionOptions } from '../session';
import { trustedVerifiedActor } from '../verified-actor';

interface PhotoSource {
  readonly actorId: string;
  readonly personId: string;
  readonly version: number;
}
function sameSource(first: PhotoSource | null, second: PhotoSource | null): boolean {
  return (
    first?.actorId === second?.actorId &&
    first?.personId === second?.personId &&
    first?.version === second?.version
  );
}

@Component({
  selector: 'app-request-avatar',
  imports: [TuiAvatar, TuiButton],
  template: `
    @if (url(); as source) {
      <span tuiAvatar size="m" [round]="true">
        <img
          [src]="source"
          alt="Current request participant photo"
          width="64"
          height="64"
          (error)="imageFailed()"
        />
      </span>
    } @else {
      <span tuiAvatar="@tui.user" size="m" [round]="true" aria-hidden="true"></span>
    }
    @if (unavailable) {
      <p role="status">Photo unavailable.</p>
      @if (retryable) {
        <button
          tuiButton
          appearance="flat"
          size="s"
          type="button"
          aria-label="Retry request photo"
          [disabled]="photo.isFetching"
          (click)="retry()"
        >
          Retry photo
        </button>
      }
    }
  `,
  styles: `
    :host {
      display: grid;
      justify-items: start;
      gap: 0.25rem;
      min-inline-size: 0;
    }
    p {
      margin: 0;
      font: var(--tui-typography-body-xs);
    }
  `,
})
export class RequestAvatar {
  public readonly actorId = input.required<string | null>();
  public readonly peer = input.required<Api['schemas']['RequestPeerResponse']>();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly destroy = inject(DestroyRef);
  private readonly change = inject(ChangeDetectorRef);
  private readonly resource = new ImageResource();
  protected readonly url = this.resource.url;
  protected readonly failed = signal(false);
  // Binding/rejected-image identity only; server bytes stay in the shared query.
  private readonly bound = signal<PhotoSource | null>(null);
  private readonly retired = signal<PhotoSource | null>(null);
  private readonly observer = new QueryObserver(this.client, this.options(null));
  protected get photo() {
    return this.observer.getCurrentResult();
  }
  protected get unavailable(): boolean {
    return (
      this.failed() ||
      this.photo.isError ||
      (this.bound() !== null && sameSource(this.bound(), this.retired()))
    );
  }
  protected get retryable(): boolean {
    const error = this.photo.error;
    return (
      this.accepts(this.bound()) &&
      !sameSource(this.bound(), this.retired()) &&
      (this.failed() ||
        (error instanceof ApiFailure &&
          (error.status === 0 || error.status === 408 || error.status >= 500)))
    );
  }
  public constructor() {
    const photo = this.observer.subscribe(() => {
      this.paint();
    });
    const session = this.client
      .getQueryCache()
      .subscribe((event: Readonly<QueryCacheNotifyEvent>) => {
        const key: unknown = event.query.queryKey;
        if (!Array.isArray(key) || key[0] !== 'session') return;
        this.sync();
      });
    effect(() => {
      this.actorId();
      this.peer();
      untracked(() => {
        this.sync();
      });
    });
    this.destroy.onDestroy(() => {
      photo();
      session();
      this.observer.destroy();
      this.resource.clear();
    });
  }
  private source(): PhotoSource | null {
    const actorId = this.actorId();
    const peer = this.peer();
    if (
      actorId === null ||
      peer.state !== 'public' ||
      peer.photo_version === null ||
      !Number.isSafeInteger(peer.photo_version) ||
      peer.photo_version < 1 ||
      trustedVerifiedActor(this.client, actorId)?.capabilities.can_use_student_features !== true
    )
      return null;
    return { actorId, personId: peer.person_id, version: peer.photo_version };
  }
  private accepts(source: PhotoSource | null): boolean {
    return source !== null && !this.destroy.destroyed && sameSource(source, this.source());
  }
  private key(source: PhotoSource) {
    return ['account', source.actorId, 'person-photo', source.personId, source.version] as const;
  }
  private options(source: PhotoSource | null) {
    return queryOptions({
      queryKey: source === null ? (['request-avatar-idle'] as const) : this.key(source),
      enabled: source !== null,
      retry: false,
      gcTime: 0,
      staleTime: 0,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      refetchOnMount: false,
      queryFn: ({ signal }: Readonly<QueryFunctionContext>) => {
        if (source === null || !this.accepts(source) || sameSource(source, this.retired()))
          throw new CancelledError();
        return readJpeg(
          this.http,
          `/api/v1/people/${encodeURIComponent(source.personId)}/photo/${String(source.version)}`,
          signal,
        );
      },
    });
  }
  private sync(): void {
    if (this.destroy.destroyed) return;
    const source = this.source();
    if (sameSource(source, this.bound())) return;
    this.resource.clear();
    this.failed.set(false);
    this.bound.set(source);
    this.observer.setOptions(this.options(sameSource(source, this.retired()) ? null : source));
    this.change.markForCheck();
  }
  private paint(): void {
    const source = this.bound();
    if (source === null || !this.accepts(source) || sameSource(source, this.retired())) {
      this.resource.clear();
      this.change.markForCheck();
      return;
    }
    const result = this.photo;
    if (
      result.isSuccess &&
      !result.isFetching &&
      this.client.getQueryData<Readonly<Blob>>(this.key(source)) === result.data
    ) {
      if (this.resource.replace(result.data)) this.failed.set(false);
    } else this.resource.clear();
    this.change.markForCheck();
    const error = result.error;
    if (
      !(error instanceof ApiFailure) ||
      this.client.getQueryState(this.key(source))?.error !== error
    )
      return;
    if (error.status !== 404 && error.status !== 401 && error.status !== 403) return;
    this.retired.set(source);
    this.resource.clear();
    this.observer.setOptions(this.options(null));
    this.client.removeQueries({ queryKey: this.key(source), exact: true });
    if (error.status === 404) {
      const queryKey = ['account', source.actorId, 'requests'] as const;
      if (this.client.isFetching({ queryKey }) === 0)
        void this.client.invalidateQueries({ queryKey }).catch(() => undefined);
    } else {
      if (error.status === 401) {
        this.client.setQueryData(['session'], null);
        this.client.removeQueries({ queryKey: ['account', source.actorId] });
      }
      void this.client.query(sessionOptions(this.http, this.client)).catch(() => undefined);
    }
  }
  protected imageFailed(): void {
    if (!this.accepts(this.bound())) return;
    this.failed.set(true);
    this.resource.clear();
  }
  protected retry(): void {
    if (!this.retryable || this.photo.isFetching) return;
    this.failed.set(false);
    void this.observer.refetch();
  }
}
