import type { Page } from '@playwright/test';

// A failed assertion stays primary even when the browser also fails during resource cleanup.
export async function closeOwnedPage(
  page: Readonly<Pick<Page, 'isClosed' | 'close'>>,
  primaryFailed: boolean,
): Promise<Readonly<{ readonly error: unknown }> | null> {
  try {
    if (!page.isClosed()) await page.close();
    return null;
  } catch (error: unknown) {
    if (!primaryFailed) throw error;
    return { error };
  }
}
