import type { Api } from '../../api.generated';

type Status =
  Api['schemas']['PendingDeletionResponse'] | Api['schemas']['ConfirmedDeletionResponse'];
function record(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null;
}
function uuid(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/iu.test(value)
  );
}
function instant(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value));
}
export function isDeletionPreparation(
  value: unknown,
): value is Api['schemas']['DeletionPreparationResponse'] {
  return record(value) && uuid(value['workflow_id']) && instant(value['expires_at']);
}
export function isDeletionReceipt(
  value: unknown,
): value is Api['schemas']['DeletionReceiptResponse'] {
  return (
    record(value) &&
    uuid(value['workflow_id']) &&
    instant(value['deleted_at']) &&
    typeof value['source_version'] === 'number' &&
    Number.isSafeInteger(value['source_version']) &&
    value['source_version'] >= 1
  );
}
export function isConfirmedDeletion(
  value: unknown,
): value is Api['schemas']['ConfirmedDeletionResponse'] {
  return (
    record(value) &&
    (value['state'] === undefined || value['state'] === 'deleted') &&
    !('expires_at' in value) &&
    isDeletionReceipt(value)
  );
}
export function isDeletionStatus(value: unknown): value is Status {
  return (
    isConfirmedDeletion(value) ||
    (record(value) &&
      (value['state'] === undefined || value['state'] === 'pending') &&
      !('deleted_at' in value) &&
      !('source_version' in value) &&
      isDeletionPreparation(value))
  );
}
