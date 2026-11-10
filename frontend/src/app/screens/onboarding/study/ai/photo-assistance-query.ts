import type { HttpClient } from '@angular/common/http';
import { CancelledError, queryOptions } from '@tanstack/angular-query-experimental';
import type {
  Query,
  QueryClient,
  QueryFunctionContext,
} from '@tanstack/angular-query-experimental';
import type { Api } from '../../../../api.generated';
import { readJson } from '../../../../api-http';
import { trustedVerifiedActor as trustedActor } from '../../../verified-actor';
import { acceptsPhotoJob } from './photo-assistance-contract';

export interface PhotoIntent {
  readonly actorId: string;
  readonly key: string;
  readonly body: Api['schemas']['PhotoRequest'];
  readonly signal: AbortSignal;
}
export function photoJobKey(intent: PhotoIntent | null, jobId: string | null) {
  if (intent === null || jobId === null) return ['photo-assistance-idle'] as const;
  return [
    'account',
    intent.actorId,
    'photo-assistance',
    intent.body.source.id,
    intent.body.source.version,
    jobId,
  ] as const;
}
export function photoJobOptions(
  http: Readonly<HttpClient>,
  client: Readonly<QueryClient>,
  intent: PhotoIntent | null,
  jobId: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: photoJobKey(intent, jobId),
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
          ReturnType<typeof photoJobKey>
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
        jobId === null ||
        intent.signal.aborted ||
        trustedActor(client, intent.actorId) === null
      )
        throw new CancelledError();
      return readJson(
        http,
        `/api/v1/ai/jobs/${encodeURIComponent(jobId)}`,
        AbortSignal.any([signal, intent.signal, AbortSignal.timeout(15_000)]),
        (value): value is Api['schemas']['JobResponse'] =>
          acceptsPhotoJob(value, intent.body.source, jobId),
      );
    },
  });
}
