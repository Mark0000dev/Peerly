import { signal } from '@angular/core';
import { vi } from 'vitest';
import { nativeBuilds } from './config';
import type { NativeBuild } from './config';
import { NativeRuntime } from './runtime';
import type { NativeTransportPlugin } from './transport';

type Request = Parameters<NativeTransportPlugin['start']>[0];

// Controlled bridge boundary for Angular tests; never platform interoperability proof.
export function nativeFixture(build: Readonly<NativeBuild> = nativeBuilds.production) {
  const requests = signal<readonly Request[]>([]);
  const listeners = signal<readonly ((event: unknown) => void)[]>([]);
  const cancelled = vi.fn<NativeTransportPlugin['cancel']>().mockResolvedValue(undefined);
  const advance = vi.fn<NativeTransportPlugin['advance']>(() =>
    Promise.resolve({ epoch: crypto.randomUUID() }),
  );
  const configuration = vi.fn<NativeTransportPlugin['configuration']>(() => Promise.resolve(build));
  const plugin: NativeTransportPlugin = {
    configuration,
    advance,
    cancel: cancelled,
    start: (input) => {
      requests.update((current) => [...current, input]);
      return Promise.resolve();
    },
    addListener: (_name, accept) => {
      listeners.update((current) => [...current, accept]);
      return Promise.resolve({
        remove: () => {
          listeners.update((current) => current.filter((item) => item !== accept));
          return Promise.resolve();
        },
      });
    },
  };
  const errors = vi.fn();
  const runtime = new NativeRuntime(plugin, errors);
  const respond = (request: Readonly<Request>, status: number, value: unknown): void => {
    const emit = (type: string, fields: Readonly<Record<string, unknown>>): void => {
      for (const accept of listeners())
        accept({ id: request.id, epoch: request.epoch, type, ...fields });
    };
    emit('headers', { status, headers: { 'content-type': 'application/json' } });
    const text = value === null ? '' : JSON.stringify(value);
    emit('complete', { body: btoa(text) });
  };
  return { runtime, requests, cancelled, advance, configuration, errors, respond };
}
