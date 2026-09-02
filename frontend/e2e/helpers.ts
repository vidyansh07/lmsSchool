import { expect, type Page, type Response } from '@playwright/test';

/**
 * Signing in and out, in one place.
 *
 * Two things this gets right that nine hand-written copies did not.
 *
 * **It waits for the session, not the greeting.** Every copy waited for
 * "Welcome back". That works against the development server and fails against a
 * production build: the landing page renders on the server and only swaps to
 * its signed-in form once the browser has fetched the current user, so the
 * greeting arrives a beat after the session does. Twenty-four tests failed on
 * staging for that reason and none failed locally — the most expensive kind of
 * difference between environments. The Sign out control in the banner appears
 * exactly when there is a session.
 *
 * **It waits out the rate limit.** The suite signs in about fifty times from
 * one address, which is the shape of traffic the credential throttle exists to
 * refuse. Raising the limit for the tests would make credential stuffing
 * cheaper in the environment built to behave like production, so the tests wait
 * instead — the way a person would.
 */
export const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? '';

/** How long to wait for the session before deciding the sign-in failed. */
const SESSION_TIMEOUT = 15_000;

export async function signIn(page: Page, email: string, password = DEMO_PASSWORD) {
  for (let attempt = 0; attempt < 4; attempt += 1) {
    let throttledFor = 0;
    const failures: string[] = [];

    const listener = async (response: Response) => {
      if (!response.url().includes('/api/') || response.status() < 400) return;
      failures.push(`${response.status()} ${response.url()}`);
      if (response.status() === 429) {
        const body = await response.json().catch(() => null);
        throttledFor = Number(body?.error?.details?.retry_after_seconds ?? 60) + 2;
      }
    };
    page.on('response', listener);

    await page.goto('/login');
    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Password').fill(password);
    await page.getByRole('button', { name: /^sign in$/i }).click();

    const signedIn = await page
      .getByRole('banner')
      .getByRole('button', { name: /sign out/i })
      .waitFor({ state: 'visible', timeout: SESSION_TIMEOUT })
      .then(() => true)
      .catch(() => false);
    page.off('response', listener);

    if (signedIn) return;
    if (!throttledFor) {
      throw new Error(
        `Signing in as ${email} did not establish a session. API failures: ${JSON.stringify(failures)}`,
      );
    }
    await page.waitForTimeout(Math.min(throttledFor, 90) * 1000);
  }
  throw new Error(`Signing in as ${email} stayed rate limited.`);
}

export async function signOut(page: Page) {
  await page.getByRole('banner').getByRole('button', { name: /sign out/i }).click();
  // Scoped to the header: a signed-out page may also offer a Sign in link in
  // its body, and either one appearing means the sign-out landed.
  await expect(page.getByRole('banner').getByRole('link', { name: /sign in/i })).toBeVisible();
}
