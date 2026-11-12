import { afterEach, describe, expect, it } from 'vitest';
import { QueryClient } from '@tanstack/angular-query-experimental';
import { trustedVerifiedActor } from './verified-actor';
import { verifiedActor } from './onboarding/onboarding.fixtures';

describe('fresh verified editing authority', () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  afterEach(() => {
    client.clear();
  });
  it('allows verified preactivation editing without inventing an activation requirement', () => {
    client.setQueryData(['session'], verifiedActor);
    expect(verifiedActor.capabilities.can_use_student_features).toBe(false);
    expect(trustedVerifiedActor(client, verifiedActor.account_id)).toBe(verifiedActor);
  });
  it('rejects a missing, signed-out, different, banned or revoked owner', () => {
    expect(trustedVerifiedActor(client, verifiedActor.account_id)).toBeNull();
    for (const actor of [
      null,
      { ...verifiedActor, account_id: 'replacement' },
      { ...verifiedActor, account_status: 'banned' },
      { ...verifiedActor, membership_status: 'revoked' },
    ]) {
      client.setQueryData(['session'], actor);
      expect(trustedVerifiedActor(client, verifiedActor.account_id)).toBeNull();
    }
  });
  it('distinguishes retained ownership from authority during pending and failed revalidation', async () => {
    client.setQueryData(['session'], verifiedActor);
    let fail: (error: Readonly<Error>) => void = () => {
      throw new Error('Missing controlled identity read');
    };
    const pending = new Promise<never>((_resolve, reject) => {
      fail = reject;
    });
    const read = client.query({ queryKey: ['session'], queryFn: () => pending });
    const rejected = expect(read).rejects.toThrow('Controlled unavailable identity');
    expect(client.getQueryData(['session'])).toBe(verifiedActor);
    expect(trustedVerifiedActor(client, verifiedActor.account_id)).toBeNull();
    fail(new Error('Controlled unavailable identity'));
    await rejected;
    expect(client.getQueryData(['session'])).toBe(verifiedActor);
    expect(trustedVerifiedActor(client, verifiedActor.account_id)).toBeNull();
    client.setQueryData(['session'], { ...verifiedActor, csrf_token: 'fresh-csrf' });
    expect(trustedVerifiedActor(client, verifiedActor.account_id)?.csrf_token).toBe('fresh-csrf');
  });
});
