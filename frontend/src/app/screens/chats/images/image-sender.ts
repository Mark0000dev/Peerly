import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectorRef,
  Component,
  DestroyRef,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import type { OnChanges, OnInit } from '@angular/core';
import { TuiButton } from '@taiga-ui/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { TuiInputFiles, TuiInputFilesDirective } from '@taiga-ui/kit/components/files';
import {
  CancelledError,
  MutationObserver,
  QueryClient,
  QueryObserver,
} from '@tanstack/angular-query-experimental';
import type { QueryCacheNotifyEvent } from '@tanstack/angular-query-experimental';
import type { Api } from '../../../api.generated';
import { ApiFailure, writeJson } from '../../../api-http';
import { ImageResource } from '../../image-resource';
import { trustedChatActor } from '../chats-session';
import { isTerminalOperation, messageProblem } from '../message-contract';
import type { TerminalMessageOperation } from '../message-contract';
import { imageSelectionProblem } from './image-contract';
import { PreparationImage } from './preparation-image';
import { absoluteChatTime } from '../chats-date';
import { preparationsOptions } from './image-queries';
import { sendImage } from './image-send';
import type { ImageSendIntent } from './image-send';

interface Cancellation {
  readonly send: ImageSendIntent;
  readonly key: string;
}

@Component({
  selector: 'app-chat-image-sender',
  imports: [
    TuiButton,
    ReactiveFormsModule,
    TuiInputFiles,
    TuiInputFilesDirective,
    PreparationImage,
  ],
  templateUrl: './image-sender.html',
  styleUrl: './image-sender.less',
})
export class ImageSender implements OnChanges, OnInit {
  public readonly actor = input.required<Api['schemas']['IdentityResponse']>();
  public readonly conversationId = input.required<string>();
  public readonly canSend = input.required<boolean>();
  public readonly stored = output();
  public readonly stateChange = output();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly lifetime = signal<object>({});
  private readonly mutationOwner: object = {};
  protected readonly file = new FormControl<Readonly<File> | null>({ value: null, disabled: true });
  // Immutable recovery selection is user intent, retaining only operation IDs.
  // A bounded collection may later evict the selected preparation.
  private readonly recovery = signal<Readonly<{
    readonly imageId: string;
    readonly clientMessageId: string;
  }> | null>(null);
  private readonly resource = new ImageResource();
  protected readonly preview = this.resource.url;
  protected readonly problem = signal<string | null>(null);
  protected readonly pickerId = `chat-image-${crypto.randomUUID()}`;
  protected readonly absoluteChatTime = absoluteChatTime;
  private readonly sendObserver = new MutationObserver(this.client, {
    mutationKey: ['chat-image-send'],
    meta: { chatImages: this.mutationOwner },
    retry: false,
    mutationFn: (intent: ImageSendIntent) =>
      sendImage(this.http, this.client, intent, (owner) => this.authority(owner)),
    onSuccess: (value: TerminalMessageOperation, intent: ImageSendIntent) => {
      this.settle(value, intent);
    },
    onError: (error: unknown, intent: ImageSendIntent) => {
      this.sessionError(error, intent);
    },
  });
  private readonly cancelObserver = new MutationObserver(this.client, {
    mutationKey: ['chat-image-cancel'],
    meta: { chatImages: this.mutationOwner },
    retry: false,
    mutationFn: (intent: Cancellation) => {
      const actor = this.authority(intent.send);
      return writeJson(
        this.http,
        `/api/v1/conversations/${encodeURIComponent(intent.send.conversationId)}/message-operations/${encodeURIComponent(intent.send.clientMessageId)}/cancel`,
        undefined,
        { 'x-csrf-token': actor.csrf_token, 'Idempotency-Key': intent.key },
        (value): value is TerminalMessageOperation =>
          isTerminalOperation(value) &&
          value.conversation_id === intent.send.conversationId &&
          value.client_message_id === intent.send.clientMessageId,
      );
    },
    onSuccess: (value: TerminalMessageOperation, intent: Cancellation) => {
      this.settle(value, intent.send);
    },
    onError: (error: unknown, intent: Cancellation) => {
      this.sessionError(error, intent.send);
    },
  });
  private readonly collection = new QueryObserver(
    this.client,
    preparationsOptions(this.http, this.client, null, '', false),
  );
  protected get preparations() {
    return this.collection.getCurrentResult();
  }
  protected get sending() {
    return this.sendObserver.getCurrentResult();
  }
  protected get cancelling() {
    return this.cancelObserver.getCurrentResult();
  }
  protected get selected() {
    return this.preparations.data?.preparations.find(
      (entry) => entry.image_id === this.recovery()?.imageId,
    );
  }
  public get hasSelection(): boolean {
    return this.file.value !== null || this.recovery() !== null || this.locked;
  }
  public get pending(): boolean {
    return this.sending.isPending || this.cancelling.isPending;
  }
  public get locked(): boolean {
    return (
      this.pending ||
      ((this.sending.isError || this.cancelling.isError) && !this.cancelling.isSuccess)
    );
  }
  protected get recovering(): boolean {
    return this.recovery() !== null;
  }
  protected get reselecting(): boolean {
    return (
      this.sending.isError &&
      this.sending.error instanceof ApiFailure &&
      this.sending.error.code === 'image_reselect_required'
    );
  }
  protected get permitted(): boolean {
    return this.canSend() && this.trusted;
  }
  protected get trusted(): boolean {
    return trustedChatActor(this.client, this.actor().account_id) !== null;
  }
  public ngOnInit(): void {
    this.file.valueChanges
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe((file: Readonly<File> | null) => {
        this.choose(file);
      });
    const send = this.sendObserver.subscribe(() => {
      this.notify();
    });
    const cancel = this.cancelObserver.subscribe(() => {
      this.notify();
    });
    const collection = this.collection.subscribe(() => {
      const error = this.preparations.error;
      if (
        this.trusted &&
        error instanceof ApiFailure &&
        (error.status === 401 || error.status === 403)
      ) {
        this.client.setQueryData(['session'], null);
        this.client.removeQueries({ queryKey: ['account', this.actor().account_id] });
        void this.client.invalidateQueries({ queryKey: ['session'] });
      }
      this.notify();
    });
    const session = this.client
      .getQueryCache()
      .subscribe((event: Readonly<QueryCacheNotifyEvent>) => {
        const key: unknown = event.query.queryKey;
        if (!Array.isArray(key) || key[0] !== 'session') return;
        const identity = this.client.getQueryData<Api['schemas']['IdentityResponse'] | null>([
          'session',
        ]);
        if (
          identity?.account_id !== this.actor().account_id ||
          !identity.capabilities.can_use_student_features
        )
          this.retire();
        this.configure();
      });
    this.destroy.onDestroy(() => {
      send();
      cancel();
      collection();
      session();
      this.retire();
      this.collection.destroy();
      for (const mutation of this.client.getMutationCache().getAll()) {
        if (mutation.options.meta?.['chatImages'] === this.mutationOwner)
          this.client.getMutationCache().remove(mutation);
      }
    });
  }
  public ngOnChanges(): void {
    const key = this.collection.options.queryKey;
    if (key[1] !== this.actor().account_id || key[3] !== this.conversationId()) this.retire();
    if (!this.canSend()) this.sending.variables?.controller.abort();
    this.configure();
  }
  private configure(): void {
    this.configureFileControl();
    this.collection.setOptions(
      preparationsOptions(
        this.http,
        this.client,
        this.actor().account_id,
        this.conversationId(),
        trustedChatActor(this.client, this.actor().account_id) !== null,
      ),
    );
  }
  private notify(): void {
    if (this.destroy.destroyed) return;
    this.configureFileControl();
    this.change.markForCheck();
    this.stateChange.emit();
  }
  private retire(): void {
    this.sending.variables?.controller.abort();
    this.lifetime.set({});
    this.file.reset(null, { emitEvent: false });
    this.recovery.set(null);
    this.resource.clear();
    this.problem.set(null);
    this.sendObserver.reset();
    this.cancelObserver.reset();
  }
  private owns(intent: ImageSendIntent): boolean {
    return (
      intent.lifetime === this.lifetime() &&
      intent.actorId === this.actor().account_id &&
      intent.conversationId === this.conversationId()
    );
  }
  private authority(intent: ImageSendIntent): Api['schemas']['IdentityResponse'] {
    const actor = trustedChatActor(this.client, intent.actorId);
    if (!this.owns(intent) || actor === null) throw new CancelledError();
    return actor;
  }
  private sessionError(error: unknown, intent: ImageSendIntent): void {
    if (
      !this.owns(intent) ||
      !(error instanceof ApiFailure) ||
      (error.status !== 401 && error.status !== 403)
    )
      return;
    this.client.setQueryData(['session'], null);
    this.client.removeQueries({ queryKey: ['account', intent.actorId] });
    void this.client.invalidateQueries({ queryKey: ['session'] });
  }
  private settle(value: TerminalMessageOperation, intent: ImageSendIntent): void {
    if (!this.owns(intent)) return;
    intent.controller.abort();
    this.lifetime.set({});
    this.file.reset(null, { emitEvent: false });
    this.recovery.set(null);
    this.resource.clear();
    void this.client.invalidateQueries({
      queryKey: ['account', intent.actorId, 'chats', intent.conversationId],
    });
    void this.client.invalidateQueries({ queryKey: ['account', intent.actorId, 'chats', 'list'] });
    if (
      'message' in value &&
      value.message.image_id !== null &&
      (intent.imageId === null || value.message.image_id === intent.imageId)
    )
      this.stored.emit();
    this.notify();
  }
  private configureFileControl(): void {
    const disabled = (this.locked && !this.reselecting) || !this.permitted;
    if (disabled && this.file.enabled) this.file.disable({ emitEvent: false });
    if (!disabled && this.file.disabled) this.file.enable({ emitEvent: false });
  }
  private choose(file: Readonly<File> | null): void {
    if (file === null) return;
    if ((this.locked && !this.reselecting) || !this.permitted) {
      this.file.reset(null, { emitEvent: false });
      return;
    }
    if (this.selected !== undefined && this.selected.state !== 'uploading') {
      this.file.reset(null, { emitEvent: false });
      this.problem.set('Resolve this preparation before choosing a different image.');
      return;
    }
    const problem = imageSelectionProblem(file);
    this.problem.set(problem);
    if (problem !== null) {
      this.resource.clear();
    } else this.resource.replace(file);
    this.notify();
  }
  protected rejected(files: readonly File[]): void {
    const file = this.file.value;
    if (file === null || !files.includes(file)) return;
    this.problem.set(imageSelectionProblem(file));
    this.resource.clear();
    this.notify();
  }
  protected remove(): void {
    if (this.locked) return;
    if (this.recovery() !== null) {
      this.cancelRecovered();
      return;
    }
    this.file.reset(null, { emitEvent: false });
    this.recovery.set(null);
    this.resource.clear();
    this.problem.set(null);
    this.notify();
  }
  protected recover(imageId: string): void {
    if (this.locked || !this.permitted) return;
    const value = this.preparations.data?.preparations.find((entry) => entry.image_id === imageId);
    if (
      value?.message_outcome !== null ||
      (value.state !== 'uploading' &&
        value.state !== 'queued' &&
        value.state !== 'processing' &&
        value.state !== 'ready')
    )
      return;
    this.file.reset(null, { emitEvent: false });
    this.resource.clear();
    this.problem.set(null);
    this.recovery.set({ imageId, clientMessageId: value.client_message_id });
    this.notify();
  }
  public requestSend(caption: string): void {
    if (!this.permitted || this.locked || !this.hasSelection) return;
    const file = this.file.value;
    const fileProblem = file === null ? null : imageSelectionProblem(file);
    if (fileProblem !== null) {
      this.problem.set(fileProblem);
      return;
    }
    const problem = caption.trim().length === 0 ? null : messageProblem(caption);
    this.problem.set(problem);
    if (problem !== null) return;
    const selected = this.selected;
    if (selected?.state === 'uploading' && this.file.value === null) {
      this.problem.set('Reselect the original image to resume this upload.');
      return;
    }
    const intent: ImageSendIntent = {
      actorId: this.actor().account_id,
      conversationId: this.conversationId(),
      lifetime: this.lifetime(),
      controller: new AbortController(),
      file: this.file.value,
      imageId: this.recovery()?.imageId ?? null,
      clientMessageId: this.recovery()?.clientMessageId ?? crypto.randomUUID(),
      caption,
      startKey: crypto.randomUUID(),
      finalizeKey: crypto.randomUUID(),
      sendKey: crypto.randomUUID(),
    };
    this.cancelObserver.reset();
    void this.sendObserver.mutate(intent).catch(() => undefined);
  }
  protected retry(): void {
    const intent = this.sending.variables;
    if (!this.permitted || !this.sending.isError || this.pending || intent === undefined) return;
    void this.sendObserver
      .mutate({
        ...intent,
        controller: intent.controller.signal.aborted ? new AbortController() : intent.controller,
        file: this.reselecting ? this.file.value : intent.file,
      })
      .catch(() => undefined);
  }
  protected cancel(): void {
    const send = this.sending.variables ?? this.cancelling.variables?.send;
    if (
      !this.trusted ||
      send === undefined ||
      this.cancelling.isPending ||
      this.cancelling.isSuccess
    )
      return;
    send.controller.abort();
    const intent = this.cancelling.variables ?? { send, key: crypto.randomUUID() };
    void this.cancelObserver.mutate(intent).catch(() => undefined);
  }
  private cancelRecovered(): void {
    const selected = this.recovery();
    if (selected === null || !this.trusted) return;
    const send: ImageSendIntent = {
      actorId: this.actor().account_id,
      conversationId: this.conversationId(),
      lifetime: this.lifetime(),
      controller: new AbortController(),
      file: null,
      imageId: selected.imageId,
      clientMessageId: selected.clientMessageId,
      caption: '',
      startKey: crypto.randomUUID(),
      finalizeKey: crypto.randomUUID(),
      sendKey: crypto.randomUUID(),
    };
    void this.cancelObserver.mutate({ send, key: crypto.randomUUID() }).catch(() => undefined);
  }
  protected refresh(): void {
    if (!this.permitted) return;
    void this.collection.refetch();
  }
  protected previewDenied(): void {
    if (!this.trusted) return;
    this.client.setQueryData(['session'], null);
    this.client.removeQueries({ queryKey: ['account', this.actor().account_id] });
    void this.client.invalidateQueries({ queryKey: ['session'] });
  }
}
