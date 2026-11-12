import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, describe, expect, it } from 'vitest';
import { ObservationRelease, publicRelease } from './observation-release';

const origin = 'https://peerly.example';
const release = {
  releaseId: 'a'.repeat(40),
  origin,
  assets: [{ basename: 'main-ABC123.js', assetId: 0 }],
} as const;

describe('public release metadata boundary', () => {
  afterEach(() => TestBed.resetTestingModule());
  it('accepts only exact current-origin validated numeric asset mappings', () => {
    expect(publicRelease(release, origin)).toEqual(release);
    for (const invalid of [
      null,
      {},
      '<html>SPA fallback</html>',
      { ...release, extra: 'private' },
      { ...release, origin: 'https://other.example' },
      { ...release, releaseId: 'latest' },
      { ...release, assets: [{ basename: '../secret.js', assetId: 0 }] },
      { ...release, assets: [{ basename: 'main-ABC123.js', assetId: 1 }] },
      { ...release, assets: [{ basename: 'main-ABC123.js', assetId: 0, path: '/private' }] },
    ])
      expect(publicRelease(invalid, origin)).toBeNull();
  });
  it('uses only the approved same-origin path and fails frame-free on unavailable metadata', async () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    const source = TestBed.inject(ObservationRelease);
    const backend = TestBed.inject(HttpTestingController);
    expect(source.current()).toBeNull();
    const loaded = source.load();
    const request = backend.expectOne('/assets/observation-release.json');
    expect(request.request.method).toBe('GET');
    expect(request.request.headers.has('Authorization')).toBe(false);
    request.flush('missing', { status: 404, statusText: 'Not Found' });
    await loaded;
    expect(source.current()).toBeNull();
    backend.verify();
  });
  it('publishes validated metadata without depending on an authenticated session', async () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    const source = TestBed.inject(ObservationRelease);
    const backend = TestBed.inject(HttpTestingController);
    const loaded = source.load();
    backend
      .expectOne('/assets/observation-release.json')
      .flush({ ...release, origin: location.origin });
    await loaded;
    // Browser units may run on loopback HTTP; HTTPS-only validation remains in force.
    expect(source.current()).toEqual(
      publicRelease({ ...release, origin: location.origin }, location.origin),
    );
    backend.verify();
  });
});
