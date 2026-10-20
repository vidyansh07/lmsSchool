import { describe, expect, it } from 'vitest';

import { isStaff, isVisible, navFor } from '@/components/navigation';
import { workspaceHomeForUser } from '@/lib/workspace';

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
    expect(workspaceHomeForUser(placementOfficer)).toBe('/admin/students');
    expect(
      workspaceHomeForUser({ role: 'placement', custom_role: 'x', capabilities: [] }),
    ).toBe('/profile');
  });
});
