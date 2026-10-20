import type { UserRole } from '@/types/api';

/**
 * What each built-in role's navigation is called — the sidebar's accessible
 * name and its heading. Where a person lands is `homeFor` in
 * `components/navigation.ts`: the first entry of their own sidebar, so the
 * landing page and the menu never disagree and a configured role that lost a
 * capability never lands on a page it can no longer open.
 */
const WORKSPACE_LABEL: Record<UserRole, string> = {
  superadmin: 'Superadmin workspace',
  admin: 'Administrator workspace',
  manager: 'Manager workspace',
  counsellor: 'Admissions workspace',
  trainer: 'Trainer workspace',
  student: 'Student workspace',
};

function isUserRole(role: string | undefined): role is UserRole {
  return Boolean(role && role in WORKSPACE_LABEL);
}

export function workspaceLabel(role: string | undefined): string {
  return isUserRole(role) ? WORKSPACE_LABEL[role] : 'Your workspace';
}
