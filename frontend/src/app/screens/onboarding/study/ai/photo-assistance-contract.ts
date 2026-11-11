import type { Api } from '../../../../api.generated';

function record(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null;
}
function uuid(value: unknown): value is string {
  return typeof value === 'string' && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value);
}
export function validPhotoSource(source: Api['schemas']['ResourceSourceRequest']): boolean {
  return uuid(source.id) && Number.isSafeInteger(source.version) && source.version >= 1;
}
export function samePhotoSource(
  left: Api['schemas']['ResourceSourceRequest'],
  right: Api['schemas']['ResourceSourceRequest'],
): boolean {
  return left.id === right.id && left.version === right.version;
}
function observation(value: unknown): value is Api['schemas']['PhotoResultResponse']['blurred'] {
  return value === 'yes' || value === 'no' || value === 'uncertain';
}
export function isPhotoAdvice(value: unknown): value is Api['schemas']['PhotoResultResponse'] {
  return (
    record(value) &&
    Object.keys(value).length === 3 &&
    observation(value['blurred']) &&
    observation(value['face_visible']) &&
    observation(value['multiple_people'])
  );
}
const failures: readonly Api['schemas']['Failure'][] = [
  'transient',
  'invalid_output',
  'invalid_input',
  'timeout',
  'auth_unavailable',
  'rate_limited',
  'account_unavailable',
  'stale_source',
  'executor_lost',
];
export function acceptsPhotoJob(
  value: unknown,
  source: Api['schemas']['ResourceSourceRequest'],
  jobId?: string,
): value is Api['schemas']['JobResponse'] {
  if (
    !record(value) ||
    !uuid(value['id']) ||
    (jobId !== undefined && value['id'] !== jobId) ||
    value['kind'] !== 'assess_photo' ||
    value['target'] !== null ||
    !record(value['source']) ||
    value['source']['kind'] !== 'resource' ||
    value['source']['id'] !== source.id ||
    value['source']['version'] !== source.version ||
    typeof value['created_at'] !== 'string' ||
    !Number.isFinite(Date.parse(value['created_at'])) ||
    typeof value['deadline'] !== 'string' ||
    !Number.isFinite(Date.parse(value['deadline'])) ||
    Date.parse(value['deadline']) <= Date.parse(value['created_at'])
  )
    return false;
  if (value['state'] === 'queued' || value['state'] === 'running')
    return (
      value['result'] === null &&
      value['failure'] === null &&
      typeof value['poll_after_ms'] === 'number' &&
      Number.isSafeInteger(value['poll_after_ms']) &&
      value['poll_after_ms'] > 0
    );
  if (value['poll_after_ms'] !== null) return false;
  if (value['state'] === 'succeeded')
    return value['failure'] === null && isPhotoAdvice(value['result']);
  if (value['result'] !== null) return false;
  if (value['state'] === 'cancelled') return value['failure'] === null;
  return (
    (value['state'] === 'failed' || value['state'] === 'expired') &&
    (value['failure'] === null ||
      failures.some((failure: Api['schemas']['Failure']) => failure === value['failure']))
  );
}
export const photoAdvice: Readonly<
  Record<
    keyof Api['schemas']['PhotoResultResponse'],
    Readonly<Record<Api['schemas']['PhotoResultResponse']['blurred'], string>>
  >
> = {
  blurred: {
    yes: 'A sharper photo may be easier to recognise.',
    no: 'Blur was not apparent in this check.',
    uncertain: 'We couldn’t tell whether the photo is blurred.',
  },
  face_visible: {
    yes: 'A face appears visible in this photo.',
    no: 'Consider a photo with your face clearly visible.',
    uncertain: 'We couldn’t tell whether a face is clearly visible.',
  },
  multiple_people: {
    yes: 'Consider a photo showing just you.',
    no: 'Additional people were not apparent in this check.',
    uncertain: 'We couldn’t tell whether other people are in the photo.',
  },
};
