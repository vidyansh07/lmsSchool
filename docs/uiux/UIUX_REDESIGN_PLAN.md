# UI/UX redesign + performance plan

No new business functionality. No backend rewrites except where a specific
frontend-performance problem genuinely requires one. Preserve every route,
API contract, permission, and workflow. This document tracks phases the same
way `docs/erp/IMPLEMENTATION_PLAN.md` did for the ERP build — each phase ends
with a deploy to staging and a verified row below.

## Starting point (audit, 2026-09-18)

The frontend (`frontend/`, Next.js 16 App Router, ~95 `page.tsx` files) is
already unusually disciplined for a "before" state:

- A real v2 design-token system in `app/globals.css` (oklch colors, a
  documented type scale, 6 dashboard-tile accent trios, semantic
  success/warning/error/info, a 6-keyframe motion vocabulary,
  `prefers-reduced-motion` handled globally) — proven by
  `tests/unit/theme-contrast.test.ts`, which parses the file and asserts
  every real fg/bg pair clears WCAG AA.
- `lucide-react` only, no second icon system, no emoji-as-icon.
- A mature `components/ui/` primitive set (25 files) with no duplicated
  modal/table/dropdown implementations found.
- A single, well-documented app shell (`components/app-shell.tsx` +
  `components/navigation.ts`) with capability-driven nav and a real mobile
  drawer (focus trap, Escape, backdrop).
- No React Query/SWR — a deliberate custom `useApi`/`useList` layer, already
  server-paginated everywhere and AbortController-cancelled (Phase 22 of the
  ERP build). No obvious duplicate-fetch pattern in the pages sampled.
- No global store, no heavy dependencies, 22 total deps — a lean bundle.
- `motion` (framer-motion) plus the CSS keyframe vocabulary — not competing
  systems.
- Accessibility already spot-checked in 100 unit test files.

**Real gaps found, not assumed:**

1. **No charting library anywhere.** Zero line/bar/donut/area/funnel charts
   in the entire app — every dashboard and report screen is numbers and
   tables only. The 5 `--color-chart-N` tokens already defined in
   `globals.css` are used nowhere. This is the single biggest, most visible
   gap and where a redesign will read as genuinely new rather than polish.
2. **No collapsed/icon-only sidebar state.** The shell is binary — full
   sidebar or full mobile drawer. The brief's 250–280px expanded /
   72–84px collapsed ask is real, unbuilt work.
3. **Loading states are inconsistent.** Only 7 files use `<Skeleton>` and 2
   use `<Spinner>` across ~95 pages.
4. **Three back-compat color aliases** (`--color-blue/green/pink`, aliasing
   `sky/emerald/fuchsia`) are still referenced by `app/admin/activity`,
   `app/admin/students`, `app/admissions` — a small, already-identified
   cleanup the token file itself flags.
5. **Not yet audited** (each gets its own phase's own first step, not
   assumed): forms UX quality, table implementation detail, per-page
   responsive behavior at 375/768/1024px, `AuthProvider`'s render width, and
   a systematic `'use client'` necessity check (6 files flagged as possibly
   unnecessary, not confirmed).

**Chart library decision:** Recharts. Composable React/SVG components (themes
cleanly via the existing CSS custom properties, no canvas layer to fight),
reasonably tree-shakeable, the standard choice for this exact shape of work,
and it keeps the existing "SVG, not a second rendering system" philosophy
this codebase already applies to its hand-rolled sparklines. Compact KPI
sparklines and gauge/bullet-style target visuals stay hand-rolled SVG/CSS
(extending the two existing sparkline components) rather than pulling
Recharts into every tile — matching this codebase's own stated bias against
dependencies that "ship two hundred things to upgrade forever."

## Phases

| Phase | Name | Depends on | Delivers |
| --- | --- | --- | --- |
| R1 | Foundation audit + token cleanup | — | Finish the audits the first pass didn't reach (forms, tables, responsive, `AuthProvider`, `'use client'` sweep); remove the 3 back-compat color aliases; no visual change beyond that |
| R2 | Charting system | R1 | Recharts integrated, themed to `--color-chart-N` and the accent trios; line/area/bar/donut/radial components in `components/ui/charts/`; applied first to the admin dashboard |
| R3 | App shell + navigation | R1 | Collapsed/icon-only sidebar (72–84px) with tooltips, auto-collapse at tablet width, navbar polish |
| R4 | Dashboard redesign | R2, R3 | Admin/manager/counsellor/trainer/student dashboards rebuilt as the visual reference screen: KPI cards (metric/period/change/trend/sparkline), real charts, compact secondary info |
| R5 | Loading/error/empty states | R1 | Skeletons matching real layouts rolled out broadly; empty states get an explanation + action; error states confirmed/standardized as local-retry, never full-page replacement |
| R6 | Tables | R1 | Density, sticky headers, row/bulk actions standardized across the largest tables; server-pagination discipline confirmed everywhere |
| R7 | Forms | R1 | Grouping, validation timing, progressive disclosure standardized across the most complex forms |
| R8 | Micro-interactions + motion coverage | R2–R7 | Existing hover/press/transition vocabulary applied consistently to every interactive surface that doesn't yet use it |
| R9 | Responsive pass | R4–R7 | Per-page fixes at 375/768/1024/1440, especially dense table/dashboard/chart screens |
| R10 | Accessibility pass | R2–R9 | Skip link, heading hierarchy, remaining aria gaps, keyboard nav through drawers/modals/comboboxes |
| R11 | Network + render performance | R1 | The broader duplicate-fetch sweep the first audit pass couldn't finish, `AuthProvider` render-width fix if needed, the `'use client'` sweep, double-submission protection audit, bundle check |
| R12 | Visual + performance QA, docs | all | Cross-page consistency sweep, `docs/uiux/UI_UX_PERFORMANCE_NOTES.md` (practical notes, not a system), final verification |

## R4 dashboard route map

Read-only mapping, done before any code changed for this phase, per its own
"map the five real dashboards first" instruction. Resolved by evidence, not
assumption: for each role, `components/navigation.ts` was read for which
route its own "Dashboard"/"Home"-labelled nav link actually points at
(`isVisible()`'s capability/role gate applied by hand for each role), cross-
checked against `docs/erp/USER_JOURNEYS.md`'s own "Dashboards — loading
contract" table (§6/§67) and the page/`lib/*.ts` code itself.

| Role | Real landing route | Evidence |
| --- | --- | --- |
| Admin | `app/admin/overview/page.tsx` | `ADMIN_NAV`'s first group: `{ href: '/admin/overview', label: 'Overview', capability: reportViewAny }` — the only dashboard-shaped link an admin/superadmin sees first. Already has a real chart (Phase R2's attendance trend) — not touched further here beyond what R2 already built. |
| Student | `app/dashboard/page.tsx` (`StudentView` branch) | `STUDENT_NAV`: `{ href: '/dashboard', label: 'Dashboard', roles: ['student'] }` — the only "Dashboard" link a student's nav has. Calls `getStudentDashboard()` → `GET /api/v1/dashboard/student/`. Already rebuilt by an earlier hand ("only `StudentView` was rebuilt" per the file's own top docstring); this phase adds the one chart it lacked. |
| Trainer | `app/dashboard/page.tsx` (`TrainerView` branch) — **not** `/teaching/today` | `STAFF_NAV`'s first group: `{ href: '/dashboard', label: 'Dashboard', roles: ['trainer'] }` is the *only* item in the whole nav config labelled "Dashboard" for the trainer role. `/teaching/today` is a real, heavily-built screen (722 lines) but its own nav entry is labelled **"Today"**, sits under the separate "Teaching" group, and its page is a session/attendance/DSR work tool (`listTodaySessions`, `getRegister`, `markAttendance`, `startDsr`/`updateDsr`) — a daily-class workspace, not a KPI dashboard, and it fetches none of `getTrainerDashboard()`'s data. `docs/erp/USER_JOURNEYS.md`'s own §67 table documents the trainer's loading contract as `/teaching/today` → `GET /dashboards/trainer/`, which matches **neither** today's nav wiring **nor** the actual endpoint the code calls: `app/dashboard/page.tsx` calls `getTrainerDashboard()` (`lib/batches.ts`), which hits `GET /api/v1/dashboard/trainer/` (singular "dashboard", not the doc's plural "dashboards"). That table is stale documentation from the earlier ERP build, not a second real route — resolved here by what the shipped nav and code actually do, per this phase's own instruction. `/teaching/today` is correctly untouched by this phase; `TrainerView` in `app/dashboard/page.tsx` is where its chart was added. |
| Counsellor | `app/admissions/dashboard/page.tsx` | `STAFF_NAV`: `{ href: '/admissions/dashboard', label: 'Dashboard', roles: ['counsellor'], capability: enrolmentCreate }`; also linked from `ADMIN_NAV` as "Admissions pipeline" for admin/superadmin visibility. Confirms the pre-check's assumption. |
| Manager | **`app/manage/page.tsx` — newly built this phase**, alongside the pre-existing shared `/admin/overview` | Corrected after review: `STAFF_NAV`'s first group *does* already have an item visible to a manager — `{ href: '/admin/overview', label: 'Overview', capability: reportViewAny }` carries no `roles` restriction, and `isVisible()` (`components/navigation.ts`) checks `user?.capabilities.includes(item.capability)` before ever consulting `roles`, so any role holding `report.view_any` sees it regardless of role. A manager does: `_MANAGER_CAPABILITIES` (`backend/apps/accounts/roles.py`) explicitly includes `Capability.REPORT_VIEW_ANY`, and `backend/apps/reporting/access.py:162-163` says outright that "a branch-scoped manager *holds* `report.view_any`." So a manager already saw "Overview" pointing at `/admin/overview` before this phase — the earlier claim that no first-group item is visible to a manager was wrong, confirmed by hand-applying `isVisible()` to that item with a manager's actual capability set. That page's own data isn't leaked to a manager either: `AdminDashboardView.get()` gates on `access.can_read_everything(user)` (`= has_capability(user, REPORT_VIEW_ANY)`, true for a manager), and `dashboards.admin_dashboard()` builds every figure from `access.scope_for(user)` / `access.visible_batches(user)` / `access.visible_enrollments(user)` / `trainers_access.visible_trainers(user)` — all branch-bounded via `is_unbounded`, per `scope_for`'s own comment. So a manager opening `/admin/overview` before this phase already got a real, correctly branch-scoped dashboard carrying Phase R2's attendance chart, not a blank or forbidden screen; "Batch review" and "Trainer review" were not their only two real entry points. This doesn't make `app/manage/page.tsx` redundant — it's a distinct route (`/manage`, not `/admin/overview`) gated on the separate `performance.view_any` capability, and turning it into a real dashboard is still genuine new work: `/manage` itself was `redirect('/manage/batches')` with no content of its own, and `getManagerDashboard()` (`lib/manage.ts`, `GET /api/v1/dashboards/manager/`) had zero call sites anywhere in the app — `components/manage/attention-strip.tsx` calls the same endpoint through `useApi` directly, not through the named function, so the function itself was genuinely dead code until this phase's new `app/manage/page.tsx` became its first caller. What was wrong is only the premise that a manager had *no* real, chart-bearing landing page before this phase; they did, shared with admin at `/admin/overview` — this phase adds a manager-specific one at `/manage` beside it, not in place of a blank. |

Five files this phase actually touched (for R9/R10 to know precisely):
`app/dashboard/page.tsx` (both branches share this file — `TrainerView` got
a new chart; `StudentView`'s own chart lives in the panel it already
composed, `components/student/standing-panel.tsx`), `app/admissions/
dashboard/page.tsx`, and `app/manage/page.tsx` (new, replacing the bare
redirect). `app/admin/overview/page.tsx` needed no change — R2 already gave
it a chart. `app/manage/batches/page.tsx` and `app/manage/trainers/page.tsx`
were **not** touched — they keep `ManagerAttentionStrip` exactly as an
earlier ERP phase left it, on purpose, per the "drill all the way down, not
a dashboard of widgets" design intent quoted above.

## Phase log

(Filled in as each phase completes — same evidence bar as the ERP
programme: independently re-verified, not just the workflow's own report.)

### R6 — Tables (2026-09-18, commit `ab712d2`)

Migrated every remaining hand-rolled `<TableWrapper>`/`<Table>` large list
onto the shared `components/data-table.tsx` primitive: `admin/students`,
`admin/trainers`, `admin/users`, `admin/batches`, `admissions`,
`activities`, `admin/activity`, `teaching/work`, plus four tab components
(`communication/deliveries-tab`, `communication/templates-tab`,
`manage/trainer-work-tab`, `students/student-activities-tab`) — 12 files.
`DataTable` gained two backward-compatible props these migrations needed:
`loadingLabel` (sr-only loading copy) and `errorTitle` (passed to the
internal `ErrorState`), since several pages had existing tests asserting
specific loading/error copy the primitive previously hardcoded generically.
Correctly left alone as structurally incompatible: `teaching/register-editor`
(a deliberate P/A/L/E keyboard-chord model, documented in its own file, not
a generic table) and `admissions/batches` (an inline expand-to-roster
feature inserting extra `<tr>` rows between data rows).

Original triage undercounted by one file — `app/activities/page.tsx` was
missed from the initial grep and never categorized. Review caught this as a
major finding; the fix round migrated it too, confirmed by me directly
(`DataTable` import at line 33, `<DataTable` usage at line 488) and via the
final commit's file list.

One real, deliberately-unfixed gap review surfaced and I independently
confirmed: `app/admin/certificates/page.tsx` calls `listCertificates()` with
no `page`/`page_size` param and has no `Pagination` control at all, so
anything past the server's default first page is invisible with no way to
reach it. Confirmed via grep — only the import and two call sites, no
pagination machinery anywhere in the file. Left unfixed on purpose: it's a
pre-existing gap, not something this phase's table migration touched or
caused, and fixing it means guessing at intended default page size/UX
rather than a mechanical migration — flagging for a future phase instead of
guessing.

**Unresolved, worth recording plainly:** two pre-existing untracked files
(`docs/ER_DIAGRAM.mmd`, `docs/SCHEMA.md` — never git-tracked, first noted in
R3, consistently excluded from every phase's commits since) were flagged
again by this phase's review as a false-positive "contamination" re-flag.
While checking that finding I found both files **physically gone from
disk** (`ls -la` → "No such file or directory" for both), directly
contradicting this phase's own Finalize commit message, which explicitly
states they "remain untracked and untouched." Since neither file was ever
git-tracked, there is no commit or reflog to recover them from, and I could
not find an explicit deletion step in this phase's own instructions or
prompts that would explain it. They are unrelated to the redesign's own
content (an ER diagram and schema doc, not app code), so this does not
block or compromise R6's actual work, but the discrepancy itself is real
and I'm not glossing over it: something deleted two files this phase's own
report claimed it left untouched, and I don't have a confirmed cause.

Independent verification: `tsc --noEmit` clean, `lint` clean,
`npx vitest run --maxWorkers=2` — 136 files / 1230 tests, all passed,
matching Finalize's own claim exactly. `npm run build` succeeded cleanly.

Live on staging: login and a sample of the 12 migrated table pages return
`200`, container logs clean. claude-in-chrome still not connected.

### R5 — Loading/error/empty states (2026-09-18, commit `bc94d22`)

The plan doc's own R5 row ("only 7/95 pages use Skeleton") was stale — a
raw-component-usage undercount. The real picture, confirmed before this
phase started: `components/states.tsx` already exports
`LoadingState`/`ErrorState`/`EmptyState`, and 79 of 95 pages already use at
least one, most of the rest by delegating to a child component or to
`components/data-table.tsx` (itself built on the same shared states). This
phase triaged the real 21-file gap and found **all 21 were genuine
non-gaps** — every one either delegates to a component that already handles
its own states, or is a static page with no async fetch at all. Sampled
~30 of the 79 existing `EmptyState` call sites and found real, specific
copy everywhere already, with genuine CTAs tied to real reachable actions
(e.g. "Register a student" → `/admissions/new`) — zero changes needed
there either. The one real, concrete finding: `app/admin/overview/page.tsx`
combined `adminDashboard()` and `attendanceTrend()` in one `Promise.all`, so
a trend-fetch failure replaced the *entire page* — including six
already-loaded KPI tiles and the metrics list — with a full-page error.
Fixed by splitting the trend into its own effect/state with an
independently-scoped `LoadingState`/`ErrorState` and its own retry, matching
the same pattern `useDashboardSection`/`ManagerOverview` already use
elsewhere in this app.

**Review caught something serious mid-run**, worth recording plainly: it
found the working tree contained an uncommitted, unrelated 555-insertion
rewrite of `app/globals.css` into a "gradients/glassmorphism/shimmer-rainbow"
visual overhaul that had nothing to do with this phase and directly
contradicted every design decision R1's own audit documented (restrained
tokens, no second visual system, light-only by deliberate choice). The
review correctly flagged it as a blocker rather than letting it ride along
with the legitimate fix, and the fix round discarded it entirely — the
final commit contains only the two legitimate files
(`app/admin/overview/page.tsx` + its test). I independently confirmed this
myself: `git status`/`git diff` in the worktree show nothing of that content
anywhere, not in the working tree, not in any commit, and a targeted grep
for its own hallmark keywords (`glassmorphism`, `shimmer-rainbow`,
`blob-morph`, `confetti-pop`, `spin-glow`) across the current
`globals.css` returns zero matches — the only "gradient" hits are a
pre-existing, unrelated `radial-gradient` in the spotlight-cursor effect
from 2026-09-08, long before this redesign started. Whether that content
originated from the other concurrent session this repo has running, or was
scope creep by an earlier draft of this same phase's own implementer, is
not fully resolved — but the actual safeguard (review reading the real
diff before commit, plus my own git-status habit before every push) caught
it cleanly either way, and nothing from it reached a commit or staging.

I also hit a real false alarm of my own during independent verification,
worth recording so it does not get mistaken for a regression later: my
first `npx vitest run` came back with 9 failed files / 11 failed tests, all
`[vitest-pool-runner]: Timeout waiting for worker to respond` — worker-pool
resource contention (this machine had several unrelated heavy processes
running), not a real regression. A second run with `--maxWorkers=2` came
back clean: 130 files / 1197 tests, exactly matching Finalize's own claim.
`tsc --noEmit`, `lint`, and `npm run build` all clean on my own independent
run too.

Live on staging: login and `/admin/overview` both return `200`, container
logs clean. claude-in-chrome still not connected.

### R4 — Dashboard redesign (2026-09-18, commit `c7a33b2`)

The biggest scope so far: five dashboard screens, one of them (manager,
`app/manage/page.tsx`) genuinely built rather than redesigned, since
`getManagerDashboard()` — a real, working endpoint from an earlier ERP phase
— had zero call sites anywhere in the app before this phase. Review found
one real **major**: the route map's own reasoning for why the manager page
was needed was factually wrong — a manager actually already holds
`report.view_any` (`_MANAGER_CAPABILITIES` in
`backend/apps/accounts/roles.py`) and so already saw `/admin/overview` in
`STAFF_NAV` (that nav item carries a capability gate with no `roles`
restriction), and that page's own data is correctly branch-scoped for a
manager too (`admin_dashboard()` builds every figure from
`access.visible_batches`/`visible_enrollments`, not an unbounded query). The
fix didn't just patch the doc — it re-derived the whole evidence chain and
concluded, correctly, that the underlying work (a manager-specific `/manage`
overview, a distinct route gated on the separate `performance.view_any`
capability) was still legitimate and non-redundant; only the claim that a
manager had *no* dashboard-shaped page at all before this phase was wrong,
and the plan doc's route map now states the corrected version plainly.

I independently re-traced this myself rather than taking either side's word
for it: confirmed `REPORT_VIEW_ANY` is genuinely in `_MANAGER_CAPABILITIES`;
confirmed the `/admin/overview` `STAFF_NAV` entry has no `roles` array,
only a `capability` check; confirmed `admin_dashboard()` in
`apps/reporting/dashboards.py` scopes through `access.visible_batches(user)`
the same way any bounded caller's own query would, not an admin-only
unbounded path — the review's finding and its fix both check out. Read the
new `app/manage/page.tsx` in full myself: every field traced to a real
`ManagerDashboard` property (`data.batches.total`, `data.risk.critical`,
etc.), real loading/error states with a retry, `ManagerAttentionStrip`
reused rather than duplicated, `RequireAuth` correctly gated on
`performanceViewAny`. Ran `tsc --noEmit`, `lint`, the full suite (130 files
/ 1196 tests, matching exactly), and `npm run build` myself — all clean.

Live on staging: all five dashboard routes (`/admin/overview`, the new
`/manage`, `/admissions/dashboard`, and `/dashboard` for both trainer1 and
student1) return `200`, as do their underlying data endpoints. Fetched
`GET /api/v1/dashboards/manager/` directly and confirmed real, non-trivial
data (21 batches, 1,060 students, 213 critical/337 warning risk counts) —
the new bar chart has genuine data to render on first load, not an empty
edge case. Container logs clean. As with R2/R3, claude-in-chrome was still
not connected; the same caveat applies — this is strong indirect evidence
(code review, real branch-scoped data confirmed live, a green production
build), not the same as having looked at the rendered charts.

### R3 — App shell + navigation (2026-09-18, commit `bcb5f6f`)

The highest-blast-radius phase so far: `components/app-shell.tsx` is the one
shell every page in the app renders through. Collapsed sidebar at 80px
(middle of the 72-84px range), icon-only with right-side tooltips, toggle
persisted to `localStorage` (`grras.sidebar-collapsed`), defaults to
collapsed at `lg:` and expanded at `xl:` via a new `useMediaQuery` hook,
user's own choice always wins. Review found a real **major** (the collapsed
Brand/home link had no accessible name outside a non-production environment
— production builds would announce it as a blank link) and a real **minor**
(the AccountCard's collapsed name/role tooltip sat on a non-focusable
`<span>`, reachable by mouse only), both fixed. Independently re-verified
both fixes myself by reading the final code, not the report: confirmed the
`sr-only` "Grras LMS — Home" label on the collapsed Brand link is now
unconditional (not gated on `showEnvDot`/non-production), and confirmed
`tabIndex={0}` was added to the AccountCard avatar with a clear comment
explaining why it's the one non-interactive-element tooltip trigger in the
file. Confirmed the single most important thing for a phase like this:
`git diff` on `components/ui/sheet.tsx` between the R2 and R3 commits is
empty — untouched — and inside `app-shell.tsx`'s own `<Sheet>` block, the
nav is hardcoded to `collapsed={false}` and `Brand`/`AccountCard` are called
with no props (their existing defaults), so the mobile drawer is
byte-for-byte the same experience it always was regardless of the sidebar's
new state. Ran `tsc --noEmit`, `lint`, the full suite (130 files / 1180
tests, matching exactly), and `npm run build` myself — all clean.

Live on staging: clean container startup with no errors, login and a fetch
of `/admin/overview` and `/manage` (both render through the shell) both
return `200` with a real page shell, no server-side crash. As with R2, a
true visual check via claude-in-chrome was attempted again and the
extension was still not connected; the evidence above (diff-level
confirmation the drawer is untouched, both accessibility fixes read
directly in the final code, a green production build, and clean live
container logs) stands in for it, not equivalent to actually having looked
at the collapsed sidebar. Two unrelated untracked files
(`docs/ER_DIAGRAM.mmd`, `docs/SCHEMA.md`, apparently a schema-dump from
some other process, dated 17:23 today) were found sitting in the worktree
during this phase's own finalize step — correctly left uncommitted and
unrelated to this phase, still sitting there untracked; harmless, but worth
the user's own attention if they didn't mean to generate them.

### R2 — Charting system (2026-09-18, commits `c57c898`, `2cb02c2`)

Recharts 3.10.1 installed; themed chart wrappers (`LineChart`, `AreaChart`,
`BarChart`, `DonutChart`, hand-rolled `RadialProgress`) added under
`components/ui/charts/`, applied to `app/admin/overview/page.tsx`'s
attendance trend. Review found one real finding, rated minor and not
auto-fixed by the workflow: the new chart plots only `percent`, so the
`counted`/`attended` figures the old table showed disappeared from the page
entirely — not in the chart, not in its own accessible data table. I judged
this a genuine functionality-preservation regression (the brief is explicit:
"do not remove functionality simply because the UI is being redesigned")
regardless of the review's severity label, and fixed it myself rather than
carrying it forward: a "Show exact figures" toggle now swaps the chart for
the original table on demand, with its own test
(`admin-overview-page.test.tsx`) proving both the toggle and the real
counted/attended values appear.

Independently re-verified: read `chart-colors.ts` and confirmed every color
is a `var(--color-*)` reference, zero hardcoded hex anywhere in the
directory (grepped myself); confirmed every wrapper imports the same
`useReducedMotion` hook `Sparkline`/`StatCard` already use, not a second
mechanism; confirmed `chart-data-table.tsx` is a real `sr-only` text
alternative present in the DOM for every chart; confirmed via `git diff`
that no other dashboard (manager/trainer/counsellor/student) was touched —
R4's scope, not this phase's. Ran `tsc --noEmit`, `lint`, the full frontend
suite (130 files / 1173 tests after my own fix's added test), and
`npm run build` myself — all clean, including the production build that
would surface any Recharts SSR/hydration-specific failure.

Live on staging: `GET /api/v1/reports/metrics/attendance-trend/?weeks=12`
returns real, non-trivial data (e.g. `{"week":"2026-06-22","counted":2057,
"attended":1251,"percent":60.82}`, dozens of weeks) — confirming the fixed
toggle has real numbers to show, not an edge case with nothing to display.
`docker compose logs frontend` shows a clean start with no runtime errors.
A true visual check was attempted via claude-in-chrome both before and after
deploying; the extension was not connected either time. Since this app's
pages are client-rendered behind `RequireAuth` (confirmed by fetching the
live page's raw HTML — the server shell has no visible content until client
hydration runs), a curl-based HTML fetch cannot substitute for an actual
screenshot here; the evidence above (component-code review, real API data,
clean container logs, a green production build with SSR checks, and a full
local test suite including my own new toggle test) is real but is not the
same as having looked at the rendered page. Worth a manual look next time
the browser extension is available, not treated as a blocker.

### R1 — Foundation audit + token cleanup (2026-09-18, commit `95e577b`)

Review found zero findings. Independently re-verified given this phase
touched two shared primitives (`components/ui/badge.tsx`,
`components/ui/motion/stat-card.tsx`): confirmed via `git show` on the prior
commit that the removed `--color-blue/green/pink` (+tint/soft) oklch values
were byte-for-byte identical to the `sky/emerald/fuchsia` values they
aliased — a genuine zero-visual-change rename, not just a claimed one;
confirmed the `StatAccent`/`variant` object *keys* (`blue`, `green`, `pink`)
were correctly left untouched since they are the components' public prop
values, only the internal Tailwind class strings changed; grepped the whole
`app/`/`components/` tree myself and found zero remaining
`bg-/text-/border-/fill-/ring-blue|green|pink` usage; ran `tsc --noEmit`,
`lint`, and the full frontend suite myself (128 files / 1153 tests, matching
pre-phase counts exactly). Deployed to staging and fetched the real compiled
CSS bundle (`/_next/static/chunks/3-z4-wxpb9kvl.css`) to confirm live: zero
old classes/tokens in the deployed bundle, the new classes present and
resolving through the correct custom properties
(`.text-emerald{color:var(--color-emerald)}`). The audit findings section
(forms/tables/responsive/AuthProvider/`'use client'` sweep) was spot-checked
against the cited files and is genuinely evidence-based, not filler.

## R1 follow-up audit findings

Read-only investigation (Part 1 of R1). No code was changed for any finding
in this section — each is a target for the phase named in parentheses, not
work done here. Every finding below is cited by file (and line, where a
single line matters); nothing here is inferred without reading the code.

### Forms

**`app/admin/students/create-student-dialog.tsx`** (145 lines) + the shared
`components/admissions/student-background-fields.tsx` it renders — the
student creation form (there is no separate "wizard" route; it is one dialog
with one nested progressive section):

- Grouping: reasonable. Identity fields (email/phone/name/city/qualification/
  fee/branch) sit in one `sm:grid-cols-2` grid, and the "who is registering"
  background section is visually separated as its own `<fieldset>` below it.
- Progressive disclosure: partial and real, but only for one sub-section.
  `StudentBackgroundFields` (lines 110–211) genuinely defers: it shows three
  radio cards first (College / Working / Not sure) and only reveals the
  matching two fields (college name + graduation year, or company + title)
  after a choice — `value.kind === 'college' ? (...) : null` /
  `value.kind === 'employer' ? (...) : null`. But the eight fields above it
  (email, phone, first/last name, city, qualification, fee, branch) are all
  shown at once with no staging — a flat form, not a wizard, despite the
  plan doc's working name for it. Not necessarily wrong for eight fields, but
  worth naming precisely since "wizard" implies steps that do not exist.
- Validation timing: on-submit only. `onSubmit` (line 46) calls
  `createStudent(...)` and populates `errors` from `fieldErrors(cause)` —
  the server's response. There is no client-side per-field validation on
  blur or on keystroke anywhere in this file; a required field left empty is
  only caught after a round trip. The `<input>`s render with plain
  `onChange` handlers and no `onBlur`.
- Required-field indication: present and correct. `Field` (see
  `components/ui/field.tsx`) renders a `*` for `required` props, but only
  `Email` and `First name` carry `required` in this file (line 81, 91) even
  though the backend presumably requires more (e.g. `last_name` is optional
  here per the UI, which may or may not match the server's own validation —
  not verified against the backend in this read-only pass).
- Error placement: good and consistent. `Field` wires `aria-describedby` to
  an error `<p>` directly under the input (see `components/ui/field.tsx`
  lines 43–54), so the message sits where a person is already looking and a
  screen reader announces it.

**`components/automation/rule-builder.tsx`** (453 lines) — the automation
rule builder, reached via `app/admin/automation/[id]/page.tsx`:

- Grouping: the strongest example in the app. Four `Card`s — Details,
  Conditions, Actions, Test — each a self-contained section a person can
  visit in any order (the file's own docstring, lines 3–12, explains this is
  deliberate: "not a modal wizard... a person moves back and forth between
  them"). The list screen's own "New rule" dialog (`app/admin/automation/
  page.tsx`, `NewRuleDialog`, lines 48–136) only asks for name + trigger
  before handing off here — genuine progressive disclosure at the
  screen-to-screen level, matching the file's own docstring claim.
- Validation timing: on-submit only, same as the student dialog — `save()`
  (line 137) surfaces failure through one page-level `Alert`, not per field.
- **Real inconsistency, not present elsewhere**: this builder has no
  field-level error state at all. Unlike every other form read in this
  audit (student dialog, `NewRuleDialog`, activity type dialog), the `Name`,
  `Trigger` and `Description` `Field`s here (lines 260–308) are never passed
  an `error` prop, and none of the three carries `required` either — a
  validation failure from the server surfaces only as the one generic
  `Alert variant="error"` banner at the top (line 247), not attached to the
  field that caused it. Worth standardizing in R7.

**`app/admin/activity-types/page.tsx`** (621 lines) — the activity type
editor, a single `Dialog` (`ActivityTypeDialog`, lines 144–460) with no
separate detail route (the file's own docstring, lines 3–9, says this is
deliberate: no version history to justify one):

- Grouping: present but shallow — related pairs share a `grid-cols-2` (not
  even Duration/Reminder and Weight/Risk get their own visual section
  headers the way `rule-builder.tsx`'s Cards do), and the two role-checkbox
  groups (`RoleCheckboxes`, lines 111–142) are the only visually distinct
  sub-sections.
- **Progressive disclosure: none. This is the one form in the audit that
  genuinely dumps every field on one screen**, exactly the pattern the task
  brief asked to check for. All ~15 fields (name, slug, description,
  category, two role-checkbox groups, visible-to-student switch, duration,
  reminder, form picker, requires-review switch, performance weight, risk
  effect, and — when editing — status) render unconditionally regardless of
  category or of each other's values, unlike `student-background-fields.tsx`
  in the same audit, which stages its fields behind a choice. The dialog
  compensates with `max-h-[85vh] overflow-y-auto` (line 196) so it scrolls
  rather than overflowing the viewport, but nothing is hidden until
  relevant — a real R7 target given its field count.
- Validation timing: on-submit only, same pattern as the rest — `submit()`
  (line 178) populates `errors` from the server's `fieldErrors(cause)`. One
  small, real exception: the Slug field auto-derives from Name as it is
  typed (`slugify(value)`, line 219) until the person edits Slug directly,
  which is live, on-keystroke behavior — but it is a convenience default,
  not validation.
- Required-field indication: Name, Slug and Category carry `required`
  (lines 209, 229, 253); the rest do not, which is plausible (most really
  are optional on this record) but not verified against the backend
  serializer in this read-only pass.
- Error placement: consistent with the rest of the app for `Field`-wrapped
  inputs. The two `RoleCheckboxes` groups are the one exception — they are
  plain `<div>`s, not `Field`s, so their errors are hand-rendered as a bare
  `<p className="text-xs text-destructive">` right after each group (lines
  279–281, 290–292) rather than through `aria-describedby` — visually
  identical to `Field`'s own error styling but not wired to the checkbox
  group's accessible name the way `Field` wires an `<input>`.
- **Responsive, file+line-cited**: lines 310 and 386 each use a bare
  `grid grid-cols-2 gap-4` for a field pair (Default duration / Reminder,
  and Performance weight / Risk effect) with no `sm:` prefix — unlike every
  other multi-column field grid found in this audit, which all collapse to
  one column below `sm:` (e.g. `create-student-dialog.tsx` line 80:
  `grid gap-4 sm:grid-cols-2`). At 375px, inside a dialog with `p-5` padding
  and no `max-w` override below `sm` (`components/ui/dialog.tsx`: base
  variant is `w-full` with a `max-w-md` cap), each of these two columns
  works out to roughly 140–150px — enough to render but visibly cramped for
  a labelled number input with a spinner, and inconsistent with the rest of
  the app's own convention. A real, narrow R7/R9 fix (add `sm:` before
  `grid-cols-2` at both lines), not a redesign.

### Tables

Read `components/data-table.tsx` (the shared primitive), `hooks/use-list.ts`
(the shared server-pagination hook), and all four named table
implementations.

- **Server-pagination discipline: confirmed everywhere, no exceptions
  found.** `hooks/use-list.ts` sends `page`/`page_size`/`ordering`/filters as
  query-string parameters on every request and holds only the current page's
  `results` in state (lines 32, 56); nothing slices a larger array
  client-side. All four target tables confirmed independently:
  - **Batch roster** — `app/manage/batches/[batchId]/students/page.tsx`
    (`BatchRoster`, lines 39–172): `useList` bound to `listBatchStudents`
    (`lib/manage.ts` lines 179–188), which calls
    `GET /api/v1/batches/{batchId}/students/${queryString(query)}` — a real
    server round trip per page.
  - **Students list** — `app/admin/students/page.tsx` (`StudentsTable`,
    lines 34–332): `useList(listStudents)`, same query-string pattern via
    `lib/people.ts`.
  - **Activities feed** — `app/admin/activity/page.tsx`
    (`ActivityReview`, lines 120–491): does not use `useList`/`useApi` (its
    own request-identity-keyed `useState`/`useEffect` pair, lines 172–212)
    but still sends `page`/`page_size: 25` plus every active filter to
    `getActivityFeed` (line 181) and only ever holds one page's
    `feed.results` — genuinely server-paginated, just a different (older,
    pre-`useList`) implementation of the same discipline.
  - **Deliveries** — `components/communication/deliveries-tab.tsx`
    (`DeliveriesTab`, lines 35–276): `useApi` against
    `` `/api/v1/deliveries/${queryString(filters)}` `` (line 61–63) with
    `page` in `filters` — same pattern.
  - A broader repo grep for `.map(` over a full unpaginated array in any
    table-shaped component (searched every `useApi<T[]>`/`useApi<Array...>`
    call site, since a non-paginated `useApi` fetching a whole collection is
    the shape a client-side-sliced list would take) found exactly three:
    `app/admin/roles/page.tsx`, `app/admin/policies/page.tsx` and
    `components/warnings-strip.tsx`. All three are legitimately bounded,
    non-growing collections (the platform's own finite role list, its finite
    policy catalog, and one staff member's own active warnings), not
    unbounded user/record lists — not a violation.
- **Row density / sticky headers: real, consistent gap found.** Only
  `components/data-table.tsx` (used by the batch roster, via `DataTable`)
  has the comfortable/compact density toggle (`toggleDensity`, lines
  182–188, persisted to `localStorage`) and roving-tabIndex keyboard row
  navigation. The other three target tables (students list, activities
  feed, deliveries) each hand-roll a plain `<Table>`/`<TableWrapper>`
  directly instead of using the shared `DataTable` component:
  - `app/admin/students/page.tsx` does replicate sticky headers by hand
    (`sticky top-0 z-10 bg-surface` repeated on every `<Th>`, lines
    163–183) but has no density toggle and no keyboard row navigation.
  - `app/admin/activity/page.tsx`'s feed table (lines 404–469) has neither
    sticky headers nor a density toggle — a plain `<TableWrapper><Table>`
    with no positioning classes on its `<Th>`s at all.
  - `components/communication/deliveries-tab.tsx`'s table (lines 198–262)
    is the same — no sticky header, no density toggle.
  - Net: of the four target tables, only one (batch roster) gets the
    density toggle, keyboard nav and sticky-header behavior `DataTable`
    provides; the other three each reimplement a subset by hand with
    varying completeness. A real R6 target: migrate the other three onto
    `DataTable`, or accept the inconsistency as intentional and document
    why (e.g. the activities feed mixes rich multi-line cells that
    `DataTable`'s column-render shape may not suit as cleanly — not
    evaluated here).
  - `TableWrapper`/`Table` (`components/ui/table.tsx`, lines 11–24) both
    apply regardless: the wrapper scrolls horizontally
    (`overflow-x-auto`) and the table itself has `min-w-[42rem]`, so a
    wide table's *own* scroll area moves sideways rather than the page —
    this holds for all four tables checked, including the two that skip
    `DataTable`.

### Responsive (375px / 768px)

Checked by reading Tailwind breakpoint classes closely across the main
dashboard (`app/dashboard/page.tsx`), the students table (the large-table
screen, `app/admin/students/page.tsx`) and the activity type editor (the
form screen, `app/admin/activity-types/page.tsx`), plus the shared shell,
table, dialog and button primitives those pages build on.

- **Dashboard** (`app/dashboard/page.tsx`): every stat/card grid found
  starts at `grid-cols-1` and only widens at `sm:`/`lg:`/`xl:` (lines 276,
  343, 381, 464, 485, 504, 538) — confirmed to stack cleanly to one column
  at 375px, with no bare (non-responsive) multi-column grid found in this
  file.
- **Students table / large-table screens generally**: at 375px, the
  students table (10 columns) does not fit and is not meant to —
  `TableWrapper`'s `overflow-x-auto` plus `Table`'s `min-w-[42rem]`
  (`components/ui/table.tsx` lines 11–24, comment: "a wide table never
  forces the whole page sideways on a phone") means the table scrolls
  *within its own bordered card*, not the page. This is confirmed
  deliberate, working behavior, not a bug — flagging it here only because
  the task asked to check for horizontal scroll at 375px specifically: it
  is present, by design, and contained.
- **Activity type dialog / form screens**: the one real, precise finding is
  the `grid-cols-2` (no `sm:`) at `app/admin/activity-types/page.tsx` lines
  310 and 386, already detailed above under Forms — cramped, not cut off,
  at 375px.
- **Touch targets**: checked because it is a common 375px failure mode.
  Not a real finding — `components/ui/button.tsx`'s `sm` and `md` sizes
  (lines 24–25) keep a compact *visible* box (`h-8`/`h-10`) but expand the
  actual *hit* area to 44px with a centred `before:h-11` pseudo-element,
  specifically so a toolbar of compact buttons (like the app shell's
  header icons, `components/app-shell.tsx` lines 343–353, at `size-9`
  visible) still meets the 44px guideline. Checked directly against the
  guideline rather than assumed; the app shell's own header buttons use
  this pattern and are fine at 375px.
- **768px**: the `sm:` breakpoint (640px in this Tailwind config, the
  default) is already crossed by 768px for every grid cited above, so
  every "single column at 375" case above is multi-column and clear of the
  phone-only cases by 768px. No 768px-specific breakage found in the three
  screens read.
- Not independently loaded in a browser at either width for this pass —
  done by close reading of the breakpoint classes and the primitives they
  compose, per the task's own stated alternative to a live dev-server
  check. A later phase (R9) that touches these screens should still do a
  live check before calling them done, since a class-reading pass cannot
  catch a runtime-only issue (e.g. content that overflows because of
  actual data length, not a missing breakpoint class).

### `AuthProvider` (`components/auth-provider.tsx`)

**Already fine — no fix needed, and no fix invented.** Read in full (114
lines). There is no background session-refresh tick of any kind: the only
places `setUser`/`setError`/`setIsLoading` are called are (1) the one
`useEffect` that runs once on mount (lines 61–83, empty dependency array)
to ask `GET` "who am I" once, and (2) `refresh()`/`signOut()`, both only
ever invoked by a consumer's own explicit action, never on a timer or
interval. There is no `setInterval`, no polling, nothing in this file fires
on its own after mount. The context value is correctly memoized:
`useMemo(() => ({...}), [user, isLoading, error, load, signOut])` (lines
93–104) — `load` and `signOut` are themselves `useCallback`s with empty
dependency arrays (lines 44, 85), so the memo's dependency list is stable
apart from the three pieces of state that are meant to cause a re-render
when they actually change. Every consumer of `useAuth()` re-renders only
when `user`, `isLoading` or `error` genuinely change (mount-resolution,
sign-out, or an explicit `refresh()` call) — not on some unrelated tick.
This matches the plan doc's own audit note (line 27: "no obvious
duplicate-fetch pattern") and closes out the "AuthProvider's render width"
open question from the starting-point audit with a plain answer: it was
never a problem.

### `'use client'` sweep

For each of the six files the plan doc flagged, plus a full-repo grep for
every other `'use client'` `page.tsx` with no interactive hook at its own
top level (methodology: grepped every `app/**/page.tsx` starting with
`'use client'` for `useState|useEffect|useCallback|useMemo|useReducer|
useRef|onClick|onChange|onSubmit|useAuth|useApi|useList|use(` at the file's
own level, i.e. not inside a component it merely renders):

| File | Verdict | Why |
| --- | --- | --- |
| `app/admin/communication/page.tsx` | **Genuinely needs client** | `CommunicationCenter` (the file's own component, not a child) calls `useAuth()` directly (line 18) to gate which `TabsTrigger`s render (`mayViewDeliveries`/`maySend`, lines 19–21) — the tab set itself is capability-dependent, not just what is inside a tab. |
| `app/admin/communication/templates/[key]/page.tsx` | **Could plausibly become server-rendered** | Zero hooks of its own — the entire body is `const { key } = use(params); return <RequireAuth ...><TemplateBuilder .../></RequireAuth>`. `RequireAuth` and `TemplateBuilder` are already independently `'use client'`, so this file's own `'use client'` does nothing but force the file itself to also be treated as client; a Server Component `page.tsx` that `await`s `params` (Next 15+ async params, no `use()` needed) and renders the same already-client children would be equivalent. Not converted here per the brief. |
| `app/calendar/page.tsx` | **Could plausibly become server-rendered** | Zero hooks anywhere in the file (20 lines total) — `export default function CalendarPage()` renders static JSX plus `<RequireAuth><CalendarView /></RequireAuth>`, both already `'use client'` themselves. The only broader grep hit with genuinely *no* hooks at all, not even `use(params)`. |
| `app/my-fees/page.tsx` | **Genuinely needs client** | `MyFees` (the file's own component) calls the `useStudentFees` hook directly (line 14: `useStudentFees(getMyFees, [])`) — a hook call at this file's own level, not merely rendering an already-client child. |
| `app/profile/page.tsx` | **Genuinely needs client** | `ProfileContent` (the file's own component) calls `useAuth()` directly (line 13) and branches which form renders on `user?.profile_type` (lines 36–37) — the page's own structure, not just a child's, depends on client-fetched session state. |
| `app/page.tsx` | **Genuinely needs client** | `HomePage` calls `useAuth()` directly (line 35) and the entire page body — signed-out marketing content vs. a per-role signed-in dashboard-links grid — depends on it. Also structurally hard to make server-rendered without a broader change: the file's own comment on `AuthProvider` (line 6 of that file) notes the session lives in an HttpOnly cookie "the browser cannot read", i.e. today's session check is a client-side fetch to `/api/v1/me`-equivalent, not something this page could read server-side without a different auth-reading mechanism — out of scope for a rename/no-behavior-change phase. |

**Two more found by the broader grep, same shape as the
`templates/[key]` case** (thin pass-through detail pages whose only
"hook" is `use(params)`, wrapping already-`'use client'` children) —
**could plausibly become server-rendered**, same reasoning:

- `app/admin/automation/[id]/page.tsx` (20 lines: `use(params)` →
  `<RequireAuth><RuleBuilder id={id} /></RequireAuth>`)
- `app/admin/forms/[slug]/page.tsx` (20 lines: same shape, `FormDetail`)
- `app/admin/roles/[slug]/page.tsx` (19 lines: same shape, `RoleBuilder`)

No other `'use client'` `page.tsx` in the repo was found with zero
interactive hooks at its own level beyond the ones listed above — every
other page either calls a hook directly (most commonly `useState`/
`useEffect` for its own local fetch-and-render logic, predating `useList`/
`useApi` in some older screens) or reads `useSearchParams`/`useRouter`
itself. None of those were converted in this phase; this table is a
findings list for a later phase (the brief's own instruction, since a
wrong conversion here would itself be an architecture change beyond
polish).
