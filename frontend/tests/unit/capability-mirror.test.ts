/**
 * `lib/capabilities.ts` and `lib/labels.ts` claim to mirror the backend. This
 * checks that they do.
 *
 * The claim was a comment, and a comment cannot fail. Drift here is quiet in
 * the worst way: a capability string with a typo simply never matches, so the
 * control it guards is hidden from everybody forever, on every screen, with no
 * error anywhere. Nobody reports a button they have never seen.
 *
 * So the backend's own source is the fixture. It is read and parsed rather than
 * duplicated, because a duplicated list is the thing being guarded against.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import { Capability } from '@/lib/capabilities';
import { ROLE_LABEL } from '@/lib/labels';

// Resolved from the Vitest root (`frontend/`) rather than from `import.meta.url`,
// which is not a file URL under the jsdom environment.
const ROLES_PY = resolve(process.cwd(), '../backend/apps/accounts/roles.py');

/**
 * Pull the values out of one `models.TextChoices` class.
 *
 * Members look like `NAME = "value", _("Label")`, sometimes wrapped across
 * lines when the label is long. Only the string literal that comes first on the
 * right-hand side is the stored value, which is the part the API speaks.
 */
function choiceValues(source: string, className: string): string[] {
  const start = source.indexOf(`class ${className}(models.TextChoices):`);
  if (start === -1) throw new Error(`${className} not found in roles.py`);

  const rest = source.slice(start);
  const end = rest.indexOf('\nclass ', 1);
  const body = end === -1 ? rest : rest.slice(0, end);

  return [...body.matchAll(/^\s{4}[A-Z][A-Z0-9_]*\s*=\s*\(?\s*"([^"]+)"/gm)].map(
    (match) => match[1] as string,
  );
}

const source = readFileSync(ROLES_PY, 'utf8');
const backendCapabilities = choiceValues(source, 'Capability');
const backendRoles = choiceValues(source, 'UserRole');

describe('the capability mirror', () => {
  it('parsed something, so a parser change cannot make this vacuous', () => {
    expect(backendCapabilities.length).toBeGreaterThan(40);
    expect(backendRoles.length).toBeGreaterThan(4);
  });

  it('names no capability the backend does not define', () => {
    // This is the direction that hides controls: a typo here matches nothing.
    const unknown = Object.values(Capability).filter(
      (value) => !backendCapabilities.includes(value),
    );
    expect(unknown).toEqual([]);
  });

  it('covers every capability the backend defines', () => {
    // The other direction is a weaker failure — a capability the interface has
    // no use for yet — but leaving it out silently is how the two lists start
    // to drift, and adding the constant costs one line.
    const missing = backendCapabilities.filter(
      (value) => !Object.values(Capability).includes(value as never),
    );
    expect(missing).toEqual([]);
  });
});

describe('the role mirror', () => {
  it('matches the backend role list exactly, in both directions', () => {
    expect([...Object.keys(ROLE_LABEL)].sort()).toEqual([...backendRoles].sort());
  });

  it('gives every role a label a person would recognise', () => {
    for (const [role, label] of Object.entries(ROLE_LABEL)) {
      expect(label, role).toBeTruthy();
      expect(label, role).not.toMatch(/undefined|NaN|null/i);
    }
  });
});
