import {
  operatorDenied,
  recheckOperatorAuthority,
  retireOperatorFailure,
} from './operator-authority';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectorRef, Component, DestroyRef, inject, signal, viewChild } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink, convertToParamMap } from '@angular/router';
import type { Query } from '@tanstack/angular-query-experimental';
import { QueryClient, QueryObserver } from '@tanstack/angular-query-experimental';
import { TuiButton, TuiInput, TuiLink, TuiTextfield } from '@taiga-ui/core';
import { TuiNativeSelect } from '@taiga-ui/kit/components/select';
import { ApiFailure } from '../../api-http';
import { sessionOptions } from '../session';
import { reportCategories, reportOptions, reportsOptions } from './operator-reports-contract';
import { reportFields, reportRoute } from './operator-reports-route';
import { OperatorOrigin } from './operator-origin';
import { OperatorInvestigation } from './operator-investigation';
import { OperatorReportReview } from './reports/review/review';

@Component({
  selector: 'app-operator-reports',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TuiButton,
    TuiInput,
    TuiLink,
    TuiTextfield,
    TuiNativeSelect,
    OperatorOrigin,
    OperatorInvestigation,
    OperatorReportReview,
  ],
  templateUrl: './operator-reports.html',
  styleUrl: './operator-reports.less',
})
export class OperatorReports {
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly submitted = signal(false);
  private readonly resetting = signal(false);
  protected readonly reviewOpen = signal(false);
  private readonly review = viewChild(OperatorReportReview);
  protected readonly fields = reportFields;
  protected readonly categories = ['all', ...reportCategories];
  protected readonly form = new FormGroup({
    reporter_id: new FormControl('', { nonNullable: true }),
    target_id: new FormControl('', { nonNullable: true }),
    context_id: new FormControl('', { nonNullable: true }),
    category: new FormControl<string | null>('all'),
    submitted_from: new FormControl('', { nonNullable: true }),
    submitted_before: new FormControl('', { nonNullable: true }),
  });
  private readonly sessionQuery = new QueryObserver(
    this.client,
    sessionOptions(this.http, this.client),
  );
  private readonly listQuery = new QueryObserver(
    this.client,
    reportsOptions(this.http, null, {}, false),
  );
  private readonly detailQuery = new QueryObserver(
    this.client,
    reportOptions(this.http, null, null, false),
  );
  protected get session() {
    return this.sessionQuery.getCurrentResult();
  }
  protected get reports() {
    return this.listQuery.getCurrentResult();
  }
  protected get detail() {
    return this.detailQuery.getCurrentResult();
  }
  protected get ownerId(): string | null {
    return this.session.data?.account_id ?? null;
  }
  protected get actorId(): string | null {
    return this.session.isSuccess && this.session.fetchStatus === 'idle' && !this.resetting()
      ? (this.session.data?.account_id ?? null)
      : null;
  }
  protected get state() {
    return reportRoute(this.route.snapshot.queryParamMap);
  }
  protected get formError(): string | null {
    return this.submitted() ? reportRoute(convertToParamMap(this.draft())).error : null;
  }
  protected get denied(): boolean {
    return operatorDenied(this.client, this.actorId);
  }
  public constructor() {
    const session = this.sessionQuery.subscribe(() => {
      const previous = this.listQuery.options.queryKey[1];
      if (
        this.ownerId === null ||
        this.session.data?.account_status !== 'active' ||
        (typeof previous === 'string' && previous !== this.ownerId)
      )
        this.reviewOpen.set(false);
      if (this.actorId !== null && typeof previous === 'string' && previous !== this.actorId)
        this.resetActorCursors();
      this.sync();
      this.change.markForCheck();
    });
    const list = this.listQuery.subscribe(() => {
      this.authorityFailure(this.reports.error, this.listQuery.options.queryKey[1]);
      this.change.markForCheck();
    });
    const detail = this.detailQuery.subscribe(() => {
      this.authorityFailure(this.detail.error, this.detailQuery.options.queryKey[1]);
      this.change.markForCheck();
    });
    const route = this.route.queryParamMap.subscribe((params) => {
      if (this.detailQuery.options.queryKey[5] !== params.get('report')) this.reviewOpen.set(false);
      for (const field of reportFields)
        this.form.controls[field.key].setValue(params.get(field.key) ?? '');
      this.form.controls.category.setValue(params.get('category') ?? 'all');
      this.submitted.set(false);
      this.sync();
      this.change.markForCheck();
    });
    this.destroy.onDestroy(() => {
      session();
      list();
      detail();
      route.unsubscribe();
      this.sessionQuery.destroy();
      this.listQuery.destroy();
      this.detailQuery.destroy();
      void this.client.cancelQueries({
        predicate: (query: Readonly<Query>) =>
          query.queryKey[0] === 'account' && query.queryKey[2] === 'operator',
      });
      this.client.removeQueries({
        predicate: (query: Readonly<Query>) =>
          query.queryKey[0] === 'account' && query.queryKey[2] === 'operator',
      });
      this.form.reset();
    });
  }
  private resetActorCursors(): void {
    if (
      !['reports_cursor', 'events_cursor', 'report_review_cursor'].some((key) =>
        this.route.snapshot.queryParamMap.has(key),
      )
    )
      return;
    this.resetting.set(true);
    void this.router
      .navigate([], {
        relativeTo: this.route,
        queryParams: { reports_cursor: null, events_cursor: null, report_review_cursor: null },
        queryParamsHandling: 'merge',
      })
      .then(() => {
        if (this.destroy.destroyed) return;
        this.resetting.set(false);
        this.sync();
        this.change.markForCheck();
      });
  }
  private sync(): void {
    const enabled = this.actorId !== null && !this.denied && this.state.error === null;
    this.listQuery.setOptions(reportsOptions(this.http, this.ownerId, this.state.filters, enabled));
    this.detailQuery.setOptions(
      reportOptions(this.http, this.ownerId, this.state.reportId, enabled),
    );
  }
  protected authorityFailure(error: unknown, actor: unknown): void {
    retireOperatorFailure(
      this.client,
      error,
      actor,
      () => this.actorId,
      () => {
        this.sync();
      },
      () => {
        void this.sessionQuery.refetch();
      },
    );
    this.change.markForCheck();
  }

  private draft(): Readonly<Record<string, string>> {
    const value = this.form.getRawValue();
    return Object.fromEntries(
      Object.entries({
        ...value,
        category: value.category === 'all' || value.category === null ? '' : value.category,
      }).filter(([, value]: readonly [string, string]) => value !== ''),
    );
  }
  protected search(): void {
    this.submitted.set(true);
    if (this.actorId === null || this.denied || this.formError !== null) return;
    this.navigate({
      reporter_id: null,
      target_id: null,
      context_id: null,
      category: null,
      submitted_from: null,
      submitted_before: null,
      ...this.draft(),
      reports_cursor: null,
      report: null,
    });
  }
  protected navigate(params: Readonly<Record<string, string | null>>): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {
        ...params,
        ...(Object.hasOwn(params, 'report') && params['report'] !== this.state.reportId
          ? { report_review_cursor: null }
          : {}),
      },
      queryParamsHandling: 'merge',
    });
  }
  protected async retry(kind: 'list' | 'detail'): Promise<void> {
    const actor = this.actorId;
    const report = this.state.reportId;
    if (actor === null || this.denied) return;
    if (kind === 'detail') {
      if (!(await this.canLeave()) || this.actorId !== actor || this.state.reportId !== report)
        return;
      this.reviewOpen.set(false);
      await this.detailQuery.refetch();
    } else await this.listQuery.refetch();
  }
  protected openReview(): void {
    if (
      this.actorId !== null &&
      !this.denied &&
      this.detail.isSuccess &&
      !this.detail.isFetching &&
      this.detail.data.report.id === this.state.reportId
    )
      this.reviewOpen.set(true);
  }
  protected async closeReview(): Promise<void> {
    const actor = this.ownerId;
    const report = this.state.reportId;
    if ((await this.canLeave()) && actor === this.ownerId && report === this.state.reportId)
      this.reviewOpen.set(false);
  }
  public async canLeave(): Promise<boolean> {
    const review = this.review();
    return review === undefined ? true : await review.confirmLeave();
  }
  protected recheck(): void {
    void recheckOperatorAuthority(
      this.client,
      this.ownerId,
      () => (this.destroy.destroyed ? null : this.ownerId),
      () => this.sessionQuery.refetch(),
    ).then(() => {
      if (this.destroy.destroyed) return;
      this.sync();
      this.change.markForCheck();
    });
  }
  protected cursorError(error: unknown): boolean {
    return error instanceof ApiFailure && error.status === 422;
  }
  protected errorText(error: unknown): string {
    if (error instanceof ApiFailure && error.status === 404)
      return 'This retained report is unavailable.';
    if (this.cursorError(error))
      return 'These filters or this cursor could not be used. Check filters or return to the first page.';
    return 'The records could not be loaded. Your filters are kept. Try again.';
  }
}
