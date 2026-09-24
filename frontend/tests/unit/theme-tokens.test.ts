import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * Every design token the interface *references* must exist in `@theme`.
 *
 * Why this file exists: Tailwind v4 generates utility names from token names,
 * so `--color-amber-tint` is what makes `bg-amber-tint` work. Delete or rename
 * that token and every `bg-amber-tint` in the app emits **no CSS and no
 * error** — `next build`, `eslint` and `tsc` all stay green while the screen
 * silently loses its background. There is no other gate in this repo that
 * catches it, which makes a token rename the most dangerous edit a person can
 * make to the design system.
 *
 * So: parse the stylesheet, collect every token reference in the source, and
 * fail on any reference that resolves to nothing.
 */

const CSS = readFileSync(join(process.cwd(), 'app/globals.css'), 'utf8');
const SOURCE_DIRS = ['app', 'components', 'lib', 'hooks'];

/* ------------------------------------------------------------------ tokens */

/** The `@theme { … }` body, brace-matched so nested rules cannot truncate it. */
function themeBlock(css: string): string {
  const start = css.indexOf('@theme');
  if (start === -1) throw new Error('no @theme block in globals.css');
  const open = css.indexOf('{', start);
  let depth = 0;
  for (let i = open; i < css.length; i++) {
    if (css[i] === '{') depth++;
    else if (css[i] === '}' && --depth === 0) return css.slice(open + 1, i);
  }
  throw new Error('unbalanced @theme block in globals.css');
}

/** Declared token names, without the leading `--`: `color-primary`, `radius-card`, … */
const DEFINED = new Set(
  [...themeBlock(CSS).matchAll(/^\s*--([a-z0-9-]+)\s*:/gm)].map((match) => match[1]),
);

/* ------------------------------------------------------------------ sources */

function walk(dir: string, found: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) walk(path, found);
    else if (/\.tsx?$/.test(entry)) found.push(path);
  }
  return found;
}

/**
 * Remove comments while leaving string literals intact.
 *
 * Necessary because this codebase comments heavily, and prose like "rebuilt
 * from scratch" or "border-radius" otherwise parses as a class reference and
 * reports a token that was never referenced.
 */
function stripComments(source: string): string {
  let out = '';
  let i = 0;
  while (i < source.length) {
    const here = source[i];
    const next = source[i + 1];
    if (here === '/' && next === '*') {
      const end = source.indexOf('*/', i + 2);
      i = end === -1 ? source.length : end + 2;
      out += ' ';
    } else if (here === '/' && next === '/') {
      const end = source.indexOf('\n', i);
      i = end === -1 ? source.length : end;
      out += ' ';
    } else if (here === '"' || here === "'" || here === '`') {
      let j = i + 1;
      while (j < source.length && source[j] !== here) j += source[j] === '\\' ? 2 : 1;
      out += source.slice(i, j + 1);
      i = j + 1;
    } else {
      out += here;
      i++;
    }
  }
  return out;
}

function stringLiterals(source: string): string[] {
  const literals: string[] = [];
  let i = 0;
  while (i < source.length) {
    const quote = source[i];
    if (quote === '"' || quote === "'" || quote === '`') {
      let j = i + 1;
      while (j < source.length && source[j] !== quote) j += source[j] === '\\' ? 2 : 1;
      literals.push(source.slice(i + 1, j));
      i = j + 1;
    } else {
      i++;
    }
  }
  return literals;
}

/* -------------------------------------------------------------- namespaces */

/**
 * Utility prefix → the `@theme` namespaces it may read from.
 *
 * Mostly one each, but `text-` is genuinely ambiguous: `text-primary` is a
 * colour and `text-base` is a font size, and Tailwind resolves against both
 * `--color-*` and `--text-*`. So a prefix carries a list, and a reference is
 * satisfied if any one of its namespaces declares the token.
 *
 * `accent-` is the CSS `accent-color` utility (checkbox and radio tint), which
 * is a colour like the rest, not the old `--color-accent` token.
 */
const NAMESPACES: Record<string, string[]> = {
  bg: ['color'],
  text: ['color', 'text'],
  border: ['color'],
  ring: ['color'],
  fill: ['color'],
  stroke: ['color'],
  from: ['color'],
  to: ['color'],
  via: ['color'],
  decoration: ['color'],
  outline: ['color'],
  caret: ['color'],
  divide: ['color'],
  accent: ['color'],
  rounded: ['radius'],
  shadow: ['shadow'],
  ease: ['ease'],
  font: ['font'],
  duration: ['duration'],
};

/** Tailwind's own default palette, which `@theme` extends rather than replaces. */
const DEFAULT_HUES =
  '(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)';

/**
 * Suffixes Tailwind resolves without any project token.
 *
 * Kept explicit rather than inferred: a typo like `rounded-fulll` should be
 * reported, and a permissive rule would wave it through.
 */
const BUILT_IN: RegExp[] = [
  // colour keywords and the default palette
  /^(?:white|black|transparent|current|inherit|none)$/,
  new RegExp(`^${DEFAULT_HUES}-(?:50|100|200|300|400|500|600|700|800|900|950)$`),
  // borders and dividers: width, side and style, not colour
  /^(?:x|y|s|e|t|r|b|l)(?:-(?:0|2|4|8|reverse))?$/,
  /^(?:0|2|4|8|solid|dashed|dotted|double|hidden|collapse|separate|spacing)$/,
  // radius: sizes, plus per-corner and per-side forms
  /^(?:xs|sm|md|lg|xl|2xl|3xl|4xl|full)$/,
  /^(?:t|r|b|l|s|e|tl|tr|br|bl|ss|se|es|ee)(?:-(?:xs|sm|md|lg|xl|2xl|3xl|4xl|full|none))?$/,
  // shadow
  /^(?:2xs|xs|sm|md|lg|xl|2xl|inner)$/,
  // text: sizes beyond the project scale, alignment, wrapping, overflow
  /^(?:5xl|6xl|7xl|8xl|9xl)$/,
  /^(?:left|center|right|justify|start|end|wrap|nowrap|balance|pretty|ellipsis|clip)$/,
  // font: families and weights
  /^(?:sans|serif|mono|thin|extralight|light|normal|medium|semibold|bold|extrabold|black|stretch)$/,
  // ring and outline widths, and the ring inset flag
  /^(?:inset|offset-(?:0|1|2|4|8))$/,
  // ease and duration literals
  /^(?:linear|in|out|in-out|initial)$/,
  /^\d+$/,
];

/**
 * `--duration-*` is not a Tailwind v4 theme namespace.
 *
 * v4.3.3 reads durations from `--transition-duration-*`, so although
 * `--duration-quick` is declared in `@theme`, the bare class `duration-quick`
 * compiles to nothing at all — verified by running these classes through
 * `@tailwindcss/postcss`. The arbitrary form `duration-[var(--duration-quick)]`
 * does work, which is why most call sites look fine and these do not.
 *
 * The token rewrite removed the `--duration-*` tokens entirely and moved
 * every call site to a literal (`duration-150`), so this list is empty. It
 * stays as an assertion because a named duration is the natural thing to
 * reach for, and reaching for it costs a transition with no error anywhere.
 */
const DEAD_DURATION_CLASSES: string[] = [];

/** Custom properties set outside `@theme`, so the scan must not demand them. */
const RUNTIME_PROPERTIES = new Set([
  // next/font injects these as class-scoped properties; app/layout.tsx wires
  // them into --font-sans and --font-heading.
  'font-inter',
  'font-sora',
]);

/* ------------------------------------------------------------------- collect */

interface Reference {
  /** Every token name that would satisfy this reference. */
  candidates: string[];
  where: string;
  via: string;
}

function collect(): { utilities: Reference[]; variables: Reference[]; durations: Set<string> } {
  const utilities: Reference[] = [];
  const variables: Reference[] = [];
  const durations = new Set<string>();
  const prefixes = Object.keys(NAMESPACES).join('|');
  const utility = new RegExp(`(?<![a-z0-9-])(${prefixes})-([a-z][a-z0-9-]*)`, 'g');

  for (const dir of SOURCE_DIRS) {
    for (const file of walk(dir)) {
      const source = stripComments(readFileSync(file, 'utf8'));

      for (const match of source.matchAll(/var\(\s*--([a-z0-9-]+)/g)) {
        const token = match[1] ?? '';
        variables.push({ candidates: [token], where: file, via: `var(--${token})` });
      }

      for (const literal of stringLiterals(source)) {
        // Arbitrary values carry their own `var(--…)`, already collected above.
        const classes = literal.replace(/\[[^\]]*\]/g, ' ');
        // A literal still holding `var(` after that is an inline style string
        // ('stroke-dashoffset var(--duration-slow) …'), not a class list.
        if (classes.includes('var(')) continue;

        for (const match of classes.matchAll(utility)) {
          const whole = match[0];
          const prefix = match[1] ?? '';
          const suffix = match[2] ?? '';
          if (BUILT_IN.some((pattern) => pattern.test(suffix))) continue;
          if (prefix === 'duration') {
            durations.add(whole);
            continue;
          }
          const candidates = (NAMESPACES[prefix] ?? []).map(
            (namespace) => `${namespace}-${suffix}`,
          );
          utilities.push({ candidates, where: file, via: whole });
        }
      }
    }
  }

  return { utilities, variables, durations };
}

function unresolved(references: Reference[], alsoAllowed = new Set<string>()): string[] {
  const missing = references
    .filter(
      (reference) =>
        !reference.candidates.some(
          (token) => DEFINED.has(token) || alsoAllowed.has(token),
        ),
    )
    .map((reference) => `${reference.via} in ${reference.where}`);

  return [...new Set(missing)].sort();
}

const { utilities, variables, durations } = collect();

/* --------------------------------------------------------------------- tests */

describe('design tokens', () => {
  it('declares tokens for every utility class that needs one', () => {
    expect(unresolved(utilities)).toEqual([]);
  });

  it('declares tokens for every var(--…) the source reads', () => {
    expect(unresolved(variables, RUNTIME_PROPERTIES)).toEqual([]);
  });

  it('has no bare duration utility, which Tailwind would drop', () => {
    // See the note on DEAD_DURATION_CLASSES: `duration-quick` compiles to
    // nothing, while `duration-[var(--duration-quick)]` works. Every call site
    // currently uses the arbitrary form, so this list is empty and must stay
    // empty — a bare `duration-<token>` is silently no transition at all.
    expect([...durations].sort()).toEqual(DEAD_DURATION_CLASSES);
  });

  it('finds enough references for the scan to be meaningful', () => {
    // A refactor that breaks the walk or the literal parser would otherwise
    // make this whole file pass by checking nothing at all. The `var()` floor
    // is deliberately low: the token rewrite converted 99 arbitrary-value
    // classes (`rounded-[var(--radius-card)]`) into named utilities
    // (`rounded-card`), so most token reads are now counted as utilities.
    expect(utilities.length).toBeGreaterThan(500);
    expect(variables.length).toBeGreaterThan(25);
  });
});
