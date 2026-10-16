import { describe, expect, it } from 'vitest';

import { workspaceHome, workspaceHomeForUser, workspaceLabel } from '@/lib/workspace';

describe('role workspaces', () => {
  it.each([
    ['superadmin', '/admin/overview'],
    ['admin', '/admin/overview'],
    ['manager', '/manage'],
    ['counsellor', '/admissions/dashboard'],
    ['trainer', '/dashboard'],
    ['student', '/dashboard'],
  ])('routes %s to its operational home', (role, expected) => {
    expect(workspaceHome(role)).toBe(expected);
  });

  it('uses a safe signed-in fallback for an unknown role', () => {
    expect(workspaceHome('future-role')).toBe('/dashboard');
    expect(workspaceLabel('future-role')).toBe('Your workspace');
  });

  it('does not restore a dashboard capability removed from a custom role', () => {
    expect(
      workspaceHomeForUser({
        role: 'manager',
        custom_role: 'admissions-lead',
        capabilities: ['enquiry.view_any'],
      }),
    ).toBe('/enquiries');

    expect(
      workspaceHomeForUser({
        role: 'admin',
        custom_role: 'restricted-auditor',
        capabilities: [],
      }),
    ).toBe('/profile');
  });
});
