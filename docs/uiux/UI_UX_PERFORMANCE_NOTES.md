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

**Lighthouse, this phase (R12): not run.** No Lighthouse binary, cached
`npx` download, or generated report (`.json`/`.html`) exists anywhere in
this environment, and there is no way to install or execute one from this
session. An earlier draft of this document reported specific Accessibility/
Best Practices/SEO scores, pass/fail counts, and a CLS number for this
phase, plus a category called "Agentic Browsing" and a claim that the local
`lighthouse` tool "only runs accessibility/SEO/best-practices/agentic-
browsing audits" and skips Performance entirely. None of that was accurate:
no run actually happened this phase (there is nothing to trace those
numbers to), "Agentic Browsing" is not a real Lighthouse category, and the
real Lighthouse CLI's default and primary category is Performance. Those
claims have been removed rather than replaced with new numbers, since no
measurement was taken. R11's bundle numbers above remain the only measured
performance evidence for this redesign.

## Known limitations

- **claude-in-chrome (the browser automation tool) was never available in
  any phase of this redesign.** Nearly all visual QA on authenticated
  screens — the dashboards, tables, forms, the collapsed sidebar — relied
  on close reading of the component code and Tailwind breakpoint classes,
  cross-checked against real API data and clean production builds, not on
  actually looking at rendered pixels. R12 did not run a Lighthouse or
  screenshot check either — see "Real numbers" above. This is the single
  biggest gap in how thoroughly this redesign was actually verified, and
  it's been flagged consistently since R2.
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
