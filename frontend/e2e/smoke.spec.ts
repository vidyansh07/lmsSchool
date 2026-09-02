import { expect, test } from '@playwright/test';

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

test.describe('Foundation smoke', () => {
  test('the frontend renders the application shell', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible();
    await expect(page.getByRole('link', { name: /sign in/i }).first()).toBeVisible();
  });

  test('unknown routes render the 404 page', async ({ page }) => {
    const response = await page.goto('/no-such-page');
    expect(response?.status()).toBe(404);
    await expect(page.getByRole('heading', { name: /page not found/i })).toBeVisible();
  });

  test('the backend health endpoint is reachable', async ({ request }) => {
    const response = await request.get(`${apiBaseUrl}/health/ready/`);
    expect(response.status()).toBe(200);
    expect((await response.json()).status).toBe('ok');
  });

  test('the frontend reads live status from the backend', async ({ page }) => {
    await page.goto('/status');
    // The panel fetches readiness from the browser, and readiness touches the
    // database and the cache. On a dev server compiling the route under a full
    // suite that can outlast the default expect window; the assertion is the
    // same, it is just allowed to take longer.
    await expect(page.getByText('Operational')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText('database', { exact: false })).toBeVisible();
  });

  test('protected endpoints refuse anonymous callers', async ({ request }) => {
    for (const path of ['/api/v1/users/', '/api/v1/students/', '/api/v1/trainers/']) {
      const response = await request.get(`${apiBaseUrl}${path}`);
      expect([401, 403]).toContain(response.status());
      const body = await response.json();
      expect(body.error.code).toBeTruthy();
      expect(JSON.stringify(body)).not.toContain('Traceback');
    }
  });
});
