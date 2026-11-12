import type { Locator } from '@playwright/test';
import { expect } from './visual';

// Known human-readable UI copy must not wrap inside ordinary words.
export async function assertNaturalWordWrapping(locator: Readonly<Locator>): Promise<void> {
  const words = await locator.evaluate((element: Readonly<HTMLElement>) => {
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    let tested = 0;
    let broken: readonly string[] = [];
    for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
      const text = node.textContent ?? '';
      for (const match of text.matchAll(/\p{L}[\p{L}\p{M}]*/gu)) {
        const word = match[0];
        const range = document.createRange();
        range.setStart(node, match.index);
        range.setEnd(node, match.index + word.length);
        const rows = new Set(
          Array.from(range.getClientRects())
            .filter((rect: Readonly<DOMRect>) => rect.width > 0 && rect.height > 0)
            .map((rect: Readonly<DOMRect>) => rect.top),
        );
        tested += 1;
        if (rows.size !== 1) broken = [...broken, word];
      }
    }
    return { tested, broken };
  });
  expect(words.tested).toBeGreaterThan(0);
  expect(words.broken).toEqual([]);
}

// Exact painted text containment; no tolerance, clipping or font changes.
export async function assertFullTextFits(locator: Readonly<Locator>): Promise<void> {
  const fit = await locator.evaluate((element: Readonly<HTMLElement>) => {
    const box = element.getBoundingClientRect();
    const range = document.createRange();
    range.selectNodeContents(element);
    return {
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      clientHeight: element.clientHeight,
      scrollHeight: element.scrollHeight,
      allTextRectsInside: Array.from(range.getClientRects()).every(
        (rect: Readonly<DOMRect>) =>
          rect.left >= box.left &&
          rect.right <= box.right &&
          rect.top >= box.top &&
          rect.bottom <= box.bottom,
      ),
    };
  });
  expect(fit.scrollWidth).toBeLessThanOrEqual(fit.clientWidth);
  expect(fit.scrollHeight).toBeLessThanOrEqual(fit.clientHeight);
  expect(fit.allTextRectsInside).toBe(true);
}

// Visible-overflow text can extend beyond a rounded client box without clipping.
// Check every actual hidden/clip ancestor exactly; primary buttons retain the
// separate full-control containment assertion above.
export async function assertTextPaintNotClipped(locator: Readonly<Locator>): Promise<void> {
  const paint = await locator.evaluate((element: Readonly<HTMLElement>) => {
    const range = document.createRange();
    range.selectNodeContents(element);
    const rects = Array.from(range.getClientRects()).map((rect: Readonly<DOMRect>) => ({
      left: rect.left,
      right: rect.right,
      top: rect.top,
      bottom: rect.bottom,
    }));
    let clips: readonly Readonly<{
      readonly x: boolean;
      readonly y: boolean;
      readonly left: number;
      readonly right: number;
      readonly top: number;
      readonly bottom: number;
    }>[] = [];
    for (
      let ancestor: Readonly<HTMLElement> | null = element;
      ancestor !== null;
      ancestor = ancestor.parentElement
    ) {
      const style = getComputedStyle(ancestor);
      const x = style.overflowX === 'hidden' || style.overflowX === 'clip';
      const y = style.overflowY === 'hidden' || style.overflowY === 'clip';
      if (x || y) {
        const box = ancestor.getBoundingClientRect();
        clips = [
          ...clips,
          {
            x,
            y,
            left: box.left + Number.parseFloat(style.borderLeftWidth),
            right: box.right - Number.parseFloat(style.borderRightWidth),
            top: box.top + Number.parseFloat(style.borderTopWidth),
            bottom: box.bottom - Number.parseFloat(style.borderBottomWidth),
          },
        ];
      }
    }
    return { rects, clips };
  });
  expect(paint.rects.length).toBeGreaterThan(0);
  expect(paint.clips.length).toBeGreaterThan(0);
  for (const rect of paint.rects) {
    for (const clip of paint.clips) {
      if (clip.x) {
        expect(rect.left).toBeGreaterThanOrEqual(clip.left);
        expect(rect.right).toBeLessThanOrEqual(clip.right);
      }
      if (clip.y) {
        expect(rect.top).toBeGreaterThanOrEqual(clip.top);
        expect(rect.bottom).toBeLessThanOrEqual(clip.bottom);
      }
    }
  }
}
