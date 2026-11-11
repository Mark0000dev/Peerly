import type { QueryClient, Query, Mutation } from '@tanstack/angular-query-experimental';
import { ApiFailure } from '../../api-http';

export function operatorDenied(client: Readonly<QueryClient>, actor: string | null): boolean {
  return (
    actor !== null &&
    (deniedMutations(client, actor).length > 0 ||
      client
        .getQueryCache()
        .findAll({ queryKey: ['account', actor, 'operator'] })
        .some(
          (query: Readonly<Query>) =>
            query.state.error instanceof ApiFailure && query.state.error.status === 403,
        ))
  );
}

function deniedMutations(client: Readonly<QueryClient>, actor: string) {
  return client.getMutationCache().findAll({
    mutationKey: ['account', actor, 'operator'],
    predicate: (mutation: Readonly<Mutation>) =>
      mutation.state.error instanceof ApiFailure && mutation.state.error.status === 403,
  });
}

export async function recheckOperatorAuthority(
  client: Readonly<QueryClient>,
  actor: string | null,
  currentActor: () => string | null,
  refetch: () => Promise<Readonly<{ readonly isSuccess: boolean }>>,
): Promise<void> {
  const previous: ReadonlyMap<Readonly<Mutation>, unknown> = new Map(
    (actor === null ? [] : deniedMutations(client, actor)).map(
      (mutation: Readonly<Mutation>) => [mutation, mutation.state.error] as const,
    ),
  );
  const result = await refetch();
  if (!result.isSuccess || actor === null || currentActor() !== actor) return;
  // Only explicit successful revalidation retires the denial we started with.
  // A concurrent newer denial must survive this check.
  for (const mutation of client.getMutationCache().getAll()) {
    if (previous.has(mutation) && previous.get(mutation) === mutation.state.error)
      client.getMutationCache().remove(mutation);
  }
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
    const mutation = deniedMutations(client, actor).find(
      (item: Readonly<Mutation>) => item.state.error === error,
    );
    sync();
    void client.cancelQueries({ queryKey: prefix }).then(() => {
      if (
        currentActor() !== actor ||
        (failed === undefined
          ? mutation === undefined || !client.getMutationCache().getAll().includes(mutation)
          : client.getQueryCache().get(failed.queryHash) !== failed)
      )
        return;
      if (failed?.state.data !== undefined) failed.setState({ data: undefined });
      client.removeQueries({
        queryKey: prefix,
        predicate: (query: Readonly<Query>) => query !== failed,
      });
    });
  }
}
