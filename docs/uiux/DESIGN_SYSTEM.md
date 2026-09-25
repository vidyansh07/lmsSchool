# The design system

The single source of truth for how this product looks. If a screen needs
something that is not described here, the answer is to add it here and to
`components/ui/`, not to invent it in the page.

For how the screens *behave* — confirmations, error states, the
unsaved-changes guard, per-screen contracts — see
[`docs/erp/DESIGN_DECISIONS.md`](../erp/DESIGN_DECISIONS.md).

---

## 1. The direction

The system this replaced was the end state of fifteen incremental passes that
finished on a "bold, multi-colour dashboard" brief: six accent colour trios,
three more pill-only accents, an indigo action colour, tinted two-layer card
shadows, eight animation keyframes. Around ninety tokens. A dashboard built
from it read as six colours competing before a single number had been read.

The replacement was built from zero against a reference product whose UI was
measured in the browser rather than described from memory. Three rules carry
it:

1. **Colour means state.** `info`, `success`, `warning`, `danger` — and
   nothing else. There are no decorative colours and no per-metric hues, so
   anything tinted on screen is saying something. This is the rule that
   removed two whole category palettes (see §4).
   **One bounded exception, added when the charts landed:** a chart series'
   colour is its *identity*, and identity is information, so
   `--color-chart-1..8` is categorical rather than semantic. The exception
   stops at the plot — a stat tile, a badge and an icon chip still tint only
   by state, and there are still no per-metric hues.
2. **Separation is a hairline and space, not elevation.** A card is
   `--color-surface` with a `--color-line` border on a `--color-canvas` page.
   **Two shadows exist:** `--shadow-overlay` for things above the page, and
   `--shadow-panel` for `ChartCard` and nothing else. The original rule — a
   shadow and a border draw the same edge twice — holds for a 12px card in a
   dense list, and stops holding for a 300px-tall chart panel, which a
   hairline alone does not separate from the identically-white panel 16px
   below it. `Card` is unchanged and stays the default for anything that is
   not a plot.
3. **The brand is a fill, never an action.** Grras orange is 2.96:1 on white.
   It cannot carry a white button label, so `--color-brand` paints the logo
   and `--color-action` — a darker relative of it, 5.18:1 — carries every
   action. Both halves are pinned by `theme-contrast.test.ts`.

**Light only, deliberately.** No `prefers-color-scheme` branch. A grade book,
a ledger and a status board need to be the same screen on a projector, in a
screenshot in a support ticket, and on a laptop with dark mode on for
everything else. One theme means "what does the product look like" has one
answer. The tokens are structured so dark mode could be added as a second
block later; nothing about that is started.

---

## 2. Tokens

All 51 live in the `@theme` block of `frontend/app/globals.css`, which is the
only stylesheet in the frontend. Values are OKLCH; the hex in each comment is
what it resolves to.

### Surfaces

| Token | Hex | Use |
|---|---|---|
| `--color-canvas` | `#F8FAFC` | the page |
| `--color-surface` | `#FFFFFF` | cards, table rows, the top bar |
| `--color-sunken` | `#F1F5F9` | toolbars, table heads, segmented tracks |
| `--color-line` | `#E2E8F0` | hairlines, input borders |
| `--color-line-strong` | `#CBD5E1` | hover borders, real dividers |

### The rail

The one dark surface in the product, and the reason everything else can stay
light without looking unframed.

| Token | Hex | Use |
|---|---|---|
| `--color-rail` | `#2A1B12` | the rail itself (warm charcoal, not a neutral) |
| `--color-rail-fg` | `#E7E5E4` | rail labels — 13.2:1 on it |
| `--color-rail-active` | `#FDBA74` | the active rail item — 9.9:1 on it |

### Ink

| Token | Hex | Use |
|---|---|---|
| `--color-ink` | `#0F172A` | body text — 17.9:1 on a card |
| `--color-ink-muted` | `#4E5E76` | secondary text |
| `--color-ink-faint` | `#5C6B80` | column heads, meta, placeholders |

`ink-faint` is the floor of the palette, and it is darker than it looks like it
should be on purpose. The reference product uses `#94A3B8` for its 11px column
headers, which is 2.56:1 and fails AA. The first value tried here, `#64748B`,
is fine on a card at 4.76:1 but only 4.35:1 on `--color-sunken` — which is
exactly the band a table head sits on, so every column header in the product
would have failed. Do not lighten it without re-running the contrast test.

### Action and selection

| Token | Hex | Use |
|---|---|---|
| `--color-action` | `#C2410B` | primary buttons, links, the focus ring |
| `--color-action-hover` | `#9A3412` | its hover |
| `--color-action-fg` | `#FFFFFF` | labels on it — 5.18:1 |
| `--color-selected` | `#FFF3EA` | active nav, a chosen row |
| `--color-selected-fg` | `#9A3412` | text on that wash |

### Brand

`--color-brand` (`#EF7220`) is the logo mark, and the **only** token a tenant
overrides at runtime. See §6.

### Semantic states

Four states, each with a white label colour for a filled badge and an opaque
wash for a chip or a banner.

| State | Hex | On a card |
|---|---|---|
| `--color-info` | `#0469A1` | 5.93:1 |
| `--color-success` | `#047857` | 5.48:1 |
| `--color-warning` | `#B45307` | 5.02:1 |
| `--color-danger` | `#B91C1C` | 6.47:1 |

Plus `--color-<state>-fg` and `--color-<state>-wash` for each. Washes are
opaque, not the state colour at 10% — a translucent fill picks up whatever is
behind it, so the same alert used to read differently on a card than on the
page.

### Charts

Eight categorical steps, read through `components/ui/charts/chart-colors.ts`;
never a hex in a caller.

| Step | Hex | On a card | Hue |
|---|---|---|---|
| `chart-1` | `#C2410B` | 5.19:1 | 38 |
| `chart-2` | `#0469A1` | 5.93:1 | 243 |
| `chart-3` | `#047857` | 5.49:1 | 166 |
| `chart-4` | `#B45307` | 5.03:1 | 49 |
| `chart-5` | `#4E5E76` | 6.56:1 | 257 |
| `chart-6` | `#7C3AED` | 5.71:1 | 293 |
| `chart-7` | `#0D7490` | 5.35:1 | 223 |
| `chart-8` | `#BE113C` | 6.29:1 | 17 |

**The hues are the reference product's; the lightness is not.** Five of its
ten series colours fail WCAG 1.4.11's 3:1 threshold against a white card,
which a 2px stroke has to clear: amber-500 `#F59E0B` **2.15:1**, cyan-500
`#06B6D4` **2.43**, teal-500 `#14B8A6` **2.49**, emerald-500 `#10B981`
**2.54**, sky-500 `#0EA5E9` **2.77**. The 600/700 family clears it at the same
hue. If one of these looks dull next to the reference, that gap is the reason.

Steps 1–5 have not moved since the rebuild, so nothing already plotted
repaints. The smallest hue gap is 10.6° between `chart-1` and `chart-4` — a
pre-existing weakness left alone deliberately, because renumbering repaints
every chart in the product for a cosmetic gain.

**Five series is the cap.** Past that, colour stops distinguishing them and
the fix is small multiples, not a ninth step. `chart-colors.ts` warns in
development via `SERIES_COUNT_WARNING_THRESHOLD`, the same soft-warning shape
as `DONUT_CATEGORY_WARNING_THRESHOLD`. Seven dots in the overview strip are
fine only because each is paired with its own text label — colour is never the
identifier there.

### Type

| Token | Value |
|---|---|
| `--font-sans` | Inter — everything read at length |
| `--font-heading` | Sora 600 — `h1`–`h4` (applied in the base layer) and KPI figures |
| `--font-mono` | a system stack — ids, codes, ledger references |

Scale, 14px base: `--text-2xs` 11px · `xs` 12 · `sm` 13 · `base` 14 · `lg` 16
· `xl` 18 · `2xl` 22 · `3xl` 28 · `4xl` 36.

At this density the scale cannot afford large size jumps to signal hierarchy,
so hierarchy comes from the family change instead — a heading is a different
voice, not a bigger one.

### Geometry and motion

`--radius-control` 8px · `--radius-card` 12px · `--radius-panel` 16px
(`ChartCard` only) · `--radius-pill` 999px · `--shadow-overlay` (overlays) ·
`--shadow-panel` (`ChartCard` only) · `--ease-out` (the only curve).

Durations are **literals** at the call site (`duration-150`). There is no
`--duration-*` namespace in Tailwind v4 — it reads `--transition-duration-*` —
so a bare `duration-quick` compiles to nothing at all. See §3.

### Spacing

Deliberately un-tokenised: Tailwind's default 4px scale. A second spacing
vocabulary on top of a perfectly good one is a thing to keep in sync forever.

---

## 3. The silent-failure warning

**Read this before renaming a token.**

Tailwind v4 generates utility names *from* token names: `--color-amber-tint`
is what makes `bg-amber-tint` work. Delete or rename a token and every use of
its utility emits **no CSS and no error**. `next build`, `eslint`, `tsc` and
the entire test suite stay green while the screen quietly loses its
background.

`frontend/tests/unit/theme-tokens.test.ts` is the only thing in this repo that
catches it. It parses `@theme`, collects every token reference in `app/`,
`components/`, `lib/` and `hooks/` — utility classes *and* `var(--…)` reads
inside string literals — and fails on any that resolves to nothing. It earned
its place during the rebuild: when the compatibility shim came out it named
seven `var(--color-primary)`-era reads inside chart SVG attributes that no
class rename could reach, and which every other gate had passed.

Never weaken it to make a change land.

---

## 4. Primitives

26 files in `frontend/components/ui/`. The rule: **if a screen needs a new
visual pattern, add a primitive.** Do not hand-roll it in the page. Four
separate stat cards and two sparklines are how the previous system got here.

Controls · `button` `input` `select` `checkbox` `radio-group` `switch`
`field` `toolbar`
Surfaces · `card` `table` `layout` (`PageHeader` / `Section` / `Grid` /
`GridItem`, with `lgSpan`) `tabs` `skeleton`
Feedback · `alert` `badge` `toast` `progress` `spinner` `empty` `stat`
`stat-strip` `icon-chip`
Overlays · `dialog` `sheet` `popover` `dropdown-menu` `tooltip`
Identity · `avatar`
Data · `components/ui/charts/` — `ChartCard` (the panel), area, bar,
horizontal bar, combo (dual axis), line, donut, radar, stage funnel,
radial-progress, sparkline, and `useChartAnimation()`

Notable contracts:

- **`Button`** — one filled `primary` per screen; `secondary` and `outline`
  are the same weight on purpose, because a toolbar of five equally loud
  buttons says nothing about which one the person came to press. 36px tall,
  12px radius, 12px label.
- **`Badge`** — five semantic variants, dot on by default. There is no
  category variant: `categoryVariant()` used to hash a string into one of nine
  hues, which made "Python" teal for no reason. The name was always the
  information.
- **`StatCard`** — one figure, its meaning, and its direction. No accent, no
  counting animation, no cursor spotlight. The delta says which way is good in
  words *and* colour *and* an arrow. The figure carries `data-numeric`, which
  the base layer turns into tabular figures.
- **`Grid` / `GridItem`** — twelve columns at `md`, one below. `span` is a
  closed set (3, 4, 6, 8, 9, 12): the widths that divide twelve cleanly are
  the ones that tile without leaving a gap. `lgSpan` overrides it from `lg`
  up; chart rows use `span={12} lgSpan={6}` so two charts sit side by side on
  a laptop but never at ~360px each on a tablet.
- **`ChartCard`** — the only surface a plot sits in: 16px, hairline ring,
  `--shadow-panel`. `subtitle` is **required**, because a plot is a metric
  with more ink and every metric carries its definition; it renders as
  `data-testid="chart-definition"`. `testId` lets a page's test scope its
  Recharts queries to one card, which is what stops the next chart added to
  that page breaking the last one's test.
- **`StatStrip`** — the headline figures as one card divided by hairlines,
  not N tiles. Its dots are the one place seven palette hues sit in a row,
  and only because each is paired with its own text label.
- **`IconChip`** — a 32px tinted square for a card heading. Tone is one of
  the four states; there is no per-metric hue.
- **`ComboChart`** — two scales on one plot. `leftLabel` and `rightLabel`
  are required with no default, because two unlabelled axes is the classic
  false-correlation chart.
- **`HorizontalBarChart`** — for categories that are words rather than
  dates. `colorPerBar` cycles the palette to say "different things";
  `colorKey` reads a colour off each datum to say *what* each thing is
  (above or below a target). Use the second whenever the bars are one metric.
- **`RadarChart`** — `max` fixed at 100, never inferred, so two radars are
  comparable. Refuses fewer than three spokes.
- **`StageFunnel`** — horizontal bars plus a conversion column, not a
  Recharts trapezoid: a width is only honest when every stage strictly
  nests, and the number a counsellor wants is the drop-off between stages.
- **`hideLegend`** on the multi-series charts, for when the card carries the
  legend — two legends for one plot is the same information twice.

---

## 5. Layout and density

- A screen opens with `PageHeader`: title, a meta line carrying live context
  ("sorted by last active", "12 of 340 shown") rather than a restatement of
  the title, and a right-aligned action slot with at most one filled button.
- Tables: 11px semibold uppercase column heads with 0.055em tracking on the
  sunken band; 13px cells with 20px side padding; rows light on hover. Cells
  stack a primary value over grey secondary meta rather than adding columns.
- Cards: 12px radius, 16px padding, hairline, no shadow.
- Composite cards divide internally with vertical hairlines into labelled
  columns rather than nesting more cards.

---

## 6. Hard constraints

Each of these breaks something in a way that does not look related to the
change that caused it.

1. **`--color-brand` is a backend contract.** `frontend/lib/brand.ts` writes
   exactly that property onto `<html>`; `components/brand-theme.tsx` reads it
   from `/api/v1/branding/`; `backend/apps/branding/` stores it;
   `app/admin/branding/page.tsx` previews it. Renaming the token breaks all
   four with no error anywhere.
2. **Never promote the brand to an action.** It is 2.96:1 on white. The
   contrast test asserts it stays *under* 4.5:1 precisely so this cannot
   happen quietly.
3. **The CSP forbids a font CDN.** `frontend/middleware.ts` sets
   `font-src 'self' data:`. Fonts come through `next/font` and are self-hosted
   at build. A Google Fonts URL yields unstyled text in production and nowhere
   else. Never widen the CSP for a font.
4. **Focus must be an `outline`.** `e2e/interface.spec.ts` asserts a non-`none`
   computed `outlineStyle` on a nav link, so a `box-shadow` ring fails a test
   that looks unrelated to colour.
5. **The page background must keep every sRGB channel above 230.** The same
   spec paints `body` to a canvas and checks it. `--color-canvas` clears it.
6. **`components/navigation.ts` is not a layout file.** 828 lines of nav data
   plus `isVisible()` capability gating. Editing it during a visual pass is
   how a trainer silently gains an admin route.
7. **The dynamic `style={{}}` sites are logic, not styling** — chart geometry,
   progress percentages, the tenant colour preview. Change only the token
   names they interpolate, never the computation:
   `components/ui/charts/{chart-skeleton,chart-legend,chart-tooltip,donut-chart}.tsx`,
   `components/ui/{tooltip,switch,progress}.tsx`, `components/progress-bar.tsx`,
   `components/fees/fee-ledger.tsx`, `components/app-shell.tsx`,
   `app/admin/branding/page.tsx`.
8. **A colour token must be written as `oklch(L% C H)`.**
   `theme-contrast.test.ts` finds tokens with a regex that matches only that
   form, so a new colour written as a hex, with an alpha slash, or via
   `color-mix()` makes the test **throw** (`no --color-chart-9 in
   globals.css`) instead of failing a contrast row. It reads as a broken test
   rather than an unmeasured colour, which is how an unmeasured colour gets
   committed. `--shadow-panel` may use an alpha channel because it is not a
   `--color-*` token and nothing parses it.

---

## 7. The accessibility contract

- AA everywhere: 4.5:1 for text, 3:1 for large text, interactive boundaries
  and graphical objects. `tests/unit/theme-contrast.test.ts` parses the
  stylesheet and checks every pair the interface puts on screen, including the
  inverted pairs on the dark rail.
- Colour is never the only carrier of meaning: a status is a dot and a word, a
  delta is an arrow and a sign and a sentence, an active filter is
  `aria-pressed` and not only a fill.
- Tabular figures on anything in a column, via `table`, `[data-numeric]` or
  `.tabular`.
- `prefers-reduced-motion` is honoured globally in the base layer, so a new
  animation cannot forget.
- Focus is visible on everything, and it is an outline (§6.4).

---

## 8. Motion

Five keyframes, all of them in `globals.css`: `fade-in`, three directional
`slide-in`s for the sheets, and `shimmer` for skeletons. Each animates only
`transform` or `opacity`.

What is deliberately absent: a rise-in on every tile, a scale-in on every
overlay, per-child staggers, a cursor-tracking spotlight gradient, a sparkline
drawing itself, and a press dip. That was motion decorating screens whose job
is to show a number, and the `motion` package that drove half of it is no
longer a dependency.

**Charts.** A chart's entrance is Recharts' own tween at `CHART_ANIMATION_MS`,
and every chart primitive reads it through `useChartAnimation()` — a hook
rather than a per-chart prop, so a new chart cannot forget
`prefers-reduced-motion`. `ChartCard` uses the existing `fade-in`.
Deliberately **not** a rise-in and deliberately **not** staggered, for the
same reason both were removed: a dashboard that assembles itself over a third
of a second is a third of a second in which the numbers cannot be read.
Hover on a panel is a ring change, not a lift.
