import type { Epoch, Metric, ObservationSink } from './observation-contract';
interface NumericEntry {
  readonly entryType: string;
  readonly name: string;
  readonly startTime: number;
  readonly duration: number;
}
// Does not retain a native entry, target, resource URL, attribution or DOM element.
export function performanceValue(
  entry: NumericEntry,
  epoch: Epoch,
  now: number,
): Readonly<{ readonly metric: Metric; readonly value: number }> | null {
  if (
    !Number.isFinite(entry.startTime) ||
    entry.startTime < epoch.startedAt ||
    entry.startTime > now
  )
    return null;
  if (entry.entryType === 'paint' && entry.name === 'first-contentful-paint')
    return { metric: 'fcp', value: entry.startTime };
  if (
    entry.entryType === 'navigation' &&
    'responseStart' in entry &&
    typeof entry.responseStart === 'number'
  )
    return { metric: 'ttfb', value: entry.responseStart - entry.startTime };
  if (entry.entryType === 'largest-contentful-paint')
    return { metric: 'lcp', value: entry.startTime };
  return null;
}
// LCP/FCP are page timings; event timing is NOT mislabeled as INP. INP/CLS require
// full lifecycle aggregation; unsupported/unimplemented metrics are not fabricated.
export function observeNativePerformance(sink: ObservationSink, now: () => number): () => void {
  if (typeof PerformanceObserver === 'undefined') return () => undefined;
  const supported = PerformanceObserver.supportedEntryTypes;
  const observers: readonly PerformanceObserver[] = [
    'paint',
    'navigation',
    'largest-contentful-paint',
  ]
    .filter((type) => supported.includes(type))
    .map((type) => {
      const observer = new PerformanceObserver((list) => {
        const epoch = sink.epoch();
        if (epoch === null) return;
        for (const entry of list.getEntries()) {
          const value = performanceValue(entry, epoch, now());
          if (value !== null) sink.observe({ kind: 'performance.observed', ...value });
        }
      });
      // No buffered previous-actor/guest history and no global performance-buffer clear.
      observer.observe({ type, buffered: false });
      return observer;
    });
  return () => {
    for (const observer of observers) observer.disconnect();
  };
}
