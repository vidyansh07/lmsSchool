import { describe, expect, it } from 'vitest';

import { homeFor } from '@/components/navigation';
import { workspaceLabel } from '@/lib/workspace';

describe('role workspaces', () => {
  it.each([
    ['superadmin', 'Superadmin workspace'],
    ['admin', 'Administrator workspace'],
    ['manager', 'Manager workspace'],
    ['counsellor', 'Admissions workspace'],
    ['trainer', 'Trainer workspace'],
    ['student', 'Student workspace'],
  ])('names the %s navigation', (role, expected) => {
    expect(workspaceLabel(role)).toBe(expected);
  });

  it('uses a neutral name for an unknown role', () => {
    expect(workspaceLabel('future-role')).toBe('Your workspace');
  });

  it('does not restore a dashboard capability removed from a custom role', () => {
    const manager = homeFor({
      role: 'manager',
      custom_role: 'admissions-lead',
      capabilities: ['enquiry.view_any'],
    });
    expect(manager).not.toBe('/manage');

    const admin = homeFor({ role: 'admin', custom_role: 'restricted-auditor', capabilities: [] });
    expect(admin).not.toBe('/admin/activity');
    expect(admin).not.toBe('/admin/overview');
  });
});
