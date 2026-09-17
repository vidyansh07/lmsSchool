import { expect, test } from '@playwright/test';

import { signIn, signOut } from './helpers';

/**
 * The activity engine, end to end through a real browser session
 * (`docs/erp/USER_JOURNEYS.md` §3.2 "Conduct a mock interview" and §2.2
 * "Open a student"; the backend half of the same chain is
 * `tests/test_erp_journey.py`'s §103 walk).
 *
 * Not a duplicate of `release-journey.spec.ts`: that spec proves the base
 * LMS (course, batch, register, completion, certificate). Nothing in it
 * touches an `Activity`, Student 360, or risk — this spec is the first e2e
 * coverage of any of the three.
 *
 * Trainer conducts a weak mock interview (created from the class's own DSR
 * panel, the one place the UI currently offers to create an activity — see
 * `components/teaching/dsr-create-activity.tsx`'s own docstring on why the
 * "Plan an activity" button `USER_JOURNEYS.md` describes is not a second,
 * separate control) → completes it with a low communication score → the
 * manager opens the same student's Student 360 page and finds it on the
 * Activities and Timeline tabs, with the Risk tab already reflecting it
 * (`risk_state_for`'s synchronous first-read fallback, `apps.performance
 * .services`, computes the verdict on this exact request rather than
 * waiting on the debounced Celery recompute — no polling needed here).
 *
 * The automation-created follow-up activity ("Communication practice after
 * a weak mock") is deliberately **not** asserted here: dispatching it runs
 * off a Celery worker via `transaction.on_commit`, and how long that takes
 * to land is not something a UI test should be timing — `test_erp_journey
 * .py` already proves that chain link for real, synchronously, through the
 * service layer.
 */
const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? '';
const TRAINER = 'trainer1@demo.grras.invalid';
const MANAGER = 'manager@demo.grras.invalid';
const STUDENT = 'student1@demo.grras.invalid';
const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

test.skip(!DEMO_PASSWORD, 'E2E_DEMO_PASSWORD is not set; seeded-data tests are skipped.');

test.describe.configure({ mode: 'serial' });

const ACTIVITY_TITLE = `E2E mock interview ${Date.now()}`;
let studentName = '';

test.describe('Journey: a weak mock interview, from the trainer to the manager', () => {
  test('a trainer conducts and completes a mock interview from today\'s class', async ({ page }) => {
    await signIn(page, TRAINER);

    // The activity created below starts unassigned (`apps.dsr.views`'s
    // create-activity endpoint sets `created_by` only) — the trainer's own
    // id is needed to self-assign it before PLANNED -> ASSIGNED accepts
    // (`apps.work.transitions`'s `assigned_to` precondition).
    const me = await page.request.get(`${API}/api/v1/auth/me/`);
    expect(me.ok()).toBeTruthy();
    const trainerId = ((await me.json()) as { id: string }).id;

    await page
      .getByRole('navigation', { name: 'Main' })
      .getByRole('link', { name: 'Classes today', exact: true })
      .click();
    await expect(page.getByRole('heading', { name: 'Teaching today' })).toBeVisible();

    // Open today's class — the same entry point `academics.spec.ts` already
    // proves lands on the class workspace (register, DSR panel, activities
    // panel, all on one page).
    await page.getByRole('link', { name: /take register|review register/i }).first().click();

    // --- Create the activity from the class's own DSR panel --------------
    const createButton = page.getByRole('button', { name: 'Create activity from this class' });
    await createButton.scrollIntoViewIfNeeded();
    await createButton.click();

    const form = page.getByRole('form', { name: 'Create activity from this class' });
    const studentSelect = form.getByLabel('Student');
    await expect(studentSelect.locator('option')).not.toHaveCount(1); // more than the placeholder
    await studentSelect.selectOption({ index: 1 });
    const rosterLabel = (await studentSelect.locator('option:checked').textContent()) ?? '';
    // The roster option reads "Full Name (GRS-S-00001)" — only the name
    // half is useful for finding this student again as the manager.
    studentName = rosterLabel.replace(/\s*\([^)]*\)\s*$/, '').trim();
    expect(studentName).not.toBe('');

    await form.getByLabel('Activity type').selectOption({ label: 'Mock Interview' });
    await form.getByLabel('Title').fill(ACTIVITY_TITLE);
    await form.getByRole('button', { name: 'Create activity' }).click();

    await expect(page.getByText('Activity created.')).toBeVisible();
    await page.getByRole('button', { name: 'Done' }).click();

    // --- Find it on the trainer's own work queue and open the drawer -----
    await page
      .getByRole('navigation', { name: 'Main' })
      .getByRole('link', { name: 'Activities', exact: true })
      .click();
    await page.getByRole('checkbox', { name: 'Mine' }).check();
    await page.getByRole('button', { name: ACTIVITY_TITLE }).click();

    const drawer = page.getByRole('dialog');
    await expect(drawer.getByText('Details')).toBeVisible();

    // A freshly-created activity has no `planned_at` and no `assigned_to`
    // yet — both are preconditions further down the transition table
    // (`apps.work.transitions`), so both are set here, once, before any
    // transition is attempted.
    await drawer.getByLabel('Planned at').fill('2020-01-01T09:00');
    await drawer.getByLabel('Assigned to (user id)').fill(trainerId);
    await drawer.getByRole('button', { name: 'Save details' }).click();
    await expect(drawer.getByText('Saved.')).toBeVisible();

    await drawer.getByRole('button', { name: 'Plan' }).click();
    await drawer.getByRole('button', { name: 'Assign' }).click();
    await drawer.getByRole('button', { name: 'Start' }).click();

    // --- Complete it with a weak score: trips the risk/activity rule -----
    await expect(drawer.getByText('Complete this activity')).toBeVisible();
    await drawer.getByLabel(/Technical/).fill('3');
    await drawer.getByLabel(/Communication/).fill('3');
    await drawer.getByLabel(/Confidence/).fill('3');
    await drawer.getByLabel(/Overall/).fill('2');
    await drawer.getByLabel('Outcome').selectOption({ label: 'Not ready' });
    await drawer.getByLabel('Improve').fill('Structure answers and slow down under follow-up questions.');
    await drawer.getByLabel('Private notes').fill('Struggled badly under pressure; flag for the manager.');
    await drawer.getByRole('button', { name: 'Mark complete' }).click();

    await expect(drawer.getByText('Marked complete.')).toBeVisible();
    await expect(drawer.getByText('Completed', { exact: true })).toBeVisible();

    await signOut(page);
  });

  test('a manager finds it on the student\'s 360 profile, with risk already reflecting it', async ({
    page,
  }) => {
    test.skip(studentName === '', 'the trainer test above did not record a student name');

    await signIn(page, MANAGER);

    await page
      .getByRole('navigation', { name: 'Main' })
      .getByRole('link', { name: 'Students', exact: true })
      .click();
    await page.getByPlaceholder('Student ID, name, email or institution').fill(studentName);
    await page.getByRole('link', { name: `Open ${studentName}` }).click();
    await page.getByRole('link', { name: 'View 360 profile' }).click();

    await expect(page.getByRole('tab', { name: 'Overview' })).toBeVisible();

    await page.getByRole('tab', { name: 'Activities' }).click();
    await expect(page.getByText(ACTIVITY_TITLE)).toBeVisible();

    await page.getByRole('tab', { name: 'Timeline' }).click();
    await expect(page.getByText(ACTIVITY_TITLE)).toBeVisible();

    // The Risk tab: `risk_state_for`'s synchronous first-read fallback means
    // this reflects the weak score on this very request, no waiting on a
    // background recompute.
    await page.getByRole('tab', { name: 'Risk' }).click();
    await expect(page.getByText(/warning|critical/i).first()).toBeVisible();

    await signOut(page);
  });

  test('a student cannot reach the staff activity surfaces directly', async ({ page }) => {
    await signIn(page, STUDENT);

    // No nav link is offered (`RequireAuth`'s own capability gate never
    // renders it) — this is the thing behind that: the page loads and the
    // API refuses, the same shape `hardening.spec.ts` already proves for
    // `/admin/*`.
    await page.goto('/activities');
    await expect(page.getByRole('heading', { name: 'Activities', exact: true })).toHaveCount(0);

    await page.goto('/admin/activity-types');
    await expect(page.getByRole('heading', { name: 'Activity types' })).toHaveCount(0);
  });
});
