import type { Api } from '../../../../api.generated';

export const maxPhotoBytes = 10_000_000;
export interface Crop {
  readonly left: number;
  readonly top: number;
  readonly edge: number;
}
export interface ImageSize {
  readonly width: number;
  readonly height: number;
}

export function initialCrop(size: Readonly<ImageSize>): Crop {
  const edge = Math.min(size.width, size.height);
  return { left: (size.width - edge) / 2, top: (size.height - edge) / 2, edge };
}
export function moveCrop(
  crop: Readonly<Crop>,
  size: Readonly<ImageSize>,
  x: number,
  y: number,
): Crop {
  return {
    ...crop,
    left: Math.max(0, Math.min(size.width - crop.edge, crop.left + x)),
    top: Math.max(0, Math.min(size.height - crop.edge, crop.top + y)),
  };
}
export function zoomCrop(crop: Readonly<Crop>, size: Readonly<ImageSize>, ratio: number): Crop {
  const edge = Math.max(
    Math.min(size.width, size.height) / 4,
    Math.min(Math.min(size.width, size.height), crop.edge / ratio),
  );
  return moveCrop(
    { left: crop.left + (crop.edge - edge) / 2, top: crop.top + (crop.edge - edge) / 2, edge },
    size,
    0,
    0,
  );
}
export async function sourceType(
  file: Readonly<Blob>,
): Promise<Api['schemas']['PhotoContentType'] | null> {
  if (file.size === 0 || file.size > maxPhotoBytes) return null;
  const head = new Uint8Array(await file.slice(0, 8).arrayBuffer());
  if (head[0] === 0xff && head[1] === 0xd8 && head[2] === 0xff) return 'image/jpeg';
  if ([137, 80, 78, 71, 13, 10, 26, 10].every((part, index) => part === head[index]))
    return 'image/png';
  return null;
}
export async function sourceHash(file: Readonly<Blob>): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (part) => part.toString(16).padStart(2, '0')).join('');
}
export async function croppedImage(
  source: Readonly<CanvasImageSource>,
  crop: Readonly<Crop>,
): Promise<Blob> {
  const edge = Math.max(1, Math.min(1024, Math.floor(crop.edge)));
  const canvas = new OffscreenCanvas(edge, edge);
  const context = canvas.getContext('2d');
  if (context === null) throw new Error('Photo canvas is unavailable');
  context.drawImage(source, crop.left, crop.top, crop.edge, crop.edge, 0, 0, edge, edge);
  return await canvas.convertToBlob({ type: 'image/jpeg', quality: 0.9 });
}
