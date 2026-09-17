import { expect, test } from '@playwright/test';

import { signIn, signOut } from './helpers';

/**
 * Duplicate detection on registration — `docs/erp/USER_JOURNEYS.md` §4.2
 * (ERP Phase 17): "as soon as email or phone is complete, the wizard asks
 * the server 'does anyone match?'" and shows "Possible existing student
 * found" rather than silently letting a second record for the same person
 * through.
 *
 * Not covered anywhere else: `academics.spec.ts`/`batches.spec.ts` walk a
 * trainer's and a student's own screens; no existing spec signs in as a
 * counsellor or opens `/admissions/new` at all.
 *
 * The duplicate is forced with the seeded student's own email — a real
 * match the server itself finds (`apps.students.services
 * .find_duplicate_candidates`), not a fabricated one — and the journey is
 * proved only as far as the warning and its two ways out (open the
 * existing record; confirm a different person and continue), which is the
 * ERP-introduced part. The rest of the wizard (course, batch, fee) is base
 * LMS admissions, unrelated to this phase.
 */
const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? '';
const COUNSELLOR = 'counsellor@demo.grras.invalid';
const EXISTING_STUDENT_EMAIL = 'student1@demo.grras.invalid';

test.skip(!DEMO_PASSWORD, 'E2E_DEMO_PASSWORD is not set; seeded-data tests are skipped.');

test.describe('Journey: registering a student the server has already met', () => {
  test('a counsellor is warned of a likely duplicate, and can open the existing record', async ({
    page,
  }) => {
    await signIn(page, COUNSELLOR);

    await page
      .getByRole('navigation', { name: 'Main' })
      .getByRole('link', { name: 'Register a student', exact: true })
      .click();
    await expect(page.getByRole('heading', { name: 'Register a student' })).toBeVisible();

    await page.getByLabel('Email').fill(EXISTING_STUDENT_EMAIL);
    await page.getByLabel('First name').fill('Duplicate');
    await page.getByLabel('Last name').fill('Check');

    const warning = page.getByTestId('duplicate-warning');
    await expect(warning).toBeVisible();
    await expect(warning).toContainText(/possible existing student/i);

    // Continuing is refused until the duplicate is resolved one way or the
    // other — the same "cannot submit past an unresolved warning" the
    // component's own docstring describes.
    const nextButton = page.getByRole('button', { name: 'Next: choose a course' });
    await expect(nextButton).toBeDisabled();

    // Way out #1: open the record the server matched, rather than register
    // a second one.
    await warning.getByRole('link', { name: 'Open that record' }).click();
    await expect(page).toHaveURL(/\/admissions\/[0-9a-f-]+$/);
    await expect(page.getByRole('link', { name: 'View 360 profile' })).toBeVisible();

    await signOut(page);
  });

  test('a counsellor can confirm a different person and continue, with a reason on record', async ({
    page,
  }) => {
    await signIn(page, COUNSELLOR);

    await page
      .getByRole('navigation', { name: 'Main' })
      .getByRole('link', { name: 'Register a student', exact: true })
      .click();

    await page.getByLabel('Email').fill(EXISTING_STUDENT_EMAIL);
    await page.getByLabel('First name').fill('Also Not');
    await page.getByLabel('Last name').fill('The Same Person');

    const warning = page.getByTestId('duplicate-warning');
    await expect(warning).toBeVisible();

    const nextButton = page.getByRole('button', { name: 'Next: choose a course' });
    await expect(nextButton).toBeDisabled();

    // Way out #2: the override reason is required — the "continue" action
    // stays disabled on an empty one.
    const continueButton = page.getByRole('button', {
      name: 'Continue registering — different person',
    });
    await expect(continueButton).toBeDisabled();
    await page
      .getByLabel('This is a different person — why?')
      .fill('Confirmed by phone: a different person who shares this household email.');
    await expect(continueButton).toBeEnabled();
    await continueButton.click();

    await expect(nextButton).toBeEnabled();

    await signOut(page);
  });
});
