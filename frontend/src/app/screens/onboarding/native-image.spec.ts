import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { describe, expect, it, vi } from 'vitest';
import { NativeImage } from './native-image';
import { NATIVE_RUNTIME } from '../../native-transport/runtime';
import { nativeFixture } from '../../native-transport/native-test.fixtures';
import { jpegBase64 } from '../../../../testing/image-fixture';
import { host } from './testing-host';
import { verifiedActor } from './onboarding.fixtures';

const imagePath = '/api/v1/media/00000000-0000-4000-8000-000000000001/display';
@Component({
  imports: [NativeImage],
  template: `<img [peerlyNativeImage]="path()" [nativeImageActor]="actor()" alt="Own photo" />`,
})
class Host {
  public readonly path = signal(imagePath);
  public readonly actor = signal<string | null>(verifiedActor.account_id);
}
function jpeg(): Blob {
  return new Blob([Uint8Array.from(atob(jpegBase64), (value) => value.charCodeAt(0))], {
    type: 'image/jpeg',
  });
}

describe('actual own-profile native img consumers', () => {
  it('never assigns a raw API URL in native mode; retires Blob URLs on epoch and destroy', async () => {
    const native = nativeFixture();
    await native.runtime.initialize();
    const client = new QueryClient();
    client.setQueryData(['session'], verifiedActor);
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTanStackQuery(client),
        { provide: NATIVE_RUNTIME, useValue: native.runtime },
      ],
    });
    const fixture = TestBed.createComponent(Host);
    const http = TestBed.inject(HttpTestingController);
    const revoked = vi.spyOn(URL, 'revokeObjectURL');
    fixture.detectChanges();
    const image: unknown = host(fixture).querySelector('img');
    if (!(image instanceof HTMLImageElement)) throw new Error('Expected native image');
    expect(image.getAttribute('src') ?? '').toBe('');
    const request = await vi.waitFor(() => http.expectOne(imagePath));
    request.flush(jpeg(), { headers: { 'Content-Type': 'image/jpeg' } });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(image.src).toMatch(/^blob:/);
    });
    const old = image.src;
    await native.runtime.transport.advance(false);
    fixture.detectChanges();
    expect(image.getAttribute('src') ?? '').toBe('');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(revoked).toHaveBeenCalledWith(old);
    });
    fixture.destroy();
    client.clear();
    http.verify({ ignoreCancelled: true });
    revoked.mockRestore();
  });

  it('physically cancels an image request on actor replacement and exposes no old bytes', async () => {
    const native = nativeFixture();
    await native.runtime.initialize();
    const client = new QueryClient();
    client.setQueryData(['session'], verifiedActor);
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTanStackQuery(client),
        { provide: NATIVE_RUNTIME, useValue: native.runtime },
      ],
    });
    const fixture = TestBed.createComponent(Host);
    const http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    const request = await vi.waitFor(() => http.expectOne(imagePath));
    client.setQueryData(['session'], {
      ...verifiedActor,
      account_id: '00000000-0000-4000-8000-000000000002',
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(request.cancelled).toBe(true);
    });
    const image: unknown = host(fixture).querySelector('img');
    expect(image instanceof HTMLImageElement && (image.getAttribute('src') ?? '')).toBe('');
    fixture.destroy();
    client.clear();
    http.verify();
  });

  it('keeps web src semantics without adding a private byte query', () => {
    const client = new QueryClient();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTanStackQuery(client),
        { provide: NATIVE_RUNTIME, useValue: null },
      ],
    });
    const fixture = TestBed.createComponent(Host);
    fixture.componentInstance.path.set(
      'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==',
    );
    fixture.detectChanges();
    const image: unknown = host(fixture).querySelector('img');
    expect(image instanceof HTMLImageElement && image.getAttribute('src')).toBe(
      fixture.componentInstance.path(),
    );
    expect(client.getQueryCache().getAll()).toEqual([]);
    fixture.destroy();
    client.clear();
  });
});

it.each([401, 403])('retires authority on native own-image denial %s', async (status) => {
  const native = nativeFixture();
  await native.runtime.initialize();
  const client = new QueryClient();
  client.setQueryData(['session'], verifiedActor);
  TestBed.configureTestingModule({
    providers: [
      provideHttpClient(),
      provideHttpClientTesting(),
      provideTanStackQuery(client),
      { provide: NATIVE_RUNTIME, useValue: native.runtime },
    ],
  });
  const fixture = TestBed.createComponent(Host);
  fixture.detectChanges();
  const http = TestBed.inject(HttpTestingController);
  const request = await vi.waitFor(() => http.expectOne(imagePath));
  request.flush(new Blob(), { status, statusText: 'Denied' });
  await vi.waitFor(() => {
    fixture.detectChanges();
    expect(
      client.getQueryCache().find({
        queryKey: [
          'account',
          verifiedActor.account_id,
          'native-own-image',
          imagePath,
          native.runtime.epoch(),
        ],
      })?.state.status,
    ).toBe('error');
  });
  expect(host(fixture).querySelector('img')?.getAttribute('src') ?? '').toBe('');
  fixture.destroy();
  client.clear();
  http.verify();
});
