import type { QueryClient, Query } from '@tanstack/angular-query-experimental';
import { ApiFailure } from '../../api-http';

export function operatorDenied(client: Readonly<QueryClient>, actor: string | null): boolean {
  return (
    actor !== null &&
    client
      .getQueryCache()
      .findAll({ queryKey: ['account', actor, 'operator'] })
      .some(
        (query: Readonly<Query>) =>
          query.state.error instanceof ApiFailure && query.state.error.status === 403,
      )
  );
}

export function retireOperatorFailure(
  client: Readonly<QueryClient>,
  error: unknown,
  actor: unknown,
  currentActor: () => string | null,
  sync: () => void,
  recheck: () => void,
): void {
  if (!(error instanceof ApiFailure) || actor !== currentActor() || typeof actor !== 'string')
    return;
  if (error.status === 401) {
    client.setQueryData(['session'], null);
    client.removeQueries({ queryKey: ['account'] });
    recheck();
  } else if (error.status === 403) {
    const prefix = ['account', actor, 'operator'] as const;
    const failed = client
      .getQueryCache()
      .findAll({ queryKey: prefix })
      .find((query: Readonly<Query>) => query.state.error === error);
    sync();
    void client.cancelQueries({ queryKey: prefix }).then(() => {
      if (
        failed === undefined ||
        currentActor() !== actor ||
        client.getQueryCache().get(failed.queryHash) !== failed
      )
        return;
      if (failed.state.data !== undefined) failed.setState({ data: undefined });
      client.removeQueries({
        queryKey: prefix,
        predicate: (query: Readonly<Query>) => query !== failed,
      });
    });
  }
}
