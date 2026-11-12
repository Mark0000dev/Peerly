import { HttpClient } from '@angular/common/http';
import { ChangeDetectorRef, Component, DestroyRef, inject, signal } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { TuiAppearance, TuiButton, TuiDialogService, TuiLink, TuiRadio } from '@taiga-ui/core';
import { TuiAppBar, TuiCardLarge } from '@taiga-ui/layout';
import {
  CancelledError,
  MutationObserver,
  QueryClient,
  QueryObserver,
} from '@tanstack/angular-query-experimental';
import type { Mutation } from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { ApiFailure, writeJson } from '../../api-http';
import { confirmDraftExit } from '../draft-exit';
import { trustedVerifiedActor } from '../verified-actor';
import { sessionOptions } from '../session';
import { isPreference } from './notification-contract';
import { preferenceOptions, preferenceUnknown, preferenceWrite } from './notification-query';

interface PreferenceIntent {
  readonly actorId: string;
  readonly key: string;
  readonly body: Api['schemas']['PreferenceBody'];
}
@Component({
  selector: 'app-notification-preferences',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TuiButton,
    TuiLink,
    TuiRadio,
    TuiAppBar,
    TuiCardLarge,
    TuiAppearance,
  ],
  templateUrl: './notification-preferences.html',
  styleUrl: './notifications.less',
})
export class NotificationPreferences {
  private readonly http = inject(HttpClient);
  private readonly dialogs = inject(TuiDialogService);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly lifetime = new AbortController();
  private readonly owner: object = {};
  private readonly retired = signal(false);
  private readonly actorId = signal<string | null>(null);
  private readonly intent = signal<PreferenceIntent | null>(null);
  private readonly session = new QueryObserver(this.client, sessionOptions(this.http, this.client));
  private readonly query = new QueryObserver(
    this.client,
    preferenceOptions(this.http, this.client, null),
  );
  private readonly mutation = new MutationObserver(this.client, {
    mutationKey: ['notification-preference-save'],
    meta: { preferenceOwner: this.owner },
    retry: false,
    mutationFn: (intent: PreferenceIntent) => {
      const actor = trustedVerifiedActor(this.client, intent.actorId);
      if (this.retired() || this.lifetime.signal.aborted || actor?.account_id !== intent.actorId)
        throw new CancelledError();
      return preferenceWrite(
        writeJson(
          this.http,
          '/api/v1/me/notification-preference',
          intent.body,
          { 'x-csrf-token': actor.csrf_token, 'idempotency-key': intent.key },
          isPreference,
          'PUT',
        ),
        this.lifetime.signal,
      );
    },
  });
  protected readonly mode = new FormControl<Api['schemas']['NotificationMode']>(
    'messages_and_requests',
    { nonNullable: true },
  );
  protected get result() {
    return this.query.getCurrentResult();
  }
  protected get saveResult() {
    return this.mutation.getCurrentResult();
  }
  protected get authorized(): boolean {
    const actorId = this.actorId();
    return (
      !this.retired() && actorId !== null && trustedVerifiedActor(this.client, actorId) !== null
    );
  }
  protected get locked(): boolean {
    return (
      !this.authorized || !this.result.isSuccess || this.result.isFetching || this.intent() !== null
    );
  }
  protected get uncertain(): boolean {
    return preferenceUnknown(this.saveResult.error);
  }
  protected get conflict(): boolean {
    return this.saveResult.error instanceof ApiFailure && this.saveResult.error.status === 409;
  }
  protected get reference(): string | null {
    return this.saveResult.error instanceof ApiFailure ? this.saveResult.error.requestId : null;
  }
  public constructor() {
    const unsubscribeSession = this.session.subscribe(
      (result: Readonly<ReturnType<typeof this.session.getCurrentResult>>) => {
        const prior = this.actorId();
        if (
          result.isSuccess &&
          !result.isFetching &&
          prior !== null &&
          (result.data?.account_id !== prior ||
            result.data.account_status !== 'active' ||
            result.data.membership_status !== 'verified')
        ) {
          this.retired.set(true);
          this.lifetime.abort();
          this.mode.reset();
          this.intent.set(null);
          this.mutation.reset();
          this.clearMutations();
        }
        const actor =
          result.data === undefined || result.data === null
            ? null
            : trustedVerifiedActor(this.client, result.data.account_id);
        if (!this.retired() && actor !== null && prior === null) this.actorId.set(actor.account_id);
        this.query.setOptions(
          preferenceOptions(this.http, this.client, this.authorized ? this.actorId() : null),
        );
        this.change.markForCheck();
      },
    );
    const unsubscribeQuery = this.query.subscribe(
      (result: Readonly<ReturnType<typeof this.query.getCurrentResult>>) => {
        if (result.isSuccess && !result.isFetching && !this.mode.dirty && this.intent() === null)
          this.mode.setValue(result.data.mode);
        this.change.markForCheck();
      },
    );
    const unsubscribeMutation = this.mutation.subscribe(() => {
      this.change.markForCheck();
    });
    this.destroy.onDestroy(() => {
      this.lifetime.abort();
      unsubscribeSession();
      unsubscribeQuery();
      unsubscribeMutation();
      this.session.destroy();
      this.query.destroy();
      this.mutation.reset();
      this.clearMutations();
      const actorId = this.actorId();
      if (actorId !== null)
        this.client.removeQueries({
          queryKey: ['account', actorId, 'notification-preference'],
          type: 'inactive',
        });
    });
  }
  private clearMutations(): void {
    for (const mutation of this.client.getMutationCache().findAll({
      predicate: (mutation: Readonly<Mutation>) =>
        mutation.options.meta?.['preferenceOwner'] === this.owner,
    }))
      this.client.getMutationCache().remove(mutation);
  }
  protected save(): void {
    const actorId = this.actorId();
    const current = this.result.data;
    if (this.locked || actorId === null || current === undefined) return;
    const intent: PreferenceIntent = {
      actorId,
      key: crypto.randomUUID(),
      body: { mode: this.mode.value, expected_version: current.version },
    };
    this.intent.set(intent);
    this.submit(intent);
  }
  protected replay(): void {
    const intent = this.intent();
    if (
      !this.authorized ||
      intent === null ||
      this.saveResult.isPending ||
      this.saveResult.isSuccess ||
      this.conflict
    )
      return;
    this.submit(intent);
  }
  private submit(intent: PreferenceIntent): void {
    void this.mutation
      .mutate(intent)
      .then(() => {
        if (this.lifetime.signal.aborted || !this.authorized) return;
        this.mode.markAsPristine();
        void this.query.refetch();
      })
      .catch((error: unknown) => {
        if (
          error instanceof ApiFailure &&
          (error.status === 401 || error.status === 403) &&
          !this.lifetime.signal.aborted
        )
          void this.session.refetch();
        if (!(error instanceof ApiFailure) && !(error instanceof CancelledError)) throw error;
      });
  }
  protected refresh(): void {
    if (this.authorized && !this.saveResult.isPending) void this.query.refetch();
  }
  protected useCurrent(): void {
    if (!this.authorized || this.result.isFetching || this.saveResult.isPending || this.uncertain)
      return;
    void this.query
      .refetch()
      .then((current: Readonly<ReturnType<typeof this.query.getCurrentResult>>) => {
        if (
          !this.authorized ||
          this.lifetime.signal.aborted ||
          !current.isSuccess ||
          current.isFetching
        )
          return;
        this.mode.setValue(current.data.mode);
        this.mode.markAsPristine();
        this.intent.set(null);
        this.mutation.reset();
        this.clearMutations();
      });
  }
  public async canLeave(): Promise<boolean> {
    return await confirmDraftExit(this.dialogs, this.destroy, {
      dirty: !this.retired() && this.mode.dirty && !this.saveResult.isSuccess,
      unconfirmed: !this.retired() && (this.saveResult.isPending || this.uncertain),
    });
  }
  protected checkSession(): void {
    void this.session.refetch();
  }
}
