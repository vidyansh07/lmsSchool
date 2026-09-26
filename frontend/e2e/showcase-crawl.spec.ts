import { expect, test, type Page } from '@playwright/test';

import { signIn, signOut } from './helpers';

/**
 * The same walk as `crawl.spec.ts`, over the showcase people instead of the
 * demo ones — and one route deeper.
 *
 * Two things this covers that the demo crawl cannot.
 *
 * **Real quantities.** The `@demo.grras.invalid` accounts live in a handful of
 * hand-made rows; the showcase set (`apps.common.showcase`, ten stages on top
 * of a staging clone) gives the same screens a hundred students, two centres,
 * years of fee history and twenty-five thousand activity entries. A screen that
 * renders a thin fixture and falls over on a real page of rows — a total that
 * overflows, a chart with no room for its labels, a date nobody parsed — is
 * only visible against this data.
 *
 * **Detail screens.** The nav walk never opens one: navigation offers lists,
 * and a batch, a student, a course, an activity or a thread is reachable only
 * by following a row. So for every list screen a role's nav offers, this also
 * follows that list's first row into its own screen and asserts the same
 * things there — which is where an id-driven fetch, a tab that depends on the
 * row's state, or a detail-only chart first gets looked at.
 *
 * Driven by `E2E_SHOWCASE_PASSWORD` (falling back to `E2E_DEMO_PASSWORD`, which
 * is the same password in the showcase stack) so this file is committable and
 * skips itself where the seeded people do not exist:
 *
 *   E2E_BASE_URL=http://localhost:3123 \
 *   E2E_SHOWCASE_PASSWORD='…' npx playwright test e2e/showcase-crawl.spec.ts
 *
 * The assertions are `crawl.spec.ts`'s, deliberately repeated here rather than
 * imported from it: importing a spec file would register its six tests a second
 * time inside this one. Change an assertion in one, change it in both.
 */
const SHOWCASE_PASSWORD = process.env.E2E_SHOWCASE_PASSWORD ?? process.env.E2E_DEMO_PASSWORD ?? '';

test.skip(!SHOWCASE_PASSWORD, 'E2E_SHOWCASE_PASSWORD is not set; showcase-data tests are skipped.');

/**
 * A superadmin's nav offers about fifty routes, and each now costs a detail
 * screen as well — six minutes of real page loads, against the suite's 60s
 * default. The walk is a crawl, not a unit test; it is allowed to take the time
 * the screens take.
 */
test.describe.configure({ timeout: 600_000 });

interface CrawlRole {
  name: string;
  email: string;
}

/**
 * The showcase cast, one per role, plus a second centre's manager — the one
 * place where "every centre" and "my centre only" differ on screens that look
 * identical otherwise (`manager@grras.com` is Jaipur, `manager.pune@grras.com`
 * is Pune), which is exactly where a scoping mistake shows up as an empty list
 * rather than an error.
 */
const ROLES: CrawlRole[] = [
  { name: 'owner (superadmin)', email: 'owner@grras.com' },
  { name: 'admin (Jaipur)', email: 'admin@grras.com' },
  { name: 'manager (Jaipur)', email: 'manager@grras.com' },
  { name: 'manager (Pune)', email: 'manager.pune@grras.com' },
  { name: 'counsellor (Jaipur)', email: 'counsellor@grras.com' },
  { name: 'trainer (Jaipur)', email: 'trainer@grras.com' },
  { name: 'student (Aarav Mehta)', email: 'student@grras.com' },
];

/** Left uncaught, these are exactly what the crawl is for: a number that failed
 *  to compute, a date that failed to parse, a value nobody null-guarded before
 *  interpolating it into text. */
const LEAKED_PLACEHOLDER = /\bundefined\b|\bNaN\b|\bInvalid Date\b/;

/** API failures the crawl treats as real breakage — everything except the
 *  handful of statuses a screen may legitimately see on its own probes (an
 *  optional lookup that isn't there yet, a capability check that asks and is
 *  refused, a background poll racing a sign-out). */
function isUnexpectedFailure(status: number): boolean {
  return status >= 400 && ![401, 403, 404, 429].includes(status);
}

/** Chromium writes a console error of its own for every subresource that came
 *  back non-2xx. A note about a status {@link isUnexpectedFailure} accepts is
 *  not a defect — see the longer account in `crawl.spec.ts`. */
const RESOURCE_STATUS = /^Failed to load resource: the server responded with a status of (\d{3})\b/;

function isAppConsoleError(text: string): boolean {
  const status = RESOURCE_STATUS.exec(text)?.[1];
  return status === undefined || isUnexpectedFailure(Number(status));
}

/** Every same-origin path the signed-in caller's own rendered nav links to, in
 *  document order, de-duplicated. Read from the rendered `<nav aria-label=
 *  "Main">` rather than re-derived from `components/navigation.ts`: the DOM
 *  already is that per-role filtering's output, and a second hand-maintained
 *  copy of it could drift without either ever failing. */
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

/**
 * The first row of the list currently on screen, as a path — or `null` where
 * this route is not a list.
 *
 * "A row of this list" means a link inside `<main>` to a path below the list's
 * own: `/batches` → `/batches/<id>`, `/courses` → `/courses/<id>`. That shape
 * is what every list screen's row link has, and reading it from the rendered
 * table means this needs no per-screen table of id columns and no seeded ids
 * hard-coded here — it follows whatever the first row happens to be, which is
 * also the row a person sees first.
 *
 * Deliberately narrow: a link to a *different* section (a batch's course, a
 * student's fee ledger) is that section's own list to crawl, and following
 * those too would walk the whole graph rather than one row deep.
 */
async function firstRowLink(page: Page, route: string): Promise<string | null> {
  // '/' is a prefix of everything; the landing page is not a list anyway.
  if (route === '/') return null;
  const prefix = `${route}/`;
  const hrefs = await page
    .getByRole('main')
    .getByRole('link')
    .evaluateAll((links) =>
      links
        .map((el) => el.getAttribute('href'))
        .filter((href): href is string => Boolean(href)),
    );
  const row = hrefs.find(
    (href) => href.startsWith(prefix) && href.length > prefix.length && !href.includes('?'),
  );
  return row ?? null;
}

for (const role of ROLES) {
  test(`showcase crawl: ${role.name} — every route, and one row deep, renders cleanly`, async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    const networkFailures: string[] = [];

    page.on('console', (message) => {
      if (message.type() === 'error' && isAppConsoleError(message.text())) {
        consoleErrors.push(message.text());
      }
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

    /** One route, asserted the way `crawl.spec.ts` asserts one: it answered,
     *  it rendered, it leaked nothing, it logged nothing, nothing it asked for
     *  failed beyond an expected probe. Answers the paths its rows lead to. */
    async function visit(route: string): Promise<string | null> {
      consoleErrors.length = 0;
      networkFailures.length = 0;

      const response = await page.goto(route);

      // The broken-link half of this test: a nav entry whose route the app
      // router no longer has renders Next.js's own not-found page at a real
      // 404 status.
      expect(response?.status(), `${route} should not 404`).not.toBe(404);

      await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {
        // A screen that polls (notifications, a live dashboard tile) never
        // truly goes idle — the checks below do not depend on it having.
      });

      const bodyText = (await page.locator('body').innerText()).trim();
      expect(
        bodyText.length,
        `${route} rendered visible content, not a blank shell`,
      ).toBeGreaterThan(40);
      expect(bodyText, `${route} leaked a placeholder value to the screen`).not.toMatch(
        LEAKED_PLACEHOLDER,
      );

      expect(consoleErrors, `${route} had an uncaught console error`).toEqual([]);
      expect(networkFailures, `${route} had a request fail beyond an expected probe`).toEqual([]);

      return firstRowLink(page, route);
    }

    await signIn(page, role.email, SHOWCASE_PASSWORD);

    const routes = await navRoutes(page);
    expect(routes.length, `${role.name}'s nav offers at least one route`).toBeGreaterThan(0);

    const detailRoutes: string[] = [];
    for (const route of routes) {
      const row = await visit(route);
      if (row && !routes.includes(row)) detailRoutes.push(row);
    }

    // The screens navigation cannot reach. Visited after the nav walk rather
    // than in the middle of it so that a detail screen's breakage is reported
    // as its own route, in a list that says plainly which rows were followed.
    for (const detail of [...new Set(detailRoutes)]) {
      await visit(detail);
    }

    await signOut(page);
  });
}
