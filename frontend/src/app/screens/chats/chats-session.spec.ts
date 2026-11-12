import { QueryClient } from '@tanstack/angular-query-experimental';
import { describe, expect, it } from 'vitest';
import { identity } from './chats.fixtures';
import { trustedChatActor } from './chats-session';

describe('Private chat authority from the successful current session', () => {
  it('requires an actual matching eligible identity, not an absent/replaced account', () => {
    const client = new QueryClient();
    expect(trustedChatActor(client, identity.account_id)).toBeNull();
    client.setQueryData(['session'], null);
    expect(trustedChatActor(client, identity.account_id)).toBeNull();
    client.setQueryData(['session'], identity);
    expect(trustedChatActor(client, identity.account_id)).toEqual(identity);
    expect(trustedChatActor(client, 'replacement')).toBeNull();
    client.setQueryData(['session'], {
      ...identity,
      capabilities: { ...identity.capabilities, can_use_student_features: false },
    });
    expect(trustedChatActor(client, identity.account_id)).toBeNull();
    client.clear();
  });
  it('blocks both in-flight and failed revalidation even when the old identity remains cached', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(['session'], identity);
    let fail: ((error: Readonly<Error>) => void) | undefined;
    const pending = new Promise<never>((_resolve, reject) => {
      fail = reject;
    });
    const release = fail;
    if (release === undefined) throw new Error('Missing controlled failure');
    const refresh = client.query({ queryKey: ['session'], queryFn: () => pending, staleTime: 0 });
    expect(trustedChatActor(client, identity.account_id)).toBeNull();
    release(new Error('Controlled session read failure'));
    await expect(refresh).rejects.toThrow('Controlled session read failure');
    expect(client.getQueryData(['session'])).toEqual(identity);
    expect(client.getQueryState(['session'])?.status).toBe('error');
    expect(client.getQueryState(['session'])?.fetchStatus).toBe('idle');
    expect(trustedChatActor(client, identity.account_id)).toBeNull();
    client.clear();
  });
});
