import { describe, expect, it } from 'vitest';
import type { Api } from '../../../../api.generated';
import { isPhotoResume, isPhotoUpload, isUploadAccess } from './photo-contract';

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
const item = { upload, source_sha256: 'a'.repeat(64) };

describe('actual private photo transport contracts', () => {
  it('accepts real states without synthesizing a READY photo', () => {
    expect(isPhotoUpload(upload)).toBe(true);
    expect(
      isPhotoUpload({
        ...upload,
        state: 'ready',
        display_url: `/api/v1/media/${upload.id}/display`,
        poll_after_ms: 500,
      }),
    ).toBe(true);
    expect(isPhotoResume({ photo: null, uploads: [item] })).toBe(true);
    expect(
      isPhotoResume({
        photo: {
          upload_id: upload.id,
          version: 1,
          display_url: `/api/v1/media/${upload.id}/display`,
        },
        uploads: [],
      }),
    ).toBe(true);
  });
  for (const key of Object.keys(upload)) {
    it(`rejects a missing or mistyped upload field ${key}`, () => {
      expect(
        isPhotoUpload(
          Object.fromEntries(
            Object.entries(upload).filter((entry: readonly [string, unknown]) => entry[0] !== key),
          ),
        ),
      ).toBe(false);
      expect(isPhotoUpload({ ...upload, [key]: false })).toBe(false);
    });
  }
  for (const invalid of [
    null,
    false,
    [],
    {},
    { ...upload, version: 0 },
    { ...upload, version: 1.5 },
    { ...upload, expected_photo_version: -1 },
    { ...upload, expected_photo_version: 0.5 },
    { ...upload, size_bytes: 0 },
    { ...upload, size_bytes: 1.5 },
    { ...upload, state: 'invented' },
    { ...upload, failure: 'private-detail' },
    { ...upload, content_type: 'image/heic' },
    { ...upload, poll_after_ms: 0 },
    { ...upload, poll_after_ms: 1.5 },
    { ...upload, display_url: 'https://outside.invalid/photo' },
  ]) {
    it(`rejects malformed upload ${JSON.stringify(invalid)}`, () => {
      expect(isPhotoUpload(invalid)).toBe(false);
    });
  }
  it('accepts each documented failure code', () => {
    const failures: readonly Api['schemas']['PhotoFailure'][] = [
      'invalid_image',
      'unsupported_format',
      'too_large',
      'dimensions_exceeded',
      'animated_image',
      'content_changed',
      'photo_changed',
      'account_unavailable',
      'storage_unavailable',
      'processing_unavailable',
    ];
    for (const failure of failures) expect(isPhotoUpload({ ...upload, failure })).toBe(true);
  });
  for (const invalid of [
    null,
    false,
    {},
    { photo: null },
    { uploads: [] },
    { photo: null, uploads: {} },
    { photo: null, uploads: Array.from({ length: 25 }, () => item) },
    ...[
      null,
      false,
      {},
      { upload },
      { ...item, upload: {} },
      { ...item, source_sha256: 1 },
      { ...item, source_sha256: 'A'.repeat(64) },
      { ...item, source_sha256: 'a'.repeat(63) },
    ].map((entry: unknown) => ({ photo: null, uploads: [entry] })),
    ...[
      false,
      {},
      { upload_id: upload.id, version: 0, display_url: `/api/v1/media/${upload.id}/display` },
      { upload_id: upload.id, version: 1.1, display_url: `/api/v1/media/${upload.id}/display` },
      { upload_id: 1, version: 1, display_url: 'private' },
      { upload_id: upload.id, version: 1, display_url: '//outside.invalid/photo' },
    ].map((photo: unknown) => ({ photo, uploads: [] })),
  ]) {
    it(`rejects malformed owner resume projection ${JSON.stringify(invalid)}`, () => {
      expect(isPhotoResume(invalid)).toBe(false);
    });
  }
  it('accepts the documented maximum projection size', () => {
    expect(isPhotoResume({ photo: null, uploads: Array.from({ length: 24 }, () => item) })).toBe(
      true,
    );
  });
  it('allows opaque HTTPS upload fields, never a preexisting file or credentials in URL', () => {
    expect(
      isUploadAccess({
        url: 'https://storage.invalid/upload',
        fields: { policy: 'opaque', key: 'opaque' },
      }),
    ).toBe(true);
    for (const value of [
      null,
      false,
      {},
      { url: false, fields: {} },
      { url: 'https://storage.invalid', fields: null },
      { url: 'https://storage.invalid', fields: [] },
      { url: 'https://storage.invalid', fields: { key: 1 } },
      ...[
        'http://storage.invalid',
        '/api/v1/uploads',
        'invalid',
        'https://user:password@storage.invalid',
      ].map((url) => ({ url, fields: {} })),
      { url: 'https://storage.invalid', fields: { file: 'forbidden' } },
    ]) {
      expect(isUploadAccess(value)).toBe(false);
    }
  });
});
