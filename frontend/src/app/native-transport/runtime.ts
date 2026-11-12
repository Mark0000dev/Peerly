import { computed, ErrorHandler, inject, InjectionToken, signal } from '@angular/core';
import { Capacitor, registerPlugin } from '@capacitor/core';
import { readNativeBuild, NativeConfigurationFailure } from './config';
import type { NativeBuild } from './config';
import type { NativeApiTransport, NativeTransportPlugin } from './transport';

// Runtime/config/resource ownership only: no actor, credential or server data here.
export class NativeRuntime {
  private readonly configured = signal<NativeBuild | null>(null);
  public readonly config = this.configured.asReadonly();
  private readonly transportState = signal<NativeApiTransport | null>(null);
  public readonly epoch = computed(() => this.transportState()?.epoch() ?? null);
  public constructor(
    private readonly plugin: Readonly<NativeTransportPlugin>,
    private readonly report: (error: Readonly<Error>) => void,
  ) {}
  public async initialize(): Promise<void> {
    const build = readNativeBuild(await this.plugin.configuration());
    const { NativeApiTransport } = await import('./transport');
    const transport = new NativeApiTransport(this.plugin, (error) => {
      this.report(error);
    });
    await transport.advance(false);
    this.transportState.set(transport);
    this.configured.set(build);
  }
  public get transport(): NativeApiTransport {
    const transport = this.transportState();
    if (transport === null) throw new NativeConfigurationFailure();
    return transport;
  }
  public build(): NativeBuild {
    const configured = this.configured();
    if (configured === null) throw new NativeConfigurationFailure();
    return configured;
  }
}

export const NATIVE_RUNTIME = new InjectionToken<NativeRuntime | null>('Peerly native transport', {
  providedIn: 'root',
  factory: () => {
    if (!Capacitor.isNativePlatform()) return null;
    const errors = inject(ErrorHandler);
    return new NativeRuntime(registerPlugin<NativeTransportPlugin>('PeerlyTransport'), (error) => {
      errors.handleError(error);
    });
  },
});
