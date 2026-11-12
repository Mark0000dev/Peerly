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
import { ActivatedRoute, Router, RouterLink, convertToParamMap } from '@angular/router';
import { QueryClient, QueryObserver } from '@tanstack/angular-query-experimental';
import { TuiButton, TuiInput, TuiLink, TuiTextfield } from '@taiga-ui/core';
import { TuiNativeSelect } from '@taiga-ui/kit/components/select';
import { ApiFailure } from '../../api-http';
import { auditOptions, eventKinds, eventOptions, eventsOptions } from './operator-reports-contract';
import { eventFields, eventRoute } from './operator-reports-route';
import { OperatorOrigin } from './operator-origin';

@Component({
  selector: 'app-operator-investigation',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TuiButton,
    TuiInput,
    TuiLink,
    TuiTextfield,
    TuiNativeSelect,
    OperatorOrigin,
  ],
  templateUrl: './operator-investigation.html',
  styleUrl: './operator-reports.less',
})
export class OperatorInvestigation {
  public readonly actorId = input.required<string>();
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
  protected readonly state = computed(() => eventRoute(this.params()));
  protected readonly fields = eventFields;
  protected readonly kinds = ['all', ...eventKinds];
  private readonly submitted = signal(false);
  protected readonly form = new FormGroup({
    subject_account_id: new FormControl('', { nonNullable: true }),
    http_request_id: new FormControl('', { nonNullable: true }),
    action_id: new FormControl('', { nonNullable: true }),
    trace_id: new FormControl('', { nonNullable: true }),
    kind: new FormControl<string | null>('all'),
    occurred_from: new FormControl('', { nonNullable: true }),
    occurred_before: new FormControl('', { nonNullable: true }),
  });
  private readonly listQuery = new QueryObserver(
    this.client,
    eventsOptions(this.http, null, {}, false),
  );
  private readonly eventQuery = new QueryObserver(
    this.client,
    eventOptions(this.http, null, null, false),
  );
  private readonly auditQuery = new QueryObserver(
    this.client,
    auditOptions(this.http, null, null, false),
  );
  protected get events() {
    return this.listQuery.getCurrentResult();
  }
  protected get event() {
    return this.eventQuery.getCurrentResult();
  }
  protected get audit() {
    return this.auditQuery.getCurrentResult();
  }
  protected get auditLinked(): boolean {
    return (
      this.state().auditId !== null &&
      this.event.isSuccess &&
      this.event.fetchStatus === 'idle' &&
      this.event.data.sources.some(
        (source) => source.kind === 'operator_audit' && source.id === this.state().auditId,
      )
    );
  }
  protected get factRows() {
    return Object.entries(this.event.data?.facts ?? {}).filter(
      ([key, value]: readonly [string, unknown]) => key !== 'lifecycle_operation' || value !== null,
    );
  }
  protected get formError(): string | null {
    return this.submitted() ? eventRoute(convertToParamMap(this.draft())).error : null;
  }
  public constructor() {
    const list = this.listQuery.subscribe(() => {
      this.report(this.events.error, this.listQuery.options.queryKey[1]);
      this.change.markForCheck();
    });
    const event = this.eventQuery.subscribe(() => {
      this.report(this.event.error, this.eventQuery.options.queryKey[1]);
      this.syncAudit();
      this.change.markForCheck();
    });
    const audit = this.auditQuery.subscribe(() => {
      this.report(this.audit.error, this.auditQuery.options.queryKey[1]);
      this.change.markForCheck();
    });
    effect((cleanup) => {
      const actor = this.actorId();
      cleanup(() => {
        void this.client.cancelQueries({ queryKey: ['account', actor, 'operator', 'events'] });
        void this.client.cancelQueries({ queryKey: ['account', actor, 'operator', 'audits'] });
      });
    });
    effect(() => {
      const actor = this.actorId();
      const state = this.state();
      for (const field of eventFields)
        this.form.controls[field.key].setValue(state.filters[field.key] ?? '');
      this.form.controls.kind.setValue(state.filters.kind ?? 'all');
      this.submitted.set(false);
      this.listQuery.setOptions(
        eventsOptions(this.http, actor, state.filters, state.opened && state.error === null),
      );
      this.eventQuery.setOptions(
        eventOptions(this.http, actor, state.eventId, state.error === null),
      );
      this.syncAudit();
    });
    this.destroy.onDestroy(() => {
      list();
      event();
      audit();
      this.listQuery.destroy();
      this.eventQuery.destroy();
      this.auditQuery.destroy();
      this.form.reset();
    });
  }
  private syncAudit(): void {
    const state = this.state();
    const linked =
      this.eventQuery.options.queryKey[1] === this.actorId() &&
      this.eventQuery.options.queryKey[5] === state.eventId &&
      this.auditLinked;
    this.auditQuery.setOptions(
      auditOptions(this.http, this.actorId(), state.auditId, state.error === null && linked),
    );
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
        ...value,
        kind: value.kind === 'all' || value.kind === null ? '' : value.kind,
      })
        .filter(([, value]: readonly [string, string]) => value !== '')
        .map(([key, value]: readonly [string, string]) => [`event_${key}`, value]),
    );
  }
  protected search(): void {
    this.submitted.set(true);
    if (this.formError !== null) return;
    this.navigate({
      event_subject_account_id: null,
      event_http_request_id: null,
      event_action_id: null,
      event_trace_id: null,
      event_kind: null,
      event_occurred_from: null,
      event_occurred_before: null,
      ...this.draft(),
      timeline: '1',
      events_cursor: null,
      event: null,
      audit: null,
    });
  }
  protected navigate(params: Readonly<Record<string, string | null>>): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: params,
      queryParamsHandling: 'merge',
    });
  }
  protected retry(kind: 'list' | 'event' | 'audit'): void {
    if (kind === 'list') void this.listQuery.refetch();
    else if (kind === 'event') void this.eventQuery.refetch();
    else if (this.auditLinked) void this.auditQuery.refetch();
  }
  protected cursorError(error: unknown): boolean {
    return error instanceof ApiFailure && error.status === 422;
  }
  protected errorText(error: unknown): string {
    if (error instanceof ApiFailure && error.status === 404)
      return 'This stored investigation record is unavailable.';
    if (this.cursorError(error))
      return 'These filters or this cursor could not be used. Check filters or return to the first page.';
    return 'This investigation record could not be loaded. Try again.';
  }
}
