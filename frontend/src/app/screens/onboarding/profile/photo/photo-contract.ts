import type { Api } from '../../../../api.generated';

const states: Readonly<Record<Api['schemas']['PhotoUploadState'], true>> = {
  uploading: true,
  queued: true,
  processing: true,
  ready: true,
  rejected: true,
  cancelled: true,
  expired: true,
};
const failures: Readonly<Record<Api['schemas']['PhotoFailure'], true>> = {
  invalid_image: true,
  unsupported_format: true,
  too_large: true,
  dimensions_exceeded: true,
  animated_image: true,
  content_changed: true,
  photo_changed: true,
  account_unavailable: true,
  storage_unavailable: true,
  processing_unavailable: true,
};
export function isPhotoUpload(value: unknown): value is Api['schemas']['PhotoUploadResponse'] {
  return (
    typeof value === 'object' &&
    value !== null &&
    'id' in value &&
    typeof value.id === 'string' &&
    'version' in value &&
    typeof value.version === 'number' &&
    Number.isInteger(value.version) &&
    value.version >= 1 &&
    'state' in value &&
    typeof value.state === 'string' &&
    Object.hasOwn(states, value.state) &&
    'content_type' in value &&
    (value.content_type === 'image/jpeg' || value.content_type === 'image/png') &&
    'size_bytes' in value &&
    typeof value.size_bytes === 'number' &&
    Number.isInteger(value.size_bytes) &&
    value.size_bytes > 0 &&
    'expected_photo_version' in value &&
    typeof value.expected_photo_version === 'number' &&
    Number.isInteger(value.expected_photo_version) &&
    value.expected_photo_version >= 0 &&
    'failure' in value &&
    (value.failure === null ||
      (typeof value.failure === 'string' && Object.hasOwn(failures, value.failure))) &&
    'display_url' in value &&
    (value.display_url === null ||
      value.display_url === `/api/v1/media/${encodeURIComponent(value.id)}/display`) &&
    'poll_after_ms' in value &&
    (value.poll_after_ms === null ||
      (typeof value.poll_after_ms === 'number' &&
        Number.isInteger(value.poll_after_ms) &&
        value.poll_after_ms > 0)) &&
    'updated_at' in value &&
    typeof value.updated_at === 'string' &&
    'upload_expires_at' in value &&
    typeof value.upload_expires_at === 'string' &&
    'processing_expires_at' in value &&
    typeof value.processing_expires_at === 'string'
  );
}
export function isUploadAccess(value: unknown): value is Api['schemas']['UploadAccessResponse'] {
  if (
    typeof value !== 'object' ||
    value === null ||
    !('url' in value) ||
    typeof value.url !== 'string' ||
    !('fields' in value) ||
    typeof value.fields !== 'object' ||
    value.fields === null ||
    Array.isArray(value.fields) ||
    !Object.values(value.fields).every((field: unknown) => typeof field === 'string')
  )
    return false;
  try {
    const url = new URL(value.url);
    return (
      url.protocol === 'https:' &&
      url.username === '' &&
      url.password === '' &&
      !Object.hasOwn(value.fields, 'file')
    );
  } catch {
    return false;
  }
}

export function isPhotoResume(value: unknown): value is Api['schemas']['OwnPhotoResumeResponse'] {
  if (
    typeof value !== 'object' ||
    value === null ||
    !('photo' in value) ||
    !('uploads' in value) ||
    !Array.isArray(value.uploads) ||
    value.uploads.length > 24 ||
    !value.uploads.every(
      (item: unknown) =>
        typeof item === 'object' &&
        item !== null &&
        'upload' in item &&
        isPhotoUpload(item.upload) &&
        'source_sha256' in item &&
        typeof item.source_sha256 === 'string' &&
        /^[0-9a-f]{64}$/.test(item.source_sha256),
    )
  )
    return false;
  const photo = value.photo;
  return (
    photo === null ||
    (typeof photo === 'object' &&
      'upload_id' in photo &&
      typeof photo.upload_id === 'string' &&
      'version' in photo &&
      typeof photo.version === 'number' &&
      Number.isInteger(photo.version) &&
      photo.version >= 1 &&
      'display_url' in photo &&
      photo.display_url === `/api/v1/media/${encodeURIComponent(photo.upload_id)}/display`)
  );
}
