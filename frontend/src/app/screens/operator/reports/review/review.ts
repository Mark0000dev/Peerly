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
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import type { AbstractControl } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { TuiAppearance, TuiButton, TuiDialogService, TuiRadio, TuiTextfield } from '@taiga-ui/core';
import { TuiAccordion } from '@taiga-ui/kit/components/accordion';
import { TuiTextarea } from '@taiga-ui/kit/components/textarea';
import { TuiCardLarge } from '@taiga-ui/layout';
import {
  CancelledError,
  MutationObserver,
  QueryClient,
  QueryObserver,
} from '@tanstack/angular-query-experimental';
import type {
  Mutation,
  Query,
  QueryCacheNotifyEvent,
  MutationCacheNotifyEvent,
} from '@tanstack/angular-query-experimental';
import type { Api } from '../../../../api.generated';
import { ApiFailure, writeJson } from '../../../../api-http';
import { confirmDraftExit } from '../../../draft-exit';
import { isUncertain } from '../../../uncertain';
import { operatorDenied } from '../../operator-authority';
import { uuid } from '../../operator-contract';
import { cursorProblem, isReview, isReviewAction, reasonProblem } from './review-contract';
import { historyOptions, reviewActor, reviewKey } from './review-query';
import { ReviewProof } from './review-proof';

type Body = Api['schemas']['ReviewReportBody'];
type Review = Api['schemas']['ReportReviewResponse'];
interface Intent {
  readonly actorId: string;
  readonly reportId: string;
  readonly lifetime: object;
  readonly key: string;
  readonly body: Body;
}
interface Owner {
  readonly actorId: string | null;
  readonly reportId: string | null;
}

@Component({
  selector: 'app-operator-report-review',
  imports: [
    ReactiveFormsModule,
    TuiAppearance,
    TuiButton,
    TuiRadio,
    TuiTextfield,
    TuiTextarea,
    TuiCardLarge,
    ReviewProof,
    TuiAccordion,
  ],
  templateUrl: './review.html',
  styleUrl: './review.less',
})
export class OperatorReportReview implements OnInit, OnChanges {
  public readonly actorId = input.required<string>();
  public readonly reportId = input.required<string>();
  public readonly authorityFailure =
    output<Readonly<{ readonly actorId: string; readonly error: ApiFailure }>>();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly dialogs = inject(TuiDialogService);
  private readonly lifetime = signal<object>({});
  private readonly owner = signal<Owner>({ actorId: null, reportId: null });
  private readonly reported = signal<unknown>(null);
  private readonly retiring = signal(false);
  private readonly mutationOwner: object = {};
  protected readonly staged = signal<Body | null>(null);
  protected readonly reasonId = `report-review-reason-${crypto.randomUUID()}`;
  protected readonly reasonProblem = reasonProblem;
  protected readonly form = new FormGroup({
    action: new FormControl<Api['schemas']['ReportReviewAction'] | null>(
      null,
      (control: Readonly<AbstractControl<unknown>>) =>
        isReviewAction(control.value) ? null : { required: true },
    ),
    reason: new FormControl('', {
      nonNullable: true,
      validators: [
        (control: Readonly<AbstractControl<unknown>>) =>
          typeof control.value === 'string' && reasonProblem(control.value) === null
            ? null
            : { reason: true },
      ],
    }),
  });
  private readonly historyQuery = new QueryObserver(
    this.client,
    historyOptions(this.http, this.client, null, null, null, false),
  );
  private readonly mutation = new MutationObserver(this.client, this.mutationOptions(null, null));
  protected get history() {
    return this.historyQuery.getCurrentResult();
  }
  protected get operation() {
    return this.mutation.getCurrentResult();
  }
  protected get cursor(): string | null {
    return this.route.snapshot.queryParamMap.get('report_review_cursor');
  }
  protected get routeProblem(): string | null {
    return uuid(this.actorId()) && uuid(this.reportId())
      ? cursorProblem(this.cursor)
      : 'The operator or report ID is invalid.';
  }
  protected get authorized(): boolean {
    return (
      reviewActor(this.client, this.actorId()) !== null &&
      !operatorDenied(this.client, this.actorId())
    );
  }
  protected get page() {
    const value = this.history.data;
    return this.authorized && this.history.isSuccess && value?.report_id === this.reportId()
      ? value
      : undefined;
  }
  protected get reasonCount(): number {
    return Array.from(this.form.controls.reason.value).length;
  }
  protected get currentVersion(): number {
    return this.page?.current?.version ?? 0;
  }
  protected get uncertain(): boolean {
    return isUncertain(this.operation.error);
  }
  protected get locked(): boolean {
    return (
      !this.authorized ||
      this.routeProblem !== null ||
      !this.history.isSuccess ||
      this.history.isFetching ||
      !this.operation.isIdle ||
      this.staged() !== null
    );
  }
  protected get canApply(): boolean {
    const draft = this.staged();
    return (
      this.authorized &&
      this.routeProblem === null &&
      this.history.isSuccess &&
      !this.history.isFetching &&
      this.operation.isIdle &&
      draft !== null &&
      draft.expected_version === this.currentVersion
    );
  }
  protected get errorText(): string {
    const error = this.operation.error ?? this.history.error;
    if (this.uncertain)
      return 'The decision outcome is unknown. Keep the original action and reason, then retry the identical decision to confirm its result.';
    if (error instanceof ApiFailure) {
      if (error.status === 401 || error.status === 403)
        return 'Operator access must be checked before continuing.';
      if (error.status === 404) return 'This report is unavailable for review.';
      if (error.status === 409)
        return 'The decision or history changed. Read the current state before reviewing a new decision. Your draft is kept.';
      if (error.status === 422)
        return 'The report, history cursor or decision could not be accepted. Review the fields and read the current state.';
    }
    return 'The report review could not be loaded or confirmed. Your draft is kept.';
  }
  public ngOnChanges(): void {
    this.sync();
  }
  public ngOnInit(): void {
    const history = this.historyQuery.subscribe(() => {
      this.report(this.history.error);
      this.change.markForCheck();
    });
    const operation = this.mutation.subscribe(() => {
      if (this.operation.variables !== undefined && this.owns(this.operation.variables))
        this.report(this.operation.error);
      this.change.markForCheck();
    });
    const route = this.route.queryParamMap.subscribe(() => {
      this.sync();
      this.change.markForCheck();
    });
    const queries = this.client
      .getQueryCache()
      .subscribe((event: Readonly<QueryCacheNotifyEvent>) => {
        const key: unknown = event.query.queryKey;
        if (
          Array.isArray(key) &&
          (key[0] === 'session' ||
            (key[0] === 'account' &&
              key[1] === this.actorId() &&
              key[2] === 'operator' &&
              (event.type === 'removed' ||
                (event.type === 'updated' &&
                  (event.action.type === 'error' || event.action.type === 'success')))))
        ) {
          this.authorityChanged();
        }
      });
    const mutations = this.client
      .getMutationCache()
      .subscribe((event: Readonly<MutationCacheNotifyEvent>) => {
        const key = event.mutation?.options.mutationKey;
        if (
          key?.[0] === 'account' &&
          key[1] === this.actorId() &&
          key[2] === 'operator' &&
          (event.type === 'removed' || (event.type === 'updated' && event.action.type === 'error'))
        )
          this.authorityChanged();
      });
    this.destroy.onDestroy(() => {
      history();
      operation();
      route.unsubscribe();
      queries();
      mutations();
      this.retire(false);
      this.historyQuery.destroy();
    });
  }
  private mutationOptions(actor: string | null, report: string | null) {
    return {
      mutationKey: [...reviewKey(actor, report), 'write'] as const,
      meta: { reportReviewOwner: this.mutationOwner },
      retry: false as const,
      mutationFn: (intent: Intent) =>
        writeJson(
          this.http,
          `/api/v1/operator/reports/${encodeURIComponent(intent.reportId)}/reviews`,
          intent.body,
          this.headers(intent),
          (value): value is Review =>
            isReview(value) &&
            value.report_id === intent.reportId &&
            value.operator_id === intent.actorId &&
            value.action === intent.body.action &&
            value.reason === intent.body.reason &&
            value.version === intent.body.expected_version + 1,
        ),
      onSuccess: async (_receipt: Review, intent: Intent) => {
        if (!this.owns(intent)) return;
        this.staged.set(null);
        this.form.reset({ action: null, reason: '' });
        await this.client.invalidateQueries({
          queryKey: reviewKey(intent.actorId, intent.reportId),
        });
      },
    };
  }
  private owns(intent: Intent): boolean {
    return (
      !this.destroy.destroyed &&
      intent.lifetime === this.lifetime() &&
      intent.actorId === this.actorId() &&
      intent.reportId === this.reportId()
    );
  }
  private headers(intent: Intent): Readonly<Record<string, string>> {
    const actor = reviewActor(this.client, intent.actorId);
    if (!this.owns(intent) || actor === null || operatorDenied(this.client, intent.actorId))
      throw new CancelledError();
    return { 'X-CSRF-Token': actor.csrf_token, 'Idempotency-Key': intent.key };
  }
  private report(error: unknown): void {
    if (
      !(error instanceof ApiFailure) ||
      (error.status !== 401 && error.status !== 403) ||
      error === this.reported()
    )
      return;
    this.reported.set(error);
    this.authorityFailure.emit({ actorId: this.actorId(), error });
  }
  private authorityChanged(): void {
    if (this.destroy.destroyed || this.retiring()) return;
    const actor = this.client.getQueryData<Api['schemas']['IdentityResponse'] | null>(['session']);
    if (actor?.account_id !== this.actorId() || actor.account_status !== 'active')
      this.retire(false);
    else if (operatorDenied(this.client, this.actorId())) this.retire(true);
    this.sync();
    this.change.markForCheck();
  }
  private sync(): void {
    if (this.destroy.destroyed) return;
    const previous = this.owner();
    if (previous.actorId !== this.actorId() || previous.reportId !== this.reportId()) {
      this.retire(false);
      this.owner.set({ actorId: this.actorId(), reportId: this.reportId() });
    }
    const actor = this.client.getQueryData<Api['schemas']['IdentityResponse'] | null>(['session']);
    if (actor?.account_id !== this.actorId() || actor.account_status !== 'active') {
      // A retired canonical identity must not recreate the previous actor's scope.
      // Same-actor session checking retains its draft and disabled resource query below.
      this.mutation.setOptions(this.mutationOptions(null, null));
      this.historyQuery.setOptions(historyOptions(this.http, this.client, null, null, null, false));
      return;
    }
    this.mutation.setOptions(this.mutationOptions(this.actorId(), this.reportId()));
    this.historyQuery.setOptions(
      historyOptions(
        this.http,
        this.client,
        this.actorId(),
        this.reportId(),
        this.cursor,
        this.authorized && this.routeProblem === null,
      ),
    );
  }
  private retire(preserveDenied: boolean): void {
    if (this.retiring()) return;
    this.retiring.set(true);
    try {
      const previous = this.owner();
      this.lifetime.set({});
      this.staged.set(null);
      this.form.reset({ action: null, reason: '' });
      this.mutation.reset();
      this.historyQuery.setOptions(historyOptions(this.http, this.client, null, null, null, false));
      if (previous.actorId !== null && previous.reportId !== null) {
        const prefix = reviewKey(previous.actorId, previous.reportId);
        void this.client.cancelQueries({ queryKey: prefix });
        this.client.removeQueries({
          queryKey: prefix,
          predicate: (query: Readonly<Query>) =>
            !preserveDenied ||
            !(query.state.error instanceof ApiFailure && query.state.error.status === 403),
        });
      }
      for (const mutation of this.client.getMutationCache().findAll({
        predicate: (value: Readonly<Mutation>) =>
          value.options.meta?.['reportReviewOwner'] === this.mutationOwner,
      })) {
        if (
          !preserveDenied ||
          !(mutation.state.error instanceof ApiFailure && mutation.state.error.status === 403)
        )
          this.client.getMutationCache().remove(mutation);
      }
    } finally {
      this.retiring.set(false);
    }
  }
  protected prepare(): void {
    this.form.markAllAsTouched();
    const value = this.form.getRawValue();
    if (
      this.locked ||
      this.form.invalid ||
      !isReviewAction(value.action) ||
      this.currentVersion >= 2147483647
    )
      return;
    this.staged.set({
      action: value.action,
      reason: value.reason,
      expected_version: this.currentVersion,
    });
  }
  protected edit(): void {
    if (this.operation.isIdle) this.staged.set(null);
  }
  protected apply(): void {
    const body = this.staged();
    if (!this.canApply || body === null) return;
    this.submit({
      actorId: this.actorId(),
      reportId: this.reportId(),
      lifetime: this.lifetime(),
      key: crypto.randomUUID(),
      body,
    });
  }
  private submit(intent: Intent): void {
    void this.mutation.mutate(intent).catch((error: unknown) => {
      if (!(error instanceof ApiFailure) && !(error instanceof CancelledError)) throw error;
    });
  }
  protected replay(): void {
    const intent = this.operation.variables;
    if (
      this.uncertain &&
      !this.operation.isPending &&
      this.authorized &&
      intent !== undefined &&
      this.owns(intent)
    )
      this.submit(intent);
  }
  protected async reload(): Promise<void> {
    if (this.operation.isPending || !this.authorized) return;
    const lifetime = this.lifetime();
    const result = await this.historyQuery.refetch();
    if (lifetime === this.lifetime() && result.isSuccess && !result.isFetching && !this.uncertain) {
      this.mutation.reset();
      this.staged.set(null);
    }
  }
  protected pageHistory(cursor: string | null): void {
    if (this.operation.isPending || !this.authorized) return;
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { report_review_cursor: cursor },
      queryParamsHandling: 'merge',
    });
  }
  public async confirmLeave(): Promise<boolean> {
    const owner = this.owner();
    const lifetime = this.lifetime();
    const accepted = await confirmDraftExit(this.dialogs, this.destroy, {
      dirty: this.form.dirty || this.staged() !== null,
      unconfirmed: this.operation.isPending || this.uncertain,
    });
    return (
      accepted &&
      !this.destroy.destroyed &&
      lifetime === this.lifetime() &&
      owner.actorId === this.actorId() &&
      owner.reportId === this.reportId()
    );
  }
}
