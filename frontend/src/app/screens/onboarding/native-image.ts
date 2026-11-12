import { HttpClient } from '@angular/common/http';
import {
  Directive,
  DestroyRef,
  ChangeDetectorRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
} from '@angular/core';
import { CancelledError, QueryClient, QueryObserver } from '@tanstack/angular-query-experimental';
import type { Query, QueryObserverResult } from '@tanstack/angular-query-experimental';
import { ApiFailure, readJpeg } from '../../api-http';
import { NATIVE_RUNTIME } from '../../native-transport/runtime';
import { ImageResource } from '../image-resource';
import { trustedVerifiedActor } from '../verified-actor';

// The three own-profile <img> consumers need native binary reads: their raw URLs
// cannot authenticate a cross-origin WebView request. Web src stays unchanged.
@Directive({ selector: 'img[peerlyNativeImage]', host: { '[attr.src]': 'source()' } })
export class NativeImage {
  public readonly peerlyNativeImage = input.required<string>();
  public readonly nativeImageActor = input<string | null>(null);
  public readonly nativeImageEnabled = input(true);
  public readonly nativeImageExpired = output();
  private readonly native = inject(NATIVE_RUNTIME);
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly resource = new ImageResource();
  private readonly authorityRevision = signal(0);
  private readonly owner = signal<Readonly<{
    readonly actor: string;
    readonly path: string;
    readonly epoch: string;
  }> | null>(null);
  private readonly observer =
    this.native === null ? null : new QueryObserver(this.client, this.options(null, '', null));
  protected readonly source = computed(() => {
    if (this.native === null) return this.peerlyNativeImage();
    this.authorityRevision();
    const owner = this.owner();
    return owner !== null &&
      owner.actor === this.nativeImageActor() &&
      owner.path === this.peerlyNativeImage() &&
      this.nativeImageEnabled() &&
      this.trusted(owner.actor, owner.epoch)
      ? this.resource.url()
      : null;
  });

  private trusted(actor: string | null, epoch: string | null): boolean {
    return (
      actor !== null &&
      epoch !== null &&
      this.native?.epoch() === epoch &&
      trustedVerifiedActor(this.client, actor) !== null
    );
  }
  private options(actor: string | null, path: string, epoch: string | null) {
    const enabled = this.native !== null && this.nativeImageEnabled() && this.trusted(actor, epoch);
    return {
      queryKey: enabled
        ? (['account', actor, 'native-own-image', path, epoch] as const)
        : (['native-image-idle'] as const),
      enabled,
      retry: false,
      staleTime: 0,
      gcTime: 0,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      queryFn: ({ signal }: Readonly<{ readonly signal: AbortSignal }>) => {
        if (!this.trusted(actor, epoch) || !/^\/api\/v1\/media\/[^/?#]+\/display$/.test(path))
          throw new CancelledError();
        return readJpeg(this.http, path, signal);
      },
    };
  }
  public constructor() {
    const observer = this.observer;
    if (observer === null) return;
    const stop = observer.subscribe((result: Readonly<QueryObserverResult<Readonly<Blob>>>) => {
      const actor = this.nativeImageActor();
      const epoch = this.native?.epoch() ?? null;
      if (
        result.isSuccess &&
        actor !== null &&
        epoch !== null &&
        this.trusted(actor, epoch) &&
        this.nativeImageEnabled()
      ) {
        this.resource.replace(result.data);
        this.owner.set({ actor, epoch, path: this.peerlyNativeImage() });
      } else {
        this.resource.clear();
        this.owner.set(null);
      }
      if (
        result.error instanceof ApiFailure &&
        (result.error.status === 401 || result.error.status === 403) &&
        this.trusted(actor, epoch)
      )
        this.nativeImageExpired.emit();
      this.change.markForCheck();
    });
    const stopAuthority = this.client
      .getQueryCache()
      .subscribe((event: Readonly<{ readonly query: Readonly<Query> }>) => {
        if (event.query.queryKey[0] === 'session')
          this.authorityRevision.update((value) => value + 1);
      });
    effect(() => {
      this.authorityRevision();
      const options = this.options(
        this.nativeImageActor(),
        this.peerlyNativeImage(),
        this.native?.epoch() ?? null,
      );
      untracked(() => {
        this.resource.clear();
        this.owner.set(null);
        observer.setOptions(options);
      });
    });
    this.destroy.onDestroy(() => {
      stopAuthority();
      stop();
      observer.destroy();
      this.resource.clear();
    });
  }
}
