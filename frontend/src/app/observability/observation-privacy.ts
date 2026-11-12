import {
  actions,
  outcomes,
  metrics,
  categories,
  methods,
  httpRoutes,
  statusClasses,
  qualityReasons,
  uuid,
  traceId,
} from './observation-contract';
import type { ObservationInput, PublicFrame } from './observation-contract';
export interface ReleaseAssets {
  readonly releaseId: string;
  readonly origin: string;
  readonly assets: readonly Readonly<{ readonly basename: string; readonly assetId: number }>[];
}
function object(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null;
}
function member<T extends string>(items: readonly T[], value: unknown): value is T {
  return items.some((item) => item === value);
}
function number(value: unknown, max: number, integer = false): value is number {
  return (
    typeof value === 'number' &&
    Number.isFinite(value) &&
    value >= 0 &&
    value <= max &&
    (!integer || Number.isInteger(value))
  );
}
function frame(value: unknown): value is PublicFrame {
  return (
    object(value) &&
    number(value['asset_id'], 4095, true) &&
    number(value['line'], 2147483647, true) &&
    value['line'] >= 1 &&
    number(value['column'], 2147483647, true)
  );
}
// Reconstruct every field. Even typed callers cannot smuggle extra properties via spread/JSON.
export function sanitizeObservation(
  value: unknown,
  release: ReleaseAssets | null,
): ObservationInput | null {
  try {
    return sanitize(value, release);
  } catch {
    return null;
  }
}
function sanitize(value: unknown, release: ReleaseAssets | null): ObservationInput | null {
  if (!object(value)) return null;
  switch (value['kind']) {
    case 'screen.viewed':
      return { kind: 'screen.viewed' };
    case 'action.observed': {
      if (!member(actions, value['action']) || !member(outcomes, value['outcome'])) return null;
      return {
        kind: 'action.observed',
        action: value['action'],
        outcome: value['outcome'],
        ...(uuid(value['action_id']) ? { action_id: value['action_id'] } : {}),
      };
    }
    case 'performance.observed':
      return member(metrics, value['metric']) &&
        number(value['value'], value['metric'] === 'cls' ? 100 : 60000)
        ? { kind: 'performance.observed', metric: value['metric'], value: value['value'] }
        : null;
    case 'error.observed': {
      if (!member(categories, value['category'])) return null;
      const candidates: readonly unknown[] = Array.isArray(value['frames']) ? value['frames'] : [];
      const frames =
        release === null
          ? []
          : candidates
              .slice(0, 3)
              .filter(frame)
              .filter((item) => release.assets.some((asset) => asset.assetId === item.asset_id))
              .map((item) => ({ asset_id: item.asset_id, line: item.line, column: item.column }));
      return {
        kind: 'error.observed',
        category: value['category'],
        ...(frames.length > 0 ? { frames } : {}),
      };
    }
    case 'quality.observed':
      return member(qualityReasons, value['reason']) &&
        number(value['count'], 65535, true) &&
        value['count'] >= 1
        ? { kind: 'quality.observed', reason: value['reason'], count: value['count'] }
        : null;
    case 'http.observed':
      if (
        !member(methods, value['method']) ||
        !member(httpRoutes, value['route']) ||
        !member(statusClasses, value['status_class']) ||
        !number(value['duration_ms'], 60000, true)
      )
        return null;
      return {
        kind: 'http.observed',
        method: value['method'],
        route: value['route'],
        status_class: value['status_class'],
        duration_ms: value['duration_ms'],
        ...(uuid(value['request_id']) ? { request_id: value['request_id'] } : {}),
        ...(uuid(value['action_id']) ? { action_id: value['action_id'] } : {}),
        ...(traceId(value['trace_id']) ? { trace_id: value['trace_id'] } : {}),
      };
    default:
      return null;
  }
}
export function validatedRelease(value: ReleaseAssets | null): ReleaseAssets | null {
  if (
    value === null ||
    !/^[0-9a-f]{40}$/.test(value.releaseId) ||
    value.assets.length === 0 ||
    value.assets.length > 4096
  )
    return null;
  try {
    const origin = new URL(value.origin);
    if (origin.origin !== value.origin || origin.protocol !== 'https:') return null;
    if (
      !value.assets.every(
        (asset, index) =>
          asset.assetId === index &&
          /^(?:main|polyfills|chunk)-[A-Za-z0-9_-]{1,64}\.js$/.test(asset.basename) &&
          (index === 0 || String(value.assets[index - 1]?.basename) < asset.basename),
      )
    )
      return null;
    return {
      releaseId: value.releaseId,
      origin: value.origin,
      assets: value.assets.map((asset) => ({ basename: asset.basename, assetId: asset.assetId })),
    };
  } catch {
    return null;
  }
}
// Stack text is transient input only. Emit neither URL, message nor function name.
export function publicFrames(
  stack: unknown,
  release: ReleaseAssets | null,
): readonly PublicFrame[] {
  if (typeof stack !== 'string' || release === null) return [];
  const frames = stack
    .slice(0, 8192)
    .split('\n')
    .slice(0, 32)
    .flatMap((line) => {
      const location = /(https:\/\/[^\s()]+):(\d{1,10}):(\d{1,10})\)?$/.exec(line);
      if (location === null) return [];
      try {
        const url = new URL(location[1] ?? '');
        if (
          url.origin !== release.origin ||
          url.search !== '' ||
          url.hash !== '' ||
          url.username !== '' ||
          url.password !== ''
        )
          return [];
        const asset = release.assets.find((item) => url.pathname === '/' + item.basename);
        const candidate = {
          asset_id: asset?.assetId,
          line: Number(location[2]),
          column: Number(location[3]),
        };
        return frame(candidate)
          ? [{ asset_id: candidate.asset_id, line: candidate.line, column: candidate.column }]
          : [];
      } catch {
        return [];
      }
    });
  return frames.slice(0, 3);
}
