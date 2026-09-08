/**
 * The tenant brand colour, and the one thing it is allowed to change.
 *
 * The interface went entirely orange once, while the stylesheet said navy:
 * a saved brand colour was being derived into `--color-primary`, so every
 * button, link and active nav item took the logo's colour. The owner's
 * instruction is the opposite — navy actions, orange logo — and this pins it.
 */

import { afterEach, describe, expect, it } from 'vitest';

import { applyBrandColor, isValidBrandColor } from '@/lib/brand';

const root = () => document.documentElement.style;

afterEach(() => {
  applyBrandColor(null);
});

describe('applyBrandColor', () => {
  it('sets the logo mark colour', () => {
    applyBrandColor('#EF7220');
    expect(root().getPropertyValue('--color-brand')).toBe('#EF7220');
  });

  it('never touches the action colour, whatever the brand is', () => {
    applyBrandColor('#EF7220');
    expect(root().getPropertyValue('--color-primary')).toBe('');
    expect(root().getPropertyValue('--color-primary-foreground')).toBe('');
    expect(root().getPropertyValue('--color-accent')).toBe('');
  });

  it('clears back to the stylesheet default rather than writing one', () => {
    applyBrandColor('#123456');
    applyBrandColor(null);
    expect(root().getPropertyValue('--color-brand')).toBe('');
  });

  it.each(['', '   ', 'not a colour', '#GGGGGG', undefined, 42])(
    'ignores %p and clears any earlier value',
    (value) => {
      applyBrandColor('#123456');
      applyBrandColor(value as string);
      expect(root().getPropertyValue('--color-brand')).toBe('');
    },
  );
});

describe('isValidBrandColor', () => {
  it.each(['#EF7220', '#fff', '#0d6efd'])('accepts %s', (value) => {
    expect(isValidBrandColor(value)).toBe(true);
  });

  it.each(['orange-ish', '#EF722', '', null, 7])('rejects %p', (value) => {
    expect(isValidBrandColor(value)).toBe(false);
  });
});
