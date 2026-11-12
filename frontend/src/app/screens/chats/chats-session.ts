import type { QueryClient } from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';

// An idle failed revalidation may still retain old identity data. Data alone is
// never authority for a new private read or command.
export function trustedChatActor(
  client: Readonly<QueryClient>,
  actorId: string,
): Api['schemas']['IdentityResponse'] | null {
  const state = client.getQueryState(['session']);
  const identity = client.getQueryData<Api['schemas']['IdentityResponse'] | null>(['session']);
  return state?.status === 'success' &&
    state.fetchStatus === 'idle' &&
    identity?.account_id === actorId &&
    identity.capabilities.can_use_student_features
    ? identity
    : null;
}
