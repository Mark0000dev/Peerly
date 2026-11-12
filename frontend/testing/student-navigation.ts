import type { Page } from '@playwright/test';
import { expect } from './visual';

export async function assertStudentNavigationInViewport(
  page: Readonly<Page>,
  current: 'Discover' | 'Requests' | 'Chats' | 'Profile',
): Promise<void> {
  const navigation = page.getByRole('navigation', { name: 'Student navigation', exact: true });
  const bounds = await navigation.evaluate((element: Readonly<HTMLElement>) => {
    const box = element.getBoundingClientRect();
    return {
      left: box.left,
      right: box.right,
      top: box.top,
      bottom: box.bottom,
      viewportWidth: innerWidth,
      viewportHeight: innerHeight,
    };
  });
  expect(bounds.left).toBeGreaterThanOrEqual(0);
  expect(bounds.right).toBeLessThanOrEqual(bounds.viewportWidth);
  expect(bounds.top).toBeGreaterThanOrEqual(0);
  expect(bounds.bottom).toBeLessThanOrEqual(bounds.viewportHeight);
  await expect(navigation.getByRole('link', { name: current, exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  );
}
