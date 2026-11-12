import type { Api } from '../../../api.generated';

type Preparation = Api['schemas']['ImagePreparationResponse'];
type Receipt = Api['schemas']['ImagePreparationReceipt'];
type Source = Api['schemas']['ExpectedImageSource'];

function record(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function positive(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
}
function date(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value));
}
function id(value: unknown): value is string {
  return typeof value === 'string' && /^[\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12}$/iu.test(value);
}
function state(value: unknown): value is Api['schemas']['ChatImageState'] {
  return (
    value === 'uploading' ||
    value === 'queued' ||
    value === 'processing' ||
    value === 'ready' ||
    value === 'rejected' ||
    value === 'cancelled' ||
    value === 'expired'
  );
}
function failure(value: unknown): value is Api['schemas']['ChatImageFailure'] | null {
  return (
    value === null ||
    value === 'invalid_image' ||
    value === 'unsupported_format' ||
    value === 'too_large' ||
    value === 'dimensions_exceeded' ||
    value === 'animated_image' ||
    value === 'content_changed' ||
    value === 'account_unavailable' ||
    value === 'contact_unavailable' ||
    value === 'storage_unavailable' ||
    value === 'processing_unavailable'
  );
}
export function isImageSource(value: unknown): value is Source {
  return (
    record(value) &&
    (value['content_type'] === 'image/jpeg' || value['content_type'] === 'image/png') &&
    typeof value['sha256'] === 'string' &&
    /^[\da-f]{64}$/u.test(value['sha256']) &&
    positive(value['size']) &&
    value['size'] <= 10_000_000
  );
}
function display(value: unknown): value is Api['schemas']['ReadyImageMetadata'] | null {
  return (
    value === null ||
    (record(value) &&
      positive(value['height']) &&
      positive(value['width']) &&
      positive(value['size']))
  );
}
function outcome(value: unknown): value is Api['schemas']['PreparationMessageOutcome'] | null {
  return (
    value === null ||
    (record(value) &&
      typeof value['attachment_confirmed'] === 'boolean' &&
      (value['message_id'] === null || id(value['message_id'])) &&
      id(value['operation_id']) &&
      (value['outcome'] === 'confirmed' || value['outcome'] === 'cancelled'))
  );
}
export function isImageReceipt(value: unknown): value is Receipt {
  return (
    record(value) &&
    id(value['client_message_id']) &&
    id(value['conversation_id']) &&
    id(value['image_id']) &&
    state(value['receipt_state']) &&
    positive(value['receipt_version'])
  );
}
export function isImagePreparation(value: unknown): value is Preparation {
  return (
    record(value) &&
    id(value['client_message_id']) &&
    id(value['conversation_id']) &&
    id(value['image_id']) &&
    date(value['created_at']) &&
    date(value['updated_at']) &&
    date(value['upload_expires_at']) &&
    date(value['processing_expires_at']) &&
    display(value['display']) &&
    isImageSource(value['expected_source']) &&
    failure(value['failure']) &&
    outcome(value['message_outcome']) &&
    state(value['state']) &&
    state(value['source_state']) &&
    positive(value['source_version'])
  );
}
export function isImagePreparations(
  value: unknown,
): value is Api['schemas']['ImagePreparationsResponse'] {
  return (
    record(value) &&
    Array.isArray(value['preparations']) &&
    value['preparations'].every(isImagePreparation)
  );
}
export function isImageReportContext(
  value: unknown,
): value is Api['schemas']['MessageImageReportContextResponse'] {
  return (
    record(value) &&
    id(value['id']) &&
    id(value['conversation_id']) &&
    id(value['image_id']) &&
    id(value['message_id']) &&
    date(value['issued_at']) &&
    (value['kind'] === undefined || value['kind'] === 'message_image')
  );
}
export function isImageReportReceipt(
  value: unknown,
): value is Api['schemas']['MessageImageReportReceipt'] {
  return (
    record(value) &&
    id(value['id']) &&
    id(value['context_id']) &&
    date(value['submitted_at']) &&
    (value['kind'] === undefined || value['kind'] === 'message_image')
  );
}

export function imageSelectionProblem(file: Readonly<Blob>): string | null {
  if (file.type !== 'image/jpeg' && file.type !== 'image/png') return 'Choose a JPEG or PNG image.';
  if (file.size === 0) return 'Choose an image that is not empty.';
  if (file.size > 10_000_000) return 'Choose an image up to 10 MB.';
  return null;
}
export async function imageSource(file: Readonly<Blob>): Promise<Source> {
  if (file.type !== 'image/jpeg' && file.type !== 'image/png')
    throw new TypeError('Unsupported image type');
  const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer());
  return {
    content_type: file.type,
    size: file.size,
    sha256: Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join(
      '',
    ),
  };
}
export function sameImageSource(left: Source, right: Source): boolean {
  return (
    left.sha256 === right.sha256 &&
    left.size === right.size &&
    left.content_type === right.content_type
  );
}
