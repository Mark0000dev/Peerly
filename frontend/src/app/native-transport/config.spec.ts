import { describe, expect, it } from 'vitest';
import { NativeConfigurationFailure, nativeBuilds, readNativeBuild } from './config';
import { nativeFixture } from './native-test.fixtures';

describe('actual application identity and fixed native origin', () => {
  it.each([nativeBuilds.production, nativeBuilds.staging])(
    'initializes the owned variant $appId',
    async (build) => {
      const context = nativeFixture(build);
      expect(() => context.runtime.build()).toThrow(NativeConfigurationFailure);
      expect(() => context.runtime.transport).toThrow(NativeConfigurationFailure);
      expect(context.runtime.epoch()).toBeNull();
      await context.runtime.initialize();
      expect(context.runtime.build()).toBe(build);
      expect(context.runtime.config()).toBe(build);
      expect(context.runtime.epoch()).not.toBeNull();
    },
  );
  it.each([
    null,
    {},
    { ...nativeBuilds.production, appId: nativeBuilds.staging.appId },
    { ...nativeBuilds.production, wakeUrl: nativeBuilds.production.wakeUrl + '?token=forbidden' },
    { ...nativeBuilds.staging, apiOrigin: nativeBuilds.production.apiOrigin },
  ])('rejects an incoherent or data-bearing configuration', (value) => {
    expect(() => readNativeBuild(value)).toThrow(NativeConfigurationFailure);
  });
});
