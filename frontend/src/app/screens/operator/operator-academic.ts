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
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';
import { QueryClient, QueryObserver } from '@tanstack/angular-query-experimental';
import { TuiButton, TuiInput, TuiTextfield } from '@taiga-ui/core';
import { TuiNativeSelect } from '@taiga-ui/kit/components/select';
import { ApiFailure } from '../../api-http';
import { goalsOptions, goalHistoryOptions, helpHistoryOptions } from './operator-academic-contract';
import { academicRoute } from './operator-academic-route';

@Component({
  selector: 'app-operator-academic',
  imports: [ReactiveFormsModule, TuiButton, TuiInput, TuiTextfield, TuiNativeSelect],
  templateUrl: './operator-academic.html',
  styleUrl: './operator-academic.less',
})
export class OperatorAcademic {
  public readonly actorId = input.required<string>();
  public readonly accountId = input.required<string>();
  public readonly tab = input.required<'goals' | 'help'>();
  public readonly authorityFailure = output<{
    readonly error: unknown;
    readonly actorId: string | null;
  }>();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly params = toSignal(this.route.queryParamMap, {
    initialValue: this.route.snapshot.queryParamMap,
  });
  protected readonly state = computed(() => academicRoute(this.params(), this.tab()));
  protected readonly states = ['all', 'active', 'completed'] as const;
  protected readonly form = new FormGroup({
    state: new FormControl<string | null>('all'),
    created_from: new FormControl('', { nonNullable: true }),
    created_before: new FormControl('', { nonNullable: true }),
  });
  private readonly submitted = signal(false);
  private readonly goalsQuery = new QueryObserver(
    this.client,
    goalsOptions(this.http, null, null, {}, false),
  );
  private readonly historyQuery = new QueryObserver(
    this.client,
    goalHistoryOptions(this.http, null, null, null, null, false),
  );
  private readonly helpQuery = new QueryObserver(
    this.client,
    helpHistoryOptions(this.http, null, null, null, false),
  );
  protected get goals() {
    return this.goalsQuery.getCurrentResult();
  }
  protected get history() {
    return this.historyQuery.getCurrentResult();
  }
  protected get help() {
    return this.helpQuery.getCurrentResult();
  }
  protected get formError(): string | null {
    return this.submitted() ? academicRoute(convertToParamMap(this.draft()), 'goals').error : null;
  }
  protected get rootsPaged(): boolean {
    return this.params().has('goals_cursor');
  }
  protected get historyPaged(): boolean {
    return this.params().has('goal_cursor');
  }
  protected get helpPaged(): boolean {
    return this.params().has('help_cursor');
  }
  public constructor() {
    const goals = this.goalsQuery.subscribe(() => {
      this.report(this.goals.error, this.goalsQuery.options.queryKey[1]);
      this.change.markForCheck();
    });
    const history = this.historyQuery.subscribe(() => {
      this.report(this.history.error, this.historyQuery.options.queryKey[1]);
      this.change.markForCheck();
    });
    const help = this.helpQuery.subscribe(() => {
      this.report(this.help.error, this.helpQuery.options.queryKey[1]);
      this.change.markForCheck();
    });
    effect((cleanup) => {
      const actor = this.actorId();
      const account = this.accountId();
      this.tab();
      cleanup(() => {
        void this.client.cancelQueries({
          queryKey: ['account', actor, 'operator', 'academic', account],
        });
      });
    });
    effect(() => {
      const actor = this.actorId();
      const account = this.accountId();
      const state = this.state();
      this.form.setValue({
        state: state.filters.state ?? 'all',
        created_from: state.filters.created_from ?? '',
        created_before: state.filters.created_before ?? '',
      });
      this.submitted.set(false);
      this.goalsQuery.setOptions(
        goalsOptions(
          this.http,
          actor,
          account,
          state.filters,
          this.tab() === 'goals' && state.error === null,
        ),
      );
      this.historyQuery.setOptions(
        goalHistoryOptions(
          this.http,
          actor,
          account,
          state.goalId,
          state.goalCursor,
          this.tab() === 'goals' && state.error === null,
        ),
      );
      this.helpQuery.setOptions(
        helpHistoryOptions(
          this.http,
          actor,
          account,
          state.helpCursor,
          this.tab() === 'help' && state.error === null,
        ),
      );
    });
    this.destroy.onDestroy(() => {
      goals();
      history();
      help();
      this.goalsQuery.destroy();
      this.historyQuery.destroy();
      this.helpQuery.destroy();
      this.form.reset();
    });
  }
  private report(error: unknown, actorId: unknown): void {
    if (
      typeof actorId === 'string' &&
      error instanceof ApiFailure &&
      (error.status === 401 || error.status === 403)
    )
      this.authorityFailure.emit({ error, actorId });
  }
  private draft(): Readonly<Record<string, string>> {
    const value = this.form.getRawValue();
    return Object.fromEntries(
      Object.entries({
        goal_state: value.state === 'all' || value.state === null ? '' : value.state,
        goal_created_from: value.created_from,
        goal_created_before: value.created_before,
      }).filter(([, value]: readonly [string, string]) => value !== ''),
    );
  }
  protected apply(): void {
    this.submitted.set(true);
    if (this.formError !== null) return;
    this.navigate({
      goal_state: null,
      goal_created_from: null,
      goal_created_before: null,
      ...this.draft(),
      goals_cursor: null,
      goal: null,
      goal_cursor: null,
    });
  }
  protected reset(): void {
    this.navigate({
      goal_state: null,
      goal_created_from: null,
      goal_created_before: null,
      goals_cursor: null,
      goal: null,
      goal_cursor: null,
      help_cursor: null,
    });
  }
  protected openGoal(id: string): void {
    this.navigate({ goal: id, goal_cursor: null });
  }
  protected closeGoal(): void {
    this.navigate({ goal: null, goal_cursor: null });
  }
  protected page(
    kind: 'goals_cursor' | 'goal_cursor' | 'help_cursor',
    cursor: string | null,
  ): void {
    this.navigate(
      kind === 'goals_cursor'
        ? { goals_cursor: cursor, goal: null, goal_cursor: null }
        : { [kind]: cursor },
    );
  }
  protected refresh(kind: 'goals' | 'history' | 'help'): void {
    if (kind === 'goals') {
      if (this.rootsPaged) this.page('goals_cursor', null);
      else void this.goalsQuery.refetch();
    } else if (kind === 'history') {
      if (this.historyPaged) this.page('goal_cursor', null);
      else void this.historyQuery.refetch();
    } else {
      if (this.helpPaged) this.page('help_cursor', null);
      else void this.helpQuery.refetch();
    }
  }
  protected errorText(error: unknown): string {
    if (error instanceof ApiFailure && error.status === 404)
      return 'This academic record is unavailable.';
    if (error instanceof ApiFailure && error.status === 422)
      return 'These filters or this cursor could not be used. Check filters or return to the first page.';
    return 'The records could not be loaded. Try again.';
  }
  protected cursorError(error: unknown): boolean {
    return error instanceof ApiFailure && error.status === 422;
  }
  private navigate(params: Readonly<Record<string, string | null>>): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: params,
      queryParamsHandling: 'merge',
    });
  }
}
