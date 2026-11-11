import { HttpClient, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { QueryClient } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { challengeOptions, isChallenge, isCreated, isVerified } from './challenge';
import { actor, challenge } from './onboarding.fixtures';

describe('actor-owned verification status boundary', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
  });
  afterEach(() => {
    TestBed.inject(HttpTestingController).verify();
  });
  it('accepts explicit server state without inferring resend or verification success', () => {
    expect(isChallenge(challenge)).toBe(true);
    expect(
      isChallenge({
        ...challenge,
        state: 'consumed',
        verification_outcome: 'support_required',
        delivery: 'failed',
        can_verify: false,
      }),
    ).toBe(true);
  });
  for (const value of [
    null,
    [],
    0,
    ...Object.keys(challenge).flatMap((key) => [
      Object.fromEntries(
        Object.entries(challenge).filter(([name]: readonly [string, unknown]) => name !== key),
      ),
      { ...challenge, [key]: {} },
    ]),
    { ...challenge, state: 'invented' },
    { ...challenge, delivery: 'delivered' },
    { ...challenge, verification_outcome: 'invented' },
    { ...challenge, attempts_remaining: -1 },
  ]) {
    it(`rejects malformed status ${JSON.stringify(value)}`, () => {
      expect(isChallenge(value)).toBe(false);
    });
  }
  for (const value of [
    null,
    0,
    {},
    { id: 0, expires_at: 'x', resend_at: 'x' },
    { id: 'x', expires_at: 0, resend_at: 'x' },
    { id: 'x', expires_at: 'x', resend_at: 0 },
  ]) {
    it(`rejects malformed created response ${JSON.stringify(value)}`, () => {
      expect(isCreated(value)).toBe(false);
    });
  }
  it('validates actual creation and verification receipts', () => {
    expect(
      isCreated({
        id: challenge.id,
        expires_at: challenge.expires_at,
        resend_at: challenge.resend_at,
      }),
    ).toBe(true);
    expect(isVerified({ verified_at: '2026-11-07T12:00:00Z' })).toBe(true);
    for (const value of [null, 0, {}, { verified_at: 0 }]) expect(isVerified(value)).toBe(false);
  });
  it('queries the owned challenge with all identity parameters in its key', async () => {
    const client = new QueryClient();
    const options = challengeOptions(
      TestBed.inject(HttpClient),
      actor.account_id,
      challenge.id,
      true,
    );
    expect(options.queryKey).toEqual([
      'account',
      actor.account_id,
      'email-challenge',
      challenge.id,
    ]);
    const result = client.query(options);
    const request = await vi.waitFor(() =>
      TestBed.inject(HttpTestingController).expectOne(
        `/api/v1/auth/email-challenges/${challenge.id}`,
      ),
    );
    request.flush(challenge);
    await expect(result).resolves.toEqual(challenge);
    client.clear();
  });
  it('never permits a manual fetch without an actor-owned challenge', async () => {
    const client = new QueryClient();
    const options = challengeOptions(TestBed.inject(HttpClient), null, null, false);
    expect(options.enabled).toBe(false);
    await expect(client.query(options)).rejects.toMatchObject({ code: 'challenge_unavailable' });
    client.clear();
  });
});
