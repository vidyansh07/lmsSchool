<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

<!-- BEGIN:grras-styling-rules -->

# Styling

Read [`docs/uiux/DESIGN_SYSTEM.md`](../docs/uiux/DESIGN_SYSTEM.md) before
changing how anything looks. The three things that bite hardest:

1. **A renamed `@theme` token fails silently.** Tailwind v4 builds utility
   names from token names, so removing one takes the background off a screen
   with `build`, `lint`, `typecheck` and the whole suite still green.
   `tests/unit/theme-tokens.test.ts` is the only gate that catches it.
2. **Colour means state.** `info` / `success` / `warning` / `danger`, and
   nothing else. If a screen wants a hue to tell two categories apart, the
   answer is the category's name, not a colour.
3. **If a screen needs a new visual pattern, add a primitive** to
   `components/ui/` rather than hand-rolling it in the page. Four competing
   stat cards and two sparklines are how the last system ended up needing a
   rebuild.

<!-- END:grras-styling-rules -->
