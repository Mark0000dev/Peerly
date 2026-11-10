import { trustedChatActor } from './chats-session';
import { MessageImage } from './images/message-image';
import { absoluteChatTime, chatTime } from './chats-date';
import { DOCUMENT } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import type { ElementRef } from '@angular/core';
import {
  afterNextRender,
  ChangeDetectorRef,
  Component,
  DestroyRef,
  inject,
  input,
  signal,
  viewChild,
} from '@angular/core';
import { TuiAppearance, TuiButton } from '@taiga-ui/core';
import { TuiMessage } from '@taiga-ui/kit/components/message';
import {
  CancelledError,
  MutationObserver,
  QueryClient,
} from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { ApiFailure, writeJson } from '../../api-http';
import { isReadPosition, peerName } from './chats-contract';

interface ReadIntent {
  readonly actorId: string;
  readonly conversationId: string;
  readonly messageId: string;
  readonly sequence: number;
  readonly key: string;
}
@Component({
  selector: 'app-confirmed-chat-message',
  imports: [TuiAppearance, TuiButton, TuiMessage, MessageImage],
  template: `
    <article>
      <h3>{{ message().author_id === actor().account_id ? 'You' : peerName(peer()) }}</h3>
      @if (message().image_id === null) {
        <p
          tuiMessage
          [tuiAppearance]="message().author_id === actor().account_id ? 'primary' : 'neutral'"
        >
          <span #content class="message-text">{{ message().text }}</span>
        </p>
      } @else {
        <div
          tuiMessage
          [tuiAppearance]="message().author_id === actor().account_id ? 'primary' : 'neutral'"
        >
          <div #content>
            <app-chat-message-image
              [actorId]="actor().account_id"
              [message]="message()"
              [authorLabel]="message().author_id === actor().account_id ? 'You' : peerName(peer())"
            />
            @if (message().text !== null) {
              <p class="message-text">{{ message().text }}</p>
            }
          </div>
        </div>
      }
      <p>
        <time [attr.datetime]="message().sent_at" [title]="absoluteChatTime(message().sent_at)">{{
          when(message().sent_at)
        }}</time>
        · Stored
      </p>
      @if (message().sequence > readThrough()) {
        <button
          tuiButton
          size="s"
          type="button"
          aria-label="Mark read through this message"
          [disabled]="!visible() || !active() || operation.isPending"
          (click)="acknowledge()"
        >
          Mark read
        </button>
      }
      @if (operation.isPending) {
        <p role="status">Updating your read position…</p>
      }
      @if (operation.isError) {
        <p role="alert">
          We couldn’t confirm your read position. Retry marking this displayed message.
        </p>
      }
    </article>
  `,
  styles:
    ':host { display: block; min-inline-size: 0; } .message-text { white-space: pre-wrap; overflow-wrap: anywhere; }',
})
export class ConfirmedMessage {
  public readonly actor = input.required<Api['schemas']['IdentityResponse']>();
  public readonly peer = input.required<Api['schemas']['ChatParticipantResponse']>();
  public readonly message = input.required<Api['schemas']['MessageResponse']>();
  public readonly active = input.required<boolean>();
  public readonly readThrough = input.required<number>();
  private readonly http = inject(HttpClient);
  private readonly clock = signal(Date.now());
  protected readonly absoluteChatTime = absoluteChatTime;
  private readonly client = inject(QueryClient);
  private readonly destroy = inject(DestroyRef);
  private readonly change = inject(ChangeDetectorRef);
  private readonly document = inject(DOCUMENT);
  private readonly content = viewChild.required<ElementRef<HTMLElement>>('content');
  private readonly mutationOwner: object = {};
  protected readonly visible = signal(false);
  protected readonly peerName = peerName;
  private readonly observer = new MutationObserver(this.client, {
    mutationKey: ['chat-read-position'],
    meta: { chatReadOwner: this.mutationOwner },
    retry: false,
    mutationFn: (intent: ReadIntent) =>
      writeJson(
        this.http,
        `/api/v1/conversations/${encodeURIComponent(intent.conversationId)}/read-position`,
        { through_sequence: intent.sequence },
        this.headers(intent),
        (value): value is Api['schemas']['ConversationReadPositionResponse'] =>
          isReadPosition(value) &&
          value.conversation_id === intent.conversationId &&
          value.through_sequence >= intent.sequence,
        'PUT',
      ),
    onSuccess: (
      _receipt: Api['schemas']['ConversationReadPositionResponse'],
      intent: ReadIntent,
    ) => {
      if (this.current(intent))
        void this.client.invalidateQueries({ queryKey: ['account', intent.actorId, 'chats'] });
    },
    onError: (error: unknown, intent: ReadIntent) => {
      if (!(error instanceof ApiFailure) || error.status !== 401 || !this.current(intent)) return;
      this.client.setQueryData(['session'], null);
      this.client.removeQueries({ queryKey: ['account'] });
      void this.client.invalidateQueries({ queryKey: ['session'] });
    },
  });
  protected get operation() {
    return this.observer.getCurrentResult();
  }
  public constructor() {
    const timer = setInterval(() => {
      this.clock.set(Date.now());
    }, 30_000);
    this.destroy.onDestroy(() => {
      clearInterval(timer);
    });
    const mutation = this.observer.subscribe(() => {
      this.change.markForCheck();
    });
    afterNextRender(() => {
      const observer = new IntersectionObserver((entries: readonly IntersectionObserverEntry[]) => {
        this.visible.set(
          entries.some((entry) => entry.isIntersecting && entry.intersectionRatio > 0),
        );
      });
      observer.observe(this.content().nativeElement);
      this.destroy.onDestroy(() => {
        observer.disconnect();
      });
    });
    this.destroy.onDestroy(() => {
      mutation();
      this.observer.reset();
      for (const operation of this.client.getMutationCache().getAll())
        if (operation.options.meta?.['chatReadOwner'] === this.mutationOwner)
          this.client.getMutationCache().remove(operation);
    });
  }
  private current(intent: ReadIntent): boolean {
    return (
      !this.destroy.destroyed &&
      trustedChatActor(this.client, intent.actorId) !== null &&
      this.actor().account_id === intent.actorId &&
      this.message().conversation_id === intent.conversationId &&
      this.message().message_id === intent.messageId
    );
  }
  private headers(intent: ReadIntent): Readonly<Record<string, string>> {
    const identity = this.client.getQueryData<Api['schemas']['IdentityResponse'] | null>([
      'session',
    ]);
    if (!this.current(intent) || identity === undefined || identity === null)
      throw new CancelledError();
    return { 'X-CSRF-Token': identity.csrf_token, 'Idempotency-Key': intent.key };
  }
  protected acknowledge(): void {
    if (
      !this.active() ||
      !this.visible() ||
      this.document.visibilityState !== 'visible' ||
      this.operation.isPending ||
      this.message().sequence <= this.readThrough()
    )
      return;
    const message = this.message();
    const previous = this.operation.variables;
    const intent: ReadIntent =
      previous !== undefined && this.current(previous)
        ? previous
        : {
            actorId: this.actor().account_id,
            conversationId: message.conversation_id,
            messageId: message.message_id,
            sequence: message.sequence,
            key: crypto.randomUUID(),
          };
    if (!this.current(intent)) return;
    void this.observer.mutate(intent).catch(() => undefined);
  }
  protected when(value: string): string {
    return chatTime(value, this.clock());
  }
}
