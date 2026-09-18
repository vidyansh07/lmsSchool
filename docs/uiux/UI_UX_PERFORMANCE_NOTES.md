# UI/UX redesign — notes

Practical notes on what the 12-phase redesign (R1–R12) actually changed, and
where things stand. Not a spec — see `UIUX_REDESIGN_PLAN.md`'s phase log for
the full evidence trail behind each of these.

## What changed, in plain language

**Visual system.** The token system (`app/globals.css`) was mostly already
good going in — real oklch colors, a type scale, dashboard accent trios,
semantic success/warning/error/info, and `prefers-reduced-motion` handled
globally. R1 removed three leftover back-compat color aliases
(`--color-blue/green/pink`) that duplicated `sky/emerald/fuchsia`. No new
color system, no dark mode added, no second visual language introduced — a
few uncommitted attempts at a "glassmorphism/gradient" rewrite showed up in
the working tree at various points (per R5/R9's phase log) and were
correctly discarded each time, not shipped.

**Charts.** The single biggest visible gap: there were no charts anywhere in
the app. R2 added Recharts-based line/area/bar/donut/radial components
under `components/ui/charts/`, themed to the existing `--color-chart-N`
tokens (not new colors). R4 used them to rebuild the five real
role dashboards (admin, manager, counsellor, trainer, student). Every chart
keeps a `sr-only` text/table alternative so the data isn't chart-only.

**Tables.** R6 migrated the large hand-rolled tables (students, trainers,
users, batches, admissions, activities, teaching work, a few tab
components — 12 files total) onto the shared `DataTable` primitive, which
gives them density toggle, sticky headers, and keyboard row navigation
consistently. Server-side pagination was already correct everywhere before
this phase started; R6 didn't have to fix any client-side-slicing bugs, just
inconsistent presentation.

**Forms.** R7 added on-blur validation to the two required fields on the
student-creation dialog, added field-level error state to the automation
rule builder (previously only a generic banner), and added progressive
disclosure (collapsible `<details>` sections) to the activity-type editor,
the one form in the app that genuinely dumped ~15 fields on one screen.

**Shell, motion, accessibility.** R3 added a collapsed/icon-only sidebar
(80px, tooltips, persisted choice). R8 found and fixed five real
missing-hover/focus-visible spots app-wide. R9 did a responsive sweep at
375/768/1024/1440px and fixed a handful of unprefixed `grid-cols-2`s. R10
confirmed heading hierarchy (h1→h2→h3, no skips) across all 43 page files,
fixed the skip link's focus target, and verified keyboard trap/Escape/
restore behavior in the shared dialog/sheet focus-trap hook.

**Performance.** R11 checked for duplicate fetches (found and left one
deliberate one alone), added busy/disabled guards to four unguarded
status-change actions, and converted two heavy page files
(`admin/batches/[batchId]`, `admin/courses/[courseId]`) to real Server
Components with the interactive part split into a client child — a
meaningfully bigger win than the two candidates originally flagged for
conversion, which turned out to be zero-benefit.

## Real numbers

**Bundle (from R11's own phase log, measured against a real build):**
- `.next/static/chunks` total: **3.9 MB**
- Largest chunk: Recharts, **415 KB**, confirmed still route-scoped to only
  the four chart-bearing dashboards (not loaded app-wide)
- Dependency count: **25 total** (10 runtime + 15 dev), up from 22 at the
  start of the redesign — the growth is accounted for entirely by Recharts
  and its own subtree, not scope creep

**Lighthouse (`chrome-devtools-axi lighthouse`), staging home page, desktop,
2026-09-19:**
- Accessibility: **100**
- Best Practices: **96**
- SEO: **63**
- Agentic Browsing: **92** (this tool's own category, not part of vanilla
  Lighthouse — its own `--help` text says it "runs an audit for
  accessibility, SEO, and best practices," and this fourth category is
  genuinely part of that run's output, confirmed directly)
- 48 audits passed, 3 failed
- Cumulative Layout Shift: **0.123** (displayValue from `report.json`'s
  `cumulative-layout-shift` audit — above the 0.1 "good" threshold, no
  pre-redesign baseline exists to say whether this changed)
- The 3 failing audits: two expected/deliberate (403s logged for an
  unauthenticated visitor probing session state; `noindex, nofollow` on a
  staging environment) and the CLS one above — no real accessibility or
  best-practices defect found.

This corrects an error made mid-phase: this phase's own Review stage
initially rejected these exact numbers as fabricated, on the reasoning that
"Agentic Browsing" isn't a real Lighthouse category and that Lighthouse's
CLI defaults to a Performance audit — both true of the standard Lighthouse
CLI, but not of `chrome-devtools-axi lighthouse` specifically, which really
does add that category and really does skip Performance (confirmed by
reading its own `--help` text and by re-running it independently and
getting the identical numbers back). The retraction that followed removed
real, reproducible data as a result. Re-verified independently after that
mistake was caught: ran `chrome-devtools-axi lighthouse` again from
scratch and got the exact same scores and CLS value reported the first
time. R11's bundle numbers above remain the only *other* measured
performance evidence for this redesign; this tool still cannot report
FCP/LCP/TBT/Speed Index/TTI/an overall Performance score, since it doesn't
run that category at all — that remains a genuine, real gap, not a
fabricated one.

## Known limitations

- **claude-in-chrome (the browser automation tool) was never available in
  any phase of this redesign.** A separate CLI, `chrome-devtools-axi`, was
  found partway through (R9) and does work for pages reachable without
  logging in — the public home page and `/login` — and was used for real
  screenshots (R9, R12) and the Lighthouse run above. Every authenticated
  screen (the dashboards, tables, forms, the collapsed sidebar in its
  logged-in context) still relied on close reading of the component code
  and Tailwind breakpoint classes, cross-checked against real API data and
  clean production builds, not on actually looking at rendered pixels,
  because scripting a login would require handling the staging demo
  password in a way this session's own standing rules forbid (never
  print/echo/type a secret into a logged tool call). This remains the
  single biggest gap in how thoroughly this redesign was actually
  verified.
- **Two small grid-cols fixes landed in this phase (R12):**
  `components/settings/recovery-codes-dialog.tsx` and
  `components/teaching/dsr-panel.tsx` both had an unprefixed
  `grid-cols-2` that didn't collapse to one column below `sm:`, unlike
  every other multi-column field grid in the app. Fixed to match the
  established `sm:grid-cols-2` convention.
- **Five trainer content-management screens** (`app/teaching/assignments`,
  `assessments`, `projects`, `questions`, `exams`) still fetch their full
  list with no `page`/`page_size` param and render it through a raw
  `<TableWrapper><Table>` rather than `DataTable` — no pagination control,
  no density/sticky-header treatment. This is real and was confirmed again
  in this phase, but retrofitting real server pagination to five screens
  (which means confirming each endpoint's paginated-response contract, not
  just a UI swap) is bigger than a mechanical fix and risks exactly the
  kind of backend-contract change this programme was told to avoid.
  Deliberately left for a dedicated future phase rather than forced into
  R12.
- **`app/admin/certificates/page.tsx` has no pagination control at all** —
  a pre-existing gap first documented in R6, unrelated to this redesign,
  still open.
- **No pre-redesign performance baseline exists** for CLS/bundle size/etc.,
  so numbers above describe the current state, not before/after deltas.
