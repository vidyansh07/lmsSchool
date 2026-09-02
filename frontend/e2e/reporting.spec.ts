import { expect, test } from '@playwright/test';

import { signIn } from './helpers';

/**
 * Reports, analytics and data tools — §8.7, end to end.
 *
 * The journeys that matter: a report is scoped to who is asking, an export is
 * the same rows, and a bulk import shows you what it would do before it does it.
 */
const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? '';
const ADMIN = 'admin@demo.grras.invalid';
const STUDENT = 'student1@demo.grras.invalid';
const TRAINER = 'trainer1@demo.grras.invalid';

test.skip(!DEMO_PASSWORD, 'E2E_DEMO_PASSWORD is not set; seeded-data tests are skipped.');


test.describe('Dashboards and analytics', () => {
  test('an admin sees the overview, and every metric states what it means', async ({ page }) => {
    await signIn(page, ADMIN);
    await page
      .getByRole('navigation', { name: 'Main' })
      .getByRole('link', { name: 'Overview', exact: true })
      .click();

    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
    await expect(page.getByTestId('headline-figure').first()).toBeVisible();

    // §8.6: every metric must have a documented definition, and it is shown.
    const metrics = page.getByTestId('metric');
    const count = await metrics.count();
    expect(count).toBeGreaterThan(0);
    for (let index = 0; index < count; index += 1) {
      await expect(metrics.nth(index).getByTestId('metric-definition')).not.toBeEmpty();
    }
  });

  test('a student cannot reach the overview or reports', async ({ page }) => {
    await signIn(page, STUDENT);
    const nav = page.getByRole('navigation', { name: 'Main' });
    await expect(nav.getByRole('link', { name: 'Overview' })).toHaveCount(0);
    await expect(nav.getByRole('link', { name: 'Reports' })).toHaveCount(0);
  });
});

test.describe('Journey: run and export a report', () => {
  test('an admin runs a report and can export the same rows', async ({ page }) => {
    await signIn(page, ADMIN);
    await page.goto('/admin/reports');
    await expect(page.getByRole('heading', { name: 'Reports' })).toBeVisible();

    await page.getByRole('combobox', { name: 'Report' }).selectOption('attendance');
    await page.getByRole('button', { name: 'Run the report' }).click();

    const body = page.getByTestId('report-body');
    await expect(body).toBeVisible();
    await expect(body.locator('tr').first()).toBeVisible();

    // The export is a link to the same report, and it is offered because this
    // account may export.
    // The button renders as the anchor itself, so the test id is the link.
    const link = page.getByTestId('export-link');
    await expect(link).toBeVisible();
    const href = await link.getAttribute('href');
    expect(href).toContain('/reports/attendance/export/');

    const download = await page.request.get(href as string);
    expect(download.status()).toBe(200);
    expect(download.headers()['content-type']).toContain('text/csv');
    const csv = await download.text();
    expect(csv.split('\n')[0]).toContain('Student');
  });

  test('a trainer may read a report but not export it', async ({ page }) => {
    await signIn(page, TRAINER);
    await page.goto('/admin/reports');
    await expect(page.getByRole('heading', { name: 'Reports' })).toBeVisible();

    await page.getByRole('combobox', { name: 'Report' }).selectOption('attendance');
    await page.getByRole('button', { name: 'Run the report' }).click();
    await expect(page.getByTestId('report-body')).toBeVisible();

    // Reading a page and walking out with the institution are different acts.
    await expect(page.getByTestId('export-link')).toHaveCount(0);
  });
});

test.describe('Journey: bulk import students', () => {
  test('preview shows what would happen, and confirming creates the accounts', async ({
    page,
  }) => {
    const stamp = Date.now();
    await signIn(page, ADMIN);
    await page.goto('/admin/imports');
    await expect(page.getByRole('heading', { name: 'Bulk import' })).toBeVisible();

    await page.getByLabel('File').setInputFiles({
      name: 'new-students.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(
        `email,first name,last name\ne2e.${stamp}a@example.test,Asha,Rao\n` +
          `e2e.${stamp}b@example.test,Bilal,Khan\n`,
      ),
    });
    await page.getByRole('button', { name: 'Preview the import' }).click();

    const preview = page.getByTestId('import-preview');
    await expect(preview).toBeVisible();
    await expect(preview).toContainText('2 of 2 rows would apply');
    await expect(preview).toContainText('0 with problems');

    await preview.getByRole('button', { name: 'Confirm the import' }).click();
    await expect(page.getByRole('status')).toContainText(/imported/i);
    await expect(preview).toContainText('2 created');
  });

  test('a file with a bad row is reported and cannot be confirmed', async ({ page }) => {
    await signIn(page, ADMIN);
    await page.goto('/admin/imports');

    await page.getByLabel('File').setInputFiles({
      name: 'broken.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('email,first name\nnot-an-email,Asha\n'),
    });
    await page.getByRole('button', { name: 'Preview the import' }).click();

    const preview = page.getByTestId('import-preview');
    await expect(preview).toContainText(/valid email/i);
    // Nothing usable in the file, so there is nothing to confirm — the screen
    // says so rather than offering a button that would refuse.
    await expect(preview).toContainText(/nothing in this file can be imported/i);
    await expect(preview.getByRole('button', { name: 'Confirm the import' })).toHaveCount(0);
  });

  test('a trainer cannot reach bulk import', async ({ page }) => {
    await signIn(page, TRAINER);
    await expect(
      page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Bulk import' }),
    ).toHaveCount(0);
  });
});
