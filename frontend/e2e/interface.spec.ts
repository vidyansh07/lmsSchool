import { expect, test } from '@playwright/test';

import { DEMO_PASSWORD, signIn, signOut } from './helpers';

/**
 * §11.4 and §11.5 in a browser.
 *
 * The theme's contrast is measured in a unit test, which can read the palette
 * exactly. What a browser adds is everything the palette cannot tell you: that
 * the page is actually light whatever the viewer's operating system says, that
 * staff get a sidebar and students do not, and that the whole thing can be
 * driven from a keyboard.
 */
const ADMIN = 'admin@demo.grras.invalid';
const TRAINER = 'trainer1@demo.grras.invalid';
const STUDENT = 'student1@demo.grras.invalid';

test.skip(!DEMO_PASSWORD, 'E2E_DEMO_PASSWORD is not set; seeded-data tests are skipped.');

test.describe('The interface is light, whatever the machine prefers', () => {
  test.use({ colorScheme: 'dark' });

  test('a viewer whose system is dark still sees the light theme', async ({ page }) => {
    // The reason this is pinned: the app used to follow the operating system,
    // so the same install looked different on two people's machines and nobody
    // could say what the product looked like.
    await page.goto('/login');

    // Painted onto a canvas and read back, rather than parsed from
    // `getComputedStyle`. Modern engines return whatever colour syntax they
    // like — this one answers `lab(98.2578 …)` — and a regex written for
    // `rgb(…)` silently reads the wrong numbers out of it.
    const channels = await page.evaluate(() => {
      const colour = getComputedStyle(document.body).backgroundColor;
      const canvas = document.createElement('canvas');
      canvas.width = 1;
      canvas.height = 1;
      const context = canvas.getContext('2d')!;
      context.fillStyle = colour;
      context.fillRect(0, 0, 1, 1);
      const pixel = context.getImageData(0, 0, 1, 1).data;
      return [pixel[0] ?? 0, pixel[1] ?? 0, pixel[2] ?? 0];
    });
    // A light page: every channel high. A dark one would be under 60.
    expect(Math.min(...channels)).toBeGreaterThan(230);

    const scheme = await page.evaluate(() => getComputedStyle(document.documentElement).colorScheme);
    expect(scheme).toContain('light');
  });
});

test.describe('Staff navigation', () => {
  test('an administrator gets a grouped sidebar', async ({ page }) => {
    await signIn(page, ADMIN);

    const nav = page.getByRole('navigation', { name: 'Main' });
    await expect(nav).toBeVisible();

    // Grouped by the job being done, not by the system's tables.
    await expect(nav.getByText('People', { exact: true })).toBeVisible();
    await expect(nav.getByRole('link', { name: 'Users' })).toBeVisible();
    await expect(nav.getByRole('link', { name: 'Students' })).toBeVisible();
    await expect(nav.getByRole('link', { name: 'Trainers' })).toBeVisible();

    await signOut(page);
  });

  test('the current page is marked, and only the current page', async ({ page }) => {
    await signIn(page, ADMIN);
    await page.goto('/admin/students');

    const nav = page.getByRole('navigation', { name: 'Main' });
    await expect(nav.getByRole('link', { name: 'Students' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    // Longest match wins: a nested page must not light up its parent as well.
    await expect(nav.locator('[aria-current="page"]')).toHaveCount(1);

    await signOut(page);
  });

  test('a trainer sees teaching, and not the screens that administer people', async ({ page }) => {
    await signIn(page, TRAINER);

    const nav = page.getByRole('navigation', { name: 'Main' });
    await expect(nav.getByRole('link', { name: 'Classes today' })).toBeVisible();
    await expect(nav.getByRole('link', { name: 'Users' })).toHaveCount(0);
    await expect(nav.getByRole('link', { name: 'Academic rules' })).toHaveCount(0);

    await signOut(page);
  });

  test('a student keeps the top bar and gets no sidebar', async ({ page }) => {
    await signIn(page, STUDENT);

    const nav = page.getByRole('navigation', { name: 'Main' });
    await expect(nav.getByRole('link', { name: 'My learning' })).toBeVisible();
    // The staff groups are the tell: a student should never see them.
    await expect(nav.getByText('People', { exact: true })).toHaveCount(0);
    await expect(nav.getByText('Outcomes', { exact: true })).toHaveCount(0);

    await signOut(page);
  });

  test('the sidebar can be reached and used from the keyboard', async ({ page }) => {
    await signIn(page, ADMIN);
    await page.goto('/admin/overview');

    // Tab from the top: the skip link comes first, which is the point of it.
    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: /skip to content/i })).toBeFocused();

    // Keep going until a navigation link has focus, and check it is visibly so.
    const navLink = page.getByRole('navigation', { name: 'Main' }).getByRole('link').first();
    for (let step = 0; step < 12; step += 1) {
      await page.keyboard.press('Tab');
      if (await navLink.evaluate((node) => node === document.activeElement)) break;
    }
    await expect(navLink).toBeFocused();

    const outline = await navLink.evaluate((node) => getComputedStyle(node).outlineStyle);
    expect(outline).not.toBe('none');

    await signOut(page);
  });
});

test.describe('Narrow screens', () => {
  test.use({ viewport: { width: 640, height: 900 } });

  test('the sidebar becomes a menu that opens, and closes on navigation', async ({ page }) => {
    await signIn(page, ADMIN);
    await page.goto('/admin/overview');

    const toggle = page.getByRole('button', { name: /open the menu/i });
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');

    await toggle.click();
    await expect(page.getByRole('button', { name: /close the menu/i })).toHaveAttribute(
      'aria-expanded',
      'true',
    );

    const nav = page.getByRole('navigation', { name: 'Main' });
    await nav.getByRole('link', { name: 'Users' }).first().click();

    // Leaving the menu open over the page somebody just asked for is the most
    // irritating thing a mobile menu can do.
    await expect(page.getByRole('heading', { name: 'Users' })).toBeVisible();
    await expect(page.getByRole('button', { name: /open the menu/i })).toHaveAttribute(
      'aria-expanded',
      'false',
    );

    await signOut(page);
  });
});
