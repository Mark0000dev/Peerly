import { trustedVerifiedActor } from '../../verified-actor';
import type { Mutation } from '@tanstack/angular-query-experimental';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectorRef,
  Component,
  DestroyRef,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import type { OnChanges, SimpleChanges, TemplateRef } from '@angular/core';
import { TuiAutoFocus } from '@taiga-ui/cdk';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  TuiButton,
  TuiLink,
  TuiCell,
  TuiIcon,
  TuiTitle,
  TuiDialogService,
  TUI_BREAKPOINT,
} from '@taiga-ui/core';
import type { TuiDialogContext } from '@taiga-ui/core';
import { firstValueFrom } from 'rxjs';
import { RouterLink } from '@angular/router';
import { TuiCardLarge } from '@taiga-ui/layout';
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
  imports: [TuiButton, TuiLink, TuiCell, TuiIcon, TuiTitle, TuiAutoFocus, RouterLink, TuiCardLarge],
  templateUrl: './visibility.html',
  styleUrl: './visibility.less',
})
export class ProfileVisibility implements OnChanges {
  public readonly actor = input.required<Identity>();
  public readonly checking = input(false);
  public readonly status = input.required<Api['schemas']['OnboardingStatusResponse']>();
  protected readonly restoreLabels: Readonly<Record<Api['schemas']['RestoreRequirement'], string>> =
    {
      photo: 'A ready profile photo',
      photo_review: 'A replacement photo reviewed by the team',
      study_context: 'A saved study goal or help area',
    };
  public readonly expired = output();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly dialogs = inject(TuiDialogService);
  private readonly hideConfirmation =
    viewChild.required<TemplateRef<TuiDialogContext<boolean>>>('hideConfirmation');
  private readonly breakpoint = inject(TUI_BREAKPOINT);
  private readonly confirming = signal(false);
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
      this.confirming() ||
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
  private canHideNow(): boolean {
    return (
      !this.locked &&
      !this.changing.isError &&
      this.status().capabilities.can_hide_profile &&
      this.status().visibility?.hidden === false
    );
  }
  protected async requestHide(): Promise<void> {
    const actor = this.actor();
    const visibility = this.status().visibility;
    if (visibility === null || !this.canHideNow()) return;
    this.confirming.set(true);
    const accepted = await firstValueFrom(
      this.dialogs
        .open<boolean>(this.hideConfirmation(), {
          label: '',
          appearance: this.breakpoint() === 'mobile' ? 'fullscreen' : 'taiga',
        })
        .pipe(takeUntilDestroyed(this.destroy)),
      { defaultValue: false },
    ).finally(() => {
      this.confirming.set(false);
    });
    if (
      !accepted ||
      !this.current(actor) ||
      !this.canHideNow() ||
      this.status().visibility?.version !== visibility.version
    )
      return;
    await this.changeVisibility(true);
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
