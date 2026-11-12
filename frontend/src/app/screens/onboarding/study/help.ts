import { confirmDraftExit } from '../../draft-exit';
import { trustedVerifiedActor } from '../../verified-actor';
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
import { FormArray, FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import {
  TuiButton,
  TuiInput,
  TuiLink,
  TuiLoader,
  TuiDialog,
  TuiDialogService,
} from '@taiga-ui/core';
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
import { isCatalogue } from './help-contract';
import { isHelp, isOwnHelp } from '../../study-context-contract';

type Identity = Api['schemas']['IdentityResponse'];
type Subject = Api['schemas']['SubjectResponse'];
interface HelpIntent {
  readonly accountId: string;
  readonly key: string;
  readonly body: Api['schemas']['SaveHelpRequest'];
}
function helpOptions(http: Readonly<HttpClient>, accountId: string | null, enabled: boolean) {
  return queryOptions({
    queryKey:
      accountId === null
        ? (['help-editor-idle', 'help-subjects'] as const)
        : (['account', accountId, 'help-subjects'] as const),
    enabled,
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(http, '/api/v1/me/help-subjects', signal, isOwnHelp),
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
        ? (['help-editor-idle', 'subjects'] as const)
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
  });
}
function row(value: Api['schemas']['HelpSubjectResponse']) {
  return new FormGroup({
    subject: new FormControl(value, { nonNullable: true }),
    note: new FormControl(value.topic_note ?? '', {
      nonNullable: true,
      validators: [Validators.maxLength(80)],
    }),
  });
}

@Component({
  selector: 'peerly-help-subjects',
  imports: [ReactiveFormsModule, TuiInput, TuiButton, TuiLink, TuiLoader, TuiDialog],
  templateUrl: './help.html',
  styleUrl: './help.less',
})
export class HelpSubjects implements OnChanges {
  public readonly actor = input.required<Identity>();
  public readonly checking = input(false);
  public readonly expired = output();
  private readonly dialogs = inject(TuiDialogService);
  private readonly draftOwner = signal<string | null>(null);
  private readonly sourceVersion = signal<number | null>(null);
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly lifetime = new AbortController();
  protected readonly adding = signal(false);
  protected readonly searchText = new FormControl('', { nonNullable: true });
  protected readonly rows = new FormArray<ReturnType<typeof row>>([]);
  protected readonly form = new FormGroup({ subjects: this.rows });
  private readonly helpQuery = new QueryObserver(this.client, helpOptions(this.http, null, false));
  private readonly catalogueQuery = new QueryObserver(
    this.client,
    catalogueOptions(this.http, null, '', null, false),
  );
  private readonly saveMutation = new MutationObserver(this.client, {
    retry: false,
    mutationFn: (intent: Readonly<HelpIntent>) => {
      const actor = trustedVerifiedActor(this.client, intent.accountId);
      if (this.checking() || !this.current(intent.accountId) || actor === null)
        throw new CancelledError();
      return writeJson(
        this.http,
        '/api/v1/me/help-subjects',
        intent.body,
        { 'x-csrf-token': actor.csrf_token, 'idempotency-key': intent.key },
        isHelp,
        'PUT',
      );
    },
    onSuccess: async (result, intent: Readonly<HelpIntent>) => {
      if (!this.current(intent.accountId)) return;
      this.adoptHelp(result);
      if (!this.checking() && trustedVerifiedActor(this.client, intent.accountId) !== null) {
        const canonical = await this.helpQuery.refetch();
        if (
          this.current(intent.accountId) &&
          canonical.isSuccess &&
          (canonical.data.selection === null || canonical.data.selection.version >= result.version)
        )
          this.adoptHelp(canonical.data.selection);
      } else
        await this.client.invalidateQueries({
          queryKey: ['account', intent.accountId, 'help-subjects'],
          refetchType: 'none',
        });
    },
    onError: (error: unknown, intent: Readonly<HelpIntent>) => {
      if (this.current(intent.accountId)) this.denied(error);
    },
  });
  protected get help() {
    return this.helpQuery.getCurrentResult();
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
    return (
      this.checking() ||
      trustedVerifiedActor(this.client, this.actor().account_id) === null ||
      this.saving.isPending ||
      this.uncertain ||
      this.conflict
    );
  }
  protected get draftPresent(): boolean {
    return this.form.dirty || this.rows.length > 0 || this.adding();
  }
  protected get remoteChanged(): boolean {
    const source = this.sourceVersion();
    const current = this.help;
    return (
      source !== null &&
      current.isSuccess &&
      !current.isFetching &&
      source !== (current.data.selection?.version ?? 0)
    );
  }
  public get hasUnsavedChanges(): boolean {
    return this.form.dirty;
  }
  public async confirmLeave(): Promise<boolean> {
    const owner = this.actor().account_id;
    const accepted = await confirmDraftExit(this.dialogs, this.destroy, {
      dirty: this.form.dirty,
      unconfirmed: this.saving.isPending || this.uncertain,
    });
    return accepted && this.current(owner);
  }
  protected get message(): string | null {
    if (this.remoteChanged)
      return 'Your help areas changed elsewhere. Your draft is still here. Reload before editing again.';
    if (this.saving.error instanceof CancelledError)
      return 'Your save paused during a sign-in check. Retry the same save once sign-in is confirmed.';
    if (this.saving.error === null) return null;
    if (this.uncertain)
      return 'We couldn’t confirm your save. Retry the same save or reload the saved areas.';
    if (
      this.saving.error instanceof ApiFailure &&
      this.saving.error.code === 'help_version_conflict'
    )
      return 'Your help areas changed elsewhere. Your draft is still here. Reload before editing again.';
    if (this.saving.error instanceof ApiFailure && this.saving.error.code === 'subject_unavailable')
      return 'An area is no longer available. Reload your saved areas and choose another.';
    if (this.conflict)
      return 'We couldn’t resolve this save. Reload your saved areas before trying again.';
    return 'We couldn’t save your areas. Check your choices and try again.';
  }
  public constructor() {
    const update = () => {
      this.change.markForCheck();
    };
    const stopHelp = this.helpQuery.subscribe(
      (result: Readonly<QueryObserverResult<Api['schemas']['OwnHelpResponse']>>) => {
        if (result.isSuccess && !result.isFetching && this.sourceVersion() === null)
          this.adoptHelp(result.data.selection);
        this.denied(result.error);
        update();
      },
    );
    const stopCatalogue = this.catalogueQuery.subscribe(
      (result: Readonly<QueryObserverResult<Api['schemas']['SubjectsResponse']>>) => {
        this.denied(result.error);
        update();
      },
    );
    const stopSave = this.saveMutation.subscribe(update);
    this.destroy.onDestroy(() => {
      this.lifetime.abort();
      this.reset();
      stopHelp();
      stopCatalogue();
      stopSave();
      this.helpQuery.destroy();
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
      this.draftOwner.set(this.actor().account_id);
    }
    const eligible =
      !this.checking() && trustedVerifiedActor(this.client, this.actor().account_id) !== null;
    this.helpQuery.setOptions(helpOptions(this.http, this.actor().account_id, eligible));
    this.catalogueQuery.setOptions(
      catalogueOptions(this.http, this.actor().account_id, '', null, false),
    );
  }
  private current(accountId: string): boolean {
    const actor = this.client.getQueryData<Identity | null>(['session']);
    return (
      !this.lifetime.signal.aborted &&
      this.actor().account_id === accountId &&
      actor?.account_id === accountId
    );
  }
  private adoptHelp(selection: Api['schemas']['HelpResponse'] | null): void {
    this.sourceVersion.set(selection?.version ?? 0);
    this.rows.clear();
    for (const subject of selection?.subjects ?? []) this.rows.push(row(subject));
    this.form.markAsPristine();
  }
  private reset(): void {
    this.sourceVersion.set(null);
    this.rows.clear();
    this.form.markAsPristine();
    this.searchText.reset();
    this.adding.set(false);
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
  protected selected(subject: Readonly<Subject>): boolean {
    return this.rows.controls.some(
      (item: Readonly<ReturnType<typeof row>>) =>
        item.controls.subject.value.subject_id === subject.id,
    );
  }
  protected openPicker(): void {
    if (this.locked || this.rows.length >= 5) return;
    this.searchText.reset();
    this.adding.set(true);
    this.catalogueQuery.setOptions(
      catalogueOptions(this.http, this.actor().account_id, '', null, true),
    );
  }
  protected search(): void {
    if (this.locked) return;
    this.catalogueQuery.setOptions(
      catalogueOptions(this.http, this.actor().account_id, this.searchText.value, null, true),
    );
  }
  protected more(): void {
    const cursor = this.catalogue.data?.next_cursor;
    if (this.locked || cursor === null || cursor === undefined) return;
    this.catalogueQuery.setOptions(
      catalogueOptions(this.http, this.actor().account_id, this.searchText.value, cursor, true),
    );
  }
  protected async retryCatalogue(): Promise<void> {
    if (this.locked) return;
    await this.catalogueQuery.refetch();
  }
  protected choose(subject: Readonly<Subject>): void {
    if (this.locked || this.rows.length >= 5 || this.selected(subject)) return;
    this.rows.push(row({ subject_id: subject.id, label: subject.name, topic_note: null }));
    this.form.markAsDirty();
    this.adding.set(false);
  }
  protected remove(index: number): void {
    if (this.locked || index < 0 || index >= this.rows.length) return;
    this.rows.removeAt(index);
    this.form.markAsDirty();
  }
  protected async reload(): Promise<void> {
    if (
      this.saving.isPending ||
      this.checking() ||
      trustedVerifiedActor(this.client, this.actor().account_id) === null
    )
      return;
    this.sourceVersion.set(null);
    this.form.markAsPristine();
    this.saveMutation.reset();
    await this.helpQuery.refetch();
  }
  protected async save(): Promise<void> {
    this.form.markAllAsTouched();
    if (
      this.checking() ||
      trustedVerifiedActor(this.client, this.actor().account_id) === null ||
      this.sourceVersion() === null ||
      this.form.invalid ||
      this.saving.isPending ||
      this.conflict ||
      this.help.isFetching ||
      this.help.data === undefined
    )
      return;
    const body: Api['schemas']['SaveHelpRequest'] = {
      expected_version: this.sourceVersion() ?? 0,
      subjects: this.rows.controls.map((item: Readonly<ReturnType<typeof row>>) => ({
        subject_id: item.controls.subject.value.subject_id,
        topic_note:
          item.controls.note.value.trim().length === 0 ? null : item.controls.note.value.trim(),
      })),
    };
    const previous = this.saving.variables;
    const intent =
      this.uncertain && previous !== undefined
        ? previous
        : { accountId: this.actor().account_id, body, key: crypto.randomUUID() };
    try {
      await this.saveMutation.mutate(intent);
    } catch (error: unknown) {
      if (!(error instanceof ApiFailure) && !(error instanceof CancelledError)) throw error;
    }
  }
}
