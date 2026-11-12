import { HttpRequest } from '@angular/common/http';
import { firstValueFrom, of } from 'rxjs';
import { ErrorHandler } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it, vi } from 'vitest';

const bridge = vi.hoisted(() => ({
  native: vi.fn(() => false),
  configuration: vi.fn<() => Promise<unknown>>(),
  advance: vi.fn<() => Promise<Readonly<{ readonly epoch: string }>>>(),
  cancel: vi.fn<() => Promise<void>>(),
  start: vi.fn<() => Promise<void>>(),
}));
vi.mock('@capacitor/core', () => ({
  Capacitor: { isNativePlatform: bridge.native },
  registerPlugin: () => ({
    configuration: bridge.configuration,
    advance: bridge.advance,
    cancel: bridge.cancel,
    start: bridge.start,
    addListener: () => Promise.resolve({ remove: () => Promise.resolve() }),
  }),
}));
import { NATIVE_RUNTIME } from './runtime';
import { nativeBuilds } from './config';

describe('mounted native runtime provider', () => {
  it('does not construct the bridge for web', () => {
    bridge.native.mockReturnValue(false);
    expect(TestBed.inject(NATIVE_RUNTIME)).toBeNull();
  });
  it('uses the real native configuration and reports cleanup without exposing private values', async () => {
    bridge.native.mockReturnValue(true);
    bridge.configuration.mockResolvedValue(nativeBuilds.production);
    bridge.advance.mockResolvedValue({ epoch: crypto.randomUUID() });
    const report = vi.fn();
    TestBed.configureTestingModule({
      providers: [{ provide: ErrorHandler, useValue: { handleError: report } }],
    });
    const runtime = TestBed.inject(NATIVE_RUNTIME);
    if (runtime === null) throw new Error('Expected native runtime');
    await runtime.initialize();
    bridge.advance.mockRejectedValueOnce(new Error('synthetic private native failure'));
    await expect(runtime.transport.advance(true)).rejects.toThrow();
    bridge.advance.mockResolvedValue({ epoch: crypto.randomUUID() });
    await runtime.transport.advance(false);
    bridge.start.mockRejectedValue(new Error('synthetic start failure'));
    bridge.cancel.mockRejectedValue(new Error('synthetic private cookie failure'));
    await expect(
      firstValueFrom(runtime.transport.intercept(new HttpRequest('GET', '/api/v1/me'), () => of())),
    ).resolves.toMatchObject({ type: 0 });
    await vi.waitFor(() => {
      expect(report).toHaveBeenCalled();
    });
    expect(runtime.build().appId).toBe(nativeBuilds.production.appId);
  });
});
