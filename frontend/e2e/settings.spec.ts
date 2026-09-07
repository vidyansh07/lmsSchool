import { expect, test } from '@playwright/test';

import { signIn, signOut } from './helpers';

/**
 * The institution's own settings, against the real stack.
 *
 * This is the only layer that talks to a real URL resolver, so it is the only
 * place a mismatch between `lib/settings.ts` and `apps/configuration/urls.py`
 * can be caught — every unit test mocks the `lib/*` function, so a wrong path
 * passes all of them and 404s against a running server.
 *
 * The teardown restores the seeded name because the stack is shared and other
 * specs read institution strings.
 */
const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? '';
const ADMIN = 'admin@demo.grras.invalid';
const MANAGER = 'manager@demo.grras.invalid';
const STUDENT = 'student1@demo.grras.invalid';

test.skip(!DEMO_PASSWORD, 'E2E_DEMO_PASSWORD is not set; seeded-data tests are skipped.');

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

const SEEDED_NAME = 'Grras Solutions';
const SUPPORT_EMAIL = 'help@demo.grras.invalid';

// Serial: these tests read a setting the first of them writes, and the teardown
// puts it back.
test.describe.configure({ mode: 'serial' });

test.afterAll(async ({ browser }) => {
  const page = await browser.newPage();
  await signIn(page, ADMIN);
  await page.goto('/admin/settings');
  await page.getByLabel('Institution name').fill(SEEDED_NAME);
  await page.getByRole('button', { name: 'Save settings' }).click();
  await expect(page.getByRole('status')).toContainText(/saved/i);
  await page.close();
});

test('an administrator changes the name and support address and they survive a reload', async ({
  page,
}) => {
  await signIn(page, ADMIN);

  await page
    .getByRole('navigation', { name: 'Main' })
    .getByRole('link', { name: 'Settings', exact: true })
    .click();
  await expect(page.getByRole('heading', { name: 'Institution settings' })).toBeVisible();

  await page.getByLabel('Institution name').fill('Sunrise Academy');
  await page.getByLabel('Support email').fill(SUPPORT_EMAIL);
  await page.getByRole('button', { name: 'Save settings' }).click();
  await expect(page.getByRole('status')).toContainText(/saved/i);

  await page.reload();
  await expect(page.getByLabel('Institution name')).toHaveValue('Sunrise Academy');
  await expect(page.getByLabel('Support email')).toHaveValue(SUPPORT_EMAIL);

  await signOut(page);
});

test('the Settings entry is there for an administrator and absent for a manager', async ({
  page,
}) => {
  await signIn(page, ADMIN);
  await expect(
    page
      .getByRole('navigation', { name: 'Main' })
      .getByRole('link', { name: 'Settings', exact: true }),
  ).toBeVisible();
  await signOut(page);

  await signIn(page, MANAGER);
  await expect(
    page
      .getByRole('navigation', { name: 'Main' })
      .getByRole('link', { name: 'Settings', exact: true }),
  ).toHaveCount(0);
  await signOut(page);
});

test('a manager navigating straight to the settings screen is refused', async ({ page }) => {
  await signIn(page, MANAGER);
  await page.goto('/admin/settings');

  await expect(page.getByText(/do not have access to this page/i)).toBeVisible();
  await expect(page.getByLabel('Institution name')).toHaveCount(0);

  // And the server says the same thing, not merely the interface.
  const response = await page.request.get(`${API}/api/v1/settings/`);
  expect(response.status()).toBe(403);

  await signOut(page);
});

test('a student sees the configured support address on their own profile', async ({ page }) => {
  await signIn(page, STUDENT);
  await page.goto('/profile');

  await expect(page.getByRole('heading', { name: 'Need help?' })).toBeVisible();
  await expect(page.getByRole('link', { name: SUPPORT_EMAIL })).toBeVisible();

  await signOut(page);
});
