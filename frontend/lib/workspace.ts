import type { UserRole } from '@/types/api';

/**
 * The first useful screen for each built-in role.
 *
 * `/` used to be an old phase-one welcome page, so signing in took every
 * person away from the operational page built for their job. Keep this map in
 * one place: login, the root redirect and any future "back to workspace"
 * control must agree about what home means.
 */
const WORKSPACE_HOME: Record<UserRole, string> = {
  superadmin: '/admin/overview',
  admin: '/admin/overview',
  manager: '/manage',
  counsellor: '/admissions/dashboard',
  trainer: '/dashboard',
  student: '/dashboard',
};

const WORKSPACE_LABEL: Record<UserRole, string> = {
  superadmin: 'Superadmin workspace',
  admin: 'Administrator workspace',
  manager: 'Manager workspace',
  counsellor: 'Admissions workspace',
  trainer: 'Trainer workspace',
  student: 'Student workspace',
};

function isUserRole(role: string | undefined): role is UserRole {
  return Boolean(role && role in WORKSPACE_HOME);
}

export function workspaceHome(role: string | undefined): string {
  return isUserRole(role) ? WORKSPACE_HOME[role] : '/dashboard';
}

/**
 * Resolve a useful landing page without restoring permissions removed from a
 * configured role. Built-in roles retain their stable job home; a custom role
 * uses the first matching capability in that job's normal priority order.
 */
export function workspaceHomeForUser(user: {
  role: string;
  capabilities: readonly string[];
  custom_role?: string | null;
}): string {
  if (!user.custom_role) return workspaceHome(user.role);

  const can = (capability: string) => user.capabilities.includes(capability);

  switch (user.role) {
    case 'superadmin':
    case 'admin':
      if (can('audit.view')) return '/admin/activity';
      if (can('report.view_any')) return '/admin/overview';
      if (can('student.view_any')) return '/admin/students';
      if (can('user.view_any')) return '/admin/users';
      if (can('fee.view_any')) return '/fees';
      break;
    case 'manager':
      if (can('performance.view_any')) return '/manage';
      if (can('report.view_any')) return '/analytics';
      if (can('trainer.view_any')) return '/manage/trainers';
      if (can('fee.view_any')) return '/fees';
      if (can('student.view_any')) return '/admin/students';
      if (can('enquiry.view_any')) return '/enquiries';
      break;
    case 'counsellor':
      if (can('enrolment.create')) return '/admissions/dashboard';
      if (can('enquiry.view_any')) return '/enquiries';
      if (can('fee.view_any')) return '/fees';
      if (can('student.view_any')) return '/admin/students';
      break;
    case 'trainer':
    case 'student':
      return '/dashboard';
  }

  return '/profile';
}

export function workspaceLabel(role: string | undefined): string {
  return isUserRole(role) ? WORKSPACE_LABEL[role] : 'Your workspace';
}
