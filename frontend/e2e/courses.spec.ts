import { expect, test } from '@playwright/test';

import { signIn } from './helpers';

/**
 * Course catalogue, player and authoring, against the real stack.
 *
 * Requires the seeded demo data (`seed_demo_data` then `seed_courses`) and
 * `E2E_DEMO_PASSWORD` matching the password it was seeded with.
 */
const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? '';
const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const ADMIN = 'admin@demo.grras.invalid';
const STUDENT = 'student1@demo.grras.invalid';
const TRAINER = 'trainer1@demo.grras.invalid';

test.skip(!DEMO_PASSWORD, 'E2E_DEMO_PASSWORD is not set; seeded-data tests are skipped.');


test.describe('Course catalogue', () => {
  test('a student browses published courses and can filter them', async ({ page }) => {
    await signIn(page, STUDENT);
    await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Courses' }).click();

    await expect(page.getByRole('heading', { name: 'Course catalogue' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Linux Administration Foundations' })).toBeVisible();

    // The one seeded draft course must never appear.
    await expect(page.getByText('Data Analysis with SQL')).toHaveCount(0);

    await page.getByLabel('Search').fill('Python');
    await expect(page.getByRole('link', { name: /Python Programming/ })).toBeVisible();
  });

  test('a student opens a course page and sees its outline', async ({ page }) => {
    await signIn(page, STUDENT);
    await page.goto('/courses/linux-administration-foundations');

    await expect(
      page.getByRole('heading', { name: 'Linux Administration Foundations' }),
    ).toBeVisible();
    await expect(page.getByText('What you will learn')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Course content' })).toBeVisible();
    await expect(page.getByRole('link', { name: /Overview:/ }).first()).toBeVisible();
  });

  test('the course player renders a lesson with navigation', async ({ page }) => {
    await signIn(page, STUDENT);

    // From Phase 3 the lesson body needs a live enrolment, so the walk starts
    // from a course this student actually has access to.
    const mine = await page.request.get(`${API}/api/v1/enrollments/mine/`);
    const enrollments = (await mine.json()) as { course_slug: string; grants_access: boolean }[];
    const open = enrollments.find((row) => row.grants_access);
    test.skip(!open, 'This student has no enrolment granting access.');

    await page.goto(`/courses/${open!.course_slug}`);
    await page.getByRole('link', { name: /Overview:/ }).first().click();

    await expect(page.getByRole('navigation', { name: 'Course outline' })).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Lesson navigation' })).toBeVisible();

    // Next moves to a different lesson.
    const heading = page.getByRole('heading', { level: 1 });
    const firstTitle = await heading.textContent();
    await page.getByRole('navigation', { name: 'Lesson navigation' }).getByRole('link').last().click();
    await expect(heading).not.toHaveText(firstTitle ?? '');
  });

  test('a student cannot reach the draft course, by URL or by API', async ({ page }) => {
    await signIn(page, STUDENT);
    await page.goto('/courses/data-analysis-with-sql');
    await expect(page.getByText(/course not found/i)).toBeVisible();

    // `page.request` shares the signed-in browser context, so this is a real
    // authenticated student calling the API directly — not an anonymous client.
    const response = await page.request.get(`${API}/api/v1/courses/data-analysis-with-sql/`);
    expect(response.status()).toBe(404);
    expect(await response.text()).not.toContain('Data Analysis');
  });

  test('a student sees no authoring navigation', async ({ page }) => {
    await signIn(page, STUDENT);
    const nav = page.getByRole('navigation', { name: 'Main' });
    await expect(nav.getByRole('link', { name: 'Authoring' })).toHaveCount(0);
    await expect(nav.getByRole('link', { name: 'Courses' })).toBeVisible();
  });
});

test.describe('Course authoring', () => {
  test('an administrator sees every course including drafts', async ({ page }) => {
    await signIn(page, ADMIN);
    await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Authoring' }).click();

    await expect(page.getByRole('heading', { name: 'Courses' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Data Analysis with SQL' })).toBeVisible();
    await expect(page.getByText('Draft').first()).toBeVisible();
  });

  test('an administrator opens the course editor', async ({ page }) => {
    await signIn(page, ADMIN);
    await page.goto('/admin/courses');
    await page.getByRole('link', { name: 'Linux Administration Foundations' }).click();

    await expect(page.getByRole('heading', { name: 'Modules and lessons' })).toBeVisible();
    await expect(page.getByText('Publishing')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Course details' })).toBeVisible();
  });

  test('a trainer sees only the courses assigned to them', async ({ page }) => {
    await signIn(page, TRAINER);
    await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Authoring' }).click();

    await expect(page.getByRole('heading', { name: 'My courses' })).toBeVisible();
    // The seeder assigns one course per trainer, so the list is smaller than
    // the full catalogue.
    await expect(page.getByText(/Showing 1–1 of 1/)).toBeVisible();
  });

  test('a trainer cannot create courses', async ({ page }) => {
    await signIn(page, TRAINER);
    await page.goto('/admin/courses');
    await expect(page.getByRole('button', { name: 'New course' })).toHaveCount(0);
  });
});

test.describe('Course API access control', () => {
  test('anonymous callers are refused every course endpoint', async ({ request }) => {
    for (const path of ['/api/v1/courses/', '/api/v1/categories/', '/api/v1/courses/mine/']) {
      const response = await request.get(`${API}${path}`);
      expect([401, 403]).toContain(response.status());
    }
  });

  test('a guessed course identifier does not leak anything', async ({ request }) => {
    const response = await request.get(
      `${API}/api/v1/courses/00000000-0000-0000-0000-000000000000/`,
    );
    expect([401, 403, 404]).toContain(response.status());
    expect(await response.text()).not.toContain('Traceback');
  });
});
