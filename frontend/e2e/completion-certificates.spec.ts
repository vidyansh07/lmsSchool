import { expect, test, type Page } from '@playwright/test';

import { signIn, signOut } from './helpers';

/**
 * Completion and certificates — §6.6 to §6.9, end to end.
 *
 * The journey the spec describes:
 *   activities complete → rules evaluated → student becomes eligible → admin
 *   reviews → approves → completion recorded → certificate issued → the student
 *   downloads it → anyone verifies it publicly.
 *
 * Requires the full seed chain and `E2E_DEMO_PASSWORD`.
 */
const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? '';
const ADMIN = 'admin@demo.grras.invalid';
const STUDENT = 'student1@demo.grras.invalid';
const TRAINER = 'trainer1@demo.grras.invalid';

test.skip(!DEMO_PASSWORD, 'E2E_DEMO_PASSWORD is not set; seeded-data tests are skipped.');



const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

/** The seeded student's live batch, and their name as the queue shows it. */
async function studentIdentity(page: Page): Promise<{ batchCode: string; name: string }> {
  await signIn(page, STUDENT);

  const enrolments = await page.request.get(`${API}/api/v1/enrollments/mine/`);
  expect(enrolments.ok()).toBeTruthy();
  const rows = (await enrolments.json()) as { batch_code: string; grants_access: boolean }[];
  const live = rows.find((row) => row.grants_access);
  expect(live, 'the seeded student needs one enrolment that opens its course').toBeTruthy();

  const me = await page.request.get(`${API}/api/v1/auth/me/`);
  expect(me.ok()).toBeTruthy();
  const profile = (await me.json()) as { full_name: string };

  await signOut(page);
  return { batchCode: (live as { batch_code: string }).batch_code, name: profile.full_name };
}

test.describe('Progress', () => {
  test('a student sees one progress figure and what is still required', async ({ page }) => {
    await signIn(page, STUDENT);
    await page
      .getByRole('navigation', { name: 'Main' })
      .getByRole('link', { name: 'My progress', exact: true })
      .click();

    await expect(page.getByRole('heading', { name: 'My progress' })).toBeVisible();
    const card = page.getByTestId('progress-card').first();
    await expect(card).toBeVisible();

    // Every condition is listed, met or not, required or not.
    await expect(card.getByTestId('completion-rules')).toBeVisible();
    await expect(card.getByTestId('rule-attendance')).toBeVisible();
    await expect(card.getByTestId('rule-final_exam')).toBeVisible();
  });

  test('a trainer cannot reach the completion queue', async ({ page }) => {
    await signIn(page, TRAINER);
    await expect(
      page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Completions' }),
    ).toHaveCount(0);
  });
});

test.describe('Journey: approve, issue, verify', () => {
  test('an admin approves a completion, issues the certificate, and it verifies', async ({
    page,
  }) => {
    const { batchCode, name: studentName } = await studentIdentity(page);

    await signIn(page, ADMIN);
    await page.goto('/admin/completions');
    await expect(page.getByRole('heading', { name: 'Course completions' })).toBeVisible();

    // Work on this student's batch, and look at every status: an earlier run of
    // this suite may have left them approved, and the journey has to start from
    // the same place every time.
    const batchOption = page
      .getByRole('combobox', { name: 'Batch' })
      .locator('option', { hasText: batchCode })
      .first();
    await page
      .getByRole('combobox', { name: 'Batch' })
      .selectOption(await batchOption.getAttribute('value'));
    await page.getByRole('combobox', { name: 'Status' }).selectOption('');

    await page.getByRole('button', { name: 'Re-evaluate this batch' }).click();
    await expect(page.getByRole('status')).toContainText(/re-evaluated/i);

    const row = page.getByTestId('completion-row').filter({ hasText: studentName }).first();
    await expect(row).toBeVisible();

    // If a previous run left them approved, undo it — revoking the certificate
    // first, which is what the backend requires.
    const reopen = row.getByRole('button', { name: 'Reopen' });
    if (await reopen.count()) {
      await page.goto('/admin/certificates');
      const live = page
        .getByTestId('certificate-row')
        .filter({ hasText: studentName })
        .filter({ has: page.getByRole('button', { name: 'Revoke' }) })
        .first();
      if (await live.count()) {
        await live.getByLabel('Reason').fill('Resetting the end-to-end journey.');
        await live.getByRole('button', { name: 'Revoke' }).click();
        await expect(page.getByRole('status')).toContainText(/revoked/i);
      }

      await page.goto('/admin/completions');
      await page
        .getByRole('combobox', { name: 'Batch' })
        .selectOption(await batchOption.getAttribute('value'));
      await page.getByRole('combobox', { name: 'Status' }).selectOption('');
      const decided = page.getByTestId('completion-row').filter({ hasText: studentName }).first();
      await decided.getByLabel('Note').fill('Resetting the end-to-end journey.');
      await decided.getByRole('button', { name: 'Reopen' }).click();
      await expect(page.getByRole('status')).toContainText(/reopened/i);
    }

    const eligible = page.getByTestId('completion-row').filter({ hasText: studentName }).first();
    await expect(eligible).toBeVisible();
    await eligible.getByRole('button', { name: 'Show the rules' }).click();
    await expect(eligible.getByTestId('completion-rules')).toBeVisible();

    await eligible.getByLabel('Note').fill('Checked against the register.');
    await eligible.getByRole('button', { name: 'Approve' }).click();
    await expect(page.getByRole('status')).toContainText(/approved/i);

    // Approved, so the certificate can be issued.
    await page.getByRole('combobox', { name: 'Status' }).selectOption('approved');
    const approved = page.getByTestId('completion-row').filter({ hasText: studentName }).first();
    await expect(approved).toBeVisible();
    await approved.getByRole('button', { name: 'Issue the certificate' }).click();
    await expect(page.getByRole('status')).toContainText(/certificate issued/i);

    // The certificate exists, with a number and a downloadable PDF.
    await page.goto('/admin/certificates');
    const certificate = page.getByTestId('certificate-row').first();
    await expect(certificate).toBeVisible();
    await expect(certificate).toContainText('GRS-CERT-');

    await signOut(page);

    // The student can download it, and reach its public verification page.
    await signIn(page, STUDENT);
    await page.goto('/my-progress');
    const download = page.getByTestId('certificate-download').first();
    await expect(download).toBeVisible();

    const link = page.getByRole('link', { name: 'this address' }).first();
    await link.click();

    await expect(page.getByTestId('verification-verdict')).toContainText(/valid certificate/i);
    await expect(page.getByTestId('verified-student')).toBeVisible();
    await expect(page.getByTestId('verified-course')).toBeVisible();

    await signOut(page);

    // --- Put it back. Revoking and reopening are §6.7 features in their own
    // right, and doing them here is what keeps this journey runnable twice.
    await signIn(page, ADMIN);
    await page.goto('/admin/certificates');
    const certificateRow = page.getByTestId('certificate-row').first();
    await certificateRow.getByLabel('Reason').fill('End of the end-to-end journey.');
    await certificateRow.getByRole('button', { name: 'Revoke' }).click();
    await expect(page.getByRole('status')).toContainText(/revoked/i);

    // A revoked certificate still verifies, and says so.
    await expect(certificateRow).toContainText('Revoked');

    await page.goto('/admin/completions');
    await page.getByRole('combobox', { name: 'Status' }).selectOption('approved');
    const decided = page.getByTestId('completion-row').filter({ hasText: studentName }).first();
    await expect(decided).toBeVisible();

    // Reopen it, so the next run of this suite finds an eligible student again.
    // The certificate was revoked above, which is what the backend requires
    // before a completion can be reopened.
    await decided.getByLabel('Note').fill('End of the end-to-end journey.');
    await decided.getByRole('button', { name: 'Reopen' }).click();
    await expect(page.getByRole('status')).toContainText(/reopened/i);
  });

  test('verification is public and leaks nothing private', async ({ page, context }) => {
    // Find a verification code as the student, then check it signed out.
    await signIn(page, STUDENT);
    await page.goto('/my-progress');
    const link = page.getByRole('link', { name: 'this address' }).first();
    const href = await link.getAttribute('href');
    expect(href).toMatch(/^\/verify\//);

    await context.clearCookies();

    await page.goto(href as string);
    await expect(page.getByTestId('verification-verdict')).toBeVisible();

    // Nothing about the student beyond their name and the course reaches the page.
    const body = await page.locator('main').innerText();
    expect(body).not.toContain('@demo.grras.invalid');
    expect(body).not.toContain('GRS-S-');
    expect(body).not.toContain('GRS-B-');
  });

  test('an unknown code says so without hinting at anything', async ({ page }) => {
    await page.goto('/verify/definitely-not-a-real-code');
    await expect(page.getByText(/no certificate found/i)).toBeVisible();
    // The same answer for a typo and for a code that was never issued.
    await expect(page.locator('main')).not.toContainText(/revoked|superseded/i);
  });
});
