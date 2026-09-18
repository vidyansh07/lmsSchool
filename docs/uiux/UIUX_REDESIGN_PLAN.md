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

## Phase log

(Filled in as each phase completes — same evidence bar as the ERP
programme: independently re-verified, not just the workflow's own report.)
