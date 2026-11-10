import { trustedChatActor } from './chats-session';
import { ImageSender } from './images/image-sender';
import { HttpClient } from '@angular/common/http';
import {
  afterNextRender,
  ChangeDetectorRef,
  Component,
  DestroyRef,
  inject,
  Injector,
  input,
  signal,
  viewChild,
} from '@angular/core';
import type { OnChanges, OnInit, SimpleChanges } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import type { AbstractControl, ValidationErrors } from '@angular/forms';
import { TuiButton, TuiError, TuiTextfield } from '@taiga-ui/core';
import { TuiAutoFocus } from '@taiga-ui/cdk';
import { TuiTextarea } from '@taiga-ui/kit/components/textarea';
import {
  CancelledError,
  MutationObserver,
  QueryClient,
  QueryObserver,
} from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { ApiFailure, writeJson } from '../../api-http';
import { isUncertain } from '../uncertain';
import {
  isTerminalOperation,
  messageProblem,
  messageValidator,
  operationOptions,
} from './message-contract';
import type { MessageOperation, TerminalMessageOperation } from './message-contract';

// An empty unsent draft is allowed; a send command still requires valid content.
function draftValidator(control: Readonly<AbstractControl<string>>): ValidationErrors | null {
  return control.value === '' ? null : messageValidator(control);
}

interface SendIntent {
  readonly actorId: string;
  readonly conversationId: string;
  readonly lifetime: object;
  readonly key: string;
  readonly body: Api['schemas']['SendMessageBody'];
}
interface CancelIntent {
  readonly send: SendIntent;
  readonly key: string;
}

@Component({
  selector: 'app-chat-message-composer',
  imports: [
    ReactiveFormsModule,
    TuiButton,
    TuiError,
    TuiTextfield,
    TuiTextarea,
    TuiAutoFocus,
    ImageSender,
  ],
  templateUrl: './message-composer.html',
  styles:
    ':host { display: block; min-inline-size: 0; } form { display: grid; grid-template-columns: minmax(0, 1fr); gap: .5rem; }',
})
export class MessageComposer implements OnChanges, OnInit {
  public readonly actor = input.required<Api['schemas']['IdentityResponse']>();
  public readonly conversationId = input.required<string>();
  public readonly canSend = input.required<boolean>();
  private readonly http = inject(HttpClient);
  private readonly injector = inject(Injector);
  private readonly textFocus = viewChild.required(TuiAutoFocus);
  private readonly imageSender = viewChild(ImageSender);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly lifetime = signal<object>({});
  private readonly mutationOwner: object = {};
  protected readonly messageProblem = messageProblem;
  protected readonly form = new FormGroup({
    text: new FormControl('', { nonNullable: true, validators: [draftValidator] }),
  });
  private readonly sendObserver = new MutationObserver(this.client, {
    mutationKey: ['chat-send'],
    meta: { chatComposer: this.mutationOwner },
    retry: false,
    mutationFn: (intent: SendIntent) =>
      writeJson(
        this.http,
        `/api/v1/conversations/${encodeURIComponent(intent.conversationId)}/messages`,
        intent.body,
        this.headers(intent, intent.key),
        (value): value is TerminalMessageOperation =>
          isTerminalOperation(value) &&
          value.conversation_id === intent.conversationId &&
          value.client_message_id === intent.body.client_message_id,
      ),
    onSuccess: (receipt: TerminalMessageOperation, intent: SendIntent) => {
      this.settle(receipt, intent);
    },
    onError: (error: unknown, intent: SendIntent) => {
      this.reauthorize(error, intent);
    },
  });
  private readonly cancelObserver = new MutationObserver(this.client, {
    mutationKey: ['chat-cancel'],
    meta: { chatComposer: this.mutationOwner },
    retry: false,
    mutationFn: (intent: CancelIntent) =>
      writeJson(
        this.http,
        `/api/v1/conversations/${encodeURIComponent(intent.send.conversationId)}/message-operations/${encodeURIComponent(intent.send.body.client_message_id)}/cancel`,
        undefined,
        this.headers(intent.send, intent.key),
        (value): value is TerminalMessageOperation =>
          isTerminalOperation(value) &&
          value.conversation_id === intent.send.conversationId &&
          value.client_message_id === intent.send.body.client_message_id,
      ),
    onSuccess: (receipt: TerminalMessageOperation, intent: CancelIntent) => {
      this.settle(receipt, intent.send);
    },
    onError: (error: unknown, intent: CancelIntent) => {
      this.reauthorize(error, intent.send);
    },
  });
  private readonly lookupObserver = new QueryObserver(
    this.client,
    operationOptions(this.http, null, '', null),
  );
  protected get send() {
    return this.sendObserver.getCurrentResult();
  }
  protected get cancel() {
    return this.cancelObserver.getCurrentResult();
  }
  protected get lookup() {
    return this.lookupObserver.getCurrentResult();
  }
  protected get pending(): boolean {
    return this.send.isPending || this.cancel.isPending || this.lookup.isFetching;
  }
  protected get terminal(): MessageOperation | undefined {
    return this.send.isSuccess ? this.send.data : (this.cancel.data ?? this.lookup.data);
  }
  protected get unknown(): boolean {
    return (
      (isUncertain(this.send.error) ||
        (this.send.error instanceof ApiFailure && this.send.error.status === 409)) &&
      (this.terminal === undefined || !('operation_id' in this.terminal))
    );
  }
  protected get locked(): boolean {
    return (
      this.pending ||
      this.unknown ||
      this.imageSender()?.locked === true ||
      !this.trusted() ||
      !this.canSend()
    );
  }
  protected get count(): number {
    return Array.from(this.form.controls.text.value).length;
  }
  protected get errorText(): string {
    const error = this.cancel.error ?? this.lookup.error ?? this.send.error;
    if (this.unknown)
      return 'We couldn’t confirm whether this message was stored. Check its status, retry the same message or cancel this intent.';
    if (error instanceof ApiFailure) {
      if (error.status === 403 || error.status === 404)
        return 'Sending is unavailable. Your text is still here.';
      if (error.status === 409)
        return 'This operation changed. Check its status before sending again.';
      if (error.status === 422) return 'The message could not be accepted. Review your text.';
    }
    return 'We couldn’t complete this action. Your text is still here.';
  }
  public ngOnInit(): void {
    const send = this.sendObserver.subscribe(() => {
      this.change.markForCheck();
    });
    const cancel = this.cancelObserver.subscribe(() => {
      this.change.markForCheck();
    });
    const lookup = this.lookupObserver.subscribe(() => {
      this.change.markForCheck();
    });
    const cache = this.client.getQueryCache().subscribe(() => {
      const identity = this.client.getQueryData<Api['schemas']['IdentityResponse'] | null>([
        'session',
      ]);
      if (identity?.account_id !== this.actor().account_id) this.reset();
      this.change.markForCheck();
    });
    this.destroy.onDestroy(() => {
      send();
      cancel();
      lookup();
      cache();
      this.lookupObserver.destroy();
      this.reset();
    });
  }
  public ngOnChanges(changes: Readonly<SimpleChanges>): void {
    const previousActor: unknown = changes['actor']?.previousValue;
    const previousConversation: unknown = changes['conversationId']?.previousValue;
    if (
      (previousConversation !== undefined && previousConversation !== this.conversationId()) ||
      (typeof previousActor === 'object' &&
        previousActor !== null &&
        'account_id' in previousActor &&
        previousActor.account_id !== this.actor().account_id)
    )
      this.reset();
  }
  private trusted(): boolean {
    return trustedChatActor(this.client, this.actor().account_id) !== null;
  }

  private owns(intent: SendIntent): boolean {
    return (
      !this.destroy.destroyed &&
      intent.lifetime === this.lifetime() &&
      intent.actorId === this.actor().account_id &&
      intent.conversationId === this.conversationId()
    );
  }
  private current(intent: SendIntent): boolean {
    return this.owns(intent) && this.trusted();
  }
  private headers(intent: SendIntent, key: string): Readonly<Record<string, string>> {
    const identity = this.client.getQueryData<Api['schemas']['IdentityResponse'] | null>([
      'session',
    ]);
    if (!this.current(intent) || identity === undefined || identity === null)
      throw new CancelledError();
    return { 'X-CSRF-Token': identity.csrf_token, 'Idempotency-Key': key };
  }
  private settle(receipt: MessageOperation, intent: SendIntent): void {
    if (!this.owns(intent) || !('operation_id' in receipt)) return;
    const identity = this.client.getQueryData<Api['schemas']['IdentityResponse'] | null>([
      'session',
    ]);
    if (identity?.account_id !== intent.actorId) return;
    if ('message' in receipt) this.form.reset();
    if (this.current(intent))
      void this.client.invalidateQueries({ queryKey: ['account', intent.actorId, 'chats'] });
  }
  private reauthorize(error: unknown, intent: SendIntent): void {
    if (!(error instanceof ApiFailure) || error.status !== 401 || !this.current(intent)) return;
    this.client.setQueryData(['session'], null);
    this.client.removeQueries({ queryKey: ['account'] });
    void this.client.invalidateQueries({ queryKey: ['session'] });
  }
  private reset(): void {
    this.lifetime.set({});
    this.form.reset();
    this.sendObserver.reset();
    this.cancelObserver.reset();
    for (const mutation of this.client.getMutationCache().getAll())
      if (mutation.options.meta?.['chatComposer'] === this.mutationOwner)
        this.client.getMutationCache().remove(mutation);
  }
  protected submit(): void {
    if (this.locked) return;
    const images = this.imageSender();
    if (images?.hasSelection === true) {
      images.requestSend(this.form.controls.text.value);
      return;
    }
    const problem = messageProblem(this.form.controls.text.value);
    if (problem !== null) this.form.controls.text.setErrors({ message: problem });
    this.form.markAllAsTouched();
    if (this.form.invalid) {
      const lifetime = this.lifetime();
      afterNextRender(
        () => {
          if (lifetime === this.lifetime() && !this.locked) this.textFocus().focus();
        },
        { injector: this.injector },
      );
      return;
    }
    const previous = this.send.variables;
    const body = this.form.getRawValue();
    const intent: SendIntent =
      previous !== undefined &&
      this.send.isError &&
      (this.terminal === undefined || !('operation_id' in this.terminal)) &&
      previous.body.text === body.text &&
      this.current(previous)
        ? previous
        : {
            actorId: this.actor().account_id,
            conversationId: this.conversationId(),
            lifetime: this.lifetime(),
            key: crypto.randomUUID(),
            body: { client_message_id: crypto.randomUUID(), text: body.text },
          };
    this.cancelObserver.reset();
    this.lookupObserver.setOptions(
      operationOptions(
        this.http,
        intent.actorId,
        intent.conversationId,
        intent.body.client_message_id,
      ),
    );
    void this.sendObserver.mutate(intent).catch(() => undefined);
  }
  protected imageStateChanged(): void {
    this.change.markForCheck();
  }
  protected imageStored(): void {
    const identity = this.client.getQueryData<Api['schemas']['IdentityResponse'] | null>([
      'session',
    ]);
    // The child emits only for its owned confirmed receipt. Retiring that draft
    // is not a new command and must not wait for same-actor revalidation.
    if (!this.destroy.destroyed && identity?.account_id === this.actor().account_id) this.reset();
  }
  protected retry(): void {
    const intent = this.send.variables;
    if (
      !this.unknown ||
      this.pending ||
      intent === undefined ||
      !this.current(intent) ||
      !this.canSend()
    )
      return;
    void this.sendObserver.mutate(intent).catch(() => undefined);
  }
  protected async check(): Promise<void> {
    const intent = this.send.variables;
    if (this.pending || intent === undefined || !this.current(intent)) return;
    this.lookupObserver.setOptions(
      operationOptions(
        this.http,
        intent.actorId,
        intent.conversationId,
        intent.body.client_message_id,
      ),
    );
    const result = await this.lookupObserver.refetch();
    if (result.data !== undefined) this.settle(result.data, intent);
    if (result.isError) this.reauthorize(result.error, intent);
  }
  protected cancelIntent(): void {
    const send = this.send.variables;
    if (this.pending || send === undefined || !this.current(send)) return;
    const previous = this.cancel.variables;
    const intent = previous?.send === send ? previous : { send, key: crypto.randomUUID() };
    void this.cancelObserver.mutate(intent).catch(() => undefined);
  }
}
