import type { HttpClient } from '@angular/common/http';
import { queryOptions } from '@tanstack/angular-query-experimental';
import type { QueryFunctionContext } from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { ApiFailure, readJson } from '../../api-http';

type Status = Api['schemas']['ChallengeStatusResponse'];
export function isChallenge(value: unknown): value is Status {
  if (typeof value !== 'object' || value === null) return false;
  return (
    'id' in value &&
    typeof value.id === 'string' &&
    'email' in value &&
    typeof value.email === 'string' &&
    'expires_at' in value &&
    typeof value.expires_at === 'string' &&
    'resend_at' in value &&
    typeof value.resend_at === 'string' &&
    'state' in value &&
    typeof value.state === 'string' &&
    ['active', 'expired', 'locked', 'superseded', 'consumed'].includes(value.state) &&
    'delivery' in value &&
    typeof value.delivery === 'string' &&
    ['queued', 'sending', 'sent', 'failed', 'cancelled'].includes(value.delivery) &&
    'verification_outcome' in value &&
    (value.verification_outcome === null ||
      (typeof value.verification_outcome === 'string' &&
        ['verified', 'wrong', 'locked', 'expired', 'unavailable', 'support_required'].includes(
          value.verification_outcome,
        ))) &&
    'attempts_remaining' in value &&
    typeof value.attempts_remaining === 'number' &&
    Number.isInteger(value.attempts_remaining) &&
    value.attempts_remaining >= 0 &&
    'can_verify' in value &&
    typeof value.can_verify === 'boolean' &&
    'can_resend' in value &&
    typeof value.can_resend === 'boolean'
  );
}

export function challengeOptions(
  http: Readonly<HttpClient>,
  accountId: string | null,
  challengeId: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', accountId, 'email-challenge', challengeId] as const,
    enabled: enabled && challengeId !== null && accountId !== null,
    retry: false,
    staleTime: 0,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) => {
      if (challengeId === null || accountId === null)
        throw new ApiFailure(0, 'challenge_unavailable', null);
      return readJson(
        http,
        `/api/v1/auth/email-challenges/${encodeURIComponent(challengeId)}`,
        signal,
        isChallenge,
      );
    },
  });
}

export function isCreated(value: unknown): value is Api['schemas']['ChallengeResponse'] {
  return (
    typeof value === 'object' &&
    value !== null &&
    'id' in value &&
    typeof value.id === 'string' &&
    'expires_at' in value &&
    typeof value.expires_at === 'string' &&
    'resend_at' in value &&
    typeof value.resend_at === 'string'
  );
}
export function isVerified(value: unknown): value is Api['schemas']['VerificationResponse'] {
  return (
    typeof value === 'object' &&
    value !== null &&
    'verified_at' in value &&
    typeof value.verified_at === 'string'
  );
}
