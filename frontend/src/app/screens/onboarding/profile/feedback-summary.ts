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
import type { OnChanges } from '@angular/core';
import {
  CancelledError,
  QueryClient,
  QueryObserver,
  queryOptions,
} from '@tanstack/angular-query-experimental';
import type { QueryFunctionContext } from '@tanstack/angular-query-experimental';
import { TuiButton } from '@taiga-ui/core';
import { TuiProgressBar } from '@taiga-ui/kit';
import { TuiCardLarge } from '@taiga-ui/layout';
import type { Api } from '../../../api.generated';
import { ApiFailure, readJson } from '../../../api-http';
import {
  isFeedbackSummary,
  isBuildingSummary,
  isAvailableSummary,
} from './feedback-summary-contract';

@Component({
  selector: 'app-own-feedback-summary',
  imports: [TuiButton, TuiProgressBar, TuiCardLarge],
  templateUrl: './feedback-summary.html',
  styleUrl: './feedback-summary.less',
})
export class OwnFeedbackSummary implements OnChanges {
  public readonly actorId = input.required<string>();
  public readonly sessionFailure =
    output<Readonly<{ readonly actorId: string; readonly error: ApiFailure }>>();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly explanation = signal(false);
  protected readonly about = this.explanation.asReadonly();
  private readonly query = new QueryObserver(this.client, this.options(null));
  protected get building() {
    const value = this.summary.data;
    return isBuildingSummary(value) ? value : null;
  }
  protected get available() {
    const value = this.summary.data;
    return isAvailableSummary(value) ? value : null;
  }
  protected get unavailable(): boolean {
    const error = this.summary.error;
    return error instanceof ApiFailure && error.status === 404;
  }
  protected get summary() {
    return this.query.getCurrentResult();
  }
  public constructor() {
    const unsubscribe = this.query.subscribe(
      (result: Readonly<ReturnType<typeof this.query.getCurrentResult>>) => {
        const error = result.error;
        if (error instanceof ApiFailure && (error.status === 401 || error.status === 403))
          this.sessionFailure.emit({ actorId: this.actorId(), error });
        this.change.markForCheck();
      },
    );
    this.destroy.onDestroy(() => {
      unsubscribe();
      this.query.destroy();
    });
  }
  public ngOnChanges(): void {
    this.explanation.set(false);
    this.query.setOptions(this.options(this.actorId()));
  }
  private options(actorId: string | null) {
    return queryOptions({
      queryKey: ['account', actorId, 'feedback-summary'] as const,
      enabled: actorId !== null,
      retry: false,
      staleTime: 0,
      refetchOnMount: 'always',
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      queryFn: ({ signal }: Readonly<QueryFunctionContext>) => {
        const identity = this.client.getQueryData<Api['schemas']['IdentityResponse'] | null>([
          'session',
        ]);
        const state = this.client.getQueryState(['session']);
        if (
          actorId === null ||
          identity?.account_id !== actorId ||
          !identity.capabilities.can_use_student_features ||
          state?.status !== 'success' ||
          state.fetchStatus !== 'idle'
        )
          throw new CancelledError();
        return readJson(this.http, '/api/v1/me/feedback-summary', signal, isFeedbackSummary);
      },
    });
  }
  protected explain(): void {
    this.explanation.update((value) => !value);
  }
  protected retry(): void {
    void this.query.refetch();
  }
}
