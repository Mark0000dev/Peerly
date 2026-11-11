import { HttpClient, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { CancelledError, QueryClient } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { identity, message } from '../chats.fixtures';
import { preparationOptions, preparationsOptions } from './image-queries';

describe('C03 owner preparation query boundaries', () => {
  let http: HttpClient;
  let backend: HttpTestingController;
  let client: QueryClient;
  const base = `/api/v1/conversations/${message.conversation_id}/image-preparations`;
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
    client = new QueryClient();
    client.setQueryData(['session'], identity);
  });
  afterEach(() => {
    client.clear();
    backend.verify({ ignoreCancelled: true });
    TestBed.resetTestingModule();
  });
  it('includes every owner/path identity in keys, disables missing identities and does not authorize from stale session data', async () => {
    const absent = preparationsOptions(http, client, null, message.conversation_id, true);
    expect(absent.enabled).toBe(false);
    await expect(client.query(absent)).rejects.toBeInstanceOf(CancelledError);
    const noImage = preparationOptions(
      http,
      client,
      identity.account_id,
      message.conversation_id,
      null,
      true,
    );
    expect(noImage.enabled).toBe(false);
    await expect(client.query(noImage)).rejects.toBeInstanceOf(CancelledError);
    client.setQueryData(['session'], null);
    const foreign = preparationOptions(
      http,
      client,
      identity.account_id,
      message.conversation_id,
      message.message_id,
      true,
    );
    await expect(client.query(foreign)).rejects.toBeInstanceOf(CancelledError);
    const collection = preparationsOptions(
      http,
      client,
      identity.account_id,
      message.conversation_id,
      true,
    );
    await expect(client.query(collection)).rejects.toBeInstanceOf(CancelledError);
    backend.expectNone(base);
  });
  it('binds collection responses to the selected conversation and consumes cancellation', async () => {
    const options = preparationsOptions(
      http,
      client,
      identity.account_id,
      message.conversation_id,
      true,
    );
    const promise = client.query(options);
    const request = await vi.waitFor(() => backend.expectOne(base));
    request.flush({ preparations: [] });
    await expect(promise).resolves.toEqual({ preparations: [] });
    const current = client.query({ ...options, staleTime: 0 });
    const checked = expect(current).resolves.toEqual({ preparations: [] });
    const pending = await vi.waitFor(() => backend.expectOne(base));
    await client.cancelQueries({ queryKey: options.queryKey });
    await checked;
    expect(pending.cancelled).toBe(true);
  });
  it('rejects malformed canonical response rather than inventing a READY value', async () => {
    const options = preparationOptions(
      http,
      client,
      identity.account_id,
      message.conversation_id,
      message.message_id,
      true,
    );
    const promise = client.query(options);
    const checked = expect(promise).rejects.toMatchObject({ code: 'invalid_response' });
    (await vi.waitFor(() => backend.expectOne(`${base}/${message.message_id}`))).flush({
      state: 'ready',
    });
    await checked;
  });
});
