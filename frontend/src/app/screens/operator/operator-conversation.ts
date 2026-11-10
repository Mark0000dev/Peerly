import { HttpClient } from '@angular/common/http';
import { ChangeDetectorRef, Component, DestroyRef, inject, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import type { Query } from '@tanstack/angular-query-experimental';
import { QueryClient, QueryObserver } from '@tanstack/angular-query-experimental';
import { TuiButton, TuiInput, TuiLink, TuiTextfield } from '@taiga-ui/core';
import { ApiFailure } from '../../api-http';
import { sessionOptions } from '../session';
import { uuid } from './operator-contract';
import { operatorDenied, retireOperatorFailure } from './operator-authority';
import { conversationRoute, operatorMessagesOptions } from './operator-conversation-contract';

@Component({
  selector: 'app-operator-conversation',
  imports: [ReactiveFormsModule, RouterLink, TuiButton, TuiInput, TuiLink, TuiTextfield],
  templateUrl: './operator-conversation.html',
  styleUrl: './operator-conversation.less',
})
export class OperatorConversation {
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly submitted = signal(false);
  private readonly resetting = signal(false);
  protected readonly form = new FormGroup({
    conversation: new FormControl('', { nonNullable: true }),
  });
  private readonly sessionQuery = new QueryObserver(
    this.client,
    sessionOptions(this.http, this.client),
  );
  private readonly messagesQuery = new QueryObserver(
    this.client,
    operatorMessagesOptions(this.http, null, null, null, false),
  );
  protected get session() {
    return this.sessionQuery.getCurrentResult();
  }
  protected get messages() {
    return this.messagesQuery.getCurrentResult();
  }
  private get ownerId(): string | null {
    return this.session.data?.account_id ?? null;
  }
  protected get actorId(): string | null {
    return this.session.isSuccess && this.session.fetchStatus === 'idle' && !this.resetting()
      ? this.ownerId
      : null;
  }
  protected get state() {
    return conversationRoute(this.route.snapshot.queryParamMap);
  }
  protected get denied(): boolean {
    return operatorDenied(this.client, this.ownerId);
  }
  protected get formError(): string | null {
    return this.submitted() && !uuid(this.form.controls.conversation.value)
      ? 'Conversation ID must be a UUID.'
      : null;
  }
  public constructor() {
    const session = this.sessionQuery.subscribe(() => {
      const previous = this.messagesQuery.options.queryKey[1];
      if (
        this.actorId !== null &&
        typeof previous === 'string' &&
        previous !== this.actorId &&
        this.state.cursor !== null
      )
        this.resetActorCursor();
      this.sync();
      this.change.markForCheck();
    });
    const messages = this.messagesQuery.subscribe(() => {
      retireOperatorFailure(
        this.client,
        this.messages.error,
        this.messagesQuery.options.queryKey[1],
        () => this.actorId,
        () => {
          this.sync();
        },
        () => {
          this.recheck();
        },
      );
      this.change.markForCheck();
    });
    const route = this.route.queryParamMap.subscribe((params) => {
      const previous = this.messagesQuery.options.queryKey[4];
      this.form.controls.conversation.setValue(params.get('conversation') ?? '');
      this.submitted.set(false);
      if (typeof previous === 'string' && previous !== this.state.id && this.state.cursor !== null)
        this.resetActorCursor();
      this.sync();
      this.change.markForCheck();
    });
    this.destroy.onDestroy(() => {
      session();
      messages();
      route.unsubscribe();
      this.sessionQuery.destroy();
      this.messagesQuery.destroy();
      const operator = (query: Readonly<Query>) =>
        query.queryKey[0] === 'account' && query.queryKey[2] === 'operator';
      void this.client.cancelQueries({ predicate: operator });
      this.client.removeQueries({ predicate: operator });
      this.form.reset();
    });
  }
  private sync(): void {
    this.messagesQuery.setOptions(
      operatorMessagesOptions(
        this.http,
        this.ownerId,
        this.state.id,
        this.state.cursor,
        this.actorId !== null && !this.denied && this.state.error === null,
      ),
    );
  }
  private resetActorCursor(): void {
    if (this.resetting()) return;
    this.resetting.set(true);
    void this.router
      .navigate([], {
        relativeTo: this.route,
        queryParams: { cursor: null },
        queryParamsHandling: 'merge',
      })
      .then(() => {
        if (this.destroy.destroyed) return;
        this.resetting.set(false);
        this.sync();
        this.change.markForCheck();
      });
  }
  protected open(): void {
    this.submitted.set(true);
    if (this.formError !== null || this.actorId === null || this.denied) return;
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { conversation: this.form.controls.conversation.value, cursor: null },
    });
  }
  protected page(cursor: string | null): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { cursor },
      queryParamsHandling: 'merge',
    });
  }
  protected retry(): void {
    if (this.actorId !== null && !this.denied) void this.messagesQuery.refetch();
  }
  protected recheck(): void {
    void this.sessionQuery.refetch();
  }
  protected cursorError(error: unknown): boolean {
    return error instanceof ApiFailure && error.status === 422;
  }
  protected errorText(error: unknown): string {
    if (error instanceof ApiFailure && error.status === 404)
      return 'This retained conversation is unavailable.';
    if (this.cursorError(error))
      return 'This page cursor could not be used. Return to the first page.';
    return 'Messages could not be loaded. The selected conversation is kept. Try again.';
  }
}
