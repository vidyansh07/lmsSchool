import { expect, test, type Page } from '@playwright/test';

import { signIn, signOut } from './helpers';

/**
 * The crawl (Phase 25, `IMPLEMENTATION_PLAN.md` row 25): for each of the
 * six roles `apps.accounts.roles.UserRole` names (superadmin, admin,
 * manager, trainer, counsellor, student — `docs/erp/PERMISSION_CATALOG.md`'s
 * own six-row shape), sign in and visit every route that role's own
 * rendered navigation actually offers, and assert the screen is real: it
 * rendered, nothing leaked an `undefined`/`NaN`/`Invalid Date`, no
 * uncaught console error, no request failed beyond an expected pre-auth
 * probe.
 *
 * This reads the *rendered* `<nav aria-label="Main">` after each sign-in
 * rather than re-deriving `components/navigation.ts`'s per-role
 * `navFor`/`isVisible` capability filtering here — the rendered DOM already
 * is that filtering's output, and a second, hand-maintained copy of the
 * same logic could drift from the real one without either ever failing.
 *
 * Doubles as the broken-link test (`IMPLEMENTATION_PLAN.md` row 25's other
 * named gate): every `page.goto(route)` below asserts its own response was
 * not a 404, reusing this same walk rather than a second link-walker —
 * every internal nav link reachable by at least one of the six roles is
 * visited here, so a route removed from the app router while a nav entry
 * still points at it fails this test the same way a genuinely broken
 * screen would.
 *
 * A committed, reusable artifact for future phases, per the phase brief —
 * not a throwaway script: add a role or a nav entry, and this crawl covers
 * it on the next run with no changes needed here.
 */
const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? '';

test.skip(!DEMO_PASSWORD, 'E2E_DEMO_PASSWORD is not set; seeded-data tests are skipped.');

interface CrawlRole {
  name: string;
  email: string;
}

const ROLES: CrawlRole[] = [
  { name: 'superadmin', email: 'superadmin@demo.grras.invalid' },
  { name: 'admin', email: 'admin@demo.grras.invalid' },
  { name: 'manager', email: 'manager@demo.grras.invalid' },
  { name: 'trainer', email: 'trainer1@demo.grras.invalid' },
  { name: 'counsellor', email: 'counsellor@demo.grras.invalid' },
  { name: 'student', email: 'student1@demo.grras.invalid' },
];

/** Left uncaught, these are exactly what the phase brief asks the crawl to
 *  catch: a number that failed to compute, a date that failed to parse, a
 *  value nobody null-guarded before interpolating it into text. */
const LEAKED_PLACEHOLDER = /\bundefined\b|\bNaN\b|\bInvalid Date\b/;

/** API failures the crawl treats as real breakage — everything except the
 *  handful of statuses a screen may legitimately see on its own probes
 *  (an optional lookup that isn't there yet, a capability check that asks
 *  and is refused, a background poll racing a sign-out). */
function isUnexpectedFailure(status: number): boolean {
  return status >= 400 && ![401, 403, 404, 429].includes(status);
}

/** Every same-origin path the signed-in caller's own rendered nav links to,
 *  in document order, de-duplicated. */
async function navRoutes(page: Page): Promise<string[]> {
  const hrefs = await page
    .getByRole('navigation', { name: 'Main' })
    .getByRole('link')
    .evaluateAll((links) =>
      links
        .map((el) => el.getAttribute('href'))
        .filter((href): href is string => Boolean(href))
        .filter((href) => href.startsWith('/')),
    );
  return [...new Set(hrefs)];
}

for (const role of ROLES) {
  test(`crawl: ${role.name} — every nav-reachable route renders cleanly`, async ({ page }) => {
    const consoleErrors: string[] = [];
    const networkFailures: string[] = [];

    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    page.on('pageerror', (error) => {
      consoleErrors.push(error.message);
    });
    page.on('response', (response) => {
      if (!response.url().includes('/api/')) return;
      if (isUnexpectedFailure(response.status())) {
        networkFailures.push(`${response.status()} ${response.url()}`);
      }
    });

    await signIn(page, role.email);

    const routes = await navRoutes(page);
    expect(routes.length, `${role.name}'s nav offers at least one route`).toBeGreaterThan(0);

    for (const route of routes) {
      consoleErrors.length = 0;
      networkFailures.length = 0;

      const response = await page.goto(route);

      // The broken-link half of this test: a nav entry whose route the
      // app router no longer has renders Next.js's own not-found page at
      // a real 404 status (`smoke.spec.ts` proves that page's own shape
      // for an arbitrary unknown path; this is the same check, applied to
      // every route real navigation can reach instead of one made up).
      expect(response?.status(), `${route} should not 404`).not.toBe(404);

      await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {
        // A screen that polls (notifications, a live dashboard tile) never
        // truly goes idle — the checks below do not depend on it having.
      });

      const bodyText = (await page.locator('body').innerText()).trim();
      expect(bodyText.length, `${route} rendered visible content, not a blank shell`).toBeGreaterThan(
        40,
      );
      expect(bodyText, `${route} leaked a placeholder value to the screen`).not.toMatch(
        LEAKED_PLACEHOLDER,
      );

      expect(consoleErrors, `${route} had an uncaught console error`).toEqual([]);
      expect(networkFailures, `${route} had a request fail beyond an expected probe`).toEqual([]);
    }

    await signOut(page);
  });
}
