import { TuiForm } from '@taiga-ui/layout';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectorRef, Component, DestroyRef, inject, input, output } from '@angular/core';
import type { OnChanges, SimpleChanges } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { TuiButton, TuiLink, TuiLoader, TuiRadio } from '@taiga-ui/core';
import {
  CancelledError,
  MutationObserver,
  QueryClient,
  QueryObserver,
  queryOptions,
} from '@tanstack/angular-query-experimental';
import type {
  Mutation,
  QueryFunctionContext,
  QueryObserverResult,
} from '@tanstack/angular-query-experimental';
import type { Api } from '../../../api.generated';
import { ApiFailure, readJson, writeJson } from '../../../api-http';
import { isUncertain } from '../../uncertain';
import { isProfile, isRevision } from '../profile/profile-contract';
import { isRegistrationContext, isRegistrationReceipt, isSetupStatus } from './setup-contract';
import { ProfileVisibility } from './visibility';

type Identity = Api['schemas']['IdentityResponse'];
type Status = Api['schemas']['OnboardingStatusResponse'];
type OwnProfile = Api['schemas']['OwnProfileResponse'];
interface Intent {
  readonly actor: Identity;
  readonly key: string;
}
interface TaskIntent extends Intent {
  readonly body: Api['schemas']['SaveProfileRequest'];
}
interface RegistrationIntent extends Intent {
  readonly body: Api['schemas']['CompleteRegistrationRequest'];
  readonly task: Api['schemas']['OnboardingTask'];
}
function statusOptions(http: Readonly<HttpClient>, accountId: string | null, enabled: boolean) {
  return queryOptions({
    queryKey: ['account', accountId, 'onboarding'] as const,
    enabled,
    staleTime: Infinity,
    retry: false,
    refetchOnMount: 'always',
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(http, '/api/v1/me/onboarding', signal, isSetupStatus),
  });
}
function profileOptions(http: Readonly<HttpClient>, accountId: string | null, enabled: boolean) {
  return queryOptions({
    queryKey: ['account', accountId, 'profile'] as const,
    enabled,
    staleTime: Infinity,
    retry: false,
    refetchOnMount: 'always',
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(http, '/api/v1/me/profile', signal, isProfile),
  });
}
@Component({
  selector: 'peerly-study-setup',
  imports: [
    TuiForm,
    ReactiveFormsModule,
    RouterLink,
    TuiButton,
    TuiLink,
    TuiLoader,
    TuiRadio,
    ProfileVisibility,
  ],
  templateUrl: './setup.html',
  styleUrl: './setup.less',
})
export class StudySetup implements OnChanges {
  public readonly actor = input.required<Identity>();
  public readonly expired = output();
  public readonly edit = output<'profile' | 'goal' | 'help'>();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly router = inject(Router);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly lifetime = new AbortController();
  private readonly scope: object = {};
  protected readonly task = new FormControl<Api['schemas']['OnboardingTask']>('find_help', {
    nonNullable: true,
  });
  protected readonly taskForm = new FormGroup({ task: this.task });
  protected readonly requirements: Readonly<
    Record<Api['schemas']['OnboardingRequirement'], string>
  > = {
    display_name: 'Save your display name.',
    photo: 'Add a photo and wait for it to be ready.',
    study_goal: 'Save your study goal.',
    help_subjects: 'Choose a knowledge area you can help with.',
  };
  private readonly statusQuery = new QueryObserver(
    this.client,
    statusOptions(this.http, null, false),
  );
  private readonly profileQuery = new QueryObserver(
    this.client,
    profileOptions(this.http, null, false),
  );
  private readonly contextMutation = new MutationObserver(this.client, {
    retry: false,
    meta: { scope: this.scope },
    mutationFn: (intent: Readonly<Intent>) => {
      this.requireCurrent(intent.actor);
      return writeJson(
        this.http,
        '/api/v1/me/registration-context',
        undefined,
        this.headers(intent),
        isRegistrationContext,
      );
    },
    onError: (error: unknown, intent: Readonly<Intent>) => {
      if (this.current(intent.actor)) this.denied(error);
    },
  });
  private readonly taskMutation = new MutationObserver(this.client, {
    retry: false,
    meta: { scope: this.scope },
    mutationFn: (intent: Readonly<TaskIntent>) => {
      this.requireCurrent(intent.actor);
      return writeJson(
        this.http,
        '/api/v1/me/profile',
        intent.body,
        this.headers(intent),
        isRevision,
        'PUT',
      );
    },
    onSuccess: async (_value, intent: Readonly<TaskIntent>) => {
      if (!this.current(intent.actor)) return;
      this.taskForm.markAsPristine();
      await Promise.all([
        this.client.invalidateQueries({
          queryKey: ['account', intent.actor.account_id, 'profile'],
        }),
        this.client.invalidateQueries({
          queryKey: ['account', intent.actor.account_id, 'onboarding'],
        }),
      ]);
    },
    onError: (error: unknown, intent: Readonly<TaskIntent>) => {
      if (this.current(intent.actor)) this.denied(error);
    },
  });
  private readonly registrationMutation = new MutationObserver(this.client, {
    retry: false,
    meta: { scope: this.scope },
    mutationFn: (intent: Readonly<RegistrationIntent>) => {
      this.requireCurrent(intent.actor);
      return writeJson(
        this.http,
        '/api/v1/me/registration',
        intent.body,
        this.headers(intent),
        isRegistrationReceipt,
      );
    },
    onSuccess: async (_receipt, intent: Readonly<RegistrationIntent>) => {
      if (!this.current(intent.actor)) return;
      await this.client.invalidateQueries({
        queryKey: ['account', intent.actor.account_id, 'onboarding'],
        refetchType: 'none',
      });
      if (!this.current(intent.actor)) return;
      const navigated = await this.router.navigate(['/discover'], {
        queryParams: { mode: intent.task },
      });
      if (!navigated && this.current(intent.actor)) await this.statusQuery.refetch();
    },
    onError: async (error: unknown, intent: Readonly<RegistrationIntent>) => {
      if (!this.current(intent.actor)) return;
      this.denied(error);
      if (error instanceof ApiFailure && error.code === 'onboarding_incomplete')
        await this.statusQuery.refetch();
    },
  });
  protected get status() {
    return this.statusQuery.getCurrentResult();
  }
  protected get profile() {
    return this.profileQuery.getCurrentResult();
  }
  protected get preparing() {
    return this.contextMutation.getCurrentResult();
  }
  protected get savingTask() {
    return this.taskMutation.getCurrentResult();
  }
  protected get completing() {
    return this.registrationMutation.getCurrentResult();
  }
  protected get taskUncertain(): boolean {
    return isUncertain(this.savingTask.error);
  }
  protected get completionUncertain(): boolean {
    return isUncertain(this.completing.error);
  }
  protected get contextUnavailable(): boolean {
    return (
      this.completing.error instanceof ApiFailure &&
      this.completing.error.code === 'registration_context_unavailable'
    );
  }
  protected get busy(): boolean {
    return this.savingTask.isPending || this.completing.isPending;
  }
  protected get canFinish(): boolean {
    const status = this.status.data;
    return (
      status !== undefined &&
      !status.setup_complete &&
      (status.capabilities.can_complete_registration || status.capabilities.can_complete_setup) &&
      this.profile.data?.profile !== undefined &&
      this.profile.data.profile !== null &&
      !this.taskForm.dirty &&
      !this.taskUncertain &&
      !this.contextUnavailable &&
      !this.busy &&
      !this.profile.isFetching &&
      !this.profile.isError &&
      !this.status.isFetching &&
      !this.status.isError &&
      (status.registered ? this.actor().registration !== null : this.preparing.data !== undefined)
    );
  }
  public constructor() {
    const update = () => {
      this.change.markForCheck();
      this.prepareWhenReady();
    };
    const stopProfile = this.profileQuery.subscribe(
      (result: Readonly<QueryObserverResult<OwnProfile>>) => {
        if (result.isSuccess && !result.isFetching && this.taskForm.pristine)
          this.task.setValue(result.data.profile?.task ?? 'find_help', { emitEvent: false });
        this.denied(result.error);
        update();
      },
    );
    const stopStatus = this.statusQuery.subscribe(
      (result: Readonly<QueryObserverResult<Status>>) => {
        this.denied(result.error);
        update();
      },
    );
    const stopContext = this.contextMutation.subscribe(update);
    const stopTask = this.taskMutation.subscribe(update);
    const stopRegistration = this.registrationMutation.subscribe(update);
    this.destroy.onDestroy(() => {
      this.lifetime.abort();
      stopProfile();
      stopStatus();
      stopContext();
      stopTask();
      stopRegistration();
      this.profileQuery.destroy();
      this.statusQuery.destroy();
      this.reset();
    });
  }
  public ngOnChanges(changes: Readonly<SimpleChanges>): void {
    if (changes['actor'] === undefined) return;
    const actor = this.actor();
    const previous: unknown = changes['actor'].previousValue;
    const sameAccount =
      typeof previous === 'object' &&
      previous !== null &&
      'account_id' in previous &&
      previous.account_id === actor.account_id;
    if (!sameAccount) this.reset();
    const enabled = actor.account_status === 'active' && actor.membership_status === 'verified';
    this.profileQuery.setOptions(profileOptions(this.http, actor.account_id, enabled));
    this.statusQuery.setOptions(statusOptions(this.http, actor.account_id, enabled));
  }
  private reset(): void {
    this.taskForm.reset({ task: 'find_help' });
    this.contextMutation.reset();
    this.taskMutation.reset();
    this.registrationMutation.reset();
    for (const mutation of this.client
      .getMutationCache()
      .findAll({ predicate: (entry: Readonly<Mutation>) => entry.meta?.['scope'] === this.scope }))
      this.client.getMutationCache().remove(mutation);
  }
  private current(actor: Readonly<Identity>): boolean {
    return !this.lifetime.signal.aborted && this.actor() === actor;
  }
  private requireCurrent(actor: Readonly<Identity>): void {
    if (!this.current(actor)) throw new CancelledError();
  }
  private headers(intent: Readonly<Intent>): Readonly<Record<string, string>> {
    return { 'x-csrf-token': intent.actor.csrf_token, 'idempotency-key': intent.key };
  }
  private denied(error: unknown): void {
    if (error instanceof ApiFailure && (error.status === 401 || error.status === 403))
      this.expired.emit();
  }
  private async attempt(action: Promise<unknown>): Promise<void> {
    try {
      await action;
    } catch (error: unknown) {
      if (!(error instanceof ApiFailure) && !(error instanceof CancelledError)) throw error;
    }
  }
  protected async reload(): Promise<void> {
    await Promise.all([this.profileQuery.refetch(), this.statusQuery.refetch()]);
  }
  protected async reloadTask(): Promise<void> {
    if (this.busy) return;
    this.taskMutation.reset();
    this.taskForm.markAsPristine();
    await this.reload();
  }
  protected async saveTask(): Promise<void> {
    const current = this.profile.data;
    if (current === undefined || this.busy || this.profile.isFetching || this.profile.isError)
      return;
    const body: Api['schemas']['SaveProfileRequest'] = {
      expected_version: current.profile?.version ?? 0,
      display_name: current.profile?.display_name ?? null,
      about: current.profile?.about ?? null,
      programme: current.profile?.programme ?? null,
      year_label: current.profile?.year_label ?? null,
      languages: current.profile?.languages ?? [],
      task: this.task.value,
    };
    const previous = this.savingTask.variables;
    const intent =
      this.taskUncertain && previous !== undefined
        ? previous
        : { actor: this.actor(), key: crypto.randomUUID(), body };
    await this.attempt(this.taskMutation.mutate(intent));
  }
  private prepareWhenReady(): void {
    const status = this.status;
    if (
      this.lifetime.signal.aborted ||
      !status.isSuccess ||
      status.isFetching ||
      status.data.registered ||
      !status.data.capabilities.can_complete_registration ||
      !this.preparing.isIdle ||
      this.busy
    )
      return;
    if (this.statusQuery.options.queryKey[1] !== this.actor().account_id) return;
    void this.prepareContext().catch(reportError);
  }
  protected async prepareContext(): Promise<void> {
    if (this.preparing.isPending || this.busy) return;
    const previous = this.preparing.variables;
    const intent =
      isUncertain(this.preparing.error) && previous !== undefined
        ? previous
        : { actor: this.actor(), key: crypto.randomUUID() };
    await this.attempt(this.contextMutation.mutate(intent));
  }
  protected async refreshContext(): Promise<void> {
    if (this.busy || this.preparing.isPending) return;
    this.registrationMutation.reset();
    this.contextMutation.reset();
    await this.prepareContext();
  }
  protected async finish(): Promise<void> {
    const profile = this.profile.data?.profile;
    if (!this.canFinish || profile === undefined || profile === null) return;
    const status = this.status.data;
    const contextId =
      status?.registered === true ? this.actor().registration?.context_id : this.preparing.data?.id;
    if (contextId === undefined) return;
    const previous = this.completing.variables;
    const retry =
      this.completionUncertain ||
      (this.completing.error instanceof ApiFailure &&
        this.completing.error.code === 'onboarding_incomplete');
    const intent =
      retry && previous !== undefined
        ? previous
        : {
            actor: this.actor(),
            key: crypto.randomUUID(),
            body: { context_id: contextId },
            task: profile.task,
          };
    await this.attempt(this.registrationMutation.mutate(intent));
  }
}
