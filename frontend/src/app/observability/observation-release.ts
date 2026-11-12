import { DOCUMENT } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom, timeout } from 'rxjs';
import { validatedRelease } from './observation-privacy';
import type { ReleaseAssets } from './observation-privacy';

// Public immutable build configuration, never credentials or business/query state.
export function publicRelease(value: unknown, origin: string): ReleaseAssets | null {
  if (
    typeof value !== 'object' ||
    value === null ||
    !('releaseId' in value) ||
    typeof value.releaseId !== 'string' ||
    !('origin' in value) ||
    value.origin !== origin ||
    !('assets' in value) ||
    !Array.isArray(value.assets) ||
    Object.keys(value).length !== 3
  )
    return null;
  const assets: readonly unknown[] = value.assets;
  if (
    !assets.every(
      (asset): asset is ReleaseAssets['assets'][number] =>
        typeof asset === 'object' &&
        asset !== null &&
        'basename' in asset &&
        typeof asset.basename === 'string' &&
        'assetId' in asset &&
        typeof asset.assetId === 'number' &&
        Object.keys(asset).length === 2,
    )
  )
    return null;
  return validatedRelease({ releaseId: value.releaseId, origin, assets });
}

@Injectable({ providedIn: 'root' })
export class ObservationRelease {
  private readonly http = inject(HttpClient);
  private readonly document = inject(DOCUMENT);
  private readonly configuration = signal<ReleaseAssets | null>(null);
  public readonly current = this.configuration.asReadonly();

  public async load(): Promise<void> {
    try {
      const response: unknown = await firstValueFrom(
        this.http.get<unknown>('/assets/observation-release.json').pipe(timeout(3000)),
      );
      this.configuration.set(publicRelease(response, this.document.location.origin));
    } catch {
      // Optional public build metadata never blocks manual/core application use.
      // No response, exception, resource URL or raw stack is retained or reported.
      this.configuration.set(null);
    }
  }
}
