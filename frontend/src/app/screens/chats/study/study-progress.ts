import { NgTemplateOutlet } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectorRef,
  ErrorHandler,
  computed,
  afterRenderEffect,
  untracked,
  viewChild,
  ViewContainerRef,
  Component,
  DestroyRef,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import type { OnChanges, OnInit, SimpleChanges, TemplateRef } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import type { AbstractControl } from '@angular/forms';
import {
  TuiAppearance,
  TuiButton,
  TuiCheckbox,
  TuiRadio,
  TuiTextfield,
  TuiDialogService,
  TUI_BREAKPOINT,
} from '@taiga-ui/core';
import { TuiCardLarge } from '@taiga-ui/layout';
import { TuiAutoFocus } from '@taiga-ui/cdk';
import { TuiTextarea } from '@taiga-ui/kit/components/textarea';
import {
  CancelledError,
  MutationObserver,
  QueryClient,
  QueryObserver,
} from '@tanstack/angular-query-experimental';
import type { Api } from '../../../api.generated';
import { ApiFailure, writeJson } from '../../../api-http';
import { isUncertain } from '../../uncertain';
import { trustedChatActor } from '../chats-session';
import {
  feedbackOptions,
  isOutcome,
  isPrompt,
  isReceipt,
  outcomeOptions,
  studyKey,
} from './study-contract';
import type { Prompt } from './study-contract';
import type { QueryCacheNotifyEvent } from '@tanstack/angular-query-experimental';

interface Owner {
  readonly actorId: string;
  readonly conversationId: string;
  readonly lifetime: object;
  readonly presentation: object;
  readonly key: string;
}
type Intent = Owner &
  (
    | { readonly kind: 'visit'; readonly body: Api['schemas']['StudyPromptVisitBody'] }
    | {
        readonly kind: 'outcome';
        readonly body: Api['schemas']['StudyOutcomeBody'];
        readonly next: 'checkin' | 'feedback';
      }
    | { readonly kind: 'feedback'; readonly body: Api['schemas']['FeedbackBody'] }
  );
type Result =
  | { readonly kind: 'visit'; readonly value: Prompt }
  | { readonly kind: 'outcome'; readonly value: Api['schemas']['StudyOutcomeResponse'] }
  | { readonly kind: 'feedback'; readonly value: Api['schemas']['FeedbackReceiptResponse'] };

@Component({
  selector: 'app-study-progress',
  imports: [
    NgTemplateOutlet,
    TuiAutoFocus,
    TuiAppearance,
    TuiCardLarge,
    ReactiveFormsModule,
    TuiButton,
    TuiCheckbox,
    TuiRadio,
    TuiTextfield,
    TuiTextarea,
  ],
  templateUrl: './study-progress.html',
  styleUrl: './study-progress.less',
})
export class StudyProgress implements OnChanges, OnInit {
  public readonly actor = input.required<Api['schemas']['IdentityResponse']>();
  public readonly conversationId = input.required<string>();
  public readonly peerLabel = input<string | null>(null);
  public readonly contextLabel = input<string | null>(null);
  public readonly manualOpen = input(0);
  public readonly visit = input<Readonly<{ readonly id: string }> | null>(null);
  public readonly closed = output();
  public readonly sessionFailure = output<ApiFailure>();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly lifetime = signal<object>({});
  private readonly presentation = signal<object>({});
  private readonly visited = signal<ReadonlySet<string>>(new Set());
  private readonly mutationOwner: object = {};
  // This is the editable draft's immutable CAS basis, not a projection of the
  // latest query version. Only hydration or an explicit review replaces it.
  private readonly draftBase = signal<number | null>(null);
  private readonly reported = signal<unknown>(null);
  protected readonly view = signal<'hidden' | 'checkin' | 'feedback' | 'saved'>('hidden');
  private readonly feedbackOpen = computed(
    () => this.view() === 'feedback' || this.view() === 'saved',
  );
  private readonly feedbackDialog = viewChild.required<TemplateRef<unknown>>('feedbackDialog');
  private readonly feedbackContent = viewChild('feedbackContent', { read: ViewContainerRef });
  private readonly dialogs = inject(TuiDialogService);
  private readonly errors = inject(ErrorHandler);
  private readonly breakpoint = inject(TUI_BREAKPOINT);

  public constructor() {
    // Taiga retains leaving dialogs for their native exit animation. Retire the
    // template's private content in Angular's render before releasing its portal,
    // so a conversation or actor change cannot animate the previous draft.
    // Only explicit feedback owns a modal; automatic offers stay inline.
    afterRenderEffect((cleanup) => {
      if (!this.feedbackOpen()) return;
      const template = this.feedbackDialog();
      const subscription = untracked(() =>
        this.dialogs
          .open(template, {
            label: '',
            closable: false,
            size: 'm',
            appearance: this.breakpoint() === 'mobile' ? 'fullscreen' : 'taiga',
          })
          .subscribe({
            complete: () => {
              this.close();
            },
            error: (error: unknown) => {
              this.close();
              this.errors.handleError(error);
            },
          }),
      );
      cleanup(() => {
        if (this.destroy.destroyed) {
          // The route owner cannot render again once destruction has started.
          // Its portal content still has a live, app-owned embedded view: clear
          // that view before Taiga preserves its DOM for the exit animation.
          this.view.set('hidden');
          this.form.reset();
          const content = this.feedbackContent()?.get(0);
          if (content !== undefined && content !== null && !content.destroyed)
            content.detectChanges();
        }
        subscription.unsubscribe();
      });
    });
  }
  protected readonly feedbackFormId = `study-feedback-${crypto.randomUUID()}`;
  protected readonly againLabels: Readonly<Record<Api['schemas']['StudyAgain'], string>> = {
    yes: 'Yes',
    maybe: 'Maybe',
    no: 'No',
  };
  protected readonly form = new FormGroup({
    again: new FormControl<Api['schemas']['StudyAgain'] | null>(
      null,
      (control: Readonly<AbstractControl<unknown>>) =>
        control.value === null ? { required: true } : null,
    ),
    easy: new FormControl(false, { nonNullable: true }),
    prepared: new FormControl(false, { nonNullable: true }),
    supportive: new FormControl(false, { nonNullable: true }),
    note: new FormControl('', {
      nonNullable: true,
      validators: [
        (control: Readonly<AbstractControl<unknown>>) =>
          typeof control.value === 'string' && Array.from(control.value).length > 1000
            ? { maxlength: true }
            : null,
      ],
    }),
  });
  private readonly outcomeQuery = new QueryObserver(
    this.client,
    outcomeOptions(this.http, null, '', false),
  );
  private readonly feedbackQuery = new QueryObserver(
    this.client,
    feedbackOptions(this.http, null, '', false),
  );
  private readonly mutation = new MutationObserver(this.client, {
    mutationKey: ['study-progress'],
    meta: { studyProgress: this.mutationOwner },
    retry: false,
    mutationFn: (intent: Intent) => this.write(intent),
    onError: (error: unknown, intent: Intent) => {
      if (this.owns(intent)) this.report(error);
    },
  });
  protected get outcome() {
    return this.outcomeQuery.getCurrentResult();
  }
  protected get feedback() {
    return this.feedbackQuery.getCurrentResult();
  }
  protected get command() {
    return this.mutation.getCurrentResult();
  }
  protected get uncertain(): boolean {
    return isUncertain(this.command.error);
  }
  protected get conflict(): boolean {
    return this.command.error instanceof ApiFailure && this.command.error.status === 409;
  }
  protected get busy(): boolean {
    return this.command.isPending;
  }
  protected get draftChanged(): boolean {
    const base = this.draftBase();
    return (
      base !== null &&
      this.feedback.isSuccess &&
      base !== (this.feedback.data.current?.version ?? 0)
    );
  }
  protected get reviewLocked(): boolean {
    return this.busy || this.uncertain || this.feedback.isFetching || !this.trusted();
  }
  protected get locked(): boolean {
    return this.busy || this.uncertain || this.conflict || !this.trusted();
  }
  protected get needsConfirmation(): boolean {
    return this.feedback.data?.outcome?.answer !== 'yes';
  }
  protected get publication(): Api['schemas']['FeedbackPublication'] | null {
    return this.feedback.data?.submission_publication ?? null;
  }
  protected get readError(): unknown {
    return this.view() === 'feedback' || this.view() === 'saved'
      ? this.feedback.error
      : this.outcome.error;
  }
  protected get errorText(): string {
    const error = this.command.error ?? this.readError;
    if (this.uncertain)
      return 'We couldn’t confirm whether this action was saved. Your original answers are kept. Retry the same action to check its result.';
    if (error instanceof ApiFailure) {
      if (error.code === 'worked_confirmation_required')
        return 'Your worked-together confirmation changed. Reload the current record before confirming again. Your draft is kept.';
      if (error.status === 409)
        return 'This record changed. Reload the current record before reviewing and saving again. Your draft is kept.';
      if (error.status === 401) return 'Your session needs to be checked before continuing.';
      if (error.status === 403 || error.status === 404)
        return 'Study progress is unavailable for this conversation.';
      if (error.status === 422)
        return 'These answers could not be accepted. Review your answers and try again.';
    }
    return 'We couldn’t load or save study progress. Your answers are kept.';
  }
  public ngOnInit(): void {
    const outcome = this.outcomeQuery.subscribe(() => {
      this.report(this.outcome.error);
      this.change.markForCheck();
    });
    const feedback = this.feedbackQuery.subscribe(() => {
      this.hydrate();
      this.report(this.feedback.error);
      this.change.markForCheck();
    });
    const mutation = this.mutation.subscribe(() => {
      this.settleSuccessful();
      this.change.markForCheck();
    });
    const session = this.client
      .getQueryCache()
      .subscribe((event: Readonly<QueryCacheNotifyEvent>) => {
        const key: unknown = event.query.queryKey;
        if (!Array.isArray(key) || key[0] !== 'session') return;
        const identity = this.client.getQueryData<Api['schemas']['IdentityResponse'] | null>([
          'session',
        ]);
        if (identity?.account_id !== this.actor().account_id) this.reset();
        else {
          this.configure();
          this.settleSuccessful();
        }
        this.change.markForCheck();
      });
    this.destroy.onDestroy(() => {
      outcome();
      feedback();
      mutation();
      session();
      this.reset();
      this.outcomeQuery.destroy();
      this.feedbackQuery.destroy();
    });
  }
  public ngOnChanges(changes: Readonly<SimpleChanges>): void {
    const previous: unknown = changes['actor']?.previousValue;
    if (
      (changes['conversationId'] !== undefined && !changes['conversationId'].firstChange) ||
      (typeof previous === 'object' &&
        previous !== null &&
        'account_id' in previous &&
        previous.account_id !== this.actor().account_id)
    )
      this.reset();
    if (changes['manualOpen'] !== undefined && this.manualOpen() > 0) this.open();
    const visit = this.visit();
    if (
      changes['visit'] !== undefined &&
      visit !== null &&
      !this.visited().has(visit.id) &&
      this.trusted() &&
      !this.busy &&
      !this.uncertain &&
      !this.conflict
    ) {
      this.visited.update((values) => new Set([...values, visit.id]));
      this.run({ ...this.owner(visit.id), kind: 'visit', body: {} });
    }
  }
  private trusted(): boolean {
    return trustedChatActor(this.client, this.actor().account_id) !== null;
  }
  private owns(intent: Intent): boolean {
    return (
      !this.destroy.destroyed &&
      intent.lifetime === this.lifetime() &&
      intent.actorId === this.actor().account_id &&
      intent.conversationId === this.conversationId()
    );
  }
  private owner(key: string = crypto.randomUUID()): Owner {
    return {
      actorId: this.actor().account_id,
      conversationId: this.conversationId(),
      lifetime: this.lifetime(),
      presentation: this.presentation(),
      key,
    };
  }
  private async write(intent: Intent): Promise<Result> {
    const identity = trustedChatActor(this.client, intent.actorId);
    if (!this.owns(intent) || identity === null) throw new CancelledError();
    const url = `/api/v1/conversations/${encodeURIComponent(intent.conversationId)}`;
    const headers = { 'X-CSRF-Token': identity.csrf_token, 'Idempotency-Key': intent.key };
    switch (intent.kind) {
      case 'visit':
        return {
          kind: 'visit',
          value: await writeJson(
            this.http,
            `${url}/study-prompt-visits`,
            intent.body,
            headers,
            (value): value is Prompt => isPrompt(value, intent.conversationId),
          ),
        };
      case 'outcome':
        return {
          kind: 'outcome',
          value: await writeJson(
            this.http,
            `${url}/study-outcome`,
            intent.body,
            headers,
            (value): value is Api['schemas']['StudyOutcomeResponse'] =>
              isOutcome(value) &&
              value.conversation_id === intent.conversationId &&
              value.answer === intent.body.answer,
            'PUT',
          ),
        };
      case 'feedback':
        return {
          kind: 'feedback',
          value: await writeJson(
            this.http,
            `${url}/feedback`,
            intent.body,
            headers,
            (value): value is Api['schemas']['FeedbackReceiptResponse'] =>
              isReceipt(value) &&
              value.conversation_id === intent.conversationId &&
              value.again === intent.body.again,
            'PUT',
          ),
        };
    }
  }
  private settleSuccessful(): void {
    const command = this.command;
    // Keep a known response in its owning observer while /me is in flight.
    // Only the same reauthorized actor may settle it; reset retires old actors.
    if (!command.isSuccess || !this.trusted()) return;
    this.settle(command.data, command.variables);
    this.retireCommand();
  }
  private settle(result: Result, intent: Intent): void {
    if (!this.owns(intent) || !this.trusted()) return;
    const key = studyKey(intent.actorId, intent.conversationId);
    const presenting = intent.presentation === this.presentation();
    if (result.kind === 'visit') {
      if (presenting && result.value.outcome === 'offered' && this.view() === 'hidden') this.open();
    } else if (result.kind === 'outcome' && intent.kind === 'outcome') {
      if (presenting) this.view.set(intent.next);
      this.configure();
      // An idempotent replay can return an older successful revision. The
      // receipt is command history; only a canonical GET supplies current state.
      void this.client.invalidateQueries({ queryKey: key });
    } else if (result.kind === 'feedback') {
      this.form.reset();
      this.draftBase.set(null);
      if (presenting) this.view.set('saved');
      void this.client.invalidateQueries({ queryKey: key });
    }
    this.configure();
  }
  private report(error: unknown): void {
    if (
      error instanceof ApiFailure &&
      (error.status === 401 || error.status === 403) &&
      error !== this.reported()
    ) {
      this.reported.set(error);
      this.sessionFailure.emit(error);
    }
  }
  private configure(): void {
    const enabled = this.view() !== 'hidden' && this.trusted();
    this.outcomeQuery.setOptions(
      outcomeOptions(this.http, this.actor().account_id, this.conversationId(), enabled),
    );
    this.feedbackQuery.setOptions(
      feedbackOptions(
        this.http,
        this.actor().account_id,
        this.conversationId(),
        enabled && this.view() !== 'checkin',
      ),
    );
    this.hydrate();
  }
  private hydrate(): void {
    if (this.view() !== 'feedback' || this.draftBase() !== null || !this.feedback.isSuccess) return;
    const current = this.feedback.data.current;
    this.form.reset({
      again: current?.again ?? null,
      easy: current?.descriptors.includes('easy_to_communicate') ?? false,
      prepared: current?.descriptors.includes('prepared') ?? false,
      supportive: current?.descriptors.includes('supportive') ?? false,
      note: current?.team_note ?? '',
    });
    this.draftBase.set(current?.version ?? 0);
  }
  private run(intent: Intent): void {
    // Expected transport/cancellation failures belong to MutationObserver UI.
    // Unexpected programming errors must still reach application diagnostics.
    void this.mutation.mutate(intent).catch((error: unknown) => {
      if (!(error instanceof ApiFailure) && !(error instanceof CancelledError)) throw error;
    });
  }
  private retireCommand(): void {
    this.mutation.reset();
    for (const mutation of this.client.getMutationCache().getAll())
      if (mutation.options.meta?.['studyProgress'] === this.mutationOwner)
        this.client.getMutationCache().remove(mutation);
  }
  private reset(): void {
    const key = this.outcomeQuery.options.queryKey.slice(0, -1);
    this.lifetime.set({});
    this.presentation.set({});
    this.visited.set(new Set());
    this.view.set('hidden');
    this.form.reset();
    this.draftBase.set(null);
    this.reported.set(null);
    this.retireCommand();
    this.outcomeQuery.setOptions(outcomeOptions(this.http, null, '', false));
    this.feedbackQuery.setOptions(feedbackOptions(this.http, null, '', false));
    if (key[1] !== null) {
      void this.client.cancelQueries({ queryKey: key });
      this.client.removeQueries({ queryKey: key });
    }
  }
  protected open(): void {
    this.presentation.set({});
    this.view.set('checkin');
    this.configure();
  }
  protected close(): void {
    this.presentation.set({});
    this.view.set('hidden');
    this.configure();
    this.closed.emit();
  }
  protected answer(
    answer: Api['schemas']['StudyAnswer'],
    next: 'checkin' | 'feedback' = 'checkin',
  ): void {
    if (this.locked || !this.outcome.isSuccess || this.outcome.isFetching) return;
    this.run({
      ...this.owner(),
      kind: 'outcome',
      body: { answer, expected_version: this.outcome.data.outcome?.version ?? 0 },
      next,
    });
  }
  protected showFeedback(): void {
    if (this.busy || this.uncertain || !this.trusted()) return;
    this.view.set('feedback');
    this.configure();
  }
  protected confirm(): void {
    this.answer('yes', 'feedback');
  }
  protected save(): void {
    const base = this.draftBase();
    if (
      this.locked ||
      base === null ||
      this.draftChanged ||
      !this.feedback.isSuccess ||
      this.feedback.isFetching ||
      !this.feedback.data.can_submit ||
      this.needsConfirmation
    )
      return;
    this.form.markAllAsTouched();
    if (this.form.invalid) return;
    const value = this.form.getRawValue();
    if (value.again === null) return;
    const descriptors: readonly Api['schemas']['FeedbackDescriptor'][] = [
      ...(value.easy ? ['easy_to_communicate' as const] : []),
      ...(value.prepared ? ['prepared' as const] : []),
      ...(value.supportive ? ['supportive' as const] : []),
    ];
    this.run({
      ...this.owner(),
      kind: 'feedback',
      body: {
        again: value.again,
        descriptors,
        team_note: value.note.trim().length === 0 ? null : value.note,
        expected_version: base,
      },
    });
  }
  protected retry(): void {
    const intent = this.command.variables;
    if (
      this.command.isError &&
      intent !== undefined &&
      this.owns(intent) &&
      this.trusted() &&
      !this.conflict
    )
      this.run(intent);
  }
  protected reload(): void {
    if (this.busy || this.uncertain || !this.trusted()) return;
    this.retireCommand();
    void this.client.invalidateQueries({
      queryKey: studyKey(this.actor().account_id, this.conversationId()),
    });
  }
  protected reviewAnswers(reviewedVersion: number, loadSaved: boolean): void {
    if (
      this.reviewLocked ||
      !this.feedback.isSuccess ||
      (this.feedback.data.current?.version ?? 0) !== reviewedVersion
    )
      return;
    this.retireCommand();
    if (loadSaved) {
      this.draftBase.set(null);
      this.hydrate();
    } else this.draftBase.set(reviewedVersion);
  }
}
