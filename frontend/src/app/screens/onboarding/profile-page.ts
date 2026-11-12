import { SettingsHeader } from '../settings-header';
import type { Api } from '../../api.generated';
import { StudentLayout } from '../student-layout';
import { CompleteGoal } from './profile/complete-goal';
import { BlockedPeople } from './profile/blocked-people';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectorRef, Component, DestroyRef, inject, viewChild } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TuiButton, TuiLink, TuiCell, TuiIcon, TuiTitle } from '@taiga-ui/core';
import { TuiAvatar, TuiStatus } from '@taiga-ui/kit';
import { TuiCardLarge } from '@taiga-ui/layout';
import {
  CancelledError,
  MutationObserver,
  QueryClient,
  QueryObserver,
  queryOptions,
} from '@tanstack/angular-query-experimental';
import type { QueryFunctionContext } from '@tanstack/angular-query-experimental';
import { ApiFailure, readJson, writeJson } from '../../api-http';
import { sessionOptions } from '../session';
import { trustedVerifiedActor } from '../verified-actor';
import { ProfileBasics } from './profile/profile';
import { isProfile } from './profile/profile-contract';
import { OwnFeedbackSummary } from './profile/feedback-summary';
import { StudyGoal } from './study/goal';
import { isOwnGoal, isOwnHelp } from '../study-context-contract';
import { HelpSubjects } from './study/help';
import { ProfileVisibility } from './setup/visibility';
import { isSetupStatus } from './setup/setup-contract';

@Component({
  selector: 'peerly-profile-page',
  imports: [
    StudentLayout,
    TuiAvatar,
    TuiStatus,
    TuiCell,
    SettingsHeader,
    TuiIcon,
    TuiTitle,
    TuiCardLarge,
    CompleteGoal,
    BlockedPeople,
    RouterLink,
    TuiButton,
    TuiLink,
    ProfileBasics,
    StudyGoal,
    HelpSubjects,
    OwnFeedbackSummary,
    ProfileVisibility,
  ],
  templateUrl: './profile-page.html',
  styleUrl: './profile-page.less',
})
export class ProfilePage {
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  protected readonly mode: unknown = inject(ActivatedRoute).snapshot.data['editor'];
  protected get heading(): string {
    switch (this.mode) {
      case 'profile':
        return 'Edit profile';
      case 'goal':
        return 'Edit study goal';
      case 'help':
        return 'Edit help areas';
      case 'blocks':
        return 'Blocked people';
      case 'visibility':
        return 'Profile visibility';
      default:
        return 'Profile';
    }
  }
  protected get editing(): boolean {
    return (
      this.mode === 'profile' ||
      this.mode === 'goal' ||
      this.mode === 'help' ||
      this.mode === 'blocks' ||
      this.mode === 'visibility'
    );
  }

  private readonly profileEditor = viewChild(ProfileBasics);
  private readonly goalEditor = viewChild(StudyGoal);
  private readonly helpEditor = viewChild(HelpSubjects);
  private readonly sessionQuery = new QueryObserver(
    this.client,
    sessionOptions(this.http, this.client),
  );
  private readonly profileQuery = new QueryObserver(this.client, this.profileOptions(null, false));
  private readonly goalQuery = new QueryObserver(this.client, this.goalOptions(null, false));
  private readonly helpQuery = new QueryObserver(this.client, this.helpOptions(null, false));
  private readonly statusQuery = new QueryObserver(this.client, this.statusOptions(null, false));
  private readonly logoutMutation = new MutationObserver(this.client, {
    retry: false,
    mutationFn: (actorId: string) => {
      const actor = trustedVerifiedActor(this.client, actorId);
      if (actor === null || this.destroy.destroyed) throw new CancelledError();
      return writeJson(
        this.http,
        '/api/v1/auth/logout',
        null,
        { 'x-csrf-token': actor.csrf_token },
        (value: unknown): value is null => value === null,
      );
    },
    onMutate: async () => {
      await this.client.cancelQueries({ queryKey: ['account'] });
      this.client.removeQueries({ queryKey: ['account'] });
    },
    onError: async (_error: unknown, actorId: string) => {
      if (
        !this.destroy.destroyed &&
        this.client.getQueryData<Api['schemas']['IdentityResponse'] | null>(['session'])
          ?.account_id === actorId
      )
        await this.sessionQuery.refetch();
    },
    onSuccess: (_receipt, actorId: string) => {
      if (
        this.client.getQueryData<Api['schemas']['IdentityResponse'] | null>(['session'])
          ?.account_id !== actorId
      )
        return;
      this.client.setQueryData(['session'], null);
      this.client.removeQueries({ queryKey: ['account'] });
      this.client.getMutationCache().clear();
    },
  });
  protected get signingOut() {
    return this.logoutMutation.getCurrentResult();
  }
  protected get session() {
    return this.sessionQuery.getCurrentResult();
  }
  protected get profile() {
    return this.profileQuery.getCurrentResult();
  }
  protected get goal() {
    return this.goalQuery.getCurrentResult();
  }
  protected get help() {
    return this.helpQuery.getCurrentResult();
  }
  protected get status() {
    return this.statusQuery.getCurrentResult();
  }
  protected get discoverSummary(): Readonly<{
    readonly label: string;
    readonly color: string;
  }> | null {
    const status = this.status;
    if (!status.isSuccess || status.isFetching || status.data.visibility === null) return null;
    if (status.data.visibility.hidden)
      return { label: 'Hidden in Discover', color: 'var(--tui-status-neutral)' };
    if (status.data.discovery_exposure?.paused === true)
      return { label: 'Paused in Discover', color: 'var(--tui-status-warning)' };
    return status.data.capabilities.can_discover
      ? { label: 'Visible in Discover', color: 'var(--tui-status-positive)' }
      : { label: 'Not appearing in Discover', color: 'var(--tui-status-neutral)' };
  }
  protected get checking(): boolean {
    return this.session.isFetching || this.session.isError;
  }
  public constructor() {
    const update = () => {
      const errors: readonly unknown[] = [
        this.profile.error,
        this.goal.error,
        this.help.error,
        this.status.error,
      ];
      if (
        !this.session.isFetching &&
        errors.some(
          (error) => error instanceof ApiFailure && (error.status === 401 || error.status === 403),
        )
      )
        void this.sessionQuery.refetch();
      this.change.markForCheck();
    };
    const stops = [
      this.logoutMutation.subscribe(() => {
        this.change.markForCheck();
      }),
      this.profileQuery.subscribe(update),
      this.goalQuery.subscribe(update),
      this.helpQuery.subscribe(update),
      this.statusQuery.subscribe(update),
    ];
    const stopSession = this.sessionQuery.subscribe(
      (result: Readonly<ReturnType<typeof this.sessionQuery.getCurrentResult>>) => {
        const id = result.data?.account_id ?? null;
        const allowed = id !== null && trustedVerifiedActor(this.client, id) !== null;
        const overview = allowed && this.mode === undefined;
        this.profileQuery.setOptions(this.profileOptions(id, overview));
        this.goalQuery.setOptions(this.goalOptions(id, overview));
        this.helpQuery.setOptions(this.helpOptions(id, overview));
        this.statusQuery.setOptions(
          this.statusOptions(
            id,
            allowed && (this.mode === undefined || this.mode === 'visibility'),
          ),
        );
        update();
      },
    );
    this.destroy.onDestroy(() => {
      stopSession();
      for (const stop of stops) stop();
      this.logoutMutation.reset();
      this.sessionQuery.destroy();
      this.profileQuery.destroy();
      this.goalQuery.destroy();
      this.helpQuery.destroy();
      this.statusQuery.destroy();
    });
  }
  private profileOptions(id: string | null, enabled: boolean) {
    return queryOptions({
      queryKey:
        id === null
          ? (['profile-page-idle', 'profile'] as const)
          : (['account', id, 'profile'] as const),
      enabled,
      retry: false,
      staleTime: 0,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
        readJson(this.http, '/api/v1/me/profile', signal, isProfile),
    });
  }
  private goalOptions(id: string | null, enabled: boolean) {
    return queryOptions({
      queryKey:
        id === null ? (['profile-page-idle', 'goal'] as const) : (['account', id, 'goal'] as const),
      enabled,
      retry: false,
      staleTime: 0,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
        readJson(this.http, '/api/v1/me/goal', signal, isOwnGoal),
    });
  }
  private helpOptions(id: string | null, enabled: boolean) {
    return queryOptions({
      queryKey:
        id === null
          ? (['profile-page-idle', 'help-subjects'] as const)
          : (['account', id, 'help-subjects'] as const),
      enabled,
      retry: false,
      staleTime: 0,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
        readJson(this.http, '/api/v1/me/help-subjects', signal, isOwnHelp),
    });
  }
  private statusOptions(id: string | null, enabled: boolean) {
    return queryOptions({
      queryKey:
        id === null
          ? (['profile-page-idle', 'onboarding'] as const)
          : (['account', id, 'onboarding'] as const),
      enabled,
      retry: false,
      staleTime: 0,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
        readJson(this.http, '/api/v1/me/onboarding', signal, isSetupStatus),
    });
  }
  public async canLeave(): Promise<boolean> {
    return await (this.profileEditor()?.confirmLeave() ??
      this.goalEditor()?.confirmLeave() ??
      this.helpEditor()?.confirmLeave() ??
      Promise.resolve(true));
  }
  protected async signOut(): Promise<void> {
    const id = this.session.data?.account_id;
    if (id === undefined || this.checking || this.signingOut.isPending) return;
    try {
      await this.logoutMutation.mutate(id);
    } catch (error: unknown) {
      if (!(error instanceof ApiFailure) && !(error instanceof CancelledError)) throw error;
    }
  }
  protected checkSession(): void {
    void this.sessionQuery.refetch();
  }
  protected retryVisibility(): void {
    const id = this.session.data?.account_id;
    if (id !== undefined && trustedVerifiedActor(this.client, id) !== null)
      void this.statusQuery.refetch();
  }
  protected retryOverview(): void {
    const id = this.session.data?.account_id;
    if (id === undefined || trustedVerifiedActor(this.client, id) === null) return;
    void this.profileQuery.refetch();
    void this.goalQuery.refetch();
    void this.helpQuery.refetch();
    void this.statusQuery.refetch();
  }
}
