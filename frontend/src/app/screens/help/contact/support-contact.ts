import { HttpClient } from '@angular/common/http';
import { ChangeDetectorRef, Component, DestroyRef, inject, input, signal } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { TuiAppBar, TuiCardLarge } from '@taiga-ui/layout';
import {
  TuiButton,
  TuiDialogService,
  TuiInput,
  TuiLink,
  TuiRadio,
  TuiTextfield,
} from '@taiga-ui/core';
import { TuiTextarea } from '@taiga-ui/kit';
import {
  CancelledError,
  MutationObserver,
  QueryClient,
  QueryObserver,
} from '@tanstack/angular-query-experimental';
import type { Mutation } from '@tanstack/angular-query-experimental';
import type { Api } from '../../../api.generated';
import { ApiFailure, writeJson } from '../../../api-http';
import { confirmDraftExit } from '../../draft-exit';
import { sessionOptions } from '../../session';
import {
  isSupportPreparation,
  isSupportReceipt,
  isSupportTopic,
  supportTopics,
  validReplyAddress,
  validSupportText,
} from './support-contract';
import { supportActor, supportOutcomeUnknown, supportWrite } from './support-query';

interface SupportIntent {
  readonly actorId: string | null;
  readonly body: Api['schemas']['SupportBody'];
  readonly key: string;
}
@Component({
  selector: 'app-support-contact',
  imports: [
    TuiAppBar,
    TuiCardLarge,
    NgTemplateOutlet,
    ReactiveFormsModule,
    RouterLink,
    TuiButton,
    TuiInput,
    TuiLink,
    TuiRadio,
    TuiTextfield,
    TuiTextarea,
  ],
  templateUrl: './support-contact.html',
  styleUrl: './support.less',
})
export class SupportContact {
  public readonly embedded = input(false);
  private readonly http = inject(HttpClient);
  private readonly dialogs = inject(TuiDialogService);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly lifetime = new AbortController();
  private readonly owner: object = {};
  private readonly retired = signal(false);
  private readonly intent = signal<SupportIntent | null>(null);
  private readonly draftOwner = signal<string | null | undefined>(undefined);
  private readonly session = new QueryObserver(this.client, sessionOptions(this.http, this.client));
  private readonly preparation = new MutationObserver(this.client, {
    mutationKey: ['support-preparation'],
    meta: { supportOwner: this.owner },
    retry: false,
    mutationFn: () =>
      supportWrite(
        writeJson(this.http, '/api/v1/support-context', {}, {}, isSupportPreparation),
        this.lifetime.signal,
      ),
  });
  private readonly creation = new MutationObserver(this.client, {
    mutationKey: ['support-create'],
    meta: { supportOwner: this.owner },
    retry: false,
    mutationFn: async (intent: SupportIntent) => {
      this.authorize(intent);
      const proof = this.preparation.getCurrentResult().data ?? (await this.preparation.mutate());
      if (Date.parse(proof.expires_at) <= Date.now())
        throw new ApiFailure(404, 'support_unavailable', null);
      const actor = this.authorize(intent);
      return supportWrite(
        writeJson(
          this.http,
          intent.actorId === null ? '/api/v1/support-cases' : '/api/v1/me/support-cases',
          intent.body,
          { 'x-csrf-token': actor?.csrf_token ?? proof.csrf_token, 'idempotency-key': intent.key },
          isSupportReceipt,
        ),
        this.lifetime.signal,
      );
    },
  });
  protected readonly topics = supportTopics;
  protected readonly form = new FormGroup({
    topic: new FormControl<Api['schemas']['SupportTopic']>('other', { nonNullable: true }),
    reply: new FormControl('', {
      nonNullable: true,
    }),
    message: new FormControl('', {
      nonNullable: true,
    }),
    details: new FormControl('', { nonNullable: true }),
  });
  protected readonly attempted = signal(false);
  protected get sessionReady(): boolean {
    return !this.retired() && supportActor(this.client) !== undefined;
  }
  protected get result() {
    return this.creation.getCurrentResult();
  }
  protected get busy(): boolean {
    return this.result.isPending;
  }
  protected get uncertain(): boolean {
    return (
      supportOutcomeUnknown(this.result.error) ||
      (this.result.error instanceof ApiFailure &&
        (this.result.error.status === 404 || this.result.error.status === 409))
    );
  }
  protected get locked(): boolean {
    return this.busy || this.intent() !== null;
  }
  protected get valid(): boolean {
    const value = this.form.getRawValue();
    return (
      isSupportTopic(value.topic) &&
      validReplyAddress(value.reply) &&
      validSupportText(value.message, 4000) &&
      (value.details.length === 0 || validSupportText(value.details, 2000))
    );
  }
  protected get reference(): string | null {
    return this.result.error instanceof ApiFailure ? this.result.error.requestId : null;
  }
  protected get errorText(): string {
    const error = this.result.error;
    if (error instanceof ApiFailure && error.code === 'support_unavailable')
      return 'This support proof is unavailable or expired. Check recent requests. An anonymous request cannot be recovered without its original proof.';
    if (this.uncertain)
      return 'We couldn’t confirm whether your request was received. Check recent requests or retry the identical request.';
    if (error instanceof ApiFailure && error.status === 429)
      return 'Too many requests. Please try again later. Your text is still here.';
    return 'Your request could not be confirmed. Your text is still here. Check your connection and try again.';
  }
  public constructor() {
    const unsubscribeSession = this.session.subscribe(
      (result: Readonly<ReturnType<typeof this.session.getCurrentResult>>) => {
        const owner = this.draftOwner();
        if (result.isSuccess && !result.isFetching && owner === undefined)
          this.draftOwner.set(result.data?.account_id ?? null);
        if (
          owner !== undefined &&
          result.isSuccess &&
          !result.isFetching &&
          (result.data?.account_id ?? null) !== owner
        ) {
          this.retired.set(true);
          this.lifetime.abort();
          this.form.reset();
          this.creation.reset();
          this.clearMutations();
        }
        this.change.markForCheck();
      },
    );
    const unsubscribePreparation = this.preparation.subscribe(() => {
      this.change.markForCheck();
    });
    const unsubscribeCreation = this.creation.subscribe(() => {
      this.change.markForCheck();
    });
    this.destroy.onDestroy(() => {
      this.lifetime.abort();
      unsubscribeSession();
      unsubscribePreparation();
      unsubscribeCreation();
      this.session.destroy();
      this.creation.reset();
      this.preparation.reset();
      this.clearMutations();
    });
  }
  private authorize(intent: SupportIntent): Api['schemas']['IdentityResponse'] | null {
    const actor = supportActor(this.client);
    if (
      this.retired() ||
      this.lifetime.signal.aborted ||
      actor === undefined ||
      (actor?.account_id ?? null) !== intent.actorId
    )
      throw new CancelledError();
    return actor;
  }
  private clearMutations(): void {
    for (const mutation of this.client.getMutationCache().findAll({
      predicate: (mutation: Readonly<Mutation>) =>
        mutation.options.meta?.['supportOwner'] === this.owner,
    }))
      this.client.getMutationCache().remove(mutation);
  }
  protected send(): void {
    this.attempted.set(true);
    if (!this.sessionReady || !this.valid || this.locked) return;
    const value = this.form.getRawValue();
    const intent: SupportIntent = {
      actorId: supportActor(this.client)?.account_id ?? null,
      key: crypto.randomUUID(),
      body: {
        topic: value.topic,
        reply_address: value.reply,
        message: value.message,
        details: value.details.length === 0 ? null : value.details,
      },
    };
    this.intent.set(intent);
    this.submit(intent);
  }
  protected retry(): void {
    const intent = this.intent();
    if (!this.sessionReady || this.busy || intent === null || this.result.isSuccess) return;
    this.submit(intent);
  }
  private submit(intent: SupportIntent): void {
    void this.creation.mutate(intent).catch((error: unknown) => {
      if (
        error instanceof ApiFailure &&
        intent.actorId !== null &&
        (error.status === 401 || error.status === 403) &&
        !this.lifetime.signal.aborted
      )
        void this.session.refetch();
      if (!(error instanceof ApiFailure) && !(error instanceof CancelledError)) throw error;
    });
  }
  protected edit(): void {
    if (this.busy || this.uncertain || this.result.isSuccess) return;
    this.intent.set(null);
    this.creation.reset();
    this.clearMutations();
  }
  public async canLeave(): Promise<boolean> {
    return await confirmDraftExit(this.dialogs, this.destroy, {
      dirty: !this.retired() && this.form.dirty && !this.result.isSuccess,
      unconfirmed: !this.retired() && (this.busy || this.uncertain),
    });
  }
  protected reloadIdentity(): void {
    void this.session.refetch();
  }
}
