import { DestroyRef, Injector, afterNextRender, computed, inject, signal } from '@angular/core';

// Native resource ownership only: query cache remains the sole owner of server bytes.
// Construct in the consuming component's injection context, never in a root service.
export class ImageResource {
  private readonly destroy = inject(DestroyRef);
  private readonly injector = inject(Injector);
  private readonly resource = signal<Readonly<{
    readonly source: Readonly<Blob>;
    readonly url: string;
  }> | null>(null);
  public readonly url = computed(() => this.resource()?.url ?? null);

  public constructor() {
    this.destroy.onDestroy(() => {
      this.clear();
    });
  }

  public replace(source: Readonly<Blob>): boolean {
    if (this.resource()?.source === source) return false;
    this.clear();
    this.resource.set({ source, url: URL.createObjectURL(source) });
    return true;
  }

  public clear(): void {
    const old = this.resource()?.url ?? null;
    this.resource.set(null);
    if (old === null) return;
    const release = (): void => {
      URL.revokeObjectURL(old);
    };
    if (this.destroy.destroyed) {
      queueMicrotask(release);
      return;
    }
    const unregister = this.destroy.onDestroy(() => {
      queueMicrotask(release);
    });
    afterNextRender(
      () => {
        unregister();
        release();
      },
      { injector: this.injector },
    );
  }
}
