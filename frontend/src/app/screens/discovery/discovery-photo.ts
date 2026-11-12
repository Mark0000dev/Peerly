import { HttpClient } from '@angular/common/http';
import {
  Component,
  DestroyRef,
  ChangeDetectorRef,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
} from '@angular/core';
import { TuiButton } from '@taiga-ui/core';
import { QueryClient, QueryObserver, CancelledError } from '@tanstack/angular-query-experimental';
import type { QueryObserverResult } from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { ApiFailure, readJpeg } from '../../api-http';
import { ImageResource } from '../image-resource';

@Component({
  selector: 'app-discovery-photo',
  imports: [TuiButton],
  template: `
    @if (url() !== null && !decodeFailed()) {
      <img [src]="url()" [alt]="'Photo of ' + name()" (error)="decodeFailed.set(true)" />
    } @else if (photo.isPending && actorId() !== null) {
      <p role="status">Loading photo…</p>
    } @else {
      <p>Photo didn’t load</p>
    }
    @if (photo.isError || decodeFailed()) {
      <button
        tuiButton
        appearance="flat"
        size="s"
        type="button"
        [disabled]="photo.isFetching || actorId() === null"
        (click)="retry()"
      >
        Retry photo
      </button>
    }
  `,
  styles: `
    :host {
      display: grid;
      place-items: center;
      min-block-size: 9rem;
    }
    img {
      display: block;
      max-inline-size: 100%;
      inline-size: 100%;
      block-size: auto;
      aspect-ratio: 5 / 2;
      object-fit: cover;
      border-radius: var(--tui-radius-m);
    }
    p {
      margin: 0;
    }
  `,
})
export class DiscoveryPhoto {
  public readonly actorId = input.required<string | null>();
  public readonly personId = input.required<string>();
  public readonly version = input.required<number>();
  public readonly name = input.required<string>();
  public readonly failure = output<unknown>();
  public readonly refresh = output();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly destroy = inject(DestroyRef);
  private readonly change = inject(ChangeDetectorRef);
  private readonly resource = new ImageResource();
  protected readonly url = this.resource.url;
  protected readonly decodeFailed = signal(false);
  private readonly observer = new QueryObserver(this.client, this.options(null, '', 0));
  protected get photo() {
    return this.observer.getCurrentResult();
  }
  private options(actor: string | null, person: string, version: number) {
    return {
      queryKey: ['account', actor, 'person-photo', person, version] as const,
      enabled: actor !== null,
      retry: false,
      gcTime: 0,
      staleTime: 0,
      queryFn: ({ signal }: Readonly<{ readonly signal: AbortSignal }>) => {
        if (!this.trusted(actor)) throw new CancelledError();
        return readJpeg(
          this.http,
          `/api/v1/people/${encodeURIComponent(person)}/photo/${String(version)}`,
          signal,
        );
      },
    };
  }
  public constructor() {
    const subscription = this.observer.subscribe(
      (result: Readonly<QueryObserverResult<Readonly<Blob>>>) => {
        if (!result.isSuccess) this.resource.clear();
        else if (this.resource.replace(result.data)) this.decodeFailed.set(false);
        if (result.error !== null && this.trusted(this.observer.options.queryKey[1]))
          this.failure.emit(result.error);
        this.change.markForCheck();
      },
    );
    effect(() => {
      const options = this.options(this.actorId(), this.personId(), this.version());
      untracked(() => {
        this.resource.clear();
        this.decodeFailed.set(false);
        this.observer.setOptions(options);
      });
    });
    this.destroy.onDestroy(() => {
      subscription();
      this.observer.destroy();
      this.resource.clear();
    });
  }
  private trusted(actor: string | null): boolean {
    const identity = this.client.getQueryData<Api['schemas']['IdentityResponse'] | null>([
      'session',
    ]);
    return (
      actor !== null &&
      identity?.account_id === actor &&
      identity.capabilities.can_use_student_features &&
      this.client.isFetching({ queryKey: ['session'] }) === 0
    );
  }
  protected retry(): void {
    if (!this.trusted(this.actorId()) || this.photo.isFetching) return;
    if (this.photo.error instanceof ApiFailure && this.photo.error.status === 404)
      this.refresh.emit();
    else void this.observer.refetch();
  }
}
