import { trustedVerifiedActor } from '../../verified-actor';
import type { Mutation } from '@tanstack/angular-query-experimental';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectorRef, Component, DestroyRef, inject, input, output } from '@angular/core';
import type { OnChanges, SimpleChanges } from '@angular/core';
import { TuiLink } from '@taiga-ui/core';
import {
  CancelledError,
  MutationObserver,
  QueryClient,
} from '@tanstack/angular-query-experimental';
import type { Api } from '../../../api.generated';
import { ApiFailure, writeJson } from '../../../api-http';
import { isUncertain } from '../../uncertain';
import { isVisibility } from './setup-contract';

type Identity = Api['schemas']['IdentityResponse'];
interface Intent {
  readonly actor: Identity;
  readonly key: string;
  readonly body: Api['schemas']['ChangeVisibilityRequest'];
}
@Component({
  selector: 'peerly-profile-visibility',
  imports: [TuiLink],
  templateUrl: './visibility.html',
  styleUrl: './visibility.less',
})
export class ProfileVisibility implements OnChanges {
  public readonly actor = input.required<Identity>();
  public readonly checking = input(false);
  public readonly status = input.required<Api['schemas']['OnboardingStatusResponse']>();
  public readonly expired = output();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly lifetime = new AbortController();
  private readonly scope: object = {};
  private readonly mutation = new MutationObserver(this.client, {
    retry: false,
    meta: { scope: this.scope },
    mutationFn: (intent: Readonly<Intent>) => {
      const actor = trustedVerifiedActor(this.client, intent.actor.account_id);
      if (this.checking() || !this.current(intent.actor) || actor === null)
        throw new CancelledError();
      return writeJson(
        this.http,
        '/api/v1/me/visibility',
        intent.body,
        {
          'x-csrf-token': actor.csrf_token,
          'idempotency-key': intent.key,
        },
        isVisibility,
        'PUT',
      );
    },
    onSuccess: async (_value, intent: Readonly<Intent>) => {
      if (!this.current(intent.actor)) return;
      await this.client.invalidateQueries({
        queryKey: ['account', intent.actor.account_id, 'onboarding'],
      });
    },
    onError: (error: unknown, intent: Readonly<Intent>) => {
      if (
        this.current(intent.actor) &&
        error instanceof ApiFailure &&
        (error.status === 401 || error.status === 403)
      )
        this.expired.emit();
    },
  });
  protected get changing() {
    return this.mutation.getCurrentResult();
  }
  protected get locked(): boolean {
    return (
      this.checking() ||
      this.changing.isPending ||
      trustedVerifiedActor(this.client, this.actor().account_id) === null
    );
  }
  protected get uncertain(): boolean {
    return isUncertain(this.changing.error);
  }
  public constructor() {
    const stop = this.mutation.subscribe(() => {
      this.change.markForCheck();
    });
    this.destroy.onDestroy(() => {
      this.lifetime.abort();
      stop();
      this.reset();
    });
  }
  public ngOnChanges(changes: Readonly<SimpleChanges>): void {
    const intent = this.changing.variables;
    if (
      changes['actor'] !== undefined &&
      intent !== undefined &&
      intent.actor.account_id !== this.actor().account_id
    )
      this.reset();
  }
  private current(actor: Readonly<Identity>): boolean {
    return (
      !this.lifetime.signal.aborted &&
      this.actor().account_id === actor.account_id &&
      this.client.getQueryData<Identity | null>(['session'])?.account_id === actor.account_id
    );
  }
  private reset(): void {
    this.mutation.reset();
    for (const mutation of this.client
      .getMutationCache()
      .findAll({ predicate: (entry: Readonly<Mutation>) => entry.meta?.['scope'] === this.scope }))
      this.client.getMutationCache().remove(mutation);
  }
  protected async reload(): Promise<void> {
    if (this.locked) return;
    this.reset();
    await this.client.invalidateQueries({
      queryKey: ['account', this.actor().account_id, 'onboarding'],
    });
  }
  protected async changeVisibility(hidden: boolean): Promise<void> {
    const visibility = this.status().visibility;
    if (visibility === null || this.locked || (this.changing.isError && !this.uncertain)) return;
    const previous = this.changing.variables;
    const intent =
      this.uncertain && previous !== undefined
        ? previous
        : {
            actor: this.actor(),
            key: crypto.randomUUID(),
            body: { hidden, expected_version: visibility.version },
          };
    try {
      await this.mutation.mutate(intent);
    } catch (error: unknown) {
      if (!(error instanceof ApiFailure) && !(error instanceof CancelledError)) throw error;
    }
  }
}
