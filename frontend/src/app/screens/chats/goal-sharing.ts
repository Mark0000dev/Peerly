import { trustedChatActor } from './chats-session';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectorRef, Component, DestroyRef, inject, input, signal } from '@angular/core';
import type { OnChanges, OnInit, SimpleChanges } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TuiButton, TuiLink } from '@taiga-ui/core';
import {
  CancelledError,
  MutationObserver,
  QueryClient,
  QueryObserver,
} from '@tanstack/angular-query-experimental';
import type { QueryCacheNotifyEvent } from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { ApiFailure, writeJson } from '../../api-http';
import { isUncertain } from '../uncertain';
import { currentGoalOptions, isShareReceipt, sharesOptions } from './goal-share-contract';

interface GoalReview {
  readonly goalId: string;
  readonly goalVersion: number;
  readonly contextVersion: number;
}
interface ShareIntent {
  readonly actorId: string;
  readonly conversationId: string;
  readonly lifetime: object;
  readonly key: string;
  readonly body: Api['schemas']['ShareCurrentGoalBody'];
}
@Component({
  selector: 'app-chat-goal-sharing',
  imports: [RouterLink, TuiButton, TuiLink],
  templateUrl: './goal-sharing.html',
  styles: ':host { display: block; min-inline-size: 0; }',
})
export class GoalSharing implements OnChanges, OnInit {
  public readonly actor = input.required<Api['schemas']['IdentityResponse']>();
  public readonly conversationId = input.required<string>();
  public readonly canShare = input.required<boolean>();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly route = inject(ActivatedRoute);
  private readonly mutationOwner: object = {};
  private readonly lifetime = signal<object>({});
  protected readonly opened = signal(false);
  protected readonly review = signal<GoalReview | null>(null);
  private readonly sharesObserver = new QueryObserver(
    this.client,
    sharesOptions(this.http, null, '', null, false),
  );
  private readonly goalObserver = new QueryObserver(
    this.client,
    currentGoalOptions(this.http, null, false),
  );
  private readonly mutation = new MutationObserver(this.client, {
    mutationKey: ['chat-share-goal'],
    meta: { chatShareOwner: this.mutationOwner },
    retry: false,
    mutationFn: (intent: ShareIntent) =>
      writeJson(
        this.http,
        `/api/v1/conversations/${encodeURIComponent(intent.conversationId)}/goal-shares`,
        intent.body,
        this.headers(intent),
        (value): value is Api['schemas']['ConversationGoalShareReceiptResponse'] =>
          isShareReceipt(value) &&
          value.conversation_id === intent.conversationId &&
          value.owner_id === intent.actorId &&
          value.source.goal_id === intent.body.goal_id &&
          value.source.version === intent.body.expected_goal_version,
      ),
    onSuccess: async (
      _receipt: Api['schemas']['ConversationGoalShareReceiptResponse'],
      intent: ShareIntent,
    ) => {
      if (!this.current(intent)) return;
      this.review.set(null);
      await this.client.invalidateQueries({ queryKey: ['account', intent.actorId, 'chats'] });
    },
    onError: (error: unknown, intent: ShareIntent) => {
      if (this.current(intent)) this.reauthorize(error);
    },
  });
  protected get shares() {
    return this.sharesObserver.getCurrentResult();
  }
  protected get goal() {
    return this.goalObserver.getCurrentResult();
  }
  protected get operation() {
    return this.mutation.getCurrentResult();
  }
  protected get cursor(): string | null {
    return this.route.snapshot.queryParamMap.get('share_cursor');
  }
  protected get listCursor(): string | null {
    return this.route.snapshot.queryParamMap.get('cursor');
  }
  protected get historyCursor(): string | null {
    return this.route.snapshot.queryParamMap.get('history_cursor');
  }
  protected get uncertain(): boolean {
    return isUncertain(this.operation.error);
  }
  protected get reviewCurrent(): boolean {
    const review = this.review();
    const goal = this.goal.data?.goal;
    return (
      review !== null &&
      goal?.completed_at === null &&
      review.goalId === goal.id &&
      review.goalVersion === goal.version &&
      review.contextVersion === this.shares.data?.current_context_version
    );
  }
  protected get locked(): boolean {
    return (
      !this.trusted() ||
      !this.canShare() ||
      this.operation.isPending ||
      this.uncertain ||
      this.shares.isFetching ||
      this.goal.isFetching
    );
  }
  protected get errorText(): string {
    if (this.uncertain)
      return 'We couldn’t confirm whether this goal was shared. Retry the same share intent to check its receipt.';
    const error = this.operation.error ?? this.shares.error ?? this.goal.error;
    if (error instanceof ApiFailure && error.status === 409)
      return 'The goal or shared context changed. Refresh and review the current source before sharing.';
    if (error instanceof ApiFailure && error.status === 422)
      return 'This shared-goal page or source is no longer valid. Return to latest shared goals.';
    return 'Shared goals are unavailable right now. Please try again.';
  }
  public ngOnInit(): void {
    const shares = this.sharesObserver.subscribe(() => {
      this.reauthorize(this.shares.error);
      this.change.markForCheck();
    });
    const goal = this.goalObserver.subscribe(() => {
      this.reauthorize(this.goal.error);
      this.change.markForCheck();
    });
    const mutation = this.mutation.subscribe(() => {
      this.change.markForCheck();
    });
    const route = this.route.queryParamMap.subscribe(() => {
      if (this.opened()) this.sync();
    });
    const cache = this.client
      .getQueryCache()
      .subscribe((event: Readonly<QueryCacheNotifyEvent>) => {
        const key: unknown = event.query.queryKey;
        if (!Array.isArray(key) || key[0] !== 'session') return;
        const identity = this.client.getQueryData<Api['schemas']['IdentityResponse'] | null>([
          'session',
        ]);
        if (identity?.account_id !== this.actor().account_id) this.reset();
        if (this.opened()) this.sync();
      });
    this.destroy.onDestroy(() => {
      shares();
      goal();
      mutation();
      cache();
      route.unsubscribe();
      this.sharesObserver.destroy();
      this.goalObserver.destroy();
      this.reset();
    });
  }
  public ngOnChanges(changes: Readonly<SimpleChanges>): void {
    const previous: unknown = changes['conversationId']?.previousValue;
    const previousActor: unknown = changes['actor']?.previousValue;
    if (
      (previous !== undefined && previous !== this.conversationId()) ||
      (typeof previousActor === 'object' &&
        previousActor !== null &&
        'account_id' in previousActor &&
        previousActor.account_id !== this.actor().account_id)
    )
      this.reset();
    if (this.opened()) this.sync();
  }
  private trusted(): boolean {
    return trustedChatActor(this.client, this.actor().account_id) !== null;
  }

  private current(intent: ShareIntent): boolean {
    return (
      !this.destroy.destroyed &&
      this.trusted() &&
      intent.actorId === this.actor().account_id &&
      intent.conversationId === this.conversationId() &&
      intent.lifetime === this.lifetime()
    );
  }
  private headers(intent: ShareIntent): Readonly<Record<string, string>> {
    const identity = this.client.getQueryData<Api['schemas']['IdentityResponse'] | null>([
      'session',
    ]);
    if (!this.current(intent) || identity === undefined || identity === null)
      throw new CancelledError();
    return { 'X-CSRF-Token': identity.csrf_token, 'Idempotency-Key': intent.key };
  }
  private reauthorize(error: unknown): void {
    if (!(error instanceof ApiFailure) || error.status !== 401 || !this.trusted()) return;
    this.client.setQueryData(['session'], null);
    this.client.removeQueries({ queryKey: ['account'] });
    void this.client.invalidateQueries({ queryKey: ['session'] });
  }
  private sync(): void {
    this.sharesObserver.setOptions(
      sharesOptions(
        this.http,
        this.actor().account_id,
        this.conversationId(),
        this.cursor,
        this.trusted() && this.opened(),
      ),
    );
    this.goalObserver.setOptions(
      currentGoalOptions(this.http, this.actor().account_id, this.trusted() && this.opened()),
    );
  }
  private reset(): void {
    this.lifetime.set({});
    this.review.set(null);
    this.opened.set(false);
    this.mutation.reset();
    for (const operation of this.client.getMutationCache().getAll())
      if (operation.options.meta?.['chatShareOwner'] === this.mutationOwner)
        this.client.getMutationCache().remove(operation);
  }
  protected open(): void {
    this.opened.set(true);
    this.sync();
  }
  protected reviewGoal(): void {
    const goal = this.goal.data?.goal;
    const shares = this.shares.data;
    if (
      this.locked ||
      !this.goal.isSuccess ||
      !this.shares.isSuccess ||
      goal?.completed_at !== null ||
      shares === undefined
    )
      return;
    this.review.set({
      goalId: goal.id,
      goalVersion: goal.version,
      contextVersion: shares.current_context_version,
    });
  }
  protected share(): void {
    const review = this.review();
    if (this.locked || !this.reviewCurrent || review === null) return;
    const previous = this.operation.variables;
    const body = {
      goal_id: review.goalId,
      expected_goal_version: review.goalVersion,
      expected_context_version: review.contextVersion,
    };
    const intent: ShareIntent =
      previous !== undefined &&
      this.operation.isError &&
      this.current(previous) &&
      previous.body.goal_id === body.goal_id &&
      previous.body.expected_goal_version === body.expected_goal_version &&
      previous.body.expected_context_version === body.expected_context_version
        ? previous
        : {
            actorId: this.actor().account_id,
            conversationId: this.conversationId(),
            lifetime: this.lifetime(),
            key: crypto.randomUUID(),
            body,
          };
    void this.mutation.mutate(intent).catch(() => undefined);
  }
  protected retryShare(): void {
    const intent = this.operation.variables;
    if (
      !this.uncertain ||
      this.operation.isPending ||
      intent === undefined ||
      !this.current(intent)
    )
      return;
    void this.mutation.mutate(intent).catch(() => undefined);
  }
  protected refresh(): void {
    if (!this.trusted()) return;
    void this.client.invalidateQueries({ queryKey: ['account', this.actor().account_id, 'chats'] });
  }
}
