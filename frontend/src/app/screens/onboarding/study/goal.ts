import { confirmDraftExit } from '../../draft-exit';
import { trustedVerifiedActor } from '../../verified-actor';
import { GoalAssistance } from './ai/goal-assistance';
import type {
  ApplyGoalText,
  ApplyGoalArea,
  AssistanceExpired,
  GoalAssistanceDraft,
} from './ai/goal-assistance-contract';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { HttpClient } from '@angular/common/http';
import {
  Component,
  DestroyRef,
  ChangeDetectorRef,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import type { OnChanges } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import type { AbstractControl } from '@angular/forms';
import {
  TuiButton,
  TuiInput,
  TuiLink,
  TuiLoader,
  TuiCheckbox,
  TuiDataList,
  TuiDialogService,
} from '@taiga-ui/core';
import { TuiComboBox, TuiChevron, TuiTextarea } from '@taiga-ui/kit';
import {
  CancelledError,
  MutationObserver,
  QueryClient,
  QueryObserver,
  queryOptions,
} from '@tanstack/angular-query-experimental';
import type {
  QueryFunctionContext,
  QueryObserverResult,
} from '@tanstack/angular-query-experimental';
import type { Api } from '../../../api.generated';
import { ApiFailure, readJson, writeJson } from '../../../api-http';
import { isUncertain } from '../../uncertain';
import { isCatalogue, isGoal, isOwnGoal } from './goal-contract';
import type { CanonicalChoice, CatalogueView, SubjectChoice } from './goal-contract';

type Identity = Api['schemas']['IdentityResponse'];
interface GoalIntent {
  readonly body: Api['schemas']['SaveGoalRequest'];
  readonly key: string;
  readonly accountId: string;
}
function goalOptions(http: Readonly<HttpClient>, accountId: string | null, enabled: boolean) {
  return queryOptions({
    queryKey:
      accountId === null
        ? (['goal-editor-idle', 'goal'] as const)
        : (['account', accountId, 'goal'] as const),
    enabled,
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(http, '/api/v1/me/goal', signal, isOwnGoal),
  });
}
function catalogueOptions(
  http: Readonly<HttpClient>,
  accountId: string | null,
  query: string,
  cursor: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey:
      accountId === null
        ? (['goal-editor-idle', 'subjects'] as const)
        : (['account', accountId, 'subjects', query, cursor] as const),
    enabled,
    retry: false,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(
        http,
        `/api/v1/subjects?query=${encodeURIComponent(query)}&limit=20${cursor === null ? '' : `&cursor=${encodeURIComponent(cursor)}`}`,
        signal,
        isCatalogue,
      ),
    select: (value: Api['schemas']['SubjectsResponse']): CatalogueView => ({
      ...value,
      items: value.items.map((item): CanonicalChoice => ({
        kind: 'canonical',
        id: item.id,
        label: item.name,
        aliases: item.aliases,
      })),
    }),
  });
}
function selected(
  control: Readonly<AbstractControl<SubjectChoice | string | null>>,
): { readonly subject: true } | null {
  return control.value === null || typeof control.value === 'string' ? { subject: true } : null;
}

@Component({
  selector: 'peerly-study-goal',
  imports: [
    ReactiveFormsModule,
    TuiInput,
    TuiButton,
    TuiLink,
    TuiLoader,
    TuiCheckbox,
    TuiDataList,
    TuiComboBox,
    TuiChevron,
    TuiTextarea,
    GoalAssistance,
  ],
  templateUrl: './goal.html',
  styleUrl: './goal.less',
})
export class StudyGoal implements OnChanges {
  public readonly actor = input.required<Identity>();
  public readonly checking = input(false);
  public readonly expired = output();
  private readonly draftId = signal(crypto.randomUUID());
  private readonly draftVersion = signal(1);
  private readonly draftOwner = signal<string | null>(null);
  private readonly applied = signal<Readonly<{
    readonly original: string;
    readonly target: Api['schemas']['GoalTextTarget'];
    readonly version: number;
    readonly actorId: string;
  }> | null>(null);

  protected readonly appliedText = this.applied.asReadonly();
  private readonly dialogs = inject(TuiDialogService);
  private readonly source = signal<Readonly<{
    readonly id: string | null;
    readonly version: number;
  }> | null>(null);
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly lifetime = new AbortController();
  protected readonly subject = new FormControl<SubjectChoice | string | null>(null, {
    validators: [selected],
  });
  protected readonly topic = new FormControl('', {
    nonNullable: true,
    validators: [Validators.maxLength(80)],
  });
  protected readonly context = new FormControl('', {
    nonNullable: true,
    validators: [Validators.maxLength(240)],
  });
  protected readonly shared = new FormControl(false, { nonNullable: true });
  protected readonly form = new FormGroup({
    subject: this.subject,
    topic: this.topic,
    context: this.context,
    shared: this.shared,
  });
  protected readonly label = (value: SubjectChoice | string | null): string =>
    typeof value === 'string' ? value : (value?.label ?? '');
  protected readonly sameSubject = (
    left: SubjectChoice | string | null,
    right: SubjectChoice | string | null,
  ): boolean => {
    if (left === null || right === null || typeof left === 'string' || typeof right === 'string')
      return left === right;
    return left.kind === 'canonical' && right.kind === 'canonical'
      ? left.id === right.id
      : left.kind === right.kind && left.label === right.label;
  };
  private readonly goalQuery = new QueryObserver(this.client, goalOptions(this.http, null, false));
  private readonly catalogueQuery = new QueryObserver(
    this.client,
    catalogueOptions(this.http, null, '', null, false),
  );
  private readonly saveMutation = new MutationObserver(this.client, {
    retry: false,
    mutationFn: (intent: Readonly<GoalIntent>) => {
      const actor = trustedVerifiedActor(this.client, intent.accountId);
      if (this.checking() || !this.current(intent.accountId) || actor === null)
        throw new CancelledError();
      return writeJson(
        this.http,
        '/api/v1/me/goal',
        intent.body,
        { 'x-csrf-token': actor.csrf_token, 'idempotency-key': intent.key },
        isGoal,
        'PUT',
      );
    },
    onSuccess: async (result, intent: Readonly<GoalIntent>) => {
      if (!this.current(intent.accountId)) return;
      this.adoptGoal(result);
      if (trustedVerifiedActor(this.client, intent.accountId) !== null && !this.checking()) {
        const canonical = await this.goalQuery.refetch();
        if (
          this.current(intent.accountId) &&
          canonical.isSuccess &&
          (canonical.data.goal?.id !== result.id || canonical.data.goal.version >= result.version)
        )
          this.adoptGoal(canonical.data.goal);
      } else
        await this.client.invalidateQueries({
          queryKey: ['account', intent.accountId, 'goal'],
          refetchType: 'none',
        });
    },
    onError: (error: unknown, intent: Readonly<GoalIntent>) => {
      if (!this.current(intent.accountId)) return;
      this.denied(error);
    },
  });
  protected get assistanceDraft(): GoalAssistanceDraft {
    return {
      source: { kind: 'draft', id: this.draftId(), version: this.draftVersion() },
      context: this.context.value,
      topic: this.topic.value,
      areaLabel: this.label(this.subject.value),
      candidates:
        this.catalogue.data?.items.map((item) => ({ id: item.id, name: item.label })) ?? [],
    };
  }
  private canApplyAssistance(source: Api['schemas']['DraftSourceRequest']): boolean {
    return (
      !this.lifetime.signal.aborted &&
      !this.locked &&
      trustedVerifiedActor(this.client, this.actor().account_id) !== null &&
      source.id === this.draftId() &&
      source.version === this.draftVersion()
    );
  }

  protected applyAssistanceText(event: ApplyGoalText): void {
    if (!this.canApplyAssistance(event.source)) return;
    const control = event.target === 'context' ? this.context : this.topic;
    const original = control.value;
    control.setValue(event.value);
    control.markAsDirty();
    this.applied.set({
      original,
      target: event.target,
      version: this.draftVersion(),
      actorId: this.actor().account_id,
    });
  }
  protected get mayRestoreOriginal(): boolean {
    const previous = this.appliedText();
    return (
      previous !== null &&
      previous.actorId === this.actor().account_id &&
      this.canApplyAssistance({ kind: 'draft', id: this.draftId(), version: previous.version })
    );
  }
  protected restoreOriginalText(): void {
    const previous = this.appliedText();
    if (
      previous?.actorId !== this.actor().account_id ||
      !this.canApplyAssistance({ kind: 'draft', id: this.draftId(), version: previous.version })
    )
      return;
    const control = previous.target === 'context' ? this.context : this.topic;
    control.setValue(previous.original);
    control.markAsDirty();
  }
  protected applyAssistanceArea(event: ApplyGoalArea): void {
    if (!this.canApplyAssistance(event.source)) return;
    const choice = this.catalogue.data?.items.find((item) => item.id === event.id);
    if (choice === undefined) return;
    this.subject.setValue(choice);
    this.subject.markAsDirty();
  }
  protected assistanceExpired(event: AssistanceExpired): void {
    if (
      !this.current(event.actorId) ||
      (event.failure.status !== 401 && event.failure.status !== 403)
    )
      return;
    const actor = this.client.getQueryData<Identity | null>(['session']);
    if (actor !== undefined && actor !== null && actor.account_id !== event.actorId) return;
    this.reset();
    this.client.removeQueries({ queryKey: ['account', event.actorId] });
    this.expired.emit();
  }
  protected get draftPresent(): boolean {
    return (
      this.form.dirty ||
      this.subject.value !== null ||
      this.topic.value.length > 0 ||
      this.context.value.length > 0
    );
  }
  protected get goal() {
    return this.goalQuery.getCurrentResult();
  }
  protected get catalogue() {
    return this.catalogueQuery.getCurrentResult();
  }
  protected get saving() {
    return this.saveMutation.getCurrentResult();
  }
  protected get uncertain(): boolean {
    return isUncertain(this.saving.error) || this.saving.error instanceof CancelledError;
  }
  protected get conflict(): boolean {
    return (
      (this.remoteChanged && !this.uncertain) ||
      (this.saving.error instanceof ApiFailure && this.saving.error.status === 409)
    );
  }
  protected get locked(): boolean {
    return this.checking() || this.saving.isPending || this.uncertain || this.conflict;
  }
  protected get searchText(): string {
    const value = this.catalogueQuery.options.queryKey[3];
    if (typeof value !== 'string') throw new Error('Invalid catalogue query key');
    return value;
  }
  protected get searching(): boolean {
    return typeof this.subject.value === 'string' && this.searchText.length > 0;
  }
  protected get canUseCustom(): boolean {
    const size = Array.from(this.searchText.trim()).length;
    return size > 0 && size <= 80;
  }
  protected get customChoice(): Api['schemas']['CustomSubjectRequest'] {
    return { kind: 'custom', label: this.searchText.trim() };
  }
  protected get custom(): boolean {
    return (
      typeof this.subject.value === 'object' &&
      this.subject.value !== null &&
      this.subject.value.kind === 'custom'
    );
  }
  protected get remoteChanged(): boolean {
    const source = this.source();
    const query = this.goal;
    return (
      source !== null &&
      query.isSuccess &&
      !query.isFetching &&
      (source.id !== (query.data.goal?.id ?? null) ||
        source.version !== (query.data.goal?.version ?? 0))
    );
  }
  public get hasUnsavedChanges(): boolean {
    return this.form.dirty;
  }
  public async confirmLeave(): Promise<boolean> {
    const owner = this.actor().account_id;
    const accepted = await confirmDraftExit(this.dialogs, this.destroy, {
      dirty: this.hasUnsavedChanges,
      unconfirmed: this.saving.isPending || this.uncertain,
    });
    return accepted && this.current(owner);
  }
  protected get message(): string | null {
    if (this.saving.error === null) return null;
    if (this.uncertain)
      return 'We couldn’t confirm your save. Retry the same save or reload the saved goal.';
    if (this.saving.error instanceof ApiFailure && this.saving.error.code === 'subject_unavailable')
      return 'This area is no longer available. Reload the saved goal and choose another area.';
    if (
      this.saving.error instanceof ApiFailure &&
      this.saving.error.code === 'goal_version_conflict'
    )
      return 'Your goal changed elsewhere. Your draft is still here. Reload the saved goal before editing again.';
    if (this.conflict)
      return 'We couldn’t resolve this save. Reload the saved goal before trying again.';
    return 'We couldn’t save your goal. Check the area and try again.';
  }
  public constructor() {
    this.form.valueChanges.pipe(takeUntilDestroyed(this.destroy)).subscribe(() => {
      this.draftVersion.update((version) => version + 1);
      this.applied.set(null);
    });
    const update = () => {
      this.change.markForCheck();
    };
    const stopGoal = this.goalQuery.subscribe(
      (result: Readonly<QueryObserverResult<Api['schemas']['OwnGoalResponse']>>) => {
        if (result.isSuccess && !result.isFetching && this.source() === null)
          this.adoptGoal(result.data.goal);
        this.denied(result.error);
        update();
      },
    );
    const stopCatalogue = this.catalogueQuery.subscribe(
      (result: Readonly<QueryObserverResult<CatalogueView>>) => {
        this.denied(result.error);
        update();
      },
    );
    const stopSave = this.saveMutation.subscribe(update);
    this.destroy.onDestroy(() => {
      this.lifetime.abort();
      this.reset();
      stopGoal();
      stopCatalogue();
      stopSave();
      this.goalQuery.destroy();
      this.catalogueQuery.destroy();
    });
  }
  public ngOnChanges(): void {
    if (
      this.draftOwner() !== this.actor().account_id ||
      this.actor().account_status !== 'active' ||
      this.actor().membership_status !== 'verified'
    ) {
      this.reset();
      this.saveMutation.reset();
      this.draftId.set(crypto.randomUUID());
      this.draftVersion.set(1);
      this.draftOwner.set(this.actor().account_id);
    }
    const eligible =
      trustedVerifiedActor(this.client, this.actor().account_id) !== null && !this.checking();
    this.goalQuery.setOptions(goalOptions(this.http, this.actor().account_id, eligible));
    this.catalogueQuery.setOptions(
      catalogueOptions(this.http, this.actor().account_id, '', null, eligible),
    );
  }
  private denied(error: unknown): void {
    if (
      this.current(this.actor().account_id) &&
      error instanceof ApiFailure &&
      (error.status === 401 || error.status === 403)
    ) {
      this.reset();
      this.client.removeQueries({ queryKey: ['account', this.actor().account_id] });
      this.expired.emit();
    }
  }
  private current(accountId: string): boolean {
    const actor = this.client.getQueryData<Identity | null>(['session']);
    return (
      !this.lifetime.signal.aborted &&
      this.actor().account_id === accountId &&
      actor?.account_id === accountId
    );
  }
  private adoptGoal(goal: Api['schemas']['GoalResponse'] | null): void {
    const next = {
      subject:
        goal === null
          ? null
          : 'id' in goal.subject
            ? { kind: 'canonical' as const, id: goal.subject.id, label: goal.subject.label }
            : { kind: 'custom' as const, label: goal.subject.label },
      topic: goal?.topic ?? '',
      context: goal?.context ?? '',
      shared: goal?.shared_learning ?? false,
    };
    this.source.set({ id: goal?.id ?? null, version: goal?.version ?? 0 });
    this.applied.set(null);
    if (
      !this.sameSubject(this.subject.value, next.subject) ||
      this.label(this.subject.value) !== this.label(next.subject) ||
      this.topic.value !== next.topic ||
      this.context.value !== next.context ||
      this.shared.value !== next.shared
    )
      this.form.reset(next);
    else this.form.markAsPristine();
  }
  private reset(): void {
    this.source.set(null);
    this.form.reset({ subject: null, topic: '', context: '', shared: false });
  }
  protected search(event: Readonly<Event>): void {
    if (
      this.locked ||
      trustedVerifiedActor(this.client, this.actor().account_id) === null ||
      !(event.target instanceof HTMLInputElement)
    )
      return;
    this.subject.setValue(event.target.value);
    this.subject.markAsDirty();
    this.catalogueQuery.setOptions(
      catalogueOptions(this.http, this.actor().account_id, event.target.value, null, true),
    );
  }
  protected more(): void {
    const cursor = this.catalogue.data?.next_cursor;
    if (
      this.locked ||
      trustedVerifiedActor(this.client, this.actor().account_id) === null ||
      cursor === null ||
      cursor === undefined
    )
      return;
    this.catalogueQuery.setOptions(
      catalogueOptions(this.http, this.actor().account_id, this.searchText, cursor, true),
    );
  }
  protected async retryCatalogue(): Promise<void> {
    if (this.checking() || trustedVerifiedActor(this.client, this.actor().account_id) === null)
      return;
    await this.catalogueQuery.refetch();
  }
  protected async reload(): Promise<void> {
    if (
      this.saving.isPending ||
      this.checking() ||
      trustedVerifiedActor(this.client, this.actor().account_id) === null
    )
      return;
    this.source.set(null);
    this.applied.set(null);
    this.form.markAsPristine();
    this.saveMutation.reset();
    await this.goalQuery.refetch();
  }
  protected async save(): Promise<void> {
    this.form.markAllAsTouched();
    const current = this.goal.data;
    const choice = this.subject.value;
    if (
      this.checking() ||
      trustedVerifiedActor(this.client, this.actor().account_id) === null ||
      this.form.invalid ||
      this.saving.isPending ||
      this.conflict ||
      this.goal.isFetching ||
      current === undefined ||
      this.source() === null ||
      choice === null ||
      typeof choice === 'string'
    )
      return;
    const topic = this.topic.value.trim();
    const context = this.context.value.trim();
    const body: Api['schemas']['SaveGoalRequest'] = {
      subject:
        choice.kind === 'canonical'
          ? { kind: 'canonical', id: choice.id }
          : { kind: 'custom', label: choice.label },
      topic: topic.length === 0 ? null : topic,
      context: context.length === 0 ? null : context,
      shared_learning: this.shared.value,
      expected_goal_id: this.source()?.id ?? null,
      expected_version: this.source()?.version ?? 0,
    };
    const previous = this.saving.variables;
    const intent =
      this.uncertain && previous !== undefined
        ? previous
        : { body, key: crypto.randomUUID(), accountId: this.actor().account_id };
    try {
      await this.saveMutation.mutate(intent);
    } catch (error: unknown) {
      if (!(error instanceof ApiFailure) && !(error instanceof CancelledError)) throw error;
    }
  }
}
