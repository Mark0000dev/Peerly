import { isPolicyReference } from './policy-reference';
import type { HttpClient } from '@angular/common/http';
import { queryOptions } from '@tanstack/angular-query-experimental';
import type {
  QueryClient,
  QueryFunctionContext,
  Query,
} from '@tanstack/angular-query-experimental';
import { ApiFailure, readJson } from '../api-http';
import type { Api } from '../api.generated';

type Identity = Api['schemas']['IdentityResponse'];

function isReceipt(value: unknown): value is Api['schemas']['RegistrationReceiptResponse'] {
  if (typeof value !== 'object' || value === null) return false;
  return (
    'id' in value &&
    typeof value.id === 'string' &&
    'context_id' in value &&
    typeof value.context_id === 'string' &&
    'registered_at' in value &&
    typeof value.registered_at === 'string' &&
    'notice_text' in value &&
    typeof value.notice_text === 'string' &&
    'surface' in value &&
    value.surface === 'onboarding_completion' &&
    'terms' in value &&
    isPolicyReference(value.terms) &&
    'privacy' in value &&
    isPolicyReference(value.privacy)
  );
}

function isIdentity(value: unknown): value is Identity {
  if (typeof value !== 'object' || value === null) return false;
  if (!('account_id' in value) || typeof value.account_id !== 'string') return false;
  if (
    !('account_status' in value) ||
    typeof value.account_status !== 'string' ||
    !['active', 'banned'].includes(value.account_status)
  )
    return false;
  if (
    !('membership_status' in value) ||
    typeof value.membership_status !== 'string' ||
    !['unverified', 'verified', 'revoked'].includes(value.membership_status)
  )
    return false;
  if (
    !('verified_at' in value) ||
    !(value.verified_at === null || typeof value.verified_at === 'string')
  )
    return false;
  if (
    !('csrf_token' in value) ||
    typeof value.csrf_token !== 'string' ||
    value.csrf_token.length === 0
  )
    return false;
  if (
    !('email_challenge_id' in value) ||
    !(value.email_challenge_id === null || typeof value.email_challenge_id === 'string')
  )
    return false;
  if (!('registration' in value) || !(value.registration === null || isReceipt(value.registration)))
    return false;
  if (
    !('capabilities' in value) ||
    typeof value.capabilities !== 'object' ||
    value.capabilities === null
  )
    return false;
  const capabilities = value.capabilities;
  return (
    'can_begin_onboarding' in capabilities &&
    typeof capabilities.can_begin_onboarding === 'boolean' &&
    'can_use_student_features' in capabilities &&
    typeof capabilities.can_use_student_features === 'boolean' &&
    'can_verify_student_email' in capabilities &&
    typeof capabilities.can_verify_student_email === 'boolean'
  );
}

export function sessionOptions(http: Readonly<HttpClient>, client: Readonly<QueryClient>) {
  return queryOptions({
    queryKey: ['session'] as const,
    staleTime: 0,
    retry: false,
    queryFn: async ({ signal }: Readonly<QueryFunctionContext>): Promise<Identity | null> => {
      signal.throwIfAborted();
      // Revalidation is a boundary: old private requests may not race a new identity.
      await client.cancelQueries({
        predicate: (query: Readonly<Query>) => query.queryKey[0] === 'account',
      });
      client.removeQueries({
        predicate: (query: Readonly<Query>) => query.queryKey[0] === 'account',
      });
      signal.throwIfAborted();
      try {
        return await readJson(http, '/api/v1/me', signal, isIdentity);
      } catch (error: unknown) {
        if (error instanceof ApiFailure && error.status === 401) return null;
        throw error;
      }
    },
  });
}
