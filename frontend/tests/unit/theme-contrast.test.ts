import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * Every colour pair the interface actually uses, measured against WCAG AA.
 *
 * This parses `app/globals.css` rather than repeating the palette, so a token
 * darkened or lightened there without checking it fails here. Estimating
 * contrast by eye is exactly how a "brighter" redesign ends up with grey text
 * nobody over forty can read.
 *
 * AA is 4.5:1 for body text, 3:1 for large text and for the boundaries of
 * interactive components — which is why the focus ring has its own row.
 *
 * The palette this checks is the rebuilt one: three inks, one action colour,
 * four semantic states with a wash each, and a dark rail. The six accent
 * trios and three pill accents it used to cover are gone, along with the
 * per-metric colour they existed for.
 */

const CSS = readFileSync(join(process.cwd(), 'app/globals.css'), 'utf8');

/** `--color-name: oklch(L% C H);` → [L, C, H] */
function token(name: string): [number, number, number] {
  const match = CSS.match(
    new RegExp(`--color-${name}:\\s*oklch\\(([\\d.]+)%\\s+([\\d.]+)\\s+([\\d.]+)\\)`),
  );
  if (!match) throw new Error(`no --color-${name} in globals.css`);
  return [Number(match[1]) / 100, Number(match[2]), Number(match[3])];
}

/** OKLCH → linear sRGB, the standard conversion. */
function linearRgb([L, C, H]: [number, number, number]): [number, number, number] {
  const h = (H * Math.PI) / 180;
  const a = C * Math.cos(h);
  const b = C * Math.sin(h);

  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;

  const clamp = (value: number) => Math.min(1, Math.max(0, value));
  return [
    clamp(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
    clamp(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
    clamp(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s),
  ];
}

function luminance(name: string): number {
  const [r, g, b] = linearRgb(token(name));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(foreground: string, background: string): number {
  const a = luminance(foreground);
  const b = luminance(background);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

/** [foreground, background, minimum, what it is]. */
const PAIRS: [string, string, number, string][] = [
  // The three inks, on each of the three surfaces they are written on.
  ...(['canvas', 'surface', 'sunken'] as const).flatMap(
    (surface): [string, string, number, string][] => [
      ['ink', surface, 4.5, `body text on ${surface}`],
      ['ink-muted', surface, 4.5, `secondary text on ${surface}`],
      // The floor of the palette. The reference product puts its 11px column
      // headers at 2.56:1; this is the same role, kept legible.
      ['ink-faint', surface, 4.5, `a column header on ${surface}`],
    ],
  ),

  // The action colour: its own label, and its use as a boundary and a link.
  ['action-fg', 'action', 4.5, 'the label on a primary button'],
  ['action', 'surface', 3, 'the focus ring, and action as a boundary'],
  ['action', 'canvas', 3, 'an action-coloured link on the page'],

  // The chosen-state wash carries the active nav item and ordinary text.
  ['selected-fg', 'selected', 4.5, 'the active navigation item'],
  ['ink', 'selected', 4.5, 'text on a selected row'],
  ['ink-muted', 'selected', 4.5, 'secondary text on a selected row'],

  // The rail is the one dark surface, so its own pairs are inverted.
  ['rail-fg', 'rail', 4.5, 'a rail label'],
  ['rail-active', 'rail', 4.5, 'the active item on the rail'],

  // Each semantic state as small text on a card and on its own wash, plus
  // the label on the filled version.
  ...(['info', 'success', 'warning', 'danger'] as const).flatMap(
    (state): [string, string, number, string][] => [
      [state, 'surface', 4.5, `${state} text on a card`],
      [state, 'canvas', 4.5, `${state} text on the page`],
      [state, `${state}-wash`, 4.5, `${state} text in its own chip`],
      [`${state}-fg`, state, 4.5, `the label on a filled ${state} badge`],
      // A wash is a chip and a banner background, so ink sits on it too.
      ['ink', `${state}-wash`, 4.5, `body text on a ${state} banner`],
    ],
  ),

  // A chart series is a line or a bar against the card it is drawn on: 3:1,
  // the threshold for a graphical object rather than for text.
  ...([1, 2, 3, 4, 5] as const).map(
    (n): [string, string, number, string] => [
      `chart-${n}`,
      'surface',
      3,
      `chart series ${n} against the card`,
    ],
  ),
];

describe('theme contrast', () => {
  it.each(PAIRS)('%s on %s meets %s:1 — %s', (foreground, background, minimum) => {
    expect(contrast(foreground, background)).toBeGreaterThanOrEqual(minimum);
  });

  it('a card is never darker than the page it sits on', () => {
    // A card is lighter than the canvas and carries a hairline; a card darker
    // than the page reads as a hole in it.
    expect(luminance('surface')).toBeGreaterThanOrEqual(luminance('canvas'));
  });

  it('the sunken surface really is the darkest of the three', () => {
    // `--color-sunken` paints toolbars, table heads and segmented tracks —
    // the recessed parts. If it drifts lighter than the canvas, every one of
    // those reads as raised instead, which is the opposite of its name.
    expect(luminance('sunken')).toBeLessThanOrEqual(luminance('canvas'));
  });

  it('the brand orange is kept off text', () => {
    // 2.96:1 on white — a fill for the logo, and the whole reason
    // `--color-action` is a separate, darker token. Pinned so nobody promotes
    // it to a button colour because it "looks more on-brand": a white label
    // on it would fail AA, silently, on every primary button in the product.
    expect(contrast('brand', 'surface')).toBeLessThan(4.5);
  });

  it('the action colour is a darker relative of the brand, not a new hue', () => {
    // The point of the split is legibility, not a second identity. Same
    // family, enough lightness taken out of it to carry white text.
    const [brandL, , brandH] = token('brand');
    const [actionL, , actionH] = token('action');
    expect(Math.abs(brandH - actionH)).toBeLessThan(15);
    expect(actionL).toBeLessThan(brandL);
    expect(contrast('action-fg', 'action')).toBeGreaterThanOrEqual(4.5);
  });

  it('is light only, with no operating-system switch', () => {
    // The app used to follow `prefers-color-scheme`, so the same install looked
    // different on two machines and nobody could say what the product looked
    // like. Only the comment explaining that should remain.
    expect(CSS).not.toMatch(/@media\s*\(prefers-color-scheme/);
    expect(CSS).toMatch(/color-scheme:\s*light\s*;/);
  });
});
