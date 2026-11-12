import { Mascot } from '../mascot';
import { StudentLayout } from '../student-layout';
import { DOCUMENT } from '@angular/common';
import { StudyProgress } from './study/study-progress';
import { absoluteChatTime, chatTime } from './chats-date';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectorRef,
  Component,
  DestroyRef,
  Injector,
  afterNextRender,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { TuiAutoFocus } from '@taiga-ui/cdk';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TuiButton, TuiCell, TuiLink, TuiTitle } from '@taiga-ui/core';
import { TuiAvatar } from '@taiga-ui/kit/components/avatar';
import { TuiBadgeNotification } from '@taiga-ui/kit/components/badge-notification';
import { TuiAccordion } from '@taiga-ui/kit/components/accordion';
import { TuiAppBar, TuiBlockStatus } from '@taiga-ui/layout';
import { QueryClient, QueryObserver } from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { ApiFailure } from '../../api-http';
import { sessionOptions } from '../session';
import { MessageComposer } from './message-composer';
import { ChatAvatar } from './chat-avatar';
import { ConfirmedMessage } from './confirmed-message';
import { GoalSharing } from './goal-sharing';
import {
  contextSubject,
  detailsOptions,
  historyOptions,
  listOptions,
  peerName,
  orderedMessages,
} from './chats-contract';

@Component({
  selector: 'app-chats',
  imports: [
    StudentLayout,
    Mascot,
    RouterLink,
    TuiButton,
    TuiLink,
    TuiCell,
    TuiTitle,
    TuiBadgeNotification,
    TuiAppBar,
    TuiBlockStatus,
    TuiAvatar,
    TuiAccordion,
    TuiAutoFocus,
    MessageComposer,
    ChatAvatar,
    ConfirmedMessage,
    GoalSharing,
    StudyProgress,
  ],
  templateUrl: './chats.html',
  styleUrl: './chats.less',
})
export class Chats {
  private readonly http = inject(HttpClient);
  private readonly document = inject(DOCUMENT);
  private readonly injector = inject(Injector);
  private readonly studyFocus = viewChild(TuiAutoFocus);
  // UI visit intent only: REST refreshes and history pagination do not create visits.
  private readonly studyEntry = signal<
    Readonly<{
      readonly conversationId: string | null;
      readonly actorId: string | null;
      readonly visit: Readonly<{ readonly id: string }> | null;
    }>
  >({ conversationId: null, actorId: null, visit: null });
  private readonly manualStudy = signal(0);
  protected readonly studyManualOpen = this.manualStudy.asReadonly();
  protected get studyVisit(): Readonly<{ readonly id: string }> | null {
    const entry = this.studyEntry();
    return this.document.visibilityState === 'visible' &&
      entry.actorId === this.actor?.account_id &&
      entry.conversationId === this.selectedId &&
      this.details.isSuccess &&
      !this.details.isFetching &&
      this.details.data.conversation_id === this.selectedId
      ? entry.visit
      : null;
  }
  protected openStudy(): void {
    if (
      this.actor === null ||
      !this.details.isSuccess ||
      this.details.isFetching ||
      this.details.data.conversation_id !== this.selectedId
    )
      return;
    this.manualStudy.update((value) => value + 1);
  }
  protected restoreStudyFocus(): void {
    const actor = this.actor?.account_id;
    const selected = this.selectedId;
    if (actor === undefined || selected === null || this.destroy.destroyed) return;
    afterNextRender(
      () => {
        if (
          this.actor?.account_id === actor &&
          this.selectedId === selected &&
          this.details.isSuccess &&
          !this.details.isFetching &&
          this.details.data.conversation_id === selected
        )
          this.studyFocus()?.focus();
      },
      { injector: this.injector },
    );
  }
  protected studyFailure(error: Readonly<ApiFailure>): void {
    this.studyEntry.update((entry) => ({ ...entry, visit: null }));
    this.reauthorize(error, this.owner?.account_id);
  }
  private bindStudyOwner(): void {
    const entry = this.studyEntry();
    const actorId = this.owner?.account_id ?? null;
    if (entry.actorId === null && actorId !== null && entry.visit !== null)
      this.studyEntry.set({ ...entry, actorId });
    else if (entry.actorId !== null && actorId !== entry.actorId) {
      this.studyEntry.set({ ...entry, visit: null });
      this.manualStudy.set(0);
    }
  }
  private enterStudyConversation(): void {
    const conversationId = this.selectedId;
    if (conversationId === this.studyEntry().conversationId) return;
    this.manualStudy.set(0);
    this.studyEntry.set({
      conversationId,
      actorId: this.owner?.account_id ?? null,
      visit:
        conversationId !== null && /^[0-9a-f-]{36}$/.test(conversationId)
          ? { id: crypto.randomUUID() }
          : null,
    });
  }
  private readonly clock = signal(Date.now());
  protected readonly absoluteChatTime = absoluteChatTime;
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly route = inject(ActivatedRoute);
  private readonly sessionQuery = new QueryObserver(
    this.client,
    sessionOptions(this.http, this.client),
  );
  private readonly listQuery = new QueryObserver(
    this.client,
    listOptions(this.http, null, null, false),
  );
  private readonly detailsQuery = new QueryObserver(
    this.client,
    detailsOptions(this.http, null, null, false),
  );
  private readonly historyQuery = new QueryObserver(
    this.client,
    historyOptions(this.http, null, null, null, false),
  );
  protected readonly peerName = peerName;
  protected readonly contextSubject = contextSubject;
  protected get session() {
    return this.sessionQuery.getCurrentResult();
  }
  protected get list() {
    return this.listQuery.getCurrentResult();
  }
  protected get details() {
    return this.detailsQuery.getCurrentResult();
  }
  protected get history() {
    return this.historyQuery.getCurrentResult();
  }
  protected get selectedId(): string | null {
    return this.route.snapshot.queryParamMap.get('conversation');
  }
  protected get cursor(): string | null {
    return this.route.snapshot.queryParamMap.get('cursor');
  }
  protected get historyCursor(): string | null {
    return this.route.snapshot.queryParamMap.get('history_cursor');
  }
  protected get owner(): Api['schemas']['IdentityResponse'] | null {
    return this.session.isSuccess &&
      this.session.data?.capabilities.can_use_student_features === true
      ? this.session.data
      : null;
  }
  protected get actor(): Api['schemas']['IdentityResponse'] | null {
    return this.session.isSuccess &&
      !this.session.isFetching &&
      this.session.data?.capabilities.can_use_student_features === true
      ? this.session.data
      : null;
  }
  protected get messages(): readonly Api['schemas']['MessageResponse'][] {
    return orderedMessages(this.history.data?.messages ?? []);
  }
  protected get errorText(): string {
    const error = this.details.error ?? this.history.error ?? this.list.error;
    if (error instanceof ApiFailure) {
      if (error.status === 404) return 'This conversation is unavailable.';
      if (error.status === 403) return 'Chats are unavailable for your account right now.';
      if (error.status === 422)
        return 'This page has expired. Start from the latest conversations.';
    }
    return 'We couldn’t load chats. Please try again.';
  }
  public constructor() {
    const timer = setInterval(() => {
      this.clock.set(Date.now());
    }, 30_000);
    this.destroy.onDestroy(() => {
      clearInterval(timer);
    });
    const session = this.sessionQuery.subscribe(() => {
      this.bindStudyOwner();
      this.sync();
      this.change.markForCheck();
    });
    const list = this.listQuery.subscribe(() => {
      this.reauthorize(this.list.error, this.listQuery.options.queryKey[1]);
      this.change.markForCheck();
    });
    const details = this.detailsQuery.subscribe(() => {
      this.reauthorize(this.details.error, this.detailsQuery.options.queryKey[1]);
      this.change.markForCheck();
    });
    const history = this.historyQuery.subscribe(() => {
      this.reauthorize(this.history.error, this.historyQuery.options.queryKey[1]);
      this.change.markForCheck();
    });
    const route = this.route.queryParamMap.subscribe(() => {
      this.enterStudyConversation();
      this.sync();
      this.change.markForCheck();
    });
    const visibility = (): void => {
      this.change.markForCheck();
    };
    this.document.addEventListener('visibilitychange', visibility);
    this.destroy.onDestroy(() => {
      this.document.removeEventListener('visibilitychange', visibility);
      session();
      list();
      details();
      history();
      route.unsubscribe();
      this.sessionQuery.destroy();
      this.listQuery.destroy();
      this.detailsQuery.destroy();
      this.historyQuery.destroy();
    });
  }
  private sync(): void {
    const identity = this.session.data;
    const owner =
      identity?.capabilities.can_use_student_features === true ? identity.account_id : null;
    const enabled = this.actor !== null;
    this.listQuery.setOptions(listOptions(this.http, owner, this.cursor, enabled));
    this.detailsQuery.setOptions(detailsOptions(this.http, owner, this.selectedId, enabled));
    this.historyQuery.setOptions(
      historyOptions(this.http, owner, this.selectedId, this.historyCursor, enabled),
    );
  }
  private reauthorize(error: unknown, actorId: unknown): void {
    if (
      !(error instanceof ApiFailure) ||
      (error.status !== 401 && error.status !== 403) ||
      this.actor?.account_id !== actorId ||
      this.session.isFetching
    )
      return;
    this.studyEntry.update((entry) => ({ ...entry, visit: null }));
    this.manualStudy.set(0);
    this.client.setQueryData(['session'], null);
    this.client.removeQueries({ queryKey: ['account'] });
    void this.sessionQuery.refetch();
  }
  protected retry(): void {
    if (this.actor === null) return;
    void this.client.invalidateQueries({ queryKey: ['account', this.actor.account_id, 'chats'] });
  }
  protected retrySession(): void {
    void this.sessionQuery.refetch();
  }
  protected when(value: string): string {
    return chatTime(value, this.clock());
  }
}
