import { trustedVerifiedActor as trustedActor } from '../../../verified-actor';
import type { HttpClient } from '@angular/common/http';
import { CancelledError, queryOptions } from '@tanstack/angular-query-experimental';
import type {
  Query,
  QueryClient,
  QueryFunctionContext,
} from '@tanstack/angular-query-experimental';
import type { Api } from '../../../../api.generated';
import { ApiFailure, readJson } from '../../../../api-http';
import { acceptsJob } from './goal-assistance-contract';
import type { GoalAssistanceDraft, GoalRequest } from './goal-assistance-contract';

export interface AssistanceIntent {
  readonly actorId: string;
  readonly key: string;
  readonly body: GoalRequest;
  readonly draft: GoalAssistanceDraft;
  readonly signal: AbortSignal;
}
// Resource identity and returned source proof, never a second job state/result.
export interface JobReference {
  readonly id: string;
  readonly hash: string;
}
export function jobKey(intent: AssistanceIntent | null, reference: JobReference | null) {
  if (intent === null || reference === null) return ['goal-assistance-idle'] as const;
  return [
    'account',
    intent.actorId,
    'goal-assistance',
    intent.draft.source.id,
    intent.draft.source.version,
    reference.id,
    reference.hash,
  ] as const;
}
export function jobOptions(
  http: Readonly<HttpClient>,
  client: Readonly<QueryClient>,
  intent: AssistanceIntent | null,
  reference: JobReference | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: jobKey(intent, reference),
    enabled,
    retry: false,
    gcTime: 0,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    refetchInterval: (
      query: Readonly<
        Query<
          Api['schemas']['JobResponse'],
          Error,
          Api['schemas']['JobResponse'],
          ReturnType<typeof jobKey>
        >
      >,
    ) => {
      const job = query.state.data;
      if (
        !enabled ||
        query.state.status === 'error' ||
        job === undefined ||
        (job.state !== 'queued' && job.state !== 'running') ||
        job.poll_after_ms === null
      )
        return false;
      const remaining = Date.parse(job.deadline) - Date.now();
      return remaining > 0 ? Math.min(job.poll_after_ms, remaining, 2_147_483_647) : false;
    },
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) => {
      if (
        intent === null ||
        reference === null ||
        intent.signal.aborted ||
        trustedActor(client, intent.actorId) === null
      )
        throw new CancelledError();
      return readJson(
        http,
        `/api/v1/ai/jobs/${encodeURIComponent(reference.id)}`,
        AbortSignal.any([signal, intent.signal, AbortSignal.timeout(15_000)]),
        (value): value is Api['schemas']['JobResponse'] =>
          acceptsJob(value, intent.body, reference),
      );
    },
  });
}
// A local bounded wait is NOT confirmation that the server rejected/cancelled a write.
// A late committed admission can only be reconciled by explicit same-key replay.
export function boundedWrite<T>(
  request: Promise<T>,
  signal: Readonly<AbortSignal>,
  milliseconds = 15_000,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const cleanup = () => {
      clearTimeout(timer);
      signal.removeEventListener('abort', abort);
    };
    const abort = () => {
      cleanup();
      reject(new DOMException('Assistance view retired', 'AbortError'));
    };
    const timer = setTimeout(() => {
      cleanup();
      reject(new ApiFailure(0, 'ai_response_unknown', null));
    }, milliseconds);
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) abort();
    void request.then(
      (value: T) => {
        cleanup();
        resolve(value);
      },
      (error: unknown) => {
        cleanup();
        reject(error instanceof Error ? error : new Error('AI request failed'));
      },
    );
  });
}
export function unknownAdmission(error: unknown): boolean {
  return (
    error instanceof ApiFailure &&
    (error.status === 0 ||
      error.status === 408 ||
      (error.status >= 500 && !(error.status === 503 && error.code === 'ai_unavailable')))
  );
}
