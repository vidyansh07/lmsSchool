/**
 * Tenant brand colour, applied at runtime.
 *
 * An institution picks a colour in settings and its logo mark follows it.
 * Grras is orange (`#EF7220`, taken from grras.com); another college on the
 * same install might be maroon or navy, and nothing should need rebuilding
 * for that.
 *
 * What it does *not* touch, and why
 * ---------------------------------
 * Only `--color-brand` — the logo mark. Buttons, links, the focus ring and the
 * selected row all use `--color-primary`, which stays the navy of the design
 * whatever the brand colour is. That is a decision, not an omission: the
 * owner asked for the navy palette with the orange kept on the logo, and an
 * earlier version of this file derived a button colour from the brand and
 * painted every action orange the moment a brand colour was saved — which is
 * how the whole interface turned orange while the stylesheet said navy.
 *
 * A brand colour also cannot be relied on for text. Grras orange is 2.96:1
 * against white; as a logo fill that is fine, as a button label it is
 * unreadable, and a colour chosen for the first job should not silently take
 * on the second.
 */

/** The tokens a brand colour overrides. Everything else is left alone. */
const BRAND_TOKENS = ['--color-brand'] as const;

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

/**
 * Apply a brand colour to the document, or clear it.
 *
 * Set as an inline style on `<html>`, which beats the stylesheet's `:root`
 * rule without needing `!important` anywhere. Clearing removes the property
 * rather than writing the default back, so the stylesheet is the single
 * source of the default and this file never has to know what it is.
 */
export function applyBrandColor(color: string | null | undefined): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;

  if (!isValidBrandColor(color)) {
    BRAND_TOKENS.forEach((name) => root.style.removeProperty(name));
    return;
  }

  root.style.setProperty('--color-brand', color.trim());
}
