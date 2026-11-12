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
import { boundedWrite, unknownAdmission } from './assistance-query';
import {
  acceptsPhotoJob,
  isPhotoAdvice,
  photoAdvice,
  samePhotoSource,
  validPhotoSource,
} from './photo-assistance-contract';
import { photoJobKey, photoJobOptions } from './photo-assistance-query';
import type { PhotoIntent } from './photo-assistance-query';

interface PhotoCancellation {
  readonly intent: PhotoIntent;
  readonly jobId: string;
}

@Component({
  selector: 'peerly-photo-assistance',
  imports: [TuiButton],
  templateUrl: './photo-assistance.html',
  styleUrl: './photo-assistance.less',
})
export class PhotoAssistance implements OnChanges {
  public readonly actor = input.required<Api['schemas']['IdentityResponse']>();
  // Parent supplies current READY photo upload_id + CURRENT PHOTO version, not upload revision.
  public readonly source = input.required<Api['schemas']['ResourceSourceRequest'] | null>();
  public readonly sourceChecking = input(false);
  public readonly expired =
    output<Readonly<{ readonly actorId: string; readonly failure: ApiFailure }>>();
  public readonly chooseAnother = output();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly retired = signal(false);
  private readonly lifetime = signal(new AbortController());
  private readonly intent = signal<PhotoIntent | null>(null);
  private readonly jobId = signal<string | null>(null);
  private readonly mutationOwner: object = {};
  private readonly query = new QueryObserver(
    this.client,
    photoJobOptions(this.http, this.client, null, null, false),
  );
  private readonly admission = new MutationObserver(this.client, {
    mutationKey: ['photo-assistance-admit'],
    meta: { photoAssistance: this.mutationOwner },
    retry: false,
    mutationFn: (intent: PhotoIntent) => {
      const actor = this.authority(intent);
      if (this.sourceChecking()) throw new CancelledError();
      return boundedWrite(
        writeJson(
          this.http,
          '/api/v1/ai/jobs',
          intent.body,
          { 'x-csrf-token': actor.csrf_token, 'idempotency-key': intent.key },
          (value): value is Api['schemas']['JobResponse'] =>
            acceptsPhotoJob(value, intent.body.source),
        ),
        intent.signal,
      );
    },
  });
  private readonly cancellation = new MutationObserver(this.client, {
    mutationKey: ['photo-assistance-cancel'],
    meta: { photoAssistance: this.mutationOwner },
    retry: false,
    mutationFn: async (operation: PhotoCancellation) => {
      this.authority(operation.intent);
      await this.client.cancelQueries({
        queryKey: photoJobKey(operation.intent, operation.jobId),
        exact: true,
      });
      const actor = this.authority(operation.intent);
      return boundedWrite(
        writeJson(
          this.http,
          `/api/v1/ai/jobs/${encodeURIComponent(operation.jobId)}/cancel`,
          undefined,
          { 'x-csrf-token': actor.csrf_token },
          (value): value is Api['schemas']['JobResponse'] =>
            acceptsPhotoJob(value, operation.intent.body.source, operation.jobId),
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
  protected get admissionError(): unknown {
    return this.admission.getCurrentResult().error;
  }
  protected get uncertain(): boolean {
    return unknownAdmission(this.admissionError);
  }
  public get hasRequest(): boolean {
    return this.intent() !== null;
  }
  protected get visible(): boolean {
    return this.source() !== null || this.hasRequest;
  }
  protected get readySource(): boolean {
    const source = this.source();
    return !this.sourceChecking() && source !== null && validPhotoSource(source);
  }
  protected get knownJob(): boolean {
    return this.jobId() !== null;
  }
  protected get changed(): boolean {
    const intent = this.intent();
    if (intent === null || this.sourceChecking()) return false;
    const source = this.source();
    return source === null || !samePhotoSource(intent.body.source, source);
  }
  protected get canAsk(): boolean {
    return (
      this.permitted &&
      this.readySource &&
      !this.submitting &&
      !this.cancelling &&
      !this.uncertain &&
      this.jobId() === null
    );
  }
  protected get job(): Api['schemas']['JobResponse'] | null {
    return this.query.getCurrentResult().data ?? null;
  }
  protected get pendingJob(): boolean {
    return this.job?.state === 'queued' || this.job?.state === 'running';
  }
  protected get pollingStopped(): boolean {
    const job = this.job;
    return job !== null && this.pendingJob && Date.now() >= Date.parse(job.deadline);
  }
  protected get checking(): boolean {
    return this.jobId() !== null && this.job === null && this.query.getCurrentResult().isFetching;
  }
  protected get readFailed(): boolean {
    return this.query.getCurrentResult().isError;
  }
  protected get cancelFailed(): boolean {
    return this.cancellation.getCurrentResult().isError;
  }
  protected get tips(): readonly string[] {
    const job = this.job;
    return job?.state === 'succeeded' && isPhotoAdvice(job.result)
      ? [
          photoAdvice.blurred[job.result.blurred],
          photoAdvice.face_visible[job.result.face_visible],
          photoAdvice.multiple_people[job.result.multiple_people],
        ]
      : [];
  }
  protected get mayAskAgain(): boolean {
    const job = this.job;
    return (
      this.permitted &&
      this.readySource &&
      !this.changed &&
      !this.cancelling &&
      !this.cancelFailed &&
      !this.readFailed &&
      job !== null &&
      (job.state === 'failed' || job.state === 'expired' || job.state === 'cancelled')
    );
  }
  protected get message(): string {
    const error = this.admissionError;
    if (this.uncertain)
      return 'We couldn’t confirm your photo tips request. Retry the same request to check its outcome.';
    if (error instanceof ApiFailure && error.status === 503 && error.code === 'ai_unavailable')
      return 'Photo tips aren’t available right now. You can keep or change your photo as usual.';
    if (error instanceof ApiFailure && error.status === 429)
      return 'AI assistance is busy. You can keep or change your photo as usual, or try again later.';
    if (error instanceof ApiFailure && error.status === 409)
      return 'This saved photo is no longer available for tips. Your manual photo choices are unchanged.';
    return 'We couldn’t get photo tips. You can keep or change your photo as usual.';
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
  private owns(intent: PhotoIntent): boolean {
    return (
      !this.retired() &&
      this.intent() === intent &&
      !intent.signal.aborted &&
      intent.actorId === this.actor().account_id
    );
  }
  private authority(intent: PhotoIntent): Api['schemas']['IdentityResponse'] {
    const actor = trustedActor(this.client, intent.actorId);
    if (!this.owns(intent) || actor === null) throw new CancelledError();
    return actor;
  }
  private synchronize(): void {
    this.query.setOptions(
      photoJobOptions(
        this.http,
        this.client,
        this.intent(),
        this.jobId(),
        this.permitted && !this.changed && this.jobId() !== null && !this.cancelling,
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
    const jobId = this.jobId();
    this.lifetime().abort();
    this.lifetime.set(new AbortController());
    this.intent.set(null);
    this.jobId.set(null);
    this.admission.reset();
    this.cancellation.reset();
    this.query.setOptions(photoJobOptions(this.http, this.client, null, null, false));
    if (intent !== null && jobId !== null)
      this.client.removeQueries({ queryKey: photoJobKey(intent, jobId), exact: true });
    for (const mutation of this.client.getMutationCache().findAll({
      predicate: (mutation: Readonly<Mutation>) =>
        mutation.options.meta?.['photoAssistance'] === this.mutationOwner,
    }))
      this.client.getMutationCache().remove(mutation);
  }
  protected dismiss(): void {
    if (!this.submitting && !this.cancelling && !this.uncertain) this.clear();
  }
  protected async ask(): Promise<void> {
    const source = this.source();
    if (!this.canAsk || source === null) return;
    this.clear();
    const body: Api['schemas']['PhotoRequest'] = {
      kind: 'assess_photo',
      source: { kind: 'resource', id: source.id, version: source.version },
    };
    const intent: PhotoIntent = {
      actorId: this.actor().account_id,
      key: crypto.randomUUID(),
      body,
      signal: this.lifetime().signal,
    };
    this.intent.set(intent);
    await this.admit(intent);
  }
  private install(intent: PhotoIntent, job: Api['schemas']['JobResponse']): void {
    if (!this.owns(intent)) return;
    this.jobId.set(job.id);
    this.client.setQueryData(photoJobKey(intent, job.id), job);
    this.synchronize();
  }
  private async admit(intent: PhotoIntent): Promise<void> {
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
  protected async retry(): Promise<void> {
    const intent = this.intent();
    if (
      intent !== null &&
      this.permitted &&
      !this.sourceChecking() &&
      this.uncertain &&
      !this.submitting
    )
      await this.admit(intent);
  }
  protected async askAgain(): Promise<void> {
    if (!this.mayAskAgain || this.uncertain || this.submitting) return;
    this.clear();
    await this.ask();
  }
  protected async forCurrentPhoto(): Promise<void> {
    if (
      !this.permitted ||
      !this.changed ||
      !this.readySource ||
      this.uncertain ||
      this.submitting ||
      this.cancelling
    )
      return;
    this.clear();
    await this.ask();
  }
  protected async check(): Promise<void> {
    if (this.permitted && !this.changed && this.jobId() !== null && !this.cancelling) {
      const result = await this.query.refetch();
      if (result.isSuccess) this.cancellation.reset();
    }
  }
  protected async cancel(): Promise<void> {
    const intent = this.intent();
    const jobId = this.jobId();
    if (intent === null || jobId === null || !this.permitted || this.cancelling) return;
    try {
      const job = await this.cancellation.mutate({ intent, jobId });
      if (!this.owns(intent)) return;
      this.install(intent, job);
      this.cancellation.reset();
    } catch (error: unknown) {
      if (this.owns(intent)) this.denied(error);
    }
    this.synchronize();
    this.change.markForCheck();
  }
  protected choose(): void {
    if (
      this.permitted &&
      !this.sourceChecking() &&
      this.source() !== null &&
      !this.changed &&
      !this.cancelling &&
      !this.cancelFailed &&
      !this.readFailed &&
      this.tips.length > 0
    )
      this.chooseAnother.emit();
  }
}
