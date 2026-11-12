import { EmailDeliveryHint } from './email-delivery/email-delivery-hint';
import { StudySetup } from './setup/setup';
import { HelpSubjects } from './study/help';
import { StudyGoal } from './study/goal';
import { isUncertain } from '../uncertain';
import { ProfileBasics } from './profile/profile';
import { callbackNotice } from './callback';
import { TuiAppBar, TuiCardLarge } from '@taiga-ui/layout';
import { Brand } from '../brand';
import { Mascot } from '../mascot';
import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectorRef,
  Component,
  DestroyRef,
  afterNextRender,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Capacitor } from '@capacitor/core';
import { TuiButton, TuiLink, TuiLoader, TuiInput } from '@taiga-ui/core';
import { TuiAvatar, TuiBadge, TuiInputPin } from '@taiga-ui/kit';
import {
  CancelledError,
  MutationObserver,
  QueryClient,
  QueryObserver,
} from '@tanstack/angular-query-experimental';
import type { QueryObserverResult } from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { ApiFailure, writeJson } from '../../api-http';
import { sessionOptions } from '../session';
import { challengeOptions, isCreated, isVerified } from './challenge';

type Identity = Api['schemas']['IdentityResponse'];
interface SendIntent {
  readonly accountId: string;
  readonly input: Api['schemas']['StartEmailRequest'];
  readonly key: string;
}
interface VerifyIntent {
  readonly accountId: string;
  readonly challengeId: string;
  readonly input: Api['schemas']['VerifyEmailRequest'];
  readonly key: string;
}

@Component({
  selector: 'app-onboarding',
  imports: [
    EmailDeliveryHint,
    Brand,
    Mascot,
    ProfileBasics,
    StudyGoal,
    HelpSubjects,
    StudySetup,
    TuiCardLarge,
    TuiAppBar,
    TuiAvatar,
    TuiBadge,
    TuiInputPin,
    DatePipe,
    RouterLink,
    ReactiveFormsModule,
    TuiButton,
    TuiLink,
    TuiLoader,
    TuiInput,
  ],
  templateUrl: './onboarding.html',
  styleUrl: './onboarding.less',
})
export class Onboarding {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  protected readonly loginNotice = callbackNotice(
    this.route.snapshot.queryParamMap.get('auth_error'),
    this.route.snapshot.queryParamMap.get('auth_ref'),
  );
  private readonly profileEditor = viewChild(ProfileBasics);
  private readonly goalEditor = viewChild(StudyGoal);
  private readonly helpEditor = viewChild(HelpSubjects);
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly lifetime = new AbortController();
  private readonly editingEmail = signal(false);
  protected readonly setupView = signal<'entry' | 'profile' | 'goal' | 'help' | 'complete'>(
    'entry',
  );
  protected readonly setupHeading = computed(() => {
    switch (this.setupView()) {
      case 'profile':
        return 'Create your profile';
      case 'goal':
        return 'Your study goal';
      case 'help':
        return 'Your help areas';
      case 'complete':
        return 'Review your setup';
      case 'entry':
        return 'Your APU email is confirmed';
    }
  });
  private readonly sessionQuery = new QueryObserver(
    this.client,
    sessionOptions(this.http, this.client),
  );
  private readonly challengeQuery = new QueryObserver(
    this.client,
    challengeOptions(this.http, null, null, false),
  );
  protected readonly native = Capacitor.isNativePlatform();
  protected readonly email = new FormControl('', {
    nonNullable: true,
    validators: [
      Validators.required.bind(Validators),
      Validators.maxLength(254),
      Validators.pattern(
        /^[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*@mail\.apu\.edu\.my$/i,
      ),
    ],
  });
  protected readonly code = new FormControl('', {
    nonNullable: true,
    validators: [Validators.pattern(/^[0-9]{6}$/), Validators.required.bind(Validators)],
  });
  protected readonly emailForm = new FormGroup({ email: this.email });
  protected readonly codeForm = new FormGroup({ code: this.code });
  private readonly sendMutation = new MutationObserver(this.client, {
    retry: false,
    mutationFn: (intent: Readonly<SendIntent>) =>
      writeJson(
        this.http,
        '/api/v1/auth/email-challenges',
        intent.input,
        this.headers(intent.key),
        isCreated,
      ),
    onSuccess: (_data: unknown, intent: Readonly<SendIntent>) => {
      if (!this.currentIntent(intent.accountId)) return;
      this.editingEmail.set(false);
      this.code.reset('');
    },
    onSettled: async (_data: unknown, _error: unknown, intent: Readonly<SendIntent>) => {
      if (this.currentIntent(intent.accountId)) await this.sessionQuery.refetch();
    },
  });
  private readonly verifyMutation = new MutationObserver(this.client, {
    retry: false,
    mutationFn: (intent: Readonly<VerifyIntent>) =>
      writeJson(
        this.http,
        `/api/v1/auth/email-challenges/${encodeURIComponent(intent.challengeId)}/verify`,
        intent.input,
        this.headers(intent.key),
        isVerified,
      ),
    onSettled: async (_data: unknown, _error: unknown, intent: Readonly<VerifyIntent>) => {
      if (this.currentIntent(intent.accountId)) await this.sessionQuery.refetch();
    },
  });
  private readonly logoutMutation = new MutationObserver(this.client, {
    retry: false,
    onMutate: async () => {
      this.setupView.set('entry');
      this.email.reset('');
      this.code.reset('');
      this.editingEmail.set(false);
      await this.client.cancelQueries({ queryKey: ['account'] });
      this.client.removeQueries({ queryKey: ['account'] });
    },
    mutationFn: () =>
      writeJson(
        this.http,
        '/api/v1/auth/logout',
        null,
        this.headers(),
        (value: unknown): value is null => value === null,
      ),
    onSuccess: async () => {
      await this.client.cancelQueries();
      this.email.reset('');
      this.code.reset('');
      this.editingEmail.set(false);
      this.client.setQueryData(['session'], null);
      this.client.removeQueries({ queryKey: ['account'] });
      this.client.getMutationCache().clear();
      this.sendMutation.reset();
      this.verifyMutation.reset();
      await this.sessionQuery.refetch();
    },
  });
  protected get retainingEditor(): boolean {
    const actor = this.session.data;
    return (
      (this.setupView() === 'goal' ||
        this.setupView() === 'profile' ||
        this.setupView() === 'help') &&
      actor?.account_status === 'active' &&
      actor.membership_status === 'verified'
    );
  }
  protected get session() {
    return this.sessionQuery.getCurrentResult();
  }
  protected get challenge() {
    return this.challengeQuery.getCurrentResult();
  }
  protected get sending() {
    return this.sendMutation.getCurrentResult();
  }
  protected get verifying() {
    return this.verifyMutation.getCurrentResult();
  }
  protected get signingOut() {
    return this.logoutMutation.getCurrentResult();
  }
  protected get showEmail(): boolean {
    return this.editingEmail() || this.session.data?.email_challenge_id === null;
  }
  protected get operationError(): string | null {
    const error = this.signingOut.error ?? this.sending.error ?? this.verifying.error;
    if (error === null) return null;
    if (isUncertain(error))
      return 'We couldn’t confirm the result. Check status before trying again.';
    if (error instanceof ApiFailure && error.status === 429)
      return 'Too many attempts. Check status for when you can try again.';
    if (error instanceof ApiFailure && error.status === 401)
      return 'Your session ended. Sign in again to continue.';
    return 'We couldn’t complete that action. Check status or try again.';
  }
  protected get reference(): string | null {
    const error =
      this.signingOut.error ??
      this.verifying.error ??
      this.sending.error ??
      this.session.error ??
      this.challenge.error;
    return error instanceof ApiFailure ? error.requestId : null;
  }
  protected get retryAt(): string | null {
    const error = this.sending.error ?? this.verifying.error;
    return error instanceof ApiFailure ? error.retryAt : null;
  }
  public constructor() {
    if (
      this.route.snapshot.queryParamMap.has('auth_error') ||
      this.route.snapshot.queryParamMap.has('auth_ref')
    ) {
      afterNextRender(() => {
        void this.router.navigate([], {
          relativeTo: this.route,
          queryParams: { auth_error: null, auth_ref: null },
          queryParamsHandling: 'merge',
          replaceUrl: true,
        });
      });
    }
    const update = () => {
      this.change.markForCheck();
    };
    const challengeSubscription = this.challengeQuery.subscribe(update);
    const sessionSubscription = this.sessionQuery.subscribe(
      (result: Readonly<QueryObserverResult<Identity | null>>) => {
        const accountId = result.data?.account_id ?? null;
        if (this.challengeQuery.options.queryKey[1] !== accountId) {
          this.email.reset('');
          this.code.reset('');
          this.editingEmail.set(false);
          this.setupView.set('entry');
          this.sendMutation.reset();
          this.verifyMutation.reset();
          this.client.getMutationCache().clear();
        }
        this.challengeQuery.setOptions(
          challengeOptions(
            this.http,
            result.data?.account_id ?? null,
            result.data?.email_challenge_id ?? null,
            !result.isFetching && result.data?.capabilities.can_verify_student_email === true,
          ),
        );
        update();
      },
    );
    const sendSubscription = this.sendMutation.subscribe(update);
    const verifySubscription = this.verifyMutation.subscribe(update);
    const logoutSubscription = this.logoutMutation.subscribe(update);
    this.destroy.onDestroy(() => {
      this.lifetime.abort();
      sessionSubscription();
      challengeSubscription();
      sendSubscription();
      verifySubscription();
      logoutSubscription();
      this.sessionQuery.destroy();
      this.challengeQuery.destroy();
    });
    this.code.valueChanges.pipe(takeUntilDestroyed()).subscribe(() => {
      if (
        this.code.valid &&
        !this.sending.isPending &&
        !this.verifying.isPending &&
        this.challenge.data?.can_verify === true
      )
        this.confirmCode();
    });
  }
  private identity(): Identity {
    const actor = this.session.data;
    if (actor === null || actor === undefined) throw new ApiFailure(401, 'unauthenticated', null);
    return actor;
  }
  private headers(key?: string): Readonly<Record<string, string>> {
    const csrf = this.identity().csrf_token;
    return key === undefined
      ? { 'x-csrf-token': csrf }
      : { 'x-csrf-token': csrf, 'idempotency-key': key };
  }
  private currentIntent(accountId: string): boolean {
    return !this.lifetime.signal.aborted && this.session.data?.account_id === accountId;
  }
  private handled(error: unknown, accountId?: string): void {
    if (!(error instanceof ApiFailure) && !(error instanceof CancelledError)) throw error;
    if (accountId !== undefined && !this.currentIntent(accountId)) return;
    if (error instanceof ApiFailure && error.status === 401) {
      this.client.setQueryData(['session'], null);
      this.client.removeQueries({ queryKey: ['account'] });
      this.email.reset('');
      this.code.reset('');
      return;
    }
  }
  protected sendCode(resend = false): void {
    this.email.markAsTouched();
    const existing = this.challenge.data;
    if (
      this.session.data?.capabilities.can_verify_student_email !== true ||
      this.sending.isPending ||
      (!resend && this.email.invalid) ||
      (resend && existing?.can_resend !== true)
    )
      return;
    const previous = this.sending.variables;
    const input: Api['schemas']['StartEmailRequest'] =
      resend && existing !== undefined
        ? { email: existing.email, resend_of: existing.id }
        : { email: this.email.value };
    const same =
      previous?.input.email === input.email &&
      previous.input.resend_of === input.resend_of &&
      isUncertain(this.sending.error);
    const intent: SendIntent = {
      accountId: this.identity().account_id,
      input,
      key: same ? previous.key : crypto.randomUUID(),
    };
    void this.sendMutation.mutate(intent).catch((error: unknown) => {
      this.handled(error, intent.accountId);
    });
  }
  protected confirmCode(): void {
    this.code.markAsTouched();
    const current = this.challenge.data;
    if (
      this.code.invalid ||
      this.sending.isPending ||
      this.verifying.isPending ||
      current?.can_verify !== true
    )
      return;
    const previous = this.verifying.variables;
    const intent: VerifyIntent =
      previous?.input.code === this.code.value && isUncertain(this.verifying.error)
        ? previous
        : {
            accountId: this.identity().account_id,
            challengeId: current.id,
            input: { code: this.code.value },
            key: crypto.randomUUID(),
          };
    void this.verifyMutation.mutate(intent).catch((error: unknown) => {
      this.handled(error, intent.accountId);
    });
  }
  protected setupExpired(): void {
    this.setupView.set('entry');
    this.checkStatus();
  }
  protected checkStatus(): void {
    void this.sessionQuery.refetch();
  }
  protected changeEmail(): void {
    this.email.setValue(this.challenge.data?.email ?? '');
    this.code.reset('');
    this.editingEmail.set(true);
    this.verifyMutation.reset();
  }
  public async canLeave(): Promise<boolean> {
    if (this.signingOut.isPending || this.destroy.destroyed || this.session.data === null)
      return true;
    const editor = this.profileEditor() ?? this.goalEditor() ?? this.helpEditor();
    return editor === undefined ? true : await editor.confirmLeave();
  }
  protected async leaveEditor(next: 'entry' | 'complete' = 'entry'): Promise<void> {
    const actorId = this.session.data?.account_id;
    if (actorId === undefined || !(await this.canLeave())) return;
    const current = this.session.data;
    if (
      !this.destroy.destroyed &&
      !this.session.isFetching &&
      !this.session.isError &&
      current?.account_id === actorId &&
      current.account_status === 'active' &&
      current.membership_status === 'verified'
    )
      this.setupView.set(next);
  }
  protected signOut(): void {
    if (!this.signingOut.isPending)
      void this.logoutMutation.mutate().catch((error: unknown) => {
        this.handled(error);
      });
  }
}
