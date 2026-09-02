import { expect, test, type Page } from '@playwright/test';

/**
 * End-to-end tests against the real stack, using the seeded demo accounts.
 *
 * `E2E_DEMO_PASSWORD` must match the `DEMO_USER_PASSWORD` the stack was seeded
 * with. It is never hard-coded here.
 *
 * The stack under test must run with a raised `THROTTLE_RATE_AUTH`: these tests
 * sign in many times from one address in a few seconds, which the production
 * rate limit is specifically designed to stop. The limit itself is covered by
 * the backend test suite, so relaxing it here loses no coverage.
 */
const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? '';
const ADMIN = 'admin@demo.grras.invalid';
const STUDENT = 'student1@demo.grras.invalid';
const TRAINER = 'trainer1@demo.grras.invalid';

test.skip(!DEMO_PASSWORD, 'E2E_DEMO_PASSWORD is not set; seeded-account tests are skipped.');

async function signIn(page: Page, email: string) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: /^sign in$/i }).click();
  await expect(page.getByRole('heading', { name: /welcome back/i })).toBeVisible();
}

test.describe('Authentication', () => {
  test('a wrong password is refused without revealing whether the account exists', async ({
    page,
  }) => {
    await page.goto('/login');
    await page.getByLabel('Email').fill(ADMIN);
    await page.getByLabel('Password').fill('definitely-the-wrong-password');
    await page.getByRole('button', { name: /^sign in$/i }).click();

    // Next renders its own aria-live route announcer with role="alert", so the
    // assertion is scoped to the form's own error region.
    const alert = page.getByRole('alert').filter({ hasText: /could not sign in/i });
    await expect(alert).toContainText(/invalid credentials/i);
    await expect(alert).not.toContainText(/no such|not found|does not exist/i);
  });

  test('an administrator can sign in and reach people management', async ({ page }) => {
    await signIn(page, ADMIN);

    // The dashboard also links to these pages, so navigation links are scoped
    // to the main nav to keep the locator unambiguous.
    const nav = page.getByRole('navigation', { name: 'Main' });

    await nav.getByRole('link', { name: 'Users' }).click();
    await expect(page.getByRole('heading', { name: 'Users' })).toBeVisible();
    await expect(page.getByRole('table')).toBeVisible();

    await nav.getByRole('link', { name: 'Students' }).click();
    await expect(page.getByRole('heading', { name: 'Students' })).toBeVisible();
  });

  test('a student signs in and sees only their own areas', async ({ page }) => {
    await signIn(page, STUDENT);

    const nav = page.getByRole('navigation', { name: 'Main' });
    await expect(nav.getByRole('link', { name: 'My profile' })).toBeVisible();
    await expect(nav.getByRole('link', { name: 'Users' })).toHaveCount(0);
    await expect(nav.getByRole('link', { name: 'Students' })).toHaveCount(0);
  });

  test('a student navigating directly to an admin page is refused', async ({ page }) => {
    await signIn(page, STUDENT);
    await page.goto('/admin/users');
    // The interface refuses, and so would the API behind it.
    await expect(page.getByText(/do not have access/i)).toBeVisible();
  });

  test('a trainer can edit their own profile', async ({ page }) => {
    await signIn(page, TRAINER);
    await page.goto('/profile');
    await expect(page.getByRole('heading', { name: 'Trainer profile' })).toBeVisible();

    const bio = page.getByLabel('Biography');
    await bio.fill('Updated by an end-to-end test.');
    await page.getByRole('button', { name: /save profile/i }).click();
    await expect(page.getByText(/your profile was saved/i)).toBeVisible();
  });

  test('signing out ends the session', async ({ page }) => {
    await signIn(page, STUDENT);
    await page.getByRole('button', { name: /sign out/i }).click();
    await expect(page.getByRole('link', { name: /sign in/i }).first()).toBeVisible();

    await page.goto('/profile');
    await expect(page).toHaveURL(/\/login/);
  });

  test('the password reset request never reveals whether an address exists', async ({ page }) => {
    await page.goto('/forgot-password');
    await page.getByLabel('Email').fill('definitely-not-a-user@demo.grras.invalid');
    await page.getByRole('button', { name: /send reset link/i }).click();
    await expect(page.getByText(/if an account exists for that address/i)).toBeVisible();
  });
});
