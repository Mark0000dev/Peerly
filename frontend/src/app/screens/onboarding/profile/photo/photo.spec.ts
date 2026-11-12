import { By } from '@angular/platform-browser';
import { HttpClient } from '@angular/common/http';
import type { TestRequest } from '@angular/common/http/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, input, output } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { TuiRoot } from '@taiga-ui/core';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import type { Api } from '../../../../api.generated';
import { appConfig } from '../../../../app.config';
import { click, shown, host } from '../../testing-host';
import { verifiedActor } from '../../onboarding.fixtures';
import { PhotoWorkflow } from './photo';
import { sourceHash } from './image';
import { sessionOptions } from '../../../session';

const upload: Api['schemas']['PhotoUploadResponse'] = {
  id: '00000000-0000-0000-0000-000000000003',
  version: 1,
  state: 'uploading',
  content_type: 'image/png',
  size_bytes: 120,
  expected_photo_version: 0,
  failure: null,
  display_url: null,
  poll_after_ms: null,
  updated_at: '2026-11-07T12:00:00Z',
  upload_expires_at: '2026-11-07T12:10:00Z',
  processing_expires_at: '2026-11-07T12:20:00Z',
};
function createdPhoto(request: Readonly<TestRequest>): Api['schemas']['PhotoUploadResponse'] {
  const body: unknown = request.request.body;
  if (
    typeof body !== 'object' ||
    body === null ||
    !('size_bytes' in body) ||
    typeof body.size_bytes !== 'number' ||
    !('expected_photo_version' in body) ||
    typeof body.expected_photo_version !== 'number' ||
    !('content_type' in body) ||
    (body.content_type !== 'image/png' && body.content_type !== 'image/jpeg')
  )
    throw new Error('Invalid actual Start command');
  return {
    ...upload,
    size_bytes: body.size_bytes,
    content_type: body.content_type,
    expected_photo_version: body.expected_photo_version,
  };
}

const history = { photo: null, uploads: [{ upload, source_sha256: 'a'.repeat(64) }] };
@Component({
  selector: 'peerly-photo-test-host',
  imports: [TuiRoot, PhotoWorkflow],
  template:
    '<tui-root><peerly-photo [actor]="actor()" [checking]="checking()" [photoVersion]="version()" [currentPhoto]="photo()" (expired)="expired.emit()" (refreshProfile)="refreshed.emit()" /></tui-root>',
})
class PhotoTestHost {
  public readonly actor = input.required<Api['schemas']['IdentityResponse']>();
  public readonly version = input(0);
  public readonly checking = input(false);
  public readonly photo = input<Api['schemas']['CurrentPhotoResponse'] | null>(null);
  public readonly expired = output();
  public readonly refreshed = output();
}

describe('real photo recovery query boundary', () => {
  let fixture: ComponentFixture<PhotoTestHost>;
  let backend: HttpTestingController;
  let client: QueryClient;
  beforeEach(() => {
    client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    client.setQueryData(['session'], verifiedActor);
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideTanStackQuery(client)],
    });
    fixture = TestBed.createComponent(PhotoTestHost);
    fixture.componentRef.setInput('actor', verifiedActor);
    backend = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });
  afterEach(() => {
    try {
      fixture.destroy();
      client.clear();
      backend.verify();
    } finally {
      vi.restoreAllMocks();
      vi.unstubAllGlobals();
      TestBed.resetTestingModule();
    }
  });
  function workflow(): PhotoWorkflow {
    return fixture.debugElement.query(By.directive(PhotoWorkflow)).injector.get(PhotoWorkflow);
  }
  async function load(
    value: Readonly<Record<string, unknown>> = history,
    status = 200,
  ): Promise<void> {
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/media/uploads'));
    request.flush(value, { status, statusText: status === 200 ? 'OK' : 'Failure' });
    if (status === 200) {
      await vi.waitFor(() => {
        fixture.detectChanges();
        expect(host(fixture).textContent).not.toContain('Checking your recent photo uploads');
        const refresh = Array.from(host(fixture).querySelectorAll('button')).find(
          (button: Readonly<HTMLButtonElement>) =>
            button.textContent.trim() === 'Refresh recent uploads',
        );
        expect(refresh?.disabled).toBe(false);
      });
    } else await shown(fixture, 'We couldn’t load your recent uploads');
  }
  async function open(
    value: Readonly<Api['schemas']['PhotoUploadResponse']> = upload,
  ): Promise<void> {
    click(fixture, 'Check upload 1');
    const request = await vi.waitFor(() => backend.expectOne(`/api/v1/media/${upload.id}`));
    request.flush(value);
    await shown(
      fixture,
      value.state === 'uploading' ? 'Waiting for the file transfer.' : 'Your photo is saved.',
    );
    if (value.state === 'ready')
      await load({ photo: null, uploads: [{ upload: value, source_sha256: 'a'.repeat(64) }] });
  }
  it('loads only the owner projection and never automatically transfers or starts another intent', async () => {
    await load();
    await shown(fixture, 'Recent uploads');
    expect(host(fixture).textContent).not.toContain('a'.repeat(64));
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
    backend.expectNone(`/api/v1/media/uploads/${upload.id}/access`);
    expect(client.getQueryData(['account', verifiedActor.account_id, 'photo-uploads'])).toEqual(
      history,
    );
  });
  it('requires explicit reselection after reload, not an automatic empty upload', async () => {
    await load();
    await open();
    await shown(fixture, 'reselect the exact file');
    backend.expectNone(`/api/v1/media/uploads/${upload.id}/access`);
    click(fixture, 'Check photo status');
    const request = await vi.waitFor(() => backend.expectOne(`/api/v1/media/${upload.id}`));
    request.flush(upload);
  });
  it('recovers an already READY outcome rather than claiming cancellation', async () => {
    const refreshed = vi.fn();
    fixture.componentInstance.refreshed.subscribe(refreshed);
    await load();
    await open({ ...upload, state: 'ready', display_url: `/api/v1/media/${upload.id}/display` });
    await vi.waitFor(() => {
      expect(refreshed).toHaveBeenCalled();
    });
    expect(host(fixture).textContent).not.toContain('Cancel upload');
  });
  it('cancels explicitly with CSRF/idempotency and respects finalization winning the race', async () => {
    await load();
    await open();
    click(fixture, 'Cancel upload');
    const command = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/cancel`),
    );
    expect(command.request.headers.get('x-csrf-token')).toBe(verifiedActor.csrf_token);
    expect(command.request.headers.get('idempotency-key')).toMatch(/^[a-f0-9-]{36}$/);
    const ready = {
      ...upload,
      state: 'ready',
      display_url: `/api/v1/media/${upload.id}/display`,
    } as const;
    expect(workflow().hasUnconfirmedAction).toBe(true);
    command.flush(ready);
    const requests = await Promise.all([
      vi.waitFor(() => backend.expectOne({ url: '/api/v1/media/uploads', method: 'GET' })),
      vi.waitFor(() => backend.expectOne({ url: `/api/v1/media/${upload.id}`, method: 'GET' })),
    ]);
    for (const request of requests)
      request.flush(
        request.request.url === '/api/v1/media/uploads'
          ? { ...history, uploads: [{ ...history.uploads[0], upload: ready }] }
          : ready,
      );
    await shown(fixture, 'Your photo is saved.');
    await load({ photo: null, uploads: [{ upload: ready, source_sha256: 'a'.repeat(64) }] });
    expect(host(fixture).textContent).not.toContain('This upload was cancelled.');
  });
  it('shows projection failure and permits an explicit retry', async () => {
    await load({ code: 'unavailable' }, 503);
    click(fixture, 'Refresh recent uploads');
    await load({ photo: null, uploads: [] });
    expect(host(fixture).textContent).not.toContain('Recent uploads');
  });
  async function photoFile(): Promise<File> {
    const canvas = new OffscreenCanvas(32, 32);
    const context = canvas.getContext('2d');
    if (context === null) throw new Error('Native canvas unavailable');
    context.putImageData(
      new ImageData(
        Uint8ClampedArray.from({ length: 32 * 32 * 4 }, (_, index) => {
          const x = Math.floor(index / 4) % 32;
          return index % 4 === 3 ? 255 : index % 4 === 0 ? x * 8 : 0;
        }),
        32,
        32,
      ),
      0,
      0,
    );
    const blob = await canvas.convertToBlob({ type: 'image/png' });
    return new File([blob], 'photo.png', { type: 'image/png' });
  }
  function pickFile(file: Readonly<File>): void {
    const transfer = new DataTransfer();
    transfer.items.add(file);
    const input = host(fixture).querySelector('input[type="file"]');
    if (!(input instanceof HTMLInputElement)) throw new Error('Expected native file chooser');
    vi.spyOn(input, 'files', 'get').mockReturnValue(transfer.files);
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }
  async function choosePhoto(selected?: Readonly<File>): Promise<File> {
    const file = selected ?? (await photoFile());
    pickFile(file);
    await shown(fixture, 'Use the original without cropping');
    return file;
  }
  it('rejects changed final bytes before accessing or overwriting an existing upload', async () => {
    await load();
    await open();
    await choosePhoto();
    click(fixture, 'Use the original without cropping');
    await shown(fixture, 'This file does not match that upload');
    backend.expectNone(`/api/v1/media/uploads/${upload.id}/access`);
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
    expect(host(fixture).textContent).toContain('Cancel upload');
  });
  it('keeps the actual selected File and crop through a same-actor sign-in check, while every private command stays paused', async () => {
    await load({ photo: null, uploads: [] });
    expect(workflow().hasLocalDraft).toBe(false);
    const file = await choosePhoto();
    expect(workflow().hasLocalDraft).toBe(true);
    expect(workflow().hasUnconfirmedAction).toBe(false);
    const canvas = host(fixture).querySelector('canvas');
    fixture.componentRef.setInput('checking', true);
    fixture.detectChanges();
    client.removeQueries({ queryKey: ['account', verifiedActor.account_id] });
    const rotated = { ...verifiedActor, csrf_token: 'fresh-after-check' };
    client.setQueryData(['session'], rotated);
    fixture.componentRef.setInput('actor', rotated);
    fixture.detectChanges();
    expect(host(fixture).querySelector('canvas')).toBe(canvas);
    click(fixture, 'Use the original without cropping');
    backend.expectNone((request) => request.method !== 'GET');
    fixture.componentRef.setInput('checking', false);
    fixture.detectChanges();
    await load({ photo: null, uploads: [] });
    expect(host(fixture).querySelector('canvas')).toBe(canvas);
    click(fixture, 'Use the original without cropping');
    const request = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/media/uploads', method: 'POST' }),
    );
    expect(request.request.body).toEqual({
      expected_photo_version: 0,
      size_bytes: file.size,
      sha256: await sourceHash(file),
      content_type: 'image/png',
    });
    expect(request.request.headers.get('x-csrf-token')).toBe(rotated.csrf_token);
    expect(workflow().hasUnconfirmedAction).toBe(true);
    request.flush({ code: 'unavailable' }, { status: 503, statusText: 'Failure' });
    await shown(fixture, 'We couldn’t confirm the photo request.');
    expect(workflow().hasLocalDraft).toBe(true);
    expect(workflow().hasUnconfirmedAction).toBe(true);
    backend.expectNone(`/api/v1/media/uploads/${upload.id}/access`);
  });
  it('accepts an owned Start receipt during an unknown-session pause but requires an explicit fresh-authority action before bytes are sent', async () => {
    await load({ photo: null, uploads: [] });
    const file = await choosePhoto();
    click(fixture, 'Use the original without cropping');
    const start = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/media/uploads', method: 'POST' }),
    );
    fixture.componentRef.setInput('checking', true);
    fixture.detectChanges();
    const created = createdPhoto(start);
    start.flush(created);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(client.getMutationCache().getAll().at(-1)?.state.status).toBe('success');
    });
    backend.expectNone(`/api/v1/media/uploads/${upload.id}/access`);
    backend.expectNone('/api/v1/media/uploads');
    fixture.componentRef.setInput('checking', false);
    fixture.detectChanges();
    await settle(created, await sourceHash(file));
    await shown(fixture, 'Your photo upload paused before processing could be confirmed.');
    backend.expectNone(`/api/v1/media/uploads/${upload.id}/access`);
    await vi.waitFor(() => {
      fixture.detectChanges();
      const retry = Array.from(host(fixture).querySelectorAll('button')).find(
        (button: Readonly<HTMLButtonElement>) =>
          button.textContent.trim() === 'Resume selected photo',
      );
      expect(retry?.disabled).toBe(false);
    });
    click(fixture, 'Resume selected photo');
    const ticket = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/access`),
    );
    expect(ticket.request.headers.get('x-csrf-token')).toBe(verifiedActor.csrf_token);
    ticket.flush({ code: 'media_storage_unavailable' }, { status: 503, statusText: 'Failure' });
    await shown(fixture, 'We couldn’t access this upload.');
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
  });
  it('requires an explicit confirmation after choosing a file, with real accessible crop controls', async () => {
    await load({ photo: null, uploads: [] });
    await choosePhoto();
    click(fixture, 'Zoom in');
    click(fixture, 'Right');
    click(fixture, 'Reset crop');
    const preview = host(fixture).querySelector('canvas');
    if (!(preview instanceof HTMLCanvasElement)) throw new Error('Expected crop canvas');
    preview.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true, cancelable: true }),
    );
    preview.dispatchEvent(
      new KeyboardEvent('keydown', { key: '+', bubbles: true, cancelable: true }),
    );
    preview.dispatchEvent(
      new KeyboardEvent('keydown', { key: '0', bubbles: true, cancelable: true }),
    );
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
    click(fixture, 'Cancel');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).not.toContain('Use the original without cropping');
    });
  });
  it('continues the matching final payload under the existing intent, with no duplicate Start', async () => {
    const file = await photoFile();
    const matching = { ...upload, size_bytes: file.size };
    const resumable = {
      photo: null,
      uploads: [{ upload: matching, source_sha256: await sourceHash(file) }],
    };
    await load(resumable);
    await open(matching);
    await choosePhoto(file);
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetcher);
    click(fixture, 'Use the original without cropping');
    const ticket = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/access`),
    );
    ticket.flush({ url: 'https://storage.invalid/fixture', fields: { policy: 'opaque-fixture' } });
    const finalization = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/finalize`),
    );
    expect(finalization.request.headers.get('idempotency-key')).toMatch(/^[a-f0-9-]{36}$/);
    const queued = { ...matching, state: 'queued' } as const;
    finalization.flush(queued);
    const requests = await Promise.all([
      vi.waitFor(() => backend.expectOne({ url: '/api/v1/media/uploads', method: 'GET' })),
      vi.waitFor(() => backend.expectOne({ url: `/api/v1/media/${upload.id}`, method: 'GET' })),
    ]);
    for (const request of requests)
      request.flush(
        request.request.url === '/api/v1/media/uploads'
          ? { ...resumable, uploads: [{ ...resumable.uploads[0], upload: queued }] }
          : queued,
      );
    await shown(fixture, 'Your photo is waiting for processing.');
    expect(workflow().hasLocalDraft).toBe(false);
    expect(workflow().hasUnconfirmedAction).toBe(false);
    expect(fetcher).toHaveBeenCalledOnce();
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
  });
  for (const scenario of [
    { state: 'queued', text: 'Your photo is waiting for processing.' },
    { state: 'processing', text: 'Your photo is being processed.' },
    { state: 'rejected', text: 'We couldn’t use this photo.' },
    { state: 'expired', text: 'This upload expired.' },
    { state: 'cancelled', text: 'This upload was cancelled.' },
  ] as const) {
    it(`projects actual ${scenario.state} without a fabricated progress estimate`, async () => {
      await load();
      click(fixture, 'Check upload 1');
      const request = await vi.waitFor(() => backend.expectOne(`/api/v1/media/${upload.id}`));
      request.flush({ ...upload, state: scenario.state });
      await shown(fixture, scenario.text);
      expect(host(fixture).textContent).not.toContain('Waiting for the file transfer.');
      expect(host(fixture).textContent).not.toContain('few seconds');
    });
  }
  for (const failure of ['storage_unavailable', 'processing_unavailable'] as const) {
    it(`distinguishes ${failure} from a bad photo without retrying automatically`, async () => {
      await load();
      click(fixture, 'Check upload 1');
      const request = await vi.waitFor(() => backend.expectOne(`/api/v1/media/${upload.id}`));
      request.flush({ ...upload, state: 'rejected', failure });
      await shown(fixture, 'This upload wasn’t saved.');
      expect(host(fixture).textContent).toContain(
        failure === 'storage_unavailable'
          ? 'Photo storage is temporarily unavailable.'
          : 'Photo processing is temporarily unavailable.',
      );
      expect(host(fixture).textContent).toContain('try uploading the same photo again later');
      expect(host(fixture).textContent).not.toContain('We couldn’t use this photo.');
      expect(host(fixture).textContent).not.toContain('Choose another JPEG or PNG');
      backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
    });
  }
  it('clears private cached work on an actual authorization failure', async () => {
    const expired = vi.fn();
    fixture.componentInstance.expired.subscribe(expired);
    await load({ code: 'session_required' }, 401);
    await vi.waitFor(() => {
      expect(expired).toHaveBeenCalled();
    });
    expect(
      client.getQueryData(['account', verifiedActor.account_id, 'photo-uploads']),
    ).toBeUndefined();
  });
  it('aborts the old actor read before switching to a separately scoped projection', async () => {
    const old = await vi.waitFor(() => backend.expectOne('/api/v1/media/uploads'));
    client.setQueryData(['session'], { ...verifiedActor, account_id: 'new-account' });
    fixture.componentRef.setInput('actor', { ...verifiedActor, account_id: 'new-account' });
    fixture.detectChanges();
    await vi.waitFor(() => {
      expect(old.cancelled).toBe(true);
    });
    await load({ photo: null, uploads: [] });
    expect(client.getQueryData(['account', 'new-account', 'photo-uploads'])).toEqual({
      photo: null,
      uploads: [],
    });
    expect(host(fixture).textContent).not.toContain('Recent uploads');
  });
  it('reports a bad file without creating a new intent or leaving an old crop', async () => {
    await load({ photo: null, uploads: [] });
    const input = host(fixture).querySelector('input[type="file"]');
    if (!(input instanceof HTMLInputElement)) throw new Error('Expected native file chooser');
    const transfer = new DataTransfer();
    transfer.items.add(new File(['not an image'], 'photo.png', { type: 'image/png' }));
    vi.spyOn(input, 'files', 'get').mockReturnValue(transfer.files);
    input.dispatchEvent(new Event('change', { bubbles: true }));
    await shown(fixture, 'Choose a JPEG or PNG photo, up to 10 MB.');
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
    expect(host(fixture).querySelector('canvas')).toBeNull();
  });
  it('repositions selected pixels using the public Taiga pan directive', async () => {
    await load({ photo: null, uploads: [] });
    await choosePhoto();
    click(fixture, 'Zoom in');
    const canvas = host(fixture).querySelector('canvas');
    if (!(canvas instanceof HTMLCanvasElement)) throw new Error('Expected crop canvas');
    const context = canvas.getContext('2d');
    if (context === null) throw new Error('Native canvas unavailable');
    const before = context.getImageData(160, 160, 1, 1).data[0];
    canvas.dispatchEvent(new MouseEvent('mousedown', { clientX: 0, clientY: 0, bubbles: true }));
    document.dispatchEvent(new MouseEvent('mousemove', { clientX: 0, clientY: 0, bubbles: true }));
    document.dispatchEvent(new MouseEvent('mousemove', { clientX: 60, clientY: 0, bubbles: true }));
    document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
    expect(context.getImageData(160, 160, 1, 1).data[0]).not.toBe(before);
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
  });
  async function settle(
    status: Readonly<Api['schemas']['PhotoUploadResponse']>,
    hash: string,
  ): Promise<void> {
    const requests = await Promise.all([
      vi.waitFor(() => backend.expectOne({ url: '/api/v1/media/uploads', method: 'GET' })),
      vi.waitFor(() => backend.expectOne({ url: `/api/v1/media/${upload.id}`, method: 'GET' })),
    ]);
    for (const request of requests)
      request.flush(
        request.request.url === '/api/v1/media/uploads'
          ? { photo: null, uploads: [{ upload: status, source_sha256: hash }] }
          : status,
      );
    if (status.state === 'ready')
      await load({ photo: null, uploads: [{ upload: status, source_sha256: hash }] });
  }
  it('starts a new photo with final byte metadata and resolves an uncertain Start with the exact same intent', async () => {
    await load({ photo: null, uploads: [] });
    const file = await choosePhoto();
    click(fixture, 'Use the original without cropping');
    const first = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/media/uploads', method: 'POST' }),
    );
    const hash = await sourceHash(file);
    expect(first.request.body).toEqual({
      expected_photo_version: 0,
      size_bytes: file.size,
      sha256: hash,
      content_type: 'image/png',
    });
    const key = first.request.headers.get('idempotency-key');
    expect(key).toMatch(/^[a-f0-9-]{36}$/);
    first.flush({ code: 'temporarily_unavailable' }, { status: 503, statusText: 'Failure' });
    await shown(fixture, 'We couldn’t confirm the photo request.');
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
    click(fixture, 'Retry photo request');
    const retry = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/media/uploads', method: 'POST' }),
    );
    expect(retry.request.headers.get('idempotency-key')).toBe(key);
    expect(retry.request.body).toEqual(first.request.body);
    const started = { ...upload, size_bytes: file.size };
    retry.flush(started);
    await settle(
      { ...started, state: 'ready', display_url: `/api/v1/media/${upload.id}/display` },
      hash,
    );
    await shown(fixture, 'Your photo is saved.');
    backend.expectNone(`/api/v1/media/uploads/${upload.id}/access`);
  });
  it('retries an uncertain finalization with its original idempotency key and no second transfer', async () => {
    const file = await photoFile();
    const hash = await sourceHash(file);
    const matching = { ...upload, size_bytes: file.size };
    await load({ photo: null, uploads: [{ upload: matching, source_sha256: hash }] });
    await open(matching);
    await choosePhoto(file);
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetcher);
    click(fixture, 'Use the original without cropping');
    const access = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/access`),
    );
    access.flush({ url: 'https://storage.invalid/fixture', fields: { policy: 'opaque-fixture' } });
    const finalization = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/finalize`),
    );
    const key = finalization.request.headers.get('idempotency-key');
    await shown(fixture, 'Starting photo processing…');
    expect(workflow().hasUnconfirmedAction).toBe(true);
    expect(host(fixture).textContent).not.toContain('Waiting for the file transfer.');
    expect(host(fixture).textContent).not.toContain('To continue this upload, reselect');
    finalization.flush({ code: 'unavailable' }, { status: 503, statusText: 'Failure' });
    await shown(fixture, 'We couldn’t confirm processing started.');
    expect(workflow().hasUnconfirmedAction).toBe(true);
    expect(host(fixture).textContent).not.toContain('Waiting for the file transfer.');
    expect(host(fixture).textContent).not.toContain('To continue this upload, reselect');
    click(fixture, 'Retry finalization');
    click(fixture, 'Retry finalization');
    const retry = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/finalize`),
    );
    expect(retry.request.headers.get('idempotency-key')).toBe(key);
    const queued = { ...matching, state: 'queued' } as const;
    retry.flush(queued);
    await settle(queued, hash);
    await shown(fixture, 'Your photo is waiting for processing.');
    expect(fetcher).toHaveBeenCalledOnce();
  });
  it('retries uncertain cancellation with the original key rather than claiming it succeeded', async () => {
    await load();
    await open();
    click(fixture, 'Cancel upload');
    const first = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/cancel`),
    );
    const key = first.request.headers.get('idempotency-key');
    first.flush({ code: 'unavailable' }, { status: 503, statusText: 'Failure' });
    await shown(fixture, 'We couldn’t confirm cancellation.');
    expect(workflow().hasUnconfirmedAction).toBe(true);
    expect(host(fixture).textContent).not.toContain('This upload was cancelled.');
    click(fixture, 'Cancel upload');
    const retry = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/cancel`),
    );
    expect(retry.request.headers.get('idempotency-key')).toBe(key);
    const cancelled = { ...upload, state: 'cancelled' } as const;
    retry.flush(cancelled);
    await settle(cancelled, 'a'.repeat(64));
    await shown(fixture, 'This upload was cancelled.');
  });
  it('reloads an actual photo CAS conflict before creating an explicit new intent', async () => {
    await load({ photo: null, uploads: [] });
    const file = await choosePhoto();
    click(fixture, 'Use the original without cropping');
    const first = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/media/uploads', method: 'POST' }),
    );
    const oldKey = first.request.headers.get('idempotency-key');
    first.flush({ code: 'photo_version_conflict' }, { status: 409, statusText: 'Conflict' });
    await shown(fixture, 'Your photo changed elsewhere.');
    click(fixture, 'Reload current photo');
    await load({
      photo: {
        upload_id: upload.id,
        version: 3,
        display_url: `/api/v1/media/${upload.id}/display`,
      },
      uploads: [],
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).not.toContain('Your photo changed elsewhere.');
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).querySelector('canvas')).toBeNull();
    });
    click(fixture, 'Edit selected photo');
    await shown(fixture, 'Use the original without cropping');
    click(fixture, 'Use the original without cropping');
    const next = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/media/uploads', method: 'POST' }),
    );
    expect(next.request.body).toEqual({
      expected_photo_version: 3,
      size_bytes: file.size,
      sha256: await sourceHash(file),
      content_type: 'image/png',
    });
    expect(next.request.headers.get('idempotency-key')).not.toBe(oldKey);
    next.flush({ code: 'unavailable' }, { status: 503, statusText: 'Failure' });
    await shown(fixture, 'We couldn’t confirm the photo request.');
  });
  it('revokes local file draft on a Start401 and never contacts storage', async () => {
    const expired = vi.fn();
    fixture.componentInstance.expired.subscribe(expired);
    await load({ photo: null, uploads: [] });
    await choosePhoto();
    click(fixture, 'Use the original without cropping');
    const request = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/media/uploads', method: 'POST' }),
    );
    request.flush({ code: 'session_required' }, { status: 401, statusText: 'Unauthenticated' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(expired).toHaveBeenCalled();
    });
    expect(host(fixture).textContent).not.toContain('Edit selected photo');
    backend.expectNone(`/api/v1/media/uploads/${upload.id}/access`);
  });
  it('opens camera or file selection only after their explicit native actions', async () => {
    await load({ photo: null, uploads: [] });
    const inputs = Array.from(
      host(fixture).querySelectorAll<HTMLInputElement>('input[type="file"]'),
    );
    const file = inputs[0];
    const camera = inputs[1];
    if (file === undefined || camera === undefined) throw new Error('Missing native chooser');
    const fileClick = vi.spyOn(file, 'click').mockImplementation(() => undefined);
    const cameraClick = vi.spyOn(camera, 'click').mockImplementation(() => undefined);
    expect(fileClick).not.toHaveBeenCalled();
    expect(cameraClick).not.toHaveBeenCalled();
    click(fixture, 'Choose photo');
    expect(fileClick).toHaveBeenCalledOnce();
    expect(cameraClick).not.toHaveBeenCalled();
    click(fixture, 'Take photo');
    expect(cameraClick).toHaveBeenCalledOnce();
    expect(camera.getAttribute('capture')).toBe('user');
  });
  for (const error of [
    new DOMException('Unreadable', 'InvalidStateError'),
    new TypeError('Invalid source'),
  ]) {
    it(`reports a native decode ${error.name} without uploading anything`, async () => {
      await load({ photo: null, uploads: [] });
      vi.spyOn(globalThis, 'createImageBitmap').mockRejectedValue(error);
      pickFile(await photoFile());
      await shown(fixture, 'Choose a JPEG or PNG photo, up to 10 MB.');
      backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
    });
  }
  it('closes a late decoded bitmap after actor replacement without publishing the old draft', async () => {
    await load({ photo: null, uploads: [] });
    const file = await photoFile();
    const bitmap = await createImageBitmap(file);
    const closed = vi.spyOn(bitmap, 'close');
    let resolve: (value: ImageBitmap) => void = () => {
      throw new Error('Missing decoder gate');
    };
    const pending = new Promise<ImageBitmap>((done) => {
      resolve = done;
    });
    const decode = vi.spyOn(globalThis, 'createImageBitmap').mockReturnValue(pending);
    pickFile(file);
    await vi.waitFor(() => {
      expect(decode).toHaveBeenCalledOnce();
    });
    client.setQueryData(['session'], { ...verifiedActor, account_id: 'replacement' });
    fixture.componentRef.setInput('actor', { ...verifiedActor, account_id: 'replacement' });
    fixture.detectChanges();
    await load({ photo: null, uploads: [] });
    resolve(bitmap);
    await vi.waitFor(() => {
      expect(closed).toHaveBeenCalledOnce();
    });
    expect(host(fixture).querySelector('canvas')).toBeNull();
  });
  for (const status of [200, 401, 503]) {
    it(`ignores a late old actor Start${String(status)} without transferring or expiring the replacement`, async () => {
      const expired = vi.fn();
      fixture.componentInstance.expired.subscribe(expired);
      await load({ photo: null, uploads: [] });
      await choosePhoto();
      click(fixture, 'Use the original without cropping');
      const old = await vi.waitFor(() =>
        backend.expectOne({ url: '/api/v1/media/uploads', method: 'POST' }),
      );
      client.setQueryData(['session'], { ...verifiedActor, account_id: 'replacement' });
      fixture.componentRef.setInput('actor', { ...verifiedActor, account_id: 'replacement' });
      fixture.detectChanges();
      await load({ photo: null, uploads: [] });
      old.flush(status === 200 ? createdPhoto(old) : { code: 'unavailable' }, {
        status,
        statusText: status === 200 ? 'OK' : 'Failure',
      });
      await vi.waitFor(() => {
        expect(client.getMutationCache().getAll()[0]?.state.status).toBe(
          status === 200 ? 'success' : 'error',
        );
      });
      await shown(fixture, 'Choose photo');
      expect(expired).not.toHaveBeenCalled();
      expect(host(fixture).textContent).not.toContain('Edit selected photo');
      backend.expectNone(`/api/v1/media/uploads/${upload.id}/access`);
    });
  }
  it('supports all documented crop keys and leaves unrelated keyboard input alone', async () => {
    await load({ photo: null, uploads: [] });
    await choosePhoto();
    const canvas = host(fixture).querySelector('canvas');
    if (!(canvas instanceof HTMLCanvasElement)) throw new Error('Expected crop canvas');
    for (const key of ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', '=', '-', '0', 'Tab']) {
      const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
      canvas.dispatchEvent(event);
      expect(event.defaultPrevented).toBe(key !== 'Tab');
    }
  });
  it('creates a cropped JPEG only once and safely retries an uncertain transfer on the known intent', async () => {
    await load({ photo: null, uploads: [] });
    await choosePhoto();
    const fetcher = vi.fn<typeof fetch>().mockRejectedValue(new TypeError('fixture network loss'));
    vi.stubGlobal('fetch', fetcher);
    click(fixture, 'Use photo');
    click(fixture, 'Use photo');
    const start = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/media/uploads', method: 'POST' }),
    );
    const body: unknown = start.request.body;
    if (
      typeof body !== 'object' ||
      body === null ||
      !('sha256' in body) ||
      typeof body.sha256 !== 'string' ||
      !('size_bytes' in body) ||
      typeof body.size_bytes !== 'number'
    )
      throw new Error('Invalid native payload');
    expect(body).toMatchObject({ content_type: 'image/jpeg', expected_photo_version: 0 });
    const cropped = { ...upload, size_bytes: body.size_bytes, content_type: 'image/jpeg' } as const;
    start.flush(cropped);
    await settle(cropped, body.sha256);
    const access = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/access`),
    );
    access.flush({ url: 'https://storage.invalid/fixture', fields: {} });
    await shown(fixture, 'We couldn’t confirm the file transfer.');
    click(fixture, 'Retry selected file');
    click(fixture, 'Retry selected file');
    const retry = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/access`),
    );
    retry.flush({ url: 'https://storage.invalid/fixture', fields: {} });
    await vi.waitFor(() => {
      expect(fetcher).toHaveBeenCalledTimes(2);
    });
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
  });
  it('aborts an in-flight native transfer when cancellation is requested and never finalizes it', async () => {
    const file = await photoFile();
    const hash = await sourceHash(file);
    const matching = { ...upload, size_bytes: file.size };
    await load({ photo: null, uploads: [{ upload: matching, source_sha256: hash }] });
    await open(matching);
    await choosePhoto(file);
    const fetcher = vi.fn<typeof fetch>().mockImplementation(
      (_url: Readonly<RequestInfo | URL>, options?: Readonly<RequestInit>) =>
        new Promise((_resolve, reject) => {
          options?.signal?.addEventListener(
            'abort',
            () => {
              reject(new TypeError('fixture aborted'));
            },
            { once: true },
          );
        }),
    );
    vi.stubGlobal('fetch', fetcher);
    click(fixture, 'Use the original without cropping');
    const access = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/access`),
    );
    access.flush({ url: 'https://storage.invalid/fixture', fields: {} });
    await vi.waitFor(() => {
      expect(fetcher).toHaveBeenCalledOnce();
      fixture.detectChanges();
    });
    click(fixture, 'Cancel upload');
    const cancel = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/cancel`),
    );
    const cancelled = { ...matching, state: 'cancelled' } as const;
    cancel.flush(cancelled);
    await settle(cancelled, hash);
    await shown(fixture, 'This upload was cancelled.');
    expect(fetcher.mock.calls[0]?.[1]?.signal?.aborted).toBe(true);
    backend.expectNone(`/api/v1/media/uploads/${upload.id}/finalize`);
  });
  it('handles a native crop encoding failure without creating an upload', async () => {
    await load({ photo: null, uploads: [] });
    await choosePhoto();
    vi.spyOn(OffscreenCanvas.prototype, 'convertToBlob').mockRejectedValue(
      new DOMException('fixture failed', 'EncodingError'),
    );
    click(fixture, 'Use photo');
    await shown(fixture, 'We couldn’t prepare this file.');
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
    expect(host(fixture).querySelector('canvas')).not.toBeNull();
  });
  it('rejects unreadable final bytes without starting an upload', async () => {
    await load({ photo: null, uploads: [] });
    await choosePhoto();
    vi.spyOn(Blob.prototype, 'arrayBuffer').mockRejectedValue(
      new DOMException('fixture unreadable', 'NotReadableError'),
    );
    click(fixture, 'Use the original without cropping');
    await shown(fixture, 'We couldn’t read this file.');
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
  });
  it('rejects malformed native encoder output before any upload intent', async () => {
    await load({ photo: null, uploads: [] });
    await choosePhoto();
    vi.spyOn(OffscreenCanvas.prototype, 'convertToBlob').mockResolvedValue(
      new Blob(['invalid output'], { type: 'image/jpeg' }),
    );
    click(fixture, 'Use photo');
    await shown(fixture, 'Choose a JPEG or PNG photo, up to 10 MB.');
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
  });
  for (const status of [200, 401, 503]) {
    it(`ignores late old actor cancel${String(status)} without affecting the replacement`, async () => {
      const expired = vi.fn();
      fixture.componentInstance.expired.subscribe(expired);
      await load();
      await open();
      click(fixture, 'Cancel upload');
      click(fixture, 'Cancel upload');
      const old = await vi.waitFor(() =>
        backend.expectOne(`/api/v1/media/uploads/${upload.id}/cancel`),
      );
      client.setQueryData(['session'], { ...verifiedActor, account_id: 'replacement' });
      fixture.componentRef.setInput('actor', { ...verifiedActor, account_id: 'replacement' });
      fixture.detectChanges();
      await load({ photo: null, uploads: [] });
      old.flush(status === 200 ? { ...upload, state: 'cancelled' } : { code: 'unavailable' }, {
        status,
        statusText: status === 200 ? 'OK' : 'Failure',
      });
      await vi.waitFor(() => {
        expect(client.getMutationCache().getAll()[0]?.state.status).toBe(
          status === 200 ? 'success' : 'error',
        );
      });
      expect(expired).not.toHaveBeenCalled();
      backend.expectNone('/api/v1/media/uploads');
    });
  }
  for (const status of [200, 401, 503]) {
    it(`ignores late old actor finalize${String(status)} and never refetches into a replacement account`, async () => {
      const expired = vi.fn();
      fixture.componentInstance.expired.subscribe(expired);
      const file = await photoFile();
      const hash = await sourceHash(file);
      const matching = { ...upload, size_bytes: file.size };
      await load({ photo: null, uploads: [{ upload: matching, source_sha256: hash }] });
      await open(matching);
      await choosePhoto(file);
      vi.stubGlobal(
        'fetch',
        vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 204 })),
      );
      click(fixture, 'Use the original without cropping');
      const access = await vi.waitFor(() =>
        backend.expectOne(`/api/v1/media/uploads/${upload.id}/access`),
      );
      access.flush({ url: 'https://storage.invalid/fixture', fields: {} });
      const old = await vi.waitFor(() =>
        backend.expectOne(`/api/v1/media/uploads/${upload.id}/finalize`),
      );
      client.setQueryData(['session'], { ...verifiedActor, account_id: 'replacement' });
      fixture.componentRef.setInput('actor', { ...verifiedActor, account_id: 'replacement' });
      fixture.detectChanges();
      await load({ photo: null, uploads: [] });
      old.flush(status === 200 ? { ...matching, state: 'queued' } : { code: 'unavailable' }, {
        status,
        statusText: status === 200 ? 'OK' : 'Failure',
      });
      await vi.waitFor(() => {
        expect(client.getMutationCache().getAll()[0]?.state.status).toBe(
          status === 200 ? 'success' : 'error',
        );
      });
      expect(expired).not.toHaveBeenCalled();
      backend.expectNone('/api/v1/media/uploads');
    });
  }
  it('discards a crop finishing after actor replacement without hashing or starting it', async () => {
    await load({ photo: null, uploads: [] });
    await choosePhoto();
    let resolve: (value: Blob) => void = () => {
      throw new Error('Missing encoder gate');
    };
    const pending = new Promise<Blob>((done) => {
      resolve = done;
    });
    const encoder = vi.spyOn(OffscreenCanvas.prototype, 'convertToBlob').mockReturnValue(pending);
    click(fixture, 'Use photo');
    await vi.waitFor(() => {
      expect(encoder).toHaveBeenCalledOnce();
    });
    client.setQueryData(['session'], { ...verifiedActor, account_id: 'replacement' });
    fixture.componentRef.setInput('actor', { ...verifiedActor, account_id: 'replacement' });
    fixture.detectChanges();
    await load({ photo: null, uploads: [] });
    resolve(new Blob(['old private bytes'], { type: 'image/jpeg' }));
    await shown(fixture, 'Choose photo');
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
    expect(host(fixture).textContent).not.toContain('Edit selected photo');
  });
  it('aborts the owned transfer on component destruction and never finalizes after teardown', async () => {
    const file = await photoFile();
    const hash = await sourceHash(file);
    const matching = { ...upload, size_bytes: file.size };
    await load({ photo: null, uploads: [{ upload: matching, source_sha256: hash }] });
    await open(matching);
    await choosePhoto(file);
    const fetcher = vi.fn<typeof fetch>().mockImplementation(
      (_url: Readonly<RequestInfo | URL>, options?: Readonly<RequestInit>) =>
        new Promise((_resolve, reject) => {
          options?.signal?.addEventListener(
            'abort',
            () => {
              reject(new TypeError('fixture aborted'));
            },
            { once: true },
          );
        }),
    );
    vi.stubGlobal('fetch', fetcher);
    click(fixture, 'Use the original without cropping');
    const access = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/access`),
    );
    access.flush({ url: 'https://storage.invalid/fixture', fields: {} });
    await vi.waitFor(() => {
      expect(fetcher).toHaveBeenCalledOnce();
    });
    fixture.destroy();
    await vi.waitFor(() => {
      expect(fetcher.mock.calls[0]?.[1]?.signal?.aborted).toBe(true);
    });
    backend.expectNone(`/api/v1/media/uploads/${upload.id}/finalize`);
  });
  it('does not start an old actor upload when hashing finishes after account replacement', async () => {
    await load({ photo: null, uploads: [] });
    await choosePhoto();
    let resolve: (value: ArrayBuffer) => void = () => {
      throw new Error('Missing digest gate');
    };
    const pending = new Promise<ArrayBuffer>((done) => {
      resolve = done;
    });
    const digest = vi.spyOn(crypto.subtle, 'digest').mockReturnValue(pending);
    click(fixture, 'Use the original without cropping');
    await vi.waitFor(() => {
      expect(digest).toHaveBeenCalledOnce();
    });
    client.setQueryData(['session'], { ...verifiedActor, account_id: 'replacement' });
    fixture.componentRef.setInput('actor', { ...verifiedActor, account_id: 'replacement' });
    fixture.detectChanges();
    await load({ photo: null, uploads: [] });
    resolve(new ArrayBuffer(32));
    await new Promise<void>((done) =>
      requestAnimationFrame(() => {
        done();
      }),
    );
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
    expect(host(fixture).textContent).not.toContain('Edit selected photo');
  });
  it('ignores a native decode failure belonging to the previous actor', async () => {
    await load({ photo: null, uploads: [] });
    const file = await photoFile();
    let reject: (value: Readonly<DOMException>) => void = () => {
      throw new Error('Missing decoder gate');
    };
    const pending = new Promise<ImageBitmap>((_resolve, failed) => {
      reject = failed;
    });
    const decoder = vi.spyOn(globalThis, 'createImageBitmap').mockReturnValue(pending);
    pickFile(file);
    await vi.waitFor(() => {
      expect(decoder).toHaveBeenCalledOnce();
    });
    client.setQueryData(['session'], { ...verifiedActor, account_id: 'replacement' });
    fixture.componentRef.setInput('actor', { ...verifiedActor, account_id: 'replacement' });
    fixture.detectChanges();
    await load({ photo: null, uploads: [] });
    reject(new DOMException('old invalid image', 'InvalidStateError'));
    await new Promise<void>((done) =>
      requestAnimationFrame(() => {
        done();
      }),
    );
    expect(host(fixture).textContent).not.toContain('Choose a JPEG or PNG photo, up to 10 MB.');
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
  });
  it('recovers a failed access ticket without silently getting stuck or losing the known final fingerprint', async () => {
    await load({ photo: null, uploads: [] });
    const file = await choosePhoto();
    click(fixture, 'Use the original without cropping');
    const start = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/media/uploads', method: 'POST' }),
    );
    const matching = { ...upload, size_bytes: file.size };
    start.flush(matching);
    const requests = await Promise.all([
      vi.waitFor(() => backend.expectOne({ url: '/api/v1/media/uploads', method: 'GET' })),
      vi.waitFor(() => backend.expectOne({ url: `/api/v1/media/${upload.id}`, method: 'GET' })),
    ]);
    for (const request of requests) {
      if (request.request.url === '/api/v1/media/uploads')
        request.flush({ code: 'unavailable' }, { status: 503, statusText: 'Failure' });
      else request.flush(matching);
    }
    const first = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/access`),
    );
    first.flush({ code: 'media_storage_unavailable' }, { status: 503, statusText: 'Failure' });
    await shown(fixture, 'We couldn’t access this upload.');
    click(fixture, 'Refresh recent uploads');
    await load({
      photo: null,
      uploads: [{ upload: matching, source_sha256: await sourceHash(file) }],
    });
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetcher);
    click(fixture, 'Retry selected file');
    click(fixture, 'Retry selected file');
    const retry = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/access`),
    );
    retry.flush({ url: 'https://storage.invalid/fixture', fields: {} });
    const finalization = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/finalize`),
    );
    const queued = { ...matching, state: 'queued' } as const;
    finalization.flush(queued);
    await settle(queued, await sourceHash(file));
    await shown(fixture, 'Your photo is waiting for processing.');
    expect(fetcher).toHaveBeenCalledOnce();
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
  });
  it('leaves the local file unchanged when the native picker is cancelled', async () => {
    await load({ photo: null, uploads: [] });
    const input = host(fixture).querySelector('input[type="file"]');
    if (!(input instanceof HTMLInputElement)) throw new Error('Expected native file chooser');
    input.dispatchEvent(new Event('change', { bubbles: true }));
    fixture.detectChanges();
    expect(host(fixture).textContent).not.toContain('Edit selected photo');
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
  });
  it('uses a rotated CSRF token without resetting the same actor photo draft', async () => {
    await load();
    await open();
    await choosePhoto();
    client.setQueryData(['session'], { ...verifiedActor, csrf_token: 'rotated-fixture-token' });
    fixture.componentRef.setInput('actor', {
      ...verifiedActor,
      csrf_token: 'rotated-fixture-token',
    });
    fixture.detectChanges();
    expect(host(fixture).querySelector('canvas')).not.toBeNull();
    backend.expectNone('/api/v1/media/uploads');
    click(fixture, 'Cancel');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).querySelector('canvas')).toBeNull();
    });
    click(fixture, 'Cancel upload');
    const cancel = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/cancel`),
    );
    expect(cancel.request.headers.get('x-csrf-token')).toBe('rotated-fixture-token');
    const cancelled = { ...upload, state: 'cancelled' } as const;
    cancel.flush(cancelled);
    await settle(cancelled, 'a'.repeat(64));
    await shown(fixture, 'This upload was cancelled.');
  });
  for (const status of [401, 403]) {
    it(`clears selected bytes when the access request loses authorization${String(status)}`, async () => {
      const expired = vi.fn();
      fixture.componentInstance.expired.subscribe(expired);
      const file = await photoFile();
      const hash = await sourceHash(file);
      const matching = { ...upload, size_bytes: file.size };
      await load({ photo: null, uploads: [{ upload: matching, source_sha256: hash }] });
      await open(matching);
      await choosePhoto(file);
      click(fixture, 'Use the original without cropping');
      const access = await vi.waitFor(() =>
        backend.expectOne(`/api/v1/media/uploads/${upload.id}/access`),
      );
      access.flush({ code: 'session_required' }, { status, statusText: 'Unauthorized' });
      await vi.waitFor(() => {
        fixture.detectChanges();
        expect(expired).toHaveBeenCalled();
      });
      expect(host(fixture).textContent).not.toContain('Edit selected photo');
      expect(host(fixture).textContent).not.toContain('Retry selected file');
    });
  }
  it('can explicitly retry a failed status read after intent recovery without restarting creation', async () => {
    await load();
    click(fixture, 'Check upload 1');
    const failed = await vi.waitFor(() => backend.expectOne(`/api/v1/media/${upload.id}`));
    failed.flush({ code: 'unavailable' }, { status: 503, statusText: 'Failure' });
    await shown(fixture, 'We couldn’t check the photo upload.');
    click(fixture, 'Check photo status');
    const retry = await vi.waitFor(() => backend.expectOne(`/api/v1/media/${upload.id}`));
    retry.flush(upload);
    await shown(fixture, 'Waiting for the file transfer.');
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
  });
  it('keeps a CAS conflict unresolved when refreshing the current photo fails', async () => {
    await load({ photo: null, uploads: [] });
    await choosePhoto();
    click(fixture, 'Use the original without cropping');
    const start = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/media/uploads', method: 'POST' }),
    );
    start.flush({ code: 'photo_version_conflict' }, { status: 409, statusText: 'Conflict' });
    await shown(fixture, 'Your photo changed elsewhere.');
    click(fixture, 'Reload current photo');
    await load({ code: 'unavailable' }, 503);
    expect(host(fixture).textContent).toContain('Your photo changed elsewhere.');
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
  });
  it('resolves an uncertain immutable intent but never transfers final bytes that changed since the original read', async () => {
    await load({ photo: null, uploads: [] });
    const file = await choosePhoto();
    click(fixture, 'Use the original without cropping');
    const start = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/media/uploads', method: 'POST' }),
    );
    start.flush({ code: 'unavailable' }, { status: 503, statusText: 'Failure' });
    await shown(fixture, 'We couldn’t confirm the photo request.');
    const bytes = new Uint8Array(await file.arrayBuffer());
    const changed = Uint8Array.from(bytes, (value, index) =>
      index === bytes.length - 1 ? value ^ 1 : value,
    ).buffer;
    vi.spyOn(Blob.prototype, 'arrayBuffer').mockImplementation(function (this: Readonly<Blob>) {
      return Promise.resolve(this.size === file.size ? changed : bytes.slice(0, this.size).buffer);
    });
    click(fixture, 'Retry photo request');
    const replay = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/media/uploads', method: 'POST' }),
    );
    expect(replay.request.body).toEqual(start.request.body);
    expect(replay.request.headers.get('idempotency-key')).toBe(
      start.request.headers.get('idempotency-key'),
    );
    const matching = { ...upload, size_bytes: file.size };
    replay.flush(matching);
    const originalHash = Array.from(
      new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
      (part) => part.toString(16).padStart(2, '0'),
    ).join('');
    await settle(matching, originalHash);
    await shown(fixture, 'This file does not match that upload.');
    backend.expectNone(`/api/v1/media/uploads/${upload.id}/access`);
  });
  it('does not show an old crop failure in a replacement actor editor', async () => {
    await load({ photo: null, uploads: [] });
    await choosePhoto();
    let reject: (error: Readonly<DOMException>) => void = () => {
      throw new Error('Missing encoder gate');
    };
    const pending = new Promise<Blob>((_resolve, failed) => {
      reject = failed;
    });
    const encoder = vi.spyOn(OffscreenCanvas.prototype, 'convertToBlob').mockReturnValue(pending);
    click(fixture, 'Use photo');
    await vi.waitFor(() => {
      expect(encoder).toHaveBeenCalledOnce();
    });
    client.setQueryData(['session'], { ...verifiedActor, account_id: 'replacement' });
    fixture.componentRef.setInput('actor', { ...verifiedActor, account_id: 'replacement' });
    fixture.detectChanges();
    await load({ photo: null, uploads: [] });
    reject(new DOMException('old encode failure', 'EncodingError'));
    await new Promise<void>((done) =>
      requestAnimationFrame(() => {
        done();
      }),
    );
    expect(host(fixture).textContent).not.toContain('We couldn’t prepare this file.');
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
  });
  it('retains an accepted S3 upload when session revalidation interrupts before finalization', async () => {
    const file = await photoFile();
    const hash = await sourceHash(file);
    const matching = { ...upload, size_bytes: file.size };
    await load({ photo: null, uploads: [{ upload: matching, source_sha256: hash }] });
    await open(matching);
    await choosePhoto(file);
    let accepted: (response: Response) => void = () => {
      throw new Error('Missing accepted transfer response');
    };
    const pending = new Promise<Response>((resolve) => {
      accepted = resolve;
    });
    const fetcher = vi.fn<typeof fetch>().mockReturnValue(pending);
    vi.stubGlobal('fetch', fetcher);
    click(fixture, 'Use the original without cropping');
    const access = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/access`),
    );
    access.flush({ url: 'https://storage.invalid/fixture', fields: {} });
    await vi.waitFor(() => {
      expect(fetcher).toHaveBeenCalledOnce();
    });
    // S3 has committed the bytes, but the browser response races a /me check.
    fixture.componentRef.setInput('checking', true);
    fixture.detectChanges();
    accepted(new Response(null, { status: 204 }));
    await shown(fixture, 'uploading is paused.');
    backend.expectNone(`/api/v1/media/uploads/${upload.id}/finalize`);
    fixture.componentRef.setInput('checking', false);
    fixture.detectChanges();
    await settle(matching, hash);
    await shown(fixture, 'Your photo upload paused before processing could be confirmed.');
    expect(workflow().hasLocalDraft).toBe(true);
    await vi.waitFor(() => {
      fixture.detectChanges();
      const retry = Array.from(host(fixture).querySelectorAll('button')).find(
        (button: Readonly<HTMLButtonElement>) =>
          button.textContent.trim() === 'Resume selected photo',
      );
      expect(retry?.disabled).toBe(false);
    });
    backend.expectNone(`/api/v1/media/uploads/${upload.id}/finalize`);
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
    click(fixture, 'Resume selected photo');
    const resumedAccess = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/access`),
    );
    expect(host(fixture).textContent).not.toContain('Your photo upload paused');
    resumedAccess.flush({ url: 'https://storage.invalid/fixture', fields: {} });
    const finalize = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/finalize`),
    );
    const queued = { ...matching, state: 'queued' } as const;
    finalize.flush(queued);
    await settle(queued, hash);
    await shown(fixture, 'Your photo is waiting for processing.');
    expect(fetcher).toHaveBeenCalledTimes(2);
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
  });
  it('preserves an interrupted owned upload across the real session cache-retirement boundary', async () => {
    const file = await photoFile();
    const hash = await sourceHash(file);
    const matching = { ...upload, size_bytes: file.size };
    await load({ photo: null, uploads: [{ upload: matching, source_sha256: hash }] });
    await open(matching);
    await choosePhoto(file);
    let accepted: (response: Response) => void = () => {
      throw new Error('Missing response');
    };
    const pending = new Promise<Response>((resolve) => {
      accepted = resolve;
    });
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockReturnValue(pending));
    click(fixture, 'Use the original without cropping');
    const access = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/access`),
    );
    access.flush({ url: 'https://storage.invalid/fixture', fields: {} });
    await vi.waitFor(() => {
      expect(fetch).toHaveBeenCalledOnce();
    });
    const revalidation = client.query(sessionOptions(TestBed.inject(HttpClient), client));
    const me = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    expect(
      client.getQueryData(['account', verifiedActor.account_id, 'photo-upload', upload.id]),
    ).toBeUndefined();
    fixture.componentRef.setInput('checking', true);
    fixture.detectChanges();
    accepted(new Response(null, { status: 204 }));
    await shown(fixture, 'uploading is paused.');
    backend.expectNone(`/api/v1/media/uploads/${upload.id}/finalize`);
    me.flush(verifiedActor);
    await revalidation;
    fixture.componentRef.setInput('checking', false);
    fixture.detectChanges();
    await settle(matching, hash);
    await shown(fixture, 'Your photo upload paused before processing could be confirmed.');
    expect(workflow().hasLocalDraft).toBe(true);
    backend.expectNone(`/api/v1/media/uploads/${upload.id}/finalize`);
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
  });
  it('does not finalize a transfer response that races a successful cancellation', async () => {
    const file = await photoFile();
    const hash = await sourceHash(file);
    const matching = { ...upload, size_bytes: file.size };
    await load({ photo: null, uploads: [{ upload: matching, source_sha256: hash }] });
    await open(matching);
    await choosePhoto(file);
    let resolve: (response: Response) => void = () => {
      throw new Error('Missing storage gate');
    };
    const pending = new Promise<Response>((done) => {
      resolve = done;
    });
    const fetcher = vi.fn<typeof fetch>().mockReturnValue(pending);
    vi.stubGlobal('fetch', fetcher);
    click(fixture, 'Use the original without cropping');
    const access = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/access`),
    );
    access.flush({ url: 'https://storage.invalid/fixture', fields: {} });
    await vi.waitFor(() => {
      expect(fetcher).toHaveBeenCalledOnce();
      fixture.detectChanges();
    });
    click(fixture, 'Cancel upload');
    const cancel = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/cancel`),
    );
    const cancelled = { ...matching, state: 'cancelled' } as const;
    cancel.flush(cancelled);
    await settle(cancelled, hash);
    resolve(new Response(null, { status: 204 }));
    await new Promise<void>((done) =>
      requestAnimationFrame(() => {
        done();
      }),
    );
    backend.expectNone(`/api/v1/media/uploads/${upload.id}/finalize`);
    await shown(fixture, 'This upload was cancelled.');
  });
  it('preserves the uncertain finalization intent even when retrying the same selected bytes first', async () => {
    const file = await photoFile();
    const hash = await sourceHash(file);
    const matching = { ...upload, size_bytes: file.size };
    await load({ photo: null, uploads: [{ upload: matching, source_sha256: hash }] });
    await open(matching);
    await choosePhoto(file);
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetcher);
    click(fixture, 'Use the original without cropping');
    const access = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/access`),
    );
    access.flush({ url: 'https://storage.invalid/fixture', fields: {} });
    const first = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/finalize`),
    );
    const key = first.request.headers.get('idempotency-key');
    first.flush({ code: 'unavailable' }, { status: 503, statusText: 'Failure' });
    await shown(fixture, 'We couldn’t confirm processing started.');
    click(fixture, 'Retry selected file');
    const repeatedAccess = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/access`),
    );
    repeatedAccess.flush({ url: 'https://storage.invalid/fixture', fields: {} });
    const second = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/finalize`),
    );
    expect(second.request.headers.get('idempotency-key')).toBe(key);
    second.flush({ code: 'unavailable' }, { status: 503, statusText: 'Failure' });
    await shown(fixture, 'We couldn’t confirm processing started.');
    click(fixture, 'Retry finalization');
    const third = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/finalize`),
    );
    expect(third.request.headers.get('idempotency-key')).toBe(key);
    third.flush({ code: 'unavailable' }, { status: 503, statusText: 'Failure' });
    await shown(fixture, 'We couldn’t confirm processing started.');
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
  it('does not create a replacement when an upload completes while its reselected file is being edited', async () => {
    await load();
    await open();
    await choosePhoto();
    const refresh = client.refetchQueries({
      queryKey: ['account', verifiedActor.account_id, 'photo-upload', upload.id],
    });
    const status = await vi.waitFor(() => backend.expectOne(`/api/v1/media/${upload.id}`));
    const ready = {
      ...upload,
      state: 'ready',
      display_url: `/api/v1/media/${upload.id}/display`,
    } as const;
    status.flush(ready);
    await load({ photo: null, uploads: [{ upload: ready, source_sha256: 'a'.repeat(64) }] });
    await refresh;
    click(fixture, 'Use the original without cropping');
    await shown(fixture, 'This upload has already moved on.');
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
    backend.expectNone(`/api/v1/media/uploads/${upload.id}/access`);
    expect(host(fixture).textContent).toContain('Your photo is saved.');
  });
  it('waits for an initially unknown selected upload before accepting a local file', async () => {
    await load();
    click(fixture, 'Check upload 1');
    const pending = await vi.waitFor(() => backend.expectOne(`/api/v1/media/${upload.id}`));
    fixture.detectChanges();
    const chooser = Array.from(host(fixture).querySelectorAll('button')).find(
      (button: Readonly<HTMLButtonElement>) => button.textContent.trim() === 'Choose photo',
    );
    expect(chooser?.disabled).toBe(true);
    pending.flush(upload);
    await shown(fixture, 'Waiting for the file transfer.');
    expect(chooser?.disabled).toBe(false);
  });
  it('renders the latest owner photo projection and requires an explicit new draft to replace a completed upload', async () => {
    const ready = {
      ...upload,
      state: 'ready',
      display_url: `/api/v1/media/${upload.id}/display`,
    } as const;
    const projection = {
      photo: {
        upload_id: upload.id,
        version: 2,
        display_url: `/api/v1/media/${upload.id}/display`,
      },
      uploads: [{ upload: ready, source_sha256: 'a'.repeat(64) }],
    };
    await load(projection);
    expect(host(fixture).querySelector('img')?.getAttribute('src')).toBe(
      projection.photo.display_url,
    );
    click(fixture, 'Check upload 1');
    const status = await vi.waitFor(() => backend.expectOne(`/api/v1/media/${upload.id}`));
    status.flush(ready);
    await load(projection);
    await shown(fixture, 'Your photo is saved.');
    const input = host(fixture).querySelector('input[type="file"]');
    if (!(input instanceof HTMLInputElement)) throw new Error('Missing native chooser');
    vi.spyOn(input, 'click').mockImplementation(() => undefined);
    click(fixture, 'Choose new photo');
    const file = await choosePhoto();
    click(fixture, 'Use the original without cropping');
    const start = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/media/uploads', method: 'POST' }),
    );
    expect(start.request.body).toEqual({
      expected_photo_version: 2,
      sha256: await sourceHash(file),
      size_bytes: file.size,
      content_type: 'image/png',
    });
    start.flush({ code: 'unavailable' }, { status: 503, statusText: 'Failure' });
    await shown(fixture, 'We couldn’t confirm the photo request.');
  });
  it('does not replace a newer parent photo with an older resume snapshot', async () => {
    const newer = {
      upload_id: 'newer-photo',
      version: 3,
      display_url: '/api/v1/media/newer-photo/display',
    };
    fixture.componentRef.setInput('version', 3);
    fixture.componentRef.setInput('photo', newer);
    fixture.detectChanges();
    await load({
      photo: {
        upload_id: upload.id,
        version: 2,
        display_url: `/api/v1/media/${upload.id}/display`,
      },
      uploads: [],
    });
    expect(host(fixture).querySelector('img')?.getAttribute('src')).toBe(newer.display_url);
  });
  it('requires explicit retry after a known quota rejection and creates a fresh intent rather than replaying an unknown result', async () => {
    await load({ photo: null, uploads: [] });
    const file = await choosePhoto();
    click(fixture, 'Use the original without cropping');
    const first = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/media/uploads', method: 'POST' }),
    );
    const key = first.request.headers.get('idempotency-key');
    first.flush({ code: 'photo_upload_rate_limited' }, { status: 429, statusText: 'Limit' });
    await shown(fixture, 'The photo action couldn’t be completed.');
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
    click(fixture, 'Retry photo request');
    const retry = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/media/uploads', method: 'POST' }),
    );
    expect(retry.request.headers.get('idempotency-key')).not.toBe(key);
    expect(retry.request.body).toEqual({
      expected_photo_version: 0,
      size_bytes: file.size,
      sha256: await sourceHash(file),
      content_type: 'image/png',
    });
    retry.flush({ code: 'unavailable' }, { status: 503, statusText: 'Failure' });
    await shown(fixture, 'We couldn’t confirm the photo request.');
  });
  for (const status of [200, 401, 503]) {
    it(`ignores a creation replay${String(status)} completing after actor replacement`, async () => {
      const expired = vi.fn();
      fixture.componentInstance.expired.subscribe(expired);
      await load({ photo: null, uploads: [] });
      await choosePhoto();
      click(fixture, 'Use the original without cropping');
      const first = await vi.waitFor(() =>
        backend.expectOne({ url: '/api/v1/media/uploads', method: 'POST' }),
      );
      first.flush({ code: 'unavailable' }, { status: 503, statusText: 'Failure' });
      await shown(fixture, 'We couldn’t confirm the photo request.');
      click(fixture, 'Retry photo request');
      click(fixture, 'Retry photo request');
      const replay = await vi.waitFor(() =>
        backend.expectOne({ url: '/api/v1/media/uploads', method: 'POST' }),
      );
      expect(replay.request.body).toEqual(first.request.body);
      client.setQueryData(['session'], { ...verifiedActor, account_id: 'replacement' });
      fixture.componentRef.setInput('actor', { ...verifiedActor, account_id: 'replacement' });
      fixture.detectChanges();
      await load({ photo: null, uploads: [] });
      replay.flush(status === 200 ? createdPhoto(replay) : { code: 'unavailable' }, {
        status,
        statusText: status === 200 ? 'OK' : 'Failure',
      });
      await vi.waitFor(() => {
        expect(client.getMutationCache().getAll().at(-1)?.state.status).toBe(
          status === 200 ? 'success' : 'error',
        );
      });
      expect(expired).not.toHaveBeenCalled();
      backend.expectNone(`/api/v1/media/uploads/${upload.id}/access`);
      backend.expectNone('/api/v1/media/uploads');
    });
  }
  for (const mismatch of ['declared size', 'declared content type'] as const)
    it(`rejects matching photo hash with mismatched ${mismatch} before any storage access`, async () => {
      const file = await photoFile();
      const sha = await sourceHash(file);
      const existing = {
        ...upload,
        size_bytes: mismatch === 'declared size' ? file.size + 1 : file.size,
        content_type: mismatch === 'declared content type' ? 'image/jpeg' : 'image/png',
      } as const;
      await load({ photo: null, uploads: [{ upload: existing, source_sha256: sha }] });
      await open(existing);
      await choosePhoto(file);
      click(fixture, 'Use the original without cropping');
      await shown(fixture, 'This file does not match that upload.');
      backend.expectNone(`/api/v1/media/uploads/${upload.id}/access`);
      backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
      expect(workflow().hasLocalDraft).toBe(true);
    });
  it('does not publish an invalid header read finishing after actor replacement over the new crop', async () => {
    await load({ photo: null, uploads: [] });
    const oldFile = new File(['unreadable signature'], 'old.png', { type: 'image/png' });
    const header = new Blob(['unreadable signature']);
    let finish: (value: ArrayBuffer) => void = () => {
      throw new Error('Missing header completion');
    };
    const pending = new Promise<ArrayBuffer>((resolve) => {
      finish = resolve;
    });
    vi.spyOn(oldFile, 'slice').mockReturnValue(header);
    vi.spyOn(header, 'arrayBuffer').mockReturnValue(pending);
    pickFile(oldFile);
    const replacement = { ...verifiedActor, account_id: 'replacement-photo-actor' };
    client.setQueryData(['session'], replacement);
    fixture.componentRef.setInput('actor', replacement);
    fixture.detectChanges();
    await load({ photo: null, uploads: [] });
    await choosePhoto();
    const currentCanvas = host(fixture).querySelector('canvas');
    expect(currentCanvas).toBeInstanceOf(HTMLCanvasElement);
    finish(new ArrayBuffer(8));
    await pending;
    await fixture.whenStable();
    fixture.detectChanges();
    expect(host(fixture).textContent).not.toContain('Choose a JPEG or PNG photo, up to 10 MB.');
    expect(host(fixture).querySelector('canvas')).toBe(currentCanvas);
    expect(workflow().hasLocalDraft).toBe(true);
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
  });
  it('does not create or transfer a photo when hashing finishes during a same-actor sign-in check', async () => {
    await load({ photo: null, uploads: [] });
    const file = await choosePhoto();
    const realDigest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer());
    let finish: (value: ArrayBuffer) => void = () => {
      throw new Error('Missing hash completion');
    };
    const pending = new Promise<ArrayBuffer>((resolve) => {
      finish = resolve;
    });
    const hash = vi.spyOn(crypto.subtle, 'digest').mockReturnValue(pending);
    click(fixture, 'Use the original without cropping');
    await vi.waitFor(() => {
      expect(hash).toHaveBeenCalledOnce();
    });
    fixture.componentRef.setInput('checking', true);
    fixture.detectChanges();
    finish(realDigest);
    await pending;
    await fixture.whenStable();
    fixture.detectChanges();
    expect(workflow().hasLocalDraft).toBe(true);
    expect(workflow().hasUnconfirmedAction).toBe(false);
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'POST' });
    backend.expectNone(`/api/v1/media/uploads/${upload.id}/access`);
  });
  it('keeps a confirmed owned cancellation while pausing private rereads during sign-in validation', async () => {
    await load();
    await open();
    click(fixture, 'Cancel upload');
    const cancel = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/cancel`),
    );
    fixture.componentRef.setInput('checking', true);
    fixture.detectChanges();
    cancel.flush({ ...upload, version: 2, state: 'cancelled' });
    await shown(fixture, 'This upload was cancelled.');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(workflow().hasUnconfirmedAction).toBe(false);
    });
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'GET' });
    backend.expectNone({ url: `/api/v1/media/${upload.id}`, method: 'GET' });
  });
  it('keeps an owned ready finalization receipt without private metadata rereads while sign-in is being checked', async () => {
    const file = await photoFile();
    const sha = await sourceHash(file);
    const existing = { ...upload, size_bytes: file.size };
    await load({ photo: null, uploads: [{ upload: existing, source_sha256: sha }] });
    await open(existing);
    await choosePhoto(file);
    const transfer = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', transfer);
    click(fixture, 'Use the original without cropping');
    (await vi.waitFor(() => backend.expectOne(`/api/v1/media/uploads/${upload.id}/access`))).flush({
      url: 'https://storage.invalid/fixture',
      fields: { policy: 'opaque-fixture' },
    });
    const finalize = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/media/uploads/${upload.id}/finalize`),
    );
    fixture.componentRef.setInput('checking', true);
    fixture.detectChanges();
    finalize.flush({
      ...existing,
      version: 2,
      state: 'ready',
      display_url: `/api/v1/media/${upload.id}/display`,
    });
    await shown(fixture, 'Your photo is saved.');
    expect(transfer).toHaveBeenCalledOnce();
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(workflow().hasUnconfirmedAction).toBe(false);
    });
    backend.expectNone({ url: '/api/v1/media/uploads', method: 'GET' });
    backend.expectNone({ url: `/api/v1/media/${upload.id}`, method: 'GET' });
  });
});
