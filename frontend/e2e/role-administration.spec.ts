import { expect, test } from '@playwright/test';

import { DEMO_PASSWORD, signIn, signOut } from './helpers';

/**
 * §11.1–11.3 in a browser.
 *
 * The point of these is the pair of questions the API tests cannot answer: can
 * a superadmin actually reach and change an administrator's data from a screen,
 * and is an administrator actually stopped from reaching upward — not merely
 * refused by an endpoint they could still call by hand.
 */
const SUPERADMIN = 'superadmin@demo.grras.invalid';
const ADMIN = 'admin@demo.grras.invalid';
const MANAGER = 'manager@demo.grras.invalid';
const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

test.skip(!DEMO_PASSWORD, 'E2E_DEMO_PASSWORD is not set; seeded-data tests are skipped.');

/** Find a seeded account's id without guessing at list ordering. */
async function findUser(page: import('@playwright/test').Page, email: string): Promise<string> {
  const response = await page.request.get(
    `${API}/api/v1/users/?search=${encodeURIComponent(email)}`,
  );
  expect(response.ok(), `could not look up ${email}`).toBeTruthy();
  const rows = (await response.json()).results as { id: string; email: string }[];
  const match = rows.find((row) => row.email === email);
  expect(match, `no seeded account for ${email}`).toBeTruthy();
  return (match as { id: string }).id;
}

test.describe('A superadmin administers an administrator', () => {
  test('every field of an administrator can be configured from the screen', async ({ page }) => {
    await signIn(page, SUPERADMIN);

    const adminId = await findUser(page, ADMIN);
    await page.goto(`/admin/users/${adminId}`);
    await expect(page.getByRole('heading', { name: /adminson|admin/i }).first()).toBeVisible();

    // The fields exist at all — which they did not before this phase, when the
    // screen could only activate and deactivate.
    const stamp = String(Date.now()).slice(-6);
    await page.getByLabel('First name').fill(`Ada${stamp}`);
    await page.getByLabel('Phone').fill('+911234500000');
    await page.getByRole('button', { name: 'Save changes' }).click();
    await expect(page.getByRole('status').filter({ hasText: /saved/i })).toBeVisible();

    await page.reload();
    await expect(page.getByLabel('First name')).toHaveValue(`Ada${stamp}`);
    await expect(page.getByLabel('Phone')).toHaveValue('+911234500000');

    // Put the name back, so the demo roster reads as it did.
    await page.getByLabel('First name').fill('Ada');
    await page.getByRole('button', { name: 'Save changes' }).click();
    await expect(page.getByRole('status').filter({ hasText: /saved/i })).toBeVisible();

    await signOut(page);
  });

  test('the account history is on the same screen as the fields', async ({ page }) => {
    await signIn(page, SUPERADMIN);
    const adminId = await findUser(page, ADMIN);
    await page.goto(`/admin/users/${adminId}`);

    await expect(page.getByRole('heading', { name: 'History' })).toBeVisible();
    await expect(page.getByTestId('audit-entry').first()).toBeVisible();
    await signOut(page);
  });

  test('a reset link can be sent, and no password is ever shown', async ({ page }) => {
    await signIn(page, SUPERADMIN);
    const managerId = await findUser(page, MANAGER);
    await page.goto(`/admin/users/${managerId}`);

    await page.getByRole('button', { name: 'Send a password-reset link' }).click();
    await expect(page.getByRole('status').filter({ hasText: /link has been sent/i })).toBeVisible();

    // Nothing on the page reveals a credential — the link went to their inbox.
    const body = await page.locator('main').innerText();
    expect(body).not.toMatch(/token=/i);
    await signOut(page);
  });
});

test.describe('Authority does not flow upward', () => {
  test('an administrator cannot open a superadmin to administer them', async ({ page }) => {
    await signIn(page, ADMIN);
    const superadminId = await findUser(page, SUPERADMIN);

    await page.goto(`/admin/users/${superadminId}`);

    // The screen loads and says why it can do nothing, rather than showing a
    // form whose Save button fails. Viewing is a wider permission than
    // administering, and the difference has to be visible.
    await expect(page.getByText(/see this account but not change it/i)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Save changes' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /password-reset link/i })).toHaveCount(0);
    await expect(page.getByLabel('First name')).toBeDisabled();
    await signOut(page);
  });

  test('the API refuses it too, not only the screen', async ({ page }) => {
    await signIn(page, ADMIN);
    const superadminId = await findUser(page, SUPERADMIN);

    await page.request.get(`${API}/api/v1/auth/csrf/`);
    const csrf =
      (await page.context().cookies()).find((cookie) => cookie.name === 'grras_csrftoken')?.value ??
      '';
    const response = await page.request.patch(`${API}/api/v1/users/${superadminId}/`, {
      data: { first_name: 'Taken' },
      headers: { 'X-CSRFToken': csrf, Referer: `${API}/` },
      failOnStatusCode: false,
    });

    expect(response.status()).toBe(403);
    await signOut(page);
  });

  test('a manager cannot administer an administrator', async ({ page }) => {
    await signIn(page, MANAGER);
    const adminId = await findUser(page, ADMIN);

    await page.goto(`/admin/users/${adminId}`);
    await expect(page.getByRole('button', { name: 'Save changes' })).toHaveCount(0);
    await signOut(page);
  });
});
