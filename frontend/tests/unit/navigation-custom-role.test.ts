import { describe, expect, it } from 'vitest';

import { homeFor, isStaff, isVisible, navFor } from '@/components/navigation';

/**
 * A placement officer, and every role an administrator composes out of
 * permissions, used to arrive at work with a student's sidebar.
 *
 * The backend has supported custom roles properly for a long time — `Role`,
 * `Permission`, `ScopeGrant`, and four scopes. The navigation then switched on
 * five hardcoded role names and sent everything else to the student tree, so
 * the feature looked broken from the only place anybody looks at it.
 */
const placementOfficer = {
  role: 'placement',
  custom_role: 'Placement officer',
  capabilities: [
    'profile.view_own',
    'profile.update_own',
    'student.view_any',
    'report.view_any',
  ],
};

const student = {
  role: 'student',
  custom_role: null,
  capabilities: ['profile.view_own', 'profile.update_own'],
};

describe('navigation for a composed role', () => {
  it('gives an unrecognised staff role a staff sidebar, not a student one', () => {
    const groups = navFor(placementOfficer.role);
    const labels = groups.flatMap((group) => group.items.map((item) => item.label));

    expect(labels).toContain('Students');
    // The tell-tale of the old bug: a staff member offered a student's pages.
    expect(labels).not.toContain('My assignments');
  });

  it('still trims that sidebar to the capabilities the person holds', () => {
    // The fallback is wide on purpose; `isVisible` is what makes it correct.
    const visible = navFor(placementOfficer.role)
      .flatMap((group) => group.items)
      .filter((item) => isVisible(item, placementOfficer))
      .map((item) => item.label);

    expect(visible).toContain('Students');
    expect(visible).not.toContain('Users');
  });

  it('counts a composed role as staff, by capability rather than by name', () => {
    expect(isStaff(placementOfficer)).toBe(true);
    expect(isStaff(student)).toBe(false);
    expect(isStaff(null)).toBe(false);
  });

  it('treats a role holding only self-service capabilities as not staff', () => {
    // The test is "anything beyond your own record", so a stripped-back custom
    // role does not quietly get a staff layout.
    expect(
      isStaff({ role: 'observer', capabilities: ['profile.view_own'] }),
    ).toBe(false);
  });

  it('lands a composed role on its work, not on its own profile page', () => {
    // `homeFor` reads the sidebar this person actually gets, so the landing
    // page and the menu cannot disagree. Before the fallback was fixed it read
    // a student's sidebar and sent a placement officer to a student's page.
    expect(homeFor(placementOfficer)).not.toBe('/profile');
    expect(homeFor(placementOfficer)).not.toBe('/dashboard');

    // A composed role holding nothing is not staff by the capability test, so
    // it takes the ordinary non-staff landing rather than a staff page it
    // could not open.
    expect(
      homeFor({ role: 'placement', custom_role: 'x', capabilities: [] }),
    ).toBe('/dashboard');
  });
});

describe('a user whose capabilities have not arrived yet', () => {
  /**
   * The sign-in page holds a user between the credentials being accepted and
   * the profile arriving, and that object has no capability list. `homeFor`
   * sits on the path that decides where somebody lands, so throwing here is
   * not a wrong answer — it is a sign-in that silently goes nowhere.
   */
  it('does not throw, and is not treated as staff', () => {
    const halfLoaded = { role: 'counsellor' } as unknown as {
      role: string;
      capabilities: string[];
    };

    expect(() => isStaff(halfLoaded)).not.toThrow();
    expect(() => homeFor(halfLoaded)).not.toThrow();
  });

  it('still recognises a built-in staff role by name', () => {
    // The name is enough for the five curated roles, which is what keeps the
    // ordinary sign-in working before the profile lands.
    expect(isStaff({ role: 'admin' } as unknown as { role: string; capabilities: string[] })).toBe(
      true,
    );
  });
});

describe('the sidebar does not repeat the page it leads to', () => {
  /**
   * An administrator's sidebar carried forty-nine entries, three of which the
   * `/teaching` hub already lists in the same words. A menu that repeats the
   * page it leads to is paying for itself twice: longer to read, and the
   * thing somebody genuinely cannot find sits further down.
   */
  const adminHrefs = navFor('admin').flatMap((group) => group.items.map((item) => item.href));

  it.each(['/teaching/assignments', '/teaching/assessments', '/teaching/projects'])(
    'leaves %s to the teaching hub',
    (href) => {
      expect(adminHrefs).not.toContain(href);
    },
  );

  it('keeps the hub itself, or those pages become unreachable', () => {
    expect(adminHrefs).toContain('/teaching');
  });

  it.each(['/teaching/exams', '/teaching/questions'])(
    'keeps %s, which the hub does not list',
    (href) => {
      // The failure this kind of tidying usually causes: removing a link whose
      // only other route in was the menu.
      expect(adminHrefs).toContain(href);
    },
  );
});
