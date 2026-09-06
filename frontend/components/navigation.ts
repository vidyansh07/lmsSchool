import { Capability } from '@/lib/capabilities';

/**
 * What appears in the navigation, and for whom.
 *
 * Presentational only. Which links a person sees comes from the capability list
 * the server returned; which requests succeed is decided by the server on every
 * call. Hiding a link is a courtesy to the person using the product, never a
 * permission.
 *
 * Grouped by the job somebody is doing rather than by the system's internal
 * structure. "Users", "Students" and "Trainers" are three tables and one task —
 * looking after people — so they sit together, and an administrator hunting for
 * a student does not have to know which of the three screens owns them.
 */
export interface NavItem {
  href: string;
  label: string;
  capability?: string;
  /** Show to these roles as well, whose rights come from assignment rather than
   *  from a platform-wide capability. */
  roles?: string[];
}

export interface NavGroup {
  /** Absent for the first group, which needs no heading above the first link. */
  title?: string;
  items: NavItem[];
}

/**
 * The student's world: a short list, so it stays a top bar.
 *
 * Most entries are scoped to the student role even though only students see
 * this layout — because a signed-out visitor sees it too, and "My assignments"
 * on a public page is both meaningless and a small hint about what the product
 * holds. What remains for a visitor is the catalogue and the pages that ask
 * them to sign in.
 */
export const STUDENT_NAV: NavItem[] = [
  { href: '/dashboard', label: 'Dashboard', roles: ['student'] },
  { href: '/my-learning', label: 'My learning', roles: ['student'] },
  { href: '/courses', label: 'Courses' },
  { href: '/my-batches', label: 'My batches', roles: ['student'] },
  { href: '/my-assignments', label: 'My assignments', roles: ['student'] },
  { href: '/my-projects', label: 'My projects', roles: ['student'] },
  { href: '/exams', label: 'Examinations', roles: ['student'] },
  { href: '/my-results', label: 'My results', roles: ['student'] },
  { href: '/my-attendance', label: 'My attendance', roles: ['student'] },
  { href: '/my-progress', label: 'My progress', roles: ['student'] },
  { href: '/calendar', label: 'Calendar', roles: ['student'] },
  { href: '/announcements', label: 'Announcements' },
  { href: '/discussions', label: 'Discussions', roles: ['student'] },
  { href: '/notifications', label: 'Notifications' },
  { href: '/profile', label: 'My profile' },
];

/** Everybody who runs the institution rather than studying at it. */
export const STAFF_NAV: NavGroup[] = [
  {
    items: [
      { href: '/dashboard', label: 'Dashboard', roles: ['trainer'] },
      { href: '/admin/overview', label: 'Overview', capability: Capability.reportViewAny },
    ],
  },
  {
    title: 'Teaching',
    items: [
      {
        href: '/teaching',
        // No apostrophe: a typographic one reads better and makes every locator
        // that names this link — a test, a screen reader script, a search box —
        // depend on which character was typed.
        label: 'Classes today',
        capability: Capability.sessionManageAny,
        roles: ['trainer'],
      },
      {
        href: '/teaching/assignments',
        label: 'Assignments',
        capability: Capability.assignmentManageAny,
        roles: ['trainer'],
      },
      {
        href: '/teaching/assessments',
        label: 'Weekly tests',
        capability: Capability.assessmentManageAny,
        roles: ['trainer'],
      },
      {
        href: '/teaching/projects',
        label: 'Projects',
        capability: Capability.projectManageAny,
        roles: ['trainer'],
      },
      {
        href: '/teaching/exams',
        label: 'Examinations',
        capability: Capability.examManageAny,
        roles: ['trainer'],
      },
      {
        href: '/teaching/questions',
        label: 'Question bank',
        capability: Capability.questionViewAny,
        roles: ['trainer'],
      },
    ],
  },
  {
    title: 'People',
    items: [
      { href: '/admin/users', label: 'Users', capability: Capability.userViewAny },
      { href: '/admin/students', label: 'Students', capability: Capability.studentViewAny },
      { href: '/admin/trainers', label: 'Trainers', capability: Capability.trainerViewAny },
    ],
  },
  {
    title: 'Courses and batches',
    items: [
      {
        href: '/admin/courses',
        label: 'Authoring',
        capability: Capability.courseViewAny,
        roles: ['trainer'],
      },
      {
        href: '/admin/batches',
        label: 'Batches',
        capability: Capability.batchViewAny,
        roles: ['trainer'],
      },
      { href: '/courses', label: 'Catalogue' },
    ],
  },
  {
    title: 'Outcomes',
    items: [
      {
        href: '/admin/completions',
        label: 'Completions',
        capability: Capability.completionApprove,
      },
      {
        href: '/admin/certificates',
        label: 'Certificates',
        capability: Capability.certificateManage,
      },
      {
        href: '/admin/reports',
        label: 'Reports',
        capability: Capability.reportViewAny,
        roles: ['trainer'],
      },
      { href: '/admin/imports', label: 'Bulk import', capability: Capability.dataImport },
    ],
  },
  {
    title: 'Institution',
    items: [
      {
        href: '/admin/academics',
        label: 'Academic rules',
        capability: Capability.academicConfigure,
      },
      { href: '/calendar', label: 'Calendar', roles: ['trainer'] },
    ],
  },
  {
    title: 'Everyday',
    items: [
      { href: '/announcements', label: 'Announcements' },
      { href: '/discussions', label: 'Discussions', roles: ['trainer'] },
      { href: '/notifications', label: 'Notifications' },
      { href: '/profile', label: 'My profile' },
    ],
  },
];

/** Roles that get the sidebar. Students get the shorter top bar. */
export const STAFF_ROLES = ['superadmin', 'admin', 'manager', 'counsellor', 'trainer'];

/** Whether this person should see a given entry. */
export function isVisible(
  item: NavItem,
  user: { role: string; capabilities: string[] } | null,
): boolean {
  if (!item.capability) {
    return !item.roles || Boolean(user && item.roles.includes(user.role));
  }
  if (user?.capabilities.includes(item.capability)) return true;
  return Boolean(user && item.roles?.includes(user.role));
}
