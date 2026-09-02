import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end tests run against a real frontend and a real backend.
 *
 * `E2E_BASE_URL` points at an already-running stack (docker compose, or CI's
 * compose job). When it is not set, Playwright starts the Next.js dev server
 * itself and the backend is expected on `NEXT_PUBLIC_API_BASE_URL`.
 */
const baseURL = process.env.E2E_BASE_URL ?? 'http://localhost:3000';

/**
 * §15.2's mandatory journey.
 *
 * Separate from the suite because it signs in about a dozen times, and by the
 * time it runs inside the whole suite the credential rate limit is exhausted —
 * so it spends twelve minutes waiting out throttles that exist only because of
 * the tests before it. Run alone it takes about two, and the limit stays where
 * production needs it. It also changes its people's world (marks a register,
 * finishes a course), which the other specs read.
 *
 *   E2E_RELEASE_JOURNEY=1 npx playwright test --project=release
 */
const releaseProject = {
  name: 'release',
  testMatch: /release-journey\.spec\.ts/,
  use: { ...devices['Desktop Chrome'] },
  timeout: 900_000,
};

export default defineConfig({
  testDir: './e2e',
  // 60s, not 30s. Several of these are multi-step journeys with three or four
  // sign-ins, and they run against a production build behind TLS as well as
  // against the development server — the first is slower, and a timeout tuned
  // to the second failed thirteen tests on staging that pass everywhere else.
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    // The staging stack terminates TLS with a certificate Caddy issued itself,
    // because hardened settings mark the session cookie Secure and a browser on
    // plain http will not store it. The certificate authority is not what these
    // tests are checking.
    ignoreHTTPSErrors: true,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
      // The release journey is its own gate — see the `release` project below.
      testIgnore: /release-journey\.spec\.ts/,
    },
    // §15.2's mandatory journey. Included only when asked for:
    //
    //   E2E_RELEASE_JOURNEY=1 npx playwright test --project=release
    //
    // Playwright runs every configured project by default, so leaving it in the
    // list would put it back in the suite it was separated out of.
    ...(process.env.E2E_RELEASE_JOURNEY ? [releaseProject] : []),
  ],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: 'npm run dev',
        url: baseURL,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
