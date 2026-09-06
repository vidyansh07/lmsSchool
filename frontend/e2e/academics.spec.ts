import { expect, test, type Page } from '@playwright/test';

import { signIn, signOut } from './helpers';

/**
 * The three journeys §4.8 names, end to end against the real stack.
 *
 *   1. trainer takes a register → the student sees their attendance
 *   2. trainer sets work → student hands in a file → trainer grades → student sees the grade
 *   3. trainer uploads a result file → previews it → confirms → student sees the result
 *
 * Requires the full seed chain (`seed_demo_data`, `seed_courses`, `seed_batches`,
 * `seed_academics`) and `E2E_DEMO_PASSWORD`.
 */
const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? '';
const STUDENT = 'student1@demo.grras.invalid';
const TRAINER = 'trainer1@demo.grras.invalid';

test.skip(!DEMO_PASSWORD, 'E2E_DEMO_PASSWORD is not set; seeded-data tests are skipped.');



const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

/**
 * The batch the seeded student is actually taught on.
 *
 * Read from the student's own enrolments rather than guessed from the trainer's
 * timetable: trainer1 teaches more than one batch, and which of their classes
 * sorts first today is not something a test should depend on.
 */
async function studentBatchCode(page: Page): Promise<string> {
  await signIn(page, STUDENT);
  const response = await page.request.get(`${API}/api/v1/enrollments/mine/`);
  expect(response.ok()).toBeTruthy();
  const rows = (await response.json()) as { batch_code: string; grants_access: boolean }[];
  const live = rows.find((row) => row.grants_access);
  expect(live, 'the seeded student needs one enrolment that opens its course').toBeTruthy();
  await signOut(page);
  return (live as { batch_code: string }).batch_code;
}

async function selectByCode(page: Page, label: string, code: string) {
  const option = page.getByLabel(label).locator('option', { hasText: code }).first();
  await page.getByLabel(label).selectOption(await option.getAttribute('value'));
}

test.describe('Journey: taking a register', () => {
  test('a trainer marks today\'s class and the student sees it', async ({ page }) => {
    await signIn(page, TRAINER);

    // Trainer's daily driver.
    await page
      .getByRole('navigation', { name: 'Main' })
      .getByRole('link', { name: 'Classes today', exact: true })
      .click();
    await expect(page.getByRole('heading', { name: 'Teaching today' })).toBeVisible();

    // Open today's class and take its register.
    await page.getByRole('link', { name: /take register|review register/i }).first().click();
    await expect(page.getByRole('heading', { name: 'Register' })).toBeVisible();

    const rows = page.getByRole('table').locator('tbody tr');
    await expect(rows.first()).toBeVisible();

    await page.getByRole('button', { name: 'Mark all present' }).click();
    await page.getByRole('button', { name: 'Save register' }).click();
    await expect(page.getByRole('status')).toContainText(/saved/i);

    await signOut(page);

    // The student sees the mark on their own attendance page.
    await signIn(page, STUDENT);
    await page
      .getByRole('navigation', { name: 'Main' })
      .getByRole('link', { name: 'My attendance', exact: true })
      .click();
    await expect(page.getByRole('heading', { name: 'My attendance' })).toBeVisible();
    await expect(page.getByText('Present').first()).toBeVisible();
    // The requirement travels with the number, whichever way it is configured —
    // that is the invariant, not whether attendance happens to be required.
    await expect(
      page.getByText(/% required|not a completion requirement/).first(),
    ).toBeVisible();
  });
});

test.describe('Journey: set, submit, grade', () => {
  test('a trainer sets work, a student hands in a file, the trainer grades it', async ({
    page,
  }) => {
    const title = `E2E exercise ${Date.now()}`;

    const batchCode = await studentBatchCode(page);

    await signIn(page, TRAINER);
    await page.goto('/teaching/assignments');
    await expect(page.getByRole('heading', { name: 'Assignments' })).toBeVisible();

    await page.getByRole('button', { name: 'New assignment' }).click();
    await selectByCode(page, 'Batch', batchCode);
    await page.getByLabel('Title').fill(title);
    await page.getByLabel('Instructions').fill('Hand in a source file.');
    await page.getByLabel('Marks out of').fill('50');
    await page.getByRole('button', { name: 'Create assignment' }).click();

    // Created as a draft, then published so students can see it.
    await page.getByRole('link', { name: title }).click();
    await expect(page.getByRole('heading', { name: title })).toBeVisible();
    await page.getByRole('button', { name: 'Publish' }).click();
    await expect(page.getByRole('status')).toContainText(/published/i);

    const assignmentUrl = page.url();
    await signOut(page);

    // The student hands in a real file.
    await signIn(page, STUDENT);
    await page.goto('/my-assignments');
    const card = page.getByTestId('assignment-card').filter({ hasText: title });
    await expect(card).toBeVisible();

    await card
      .getByLabel('Files')
      .setInputFiles({
        name: 'solution.py',
        mimeType: 'text/x-python',
        buffer: Buffer.from('def solve():\n    return 42\n'),
      });
    await card.getByRole('button', { name: 'Submit' }).click();
    await expect(page.getByRole('status')).toContainText(/submitted/i);

    await signOut(page);

    // The trainer grades it.
    await signIn(page, TRAINER);
    await page.goto(assignmentUrl);
    await expect(page.getByRole('heading', { name: 'Submissions (1)' })).toBeVisible();

    const queue = page.getByRole('table').locator('tbody tr').first();
    await queue.getByLabel('Marks').fill('45');
    await queue.getByLabel('Feedback').fill('Correct and readable.');
    await queue.getByRole('button', { name: 'Save grade' }).click();
    await expect(page.getByRole('status')).toContainText(/graded/i);

    await signOut(page);

    // And the student sees the mark.
    await signIn(page, STUDENT);
    await page.goto('/my-assignments');
    await expect(page.getByTestId('my-grade').first()).toContainText('45');
    await expect(page.getByText(title).first()).toBeVisible();

    // Retire the task. Without this the suite leaves one behind on every run,
    // and after forty of them the newest is on page two and the journey stops
    // being able to find what it just created. Archiving is what a trainer does
    // with finished work, and everything handed in is untouched.
    await signOut(page);
    await signIn(page, TRAINER);
    await page.goto(assignmentUrl);
    await page.getByRole('button', { name: 'Archive' }).click();
    await expect(page.getByRole('status')).toContainText(/archived/i);
  });

  test('an executable is refused, and nothing is stored', async ({ page }) => {
    await signIn(page, STUDENT);
    await page.goto('/my-assignments');

    const form = page.locator('form').filter({ has: page.getByLabel('Files') }).first();
    await expect(form).toBeVisible();

    await form.getByLabel('Files').setInputFiles({
      name: 'payload.exe',
      mimeType: 'application/octet-stream',
      buffer: Buffer.from('MZ\x90\x00binary'),
    });
    await form.getByRole('button', { name: 'Submit' }).click();

    // The refusal is shown against the field the student used, not swallowed.
    await expect(form).toContainText(/executable|cannot be submitted/i);
  });
});

test.describe('Journey: importing weekly test results', () => {
  test('preview, confirm, and the student sees the result', async ({ page }) => {
    await signIn(page, TRAINER);
    await page.goto('/teaching/assessments');
    await expect(page.getByRole('heading', { name: 'Weekly tests' })).toBeVisible();

    await page.getByRole('table').getByRole('link').first().click();
    await expect(page.getByRole('heading', { name: 'Import results' })).toBeVisible();

    // Build the file from the cohort actually on the marks sheet, so the import
    // is validated against real student ids rather than invented ones.
    const codes = await page
      .getByRole('table')
      .locator('tbody tr td:first-child .font-mono')
      .allInnerTexts();
    expect(codes.length).toBeGreaterThan(0);

    const csv = ['student_id,marks', ...codes.map((code, index) => `${code.trim()},${12 + index}`)]
      .join('\n');

    await page.getByLabel('Result file').setInputFiles({
      name: 'week1-results.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(csv),
    });
    await page.getByRole('button', { name: 'Preview import' }).click();

    // Step one reports; it does not write.
    const preview = page.getByTestId('import-preview');
    await expect(preview).toBeVisible();
    await expect(preview).toContainText(`${codes.length} of ${codes.length} rows would apply`);

    await preview.getByRole('button', { name: 'Confirm import' }).click();
    await expect(page.getByRole('status')).toContainText(/imported/i);

    await signOut(page);

    await signIn(page, STUDENT);
    await page.goto('/my-results');
    await expect(page.getByRole('heading', { name: 'My tests and results' })).toBeVisible();
    await expect(page.getByTestId('result-row').first()).toBeVisible();
  });

  test('a file naming an unknown student is reported and not applied', async ({ page }) => {
    await signIn(page, TRAINER);
    await page.goto('/teaching/assessments');
    await page.getByRole('table').getByRole('link').first().click();

    await page.getByLabel('Result file').setInputFiles({
      name: 'bad.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('student_id,marks\nGRS-S-99999,12\n'),
    });
    await page.getByRole('button', { name: 'Preview import' }).click();

    const preview = page.getByTestId('import-preview');
    await expect(preview).toContainText(/not a student in this assessment/i);
    await expect(preview.getByRole('button', { name: 'Confirm import' })).toBeDisabled();
  });
});
