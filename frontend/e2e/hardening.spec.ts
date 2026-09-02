import { expect, test } from '@playwright/test';

import { signIn } from './helpers';

/**
 * Phase 9 (§14.4) in the browser.
 *
 * Everything here is asserted against the running stack rather than against
 * settings, because a header a middleware sets and a proxy strips is a header
 * the user does not have. The backend tests prove the configuration is right;
 * these prove it survives the trip.
 */
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? '';
const STUDENT = 'student1@demo.grras.invalid';


test.describe('Security headers', () => {
  test('the API sends the headers that constrain a browser', async ({ request }) => {
    const response = await request.get(`${apiBaseUrl}/health/live/`);
    const headers = response.headers();

    expect(headers['x-content-type-options']).toBe('nosniff');
    expect(headers['x-frame-options']).toBe('DENY');
    expect(headers['referrer-policy']).toBe('strict-origin-when-cross-origin');
    expect(headers['content-security-policy']).toContain("frame-ancestors 'none'");
    expect(headers['permissions-policy']).toBeTruthy();
  });

  test('every response carries a request id for correlation', async ({ request }) => {
    const response = await request.get(`${apiBaseUrl}/health/live/`);
    expect(response.headers()['x-request-id']).toMatch(/^[0-9a-f]{8,}$/);
  });

  test('an error body never carries internals', async ({ request }) => {
    const response = await request.get(`${apiBaseUrl}/api/v1/students/`);
    const body = JSON.stringify(await response.json());

    for (const leak of ['Traceback', 'SELECT ', '/app/', 'site-packages', 'psycopg']) {
      expect(body).not.toContain(leak);
    }
  });
});

test.describe('Cookies and authorization', () => {
  test.skip(!DEMO_PASSWORD, 'E2E_DEMO_PASSWORD is not set; seeded-data tests are skipped.');

  test('the session cookie is not readable from script', async ({ page, context }) => {
    await signIn(page, STUDENT);

    const cookies = await context.cookies();
    const session = cookies.find((cookie) => cookie.name === 'grras_sessionid');
    expect(session, 'no session cookie was set').toBeTruthy();
    expect(session?.httpOnly).toBe(true);

    // The CSRF cookie is deliberately readable — the SPA has to echo it back in
    // a header — which is exactly why it must not be what authenticates anyone.
    const csrf = cookies.find((cookie) => cookie.name === 'grras_csrftoken');
    expect(csrf?.httpOnly).toBe(false);
  });

  test('a student who types an admin URL gets nothing back', async ({ page }) => {
    await signIn(page, STUDENT);

    // Hiding a navigation link is presentation. This is the thing behind it:
    // the page loads, asks the API, and the API refuses.
    for (const path of ['/admin/overview', '/admin/reports', '/admin/imports']) {
      await page.goto(path);
      await expect(page.getByTestId('report-body')).toHaveCount(0);
      await expect(page.getByTestId('headline-figure')).toHaveCount(0);
    }
  });
});
