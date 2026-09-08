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
  ['foreground', 'background', 4.5, 'body text on the page'],
  ['foreground', 'surface', 4.5, 'body text on a card'],
  ['foreground', 'muted', 4.5, 'text on a muted panel'],
  ['muted-foreground', 'background', 4.5, 'secondary text on the page'],
  ['muted-foreground', 'surface', 4.5, 'secondary text on a card'],
  ['muted-foreground', 'muted', 4.5, 'secondary text on a muted panel'],
  ['primary-foreground', 'primary', 4.5, 'the label on a primary button'],
  ['primary', 'surface', 3, 'the focus ring, and primary as a boundary'],
  ['primary', 'background', 3, 'a primary link on the page'],
  ['destructive', 'surface', 4.5, 'danger text'],
  ['warning', 'surface', 4.5, 'warning text'],
  ['success', 'surface', 4.5, 'success text'],
  // The selected-state wash carries three kinds of text: the active nav item
  // in navy, an ordinary label, and a secondary line.
  ['primary', 'accent', 4.5, 'the active navigation item'],
  ['foreground', 'accent', 4.5, 'text on a selected row'],
  ['muted-foreground', 'accent', 4.5, 'secondary text on a selected row'],
  // Each accent is small text on its own tint (a dashboard tile) and on its
  // soft (a pill, an icon disc). The reference these came from fails three of
  // these; the tokens were darkened until they pass.
  ...(['amber', 'violet', 'rose', 'blue', 'green', 'pink'] as const).flatMap(
    (accent): [string, string, number, string][] => [
      [accent, `${accent}-tint`, 4.5, `${accent} label on its tile`],
      [accent, `${accent}-soft`, 4.5, `${accent} label in its pill`],
      [accent, 'surface', 4.5, `${accent} as small text on a card`],
    ],
  ),
  ...(['indigo', 'cyan', 'teal'] as const).flatMap((accent): [string, string, number, string][] => [
    [accent, `${accent}-soft`, 4.5, `${accent} label in its pill`],
  ]),
];

describe('theme contrast', () => {
  it.each(PAIRS)('%s on %s meets %s:1 — %s', (foreground, background, minimum) => {
    expect(contrast(foreground, background)).toBeGreaterThanOrEqual(minimum);
  });

  it('a surface is never darker than the page it sits on', () => {
    // The page and its cards are both white, by request, so a card separates
    // itself with a hairline border and `--shadow-card` rather than by being
    // lighter. What must still never happen is the inverse: a card darker than
    // the page reads as a hole in it.
    expect(luminance('surface')).toBeGreaterThanOrEqual(luminance('background'));
  });

  it('the brand orange is kept off text', () => {
    // 2.96:1 on white — a fill for the logo, and the reason `--color-primary`
    // is a different token. Pinned so nobody promotes it to a button colour
    // because it "looks more on-brand".
    expect(contrast('brand', 'surface')).toBeLessThan(4.5);
  });

  it('is light only, with no operating-system switch', () => {
    // The app used to follow `prefers-color-scheme`, so the same install looked
    // different on two machines and nobody could say what the product looked
    // like. Only the comment explaining that should remain.
    expect(CSS).not.toMatch(/@media\s*\(prefers-color-scheme/);
    expect(CSS).toMatch(/color-scheme:\s*light\s*;/);
  });
});
