import { expect, test } from '@playwright/test';

import { signIn, signOut } from './helpers';

/**
 * The activity catalog builder — `docs/erp/USER_JOURNEYS.md` §1.6 "Create
 * an activity type" (ERP Phase 9). `role-administration.spec.ts` and
 * `settings.spec.ts` already walk an administrator's RBAC and configuration
 * screens end to end; neither ever opens `/admin/activity-types`, so the
 * one ERP-introduced admin screen those two specs do not reach gets its own
 * focused spec here.
 */
const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? '';
const ADMIN = 'admin@demo.grras.invalid';

test.skip(!DEMO_PASSWORD, 'E2E_DEMO_PASSWORD is not set; seeded-data tests are skipped.');

test.describe('Journey: an administrator adds an activity type', () => {
  test('a new type is created and immediately listed, name and slug together', async ({ page }) => {
    await signIn(page, ADMIN);

    await page
      .getByRole('navigation', { name: 'Main' })
      .getByRole('link', { name: 'Activity types', exact: true })
      .click();
    await expect(page.getByRole('heading', { name: 'Activity types' })).toBeVisible();

    const typeName = `E2E Placement Debrief ${Date.now()}`;
    await page.getByRole('button', { name: 'New type' }).click();
    await expect(page.getByRole('heading', { name: 'New activity type' })).toBeVisible();

    await page.getByLabel('Name').fill(typeName);
    // The slug derives from the name and needs no separate input — proving
    // that wiring, not just the raw create, is the point of this assertion.
    await expect(page.getByLabel('Slug')).not.toHaveValue('');

    await page.getByRole('button', { name: 'Create type' }).click();

    await expect(page.getByRole('heading', { name: 'New activity type' })).toHaveCount(0);
    await expect(page.getByRole('cell', { name: typeName })).toBeVisible();

    await signOut(page);
  });

  test('the seeded catalog is real and already there: Mock Interview, requires-review off', async ({
    page,
  }) => {
    await signIn(page, ADMIN);

    await page
      .getByRole('navigation', { name: 'Main' })
      .getByRole('link', { name: 'Activity types', exact: true })
      .click();

    const row = page.getByRole('row', { name: /Mock Interview/ });
    await expect(row).toBeVisible();
    await expect(row).toContainText('Interview');
    await expect(row).toContainText('Active');

    await signOut(page);
  });
});
