import {
  operatorDenied,
  recheckOperatorAuthority,
  retireOperatorFailure,
} from './operator-authority';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectorRef, Component, DestroyRef, inject, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink, convertToParamMap } from '@angular/router';
import type { Query } from '@tanstack/angular-query-experimental';
import type { ParamMap } from '@angular/router';
import { QueryClient, QueryObserver } from '@tanstack/angular-query-experimental';
import { TuiButton, TuiInput, TuiLink, TuiTextfield } from '@taiga-ui/core';
import { TuiNativeSelect } from '@taiga-ui/kit/components/select';
import { TuiTabs } from '@taiga-ui/kit/components/tabs';
import type { Api } from '../../api.generated';
import { ApiFailure } from '../../api-http';
import { sessionOptions } from '../session';
import { accountsOptions, detailOptions, uuid } from './operator-contract';
import { hiddenFilters, lifecycleFilters, readFilters, searchFields } from './operator-search';
import { OperatorOverview } from './operator-overview';
import { OperatorAcademic } from './operator-academic';
import { OperatorProfileHistory } from './operator-profile-history';
import { academicReset } from './operator-academic-route';

@Component({
  selector: 'app-operator',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TuiButton,
    TuiInput,
    TuiLink,
    TuiTextfield,
    TuiNativeSelect,
    OperatorOverview,
    OperatorAcademic,
    OperatorProfileHistory,
    TuiTabs,
  ],
  templateUrl: './operator.html',
  styleUrl: './operator.less',
})
export class Operator {
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  protected readonly fields = searchFields;
  protected readonly lifecycles = lifecycleFilters;
  protected readonly visibility = hiddenFilters;
  private readonly submitted = signal(false);
  private readonly pendingAcademicCursor = signal(false);
  protected readonly resettingAcademicCursor = this.pendingAcademicCursor.asReadonly();
  protected readonly form = new FormGroup({
    name: new FormControl('', { nonNullable: true }),
    institutional_email: new FormControl('', { nonNullable: true }),
    account_id: new FormControl('', { nonNullable: true }),
    google_link_id: new FormControl('', { nonNullable: true }),
    google_issuer: new FormControl('', { nonNullable: true }),
    google_subject: new FormControl('', { nonNullable: true }),
    created_from: new FormControl('', { nonNullable: true }),
    created_before: new FormControl('', { nonNullable: true }),
    lifecycle: new FormControl<string | null>('all'),
    hidden: new FormControl<string | null>('any'),
  });
  private readonly sessionQuery = new QueryObserver(
    this.client,
    sessionOptions(this.http, this.client),
  );
  private readonly accountsQuery = new QueryObserver(
    this.client,
    accountsOptions(this.http, null, {}, false),
  );
  private readonly accountQuery = new QueryObserver(
    this.client,
    detailOptions(this.http, null, null, false),
  );
  protected get session() {
    return this.sessionQuery.getCurrentResult();
  }
  protected get accounts() {
    return this.accountsQuery.getCurrentResult();
  }
  protected get detail() {
    return this.accountQuery.getCurrentResult();
  }
  private get ownerId(): string | null {
    return this.session.data?.account_id ?? null;
  }
  protected get actor(): Api['schemas']['IdentityResponse'] | null {
    return this.session.isSuccess &&
      this.session.fetchStatus === 'idle' &&
      !this.resettingAcademicCursor()
      ? this.session.data
      : null;
  }
  protected get selected(): string | null {
    return this.route.snapshot.queryParamMap.get('account');
  }
  protected get tab(): 'overview' | 'goals' | 'help' {
    const value = this.route.snapshot.queryParamMap.get('tab');
    return value === 'goals' || value === 'help' ? value : 'overview';
  }
  protected get tabIndex(): number {
    return this.tab === 'overview' ? 0 : this.tab === 'goals' ? 1 : 2;
  }
  protected accountSelection(account: string) {
    return { ...academicReset, profile_history: null, profile_cursor: null, account };
  }
  protected changeTab(index: number): void {
    const tab = (['overview', 'goals', 'help'] as const)[index];
    if (tab === undefined) return;
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {
        profile_history: null,
        profile_cursor: null,
        tab: tab === 'overview' ? null : tab,
        goal: null,
        goals_cursor: null,
        goal_cursor: null,
        help_cursor: null,
      },
      queryParamsHandling: 'merge',
    });
  }
  protected get accountsQueryIsPaged(): boolean {
    return this.route.snapshot.queryParamMap.has('cursor');
  }
  protected get searched(): boolean {
    return this.route.snapshot.queryParamMap.keys.some(
      (key) =>
        key === 'lifecycle' ||
        key === 'hidden' ||
        key === 'cursor' ||
        searchFields.some((field) => field.key === key),
    );
  }
  protected get urlError(): string | null {
    const tab = this.route.snapshot.queryParamMap.get('tab');
    if (tab !== null && tab !== 'overview' && tab !== 'goals' && tab !== 'help')
      return 'Choose Overview, Goals or Help.';
    return this.selected !== null && !uuid(this.selected)
      ? 'The selected account ID must be a UUID.'
      : readFilters(this.route.snapshot.queryParamMap).error;
  }
  protected get denied(): boolean {
    return operatorDenied(this.client, this.ownerId);
  }
  protected get formError(): string | null {
    return this.submitted() ? readFilters(convertToParamMap(this.draft())).error : null;
  }
  protected get listError(): string {
    return this.errorText(this.accounts.error);
  }
  protected get detailError(): string {
    return this.errorText(this.detail.error);
  }
  protected get cursorInvalid(): boolean {
    return this.accounts.error instanceof ApiFailure && this.accounts.error.status === 422;
  }
  public constructor() {
    const session = this.sessionQuery.subscribe(() => {
      const previousActor = this.accountsQuery.options.queryKey[1];
      if (
        this.session.isSuccess &&
        this.session.fetchStatus === 'idle' &&
        typeof previousActor === 'string' &&
        this.ownerId !== previousActor
      )
        this.resetAcademicCursors();
      this.sync();
      this.change.markForCheck();
    });
    const list = this.accountsQuery.subscribe(() => {
      this.privateChanged(this.accounts.error, this.accountsQuery.options.queryKey[1]);
      this.change.markForCheck();
    });
    const detail = this.accountQuery.subscribe(() => {
      this.privateChanged(this.detail.error, this.accountQuery.options.queryKey[1]);
      this.change.markForCheck();
    });
    const route = this.route.queryParamMap.subscribe((params: Readonly<ParamMap>) => {
      for (const field of searchFields)
        this.form.controls[field.key].setValue(params.get(field.key) ?? '');
      this.form.controls.lifecycle.setValue(params.get('lifecycle') ?? 'all');
      this.form.controls.hidden.setValue(
        params.get('hidden') === 'true'
          ? 'hidden'
          : params.get('hidden') === 'false'
            ? 'visible'
            : 'any',
      );
      this.submitted.set(false);
      const previousAccount = this.accountQuery.options.queryKey[4];
      if (typeof previousAccount === 'string' && previousAccount !== this.selected)
        this.resetAcademicCursors();
      this.sync();
      this.change.markForCheck();
    });
    this.destroy.onDestroy(() => {
      session();
      list();
      detail();
      route.unsubscribe();
      this.sessionQuery.destroy();
      this.accountsQuery.destroy();
      this.accountQuery.destroy();
      if (this.ownerId !== null)
        void this.client.cancelQueries({ queryKey: ['account', this.ownerId, 'operator'] });
      this.client.removeQueries({
        predicate: (query: Readonly<Query>) =>
          query.queryKey[0] === 'account' && query.queryKey[2] === 'operator',
      });
      this.form.reset();
    });
  }
  private resetAcademicCursors(): void {
    const params = this.route.snapshot.queryParamMap;
    if (
      this.resettingAcademicCursor() ||
      !['goals_cursor', 'goal_cursor', 'help_cursor', 'profile_cursor'].some((key) =>
        params.has(key),
      )
    )
      return;
    // This signal only owns a pending URL transition, never identity or query data.
    this.pendingAcademicCursor.set(true);
    void this.router
      .navigate([], {
        relativeTo: this.route,
        queryParams: {
          goals_cursor: null,
          goal_cursor: null,
          help_cursor: null,
          profile_cursor: null,
        },
        queryParamsHandling: 'merge',
      })
      .then(() => {
        if (this.destroy.destroyed) return;
        this.pendingAcademicCursor.set(false);
        this.sync();
        this.change.markForCheck();
      });
  }
  private sync(): void {
    const enabled = this.actor !== null && !this.denied && this.urlError === null;
    this.accountsQuery.setOptions(
      accountsOptions(
        this.http,
        this.ownerId,
        readFilters(this.route.snapshot.queryParamMap).filters,
        enabled && this.searched,
      ),
    );
    this.accountQuery.setOptions(
      detailOptions(this.http, this.ownerId, this.selected, enabled && this.tab === 'overview'),
    );
  }
  protected privateChanged(error: unknown, actor: unknown): void {
    retireOperatorFailure(
      this.client,
      error,
      actor,
      () => this.actor?.account_id ?? null,
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
    const { hidden, lifecycle, ...other } = value;
    return Object.fromEntries(
      Object.entries({
        ...other,
        lifecycle: lifecycle ?? 'all',
        hidden: hidden === 'hidden' ? 'true' : hidden === 'visible' ? 'false' : '',
      }).filter(([, value]: readonly [string, string]) => value !== ''),
    );
  }
  protected search(): void {
    this.submitted.set(true);
    this.form.markAllAsTouched();
    if (this.actor === null || this.denied || this.formError !== null) return;
    const query = Object.fromEntries(
      Object.entries(this.draft()).filter(
        ([, value]: readonly [string, string]) => value.trim() !== '',
      ),
    );
    const target = this.router.createUrlTree([], { relativeTo: this.route, queryParams: query });
    if (this.router.serializeUrl(target) === this.router.url) {
      void this.accountsQuery.refetch();
      return;
    }
    void this.router.navigateByUrl(target);
  }
  protected next(cursor: string): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {
        ...academicReset,
        profile_history: null,
        profile_cursor: null,
        cursor,
        account: null,
      },
      queryParamsHandling: 'merge',
    });
  }
  protected firstPage(): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { cursor: null },
      queryParamsHandling: 'merge',
    });
  }
  protected close(): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { ...academicReset, profile_history: null, profile_cursor: null, account: null },
      queryParamsHandling: 'merge',
    });
  }
  protected retryList(): void {
    if (this.actor !== null && !this.denied) void this.accountsQuery.refetch();
  }
  protected retryDetail(): void {
    if (this.actor !== null && !this.denied) void this.accountQuery.refetch();
  }
  protected recheck(): void {
    void recheckOperatorAuthority(
      this.client,
      this.ownerId,
      () => this.ownerId,
      () => this.sessionQuery.refetch(),
    ).then(() => {
      this.sync();
      this.change.markForCheck();
    });
  }
  private errorText(error: unknown): string {
    if (error instanceof ApiFailure) {
      if (error.status === 404) return 'This account record is unavailable.';
      if (error.status === 422)
        return 'These filters or the page cursor could not be used. Check filters or return to the first page.';
    }
    return 'The inspection could not be completed. Your filters are kept. Try again.';
  }
}
