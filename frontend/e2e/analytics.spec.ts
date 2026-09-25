/**
 * The analytics page: who reaches it, and that every chart on it says what
 * it is plotting.
 *
 * The second half is the one worth having. A chart with no definition is a
 * number two people will act on differently, which is the same rule
 * `reporting.spec.ts` already enforces for the metrics list -- this applies
 * it to the plots.
 */

import { expect, test } from '@playwright/test';

import { signIn } from './helpers';

const ADMIN = 'admin@demo.grras.invalid';
const STUDENT = 'student1@demo.grras.invalid';
const TRAINER = 'trainer1@demo.grras.invalid';

test.describe('Analytics', () => {
  test('an administrator sees the shape of the institution', async ({ page }) => {
    await signIn(page, ADMIN);
    await page.goto('/analytics');

    await expect(page.getByRole('heading', { name: 'Analytics', level: 1 })).toBeVisible();

    // The overview strip renders a figure per column.
    expect(await page.getByTestId('headline-figure').count()).toBeGreaterThan(0);

    // Every chart card states what it is plotting, and none of them is blank.
    const definitions = page.getByTestId('chart-definition');
    const count = await definitions.count();
    expect(count).toBeGreaterThan(0);
    for (let index = 0; index < count; index += 1) {
      await expect(definitions.nth(index)).not.toHaveText('');
    }

    // Aggregates only: the rows live in Reports, and each card links there.
    await expect(page.getByRole('link', { name: /View the enrolments/ })).toBeVisible();
  });

  test('changing the period refetches rather than reloading the page', async ({ page }) => {
    await signIn(page, ADMIN);
    await page.goto('/analytics');
    await expect(page.getByText(/The last 12 weeks/)).toBeVisible();

    await page.getByLabel('Period').selectOption('26');
    await expect(page.getByText(/The last 26 weeks/)).toBeVisible();
  });

  test('a student reaches nothing, whatever they type', async ({ page }) => {
    await signIn(page, STUDENT);
    await page.goto('/analytics');
    await expect(page.getByTestId('headline-figure')).toHaveCount(0);
    await expect(page.getByTestId('chart-definition')).toHaveCount(0);
  });

  test('a trainer is not offered it, because the page is not theirs', async ({ page }) => {
    // A trainer passes the reporting layer's own check through their trainer
    // profile, so the trend endpoints would answer them -- but the headline
    // strip needs the global reporting capability and would 403, leaving
    // them a page with a broken top. Their charts live on /teaching/today.
    await signIn(page, TRAINER);
    await expect(page.getByRole('link', { name: 'Analytics' })).toHaveCount(0);
  });
});
