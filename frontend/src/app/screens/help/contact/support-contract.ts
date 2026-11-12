import type { Api } from '../../../api.generated';

export const supportTopics: readonly Readonly<{
  readonly value: Api['schemas']['SupportTopic'];
  readonly label: string;
}>[] = [
  { value: 'cannot_sign_in', label: 'I can’t sign in to my account' },
  { value: 'email_not_accepted', label: 'My APU email isn’t accepted' },
  { value: 'code_not_arriving', label: 'The code doesn’t arrive' },
  { value: 'email_already_in_use', label: 'My APU email is already in use' },
  { value: 'deleted_account', label: 'My account was deleted' },
  { value: 'other', label: 'Something else' },
];
export function isSupportTopic(value: unknown): value is Api['schemas']['SupportTopic'] {
  return supportTopics.some((topic) => topic.value === value);
}
function timestamp(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value));
}
export function isSupportReceipt(
  value: unknown,
): value is Api['schemas']['SupportReceiptResponse'] {
  return (
    typeof value === 'object' &&
    value !== null &&
    'case_id' in value &&
    typeof value.case_id === 'string' &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value.case_id) &&
    'status' in value &&
    (value.status === 'received' || value.status === 'in_review' || value.status === 'resolved') &&
    'version' in value &&
    typeof value.version === 'number' &&
    Number.isSafeInteger(value.version) &&
    value.version >= 1 &&
    'received_at' in value &&
    timestamp(value.received_at) &&
    'changed_at' in value &&
    timestamp(value.changed_at) &&
    Date.parse(value.changed_at) >= Date.parse(value.received_at)
  );
}
export function isRecentSupport(
  value: unknown,
): value is Api['schemas']['RecentSupportCasesResponse'] {
  return (
    typeof value === 'object' &&
    value !== null &&
    'cases' in value &&
    Array.isArray(value.cases) &&
    value.cases.length <= 20 &&
    value.cases.every(isSupportReceipt)
  );
}
export function isSupportPreparation(
  value: unknown,
): value is Api['schemas']['SupportPreparationResponse'] {
  return (
    typeof value === 'object' &&
    value !== null &&
    'csrf_token' in value &&
    typeof value.csrf_token === 'string' &&
    value.csrf_token.length > 0 &&
    'expires_at' in value &&
    timestamp(value.expires_at)
  );
}
export function validReplyAddress(value: string): boolean {
  const parts = value.split('@');
  return (
    Array.from(value).length >= 3 &&
    Array.from(value).length <= 254 &&
    value === value.trim() &&
    !/[\s\p{Cc}\p{Cs}]/u.test(value) &&
    parts.length === 2 &&
    parts[0] !== undefined &&
    parts[0].length > 0 &&
    parts[1]?.includes('.') === true
  );
}
export function validSupportText(value: string, limit: number): boolean {
  return (
    value.trim().length > 0 &&
    Array.from(value).length <= limit &&
    Array.from(value).every(
      (character: string) =>
        !/\p{Cs}/u.test(character) && (!/\p{Cc}/u.test(character) || '\n\r\t'.includes(character)),
    )
  );
}
export function supportStatus(status: Api['schemas']['SupportStatus']): string {
  switch (status) {
    case 'received':
      return 'Received';
    case 'in_review':
      return 'In review';
    case 'resolved':
      return 'Resolved';
  }
}
