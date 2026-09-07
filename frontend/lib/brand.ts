/**
 * Tenant brand colour, applied at runtime.
 *
 * An institution picks a colour in settings and the interface follows it. Grras
 * is orange (`#EF7220`, taken from grras.com); another college on the same
 * install might be maroon or navy, and nothing should need rebuilding for that.
 *
 * How this differs from the usual recipe
 * --------------------------------------
 * The common approach remaps Tailwind's own palettes — override
 * `--color-blue-500` and every `bg-blue-500` in the app follows. That works on
 * a codebase whose components reach for `blue-500` directly. This one does not:
 * it has ~12 semantic tokens (`--color-primary`, `--color-surface`, …) and no
 * component names a numbered palette anywhere. Remapping `--color-blue-*` here
 * would set variables that nothing reads.
 *
 * So the brand is applied where this codebase actually looks: the semantic
 * tokens. Fewer variables, and every one of them is genuinely in use.
 *
 * Two tokens, because a brand colour has two jobs
 * -----------------------------------------------
 * `--color-brand` is the colour as chosen — large fills, a logo lockup, a chart
 * series. `--color-primary` is the same hue *darkened until white text on it is
 * legible*, and it is what buttons, links and the focus ring use.
 *
 * They cannot be the same value. Grras orange is 2.96:1 against white: fine as
 * a block, unreadable as a button label. Deriving the legible one rather than
 * asking for two colours means an administrator picks the colour they know
 * their institution by, and cannot accidentally produce an interface nobody can
 * read.
 *
 * Semantic colours — destructive, warning, success — are never touched. Red has
 * to keep meaning "this failed" even at an institution whose brand is red.
 */

/** The tokens a brand colour overrides. Everything else is left alone. */
const BRAND_TOKENS = [
  '--color-brand',
  '--color-primary',
  '--color-primary-foreground',
  '--color-accent',
] as const;

/** Lightness, in OKLCH percent, at which a hue reliably carries white text.
 *
 * Derived rather than guessed: at this lightness the brand hues in use clear
 * 4.5:1 against white, which is the AA floor for a button label. It is the same
 * number `app/globals.css` uses for the Grras orange, kept here so a tenant
 * colour lands on the identical footing rather than on a lighter one that
 * happens to look fine in a screenshot. */
const LEGIBLE_LIGHTNESS = 57;

/** A pale wash of the brand, for selected rows and subtle fills. */
const WASH_LIGHTNESS = 96;

export function isValidBrandColor(color: unknown): color is string {
  if (typeof color !== 'string') return false;
  const value = color.trim();
  if (!value) return false;
  if (/^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(value)) return true;
  // `CSS.supports` accepts every colour syntax the browser does — oklch, hsl,
  // colour keywords — without this file having to keep a parser in step with
  // the spec. It is absent server-side, hence the guard.
  if (typeof window !== 'undefined' && typeof window.CSS?.supports === 'function') {
    return window.CSS.supports('color', value);
  }
  return /^(rgb|hsl|oklch|lab|lch)a?\(/i.test(value);
}

/** `#EF7220` → `[239, 114, 32]`. Returns null for anything not a hex colour. */
function hexToRgb(value: string): [number, number, number] | null {
  const hex = value.trim().replace('#', '');
  const full =
    hex.length === 3
      ? hex
          .split('')
          .map((c) => c + c)
          .join('')
      : hex;
  if (!/^[0-9a-f]{6}$/i.test(full)) return null;
  return [
    parseInt(full.slice(0, 2), 16),
    parseInt(full.slice(2, 4), 16),
    parseInt(full.slice(4, 6), 16),
  ];
}

/** sRGB → OKLCH. The same conversion `tests/unit/theme-contrast.test.ts` uses
 *  in reverse, so a colour chosen here is measured on the same terms. */
export function rgbToOklch([r, g, b]: [number, number, number]): {
  l: number;
  c: number;
  h: number;
} {
  const toLinear = (v: number) => {
    const n = v / 255;
    return n <= 0.04045 ? n / 12.92 : ((n + 0.055) / 1.055) ** 2.4;
  };
  const [lr, lg, lb] = [toLinear(r), toLinear(g), toLinear(b)];

  const l = Math.cbrt(0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb);
  const m = Math.cbrt(0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb);
  const s = Math.cbrt(0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb);

  const lightness = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  const a = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const bb = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;

  return {
    l: lightness * 100,
    c: Math.hypot(a, bb),
    h: ((Math.atan2(bb, a) * 180) / Math.PI + 360) % 360,
  };
}

/**
 * Apply a brand colour to the document, or clear it.
 *
 * Set as inline styles on `<html>`, which beats the stylesheet's `:root` rule
 * without needing `!important` anywhere. Clearing removes the properties rather
 * than writing the defaults back, so the stylesheet is the single source of the
 * default and this file never has to know what it is.
 */
export function applyBrandColor(color: string | null | undefined): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;

  if (!isValidBrandColor(color)) {
    BRAND_TOKENS.forEach((name) => root.style.removeProperty(name));
    return;
  }

  const brand = color.trim();
  root.style.setProperty('--color-brand', brand);

  const rgb = hexToRgb(brand);
  if (!rgb) {
    // A non-hex colour we cannot decompose. Use it as the brand fill, and leave
    // `--color-primary` at the stylesheet default rather than risk putting
    // white text on something unreadable — a slightly off-brand button is a
    // much smaller failure than an invisible one.
    ['--color-primary', '--color-primary-foreground', '--color-accent'].forEach((name) =>
      root.style.removeProperty(name),
    );
    return;
  }

  const { c, h } = rgbToOklch(rgb);
  root.style.setProperty('--color-primary', `oklch(${LEGIBLE_LIGHTNESS}% ${c.toFixed(3)} ${h.toFixed(1)})`);
  root.style.setProperty('--color-primary-foreground', `oklch(99.5% 0.01 ${h.toFixed(1)})`);
  root.style.setProperty('--color-accent', `oklch(${WASH_LIGHTNESS}% 0.03 ${h.toFixed(1)})`);
}
