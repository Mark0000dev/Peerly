import type { HttpClient } from '@angular/common/http';
import { signal } from '@angular/core';
import type { DestroyRef } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup } from '@angular/forms';
import { CancelledError, MutationObserver } from '@tanstack/angular-query-experimental';
import type { Mutation, QueryClient } from '@tanstack/angular-query-experimental';
import { TUI_CONFIRM } from '@taiga-ui/kit';
import type { TuiDialogService } from '@taiga-ui/core';
import { firstValueFrom } from 'rxjs';
import type { Api } from '../../../api.generated';
import { ApiFailure, writeJson } from '../../../api-http';
import { confirmDraftExit } from '../../draft-exit';
import { isSupportReceipt } from './support-contract';

interface StatusIntent {
  readonly actorId: string;
  readonly caseId: string;
  readonly key: string;
  readonly body: Api['schemas']['SupportStatusBody'];
}
interface StatusContext {
  readonly actor: () => Api['schemas']['IdentityResponse'] | null;
  readonly owner: () => string | null;
  readonly selected: () => string | null;
  readonly current: () => Api['schemas']['OperatorSupportResponse'] | undefined;
  readonly refresh: () => Promise<boolean>;
  readonly changed: () => Promise<void>;
  readonly authorityFailure: (error: unknown, actor: string) => void;
  readonly mark: () => void;
}
function statusUnknown(error: unknown): boolean {
  return error instanceof ApiFailure && (error.status === 0 || error.status >= 500);
}

// Owns only the editable command draft and its immutable manual replay intent.
// Receipts/errors/loading remain exclusively in the actual MutationObserver.
export class SupportStatusEditor {
  public readonly form = new FormGroup({
    status: new FormControl<Api['schemas']['SupportStatus']>('received', { nonNullable: true }),
    expected_version: new FormControl(0, { nonNullable: true }),
  });
  private readonly pendingIntent = signal<StatusIntent | null>(null);
  public readonly intent = this.pendingIntent.asReadonly();
  private readonly retired = signal(false);
  private readonly owner: object = {};
  private readonly mutation: MutationObserver<
    Api['schemas']['SupportReceiptResponse'],
    Error,
    StatusIntent
  >;
  private readonly unsubscribe: () => void;
  public constructor(
    private readonly http: Readonly<HttpClient>,
    private readonly client: QueryClient,
    private readonly dialogs: Readonly<TuiDialogService>,
    private readonly destroyRef: Readonly<DestroyRef>,
    private readonly context: StatusContext,
  ) {
    this.mutation = new MutationObserver(client, this.options(null, null));
    this.unsubscribe = this.mutation.subscribe(() => {
      const error = this.result.error;
      const actor = this.mutation.options.mutationKey?.[1];
      if (
        typeof actor === 'string' &&
        this.context.owner() === actor &&
        error instanceof ApiFailure &&
        (error.status === 401 || error.status === 403)
      )
        this.context.authorityFailure(error, actor);
      this.context.mark();
    });
  }
  public get result() {
    return this.mutation.getCurrentResult();
  }
  public get unknown(): boolean {
    return statusUnknown(this.result.error);
  }
  public get conflict(): boolean {
    return this.result.error instanceof ApiFailure && this.result.error.status === 409;
  }
  public get staleDraft(): boolean {
    const current = this.context.current();
    return (
      current !== undefined && this.form.controls.expected_version.value !== current.receipt.version
    );
  }
  public get canReview(): boolean {
    return (
      !this.retired() &&
      this.context.actor() !== null &&
      this.context.current() !== undefined &&
      !this.staleDraft &&
      this.intent() === null &&
      !this.result.isPending
    );
  }
  public get canConfirm(): boolean {
    const intent = this.intent();
    return (
      intent !== null &&
      this.owns(intent) &&
      this.result.isIdle &&
      this.context.current()?.receipt.version === intent.body.expected_version &&
      this.form.controls.status.value === intent.body.status
    );
  }
  private owns(intent: StatusIntent): boolean {
    return (
      !this.retired() &&
      !this.isDestroyed() &&
      this.context.owner() === intent.actorId &&
      this.context.selected() === intent.caseId &&
      this.intent() === intent
    );
  }
  private options(actor: string | null, caseId: string | null) {
    return {
      mutationKey: ['account', actor, 'operator', 'support', 'status', caseId] as const,
      meta: { supportEditorOwner: this.owner },
      retry: false,
      mutationFn: async (
        intent: StatusIntent,
      ): Promise<Api['schemas']['SupportReceiptResponse']> => {
        const actor = this.context.actor();
        if (!this.owns(intent) || actor === null) throw new CancelledError();
        try {
          const receipt = await writeJson(
            this.http,
            `/api/v1/operator/cases/${encodeURIComponent(intent.caseId)}/status`,
            intent.body,
            { 'x-csrf-token': actor.csrf_token, 'idempotency-key': intent.key },
            (value): value is Api['schemas']['SupportReceiptResponse'] =>
              isSupportReceipt(value) &&
              value.case_id === intent.caseId &&
              value.status === intent.body.status &&
              (value.version === intent.body.expected_version ||
                value.version === intent.body.expected_version + 1),
            'PUT',
          );
          if (!this.owns(intent)) throw new CancelledError();
          return receipt;
        } catch (error: unknown) {
          if (!this.owns(intent)) throw new CancelledError();
          throw error;
        }
      },
    };
  }
  public syncOwner(actor: string | null, caseId: string | null): void {
    const previousActor = this.mutation.options.mutationKey?.[1];
    const previousCase = this.mutation.options.mutationKey?.[5];
    if (previousActor !== actor || previousCase !== caseId) {
      this.pendingIntent.set(null);
      this.mutation.reset();
      this.clearMutations(previousActor === actor);
      this.form.reset({ status: 'received', expected_version: 0 });
      this.form.enable({ emitEvent: false });
    }
    this.mutation.setOptions(this.options(actor, caseId));
    const current = this.context.current();
    if (current !== undefined && this.intent() === null && !this.form.dirty) {
      this.form.setValue({
        status: current.receipt.status,
        expected_version: current.receipt.version,
      });
    }
  }
  public review(): void {
    const actor = this.context.actor();
    const current = this.context.current();
    if (!this.canReview || actor === null || current === undefined) return;
    this.pendingIntent.set({
      actorId: actor.account_id,
      caseId: current.receipt.case_id,
      key: crypto.randomUUID(),
      body: this.form.getRawValue(),
    });
    this.form.disable({ emitEvent: false });
  }
  public confirm(): void {
    const intent = this.intent();
    if (!this.canConfirm || intent === null) return;
    this.submit(intent);
  }
  public replay(): void {
    const intent = this.intent();
    if (
      intent === null ||
      this.context.actor() === null ||
      !this.owns(intent) ||
      !this.result.isError ||
      !this.unknown
    )
      return;
    this.submit(intent);
  }
  private submit(intent: StatusIntent): void {
    void this.mutation
      .mutate(intent)
      .then(async () => {
        if (!this.owns(intent)) return;
        this.form.markAsPristine();
        // A replay receipt can be older than current state: invalidate, never copy it
        // over the canonical detail/inbox/history query results.
        await this.context.changed();
      })
      .catch((error: unknown) => {
        if (!(error instanceof ApiFailure) && !(error instanceof CancelledError)) throw error;
      });
  }
  private isDestroyed(): boolean {
    return this.destroyRef.destroyed;
  }
  public async useCurrent(): Promise<void> {
    if (this.context.actor() === null || this.result.isPending || this.retired()) return;
    const actor = this.context.actor()?.account_id;
    const caseId = this.context.selected();
    const intent = this.intent();
    if (!(await this.context.refresh())) return;
    if (
      actor !== this.context.actor()?.account_id ||
      caseId !== this.context.selected() ||
      intent !== this.intent() ||
      this.isDestroyed()
    )
      return;
    if (intent !== null || this.form.dirty) {
      const proceed = await firstValueFrom(
        this.dialogs
          .open<boolean>(TUI_CONFIRM, {
            label: 'Use the current case for a new change?',
            data: {
              content: this.unknown
                ? 'The current status does not prove whether your earlier change completed. A delayed change may still complete. Continuing retires this device’s earlier intent and uses the current version.'
                : 'Your prepared or unsaved status choice will be replaced by the current case. The original result remains part of the server’s recorded history.',
              yes: 'Use current case',
              no: 'Keep current draft',
            },
          })
          .pipe(takeUntilDestroyed(this.destroyRef)),
        { defaultValue: false },
      );
      if (!proceed) return;
    }
    const current = this.context.current();
    if (
      current === undefined ||
      actor !== this.context.actor()?.account_id ||
      caseId !== this.context.selected() ||
      intent !== this.intent() ||
      this.isDestroyed()
    )
      return;
    this.pendingIntent.set(null);
    this.mutation.reset();
    this.clearMutations(true);
    this.form.enable({ emitEvent: false });
    this.form.setValue({
      status: current.receipt.status,
      expected_version: current.receipt.version,
    });
    this.form.markAsPristine();
    this.context.mark();
  }
  public async canLeave(): Promise<boolean> {
    return await confirmDraftExit(this.dialogs, this.destroyRef, {
      dirty: this.form.dirty || (this.intent() !== null && this.result.isIdle),
      unconfirmed: this.result.isPending || this.unknown,
    });
  }
  private clearMutations(preserveDenied: boolean): void {
    for (const mutation of this.client.getMutationCache().findAll({
      predicate: (value: Readonly<Mutation>) =>
        value.options.meta?.['supportEditorOwner'] === this.owner &&
        !(
          preserveDenied &&
          value.state.error instanceof ApiFailure &&
          value.state.error.status === 403
        ),
    }))
      this.client.getMutationCache().remove(mutation);
  }
  public destroy(): void {
    this.retired.set(true);
    this.pendingIntent.set(null);
    this.unsubscribe();
    this.mutation.reset();
    this.clearMutations(true);
    this.form.reset();
  }
}
