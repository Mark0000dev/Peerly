import type { HttpClient } from '@angular/common/http';
import { queryOptions } from '@tanstack/angular-query-experimental';
import type { QueryFunctionContext } from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { readJson } from '../../api-http';
import { isPolicyReference } from '../policy-reference';

type Parameters = Api['paths']['/api/v1/operator/accounts']['get']['parameters'];
export type AccountFilters = {
  readonly [K in keyof Parameters as K extends `query:${infer Name}` ? Name : never]: Parameters[K];
};
function record(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null;
}
function string(value: unknown): value is string {
  return typeof value === 'string';
}
function integer(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
}
export function uuid(value: unknown): value is string {
  return string(value) && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/i.test(value);
}
export function instant(value: unknown): value is string {
  return (
    string(value) && /T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value))
  );
}
function nullable<T>(value: unknown, guard: (item: unknown) => item is T): value is T | null {
  return value === null || guard(value);
}
function array<T>(value: unknown, guard: (item: unknown) => item is T): value is readonly T[] {
  return Array.isArray(value) && value.every(guard);
}
function google(value: unknown): value is Api['schemas']['GoogleLinkResponse'] {
  return (
    record(value) &&
    uuid(value['id']) &&
    string(value['issuer']) &&
    string(value['subject']) &&
    instant(value['created_at'])
  );
}
function membership(value: unknown): value is Api['schemas']['MembershipResponse'] {
  return (
    record(value) &&
    string(value['email']) &&
    instant(value['verified_at']) &&
    nullable(value['revoked_at'], instant)
  );
}
export function isAccount(value: unknown): value is Api['schemas']['OperatorAccountResponse'] {
  return (
    record(value) &&
    uuid(value['account_id']) &&
    instant(value['created_at']) &&
    nullable(value['banned_at'], instant) &&
    nullable(value['deleted_at'], instant) &&
    nullable(value['hidden_at'], instant) &&
    nullable(value['display_name'], string) &&
    nullable(value['profile_version'], integer) &&
    nullable(value['google_link'], google) &&
    nullable(value['membership'], membership)
  );
}
export function isAccounts(value: unknown): value is Api['schemas']['OperatorAccountsResponse'] {
  return (
    record(value) && array(value['accounts'], isAccount) && nullable(value['next_cursor'], string)
  );
}
function profile(value: unknown): value is Api['schemas']['ProfileRevisionResponse'] {
  return (
    record(value) &&
    nullable(value['display_name'], string) &&
    nullable(value['about'], string) &&
    nullable(value['programme'], string) &&
    nullable(value['year_label'], string) &&
    array(value['languages'], string) &&
    integer(value['version']) &&
    instant(value['saved_at']) &&
    (value['task'] === 'find_help' || value['task'] === 'offer_help')
  );
}
function subject(value: unknown): value is Api['schemas']['GoalResponse']['subject'] {
  return (
    record(value) &&
    string(value['label']) &&
    ((uuid(value['id']) && (value['kind'] === undefined || value['kind'] === 'canonical')) ||
      (!('id' in value) && (value['kind'] === undefined || value['kind'] === 'custom')))
  );
}
function goal(value: unknown): value is Api['schemas']['GoalResponse'] {
  return (
    record(value) &&
    uuid(value['id']) &&
    integer(value['version']) &&
    subject(value['subject']) &&
    nullable(value['topic'], string) &&
    nullable(value['context'], string) &&
    typeof value['shared_learning'] === 'boolean' &&
    instant(value['created_at']) &&
    instant(value['updated_at']) &&
    nullable(value['completed_at'], instant)
  );
}
function helpSubject(value: unknown): value is Api['schemas']['HelpSubjectResponse'] {
  return (
    record(value) &&
    uuid(value['subject_id']) &&
    string(value['label']) &&
    nullable(value['topic_note'], string)
  );
}
function help(value: unknown): value is Api['schemas']['HelpResponse'] {
  return (
    record(value) &&
    integer(value['version']) &&
    instant(value['saved_at']) &&
    array(value['subjects'], helpSubject)
  );
}
function photo(value: unknown): value is Api['schemas']['PhotoReferenceResponse'] {
  return (
    record(value) &&
    integer(value['version']) &&
    uuid(value['upload_id']) &&
    instant(value['saved_at'])
  );
}
function lifecycle(value: unknown): value is Api['schemas']['LifecycleResponse'] {
  return (
    record(value) &&
    instant(value['completed_at']) &&
    integer(value['visibility_version']) &&
    nullable(value['hidden_at'], instant) &&
    instant(value['changed_at'])
  );
}
function exposure(value: unknown): value is Api['schemas']['ExposureResponse'] {
  return (
    record(value) &&
    instant(value['last_activity_at']) &&
    instant(value['confirmed_at']) &&
    nullable(value['paused_at'], instant) &&
    typeof value['inactivity_seconds'] === 'number' &&
    Number.isFinite(value['inactivity_seconds']) &&
    value['inactivity_seconds'] > 0
  );
}
function registration(value: unknown): value is Api['schemas']['RegistrationReceiptResponse'] {
  return (
    record(value) &&
    uuid(value['id']) &&
    uuid(value['context_id']) &&
    instant(value['registered_at']) &&
    string(value['notice_text']) &&
    value['surface'] === 'onboarding_completion' &&
    isPolicyReference(value['terms']) &&
    isPolicyReference(value['privacy'])
  );
}
function link(value: unknown): value is Api['schemas']['AccountLinkResponse'] {
  return (
    record(value) &&
    uuid(value['id']) &&
    nullable(value['version'], integer) &&
    (value['kind'] === 'google_identity' ||
      value['kind'] === 'profile_revision' ||
      value['kind'] === 'photo_revision' ||
      value['kind'] === 'goal_revision' ||
      value['kind'] === 'help_revision' ||
      value['kind'] === 'registration_receipt')
  );
}
export function isDetail(value: unknown): value is Api['schemas']['OperatorAccountDetailResponse'] {
  return (
    record(value) &&
    isAccount(value['account']) &&
    nullable(value['profile'], profile) &&
    nullable(value['goal'], goal) &&
    nullable(value['help_subjects'], help) &&
    nullable(value['photo'], photo) &&
    nullable(value['lifecycle'], lifecycle) &&
    nullable(value['exposure'], exposure) &&
    nullable(value['registration'], registration) &&
    array(value['links'], link)
  );
}
export function filterQuery(filters: AccountFilters): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== null) params.set(key, String(value));
  }
  return params.toString();
}
export function accountsOptions(
  http: Readonly<HttpClient>,
  actorId: string | null,
  filters: AccountFilters,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', actorId, 'operator', 'accounts', filters] as const,
    enabled: enabled && actorId !== null,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 0,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(http, `/api/v1/operator/accounts?${filterQuery(filters)}`, signal, isAccounts),
  });
}
export function detailOptions(
  http: Readonly<HttpClient>,
  actorId: string | null,
  accountId: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', actorId, 'operator', 'account', accountId] as const,
    enabled: enabled && actorId !== null && accountId !== null,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 0,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(
        http,
        `/api/v1/operator/accounts/${encodeURIComponent(accountId ?? '')}`,
        signal,
        (value): value is Api['schemas']['OperatorAccountDetailResponse'] =>
          isDetail(value) && value.account.account_id === accountId,
      ),
  });
}
