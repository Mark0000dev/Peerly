import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectorRef,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router } from '@angular/router';
import type { Query } from '@tanstack/angular-query-experimental';
import { QueryClient, QueryObserver } from '@tanstack/angular-query-experimental';
import { TuiButton } from '@taiga-ui/core';
import { ApiFailure } from '../../api-http';
import { profileHistoryOptions, profileHistoryRoute } from './operator-profile-history-contract';

@Component({
  selector: 'app-operator-profile-history',
  imports: [TuiButton],
  templateUrl: './operator-profile-history.html',
  styleUrl: './operator-profile-history.less',
})
export class OperatorProfileHistory {
  public readonly actorId = input.required<string>();
  public readonly accountId = input.required<string>();
  public readonly authorityFailure = output<{
    readonly error: unknown;
    readonly actorId: string;
  }>();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroy = inject(DestroyRef);
  private readonly change = inject(ChangeDetectorRef);
  private readonly resetting = signal(false);
  private readonly params = toSignal(this.route.queryParamMap, {
    initialValue: this.route.snapshot.queryParamMap,
  });
  protected readonly state = computed(() => profileHistoryRoute(this.params()));
  private readonly query = new QueryObserver(
    this.client,
    profileHistoryOptions(this.http, null, null, null, false),
  );
  protected get history() {
    return this.query.getCurrentResult();
  }
  public constructor() {
    const subscription = this.query.subscribe(() => {
      const error = this.history.error;
      const actor = this.query.options.queryKey[1];
      if (
        typeof actor === 'string' &&
        actor === this.actorId() &&
        error instanceof ApiFailure &&
        (error.status === 401 || error.status === 403)
      )
        this.authorityFailure.emit({ error, actorId: actor });
      this.change.markForCheck();
    });
    effect(() => {
      const actor = this.actorId();
      const account = this.accountId();
      const state = this.state();
      const priorActor = this.query.options.queryKey[1];
      const priorAccount = this.query.options.queryKey[4];
      if (
        state.cursor !== null &&
        ((typeof priorActor === 'string' && priorActor !== actor) ||
          (typeof priorAccount === 'string' && priorAccount !== account))
      )
        this.resetCursor();
      this.query.setOptions(
        profileHistoryOptions(
          this.http,
          actor,
          account,
          state.cursor,
          state.open && state.error === null && !this.resetting(),
        ),
      );
    });
    effect((cleanup) => {
      const actor = this.actorId();
      const account = this.accountId();
      cleanup(() => {
        const key = ['account', actor, 'operator', 'profile-history', account];
        this.retire(key);
      });
    });
    this.destroy.onDestroy(() => {
      subscription();
      this.query.destroy();
    });
  }
  private resetCursor(): void {
    if (this.resetting()) return;
    this.resetting.set(true);
    void this.router
      .navigate([], {
        relativeTo: this.route,
        queryParams: { profile_cursor: null },
        queryParamsHandling: 'merge',
      })
      .then(() => {
        if (!this.destroy.destroyed) this.resetting.set(false);
      });
  }
  private retire(key: readonly unknown[]): void {
    void this.client.cancelQueries({ queryKey: key });
    // A denied read is the shared authority boundary until explicit session recheck.
    // Destroying this view must not erase that boundary and restart sibling reads.
    this.client.removeQueries({
      queryKey: key,
      predicate: (query: Readonly<Query>) =>
        !(query.state.error instanceof ApiFailure && query.state.error.status === 403),
    });
  }
  protected navigate(open: boolean, cursor: string | null = null): void {
    if (this.resetting()) return;
    if (open && this.state().open && this.state().cursor === cursor) {
      this.retry();
      return;
    }
    if (!open) {
      this.resetting.set(true);
      this.query.setOptions(
        profileHistoryOptions(
          this.http,
          this.actorId(),
          this.accountId(),
          this.state().cursor,
          false,
        ),
      );
      this.retire(['account', this.actorId(), 'operator', 'profile-history', this.accountId()]);
    }
    void this.router
      .navigate([], {
        relativeTo: this.route,
        queryParams: { profile_history: open ? 'open' : null, profile_cursor: cursor },
        queryParamsHandling: 'merge',
      })
      .then(() => {
        if (!this.destroy.destroyed) this.resetting.set(false);
      });
  }
  protected retry(): void {
    if (!this.resetting() && this.state().open && this.state().error === null)
      void this.query.refetch();
  }
  protected cursorError(error: unknown): boolean {
    return error instanceof ApiFailure && error.status === 422;
  }
  protected errorText(error: unknown): string {
    if (error instanceof ApiFailure && error.status === 404)
      return 'This account profile history is unavailable.';
    if (this.cursorError(error))
      return 'This profile history cursor could not be used. Return to the first page.';
    return 'Profile history could not be loaded. Other account records stay available. Try again.';
  }
}
