import { HttpClient } from '@angular/common/http';
import { ChangeDetectorRef, Component, DestroyRef, inject, input, output } from '@angular/core';
import type { OnChanges } from '@angular/core';
import { TuiButton } from '@taiga-ui/core';
import { TuiCardLarge } from '@taiga-ui/layout';
import {
  CancelledError,
  QueryClient,
  QueryObserver,
  queryOptions,
} from '@tanstack/angular-query-experimental';
import type {
  QueryFunctionContext,
  QueryObserverResult,
} from '@tanstack/angular-query-experimental';
import type { Api } from '../../../api.generated';
import { ApiFailure, readJson } from '../../../api-http';
import { trustedVerifiedActor } from '../../verified-actor';

function isReview(value: unknown): value is Api['schemas']['OwnPhotoReviewResponse'] {
  return (
    typeof value === 'object' &&
    value !== null &&
    'version' in value &&
    typeof value.version === 'number' &&
    Number.isSafeInteger(value.version) &&
    value.version >= 0 &&
    'state' in value &&
    (value.state === 'not_required' ||
      value.state === 'replacement_required' ||
      value.state === 'awaiting_human_review')
  );
}

@Component({
  selector: 'peerly-photo-review',
  imports: [TuiButton, TuiCardLarge],
  template: `@if (authorized && result.isFetching) {
      <p role="status">Checking the latest photo review status…</p>
    }
    @if (authorized && result.data; as review) {
      @if (review.state !== 'not_required') {
        <section tuiCardLarge="compact" appearance="neutral" aria-label="Photo review">
          @if (review.state === 'replacement_required') {
            <h2>A different profile photo is needed</h2>
            <p>
              Choose a different photo below. A person on the team must review your replacement.
              Other account requirements still apply.
            </p>
          } @else {
            <h2>Your replacement is awaiting review</h2>
            <p>
              Your photo has been uploaded, but a person on the team still needs to review it.
              Upload completion does not confirm approval.
            </p>
          }
          <p>Existing chats remain available when your account is otherwise eligible.</p>
          <button
            tuiButton
            appearance="secondary"
            type="button"
            [disabled]="result.isFetching"
            (click)="refresh()"
          >
            Check photo review status
          </button>
        </section>
      }
    }
    @if (authorized && result.isError) {
      <p role="status">Photo review status could not be checked. This does not confirm approval.</p>
      <button
        tuiButton
        appearance="secondary"
        type="button"
        [disabled]="result.isFetching"
        (click)="refresh()"
      >
        Check photo review status
      </button>
    }`,
  styles: `
    :host {
      display: block;
      min-inline-size: 0;
    }
    h2 {
      font: var(--tui-typography-heading-h6);
      margin: 0;
    }
    p {
      margin: 0;
    }
  `,
})
export class PhotoReview implements OnChanges {
  public readonly actor = input.required<Api['schemas']['IdentityResponse']>();
  public readonly checking = input(false);
  public readonly expired = output();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly query = new QueryObserver(this.client, this.options(null));
  protected get result() {
    return this.query.getCurrentResult();
  }
  protected get authorized(): boolean {
    return !this.checking() && trustedVerifiedActor(this.client, this.actor().account_id) !== null;
  }
  public constructor() {
    const stop = this.query.subscribe(
      (result: Readonly<QueryObserverResult<Api['schemas']['OwnPhotoReviewResponse']>>) => {
        if (
          result.error instanceof ApiFailure &&
          (result.error.status === 401 || result.error.status === 403)
        )
          this.expired.emit();
        this.change.markForCheck();
      },
    );
    this.destroy.onDestroy(() => {
      stop();
      this.query.destroy();
    });
  }
  public ngOnChanges(): void {
    const accountId = this.actor().account_id;
    const previous = this.query.getCurrentQuery().queryKey;
    if (!this.authorized || previous[1] !== accountId) {
      void this.client.cancelQueries({ queryKey: previous, exact: true });
    }
    this.query.setOptions(this.options(accountId));
  }
  private options(actorId: string | null) {
    return queryOptions({
      queryKey: ['account', actorId, 'photo-review'] as const,
      enabled:
        actorId !== null && !this.checking() && trustedVerifiedActor(this.client, actorId) !== null,
      retry: false,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      queryFn: ({ signal }: Readonly<QueryFunctionContext>) => {
        if (
          actorId === null ||
          this.checking() ||
          trustedVerifiedActor(this.client, actorId) === null
        )
          throw new CancelledError();
        return readJson(this.http, '/api/v1/me/photo-review', signal, isReview);
      },
    });
  }
  protected refresh(): void {
    if (this.authorized) void this.query.refetch();
  }
}
