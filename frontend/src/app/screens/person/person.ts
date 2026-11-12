import { SettingsHeader } from '../settings-header';
import { PersonFeedbackSummary } from './feedback-summary';
import { HttpClient } from '@angular/common/http';
import { DatePipe } from '@angular/common';
import { Component, DestroyRef, ChangeDetectorRef, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { TuiBadge, TuiTextarea } from '@taiga-ui/kit';
import {
  TuiButton,
  TuiDialog,
  TuiAppearance,
  TuiRadio,
  TuiCell,
  TuiTitle,
  TuiIcon,
  TuiTextfield,
  TUI_BREAKPOINT,
} from '@taiga-ui/core';
import { TuiCardLarge, TuiAppBarBack } from '@taiga-ui/layout';
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
  blocksOptions,
  commentProblem,
  isBlock,
  isReceipt,
  personOptions,
  photoOptions,
  languageName,
} from './person-contract';

type Actor = Api['schemas']['IdentityResponse'];
interface BlockIntent {
  readonly actor: Actor;
  readonly scope: object;
  readonly personId: string;
  readonly key: string;
  readonly body: Api['schemas']['ChangeBlockRequest'];
}
interface ReportIntent {
  readonly personId: string;
  readonly actor: Actor;
  readonly scope: object;
  readonly key: string;
  readonly body: Api['schemas']['ProfileReportRequest'];
}
@Component({
  selector: 'app-person',
  imports: [
    RouterLink,
    DatePipe,
    TuiButton,
    TuiDialog,
    TuiAppearance,
    TuiCardLarge,
    TuiAppBarBack,
    SettingsHeader,
    ReactiveFormsModule,
    TuiRadio,
    TuiCell,
    TuiTitle,
    TuiIcon,
    TuiTextfield,
    TuiTextarea,
    TuiBadge,
    PersonFeedbackSummary,
  ],
  templateUrl: './person.html',
  styleUrl: './person.less',
})
export class Person {
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly destroy = inject(DestroyRef);
  private readonly change = inject(ChangeDetectorRef);
  private readonly route = inject(ActivatedRoute);
  private get personId(): string {
    return this.route.snapshot.paramMap.get('personId') ?? '';
  }
  protected get discoveryParameters(): Readonly<Record<string, string | null>> {
    const query = this.route.snapshot.queryParamMap;
    const mode = query.get('mode');
    const view = query.get('view');
    if (
      (mode !== 'find_help' && mode !== 'offer_help' && mode !== 'study_together') ||
      (view !== 'candidates' && view !== 'passed')
    )
      return {};
    return { mode, view, cursor: query.get('cursor'), person: this.personId };
  }
  protected get reviewParameters(): Readonly<Record<string, string>> {
    const mode = this.route.snapshot.queryParamMap.get('mode');
    return {
      mode: mode === 'offer_help' || mode === 'study_together' ? mode : 'find_help',
      person: this.personId,
      compose: 'request',
    };
  }
  private readonly sessionQuery = new QueryObserver(
    this.client,
    sessionOptions(this.http, this.client),
  );
  private readonly personQuery = new QueryObserver(
    this.client,
    personOptions(this.http, null, '', false),
  );
  private readonly photoQuery = new QueryObserver(
    this.client,
    photoOptions(this.http, null, '', null, false),
  );
  private readonly blocksQuery = new QueryObserver(
    this.client,
    blocksOptions(this.http, null, null, false),
  );
  protected readonly languageName = languageName;
  protected readonly breakpoint = inject(TUI_BREAKPOINT);
  protected readonly photoUrl = signal<string | null>(null);
  protected readonly photoDecodeFailed = signal(false);
  private readonly scope = signal<object>({});
  private readonly cursor = signal<string | null>(null);
  protected readonly menu = signal(false);
  protected readonly panel = signal<'block' | 'report' | null>(null);
  protected readonly category = new FormControl<Api['schemas']['ReportCategory']>('harassment', {
    nonNullable: true,
  });
  protected readonly comment = new FormControl('', { nonNullable: true });
  protected readonly reportForm = new FormGroup({ category: this.category, comment: this.comment });
  protected readonly validation = signal<string | null>(null);
  private readonly blockObserver = new MutationObserver(this.client, {
    retry: false,
    mutationKey: ['person-safety'],
    mutationFn: (intent: BlockIntent) =>
      writeJson(
        this.http,
        `/api/v1/me/blocks/${encodeURIComponent(intent.personId)}`,
        intent.body,
        this.headers(intent.actor, intent.key),
        isBlock,
        'PUT',
      ),
    onSuccess: async (_result: Api['schemas']['BlockStateResponse'], intent: BlockIntent) => {
      if (!this.current(intent.actor, intent.scope)) return;
      this.panel.set(null);
      this.menu.set(false);
      this.cursor.set(null);
      this.syncBlocks();
      await this.refreshCanonical(intent.actor.account_id);
    },
    onError: (error: unknown, intent: BlockIntent) => {
      if (this.scope() === intent.scope) this.reauthorize(error, intent.actor);
    },
  });
  private readonly reportObserver = new MutationObserver(this.client, {
    retry: false,
    mutationKey: ['person-safety'],
    mutationFn: (intent: ReportIntent) =>
      writeJson(
        this.http,
        '/api/v1/reports',
        intent.body,
        this.headers(intent.actor, intent.key),
        isReceipt,
      ),
    onSuccess: (_result: Api['schemas']['ProfileReportReceipt'], intent: ReportIntent) => {
      if (this.current(intent.actor, intent.scope)) this.comment.reset();
    },
    onError: (error: unknown, intent: ReportIntent) => {
      if (this.scope() === intent.scope) this.reauthorize(error, intent.actor);
    },
  });
  protected get session() {
    return this.sessionQuery.getCurrentResult();
  }
  protected get profile() {
    return this.personQuery.getCurrentResult();
  }
  protected get photo() {
    return this.photoQuery.getCurrentResult();
  }
  protected get blocks() {
    return this.blocksQuery.getCurrentResult();
  }
  protected get blockMutation() {
    return this.blockObserver.getCurrentResult();
  }
  protected get reportMutation() {
    return this.reportObserver.getCurrentResult();
  }
  private owner(): Actor | null {
    const actor = this.session.data ?? null;
    return actor?.capabilities.can_use_student_features === true ? actor : null;
  }
  private actor(): Actor | null {
    return this.session.isFetching || !this.session.isSuccess ? null : this.owner();
  }
  protected get ownBlock(): Api['schemas']['BlockStateResponse'] | undefined {
    return (
      this.blocks.data?.people.find((item) => item.block.person_id === this.personId)?.block ??
      (this.profile.isError ? undefined : this.profile.data?.own_block)
    );
  }
  private get reportContext(): string | null {
    const profile = this.profile.data;
    if (profile !== undefined) return profile.access_context_id;
    const report = this.reportMutation.variables;
    if (report?.scope === this.scope() && report.personId === this.personId)
      return report.body.context_id;
    const block = this.blockMutation.variables;
    return block?.scope === this.scope() && block.personId === this.personId
      ? (block.body.context_id ?? null)
      : null;
  }
  protected get canReport(): boolean {
    return this.reportContext !== null;
  }
  protected get disclosed(): boolean {
    return this.canReport || this.ownBlock?.blocked === true;
  }
  protected get blockUncertain(): boolean {
    return isUncertain(this.blockMutation.error);
  }
  protected get reportUncertain(): boolean {
    return isUncertain(this.reportMutation.error);
  }
  protected get error(): unknown {
    return (
      this.blockMutation.error ??
      this.reportMutation.error ??
      this.profile.error ??
      this.blocks.error
    );
  }
  protected get errorText(): string | null {
    const error = this.error;
    if (error === null) return null;
    if (isUncertain(error))
      return this.blockMutation.error !== null || this.reportMutation.error !== null
        ? 'We couldn’t confirm the result. Refresh current status, or retry the same action.'
        : 'We couldn’t load this profile. Refresh current status to try again.';
    if (error instanceof ApiFailure) {
      if (error.status === 404)
        return this.reportMutation.error === error
          ? 'This report reference is unavailable. Refresh the profile before starting a new report.'
          : 'This profile is unavailable.';
      if (error.status === 409)
        return 'The state changed. Refresh current status before starting a new action.';
      if (error.status === 429) return 'Too many attempts. Please wait before trying again.';
      if (error.status === 401) return 'Your session ended. Sign in again.';
    }
    return 'We couldn’t complete this request. Please try again.';
  }
  protected get retryAt(): string | null {
    const error = this.error;
    return error instanceof ApiFailure ? error.retryAt : null;
  }
  public constructor() {
    const update = () => {
      this.change.markForCheck();
    };
    const photoSubscription = this.photoQuery.subscribe(() => {
      this.updatePhotoUrl();
      this.reauthorizePrivate();
      update();
    });
    const profileSubscription = this.personQuery.subscribe(() => {
      this.syncPhoto();
      this.reauthorizePrivate();
      update();
    });
    const blocksSubscription = this.blocksQuery.subscribe(() => {
      this.reauthorizePrivate();
      update();
    });
    const blockSubscription = this.blockObserver.subscribe(update);
    const reportSubscription = this.reportObserver.subscribe(update);
    const sessionSubscription = this.sessionQuery.subscribe(() => {
      this.syncAccount();
      update();
    });
    const routeSubscription = this.route.paramMap.subscribe(() => {
      this.syncAccount();
      update();
    });
    this.destroy.onDestroy(() => {
      routeSubscription.unsubscribe();
      sessionSubscription();
      profileSubscription();
      photoSubscription();
      blocksSubscription();
      blockSubscription();
      reportSubscription();
      this.sessionQuery.destroy();
      this.personQuery.destroy();
      this.photoQuery.destroy();
      this.blocksQuery.destroy();
      this.resetLocal();
      this.clearPhotoUrl();
    });
  }
  private resetLocal(): void {
    this.scope.set({});
    this.menu.set(false);
    this.panel.set(null);
    this.cursor.set(null);
    this.reportForm.reset();
    this.validation.set(null);
    this.blockObserver.reset();
    this.reportObserver.reset();
    for (const mutation of this.client
      .getMutationCache()
      .findAll({ mutationKey: ['person-safety'] }))
      this.client.getMutationCache().remove(mutation);
  }
  private syncAccount(): void {
    const accountId = this.owner()?.account_id ?? null;
    if (
      this.personQuery.options.queryKey[1] !== accountId ||
      this.personQuery.options.queryKey[3] !== this.personId
    )
      this.resetLocal();
    if (this.session.isFetching) {
      this.panel.set(null);
      this.menu.set(false);
    }
    this.personQuery.setOptions(
      personOptions(this.http, accountId, this.personId, this.actor() !== null),
    );
    this.syncBlocks();
    this.syncPhoto();
  }
  private syncBlocks(): void {
    this.blocksQuery.setOptions(
      blocksOptions(
        this.http,
        this.owner()?.account_id ?? null,
        this.cursor(),
        this.actor() !== null,
      ),
    );
  }
  private syncPhoto(): void {
    this.photoQuery.setOptions(
      photoOptions(
        this.http,
        this.owner()?.account_id ?? null,
        this.personId,
        this.profile.data?.photo.version ?? null,
        this.actor() !== null && this.profile.isSuccess && !this.profile.isFetching,
      ),
    );
    this.updatePhotoUrl();
  }
  private clearPhotoUrl(): void {
    const previous = this.photoUrl();
    if (previous !== null) URL.revokeObjectURL(previous);
    this.photoUrl.set(null);
  }
  private updatePhotoUrl(): void {
    this.clearPhotoUrl();
    const blob = this.photo.data;
    if (
      blob === undefined ||
      this.actor() === null ||
      !this.profile.isSuccess ||
      this.profile.isFetching
    )
      return;
    this.photoDecodeFailed.set(false);
    this.photoUrl.set(URL.createObjectURL(blob));
  }
  private reauthorizePrivate(): void {
    const actor = this.actor();
    if (actor !== null) {
      for (const error of [this.profile.error, this.blocks.error, this.photo.error])
        this.reauthorize(error, actor);
    }
  }
  private current(actor: Actor, scope: object = this.scope()): boolean {
    return (
      !this.destroy.destroyed &&
      this.scope() === scope &&
      this.client.getQueryData<Actor | null>(['session'])?.account_id === actor.account_id
    );
  }
  private headers(actor: Actor, key: string): Readonly<Record<string, string>> {
    const current = this.client.getQueryData<Actor | null>(['session']);
    if (current?.account_id !== actor.account_id)
      throw new ApiFailure(401, 'unauthenticated', null);
    return { 'x-csrf-token': current.csrf_token, 'idempotency-key': key };
  }
  private reauthorize(error: unknown, actor: Actor): void {
    if (this.current(actor) && error instanceof ApiFailure && error.status === 401) {
      this.client.setQueryData(['session'], null);
      this.client.removeQueries({ queryKey: ['account', actor.account_id] });
      this.client.getMutationCache().clear();
      void this.sessionQuery.refetch();
    }
  }
  private handled(error: unknown): void {
    if (!(error instanceof ApiFailure) && !(error instanceof CancelledError)) throw error;
  }
  protected summaryFailure(
    event: Readonly<{ readonly actorId: string; readonly error: ApiFailure }>,
  ): void {
    const actor = this.actor();
    if (
      actor?.account_id !== event.actorId ||
      (event.error.status !== 401 && event.error.status !== 403)
    )
      return;
    this.client.setQueryData(['session'], null);
    this.client.removeQueries({ queryKey: ['account', actor.account_id] });
    this.client.getMutationCache().clear();
    void this.sessionQuery.refetch();
  }
  protected retryPhoto(): void {
    if (this.actor() === null || !this.profile.isSuccess || this.profile.isFetching) return;
    const error = this.photo.error;
    if (error instanceof ApiFailure && error.status === 404) void this.personQuery.refetch();
    else void this.photoQuery.refetch();
  }
  protected closePanel(): void {
    this.panel.set(null);
  }
  protected open(panel: 'block' | 'report'): void {
    this.panel.set(panel);
  }
  protected nextBlocks(): void {
    const next = this.blocks.data?.next_cursor;
    if (next !== undefined && next !== null) {
      this.cursor.set(next);
      this.syncBlocks();
    }
  }
  protected refresh(): void {
    this.menu.set(false);
    if (!isUncertain(this.blockMutation.error)) this.blockObserver.reset();
    if (!isUncertain(this.reportMutation.error)) this.reportObserver.reset();
    this.cursor.set(null);
    this.syncBlocks();
    const actor = this.actor();
    if (actor !== null) void this.refreshCanonical(actor.account_id);
  }
  private async refreshCanonical(accountId: string): Promise<void> {
    await Promise.all([
      this.client.invalidateQueries({
        queryKey: ['account', accountId, 'person', this.personId],
      }),
      this.client.invalidateQueries({ queryKey: ['account', accountId, 'blocks'] }),
    ]);
  }
  protected changeBlock(retry = false): void {
    const actor = this.actor();
    const block = this.ownBlock;
    const context = this.reportContext;
    if (actor === null || this.blockMutation.isPending) return;
    const previous = this.blockMutation.variables;
    if (retry && previous !== undefined && isUncertain(this.blockMutation.error)) {
      void this.blockObserver.mutate(previous).catch((error: unknown) => {
        this.handled(error);
      });
      return;
    }
    if (block === undefined || (!block.blocked && context === null) || this.blockMutation.isError)
      return;
    void this.blockObserver
      .mutate({
        actor,
        scope: this.scope(),
        personId: this.personId,
        key: crypto.randomUUID(),
        body: {
          blocked: !block.blocked,
          expected_version: block.version,
          ...(context === null ? {} : { context_id: context }),
        },
      })
      .catch((error: unknown) => {
        this.handled(error);
      });
  }
  protected submitReport(retry = false): void {
    const actor = this.actor();
    const context = this.reportContext;
    if (actor === null || this.reportMutation.isPending) return;
    const previous = this.reportMutation.variables;
    if (retry && previous !== undefined && isUncertain(this.reportMutation.error)) {
      void this.reportObserver.mutate(previous).catch((error: unknown) => {
        this.handled(error);
      });
      return;
    }
    const problem = commentProblem(this.category.value, this.comment.value);
    this.validation.set(problem);
    const error = this.reportMutation.error;
    if (
      problem !== null ||
      context === null ||
      isUncertain(error) ||
      (error instanceof ApiFailure && error.status === 409)
    )
      return;
    void this.reportObserver
      .mutate({
        actor,
        scope: this.scope(),
        key: crypto.randomUUID(),
        personId: this.personId,
        body: {
          kind: 'profile',
          context_id: context,
          category: this.category.value,
          comment: this.comment.value,
        },
      })
      .catch((error: unknown) => {
        this.handled(error);
      });
  }
}
