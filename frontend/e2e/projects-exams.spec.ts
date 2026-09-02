import { expect, test, type Page } from '@playwright/test';

import { signIn, signOut } from './helpers';

/**
 * The two journeys §5.7 names, end to end against the real stack.
 *
 *   1. trainer sets a project → student hands in a deliverable → trainer reviews
 *      and grades → student sees the feedback → required-project progress moves
 *   2. admin creates an exam → student sits it → answers auto-save → submits →
 *      the server grades → results are released → the student sees the result
 *
 * Requires the full seed chain and `E2E_DEMO_PASSWORD`.
 */
const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? '';
const ADMIN = 'admin@demo.grras.invalid';
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

test.describe('Journey: set, submit, review a project', () => {
  test('a trainer sets a project, a student hands it in, the trainer grades it', async ({
    page,
  }) => {
    const title = `E2E project ${Date.now()}`;

    const batchCode = await studentBatchCode(page);

    await signIn(page, TRAINER);
    await page.goto('/teaching/projects');
    await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible();
    await page.getByRole('button', { name: 'New project' }).click();
    await selectByCode(page, 'Batch', batchCode);
    await page.getByLabel('Title').fill(title);
    await page.getByLabel('Description').fill('Build something small and useful.');
    await page.getByLabel('Deliverables').fill('Source and a README.');
    await page.getByLabel('Marks out of').fill('100');
    await page.getByRole('button', { name: 'Create project' }).click();

    // Publish, then hand it to the cohort.
    await page.getByRole('link', { name: title }).click();
    await expect(page.getByRole('heading', { name: title })).toBeVisible();
    await page.getByRole('button', { name: 'Publish' }).click();
    await expect(page.getByRole('status')).toContainText(/published/i);
    await page.getByRole('button', { name: 'Assign to the cohort' }).click();
    await expect(page.getByRole('status')).toContainText(/assigned/i);

    const projectUrl = page.url();
    await signOut(page);

    // The student hands in a real file.
    await signIn(page, STUDENT);
    await page.goto('/my-projects');
    const card = page.getByTestId('project-card').filter({ hasText: title });
    await expect(card).toBeVisible();

    await card.getByLabel('Files').setInputFiles({
      name: 'tool.py',
      mimeType: 'text/x-python',
      buffer: Buffer.from("print('my tool')\n"),
    });
    await card.getByLabel('Repository URL').fill('https://git.example.test/me/tool');
    await card.getByRole('button', { name: 'Hand in' }).click();
    await expect(page.getByRole('status')).toContainText(/handed in/i);

    await signOut(page);

    // The trainer reviews and approves it.
    await signIn(page, TRAINER);
    await page.goto(projectUrl);
    // The row for the student who actually handed something in — the rest of
    // the cohort is on the same queue with nothing to review.
    const queue = page
      .getByRole('table')
      .locator('tbody tr')
      .filter({ hasText: 'Submitted' })
      .first();
    await expect(queue).toBeVisible();
    await queue.getByLabel('Marks').fill('88');
    await queue.getByLabel('Feedback').fill('Clean, well documented.');
    await queue.getByRole('button', { name: 'Approve' }).click();
    await expect(page.getByRole('status')).toContainText(/approved/i);

    await signOut(page);

    // The student sees the mark, the feedback, and their progress moving.
    await signIn(page, STUDENT);
    await page.goto('/my-projects');
    const reviewed = page.getByTestId('project-card').filter({ hasText: title });
    await expect(reviewed.getByTestId('project-grade')).toContainText('88');
    await expect(reviewed.getByTestId('project-feedback')).toContainText('Clean, well documented');
    await expect(page.getByTestId('required-progress').first()).toBeVisible();

    // Put the brief away again. Without this the suite leaves a project behind
    // on every run, and after forty of them the newest one is on page two and
    // the journey stops being able to find what it just created. Archiving is
    // what a trainer would actually do with a finished brief, and the handed-in
    // work is untouched.
    await signOut(page);
    await signIn(page, TRAINER);
    await page.goto(projectUrl);
    await page.getByRole('button', { name: 'Archive' }).click();
    await expect(page.getByRole('status')).toContainText(/archived/i);
  });

  test('an executable deliverable is refused', async ({ page }) => {
    await signIn(page, STUDENT);
    await page.goto('/my-projects');

    const form = page.locator('form').filter({ has: page.getByLabel('Files') }).first();
    await expect(form).toBeVisible();

    await form.getByLabel('Files').setInputFiles({
      name: 'tool.exe',
      mimeType: 'application/octet-stream',
      buffer: Buffer.from('MZ\x90\x00binary'),
    });
    await form.getByRole('button', { name: 'Hand in' }).click();

    await expect(form).toContainText(/executable|cannot be submitted/i);
  });
});

/** `2026-09-01T10:30` — what a datetime-local input expects, in local time. */
function localDateTime(offsetMinutes: number): string {
  const when = new Date(Date.now() + offsetMinutes * 60_000);
  const pad = (value: number) => String(value).padStart(2, '0');
  return (
    `${when.getFullYear()}-${pad(when.getMonth() + 1)}-${pad(when.getDate())}` +
    `T${pad(when.getHours())}:${pad(when.getMinutes())}`
  );
}

test.describe('Journey: sit an examination', () => {
  /**
   * The journey §5.7 names, start to finish, on an examination this test
   * creates. Self-contained on purpose: an attempt limit means a test that
   * reuses a seeded examination passes once and fails every run after.
   */
  test('admin creates it, a student sits it, and the result is released', async ({ page }) => {
    const title = `E2E examination ${Date.now()}`;

    // --- Admin creates the examination on the student's own batch.
    const batchCode = await studentBatchCode(page);

    await signIn(page, ADMIN);
    await page.goto('/teaching/exams');
    await page.getByRole('button', { name: 'New examination' }).click();
    await selectByCode(page, 'Batch', batchCode);
    await page.getByLabel('Title', { exact: true }).fill(title);
    await page.getByLabel('Duration in minutes').fill('45');
    await page.getByLabel('Attempts allowed').fill('1');
    await page.getByLabel('Opens').fill(localDateTime(-5));
    await page.getByLabel('Closes').fill(localDateTime(60 * 24));
    await page.getByLabel('Questions to draw').fill('3');
    await page.getByRole('button', { name: 'Create examination' }).click();

    await page.getByRole('link', { name: title }).click();
    await expect(page.getByTestId('exam-readiness')).toContainText(/ready to publish/i);
    await page.getByRole('button', { name: 'Publish' }).click();
    await expect(page.getByRole('status')).toContainText(/published/i);
    const examUrl = page.url();
    await signOut(page);

    // --- The student sits it.
    await signIn(page, STUDENT);
    await page.goto('/exams');
    const card = page.getByTestId('exam-card').filter({ hasText: title });
    await expect(card).toBeVisible();
    await card.getByRole('link', { name: /start the examination/i }).click();

    // The paper is drawn, and the clock is the server's.
    await expect(page.getByTestId('exam-countdown')).not.toHaveText('—');
    const questions = page.getByTestId('exam-question');
    await expect(questions.first()).toBeVisible();
    const count = await questions.count();
    expect(count).toBe(3);

    for (let index = 0; index < count; index += 1) {
      const question = questions.nth(index);
      const choice = question.locator('input[type="radio"], input[type="checkbox"]').first();
      if (await choice.count()) {
        await choice.check();
      } else {
        await question.getByRole('textbox').fill('A shell reads commands and runs them.');
        await question.getByRole('textbox').blur();
      }
    }
    // Answers reach the server as they are given.
    await expect(page.getByTestId('autosave-marker')).toBeVisible();

    // A refresh must not lose the paper or restart the clock.
    const attemptUrl = page.url();
    await page.reload();
    await expect(page.getByTestId('exam-question').first()).toBeVisible();
    expect(page.url()).toBe(attemptUrl);

    await page.getByRole('button', { name: 'Submit my paper' }).click();
    await expect(page.getByRole('status')).toContainText(/submitted/i);

    // The attempt limit holds: there is no second sitting on offer.
    await page.goto('/exams');
    const sat = page.getByTestId('exam-card').filter({ hasText: title });
    await expect(sat.getByRole('link', { name: /start the examination/i })).toHaveCount(0);
    // And the result is withheld until it is released.
    await expect(sat).toContainText(/results have not been released/i);

    await signOut(page);

    // --- The trainer marks anything written, then releases the results.
    await signIn(page, ADMIN);
    await page.goto(examUrl);

    // Wait for the marking queue before deciding whether there is anything in
    // it: checking the button count straight after navigating races the fetch,
    // and a skipped mark leaves the attempt ungraded and the score withheld.
    const queueHeading = page.getByRole('heading', { name: /Answers awaiting marking/ });
    await expect(queueHeading).toBeVisible();
    const pending = Number(/\((\d+)\)/.exec(await queueHeading.innerText())?.[1] ?? '0');

    for (let index = 0; index < pending; index += 1) {
      await page.getByLabel(/^Marks \(out of/).first().fill('8');
      await page.getByRole('button', { name: 'Save mark' }).first().click();
      await expect(page.getByRole('status')).toContainText(/marked/i);
    }

    await page.getByRole('button', { name: 'Release results' }).click();
    await expect(page.getByRole('status')).toContainText(/released/i);
    await signOut(page);

    // --- And the candidate sees their score, marked by the server.
    await signIn(page, STUDENT);
    await page.goto('/exams');
    const released = page.getByTestId('exam-card').filter({ hasText: title });
    await expect(released.getByTestId('exam-score')).toBeVisible();
    await expect(released.getByTestId('exam-score')).toContainText('/');
  });

  test('a candidate cannot open somebody else\'s paper', async ({ page }) => {
    await signIn(page, STUDENT);
    // A well-formed identifier that is not theirs resolves to nothing at all.
    const response = await page.request.get(
      `${process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000'}` +
        '/api/v1/attempts/00000000-0000-4000-8000-000000000000/result/',
    );
    expect(response.status()).toBe(404);
  });
});
