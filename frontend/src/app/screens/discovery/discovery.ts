import { contextLabel, goalOptions, helpOptions } from './context-label';
import { trustedVerifiedActor } from '../verified-actor';
import { StudentLayout } from '../student-layout';
import { HttpClient } from '@angular/common/http';
import { Component, DestroyRef, ChangeDetectorRef, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TuiButton, TuiIcon, TuiCell, TuiTitle, TuiAppearance } from '@taiga-ui/core';
import { TuiBadge } from '@taiga-ui/kit/components/badge';
import { TuiSegmented } from '@taiga-ui/kit/components/segmented';
import { TuiCardLarge, TuiBlockStatus } from '@taiga-ui/layout';
import { TuiAutoFocus } from '@taiga-ui/cdk';
import {
  QueryClient,
  QueryObserver,
  MutationObserver,
  CancelledError,
} from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { ApiFailure, writeJson } from '../../api-http';
import { sessionOptions } from '../session';
import { isUncertain } from '../uncertain';
import {
  discoveryMode,
  discoveryView,
  discoveryOptions,
  isPass,
  relevanceText,
} from './discovery-contract';
import { DiscoveryPhoto } from './discovery-photo';
import { RequestComposer } from './compose/compose';
import { requestParameters } from './compose/compose-contract';
import type { ComposerSelection, SendResult } from './compose/compose-contract';

type Identity = Api['schemas']['IdentityResponse'];
type Mode = Api['schemas']['DiscoveryMode'];
type View = Api['schemas']['DiscoveryView'];
interface Intent {
  readonly actorId: string;
  readonly scope: object;
  readonly personId: string;
  readonly key: string;
  readonly body: Api['schemas']['ChangePassRequest'];
}
@Component({
  selector: 'app-discovery',
  imports: [
    StudentLayout,
    RouterLink,
    TuiButton,
    TuiIcon,
    TuiCell,
    TuiTitle,
    TuiCardLarge,
    TuiBlockStatus,
    TuiBadge,
    TuiSegmented,
    TuiAppearance,
    DiscoveryPhoto,
    RequestComposer,
    TuiAutoFocus,
  ],
  templateUrl: './discovery.html',
  styleUrl: './discovery.less',
})
export class Discovery {
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly scope = signal<object>({});
  protected readonly menu = signal(false);
  protected readonly relevanceText = relevanceText;
  protected readonly modes = [
    { id: 'find_help', label: 'Find help' },
    { id: 'offer_help', label: 'Offer help' },
    { id: 'study_together', label: 'Study together' },
  ] as const;
  private readonly sessionQuery = new QueryObserver(
    this.client,
    sessionOptions(this.http, this.client),
  );
  private readonly deckQuery = new QueryObserver(
    this.client,
    discoveryOptions(this.http, null, 'find_help', 'candidates', null, false),
  );
  private readonly goalQuery = new QueryObserver(this.client, goalOptions(this.http, null, false));
  private readonly helpQuery = new QueryObserver(this.client, helpOptions(this.http, null, false));
  protected get savedContextLabel(): string | null {
    if (this.actorId === null || this.deck.isFetching || !this.deck.isSuccess) return null;
    const goal = this.goalQuery.getCurrentResult();
    const help = this.helpQuery.getCurrentResult();
    return contextLabel(
      this.deck.data.context,
      goal.isSuccess && !goal.isFetching ? goal.data : undefined,
      help.isSuccess && !help.isFetching ? help.data : undefined,
    );
  }
  private syncContext(): void {
    const id = this.actorId;
    const trusted = id !== null && trustedVerifiedActor(this.client, id) !== null;
    const context =
      this.deckQuery.options.queryKey[1] === id && this.deck.isSuccess && !this.deck.isFetching
        ? this.deck.data.context
        : null;
    this.goalQuery.setOptions(
      goalOptions(this.http, id, trusted && context !== null && context.mode !== 'offer_help'),
    );
    this.helpQuery.setOptions(
      helpOptions(this.http, id, trusted && context?.mode === 'offer_help'),
    );
  }
  private readonly mutation = new MutationObserver(this.client, {
    mutationKey: ['discovery-pass'],
    retry: false,
    mutationFn: (intent: Intent) =>
      writeJson(
        this.http,
        `/api/v1/discovery/passes/${encodeURIComponent(intent.personId)}`,
        intent.body,
        this.headers(intent),
        (value): value is Api['schemas']['PrivatePassResponse'] =>
          isPass(value) &&
          value.person_id === intent.personId &&
          value.passed === intent.body.passed,
        'PUT',
      ),
    onSuccess: async (_receipt: Api['schemas']['PrivatePassResponse'], intent: Intent) => {
      if (!this.current(intent)) return;
      await this.client.invalidateQueries({ queryKey: ['account', intent.actorId, 'discovery'] });
    },
    onError: (error: unknown, intent: Intent) => {
      if (this.current(intent)) this.reauthorize(error);
    },
  });
  protected get session() {
    return this.sessionQuery.getCurrentResult();
  }
  protected get deck() {
    return this.deckQuery.getCurrentResult();
  }
  protected get decision() {
    return this.mutation.getCurrentResult();
  }
  protected get mode(): Mode {
    return discoveryMode(this.route.snapshot.queryParamMap.get('mode')) ?? 'find_help';
  }
  protected get view(): View {
    return discoveryView(this.route.snapshot.queryParamMap.get('view')) ?? 'candidates';
  }
  protected get pageCursor(): string | null {
    return this.cursor;
  }
  private get cursor(): string | null {
    return this.route.snapshot.queryParamMap.get('cursor');
  }

  protected get actorId(): string | null {
    return this.actor()?.account_id ?? null;
  }
  private owner(): Identity | null {
    const identity = this.session.data;
    return identity?.capabilities.can_use_student_features === true ? identity : null;
  }
  private actor(): Identity | null {
    return this.session.isSuccess && !this.session.isFetching ? this.owner() : null;
  }
  protected get composerActors(): readonly Identity[] {
    const owner = this.session.isSuccess ? this.owner() : null;
    return owner === null ? [] : [owner];
  }
  protected get composerRecipient(): string {
    return this.route.snapshot.queryParamMap.get('person') ?? this.selected?.id ?? '';
  }
  protected get composerName(): string | null {
    return (
      this.deck.data?.people.find((person) => person.id === this.composerRecipient)?.display_name ??
      null
    );
  }
  protected get composerOpen(): boolean {
    return (
      this.route.snapshot.queryParamMap.get('compose') === 'request' &&
      this.composerRecipient !== ''
    );
  }
  protected openComposer(): void {
    if (!this.canDecide || this.selected === undefined || this.view !== 'candidates') return;
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { person: this.selected.id, compose: 'request' },
      queryParamsHandling: 'merge',
    });
  }
  protected closeComposer(): void {
    // Taiga also closes portals during route activation; preserve that navigation.
    if (this.router.currentNavigation() !== null) return;
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { compose: null },
      queryParamsHandling: 'merge',
    });
  }
  protected reconcileComposer(selection: ComposerSelection): void {
    if (selection.actorId !== this.owner()?.account_id) return;
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { person: selection.recipientId, mode: selection.mode, compose: 'request' },
      queryParamsHandling: 'merge',
    });
  }
  protected sentRequest(receipt: SendResult): void {
    void this.router.navigate(['/requests'], { queryParams: requestParameters(receipt) });
  }
  protected composerExpired(): void {
    this.client.setQueryData(['session'], null);
    this.client.removeQueries({ queryKey: ['account'] });
    void this.sessionQuery.refetch();
  }
  protected get selected() {
    const people = this.deck.data?.people ?? [];
    const selectedId = this.route.snapshot.queryParamMap.get('person');
    return people.find((person) => person.id === selectedId) ?? people[0];
  }
  protected get currentCard(): readonly Api['schemas']['DiscoveryCardResponse'][] {
    const person = this.selected;
    return person === undefined ? [] : [person];
  }
  protected get uncertain(): boolean {
    return isUncertain(this.decision.error);
  }
  protected get locked(): boolean {
    return this.decision.isPending || this.decision.isError;
  }
  protected get canDecide(): boolean {
    return (
      this.actorId !== null &&
      this.deck.isSuccess &&
      !this.deck.isFetching &&
      this.deck.data.context !== null &&
      !this.locked
    );
  }
  protected get errorText(): string {
    const error = this.decision.error ?? this.deck.error;
    if (this.uncertain)
      return 'We couldn’t confirm this decision. Retry the same action to check its result.';
    if (error instanceof ApiFailure) {
      if (error.code === 'invalid_cursor')
        return 'This page is no longer available. Refresh from the beginning.';
      if (error.code === 'pass_undo_unavailable')
        return 'Undo is no longer available. Refresh current people.';
      if (error.status === 409)
        return 'Your saved context or pass changed. Refresh before making a new decision.';
      if (error.status === 403)
        return 'Discovery is not available for your account right now. Check your profile setup.';
      if (error.status === 404)
        return 'This person is no longer available. Refresh current people.';
    }
    return 'We couldn’t load people right now. Please try again.';
  }
  public constructor() {
    const session = this.sessionQuery.subscribe(() => {
      this.sync();
      this.change.markForCheck();
    });
    const deck = this.deckQuery.subscribe(() => {
      this.syncContext();
      this.reauthorize(this.deck.error);
      this.change.markForCheck();
    });
    const goal = this.goalQuery.subscribe(() => {
      this.reauthorize(this.goalQuery.getCurrentResult().error);
      this.change.markForCheck();
    });
    const help = this.helpQuery.subscribe(() => {
      this.reauthorize(this.helpQuery.getCurrentResult().error);
      this.change.markForCheck();
    });
    const mutation = this.mutation.subscribe(() => {
      this.change.markForCheck();
    });
    const route = this.route.queryParamMap.subscribe(() => {
      this.sync();
      this.change.markForCheck();
    });
    this.destroy.onDestroy(() => {
      session();
      deck();
      goal();
      help();
      mutation();
      route.unsubscribe();
      this.sessionQuery.destroy();
      this.deckQuery.destroy();
      this.goalQuery.destroy();
      this.helpQuery.destroy();
      this.reset();
    });
  }
  private reset(): void {
    this.scope.set({});
    this.menu.set(false);
    this.mutation.reset();
    for (const mutation of this.client
      .getMutationCache()
      .findAll({ mutationKey: ['discovery-pass'] }))
      this.client.getMutationCache().remove(mutation);
  }
  private sync(): void {
    const owner = this.owner();
    if (this.deckQuery.options.queryKey[1] !== (owner?.account_id ?? null)) this.reset();
    this.syncContext();
    this.deckQuery.setOptions(
      discoveryOptions(
        this.http,
        owner?.account_id ?? null,
        this.mode,
        this.view,
        this.cursor,
        this.actor() !== null,
      ),
    );
  }
  private current(intent: Intent): boolean {
    const identity = this.client.getQueryData<Identity | null>(['session']);
    return (
      !this.destroy.destroyed &&
      intent.scope === this.scope() &&
      identity?.account_id === intent.actorId &&
      identity.capabilities.can_use_student_features
    );
  }
  private headers(intent: Intent): Readonly<Record<string, string>> {
    const identity = this.client.getQueryData<Identity | null>(['session']);
    if (!this.current(intent) || identity === null || identity === undefined)
      throw new CancelledError();
    return { 'X-CSRF-Token': identity.csrf_token, 'Idempotency-Key': intent.key };
  }
  protected reauthorize(error: unknown): void {
    if (!(error instanceof ApiFailure) || error.status !== 401 || this.session.isFetching) return;
    this.client.setQueryData(['session'], null);
    this.client.removeQueries({ queryKey: ['account'] });
    void this.sessionQuery.refetch();
  }
  protected changeMode(index: number): void {
    const mode = this.modes[index]?.id;
    if (mode === undefined || this.locked) return;
    this.navigate(mode, 'candidates', null);
  }
  protected changeView(view: View): void {
    if (!this.locked) this.navigate(this.mode, view, null);
  }
  private navigate(mode: Mode, view: View, cursor: string | null): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { mode, view, cursor, person: null },
      queryParamsHandling: 'merge',
    });
  }
  protected next(): void {
    const cursor = this.deck.data?.next_cursor;
    if (cursor !== undefined && cursor !== null && !this.locked)
      this.navigate(this.mode, this.view, cursor);
  }
  protected select(personId: string): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { person: personId },
      queryParamsHandling: 'merge',
    });
  }
  protected decide(
    person: Api['schemas']['PrivatePassResponse'],
    passed: boolean,
    undo = false,
  ): void {
    const actor = this.actor();
    const context = this.deck.data?.context;
    if (!this.canDecide || actor === null || context === null || context === undefined) return;
    const intent: Intent = {
      actorId: actor.account_id,
      scope: this.scope(),
      personId: person.person_id,
      key: crypto.randomUUID(),
      body: { context, passed, expected_version: person.version, ...(undo ? { undo: true } : {}) },
    };
    void this.mutation.mutate(intent).catch(() => undefined);
  }
  protected retryDecision(): void {
    const intent = this.decision.variables;
    if (!this.uncertain || intent === undefined || !this.current(intent) || this.actor() === null)
      return;
    void this.mutation.mutate(intent).catch(() => undefined);
  }
  protected refresh(): void {
    if (this.decision.isPending || this.actor() === null) return;
    if (!this.uncertain) this.mutation.reset();
    if (this.mode === 'offer_help') void this.helpQuery.refetch();
    else void this.goalQuery.refetch();
    if (this.cursor !== null) this.navigate(this.mode, this.view, null);
    else void this.deckQuery.refetch();
  }
  protected retrySession(): void {
    void this.sessionQuery.refetch();
  }
}
