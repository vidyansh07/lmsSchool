import { expect, test, type Page } from '@playwright/test';

/**
 * Batches, enrolment, dashboards and the calendar, against the real stack.
 *
 * Requires the full seed chain (`seed_demo_data`, `seed_courses`,
 * `seed_batches`) and `E2E_DEMO_PASSWORD`.
 */
const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? '';
const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const ADMIN = 'admin@demo.grras.invalid';
const STUDENT = 'student1@demo.grras.invalid';
const OTHER_STUDENT = 'student2@demo.grras.invalid';
const TRAINER = 'trainer1@demo.grras.invalid';

test.skip(!DEMO_PASSWORD, 'E2E_DEMO_PASSWORD is not set; seeded-data tests are skipped.');

async function signIn(page: Page, email: string) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: /^sign in$/i }).click();
  await expect(page.getByRole('heading', { name: /welcome back/i })).toBeVisible();
}

test.describe('Batch management', () => {
  test('an administrator sees every batch with its seats', async ({ page }) => {
    await signIn(page, ADMIN);
    await page.goto('/admin/batches');

    await expect(page.getByRole('heading', { name: 'Batches' })).toBeVisible();
    await expect(page.getByRole('table')).toBeVisible();
    // The seeder makes one batch deliberately full.
    await expect(page.getByText('Full').first()).toBeVisible();
  });

  test('a batch detail page shows its timetable and roster', async ({ page }) => {
    await signIn(page, ADMIN);
    await page.goto('/admin/batches');
    await page.getByRole('table').getByRole('link').first().click();

    await expect(page.getByRole('heading', { name: 'Timetable' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Students' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Trainer' })).toBeVisible();
  });

  test('a trainer sees only the batches they teach', async ({ page }) => {
    await signIn(page, TRAINER);
    await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Batches' }).click();

    await expect(page.getByRole('heading', { name: 'My batches' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'New batch' })).toHaveCount(0);
  });
});

test.describe('Student experience', () => {
  test('the dashboard shows courses, classes and batches', async ({ page }) => {
    await signIn(page, STUDENT);
    await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Dashboard' }).click();

    await expect(page.getByRole('heading', { name: 'My courses' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Upcoming classes' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'My batches' })).toBeVisible();
  });

  test('my batches lists enrolments with their state', async ({ page }) => {
    await signIn(page, STUDENT);
    await page.goto('/my-batches');

    await expect(page.getByRole('heading', { name: 'My batches' })).toBeVisible();
    // Every enrolment carries a status badge and its course.
    await expect(page.getByText('Active').first()).toBeVisible();
    await expect(page.getByRole('link', { name: /Linux Administration/ }).first()).toBeVisible();
  });

  test('a suspended enrolment is visible on the roster', async ({ page }) => {
    await signIn(page, ADMIN);

    // Find the batch that actually holds a suspended enrolment rather than
    // assuming which row of the table it is.
    const response = await page.request.get(`${API}/api/v1/enrollments/?status=suspended`);
    const body = (await response.json()) as { results: { batch_id: string }[] };
    test.skip(body.results.length === 0, 'No suspended enrolment in the seeded data.');

    await page.goto(`/admin/batches/${body.results[0]!.batch_id}`);
    await expect(page.getByRole('heading', { name: 'Students' })).toBeVisible();
    await expect(page.getByText('Suspended').first()).toBeVisible();
  });

  test('the calendar shows classes grouped by day', async ({ page }) => {
    await signIn(page, STUDENT);
    await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Calendar' }).click();

    await expect(page.getByRole('heading', { name: 'Calendar' })).toBeVisible();
    await expect(page.getByText('Class').first()).toBeVisible();
  });

  test('a student sees no batch-administration controls', async ({ page }) => {
    await signIn(page, STUDENT);
    const nav = page.getByRole('navigation', { name: 'Main' });
    // Exact: a student does have "My batches", which a substring match would hit.
    await expect(nav.getByRole('link', { name: 'Batches', exact: true })).toHaveCount(0);
    await expect(nav.getByRole('link', { name: 'Users', exact: true })).toHaveCount(0);
    await expect(nav.getByRole('link', { name: 'My batches', exact: true })).toBeVisible();
  });
});

test.describe('Access control through the API', () => {
  test('a student cannot read another student’s enrolment', async ({ page, browser }) => {
    // Two signed-in contexts, so both requests carry a real session.
    await signIn(page, STUDENT);

    const otherContext = await browser.newContext();
    const otherPage = await otherContext.newPage();
    await signIn(otherPage, OTHER_STUDENT);
    const theirs = await otherPage.request.get(`${API}/api/v1/enrollments/mine/`);
    const theirEnrollments = await theirs.json();
    await otherContext.close();

    test.skip(theirEnrollments.length === 0, 'The other student has no enrolment to probe.');

    const probe = await page.request.get(
      `${API}/api/v1/enrollments/${theirEnrollments[0].id}/`,
    );
    expect(probe.status()).toBe(404);
  });

  test('a trainer cannot enrol a student', async ({ page }) => {
    await signIn(page, TRAINER);
    const response = await page.request.post(`${API}/api/v1/enrollments/`, {
      data: {
        student_id: '00000000-0000-0000-0000-000000000000',
        batch_id: '00000000-0000-0000-0000-000000000000',
      },
      headers: { 'X-CSRFToken': (await page.context().cookies()).find((c) => c.name === 'grras_csrftoken')?.value ?? '' },
    });
    expect([403, 404]).toContain(response.status());
  });

  test('anonymous callers are refused every Phase 3 endpoint', async ({ request }) => {
    for (const path of [
      '/api/v1/batches/',
      '/api/v1/enrollments/',
      '/api/v1/enrollments/mine/',
      '/api/v1/calendar/',
      '/api/v1/dashboard/student/',
      '/api/v1/dashboard/trainer/',
    ]) {
      const response = await request.get(`${API}${path}`);
      expect([401, 403]).toContain(response.status());
    }
  });

  test('a guessed batch identifier leaks nothing', async ({ page }) => {
    await signIn(page, STUDENT);
    const response = await page.request.get(
      `${API}/api/v1/batches/00000000-0000-0000-0000-000000000000/`,
    );
    expect(response.status()).toBe(404);
    expect(await response.text()).not.toContain('Traceback');
  });
});
