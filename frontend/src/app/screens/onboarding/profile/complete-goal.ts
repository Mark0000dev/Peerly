import type { Mutation } from '@tanstack/angular-query-experimental';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectorRef, Component, DestroyRef, inject, input, output } from '@angular/core';
import type { OnChanges } from '@angular/core';
import { TuiButton, TuiDialogService, TuiLink } from '@taiga-ui/core';
import { TUI_CONFIRM } from '@taiga-ui/kit';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { firstValueFrom } from 'rxjs';
import {
  CancelledError,
  MutationObserver,
  QueryClient,
} from '@tanstack/angular-query-experimental';
import type { Api } from '../../../api.generated';
import { ApiFailure, writeJson } from '../../../api-http';
import { isGoal } from '../../study-context-contract';
import { trustedVerifiedActor } from '../../verified-actor';
import { isUncertain } from '../../uncertain';
interface Intent {
  readonly actorId: string;
  readonly body: Api['schemas']['CompleteGoalRequest'];
  readonly key: string;
}
@Component({
  selector: 'peerly-complete-goal',
  imports: [TuiButton, TuiLink],
  template: `
    @if (goal().completed_at === null) {
      <button
        tuiButton
        type="button"
        appearance="secondary"
        [disabled]="locked || action.isError"
        (click)="complete()"
      >
        Mark goal done
      </button>
    }
    @if (action.isPending) {
      <p role="status">Completing your goal…</p>
    }
    @if (action.isSuccess) {
      <p role="status">Goal completed.</p>
    }
    @if (uncertain) {
      <p role="alert">
        We could not confirm completion. Retry the same action or reload the saved goal.
      </p>
      <button tuiButton type="button" [disabled]="locked" (click)="retry()">
        Retry same completion
      </button>
    } @else if (action.isError) {
      <p role="alert">
        Your goal could not be completed. Reload its saved state before trying again.
      </p>
    }
    @if (action.isError) {
      <button tuiLink type="button" [disabled]="locked" (click)="reload()">
        Reload saved goal
      </button>
    }
  `,
  styles: `
    :host {
      display: block;
      min-inline-size: 0;
    }
    button {
      max-inline-size: 100%;
      white-space: normal;
      block-size: auto;
      min-block-size: var(--tui-height-m);
    }
  `,
})
export class CompleteGoal implements OnChanges {
  public readonly actorId = input.required<string>();
  public readonly goal = input.required<Api['schemas']['GoalResponse']>();
  public readonly checking = input(false);
  public readonly expired = output();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly destroy = inject(DestroyRef);
  private readonly change = inject(ChangeDetectorRef);
  private readonly dialogs = inject(TuiDialogService);
  private readonly scope: object = {};
  private readonly mutation = new MutationObserver(this.client, {
    retry: false,
    meta: { scope: this.scope },
    mutationFn: (intent: Readonly<Intent>) => {
      const actor = trustedVerifiedActor(this.client, intent.actorId);
      if (this.checking() || !this.current(intent.actorId) || actor === null)
        throw new CancelledError();
      return writeJson(
        this.http,
        '/api/v1/me/goal/complete',
        intent.body,
        { 'x-csrf-token': actor.csrf_token, 'idempotency-key': intent.key },
        isGoal,
      );
    },
    onSuccess: async (_receipt, intent: Readonly<Intent>) => {
      if (!this.current(intent.actorId)) return;
      await this.client.invalidateQueries({
        queryKey: ['account', intent.actorId, 'goal'],
        refetchType: trustedVerifiedActor(this.client, intent.actorId) === null ? 'none' : 'active',
      });
      await this.client.invalidateQueries({
        queryKey: ['account', intent.actorId, 'onboarding'],
        refetchType: 'none',
      });
    },
    onError: (error: unknown, intent: Readonly<Intent>) => {
      if (
        this.current(intent.actorId) &&
        error instanceof ApiFailure &&
        (error.status === 401 || error.status === 403)
      )
        this.expired.emit();
    },
  });
  protected get action() {
    return this.mutation.getCurrentResult();
  }
  protected get locked(): boolean {
    return (
      this.checking() ||
      this.action.isPending ||
      trustedVerifiedActor(this.client, this.actorId()) === null
    );
  }
  protected get uncertain(): boolean {
    return isUncertain(this.action.error) || this.action.error instanceof CancelledError;
  }
  public constructor() {
    const stop = this.mutation.subscribe(() => {
      this.change.markForCheck();
    });
    this.destroy.onDestroy(() => {
      stop();
      this.retire();
    });
  }
  public ngOnChanges(): void {
    if (this.action.variables !== undefined && this.action.variables.actorId !== this.actorId())
      this.retire();
  }
  private retire(): void {
    this.mutation.reset();
    for (const mutation of this.client
      .getMutationCache()
      .findAll({ predicate: (entry: Readonly<Mutation>) => entry.meta?.['scope'] === this.scope }))
      this.client.getMutationCache().remove(mutation);
  }
  private current(id: string): boolean {
    return (
      !this.destroy.destroyed &&
      this.actorId() === id &&
      this.client.getQueryData<Api['schemas']['IdentityResponse'] | null>(['session'])
        ?.account_id === id
    );
  }
  private canCompleteNow(): boolean {
    return !this.locked;
  }
  protected async complete(): Promise<void> {
    if (this.locked || this.action.isError || this.goal().completed_at !== null) return;
    const actorId = this.actorId();
    const goal = this.goal();
    const accepted = await firstValueFrom(
      this.dialogs
        .open<boolean>(TUI_CONFIRM, {
          label: 'Mark this goal done?',
          data: {
            content: 'Your existing chats will remain available.',
            yes: 'Mark done',
            no: 'Keep goal',
          },
        })
        .pipe(takeUntilDestroyed(this.destroy)),
      { defaultValue: false },
    );
    if (
      !accepted ||
      !this.canCompleteNow() ||
      !this.current(actorId) ||
      this.goal().id !== goal.id ||
      this.goal().version !== goal.version
    )
      return;
    await this.run({
      actorId,
      body: { goal_id: goal.id, expected_version: goal.version },
      key: crypto.randomUUID(),
    });
  }
  protected async retry(): Promise<void> {
    const intent = this.action.variables;
    if (!this.locked && this.uncertain && intent !== undefined) await this.run(intent);
  }
  private async run(intent: Readonly<Intent>): Promise<void> {
    try {
      await this.mutation.mutate(intent);
    } catch (error: unknown) {
      if (!(error instanceof ApiFailure) && !(error instanceof CancelledError)) throw error;
    }
  }
  protected async reload(): Promise<void> {
    if (this.locked) return;
    this.mutation.reset();
    await this.client.invalidateQueries({ queryKey: ['account', this.actorId(), 'goal'] });
  }
}
