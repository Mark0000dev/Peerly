import { describe, expect, it } from 'vitest';
import {
  croppedImage,
  initialCrop,
  maxPhotoBytes,
  moveCrop,
  sourceHash,
  sourceType,
  zoomCrop,
} from './image';

describe('local photo preparation', () => {
  it('centres a square and clamps movement without changing the draft', () => {
    const size = { width: 240, height: 120 };
    const crop = initialCrop(size);
    expect(crop).toEqual({ left: 60, top: 0, edge: 120 });
    expect(moveCrop(crop, size, -1000, 1000)).toEqual({ left: 0, top: 0, edge: 120 });
    expect(moveCrop(crop, size, 1000, -1000)).toEqual({ left: 120, top: 0, edge: 120 });
    expect(crop.left).toBe(60);
    expect(initialCrop({ width: 120, height: 240 })).toEqual({ left: 0, top: 60, edge: 120 });
  });
  it('zooms around the selection centre within available pixels', () => {
    const size = { width: 240, height: 120 };
    const crop = initialCrop(size);
    expect(zoomCrop(crop, size, 2)).toEqual({ left: 90, top: 30, edge: 60 });
    expect(zoomCrop(crop, size, 100)).toEqual({ left: 105, top: 45, edge: 30 });
    expect(zoomCrop(crop, size, 0.01)).toEqual(crop);
  });
  it('inspects bytes rather than trusting the filename or MIME hint', async () => {
    expect(
      await sourceType(new Blob([new Uint8Array([255, 216, 255])], { type: 'text/plain' })),
    ).toBe('image/jpeg');
    expect(await sourceType(new Blob([new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10])]))).toBe(
      'image/png',
    );
    expect(await sourceType(new Blob(['not a photo'], { type: 'image/png' }))).toBeNull();
    expect(await sourceType(new Blob())).toBeNull();
    expect(await sourceType(new Blob([new Uint8Array(maxPhotoBytes + 1)]))).toBeNull();
  });
  it('hashes the final payload using SHA-256', async () => {
    expect(await sourceHash(new Blob(['abc']))).toBe(
      'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
    );
    expect(await sourceHash(new Blob(['abcd']))).not.toBe(await sourceHash(new Blob(['abc'])));
  });
  it('encodes only the selected pixels in a bounded JPEG', async () => {
    const source = new OffscreenCanvas(32, 16);
    const context = source.getContext('2d');
    if (context === null) throw new Error('Native canvas unavailable');
    context.putImageData(
      new ImageData(
        Uint8ClampedArray.from({ length: 32 * 16 * 4 }, (_, index) => {
          const x = Math.floor(index / 4) % 32;
          const channel = index % 4;
          return channel === 3 || (x < 16 ? channel === 0 : channel === 2) ? 255 : 0;
        }),
        32,
        16,
      ),
      0,
      0,
    );
    const blob = await croppedImage(source, { left: 16, top: 0, edge: 16 });
    expect(blob.type).toBe('image/jpeg');
    const bitmap = await createImageBitmap(blob);
    expect([bitmap.width, bitmap.height]).toEqual([16, 16]);
    const result = new OffscreenCanvas(16, 16).getContext('2d');
    if (result === null) throw new Error('Native canvas unavailable');
    result.drawImage(bitmap, 0, 0);
    const pixel = result.getImageData(8, 8, 1, 1).data;
    expect(pixel[0]).toBeLessThan(10);
    expect(pixel[2]).toBeGreaterThan(245);
    bitmap.close();
    const large = await croppedImage(source, { left: 0, top: 0, edge: 2048 });
    const limited = await createImageBitmap(large);
    expect([limited.width, limited.height]).toEqual([1024, 1024]);
    limited.close();
  });
  it('encodes a positive pixel even when a tiny source is zoomed to a fractional crop', async () => {
    const source = new OffscreenCanvas(1, 1);
    const context = source.getContext('2d');
    if (context === null) throw new Error('Native canvas unavailable');
    context.putImageData(new ImageData(new Uint8ClampedArray([255, 0, 0, 255]), 1, 1), 0, 0);
    const crop = zoomCrop(initialCrop({ width: 1, height: 1 }), { width: 1, height: 1 }, 4);
    const output = await croppedImage(source, crop);
    const bitmap = await createImageBitmap(output);
    expect([bitmap.width, bitmap.height]).toEqual([1, 1]);
    bitmap.close();
  });
});
