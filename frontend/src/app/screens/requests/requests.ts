import { StudentNavigation } from '../student-navigation';
import { DOCUMENT } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectorRef, Component, DestroyRef, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TuiAppearance, TuiButton, TuiLink, TuiDialog } from '@taiga-ui/core';
import { TuiCardLarge, TuiAppBar, TuiBlockStatus } from '@taiga-ui/layout';
import { TuiAutoFocus } from '@taiga-ui/cdk';
import {
  CancelledError,
  MutationObserver,
  QueryClient,
  QueryObserver,
} from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { ApiFailure, writeJson } from '../../api-http';
import { sessionOptions } from '../session';
import { isUncertain } from '../uncertain';
import {
  isRequestReceipt,
  isViewedReceipt,
  peerName,
  requestBox,
  requestDetailOptions,
  requestOptions,
  requestReason,
  requestView,
  undoRemaining,
  sentWhen,
  expiresWhen,
} from './requests-contract';
import type { RequestAction } from './requests-contract';

type Identity = Api['schemas']['IdentityResponse'];
type Summary = Api['schemas']['RequestSummaryResponse'];
interface OwnedIntent {
  readonly actorId: string;
  readonly scope: object;
  readonly requestId: string;
  readonly key: string;
}
interface Decision extends OwnedIntent {
  readonly action: RequestAction;
  readonly body: Api['schemas']['RequestActionBody'];
}
interface Acknowledgement extends OwnedIntent {
  readonly version: number;
  readonly body: Api['schemas']['ViewRequestBody'];
}

@Component({
  selector: 'app-requests',
  imports: [
    StudentNavigation,
    RouterLink,
    TuiButton,
    TuiAppearance,
    TuiCardLarge,
    TuiAppBar,
    TuiBlockStatus,
    TuiDialog,
    TuiAutoFocus,
    TuiLink,
  ],
  templateUrl: './requests.html',
  styleUrl: './requests.less',
})
export class Requests {
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly document = inject(DOCUMENT);
  private readonly scope = signal<object>({});
  private readonly clock = signal(Date.now());
  protected readonly withdrawal = signal<string | null>(null);
  protected readonly peerName = peerName;
  protected readonly requestReason = requestReason;
  protected readonly sentWhen = sentWhen;
  protected readonly expiresWhen = expiresWhen;
  private readonly sessionQuery = new QueryObserver(
    this.client,
    sessionOptions(this.http, this.client),
  );
  private readonly listQuery = new QueryObserver(
    this.client,
    requestOptions(this.http, null, 'received', 'active', null, false),
  );
  private readonly detailQuery = new QueryObserver(
    this.client,
    requestDetailOptions(this.http, null, null, false),
  );
  private readonly mutation = new MutationObserver(this.client, {
    mutationKey: ['requests-decision'],
    retry: false,
    mutationFn: (intent: Decision) =>
      writeJson(
        this.http,
        `/api/v1/requests/${encodeURIComponent(intent.requestId)}/${intent.action}`,
        intent.body,
        this.headers(intent),
        (value): value is Api['schemas']['RequestMutationResponse'] =>
          isRequestReceipt(value) &&
          value.request_id === intent.requestId &&
          value.outcome ===
            (
              {
                accept: 'accepted',
                decline: 'declined',
                'undo-decline': 'undo_decline',
                withdraw: 'withdrawn',
              } as const
            )[intent.action],
      ),
    onSuccess: async (_receipt: Api['schemas']['RequestMutationResponse'], intent: Decision) => {
      if (!this.current(intent)) return;
      this.withdrawal.set(null);
      await this.refreshOwned(intent.actorId);
    },
    onError: (error: unknown, intent: Decision) => {
      if (this.current(intent)) this.reauthorize(error);
    },
  });
  private readonly acknowledgement = new MutationObserver(this.client, {
    mutationKey: ['requests-viewed'],
    retry: false,
    mutationFn: (intent: Acknowledgement) =>
      writeJson(
        this.http,
        `/api/v1/requests/${encodeURIComponent(intent.requestId)}/viewed`,
        intent.body,
        this.headers(intent),
        (value): value is Api['schemas']['ViewedResponse'] =>
          isViewedReceipt(value) &&
          value.request_id === intent.requestId &&
          value.stored_version === intent.version,
      ),
    onSuccess: async (_receipt: Api['schemas']['ViewedResponse'], intent: Acknowledgement) => {
      if (this.current(intent)) await this.refreshOwned(intent.actorId);
    },
    onError: (error: unknown, intent: Acknowledgement) => {
      if (this.current(intent)) this.reauthorize(error);
    },
  });
  protected get session() {
    return this.sessionQuery.getCurrentResult();
  }
  protected get list() {
    return this.listQuery.getCurrentResult();
  }
  protected get detail() {
    return this.detailQuery.getCurrentResult();
  }
  protected get decision() {
    return this.mutation.getCurrentResult();
  }
  protected get viewed() {
    return this.acknowledgement.getCurrentResult();
  }
  protected get box() {
    return requestBox(this.route.snapshot.queryParamMap.get('box'));
  }
  protected get view() {
    return requestView(this.route.snapshot.queryParamMap.get('view'), this.box);
  }
  protected get selectedId() {
    return this.route.snapshot.queryParamMap.get('request');
  }
  private get cursor() {
    return this.route.snapshot.queryParamMap.get('cursor');
  }
  private owner(): Identity | null {
    const identity = this.session.data;
    return identity?.capabilities.can_use_student_features === true ? identity : null;
  }
  private actor(): Identity | null {
    return this.session.isSuccess && !this.session.isFetching ? this.owner() : null;
  }
  protected get actorId(): string | null {
    return this.actor()?.account_id ?? null;
  }
  protected get locked(): boolean {
    return (
      this.decision.isPending ||
      this.decision.isError ||
      this.viewed.isPending ||
      this.viewed.isError
    );
  }
  protected get uncertain(): boolean {
    return isUncertain(this.decision.error);
  }
  protected get uncertainView(): boolean {
    return isUncertain(this.viewed.error);
  }
  protected get errorText(): string {
    const error = this.decision.error ?? this.viewed.error ?? this.detail.error ?? this.list.error;
    if (this.uncertain || this.uncertainView)
      return 'We couldn’t confirm this action. Retry the same action to check its result.';
    if (error instanceof ApiFailure) {
      if (error.status === 404) return 'This request is no longer available.';
      if (error.status === 409)
        return 'This request changed or the action is no longer available. Refresh before deciding again.';
      if (error.status === 422)
        return 'This page or action is no longer available. Refresh from the beginning.';
      if (error.status === 403) return 'Requests are not available for your account right now.';
    }
    return 'We couldn’t load requests right now. Please try again.';
  }
  protected get selectedDetail(): readonly Api['schemas']['RequestDetailResponse'][] {
    return this.detail.isSuccess ? [this.detail.data] : [];
  }
  protected get visibleRequests(): readonly Summary[] {
    if (this.selectedId !== null) return this.detail.isSuccess ? [this.detail.data.request] : [];
    return this.list.isSuccess ? this.list.data.requests : [];
  }
  protected stateText(item: Summary): string {
    if (this.box === 'sent' && (item.state === 'declined' || item.state === 'pending_decline'))
      return item.state === 'pending_decline' ? 'Pending' : 'Closed';
    return (
      {
        pending: 'Pending',
        pending_decline: 'Declined · Undo available',
        accepted: 'Accepted',
        declined: 'Declined',
        withdrawn: 'Withdrawn',
        expired: 'Expired',
        closed: 'Closed',
      } as const
    )[item.state];
  }
  public constructor() {
    const session = this.sessionQuery.subscribe(() => {
      this.sync();
      this.change.markForCheck();
    });
    const list = this.listQuery.subscribe(() => {
      this.reauthorize(this.list.error);
      this.change.markForCheck();
    });
    const detail = this.detailQuery.subscribe(() => {
      this.reauthorize(this.detail.error);
      this.change.markForCheck();
    });
    const decision = this.mutation.subscribe(() => {
      this.change.markForCheck();
    });
    const viewed = this.acknowledgement.subscribe(() => {
      this.change.markForCheck();
    });
    const route = this.route.queryParamMap.subscribe(() => {
      this.withdrawal.set(null);
      this.sync();
      this.change.markForCheck();
    });
    const timer = setInterval(() => {
      const before = this.clock();
      const now = Date.now();
      const items = [
        ...(this.list.data?.requests ?? []),
        ...(this.detail.data === undefined ? [] : [this.detail.data.request]),
      ];
      const expired = items.some((item) => {
        const received =
          this.detail.data?.request === item ? this.detail.dataUpdatedAt : this.list.dataUpdatedAt;
        return (
          undoRemaining(item, received, before) > 0 && undoRemaining(item, received, now) === 0
        );
      });
      this.clock.set(now);
      const actor = this.actor();
      if (expired && actor !== null) void this.refreshOwned(actor.account_id);
    }, 250);
    this.destroy.onDestroy(() => {
      clearInterval(timer);
      session();
      list();
      detail();
      decision();
      viewed();
      route.unsubscribe();
      this.sessionQuery.destroy();
      this.listQuery.destroy();
      this.detailQuery.destroy();
      this.reset();
    });
  }
  private reset(): void {
    this.scope.set({});
    this.withdrawal.set(null);
    this.mutation.reset();
    this.acknowledgement.reset();
    for (const key of ['requests-decision', 'requests-viewed']) {
      for (const mutation of this.client.getMutationCache().findAll({ mutationKey: [key] }))
        this.client.getMutationCache().remove(mutation);
    }
  }
  private sync(): void {
    const owner = this.owner();
    if (this.listQuery.options.queryKey[1] !== (owner?.account_id ?? null)) this.reset();
    this.listQuery.setOptions(
      requestOptions(
        this.http,
        owner?.account_id ?? null,
        this.box,
        this.view,
        this.cursor,
        this.actor() !== null,
      ),
    );
    this.detailQuery.setOptions(
      requestDetailOptions(
        this.http,
        owner?.account_id ?? null,
        this.selectedId,
        this.actor() !== null,
      ),
    );
  }
  private current(intent: OwnedIntent): boolean {
    const identity = this.client.getQueryData<Identity | null>(['session']);
    return (
      !this.destroy.destroyed &&
      intent.scope === this.scope() &&
      identity?.account_id === intent.actorId &&
      this.client.getQueryState(['session'])?.fetchStatus === 'idle' &&
      identity.capabilities.can_use_student_features
    );
  }
  private headers(intent: OwnedIntent): Readonly<Record<string, string>> {
    const identity = this.client.getQueryData<Identity | null>(['session']);
    if (!this.current(intent) || identity === undefined || identity === null)
      throw new CancelledError();
    return { 'X-CSRF-Token': identity.csrf_token, 'Idempotency-Key': intent.key };
  }
  private async refreshOwned(actorId: string): Promise<void> {
    await this.client.invalidateQueries({ queryKey: ['account', actorId, 'requests'] });
  }
  private reauthorize(error: unknown): void {
    if (!(error instanceof ApiFailure) || error.status !== 401 || this.session.isFetching) return;
    this.client.setQueryData(['session'], null);
    this.client.removeQueries({ queryKey: ['account'] });
    void this.sessionQuery.refetch();
  }
  protected remaining(item: Summary): number {
    const received =
      this.detail.data?.request === item ? this.detail.dataUpdatedAt : this.list.dataUpdatedAt;
    return undoRemaining(item, received, this.clock());
  }
  protected allowed(item: Summary, action: RequestAction): boolean {
    const capability = action === 'undo-decline' ? 'undo_decline' : action;
    return (
      this.actor() !== null &&
      !this.locked &&
      item.capabilities[capability] &&
      !this.list.isFetching &&
      !this.detail.isFetching &&
      (action !== 'undo-decline' || this.remaining(item) > 0)
    );
  }
  protected decide(item: Summary, action: RequestAction): void {
    const actor = this.actor();
    if (actor === null || !this.allowed(item, action)) return;
    void this.mutation
      .mutate({
        actorId: actor.account_id,
        scope: this.scope(),
        requestId: item.request_id,
        key: crypto.randomUUID(),
        action,
        body: { person_id: item.peer.person_id, expected_version: item.version },
      })
      .catch(() => undefined);
  }
  protected acknowledge(): void {
    const actor = this.actor();
    const detail = this.detail.data;
    if (
      actor === null ||
      !this.detail.isSuccess ||
      this.detail.isFetching ||
      detail === undefined ||
      !detail.request.unread ||
      this.locked ||
      this.document.visibilityState !== 'visible'
    )
      return;
    void this.acknowledgement
      .mutate({
        actorId: actor.account_id,
        scope: this.scope(),
        requestId: detail.request.request_id,
        version: detail.disclosed_version,
        key: crypto.randomUUID(),
        body: { disclosure_id: detail.disclosure_id },
      })
      .catch(() => undefined);
  }
  protected retryDecision(): void {
    const intent = this.decision.variables;
    if (this.uncertain && intent !== undefined && this.current(intent) && this.actor() !== null)
      void this.mutation.mutate(intent).catch(() => undefined);
  }
  protected retryView(): void {
    const intent = this.viewed.variables;
    if (
      this.uncertainView &&
      intent !== undefined &&
      this.current(intent) &&
      this.actor() !== null &&
      this.document.visibilityState === 'visible'
    )
      void this.acknowledgement.mutate(intent).catch(() => undefined);
  }
  protected refresh(): void {
    const actor = this.actor();
    if (actor === null || this.decision.isPending || this.viewed.isPending) return;
    if (!this.uncertain) this.mutation.reset();
    if (!this.uncertainView) this.acknowledgement.reset();
    this.withdrawal.set(null);
    if (this.cursor !== null) this.navigate(this.box, this.view, null, this.selectedId);
    else void this.refreshOwned(actor.account_id);
  }
  private navigate(
    box: Api['schemas']['RequestBox'],
    view: Api['schemas']['RequestListView'],
    cursor: string | null,
    request: string | null,
  ): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { box, view, cursor, request },
      queryParamsHandling: 'merge',
    });
  }
  protected changeBox(box: Api['schemas']['RequestBox']): void {
    if (!this.locked) this.navigate(box, 'active', null, null);
  }
  protected changeView(view: Api['schemas']['RequestListView']): void {
    if (!this.locked) this.navigate(this.box, requestView(view, this.box), null, null);
  }
  protected select(request: string | null): void {
    if (!this.locked) this.navigate(this.box, this.view, this.cursor, request);
  }
  protected next(): void {
    const cursor = this.list.data?.next_cursor;
    if (!this.locked && cursor !== undefined && cursor !== null)
      this.navigate(this.box, this.view, cursor, null);
  }
  protected retrySession(): void {
    void this.sessionQuery.refetch();
  }
}
