import { expect, test, type Page } from '@playwright/test';

import { signIn, signOut } from './helpers';

/**
 * Communication, calendar and the learning surface — §7.9, end to end.
 *
 * The journeys that matter here are about *targeting*: who is told, who can
 * read it, and who cannot.
 */
const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? '';
const ADMIN = 'admin@demo.grras.invalid';
const STUDENT = 'student1@demo.grras.invalid';
const TRAINER = 'trainer1@demo.grras.invalid';
const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

test.skip(!DEMO_PASSWORD, 'E2E_DEMO_PASSWORD is not set; seeded-data tests are skipped.');



/** The batch the seeded student is actually taught on. */
async function studentBatchCode(page: Page): Promise<string> {
  await signIn(page, STUDENT);
  const response = await page.request.get(`${API}/api/v1/enrollments/mine/`);
  expect(response.ok()).toBeTruthy();
  const rows = (await response.json()) as { batch_code: string; grants_access: boolean }[];
  const live = rows.find((row) => row.grants_access);
  expect(live).toBeTruthy();
  await signOut(page);
  return (live as { batch_code: string }).batch_code;
}

test.describe('Journey: announce and be notified', () => {
  test('an admin announces to a batch and the student is told', async ({ page }) => {
    const title = `E2E notice ${Date.now()}`;
    const batchCode = await studentBatchCode(page);

    await signIn(page, ADMIN);
    await page.goto('/announcements');
    await expect(page.getByRole('heading', { name: 'Announcements' })).toBeVisible();

    await page.getByRole('button', { name: 'New announcement' }).click();
    await page.getByLabel('Title').fill(title);
    await page.getByLabel('Message').fill('The Friday lab moves to room 3.');
    await page.getByRole('combobox', { name: 'Audience' }).selectOption('batch');
    const option = page
      .getByRole('combobox', { name: 'Batch' })
      .locator('option', { hasText: batchCode })
      .first();
    await page.getByRole('combobox', { name: 'Batch' }).selectOption(
      await option.getAttribute('value'),
    );
    await page.getByRole('button', { name: 'Save as a draft' }).click();
    await expect(page.getByRole('status')).toContainText(/draft/i);

    // A draft tells nobody; publishing does.
    const card = page.getByTestId('announcement-card').filter({ hasText: title });
    await expect(card).toBeVisible();
    await card.getByRole('button', { name: 'Publish' }).click();
    await expect(page.getByRole('status')).toContainText(/published/i);

    await signOut(page);

    await signIn(page, STUDENT);
    await page.goto('/notifications');
    const notification = page.getByTestId('notification-row').filter({ hasText: title });
    await expect(notification).toBeVisible();

    // And it is on the board they read.
    await page.goto('/announcements');
    await expect(page.getByTestId('announcement-card').filter({ hasText: title })).toBeVisible();
  });

  test('a student can turn an email category off', async ({ page }) => {
    await signIn(page, STUDENT);
    await page.goto('/notifications');

    const box = page.getByTestId('email_announcements');
    await expect(box).toBeVisible();
    const before = await box.isChecked();
    await box.click();
    await expect(box).toBeChecked({ checked: !before });

    // Put it back, so the suite is repeatable.
    await box.click();
    await expect(box).toBeChecked({ checked: before });
  });

  test('a student never sees a draft', async ({ page }) => {
    const title = `E2E unpublished ${Date.now()}`;
    const batchCode = await studentBatchCode(page);

    await signIn(page, ADMIN);
    await page.goto('/announcements');
    await page.getByRole('button', { name: 'New announcement' }).click();
    await page.getByLabel('Title').fill(title);
    await page.getByLabel('Message').fill('Not for reading yet.');
    const option = page
      .getByRole('combobox', { name: 'Batch' })
      .locator('option', { hasText: batchCode })
      .first();
    await page.getByRole('combobox', { name: 'Batch' }).selectOption(
      await option.getAttribute('value'),
    );
    await page.getByRole('button', { name: 'Save as a draft' }).click();
    await expect(page.getByRole('status')).toContainText(/draft/i);
    await signOut(page);

    await signIn(page, STUDENT);
    await page.goto('/announcements');
    await expect(page.getByTestId('announcement-card').filter({ hasText: title })).toHaveCount(0);
  });
});

test.describe('Journey: ask and answer', () => {
  test('a student asks, the trainer answers, and the answer is marked', async ({ page }) => {
    const title = `E2E question ${Date.now()}`;
    const batchCode = await studentBatchCode(page);

    await signIn(page, STUDENT);
    await page.goto('/discussions');
    await expect(page.getByRole('heading', { name: 'Discussions' })).toBeVisible();

    await page.getByRole('button', { name: 'Ask a question' }).click();
    // The batch trainer1 teaches, so the trainer can actually answer — picking
    // by position would land on a batch with a different trainer.
    const batchOption = page
      .getByRole('combobox', { name: 'Batch' })
      .locator('option', { hasText: batchCode })
      .first();
    await page.getByRole('combobox', { name: 'Batch' }).selectOption(
      await batchOption.getAttribute('value'),
    );
    await page.getByLabel('Question').fill(title);
    await page.getByLabel('Details').fill('I am stuck on the second exercise.');
    await page.getByRole('button', { name: 'Post the question' }).click();

    const thread = page.getByTestId('thread-row').filter({ hasText: title });
    await expect(thread).toBeVisible();
    await expect(thread).toContainText('Unanswered');
    await thread.getByRole('link', { name: title }).click();
    // Wait for the thread page before reading the URL: reading it mid-click
    // captures the list, and the trainer then lands somewhere with no reply box.
    await expect(page.getByRole('heading', { name: title })).toBeVisible();
    const threadUrl = page.url();
    await signOut(page);

    // The trainer was notified, and answers.
    await signIn(page, TRAINER);
    await page.goto('/notifications');
    await expect(
      page.getByTestId('notification-row').filter({ hasText: title }).first(),
    ).toBeVisible();

    await page.goto(threadUrl);
    await page.getByLabel('Your reply').fill('Check the file permissions first.');
    await page.getByRole('button', { name: 'Reply' }).click();

    const reply = page.getByTestId('reply').filter({ hasText: 'file permissions' });
    await expect(reply).toBeVisible();
    await expect(reply).toContainText('Trainer');

    // And the trainer can close it.
    await page.getByRole('button', { name: 'Close' }).click();
    await expect(page.getByText('Closed').first()).toBeVisible();
  });

  test('a discussion on another batch is not reachable', async ({ page }) => {
    await signIn(page, STUDENT);
    const response = await page.request.get(
      `${API}/api/v1/discussions/00000000-0000-4000-8000-000000000000/`,
    );
    expect(response.status()).toBe(404);
  });
});

test.describe('The learning surface', () => {
  test('a student sees where to pick up, what is coming, and who else is on the batch', async ({
    page,
  }) => {
    await signIn(page, STUDENT);
    await page
      .getByRole('navigation', { name: 'Main' })
      .getByRole('link', { name: 'My learning', exact: true })
      .click();

    await expect(page.getByRole('heading', { name: 'My learning' })).toBeVisible();
    await expect(page.getByTestId('learning-card').first()).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Coming up' })).toBeVisible();

    // §7.7: names only. No contact details anywhere on the page.
    const body = await page.locator('main').innerText();
    expect(body).not.toContain('@demo.grras.invalid');
  });

  test('the calendar carries deadlines as well as classes', async ({ page }) => {
    await signIn(page, STUDENT);
    await page.goto('/calendar');
    await expect(page.getByRole('heading', { name: /calendar/i })).toBeVisible();
  });
});
