export type NativeVariant = 'production' | 'staging';
export interface NativeBuild {
  readonly appId: string;
  readonly appName: string;
  readonly apiOrigin: string;
  readonly wakeUrl: string;
}

export const nativeBuilds: Readonly<Record<NativeVariant, NativeBuild>> = {
  production: {
    appId: 'dev.alekseiorlov.peerly',
    appName: 'Peerly',
    apiOrigin: 'https://peerly.aleksei-orlov.dev',
    wakeUrl: 'dev.alekseiorlov.peerly://auth/complete',
  },
  staging: {
    appId: 'dev.alekseiorlov.peerly.staging',
    appName: 'Peerly Staging',
    apiOrigin: 'https://peerly-staging.aleksei-orlov.dev',
    wakeUrl: 'dev.alekseiorlov.peerly.staging://auth/complete',
  },
};

export class NativeConfigurationFailure extends Error {
  public constructor() {
    super('Native build configuration is invalid');
  }
}

export function readNativeBuild(value: unknown): NativeBuild {
  if (
    typeof value !== 'object' ||
    value === null ||
    !('appId' in value) ||
    !('apiOrigin' in value) ||
    !('wakeUrl' in value)
  )
    throw new NativeConfigurationFailure();
  const configured = Object.values(nativeBuilds).find(
    (build) =>
      build.appId === value.appId &&
      build.apiOrigin === value.apiOrigin &&
      build.wakeUrl === value.wakeUrl,
  );
  if (configured === undefined) throw new NativeConfigurationFailure();
  return configured;
}
