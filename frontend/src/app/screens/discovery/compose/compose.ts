import { HttpClient } from '@angular/common/http';
import { DATE_PIPE_DEFAULT_OPTIONS, DatePipe } from '@angular/common';
import {
  Component,
  afterNextRender,
  ChangeDetectorRef,
  DestroyRef,
  inject,
  Injector,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import type { OnChanges, SimpleChanges } from '@angular/core';
import { RouterLink } from '@angular/router';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { TuiButton, TuiDialog, TuiError, TuiLink, TuiTextfield } from '@taiga-ui/core';
import type { TuiDialogOptions } from '@taiga-ui/core';
import { TuiTextarea } from '@taiga-ui/kit/components/textarea';
import { TuiAutoFocus } from '@taiga-ui/cdk';
import { TuiForm } from '@taiga-ui/layout';
import { defer, of } from 'rxjs';
import {
  CancelledError,
  MutationObserver,
  QueryClient,
} from '@tanstack/angular-query-experimental';
import type { Mutation, QueryCacheNotifyEvent } from '@tanstack/angular-query-experimental';
import type { Api } from '../../../api.generated';
import { ApiFailure, writeJson } from '../../../api-http';
import { isUncertain } from '../../uncertain';
import {
  codePoints,
  contextBelongsTo,
  isPreview,
  isPreviewResult,
  isSendResult,
  requestParameters,
  requestTextValidator,
  sameContext,
} from './compose-contract';
import type { ComposerSelection, DraftSource, PreviewResult, SendResult } from './compose-contract';

type Identity = Api['schemas']['IdentityResponse'];
interface PreviewIntent {
  readonly actorId: string;
  readonly lifetime: object;
  readonly key: string;
  readonly body: Api['schemas']['PreviewRequestBody'];
}
interface SendIntent extends ComposerSelection {
  readonly lifetime: object;
  readonly key: string;
  readonly body: Api['schemas']['SendRequestBody'];
}

@Component({
  selector: 'app-request-composer',
  providers: [{ provide: DATE_PIPE_DEFAULT_OPTIONS, useValue: { timezone: '+0800' } }],
  imports: [
    DatePipe,
    RouterLink,
    ReactiveFormsModule,
    TuiButton,
    TuiDialog,
    TuiError,
    TuiLink,
    TuiTextfield,
    TuiTextarea,
    TuiAutoFocus,
    TuiForm,
  ],
  templateUrl: './compose.html',
  styleUrl: './compose.less',
})
export class RequestComposer implements OnChanges {
  public readonly actor = input.required<Identity>();
  public readonly recipientId = input.required<string>();
  public readonly mode = input.required<Api['schemas']['DiscoveryMode']>();
  public readonly recipientName = input<string | null>(null);
  public readonly open = input(false);
  public readonly closed = output();
  public readonly expired = output();
  public readonly sent = output<SendResult>();
  public readonly reconciliation = output<ComposerSelection>();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly injector = inject(Injector);
  private readonly textFocus = viewChild.required('requestTextFocus', { read: TuiAutoFocus });
  private readonly noteFocus = viewChild.required('requestNoteFocus', { read: TuiAutoFocus });
  private readonly dismissible = defer(() => of(!this.pending));
  protected get dialogOptions(): Readonly<Partial<TuiDialogOptions<void>>> {
    return {
      label: '',
      size: 'm',
      appearance: 'fullscreen',
      closable: this.dismissible,
      dismissible: this.dismissible,
    };
  }
  private readonly lifetime = signal<object>({});
  private readonly source = signal<DraftSource | null>(null);
  protected readonly noteOpen = signal(false);
  protected readonly form = new FormGroup({
    text: new FormControl('', { nonNullable: true, validators: [requestTextValidator(true)] }),
    note: new FormControl('', { nonNullable: true, validators: [requestTextValidator(false)] }),
  });
  protected readonly codePoints = codePoints;
  protected readonly requestParameters = requestParameters;
  private readonly previewMutation = new MutationObserver(this.client, {
    mutationKey: ['account', null, 'request-composer', 'preview'],
    gcTime: Infinity,
    retry: false,
    mutationFn: (intent: PreviewIntent) =>
      writeJson(
        this.http,
        '/api/v1/requests/preview',
        intent.body,
        this.headers(intent),
        (value): value is PreviewResult =>
          isPreviewResult(value) &&
          (!isPreview(value) ||
            contextBelongsTo(value.context, {
              actorId: intent.actorId,
              recipientId: intent.body.person_id,
              mode: intent.body.mode,
            })),
      ),
    onSuccess: (value: PreviewResult, intent: PreviewIntent) => {
      this.acceptPreview(value, intent);
    },
    onError: (error: unknown, intent: PreviewIntent) => {
      this.authorizeFailure(error, intent);
    },
  });
  private readonly sendMutation = new MutationObserver(this.client, {
    mutationKey: ['account', null, 'request-composer', 'send'],
    gcTime: Infinity,
    retry: false,
    mutationFn: (intent: SendIntent) =>
      writeJson(this.http, '/api/v1/requests', intent.body, this.headers(intent), isSendResult),
    onSuccess: async (value: SendResult, intent: SendIntent) => this.finishSend(value, intent),
    onError: (error: unknown, intent: SendIntent) => {
      this.authorizeFailure(error, intent);
    },
  });
  protected get checking() {
    return this.previewMutation.getCurrentResult();
  }
  protected get sending() {
    return this.sendMutation.getCurrentResult();
  }
  protected get uncertain(): boolean {
    return isUncertain(this.sending.error);
  }
  protected get previewUncertain(): boolean {
    return isUncertain(this.checking.error);
  }
  protected get pending(): boolean {
    return this.sending.isPending || this.checking.isPending;
  }
  protected get locked(): boolean {
    return !this.trusted() || this.pending || this.uncertain || this.previewUncertain;
  }
  protected get mismatch(): boolean {
    const source = this.source();
    return (
      source !== null &&
      (source.actorId !== this.actor().account_id ||
        source.recipientId !== this.recipientId() ||
        source.mode !== this.mode())
    );
  }
  protected get displayName(): string | null {
    return this.mismatch ? null : this.recipientName();
  }
  private records(): readonly Mutation[] {
    return this.client.getMutationCache().findAll({
      predicate: (entry: Readonly<Mutation>) =>
        entry.options.meta?.['composerOwner'] === this.lifetime(),
    });
  }
  protected get retained(): Api['schemas']['PreviewResponse'] | null {
    const id = this.source()?.previewId;
    return this.records().reduceRight<Api['schemas']['PreviewResponse'] | null>(
      (found, entry: Readonly<Mutation>) => {
        const value: unknown = entry.state.data;
        return found ?? (isPreview(value) && value.preview_id === id ? value : null);
      },
      null,
    );
  }

  protected get proposed(): Api['schemas']['PreviewResponse'] | null {
    const data = this.checking.data;
    return data !== undefined && isPreview(data) && data.preview_id !== this.source()?.previewId
      ? data
      : null;
  }
  protected get pair(): SendResult | null {
    const data = this.sending.isSuccess ? this.sending.data : this.checking.data;
    return data !== undefined && isSendResult(data) && data.outcome !== 'sent' ? data : null;
  }
  protected get canSend(): boolean {
    return (
      this.retained?.can_send === true &&
      this.proposed === null &&
      this.pair === null &&
      !this.mismatch &&
      !this.locked &&
      !(this.sending.error instanceof ApiFailure && this.sending.error.status === 409)
    );
  }
  protected get edited(): boolean {
    return this.form.controls.text.value !== this.retained?.suggested_text;
  }
  protected get errorText(): string | null {
    const error = this.sending.error ?? this.checking.error;
    if (error === null) return null;
    if (this.uncertain)
      return 'We couldn’t confirm whether this request was sent. Retry the same request to check its result.';
    if (this.previewUncertain)
      return 'We couldn’t confirm the preview. Retry the same check; nothing is sent by reviewing.';
    if (error instanceof ApiFailure) {
      if (error.status === 409)
        return 'The pair or academic source changed. Review current context before another send.';
      if (error.status === 429)
        return 'The server cannot accept another request right now. Recheck current availability.';
      if (error.status === 404) return 'This person or academic context is no longer available.';
      if (error.status === 422)
        return 'The server could not accept these fields. Your draft is kept.';
    }
    return 'We couldn’t complete this action. Your draft is kept.';
  }
  protected get availabilityText(): string {
    switch (this.retained?.block_reason) {
      case 'outgoing_pending_limit':
        return 'Your outgoing pending limit has been reached.';
      case 'daily_send_limit':
        return 'Your daily send limit has been reached.';
      case 'cooldown':
        return 'A new request in this pair is not available until the server’s date.';
      case 'source_changed':
        return 'The saved academic source changed. Review the current context.';
      case 'incoming':
        return 'An incoming request already exists. Review Requests instead of sending another.';
      case 'existing_outgoing':
        return 'You already have an outgoing request. Review Requests instead of sending another.';
      case 'connected':
        return 'A connection already exists. Your earlier request is in Requests.';
      default:
        return 'This person or academic context is no longer available.';
    }
  }
  public constructor() {
    const preview = this.previewMutation.subscribe(() => {
      this.settle();
      this.change.markForCheck();
    });
    const send = this.sendMutation.subscribe(() => {
      this.settle();
      this.change.markForCheck();
    });
    const session = this.client
      .getQueryCache()
      .subscribe((event: Readonly<QueryCacheNotifyEvent>) => {
        const key: unknown = event.query.queryKey;
        if (!Array.isArray(key) || key[0] !== 'session') return;
        const identity = this.client.getQueryData<Identity | null>(['session']);
        const state = this.client.getQueryState(['session']);
        const owner = this.previewMutation.options.mutationKey?.[1];
        if (
          typeof owner === 'string' &&
          (state?.status === 'error' ||
            identity === null ||
            (identity !== undefined &&
              (identity.account_id !== owner || !identity.capabilities.can_use_student_features)))
        )
          this.reset();
        this.settle();
        this.change.markForCheck();
      });
    this.destroy.onDestroy(() => {
      preview();
      send();
      session();
      this.reset();
    });
  }
  public ngOnChanges(changes: Readonly<SimpleChanges>): void {
    const id = this.actor().account_id;
    const ownerChanged = this.previewMutation.options.mutationKey?.[1] !== id;
    if (ownerChanged) {
      this.reset();
      this.previewMutation.setOptions({
        ...this.previewMutation.options,
        mutationKey: ['account', id, 'request-composer', 'preview'],
        meta: { composerOwner: this.lifetime() },
      });
      this.sendMutation.setOptions({
        ...this.sendMutation.options,
        mutationKey: ['account', id, 'request-composer', 'send'],
        meta: { composerOwner: this.lifetime() },
      });
    }
    const selectionChanged =
      changes['open'] !== undefined ||
      changes['recipientId'] !== undefined ||
      changes['mode'] !== undefined;
    if (
      (ownerChanged || selectionChanged) &&
      this.open() &&
      this.source() === null &&
      this.trusted()
    )
      this.review();
  }
  protected trusted(): boolean {
    const identity = this.client.getQueryData<Identity | null>(['session']);
    const state = this.client.getQueryState(['session']);
    return (
      !this.destroy.destroyed &&
      identity?.account_id === this.actor().account_id &&
      identity.capabilities.can_use_student_features &&
      state?.status === 'success' &&
      state.fetchStatus === 'idle'
    );
  }
  private current(intent: PreviewIntent | SendIntent): boolean {
    const identity = this.client.getQueryData<Identity | null>(['session']);
    return (
      !this.destroy.destroyed &&
      intent.lifetime === this.lifetime() &&
      intent.actorId === this.actor().account_id &&
      identity?.account_id === intent.actorId &&
      identity.capabilities.can_use_student_features
    );
  }
  private headers(intent: PreviewIntent | SendIntent): Readonly<Record<string, string>> {
    const identity = this.client.getQueryData<Identity | null>(['session']);
    if (!this.current(intent) || !this.trusted() || identity === undefined || identity === null)
      throw new CancelledError();
    return { 'X-CSRF-Token': identity.csrf_token, 'Idempotency-Key': intent.key };
  }
  private reset(): void {
    const records = this.records();
    this.lifetime.set({});
    this.previewMutation.setOptions({
      ...this.previewMutation.options,
      meta: { composerOwner: this.lifetime() },
    });
    this.sendMutation.setOptions({
      ...this.sendMutation.options,
      meta: { composerOwner: this.lifetime() },
    });
    this.source.set(null);
    this.noteOpen.set(false);
    this.form.reset();
    this.previewMutation.reset();
    this.sendMutation.reset();
    for (const entry of records) this.client.getMutationCache().remove(entry);
  }
  private authorizeFailure(error: unknown, intent: PreviewIntent | SendIntent): void {
    if (
      this.current(intent) &&
      this.trusted() &&
      error instanceof ApiFailure &&
      error.status === 401
    ) {
      this.reset();
      this.expired.emit();
    }
  }
  private settle(): void {
    const preview = this.checking;
    const send = this.sending;
    if (preview.isError) this.authorizeFailure(preview.error, preview.variables);
    if (send.isError) this.authorizeFailure(send.error, send.variables);
    if (send.isSuccess && send.data.outcome === 'sent' && this.trusted())
      void this.finishSend(send.data, send.variables);
  }
  private acceptPreview(value: PreviewResult, intent: PreviewIntent): void {
    if (!this.current(intent) || !isPreview(value)) return;
    const bound = this.retained;
    const source = this.source();
    if (
      source?.actorId !== intent.actorId ||
      source.recipientId !== intent.body.person_id ||
      source.mode !== intent.body.mode
    )
      return;
    if (source.previewId === null) {
      this.source.set({ ...source, previewId: value.preview_id });
      this.form.reset({ text: value.suggested_text, note: '' });
    } else if (bound !== null && sameContext(bound.context, value.context)) {
      this.source.set({ ...source, previewId: value.preview_id });
      if (!this.uncertain) this.sendMutation.reset();
    }
  }
  private async finishSend(value: SendResult, intent: SendIntent): Promise<void> {
    if (!this.current(intent) || !this.trusted()) return;
    if (value.outcome === 'sent') this.reset();
    const completion: SendIntent = { ...intent, lifetime: this.lifetime() };
    await Promise.all([
      this.client.invalidateQueries({ queryKey: ['account', intent.actorId, 'requests'] }),
      this.client.invalidateQueries({ queryKey: ['account', intent.actorId, 'discovery'] }),
    ]);
    if (!this.current(completion) || !this.trusted() || value.outcome !== 'sent') return;
    this.sent.emit(value);
  }
  protected review(): void {
    if (!this.trusted() || this.pending || this.uncertain || this.previewUncertain || this.mismatch)
      return;
    if (this.source() === null) {
      this.reset();
      this.source.set({
        actorId: this.actor().account_id,
        recipientId: this.recipientId(),
        mode: this.mode(),
        previewId: null,
      });
    }
    const intent: PreviewIntent = {
      actorId: this.actor().account_id,
      lifetime: this.lifetime(),
      key: crypto.randomUUID(),
      body: { person_id: this.recipientId(), mode: this.mode() },
    };
    void this.previewMutation.mutate(intent).catch(() => undefined);
  }
  protected retryPreview(): void {
    const intent = this.checking.variables;
    if (
      this.previewUncertain &&
      intent !== undefined &&
      this.current(intent) &&
      this.trusted() &&
      !this.mismatch
    )
      void this.previewMutation.mutate(intent).catch(() => undefined);
  }
  protected keepOriginal(): void {
    const source = this.source();
    if (source !== null && !this.pending)
      this.reconciliation.emit({
        actorId: source.actorId,
        recipientId: source.recipientId,
        mode: source.mode,
      });
  }
  protected discardAndReview(): void {
    if (!this.trusted() || this.pending || this.uncertain || this.previewUncertain) return;
    this.reset();
    this.review();
  }
  protected acceptContext(useSuggestion: boolean): void {
    const value = this.proposed;
    const source = this.source();
    if (value === null || source === null || this.locked || this.mismatch) return;
    this.source.set({ ...source, previewId: value.preview_id });
    if (useSuggestion) this.form.reset({ text: value.suggested_text, note: '' });
    this.sendMutation.reset();
  }
  protected resetText(): void {
    const value = this.retained;
    if (value !== null && !this.locked && !this.mismatch && this.proposed === null)
      this.form.controls.text.setValue(value.suggested_text);
  }
  protected close(): void {
    if (!this.pending) this.closed.emit();
  }
  protected submit(): void {
    this.form.markAllAsTouched();
    if (this.form.controls.note.invalid) this.noteOpen.set(true);
    if (!this.canSend) return;
    if (this.form.invalid) {
      const lifetime = this.lifetime();
      afterNextRender(
        () => {
          if (lifetime !== this.lifetime() || !this.open() || this.locked) return;
          if (this.form.controls.text.invalid) this.textFocus().focus();
          else if (this.form.controls.note.invalid) this.noteFocus().focus();
        },
        { injector: this.injector },
      );
      return;
    }
    const source = this.source();
    if (source?.previewId === null || source === null) return;
    const body: Api['schemas']['SendRequestBody'] = {
      person_id: source.recipientId,
      preview_id: source.previewId,
      text: this.form.controls.text.value,
      note:
        this.form.controls.note.value.trim().length === 0 ? null : this.form.controls.note.value,
    };
    const prior = this.sending.variables;
    const intent: SendIntent =
      prior !== undefined &&
      this.sending.isError &&
      prior.body.preview_id === body.preview_id &&
      prior.body.text === body.text &&
      prior.body.note === body.note
        ? prior
        : {
            actorId: source.actorId,
            recipientId: source.recipientId,
            mode: source.mode,
            lifetime: this.lifetime(),
            key: crypto.randomUUID(),
            body,
          };
    void this.sendMutation.mutate(intent).catch(() => undefined);
  }
  protected retrySend(): void {
    const intent = this.sending.variables;
    if (
      this.uncertain &&
      intent !== undefined &&
      this.current(intent) &&
      this.trusted() &&
      !this.mismatch
    )
      void this.sendMutation.mutate(intent).catch(() => undefined);
  }
}
