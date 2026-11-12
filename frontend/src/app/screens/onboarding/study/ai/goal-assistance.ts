import { trustedVerifiedActor as trustedActor } from '../../../verified-actor';
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
import type { OnChanges } from '@angular/core';
import { TuiButton } from '@taiga-ui/core';
import {
  CancelledError,
  MutationObserver,
  QueryClient,
  QueryObserver,
} from '@tanstack/angular-query-experimental';
import type {
  Mutation,
  QueryCacheNotifyEvent,
  QueryObserverResult,
} from '@tanstack/angular-query-experimental';
import type { Api } from '../../../../api.generated';
import { ApiFailure, writeJson } from '../../../../api-http';
import { boundedWrite, jobKey, jobOptions, unknownAdmission } from './assistance-query';
import type { AssistanceIntent, JobReference } from './assistance-query';
import { acceptsJob, canClarify, canSuggest, sameDraft } from './goal-assistance-contract';
import type {
  ApplyGoalArea,
  ApplyGoalText,
  AssistanceExpired,
  GoalAssistanceDraft,
  GoalRequest,
} from './goal-assistance-contract';

interface Cancellation {
  readonly intent: AssistanceIntent;
  readonly reference: JobReference;
}

@Component({
  selector: 'peerly-goal-assistance',
  imports: [TuiButton],
  templateUrl: './goal-assistance.html',
  styleUrl: './goal-assistance.less',
})
export class GoalAssistance implements OnChanges {
  public readonly actor = input.required<Api['schemas']['IdentityResponse']>();
  public readonly draft = input.required<GoalAssistanceDraft>();
  public readonly applyDisabled = input(false);
  public readonly applyText = output<ApplyGoalText>();
  public readonly applyArea = output<ApplyGoalArea>();
  public readonly expired = output<AssistanceExpired>();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly lifetime = signal(new AbortController());
  private readonly retired = signal(false);
  private readonly intent = signal<AssistanceIntent | null>(null);
  private readonly reference = signal<JobReference | null>(null);
  private readonly mutationOwner: object = {};
  private readonly query = new QueryObserver(
    this.client,
    jobOptions(this.http, this.client, null, null, false),
  );
  private readonly admission = new MutationObserver(this.client, {
    mutationKey: ['goal-assistance-admit'],
    meta: { goalAssistance: this.mutationOwner },
    retry: false,
    mutationFn: (intent: AssistanceIntent) => {
      const actor = this.authority(intent);
      return boundedWrite(
        writeJson(
          this.http,
          '/api/v1/ai/jobs',
          intent.body,
          { 'x-csrf-token': actor.csrf_token, 'idempotency-key': intent.key },
          (value): value is Api['schemas']['JobResponse'] => acceptsJob(value, intent.body),
        ),
        intent.signal,
      );
    },
  });
  private readonly cancellation = new MutationObserver(this.client, {
    mutationKey: ['goal-assistance-cancel'],
    meta: { goalAssistance: this.mutationOwner },
    retry: false,
    mutationFn: async (operation: Cancellation) => {
      this.authority(operation.intent);
      await this.client.cancelQueries({
        queryKey: jobKey(operation.intent, operation.reference),
        exact: true,
      });
      const actor = this.authority(operation.intent);
      return boundedWrite(
        writeJson(
          this.http,
          `/api/v1/ai/jobs/${encodeURIComponent(operation.reference.id)}/cancel`,
          undefined,
          { 'x-csrf-token': actor.csrf_token },
          (value): value is Api['schemas']['JobResponse'] =>
            acceptsJob(value, operation.intent.body, operation.reference),
        ),
        operation.intent.signal,
      );
    },
  });
  protected get permitted(): boolean {
    return !this.retired() && trustedActor(this.client, this.actor().account_id) !== null;
  }
  protected get submitting(): boolean {
    return this.admission.getCurrentResult().isPending;
  }
  protected get cancelling(): boolean {
    return this.cancellation.getCurrentResult().isPending;
  }
  protected get active(): boolean {
    return this.intent() !== null;
  }
  protected get changed(): boolean {
    const intent = this.intent();
    return this.reference() !== null && intent !== null && !sameDraft(intent.draft, this.draft());
  }
  protected get job(): Api['schemas']['JobResponse'] | null {
    return this.query.getCurrentResult().data ?? null;
  }
  protected get admissionError(): unknown {
    return this.admission.getCurrentResult().error;
  }
  protected get uncertain(): boolean {
    return unknownAdmission(this.admissionError);
  }
  protected get readFailed(): boolean {
    return this.query.getCurrentResult().isError;
  }
  protected get checkingJob(): boolean {
    return (
      this.reference() !== null && this.job === null && this.query.getCurrentResult().isFetching
    );
  }
  protected get cancelFailed(): boolean {
    return this.cancellation.getCurrentResult().isError;
  }
  protected get mayClarify(): boolean {
    return this.permitted && canClarify(this.draft()) && !this.locked;
  }
  protected get maySuggest(): boolean {
    return this.permitted && canSuggest(this.draft()) && !this.locked;
  }
  protected get locked(): boolean {
    return this.submitting || this.cancelling || this.uncertain || this.reference() !== null;
  }
  protected get pendingJob(): boolean {
    return this.job?.state === 'queued' || this.job?.state === 'running';
  }
  protected get mayAskAgain(): boolean {
    const job = this.job;
    return (
      this.permitted &&
      !this.changed &&
      !this.cancelling &&
      !this.cancelFailed &&
      !this.readFailed &&
      job !== null &&
      (job.state === 'failed' || job.state === 'expired' || job.state === 'cancelled')
    );
  }
  protected get pollingStopped(): boolean {
    const job = this.job;
    return job !== null && this.pendingJob && Date.now() >= Date.parse(job.deadline);
  }
  protected get suggestion(): string | null {
    const job = this.job;
    return job?.state === 'succeeded' && job.result !== null && 'suggestion' in job.result
      ? job.result.suggestion
      : null;
  }
  protected get areas(): readonly Pick<Api['schemas']['SubjectResponse'], 'id' | 'name'>[] {
    const intent = this.intent();
    const job = this.job;
    return intent !== null &&
      job?.state === 'succeeded' &&
      job.result !== null &&
      'ids' in job.result
      ? intent.draft.candidates.filter(
          (candidate: Readonly<Pick<Api['schemas']['SubjectResponse'], 'id' | 'name'>>) =>
            job.result !== null && 'ids' in job.result && job.result.ids.includes(candidate.id),
        )
      : [];
  }
  protected get admissionMessage(): string {
    const error = this.admissionError;
    if (this.uncertain)
      return 'We couldn’t confirm this request. Retry the same request to check its outcome.';
    if (error instanceof ApiFailure && error.status === 503 && error.code === 'ai_unavailable')
      return 'AI assistance isn’t available right now. You can write and save as usual.';
    if (error instanceof ApiFailure && error.status === 429)
      return 'AI assistance is busy. You can write and save as usual, or try again later.';
    if (error instanceof ApiFailure && error.status === 409)
      return 'This request no longer matches the available source. Keep editing your goal.';
    return 'We couldn’t get a suggestion. You can write and save as usual.';
  }

  public constructor() {
    const update = () => {
      this.change.markForCheck();
    };
    const stopQuery = this.query.subscribe(
      (result: Readonly<QueryObserverResult<Api['schemas']['JobResponse']>>) => {
        this.denied(result.error);
        update();
      },
    );
    const stopAdmission = this.admission.subscribe(update);
    const stopCancel = this.cancellation.subscribe(() => {
      this.synchronize();
      update();
    });
    const stopSession = this.client
      .getQueryCache()
      .subscribe((event: Readonly<QueryCacheNotifyEvent>) => {
        const key: unknown = event.query.queryKey;
        if (!Array.isArray(key) || key[0] !== 'session') return;
        const state = this.client.getQueryState(['session']);
        const actor = this.client.getQueryData<Api['schemas']['IdentityResponse'] | null>([
          'session',
        ]);
        if (
          state === undefined ||
          actor === null ||
          (actor !== undefined &&
            (actor.account_id !== this.actor().account_id ||
              actor.account_status !== 'active' ||
              actor.membership_status !== 'verified'))
        )
          this.clear();
        this.synchronize();
        update();
      });
    this.destroy.onDestroy(() => {
      this.retired.set(true);
      this.clear();
      stopSession();
      stopQuery();
      stopAdmission();
      stopCancel();
      this.query.destroy();
    });
  }
  public ngOnChanges(): void {
    const intent = this.intent();
    if (intent !== null && intent.actorId !== this.actor().account_id) this.clear();
    this.synchronize();
  }
  private owns(intent: AssistanceIntent): boolean {
    return (
      !this.retired() &&
      this.intent() === intent &&
      !intent.signal.aborted &&
      intent.actorId === this.actor().account_id
    );
  }
  private authority(intent: AssistanceIntent): Api['schemas']['IdentityResponse'] {
    const actor = trustedActor(this.client, intent.actorId);
    if (!this.owns(intent) || actor === null) throw new CancelledError();
    return actor;
  }
  private synchronize(): void {
    this.query.setOptions(
      jobOptions(
        this.http,
        this.client,
        this.intent(),
        this.reference(),
        this.permitted && !this.changed && this.reference() !== null && !this.cancelling,
      ),
    );
  }
  private denied(error: unknown): void {
    if (!(error instanceof ApiFailure) || (error.status !== 401 && error.status !== 403)) return;
    const actorId = this.actor().account_id;
    this.clear();
    this.expired.emit({ actorId, failure: error });
  }
  private clear(): void {
    const intent = this.intent();
    const reference = this.reference();
    this.lifetime().abort();
    this.lifetime.set(new AbortController());
    this.intent.set(null);
    this.reference.set(null);
    this.admission.reset();
    this.cancellation.reset();
    this.query.setOptions(jobOptions(this.http, this.client, null, null, false));
    if (intent !== null && reference !== null)
      this.client.removeQueries({ queryKey: jobKey(intent, reference), exact: true });
    for (const mutation of this.client.getMutationCache().findAll({
      predicate: (mutation: Readonly<Mutation>) =>
        mutation.options.meta?.['goalAssistance'] === this.mutationOwner,
    }))
      this.client.getMutationCache().remove(mutation);
  }
  protected dismiss(): void {
    if (!this.submitting && !this.cancelling && !this.uncertain) this.clear();
  }
  protected async request(kind: 'clarify_goal' | 'suggest_subject'): Promise<void> {
    if (kind === 'clarify_goal' ? !this.mayClarify : !this.maySuggest) return;
    this.clear();
    const draft = this.draft();
    const body: GoalRequest =
      kind === 'clarify_goal'
        ? { kind, source: draft.source, target: 'context', text: draft.context }
        : {
            kind,
            source: draft.source,
            label: draft.areaLabel,
            candidate_ids: draft.candidates.map(
              (candidate: Readonly<Pick<Api['schemas']['SubjectResponse'], 'id' | 'name'>>) =>
                candidate.id,
            ),
          };
    const intent: AssistanceIntent = {
      actorId: this.actor().account_id,
      key: crypto.randomUUID(),
      body,
      draft,
      signal: this.lifetime().signal,
    };
    this.intent.set(intent);
    await this.admit(intent);
  }
  private install(intent: AssistanceIntent, job: Api['schemas']['JobResponse']): void {
    if (!this.owns(intent) || job.source.kind !== 'draft') return;
    const reference = { id: job.id, hash: job.source.content_hash };
    this.reference.set(reference);
    this.client.setQueryData(jobKey(intent, reference), job);
    this.synchronize();
  }
  private async admit(intent: AssistanceIntent): Promise<void> {
    try {
      const job = await this.admission.mutate(intent);
      if (!this.owns(intent)) return;
      this.install(intent, job);
      this.admission.reset();
    } catch (error: unknown) {
      if (this.owns(intent)) this.denied(error);
    }
    this.change.markForCheck();
  }
  protected async retryAdmission(): Promise<void> {
    const intent = this.intent();
    if (intent !== null && this.permitted && this.uncertain && !this.submitting)
      await this.admit(intent);
  }
  protected async askAgain(): Promise<void> {
    const intent = this.intent();
    if (intent === null || !this.mayAskAgain || this.uncertain || this.submitting) return;
    const kind = intent.body.kind;
    this.clear();
    await this.request(kind);
  }
  protected async check(): Promise<void> {
    if (this.permitted && !this.changed && this.reference() !== null && !this.cancelling) {
      const result = await this.query.refetch();
      if (result.isSuccess) this.cancellation.reset();
    }
  }
  protected async cancel(): Promise<void> {
    const intent = this.intent();
    const reference = this.reference();
    if (intent === null || reference === null || !this.permitted || this.cancelling) return;
    try {
      const job = await this.cancellation.mutate({ intent, reference });
      if (!this.owns(intent)) return;
      this.install(intent, job);
      this.cancellation.reset();
    } catch (error: unknown) {
      if (this.owns(intent)) this.denied(error);
    }
    this.synchronize();
    this.change.markForCheck();
  }
  protected useText(): void {
    const intent = this.intent();
    const value = this.suggestion;
    if (
      intent === null ||
      value === null ||
      this.applyDisabled() ||
      !this.permitted ||
      this.changed ||
      this.cancelling ||
      this.cancelFailed ||
      this.readFailed
    )
      return;
    this.applyText.emit({ source: intent.draft.source, target: 'context', value });
    this.clear();
  }
  protected useArea(id: string): void {
    const intent = this.intent();
    if (
      intent === null ||
      this.applyDisabled() ||
      !this.permitted ||
      this.changed ||
      this.cancelling ||
      this.cancelFailed ||
      this.readFailed ||
      !this.areas.some(
        (area: Readonly<Pick<Api['schemas']['SubjectResponse'], 'id' | 'name'>>) => area.id === id,
      )
    )
      return;
    this.applyArea.emit({ source: intent.draft.source, id });
    this.clear();
  }
}
