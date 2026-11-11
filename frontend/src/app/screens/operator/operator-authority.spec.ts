import { MutationObserver, QueryClient } from '@tanstack/angular-query-experimental';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiFailure } from '../../api-http';
import {
  operatorDenied,
  recheckOperatorAuthority,
  retireOperatorFailure,
} from './operator-authority';

describe('operator authority across actual reads and explicit status writes', () => {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const actor = 'operator-a';
  const prefix = ['account', actor, 'operator'] as const;
  afterEach(() => {
    client.clear();
  });

  async function deniedWrite(owner = actor, status = 403) {
    const error = new ApiFailure(status, 'access_denied', null);
    const observer = new MutationObserver(client, {
      mutationKey: ['account', owner, 'operator', 'support', 'status', 'case-a'],
      mutationFn: () => Promise.reject(error),
    });
    await expect(observer.mutate()).rejects.toBe(error);
    return error;
  }

  it('a settled canonical write denial retires cached sibling content and keeps authority denied', async () => {
    client.setQueryData([...prefix, 'account', 'student-a'], { private: 'retained' });
    client.setQueryData(['account', 'other-actor', 'operator', 'account'], 'other');
    const error = await deniedWrite();
    const sync = vi.fn();
    retireOperatorFailure(client, error, actor, () => actor, sync, vi.fn());
    await vi.waitFor(() => {
      expect(client.getQueryCache().findAll({ queryKey: prefix })).toHaveLength(0);
    });
    expect(sync).toHaveBeenCalledOnce();
    expect(operatorDenied(client, actor)).toBe(true);
    expect(operatorDenied(client, 'other-actor')).toBe(false);
    expect(operatorDenied(client, null)).toBe(false);
    expect(client.getQueryData(['account', 'other-actor', 'operator', 'account'])).toBe('other');
  });

  it('only explicit successful same-actor session revalidation clears the original denial', async () => {
    await deniedWrite();
    await recheckOperatorAuthority(
      client,
      actor,
      () => actor,
      () => Promise.resolve({ isSuccess: false }),
    );
    expect(operatorDenied(client, actor)).toBe(true);
    await recheckOperatorAuthority(
      client,
      actor,
      () => 'replacement',
      () => Promise.resolve({ isSuccess: true }),
    );
    expect(operatorDenied(client, actor)).toBe(true);
    await recheckOperatorAuthority(
      client,
      actor,
      () => actor,
      () => Promise.resolve({ isSuccess: true }),
    );
    expect(operatorDenied(client, actor)).toBe(false);
  });

  it('a concurrent new denial survives rechecking an older failure', async () => {
    await deniedWrite();
    await recheckOperatorAuthority(
      client,
      actor,
      () => actor,
      async () => {
        await deniedWrite();
        return { isSuccess: true };
      },
    );
    expect(operatorDenied(client, actor)).toBe(true);
    expect(client.getMutationCache().getAll()).toHaveLength(1);
  });

  it('other actors, local errors and detached failures never retire current private data', async () => {
    client.setQueryData([...prefix, 'detail'], 'private');
    const stale = await deniedWrite('previous');
    retireOperatorFailure(client, stale, 'previous', () => actor, vi.fn(), vi.fn());
    const local = await deniedWrite(actor, 503);
    retireOperatorFailure(client, local, actor, () => actor, vi.fn(), vi.fn());
    retireOperatorFailure(
      client,
      new ApiFailure(403, 'access_denied', null),
      actor,
      () => actor,
      vi.fn(),
      vi.fn(),
    );
    await Promise.resolve();
    expect(operatorDenied(client, actor)).toBe(false);
    expect(client.getQueryData([...prefix, 'detail'])).toBe('private');
  });
});
