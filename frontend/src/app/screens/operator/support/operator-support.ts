import { HttpClient } from '@angular/common/http';
import { ChangeDetectorRef, Component, DestroyRef, inject, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink, convertToParamMap } from '@angular/router';
import type { ParamMap } from '@angular/router';
import { QueryClient, QueryObserver } from '@tanstack/angular-query-experimental';
import type { Query } from '@tanstack/angular-query-experimental';
import { TuiButton, TuiDialogService, TuiInput, TuiLink, TuiTextfield } from '@taiga-ui/core';
import { TuiNativeSelect } from '@taiga-ui/kit/components/select';
import type { Api } from '../../../api.generated';
import { ApiFailure } from '../../../api-http';
import { sessionOptions } from '../../session';
import {
  operatorDenied,
  retireOperatorFailure,
  recheckOperatorAuthority,
} from '../operator-authority';
import { inboxOptions, caseOptions, historyOptions } from './support-query';
import { statusText, topicText, supportStatuses, supportTopics } from './support-contract';
import { supportRoute } from './support-route';
import { SupportStatusEditor } from './support-status';

@Component({
  selector: 'app-operator-support',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TuiButton,
    TuiInput,
    TuiLink,
    TuiTextfield,
    TuiNativeSelect,
  ],
  templateUrl: './operator-support.html',
  styleUrl: './operator-support.less',
})
export class OperatorSupport {
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly dialogs = inject(TuiDialogService);
  private readonly pendingRoute = signal(false);
  private readonly submitted = signal(false);
  protected readonly textFields = [
    { key: 'case_id', label: 'Case ID', hint: 'Exact stored case UUID.' },
    { key: 'actor_id', label: 'Account ID', hint: 'Exact linked account UUID.' },
    {
      key: 'received_from',
      label: 'Received from',
      hint: 'Inclusive date and time with timezone.',
    },
    {
      key: 'received_before',
      label: 'Received before',
      hint: 'Exclusive date and time with timezone.',
    },
  ] as const;
  protected readonly topics: readonly string[] = ['all', ...supportTopics];
  protected readonly statuses: readonly string[] = ['all', ...supportStatuses];
  protected readonly changeStatuses = supportStatuses;
  protected readonly accountFilters = ['all', 'true', 'false'] as const;
  protected readonly statusText = statusText;
  protected readonly topicText = topicText;
  protected readonly form = new FormGroup({
    case_id: new FormControl('', { nonNullable: true }),
    actor_id: new FormControl('', { nonNullable: true }),
    received_from: new FormControl('', { nonNullable: true }),
    received_before: new FormControl('', { nonNullable: true }),
    topic: new FormControl<string | null>('all'),
    status: new FormControl<string | null>('all'),
    anonymous: new FormControl<string | null>('all'),
  });
  private readonly sessionQuery = new QueryObserver(
    this.client,
    sessionOptions(this.http, this.client),
  );
  private readonly inboxQuery = new QueryObserver(
    this.client,
    inboxOptions(this.http, null, {}, false),
  );
  private readonly caseQuery = new QueryObserver(
    this.client,
    caseOptions(this.http, null, null, false),
  );
  private readonly historyQuery = new QueryObserver(
    this.client,
    historyOptions(this.http, null, null, null, false),
  );
  protected readonly editor = new SupportStatusEditor(
    this.http,
    this.client,
    this.dialogs,
    this.destroy,
    {
      actor: () => (this.denied ? null : this.actor),
      owner: () => this.ownerId,
      selected: () => this.state.caseId,
      current: () => this.current,
      refresh: async () => await this.refreshCase(),
      changed: async () => {
        const actor = this.actor;
        if (actor !== null)
          await this.client.invalidateQueries({
            queryKey: ['account', actor.account_id, 'operator', 'support'],
          });
      },
      authorityFailure: (error, actor) => {
        this.privateChanged(error, actor);
      },
      mark: () => {
        this.change.markForCheck();
      },
    },
  );
  protected get session() {
    return this.sessionQuery.getCurrentResult();
  }
  protected get inbox() {
    return this.inboxQuery.getCurrentResult();
  }
  protected get record() {
    return this.caseQuery.getCurrentResult();
  }
  protected get history() {
    return this.historyQuery.getCurrentResult();
  }
  protected get state() {
    return supportRoute(this.route.snapshot.queryParamMap);
  }
  protected get transitioning(): boolean {
    return this.pendingRoute();
  }
  private get ownerId(): string | null {
    return this.session.data?.account_id ?? null;
  }
  protected get actor(): Api['schemas']['IdentityResponse'] | null {
    return this.session.isSuccess && this.session.fetchStatus === 'idle' && !this.pendingRoute()
      ? this.session.data
      : null;
  }
  protected get denied(): boolean {
    return operatorDenied(this.client, this.ownerId);
  }
  protected get current(): Api['schemas']['OperatorSupportResponse'] | undefined {
    return this.actor !== null &&
      !this.denied &&
      this.record.isSuccess &&
      this.record.fetchStatus === 'idle' &&
      this.record.data.receipt.case_id === this.state.caseId
      ? this.record.data
      : undefined;
  }
  protected get formError(): string | null {
    return this.submitted() ? supportRoute(convertToParamMap(this.draft())).filterError : null;
  }
  public constructor() {
    const session = this.sessionQuery.subscribe(() => {
      const previous = this.inboxQuery.options.queryKey[1];
      if (
        this.session.isSuccess &&
        this.session.fetchStatus === 'idle' &&
        typeof previous === 'string' &&
        previous !== this.ownerId
      )
        this.resetCursors(true);
      this.sync();
      this.change.markForCheck();
    });
    const inbox = this.inboxQuery.subscribe(() => {
      this.privateChanged(this.inbox.error, this.inboxQuery.options.queryKey[1]);
      this.change.markForCheck();
    });
    const record = this.caseQuery.subscribe(() => {
      this.privateChanged(this.record.error, this.caseQuery.options.queryKey[1]);
      this.editor.syncOwner(this.ownerId, this.state.caseId);
      this.change.markForCheck();
    });
    const history = this.historyQuery.subscribe(() => {
      this.privateChanged(this.history.error, this.historyQuery.options.queryKey[1]);
      this.change.markForCheck();
    });
    const mutations = this.client.getMutationCache().subscribe(() => {
      this.change.markForCheck();
    });
    const route = this.route.queryParamMap.subscribe((params: Readonly<ParamMap>) => {
      for (const field of this.textFields)
        this.form.controls[field.key].setValue(params.get(field.key) ?? '');
      this.form.controls.topic.setValue(params.get('topic') ?? 'all');
      this.form.controls.status.setValue(params.get('status') ?? 'all');
      this.form.controls.anonymous.setValue(params.get('anonymous') ?? 'all');
      this.form.markAsPristine();
      this.submitted.set(false);
      const previous = this.caseQuery.options.queryKey[5];
      if (typeof previous === 'string' && previous !== this.state.caseId) this.resetCursors(false);
      this.sync();
      this.change.markForCheck();
    });
    this.destroy.onDestroy(() => {
      session();
      inbox();
      record();
      history();
      mutations();
      route.unsubscribe();
      this.editor.destroy();
      const actor = this.ownerId;
      // Detach current observer snapshots before leaving a retained403 mutation
      // authority marker in the shared cache. No private DTO is kept by this view.
      this.inboxQuery.setOptions(inboxOptions(this.http, null, {}, false));
      this.caseQuery.setOptions(caseOptions(this.http, null, null, false));
      this.historyQuery.setOptions(historyOptions(this.http, null, null, null, false));
      this.sessionQuery.destroy();
      this.inboxQuery.destroy();
      this.caseQuery.destroy();
      this.historyQuery.destroy();
      this.retire(['account', actor, 'operator', 'support']);
      this.form.reset();
    });
  }
  private resetCursors(actorChanged: boolean): void {
    const params = this.route.snapshot.queryParamMap;
    if (
      this.pendingRoute() ||
      (!params.has('history_cursor') && !(actorChanged && params.has('cursor')))
    )
      return;
    this.pendingRoute.set(true);
    void this.router
      .navigate([], {
        relativeTo: this.route,
        queryParams: actorChanged
          ? { cursor: null, history_cursor: null }
          : { history_cursor: null },
        queryParamsHandling: 'merge',
      })
      .then(() => {
        if (this.destroy.destroyed) return;
        this.pendingRoute.set(false);
        this.sync();
        this.change.markForCheck();
      });
  }
  private sync(): void {
    if (this.destroy.destroyed) return;
    const state = this.state;
    const enabled = this.actor !== null && !this.denied;
    this.inboxQuery.setOptions(
      inboxOptions(this.http, this.ownerId, state.filters, enabled && state.filterError === null),
    );
    this.caseQuery.setOptions(
      caseOptions(this.http, this.ownerId, state.caseId, enabled && state.caseError === null),
    );
    this.historyQuery.setOptions(
      historyOptions(
        this.http,
        this.ownerId,
        state.caseId,
        state.historyCursor,
        enabled && state.caseError === null && state.historyOpen && state.historyError === null,
      ),
    );
    this.editor.syncOwner(this.ownerId, state.caseId);
  }
  private privateChanged(error: unknown, actor: unknown): void {
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
  private retire(prefix: readonly unknown[]): void {
    void this.client.cancelQueries({ queryKey: prefix });
    this.client.removeQueries({
      queryKey: prefix,
      predicate: (query: Readonly<Query>) =>
        !(query.state.error instanceof ApiFailure && query.state.error.status === 403),
    });
  }
  private draft(): Readonly<Record<string, string>> {
    const raw = this.form.getRawValue();
    return Object.fromEntries(
      Object.entries({
        ...raw,
        topic: raw.topic === 'all' ? '' : (raw.topic ?? ''),
        status: raw.status === 'all' ? '' : (raw.status ?? ''),
        anonymous: raw.anonymous === 'all' ? '' : (raw.anonymous ?? ''),
      })
        .map(([key, value]: readonly [string, string]) => [key, value.trim()] as const)
        .filter(([, value]: readonly [string, string]) => value !== ''),
    );
  }
  protected async search(): Promise<void> {
    this.submitted.set(true);
    this.form.markAllAsTouched();
    if (this.formError !== null || this.actor === null || this.denied) return;
    const target = this.router.createUrlTree([], {
      relativeTo: this.route,
      queryParams: this.draft(),
    });
    if (this.router.serializeUrl(target) === this.router.url) {
      void this.inboxQuery.refetch();
      return;
    }
    const previousFilters = JSON.stringify(this.state.filters);
    const navigated = await this.router.navigateByUrl(target);
    // Selection removal can leave the inbox key unchanged. An explicit search
    // still requests current metadata rather than silently keeping that page.
    if (navigated && previousFilters === JSON.stringify(this.state.filters)) this.retryInbox();
  }
  protected async selectCase(caseId: string | null): Promise<void> {
    await this.navigate({ case: caseId, history: null, history_cursor: null });
  }
  protected async page(cursor: string | null): Promise<void> {
    const same = this.state.filters.cursor === cursor;
    await this.navigate({ cursor, case: null, history: null, history_cursor: null });
    if (same && this.state.caseId === null) this.retryInbox();
  }
  protected async historyPage(cursor: string | null): Promise<void> {
    if (this.state.historyOpen && this.state.historyCursor === cursor) {
      this.retryHistory();
      return;
    }
    await this.navigate({ history: 'open', history_cursor: cursor });
  }
  protected async closeHistory(): Promise<void> {
    this.historyQuery.setOptions(
      historyOptions(this.http, this.ownerId, this.state.caseId, this.state.historyCursor, false),
    );
    this.retire(['account', this.ownerId, 'operator', 'support', 'history', this.state.caseId]);
    await this.navigate({ history: null, history_cursor: null });
  }
  private async navigate(params: Readonly<Record<string, string | null>>): Promise<void> {
    await this.router.navigate([], {
      relativeTo: this.route,
      queryParams: params,
      queryParamsHandling: 'merge',
    });
  }
  protected retryInbox(): void {
    if (this.actor !== null && !this.denied && this.state.filterError === null)
      void this.inboxQuery.refetch();
  }
  protected retryHistory(): void {
    if (this.actor !== null && !this.denied && this.state.historyError === null)
      void this.historyQuery.refetch();
  }
  protected async refreshCase(): Promise<boolean> {
    const actor = this.actor;
    const selected = this.state.caseId;
    if (actor === null || this.denied || this.state.caseError !== null || selected === null)
      return false;
    const result = await this.caseQuery.refetch();
    return (
      this.actor?.account_id === actor.account_id &&
      this.state.caseId === selected &&
      result.isSuccess &&
      result.fetchStatus === 'idle'
    );
  }
  protected async recheck(): Promise<void> {
    await recheckOperatorAuthority(
      this.client,
      this.ownerId,
      () => (this.destroy.destroyed ? null : this.ownerId),
      async () => await this.sessionQuery.refetch(),
    );
    if (this.destroy.destroyed) return;
    this.sync();
    this.change.markForCheck();
  }
  protected cursorError(error: unknown): boolean {
    return error instanceof ApiFailure && error.status === 422;
  }
  protected errorText(error: unknown, kind: 'inbox' | 'case' | 'history'): string {
    if (error instanceof ApiFailure && error.status === 404)
      return kind === 'inbox'
        ? 'The support inbox is unavailable.'
        : 'This support case or history is unavailable.';
    if (this.cursorError(error))
      return 'These filters or this page cursor could not be used. Return to the first page or check the filters.';
    return 'This support record could not be loaded. Other available records stay open. Try again.';
  }
  public async canLeave(): Promise<boolean> {
    return await this.editor.canLeave();
  }
}
