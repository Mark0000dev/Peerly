import { confirmDraftExit } from '../../draft-exit';
import { PhotoAssistance } from '../study/ai/photo-assistance';
import type { AssistanceExpired } from '../study/ai/goal-assistance-contract';
import { trustedVerifiedActor } from '../../verified-actor';
import { PhotoWorkflow } from './photo/photo';
import { PhotoReview } from './photo-review';
import { OwnFeedbackSummary } from './feedback-summary';
import { HttpClient } from '@angular/common/http';
import {
  Component,
  DestroyRef,
  ChangeDetectorRef,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import type { OnChanges } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import type { AbstractControl } from '@angular/forms';
import {
  TuiButton,
  TuiInput,
  TuiLink,
  TuiLoader,
  TuiSelectLike,
  TuiDialogService,
} from '@taiga-ui/core';
import {
  TuiAvatar,
  TuiInputChip,
  TuiMultiSelect,
  TuiChevron,
  TuiDataListWrapper,
  TuiTextarea,
} from '@taiga-ui/kit';
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
import { isProfile, isRevision, isProfileReference } from './profile-contract';

type Identity = Api['schemas']['IdentityResponse'];
interface Intent {
  readonly body: Api['schemas']['SaveProfileRequest'];
  readonly key: string;
  readonly accountId: string;
}

function profileOptions(http: Readonly<HttpClient>, accountId: string | null, enabled: boolean) {
  return queryOptions({
    queryKey:
      accountId === null
        ? (['profile-editor-idle', 'profile'] as const)
        : (['account', accountId, 'profile'] as const),
    enabled,
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(http, '/api/v1/me/profile', signal, isProfile),
  });
}

type ProfileReferenceView = Api['schemas']['ProfileReferenceResponse'] & {
  readonly codes: readonly string[];
};

function referenceOptions(http: Readonly<HttpClient>, accountId: string | null, enabled: boolean) {
  return queryOptions({
    queryKey:
      accountId === null
        ? (['profile-editor-idle', 'profile-reference'] as const)
        : (['account', accountId, 'profile-reference'] as const),
    enabled,
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(http, '/api/v1/profile-reference-data', signal, isProfileReference),
    select: (value: Api['schemas']['ProfileReferenceResponse']): ProfileReferenceView => ({
      ...value,
      codes: value.languages.map((item) => item.code),
    }),
  });
}

function textBounds(minimum: number, maximum: number) {
  return (control: Readonly<AbstractControl<string>>): { readonly textLength: true } | null => {
    const length = Array.from(control.value.trim()).length;
    return length < minimum || length > maximum ? { textLength: true } : null;
  };
}

export function validateProfileLanguages(
  values: readonly string[],
  reference: Api['schemas']['ProfileReferenceResponse'],
): { readonly languages: true } | null {
  return values.length > reference.max_languages ||
    new Set(values).size !== values.length ||
    values.some((code) => !reference.languages.some((item) => item.code === code))
    ? { languages: true }
    : null;
}

function optionalText(value: string): string | null {
  const text = value.trim();
  return text.length === 0 ? null : text;
}

@Component({
  selector: 'peerly-profile-basics',
  imports: [
    TuiAvatar,
    ReactiveFormsModule,
    TuiInput,
    TuiButton,
    TuiLink,
    TuiLoader,
    PhotoWorkflow,
    PhotoReview,
    OwnFeedbackSummary,
    PhotoAssistance,
    TuiSelectLike,
    TuiInputChip,
    TuiMultiSelect,
    TuiChevron,
    TuiDataListWrapper,
    TuiTextarea,
  ],
  templateUrl: './profile.html',
  styleUrl: './profile.less',
})
export class ProfileBasics implements OnChanges {
  public readonly actor = input.required<Identity>();
  public readonly checking = input(false);
  public readonly editOptional = input(false);
  public readonly expired = output();
  protected readonly photoOpen = signal(false);
  private readonly photoAdvice = viewChild(PhotoAssistance);
  private readonly details = signal(false);
  protected readonly detailsOpen = this.details.asReadonly();
  private readonly draftOwner = signal<string | null>(null);
  private readonly dialogs = inject(TuiDialogService);
  private readonly sourceVersion = signal<number | null>(null);
  private readonly photoWorkflow = viewChild(PhotoWorkflow);
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly lifetime = new AbortController();
  protected readonly name = new FormControl('', {
    nonNullable: true,
    validators: [textBounds(2, 50)],
  });
  protected readonly about = new FormControl('', {
    nonNullable: true,
    validators: [textBounds(0, 160)],
  });
  protected readonly programme = new FormControl('', {
    nonNullable: true,
    validators: [textBounds(0, 80)],
  });
  protected readonly year = new FormControl('', {
    nonNullable: true,
    validators: [textBounds(0, 32)],
  });
  protected readonly languages = new FormControl<readonly string[]>([], {
    nonNullable: true,
    validators: [Validators.maxLength(5)],
  });
  protected readonly form = new FormGroup({
    name: this.name,
    about: this.about,
    programme: this.programme,
    year: this.year,
    languages: this.languages,
  });
  private readonly referenceQuery = new QueryObserver(
    this.client,
    referenceOptions(this.http, null, false),
  );
  protected readonly languageLabel = (code: string): string =>
    this.reference.data?.languages.find((item) => item.code === code)?.label ?? code;
  protected get languageOptions(): readonly string[] {
    return this.reference.data?.codes ?? [];
  }
  protected get reference() {
    return this.referenceQuery.getCurrentResult();
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

  private readonly profileQuery = new QueryObserver(
    this.client,
    profileOptions(this.http, null, false),
  );
  private readonly saveMutation = new MutationObserver(this.client, {
    retry: false,
    mutationFn: (intent: Readonly<Intent>) => {
      const actor = trustedVerifiedActor(this.client, intent.accountId);
      if (this.checking() || !this.current(intent.accountId) || actor === null)
        throw new CancelledError();
      return writeJson(
        this.http,
        '/api/v1/me/profile',
        intent.body,
        { 'x-csrf-token': actor.csrf_token, 'idempotency-key': intent.key },
        isRevision,
        'PUT',
      );
    },
    onSuccess: async (result, intent: Readonly<Intent>) => {
      if (!this.current(intent.accountId)) return;
      this.resetDraft(result, result.version);
      if (!this.checking() && trustedVerifiedActor(this.client, intent.accountId) !== null) {
        const canonical = await this.profileQuery.refetch();
        if (
          this.current(intent.accountId) &&
          canonical.isSuccess &&
          canonical.data.profile !== null &&
          canonical.data.profile.version >= result.version
        )
          this.resetDraft(canonical.data.profile, canonical.data.profile.version);
      } else
        await this.client.invalidateQueries({
          queryKey: ['account', intent.accountId, 'profile'],
          refetchType: 'none',
        });
    },
    onError: (error: unknown, intent: Readonly<Intent>) => {
      if (!this.current(intent.accountId)) return;
      if (error instanceof ApiFailure && (error.status === 401 || error.status === 403)) {
        this.resetDraft(null);
        this.photoOpen.set(false);
        this.client.removeQueries({ queryKey: ['account'] });
        this.expired.emit();
      }
    },
  });
  protected get profile() {
    return this.profileQuery.getCurrentResult();
  }
  protected get saving() {
    return this.saveMutation.getCurrentResult();
  }
  protected get cachedRefreshFailed(): boolean {
    return this.profile.data !== undefined && isUncertain(this.profile.error);
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
  protected get remoteChanged(): boolean {
    const source = this.sourceVersion();
    const query = this.profile;
    return (
      source !== null &&
      query.isSuccess &&
      !query.isFetching &&
      source !== (query.data.profile?.version ?? 0)
    );
  }
  public get hasUnsavedChanges(): boolean {
    return this.form.dirty || this.photoWorkflow()?.hasLocalDraft === true;
  }
  public async confirmLeave(): Promise<boolean> {
    const owner = this.actor().account_id;
    const accepted = await confirmDraftExit(this.dialogs, this.destroy, {
      dirty: this.hasUnsavedChanges,
      unconfirmed:
        this.saving.isPending ||
        this.uncertain ||
        this.photoWorkflow()?.hasUnconfirmedAction === true,
    });
    return accepted && this.current(owner);
  }
  protected get message(): string | null {
    const error = this.saving.error;
    if (this.remoteChanged)
      return 'Your profile changed elsewhere. Your draft is still here. Reload the saved profile before editing again.';
    if (error === null) return null;
    if (error instanceof CancelledError)
      return 'Your save paused during a sign-in check. Retry the same save once sign-in is confirmed.';
    if (this.uncertain)
      return 'We couldn’t confirm your save. Retry the same save or reload the saved profile.';
    if (error instanceof ApiFailure && error.code === 'profile_version_conflict')
      return 'Your profile changed elsewhere. Your draft is still here. Reload the saved profile before editing again.';
    if (this.conflict)
      return 'We couldn’t resolve this save. Reload the saved profile before trying again.';
    return 'We couldn’t save your profile. Check your details and try again.';
  }
  public constructor() {
    this.languages.addValidators((control: Readonly<AbstractControl<readonly string[]>>) => {
      const reference = this.reference.data;
      if (!this.detailsOpen() || reference === undefined) return null;
      return validateProfileLanguages(control.value, reference);
    });
    const stopReference = this.referenceQuery.subscribe(
      (result: Readonly<QueryObserverResult<Api['schemas']['ProfileReferenceResponse']>>) => {
        if (
          result.error instanceof ApiFailure &&
          (result.error.status === 401 || result.error.status === 403)
        ) {
          this.resetDraft(null);
          this.photoOpen.set(false);
          this.expired.emit();
        }
        this.languages.updateValueAndValidity({ emitEvent: false });
        this.change.markForCheck();
      },
    );
    const stopProfile = this.profileQuery.subscribe(
      (result: Readonly<QueryObserverResult<Api['schemas']['OwnProfileResponse']>>) => {
        if (result.isSuccess && !result.isFetching && this.sourceVersion() === null) {
          this.resetDraft(result.data.profile, result.data.profile?.version ?? 0);
        }
        if (
          result.error instanceof ApiFailure &&
          (result.error.status === 401 || result.error.status === 403)
        ) {
          this.resetDraft(null);
          this.photoOpen.set(false);
          this.expired.emit();
        }
        this.change.markForCheck();
      },
    );
    const stopSave = this.saveMutation.subscribe(() => {
      this.change.markForCheck();
    });
    this.destroy.onDestroy(() => {
      this.lifetime.abort();
      this.resetDraft(null);
      stopReference();
      this.referenceQuery.destroy();
      stopProfile();
      stopSave();
      this.profileQuery.destroy();
    });
  }
  public ngOnChanges(): void {
    if (
      this.draftOwner() !== this.actor().account_id ||
      this.actor().account_status !== 'active' ||
      this.actor().membership_status !== 'verified'
    ) {
      this.resetDraft(null);
      this.saveMutation.reset();
      this.details.set(this.editOptional());
      this.draftOwner.set(this.actor().account_id);
    }
    this.referenceQuery.setOptions(
      referenceOptions(
        this.http,
        this.actor().account_id,
        this.detailsOpen() &&
          !this.checking() &&
          trustedVerifiedActor(this.client, this.actor().account_id) !== null,
      ),
    );
    this.profileQuery.setOptions(
      profileOptions(
        this.http,
        this.actor().account_id,
        !this.checking() && trustedVerifiedActor(this.client, this.actor().account_id) !== null,
      ),
    );
  }
  protected get adviceSource(): Api['schemas']['ResourceSourceRequest'] | null {
    const photo = this.profile.data?.photo;
    return photo === null || photo === undefined
      ? null
      : { kind: 'resource', id: photo.upload_id, version: photo.version };
  }
  protected chooseAnotherPhoto(): void {
    if (!this.checking() && trustedVerifiedActor(this.client, this.actor().account_id) !== null)
      this.photoOpen.set(true);
  }
  protected photoAdviceExpired(event: AssistanceExpired): void {
    if (
      !this.current(event.actorId) ||
      (event.failure.status !== 401 && event.failure.status !== 403)
    )
      return;
    this.resetDraft(null);
    this.photoOpen.set(false);
    this.client.removeQueries({ queryKey: ['account', event.actorId] });
    this.expired.emit();
  }
  private current(accountId: string): boolean {
    const actor = this.client.getQueryData<Identity | null>(['session']);
    return (
      !this.lifetime.signal.aborted &&
      this.actor().account_id === accountId &&
      actor?.account_id === accountId
    );
  }
  protected get draftPresent(): boolean {
    return (
      this.form.dirty ||
      this.name.value.length > 0 ||
      this.about.value.length > 0 ||
      this.programme.value.length > 0 ||
      this.year.value.length > 0 ||
      this.languages.value.length > 0 ||
      this.photoOpen() ||
      this.photoAdvice()?.hasRequest === true
    );
  }
  private resetDraft(
    revision: Api['schemas']['ProfileRevisionResponse'] | null,
    version: number | null = revision?.version ?? null,
  ): void {
    this.sourceVersion.set(version);
    this.form.reset({
      name: revision?.display_name ?? '',
      about: revision?.about ?? '',
      programme: revision?.programme ?? '',
      year: revision?.year_label ?? '',
      languages: revision?.languages ?? [],
    });
  }
  protected editDetails(): void {
    if (this.locked || !this.actor().capabilities.can_use_student_features) return;
    this.details.set(true);
    this.referenceQuery.setOptions(
      referenceOptions(
        this.http,
        this.actor().account_id,
        !this.checking() && trustedVerifiedActor(this.client, this.actor().account_id) !== null,
      ),
    );
  }
  protected async cancelDetails(): Promise<void> {
    if (this.locked || !this.profile.isSuccess || this.profile.isFetching) return;
    const owner = this.actor().account_id;
    const accepted = await confirmDraftExit(this.dialogs, this.destroy, {
      dirty: this.form.dirty,
      unconfirmed: false,
    });
    if (!accepted || !this.current(owner)) return;
    const saved = this.profileQuery.getCurrentResult().data;
    if (saved === undefined) return;
    this.details.set(false);
    this.resetDraft(saved.profile, saved.profile?.version ?? 0);
    this.referenceQuery.setOptions(referenceOptions(this.http, this.actor().account_id, false));
  }
  protected async retryReference(): Promise<void> {
    if (this.checking() || trustedVerifiedActor(this.client, this.actor().account_id) === null)
      return;
    await this.referenceQuery.refetch();
  }
  protected summaryFailure(
    event: Readonly<{ readonly actorId: string; readonly error: ApiFailure }>,
  ): void {
    if (!this.current(event.actorId) || (event.error.status !== 401 && event.error.status !== 403))
      return;
    this.resetDraft(null);
    this.client.setQueryData(['session'], null);
    this.client.removeQueries({ queryKey: ['account', event.actorId] });
    this.client.getMutationCache().clear();
    this.expired.emit();
  }
  protected async refreshProfile(): Promise<void> {
    if (this.checking() || trustedVerifiedActor(this.client, this.actor().account_id) === null)
      return;
    const accountId = this.actor().account_id;
    await this.profileQuery.refetch();
    if (!this.checking() && trustedVerifiedActor(this.client, accountId) !== null) {
      await this.client.invalidateQueries({ queryKey: ['account', accountId, 'photo-review'] });
    }
  }
  protected async reload(): Promise<void> {
    if (
      this.saving.isPending ||
      this.checking() ||
      trustedVerifiedActor(this.client, this.actor().account_id) === null
    )
      return;
    this.details.set(false);
    this.sourceVersion.set(null);
    this.form.markAsPristine();
    this.saveMutation.reset();
    await this.profileQuery.refetch();
  }
  protected async save(): Promise<void> {
    this.form.markAllAsTouched();
    const current = this.profile.data;
    if (
      this.checking() ||
      trustedVerifiedActor(this.client, this.actor().account_id) === null ||
      this.actor().account_status !== 'active' ||
      this.actor().membership_status !== 'verified' ||
      this.form.invalid ||
      this.saving.isPending ||
      this.conflict ||
      this.profile.isFetching ||
      (this.detailsOpen() && !this.reference.isSuccess) ||
      current === undefined ||
      this.sourceVersion() === null
    )
      return;
    const previous = this.saving.variables;
    const body: Api['schemas']['SaveProfileRequest'] = {
      about: optionalText(this.about.value),
      programme: optionalText(this.programme.value),
      year_label: optionalText(this.year.value),
      languages: this.languages.value,
      task: current.profile?.task ?? 'find_help',
      display_name: this.name.value.trim(),
      expected_version: this.sourceVersion() ?? 0,
    };
    // Replays must keep the original immutable payload, not new server defaults/revisions.
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
