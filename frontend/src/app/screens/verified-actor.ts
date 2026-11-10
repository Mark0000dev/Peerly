import type { QueryClient } from '@tanstack/angular-query-experimental';
import type { Api } from '../api.generated';

// Shared only by actual verified-student editing/assistance consumers.
// Cached identity during pending/failed validation is ownership, not authority.
export function trustedVerifiedActor(
  client: Readonly<QueryClient>,
  accountId: string,
): Api['schemas']['IdentityResponse'] | null {
  const state = client.getQueryState(['session']);
  const actor = client.getQueryData<Api['schemas']['IdentityResponse'] | null>(['session']);
  return state?.status === 'success' &&
    state.fetchStatus === 'idle' &&
    actor?.account_id === accountId &&
    actor.account_status === 'active' &&
    actor.membership_status === 'verified'
    ? actor
    : null;
}
