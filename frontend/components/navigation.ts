import type { LucideIcon } from 'lucide-react';
import {
  Award,
  BarChart3,
  Bell,
  BookOpen,
  BookOpenCheck,
  CalendarCheck,
  CalendarDays,
  ClipboardCheck,
  ClipboardList,
  FileSpreadsheet,
  FileText,
  FolderKanban,
  GraduationCap,
  LayoutDashboard,
  Layers,
  LibraryBig,
  ListChecks,
  Megaphone,
  MessagesSquare,
  Palette,
  PenLine,
  Repeat,
  ScrollText,
  Settings2,
  Sparkles,
  Trash2,
  TrendingUp,
  UserCircle2,
  UserPlus,
  Users,
  Wallet,
  UsersRound,
  Workflow,
} from 'lucide-react';

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
  /** Drawn beside the label. Every item has one: a list where some links
   *  have icons and some do not reads as half-finished, and the icon is what
   *  a person scanning thirty links actually recognises. */
  icon: LucideIcon;
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
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, roles: ['student'] },
  { href: '/my-learning', label: 'My learning', icon: BookOpenCheck, roles: ['student'] },
  { href: '/courses', label: 'Courses', icon: BookOpen },
  { href: '/my-batches', label: 'My batches', icon: Layers, roles: ['student'] },
  { href: '/my-fees', label: 'My fees', icon: Wallet, roles: ['student'] },
  { href: '/my-assignments', label: 'My assignments', icon: ClipboardList, roles: ['student'] },
  { href: '/my-projects', label: 'My projects', icon: FolderKanban, roles: ['student'] },
  { href: '/exams', label: 'Examinations', icon: ScrollText, roles: ['student'] },
  { href: '/my-results', label: 'My results', icon: Award, roles: ['student'] },
  { href: '/my-attendance', label: 'My attendance', icon: CalendarCheck, roles: ['student'] },
  { href: '/my-progress', label: 'My progress', icon: TrendingUp, roles: ['student'] },
  { href: '/calendar', label: 'Calendar', icon: CalendarDays, roles: ['student'] },
  { href: '/announcements', label: 'Announcements', icon: Megaphone },
  { href: '/discussions', label: 'Discussions', icon: MessagesSquare, roles: ['student'] },
  { href: '/notifications', label: 'Notifications', icon: Bell },
  { href: '/profile', label: 'My profile', icon: UserCircle2 },
];

/** Everybody who runs the institution rather than studying at it. */
export const STAFF_NAV: NavGroup[] = [
  {
    items: [
      { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, roles: ['trainer'] },
      // A counsellor's landing page is their pipeline, not an institution
      // overview they hold no capability to read.
      {
        href: '/admissions/dashboard',
        label: 'Dashboard',
        icon: LayoutDashboard,
        capability: Capability.enrolmentCreate,
        roles: ['counsellor'],
      },
      { href: '/admin/overview', label: 'Overview', icon: BarChart3, capability: Capability.reportViewAny },
    ],
  },
  {
    // The client asked for two manager pages that drill all the way down,
    // rather than a dashboard of widgets. They are grouped as "Review" because
    // that is the job: looking at how a batch or a trainer is doing.
    title: 'Review',
    items: [
      {
        href: '/manage/batches',
        label: 'Batch review',
        icon: Layers,
        capability: Capability.performanceViewAny,
      },
      {
        href: '/manage/trainers',
        label: 'Trainer review',
        icon: GraduationCap,
        capability: Capability.performanceViewAny,
      },
      {
        href: '/dsr',
        label: 'Daily reports',
        icon: FileText,
        capability: Capability.dsrViewAny,
      },
    ],
  },
  {
    // Admissions is one job done many times a day, so its screens sit together
    // and in the order somebody works through them.
    title: 'Admissions',
    items: [
      {
        href: '/admissions',
        label: 'Registrations',
        icon: ListChecks,
        capability: Capability.studentCreate,
      },
      {
        href: '/admissions/new',
        label: 'Register a student',
        icon: UserPlus,
        capability: Capability.studentCreate,
      },
      {
        href: '/admissions/batches',
        label: 'Batch planning',
        icon: CalendarDays,
        capability: Capability.batchCreate,
      },
      {
        href: '/admissions/transfer',
        label: 'Transfers',
        icon: Repeat,
        capability: Capability.enrolmentUpdateAny,
      },
    ],
  },
  {
    title: 'Teaching',
    items: [
      {
        href: '/teaching/today',
        label: 'Today',
        icon: Sparkles,
        capability: Capability.sessionManageAny,
        roles: ['trainer'],
      },
      {
        href: '/teaching',
        icon: CalendarCheck,
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
        icon: ClipboardList,
        capability: Capability.assignmentManageAny,
        roles: ['trainer'],
      },
      {
        href: '/teaching/assessments',
        label: 'Weekly tests',
        icon: ClipboardCheck,
        capability: Capability.assessmentManageAny,
        roles: ['trainer'],
      },
      {
        href: '/teaching/projects',
        label: 'Projects',
        icon: FolderKanban,
        capability: Capability.projectManageAny,
        roles: ['trainer'],
      },
      {
        href: '/teaching/exams',
        label: 'Examinations',
        icon: ScrollText,
        capability: Capability.examManageAny,
        roles: ['trainer'],
      },
      {
        href: '/teaching/questions',
        label: 'Question bank',
        icon: LibraryBig,
        capability: Capability.questionViewAny,
        roles: ['trainer'],
      },
    ],
  },
  {
    title: 'People',
    items: [
      { href: '/admin/users', label: 'Users', icon: Users, capability: Capability.userViewAny },
      { href: '/admin/students', label: 'Students', icon: UsersRound, capability: Capability.studentViewAny },
      { href: '/admin/trainers', label: 'Trainers', icon: GraduationCap, capability: Capability.trainerViewAny },
    ],
  },
  {
    title: 'Courses and batches',
    items: [
      {
        href: '/admin/courses',
        label: 'Authoring',
        icon: PenLine,
        capability: Capability.courseViewAny,
        roles: ['trainer'],
      },
      {
        href: '/admin/batches',
        label: 'Batches',
        icon: Layers,
        capability: Capability.batchViewAny,
        roles: ['trainer'],
      },
      { href: '/courses', label: 'Catalogue', icon: BookOpen },
    ],
  },
  {
    title: 'Outcomes',
    items: [
      {
        href: '/admin/completions',
        label: 'Completions',
        icon: ClipboardCheck,
        capability: Capability.completionApprove,
      },
      {
        href: '/admin/certificates',
        label: 'Certificates',
        icon: Award,
        capability: Capability.certificateManage,
      },
      {
        href: '/admin/reports',
        label: 'Reports',
        icon: FileSpreadsheet,
        capability: Capability.reportViewAny,
        roles: ['trainer'],
      },
      { href: '/admin/imports', label: 'Bulk import', icon: Workflow, capability: Capability.dataImport },
    ],
  },
  {
    title: 'Institution',
    items: [
      {
        href: '/admin/academics',
        label: 'Academic rules',
        icon: Settings2,
        capability: Capability.academicConfigure,
      },
      {
        href: '/admin/recovery',
        label: 'Deleted records',
        icon: Trash2,
        capability: Capability.recordViewDeleted,
      },
      {
        href: '/admin/branding',
        label: 'Branding',
        icon: Palette,
        capability: Capability.platformConfigure,
      },
      // Every source on the calendar scopes itself to what the caller may see,
      // so a manager gets every batch's classes and milestones and a trainer
      // only theirs. The link was trainer-only by oversight, not by design.
      {
        href: '/calendar',
        label: 'Calendar',
        icon: CalendarDays,
        roles: ['trainer', 'counsellor', 'manager', 'admin', 'superadmin'],
      },
    ],
  },
  {
    title: 'Everyday',
    items: [
      { href: '/announcements', label: 'Announcements', icon: Megaphone },
      { href: '/discussions', label: 'Discussions', icon: MessagesSquare, roles: ['trainer'] },
      { href: '/notifications', label: 'Notifications', icon: Bell },
      { href: '/profile', label: 'My profile', icon: UserCircle2 },
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
