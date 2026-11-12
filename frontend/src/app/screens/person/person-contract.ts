import type { HttpClient } from '@angular/common/http';
import { queryOptions } from '@tanstack/angular-query-experimental';
import type { QueryFunctionContext } from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { readJpeg, readJson } from '../../api-http';

type Profile = Api['schemas']['PublicProfileResponse'];
type Block = Api['schemas']['BlockStateResponse'];
function record(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null;
}
function nullableText(value: unknown): boolean {
  return value === null || typeof value === 'string';
}
function version(value: unknown): boolean {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}
export function isBlock(value: unknown): value is Block {
  return (
    record(value) &&
    typeof value['person_id'] === 'string' &&
    typeof value['blocked'] === 'boolean' &&
    version(value['version']) &&
    nullableText(value['changed_at'])
  );
}
function isGoal(value: unknown): value is Api['schemas']['GoalResponse'] {
  if (!record(value) || !record(value['subject'])) return false;
  const subject = value['subject'];
  return (
    typeof value['id'] === 'string' &&
    version(value['version']) &&
    typeof value['created_at'] === 'string' &&
    typeof value['updated_at'] === 'string' &&
    nullableText(value['completed_at']) &&
    nullableText(value['context']) &&
    nullableText(value['topic']) &&
    typeof value['shared_learning'] === 'boolean' &&
    typeof subject['label'] === 'string' &&
    (subject['kind'] === 'custom' ||
      (subject['kind'] === undefined && !('id' in subject)) ||
      ((subject['kind'] === undefined || subject['kind'] === 'canonical') &&
        typeof subject['id'] === 'string'))
  );
}
function isHelp(value: unknown): value is Api['schemas']['HelpResponse'] {
  return (
    record(value) &&
    version(value['version']) &&
    typeof value['saved_at'] === 'string' &&
    Array.isArray(value['subjects']) &&
    value['subjects'].every(
      (item: unknown) =>
        record(item) &&
        typeof item['subject_id'] === 'string' &&
        typeof item['label'] === 'string' &&
        nullableText(item['topic_note']),
    )
  );
}
export function isProfile(value: unknown): value is Profile {
  return (
    record(value) &&
    typeof value['id'] === 'string' &&
    typeof value['display_name'] === 'string' &&
    typeof value['access_context_id'] === 'string' &&
    version(value['version']) &&
    nullableText(value['about']) &&
    nullableText(value['programme']) &&
    nullableText(value['year_label']) &&
    Array.isArray(value['languages']) &&
    value['languages'].every((item: unknown) => typeof item === 'string') &&
    record(value['photo']) &&
    typeof value['photo']['display_url'] === 'string' &&
    version(value['photo']['version']) &&
    isBlock(value['own_block']) &&
    value['own_block'].person_id === value['id'] &&
    (value['goal'] === null || isGoal(value['goal'])) &&
    (value['help_subjects'] === null || isHelp(value['help_subjects']))
  );
}
export function isBlocks(value: unknown): value is Api['schemas']['OwnBlocksResponse'] {
  return (
    record(value) &&
    nullableText(value['next_cursor']) &&
    Array.isArray(value['people']) &&
    value['people'].every(
      (item: unknown) =>
        record(item) &&
        isBlock(item['block']) &&
        typeof item['deleted'] === 'boolean' &&
        nullableText(item['display_name']),
    )
  );
}
export function isReceipt(value: unknown): value is Api['schemas']['ProfileReportReceipt'] {
  return (
    record(value) &&
    typeof value['id'] === 'string' &&
    typeof value['context_id'] === 'string' &&
    typeof value['submitted_at'] === 'string' &&
    (value['kind'] === undefined || value['kind'] === 'profile')
  );
}
export function personOptions(
  http: Readonly<HttpClient>,
  accountId: string | null,
  personId: string,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', accountId, 'person', personId] as const,
    gcTime: 0,
    enabled: enabled && accountId !== null && personId.length > 0,
    retry: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(http, `/api/v1/people/${encodeURIComponent(personId)}`, signal, isProfile),
  });
}
export function blocksOptions(
  http: Readonly<HttpClient>,
  accountId: string | null,
  cursor: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', accountId, 'blocks', cursor] as const,
    enabled: enabled && accountId !== null,
    retry: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(
        http,
        `/api/v1/me/blocks${cursor === null ? '' : `?cursor=${encodeURIComponent(cursor)}`}`,
        signal,
        isBlocks,
      ),
  });
}
export function commentProblem(
  category: Api['schemas']['ReportCategory'],
  comment: string,
): string | null {
  if (Array.from(comment).length > 1000) return 'Use no more than 1000 characters.';
  return category === 'other' && comment.trim().length === 0
    ? 'Explain the reason for your report.'
    : null;
}

export function photoOptions(
  http: Readonly<HttpClient>,
  accountId: string | null,
  personId: string,
  photoVersion: number | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', accountId, 'person-photo', personId, photoVersion] as const,
    gcTime: 0,
    staleTime: 0,
    enabled: enabled && accountId !== null && photoVersion !== null,
    retry: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJpeg(
        http,
        `/api/v1/people/${encodeURIComponent(personId)}/photo/${String(photoVersion)}`,
        signal,
      ),
  });
}

const languageNames = new Intl.DisplayNames(['en'], { type: 'language' });
export function languageName(code: string): string {
  return /^[a-z]{2,3}$/.test(code) ? (languageNames.of(code) ?? code) : code;
}
