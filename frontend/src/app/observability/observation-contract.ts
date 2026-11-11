// Exact tested head55 export ea6ab8; canonical shared generation is lead-owned.
import type { Api } from '../api.generated';
export const screens = [
  'welcome',
  'verification',
  'onboarding',
  'discover',
  'requests',
  'chats',
  'conversation',
  'profile',
  'study',
  'notifications',
  'support',
  'help',
  'terms',
  'privacy',
  'operator',
  'unknown',
] as const;
export type Screen = Api['schemas']['Screen'];
export const actions = [
  'navigate',
  'submit',
  'retry',
  'cancel',
  'apply',
  'dismiss',
  'load_more',
  'upload',
  'permission_request',
  'open_settings',
] as const;
export type Action = Api['schemas']['Action'];
export const outcomes = [
  'invoked',
  'succeeded_observed',
  'rejected_observed',
  'failed_observed',
  'cancelled_observed',
  'unknown',
] as const;
export const metrics = ['route_ready', 'lcp', 'inp', 'fcp', 'ttfb', 'cls'] as const;
export type Metric = Api['schemas']['Metric'];
export const categories = [
  'network',
  'http',
  'timeout',
  'offline',
  'javascript',
  'render',
  'resource',
  'unknown',
] as const;
export const methods = ['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'] as const;
export type Method = Api['schemas']['HttpMethod'];
export const httpRoutes = [
  'identity',
  'verification',
  'registration',
  'profile',
  'study',
  'discovery',
  'requests',
  'conversations',
  'media',
  'support',
  'notifications',
  'ai',
  'operator',
  'other',
] as const;
export type HttpRoute = Api['schemas']['ApiRoute'];
export const statusClasses = ['1xx', '2xx', '3xx', '4xx', '5xx', 'network', 'cancelled'] as const;
export type StatusClass = Api['schemas']['StatusClass'];
export type PublicFrame = Api['schemas']['PublicFrameBody'];
export type Observation = Api['schemas']['ObservationBody'];
type WithoutHeader<T> = T extends Observation
  ? Omit<T, 'event_id' | 'observed_at' | 'screen'>
  : never;
export type ObservationInput = WithoutHeader<Observation>;
// Client always requires the actual actor fence even though server accepts null.
export type Batch = Omit<Api['schemas']['ObservationBatchBody'], 'expected_actor_id'> &
  Readonly<{ readonly expected_actor_id: string }>;
export type Receipt = Api['schemas']['ObservationBatchResponse'];
export type QualityReason = Api['schemas']['QualityReason'];
export const qualityReasons = [
  'overflow',
  'invalid',
  'expired',
  'rejected',
  'exhausted',
  'unavailable',
] as const satisfies readonly QualityReason[];
export type DeliveryResult =
  | Readonly<{ readonly kind: 'received'; readonly receipt: unknown }>
  | Readonly<{ readonly kind: 'failed'; readonly status: number; readonly retryAfterMs?: number }>;
export interface DeliveryIntent {
  readonly key: string;
  readonly body: Batch;
  readonly json: string;
  readonly signal: Readonly<AbortSignal>;
}
export interface Delivery {
  readonly send: (intent: DeliveryIntent) => Promise<DeliveryResult>;
}
export interface ActionHandle {
  readonly action: Action;
  readonly actionId: string;
  readonly traceId: string;
}
export interface Epoch {
  readonly id: number;
  readonly startedAt: number;
}
export interface ObservationSink {
  readonly observe: (input: ObservationInput) => boolean;
  readonly beginAction: (action: Action) => ActionHandle | null;
  readonly epoch: () => Epoch | null;
}
export function uuid(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value)
  );
}
export function traceId(value: unknown): value is string {
  return typeof value === 'string' && /^[0-9a-f]{32}$/.test(value) && !/^0+$/.test(value);
}
