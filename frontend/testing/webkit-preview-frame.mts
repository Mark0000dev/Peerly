import type { Page, Screencast } from '@playwright/test';

type CapturePage = Readonly<Pick<Page, 'viewportSize'>> &
  Readonly<{ readonly screencast: Readonly<Pick<Screencast, 'start' | 'stop'>> }>;
type NativeFrame = Readonly<{
  readonly data: Buffer;
  readonly timestamp: number;
  readonly viewportWidth: number;
  readonly viewportHeight: number;
}>;

function dimensions(
  data: Readonly<Buffer>,
): Readonly<{ readonly width: number; readonly height: number }> {
  if (data[0] !== 0xff || data[1] !== 0xd8) throw new Error('Preview frame is not JPEG');
  let offset = 2;
  while (offset + 4 <= data.length) {
    if (data[offset] !== 0xff) throw new Error('Invalid JPEG marker');
    const marker = data[offset + 1];
    if (marker === undefined || marker === 0xda || marker === 0xd9) break;
    const length = data.readUInt16BE(offset + 2);
    if (length < 2 || offset + length + 2 > data.length) throw new Error('Truncated JPEG frame');
    if (marker >= 0xc0 && marker <= 0xcf && marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc) {
      if (length < 8) throw new Error('Invalid JPEG dimensions');
      return { height: data.readUInt16BE(offset + 5), width: data.readUInt16BE(offset + 7) };
    }
    offset += length + 2;
  }
  throw new Error('JPEG frame has no dimensions');
}

// Only WebKit open/zoom TuiPreview: never substitute this for ordinary screen PNGs.
// The caller establishes public readiness; each independent start needs a fresh frame.
export async function captureWebkitPreviewFrame(
  page: CapturePage,
  options: Readonly<{
    readonly engine: 'chromium' | 'firefox' | 'webkit';
    readonly state: 'open' | 'zoom';
    readonly timeoutMs?: number;
    readonly recordFrame?: (frame: NativeFrame, cycle: number) => Promise<void>;
  }>,
): Promise<Buffer> {
  if (options.engine !== 'webkit' || !['open', 'zoom'].includes(options.state))
    throw new Error('Compositor capture is restricted to WebKit open/zoom Preview');
  const viewport = page.viewportSize();
  if (viewport === null) throw new Error('Preview requires an explicit full viewport');
  if (typeof page.screencast.start !== 'function')
    throw new Error('Pinned WebKit public screencast API is unavailable');
  let previous: Buffer | null = null;
  for (let cycle = 0; cycle < 3; cycle += 1) {
    const started = Date.now();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let primary: unknown;
    let failed = false;
    try {
      const frame = await new Promise<NativeFrame>((resolve, reject) => {
        timer = setTimeout(() => {
          reject(new Error('No fresh full-viewport Preview frame'));
        }, options.timeoutMs ?? 5000);
        let first: NativeFrame | null = null;
        let startedSuccessfully = false;
        void page.screencast
          .start({
            size: viewport,
            quality: 100,
            onFrame: (incoming: NativeFrame) => {
              if (first !== null) return;
              first = incoming;
              if (startedSuccessfully) resolve(incoming);
            },
          })
          .then(() => {
            startedSuccessfully = true;
            if (first !== null) resolve(first);
          })
          .catch(reject);
      });
      if (!Number.isFinite(frame.timestamp) || frame.timestamp < started)
        throw new Error('Stale Preview compositor frame');
      const encoded = dimensions(frame.data);
      if (
        frame.viewportWidth !== viewport.width ||
        frame.viewportHeight !== viewport.height ||
        encoded.width !== viewport.width ||
        encoded.height !== viewport.height
      )
        throw new Error('Preview compositor dimensions differ from the full viewport');
      await options.recordFrame?.(frame, cycle);
      if (previous !== null && !previous.equals(frame.data))
        throw new Error('Fresh Preview compositor frames are not byte-stable');
      previous = Buffer.from(frame.data);
    } catch (error: unknown) {
      failed = true;
      primary = error;
    } finally {
      clearTimeout(timer);
    }
    try {
      await page.screencast.stop();
    } catch (cleanup: unknown) {
      if (failed)
        throw new AggregateError([primary, cleanup], 'Preview capture and cleanup both failed', {
          cause: cleanup,
        });
      throw cleanup;
    }
    if (failed) throw primary;
  }
  if (previous === null) throw new Error('No Preview compositor frame captured');
  return previous;
}
