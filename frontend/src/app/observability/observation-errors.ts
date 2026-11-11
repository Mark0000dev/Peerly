import { ErrorHandler, InjectionToken, inject } from '@angular/core';
import { createObservationBridge } from './observation-bridge';
import type { ObservationBridge } from './observation-bridge';
import { publicFrames, validatedRelease } from './observation-privacy';
import type { ReleaseAssets } from './observation-privacy';
import { ObservationRelease } from './observation-release';
export const CLIENT_OBSERVATIONS = new InjectionToken<ObservationBridge>(
  'Authenticated client observations',
  { providedIn: 'root', factory: createObservationBridge },
);
export const CLIENT_RELEASE_ASSETS = new InjectionToken<() => ReleaseAssets | null>(
  'Validated public release assets',
  { providedIn: 'root', factory: () => inject(ObservationRelease).current },
);
// Root composition reuses Angular global listeners; never install a parallel
// window/console observer or replace the original diagnostic.
export class ObservationErrorHandler extends ErrorHandler {
  private readonly sink = inject(CLIENT_OBSERVATIONS);
  private readonly release = inject(CLIENT_RELEASE_ASSETS);
  public override handleError(error: unknown): void {
    try {
      // Only built-in identity determines a coarse category; name/message/cause
      // and arbitrary error properties never become event attributes.
      const frames =
        error instanceof Error ? publicFrames(error.stack, validatedRelease(this.release())) : [];
      this.sink.observe({
        kind: 'error.observed',
        category: error instanceof Error ? 'javascript' : 'unknown',
        ...(frames.length > 0 ? { frames } : {}),
      });
    } catch {
      // No telemetry failure may replace the original framework diagnostic.
    } finally {
      super.handleError(error);
    }
  }
}
