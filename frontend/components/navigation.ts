import type { LucideIcon } from "lucide-react";
import {
  Activity,
  Award,
  BarChart3,
  Bell,
  BookOpen,
  Building2,
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
  ListTodo,
  Megaphone,
  MessagesSquare,
  Palette,
  PenLine,
  Repeat,
  ScrollText,
  Send,
  Settings2,
  SlidersHorizontal,
  Sparkles,
  ToggleLeft,
  Trash2,
  TrendingUp,
  UserCircle2,
  UserPlus,
  Users,
  Wallet,
  UsersRound,
  Workflow,
  ShieldCheck,
  Inbox,
  Plug,
  Zap,
} from "lucide-react";

import { Capability } from "@/lib/capabilities";

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
  /**
   * Base roles whose access is resolved from an assignment or ownership check
   * on the destination rather than a platform-wide capability. This is only a
   * navigation hint: the destination still enforces the record-level scope.
   *
   * A configured custom role does not use this fallback. Its explicit
   * capability set is authoritative, so removing a capability also removes
   * the corresponding navigation item.
   */
  scopedRoles?: string[];
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
  {
    href: "/dashboard",
    label: "Dashboard",
    icon: LayoutDashboard,
    scopedRoles: ["student"],
  },
  {
    href: "/my-learning",
    label: "My learning",
    icon: BookOpenCheck,
    scopedRoles: ["student"],
  },
  { href: "/courses", label: "Courses", icon: BookOpen },
  {
    href: "/my-batches",
    label: "My batches",
    icon: Layers,
    scopedRoles: ["student"],
  },
  { href: "/my-fees", label: "My fees", icon: Wallet, scopedRoles: ["student"] },
  {
    href: "/my-assignments",
    label: "My assignments",
    icon: ClipboardList,
    scopedRoles: ["student"],
  },
  {
    href: "/my-projects",
    label: "My projects",
    icon: FolderKanban,
    scopedRoles: ["student"],
  },
  {
    href: "/exams",
    label: "Exams",
    icon: ScrollText,
    scopedRoles: ["student"],
  },
  { href: "/my-results", label: "My results", icon: Award, scopedRoles: ["student"] },
  {
    href: "/my-attendance",
    label: "My attendance",
    icon: CalendarCheck,
    scopedRoles: ["student"],
  },
  {
    href: "/my-progress",
    label: "My progress",
    icon: TrendingUp,
    scopedRoles: ["student"],
  },
  {
    href: "/my-activities",
    label: "My activities",
    icon: ListTodo,
    scopedRoles: ["student"],
  },
  {
    href: "/calendar",
    label: "Calendar",
    icon: CalendarDays,
    scopedRoles: ["student"],
  },
  { href: "/announcements", label: "Announcements", icon: Megaphone },
  {
    href: "/discussions",
    label: "Discussions",
    icon: MessagesSquare,
    scopedRoles: ["student"],
  },
  // Forms a counsellor or trainer sent them to fill.
  {
    href: "/forms",
    label: "Form inbox",
    icon: ClipboardCheck,
    scopedRoles: ["student"],
  },
  { href: "/notifications", label: "Notifications", icon: Bell },
  { href: "/profile", label: "My profile", icon: UserCircle2 },
];

// Shared entries, so a link reads and is gated the same in every sidebar.
const INBOX: NavItem[] = [
  { href: "/announcements", label: "Announcements", icon: Megaphone },
  { href: "/notifications", label: "Notifications", icon: Bell },
  { href: "/profile", label: "My profile", icon: UserCircle2 },
];
const FORM_INBOX: NavItem = { href: "/forms", label: "Form inbox", icon: ClipboardCheck };
const CALENDAR: NavItem = {
  // Every source on the calendar scopes itself to what the caller may see.
  href: "/calendar",
  label: "Calendar",
  icon: CalendarDays,
  scopedRoles: ["trainer", "counsellor", "manager", "admin", "superadmin"],
};
const FEES_HOME: NavItem = {
  href: "/fees",
  label: "Fees & collections",
  icon: Wallet,
  capability: Capability.feeViewAny,
};
/** Leads Meritto sent, waiting to be registered (17 October 2026). */
const READY_TO_ADMIT: NavItem = {
  href: "/admissions/ready",
  label: "Ready to admit",
  icon: Inbox,
  capability: Capability.studentCreate,
};
const TEACHING_ITEMS: NavItem[] = [
  {
    href: "/teaching/today",
    label: "Today's class",
    icon: Sparkles,
    capability: Capability.sessionManageAny,
    scopedRoles: ["trainer"],
  },
  {
    href: "/teaching",
    label: "Class schedule",
    icon: CalendarCheck,
    capability: Capability.sessionManageAny,
    scopedRoles: ["trainer"],
  },
];
const CLASSROOM_ITEMS: NavItem[] = [
  {
    href: "/teaching/assignments",
    label: "Assignments",
    icon: ClipboardList,
    capability: Capability.assignmentManageAny,
    scopedRoles: ["trainer"],
  },
  {
    href: "/teaching/assessments",
    label: "Weekly tests",
    icon: PenLine,
    capability: Capability.assessmentManageAny,
    scopedRoles: ["trainer"],
  },
  {
    href: "/teaching/projects",
    label: "Projects",
    icon: FolderKanban,
    capability: Capability.projectManageAny,
    scopedRoles: ["trainer"],
  },
  {
    href: "/teaching/exams",
    label: "Exams",
    icon: ScrollText,
    capability: Capability.examManageAny,
    scopedRoles: ["trainer"],
  },
  {
    href: "/teaching/questions",
    label: "Question bank",
    icon: LibraryBig,
    capability: Capability.questionViewAny,
    scopedRoles: ["trainer"],
  },
];

/**
 * The manager's sidebar: running the centre's teaching — its batches, its
 * trainers, its students — with the front office and the reports after it.
 * A manager may do everything a counsellor does (D-130); only the order and
 * the grouping differ, so the work each does most is the work at the top.
 */
export const MANAGER_NAV: NavGroup[] = [
  {
    items: [
      { href: "/manage", label: "Overview", icon: LayoutDashboard, capability: Capability.performanceViewAny },
      {
        href: "/activities",
        label: "Activities",
        icon: ListTodo,
        capability: Capability.activityViewAny,
      },
      CALENDAR,
    ],
  },
  {
    title: "Academics",
    items: [
      { href: "/admin/batches", label: "Batches", icon: Layers, capability: Capability.batchViewAny },
      {
        href: "/manage/batches",
        label: "Batch review",
        icon: BarChart3,
        capability: Capability.performanceViewAny,
      },
      { href: "/dsr", label: "Class reports", icon: FileText, capability: Capability.dsrViewAny },
      {
        href: "/admin/courses",
        label: "Courses",
        icon: LibraryBig,
        capability: Capability.courseViewAny,
      },
      {
        href: "/admin/completions",
        label: "Completions",
        icon: ClipboardCheck,
        capability: Capability.completionApprove,
      },
      {
        href: "/admin/certificates",
        label: "Certificates",
        icon: Award,
        capability: Capability.certificateManage,
      },
    ],
  },
  {
    title: "Staff",
    items: [
      {
        href: "/manage/trainers",
        label: "Trainers",
        icon: GraduationCap,
        capability: Capability.trainerViewAny,
      },
      {
        href: "/manage/reviews",
        label: "Reviews due",
        icon: ClipboardCheck,
        capability: Capability.performanceViewAny,
      },
      {
        href: "/requirements",
        label: "Trainer requirements",
        icon: Megaphone,
        capability: Capability.requirementManage,
      },
      { href: "/admin/users", label: "User accounts", icon: Users, capability: Capability.userViewAny },
    ],
  },
  {
    title: "Students",
    items: [
      {
        href: "/admin/students",
        label: "Students",
        icon: UsersRound,
        capability: Capability.studentViewAny,
      },
      FEES_HOME,
      {
        href: "/admissions",
        label: "Registrations",
        icon: ListChecks,
        capability: Capability.studentCreate,
      },
      {
        href: "/admissions/transfer",
        label: "Transfers",
        icon: Repeat,
        capability: Capability.enrolmentUpdateAny,
      },
      {
        href: "/admin/imports",
        label: "Data import",
        icon: Workflow,
        capability: Capability.dataImport,
      },
    ],
  },
  {
    title: "Front office",
    items: [
      READY_TO_ADMIT,
      {
        href: "/admissions/dashboard",
        label: "Admissions pipeline",
        icon: TrendingUp,
        capability: Capability.enrolmentCreate,
      },
      { href: "/enquiries", label: "Enquiries", icon: UserPlus, capability: Capability.enquiryViewAny },
      {
        href: "/admissions/new",
        label: "Register a student",
        icon: UserPlus,
        capability: Capability.studentCreate,
      },
      {
        href: "/admissions/batches",
        label: "Batch planning",
        icon: CalendarDays,
        capability: Capability.batchCreate,
      },
    ],
  },
  // A manager who also teaches keeps their own classes one click away.
  { title: "Teaching", items: [...TEACHING_ITEMS, ...CLASSROOM_ITEMS] },
  {
    title: "Reports",
    items: [
      {
        href: "/admin/reports",
        label: "Reports",
        icon: FileSpreadsheet,
        capability: Capability.reportViewAny,
      },
      { href: "/analytics", label: "Analytics", icon: TrendingUp, capability: Capability.reportViewAny },
      {
        href: "/admin/overview",
        label: "Institution overview",
        icon: BarChart3,
        capability: Capability.reportViewAny,
      },
    ],
  },
  { title: "My work", items: [FORM_INBOX, ...INBOX] },
];

/**
 * The counsellor's sidebar: the front desk. Leads first, then turning a lead
 * into a registered, placed, paying student, then the students themselves.
 * The academic screens a counsellor may also open (D-130) are there, lower
 * down, rather than gone.
 */
export const COUNSELLOR_NAV: NavGroup[] = [
  {
    items: [
      {
        // Their landing page is the pipeline, not an institution overview.
        href: "/admissions/dashboard",
        label: "Dashboard",
        icon: LayoutDashboard,
        capability: Capability.enrolmentCreate,
        scopedRoles: ["counsellor"],
      },
      {
        href: "/activities",
        label: "Follow-ups and tasks",
        icon: ListTodo,
        capability: Capability.activityViewAny,
      },
      CALENDAR,
    ],
  },
  {
    title: "Leads",
    items: [
      { href: "/enquiries", label: "Enquiries", icon: UserPlus, capability: Capability.enquiryViewAny },
      {
        href: "/forms/fill/enquiry",
        label: "New enquiry",
        icon: PenLine,
        capability: Capability.formAssign,
      },
      FORM_INBOX,
    ],
  },
  {
    title: "Admissions",
    items: [
      READY_TO_ADMIT,
      {
        href: "/admissions/new",
        label: "Register a student",
        icon: UserPlus,
        capability: Capability.studentCreate,
      },
      {
        href: "/admissions",
        label: "Registrations",
        icon: ListChecks,
        capability: Capability.studentCreate,
      },
      FEES_HOME,
      {
        href: "/admissions/batches",
        label: "Batch planning",
        icon: CalendarDays,
        capability: Capability.batchCreate,
      },
      {
        href: "/admissions/transfer",
        label: "Transfers",
        icon: Repeat,
        capability: Capability.enrolmentUpdateAny,
      },
      {
        href: "/admin/imports",
        label: "Data import",
        icon: Workflow,
        capability: Capability.dataImport,
      },
    ],
  },
  {
    title: "Students and batches",
    items: [
      {
        href: "/admin/students",
        label: "Students",
        icon: UsersRound,
        capability: Capability.studentViewAny,
      },
      { href: "/admin/batches", label: "Batches", icon: Layers, capability: Capability.batchViewAny },
      { href: "/dsr", label: "Class reports", icon: FileText, capability: Capability.dsrViewAny },
      { href: "/courses", label: "Course catalogue", icon: BookOpen },
    ],
  },
  {
    title: "Reports",
    items: [
      {
        href: "/admin/reports",
        label: "Reports",
        icon: FileSpreadsheet,
        capability: Capability.reportViewAny,
      },
      { href: "/analytics", label: "Analytics", icon: TrendingUp, capability: Capability.reportViewAny },
    ],
  },
  { title: "My work", items: INBOX },
];

/**
 * The trainer's sidebar: today's class first, then the classroom work they
 * set and mark, then their batches. Most entries are scoped to what they
 * teach, which the destination enforces.
 */
export const TRAINER_NAV: NavGroup[] = [
  {
    items: [
      {
        href: "/dashboard",
        label: "Dashboard",
        icon: LayoutDashboard,
        scopedRoles: ["trainer"],
      },
      ...TEACHING_ITEMS,
      CALENDAR,
    ],
  },
  { title: "Classroom", items: CLASSROOM_ITEMS },
  {
    title: "My batches",
    items: [
      {
        href: "/admin/batches",
        label: "Batches",
        icon: Layers,
        capability: Capability.batchViewAny,
        scopedRoles: ["trainer"],
      },
      {
        href: "/admin/courses",
        label: "Course management",
        icon: PenLine,
        capability: Capability.courseViewAny,
        scopedRoles: ["trainer"],
      },
      {
        href: "/teaching/work",
        label: "My work queue",
        icon: ListTodo,
        capability: Capability.activityViewAny,
        scopedRoles: ["trainer"],
      },
      {
        // Scoped to the batches they teach, like the other teaching pages.
        href: "/dsr",
        label: "Class reports",
        icon: FileText,
        capability: Capability.dsrViewAny,
        scopedRoles: ["trainer"],
      },
      {
        // A manager's ask of the teaching staff; trainers answer on it (D-132).
        href: "/requirements",
        label: "Trainer requirements",
        icon: Megaphone,
        capability: Capability.requirementManage,
        scopedRoles: ["trainer"],
      },
      {
        href: "/admin/reports",
        label: "Reports",
        icon: FileSpreadsheet,
        capability: Capability.reportViewAny,
        scopedRoles: ["trainer"],
      },
    ],
  },
  {
    title: "Community",
    items: [
      {
        href: "/discussions",
        label: "Discussions",
        icon: MessagesSquare,
        scopedRoles: ["trainer"],
      },
      FORM_INBOX,
      ...INBOX,
    ],
  },
];

/**
 * The administrator's sidebar, ranked by what the owner wants seen first
 * (14 September 2026): the activity review, then the manager's work, the
 * trainers, the counsellor's work, students and fees, batches and courses,
 * outcomes, the calendar, and only then the institution's own settings.
 * Managers, counsellors and trainers each have their own (above), grouped by
 * the job each does all day (15 October 2026); superadmins get this one with
 * governance raised (below).
 */
export const ADMIN_NAV: NavGroup[] = [
  {
    items: [
      {
        href: "/admin/activity",
        label: "Staff activity",
        icon: Activity,
        capability: Capability.auditView,
      },
      {
        href: "/admin/overview",
        label: "Institution overview",
        icon: BarChart3,
        capability: Capability.reportViewAny,
      },
      {
        href: "/analytics",
        label: "Analytics",
        icon: TrendingUp,
        capability: Capability.reportViewAny,
      },
    ],
  },
  {
    title: "Academic operations",
    items: [
      {
        href: "/activities",
        label: "Activities",
        icon: ListTodo,
        capability: Capability.activityViewAny,
      },
      {
        href: "/dsr",
        label: "Class reports",
        icon: FileText,
        capability: Capability.dsrViewAny,
      },
      {
        href: "/manage/batches",
        label: "Batch review",
        icon: Layers,
        capability: Capability.performanceViewAny,
      },
      {
        href: "/manage/reviews",
        label: "Reviews due",
        icon: ClipboardCheck,
        capability: Capability.performanceViewAny,
      },
      {
        href: "/requirements",
        label: "Trainer requirements",
        icon: Megaphone,
        capability: Capability.requirementManage,
      },
    ],
  },
  {
    title: "Trainers",
    items: [
      {
        href: "/manage/trainers",
        label: "Trainers",
        icon: GraduationCap,
        capability: Capability.trainerViewAny,
      },
    ],
  },
  {
    title: "Admissions",
    items: [
      READY_TO_ADMIT,
      {
        href: "/admissions/dashboard",
        label: "Admissions pipeline",
        icon: LayoutDashboard,
        capability: Capability.enrolmentCreate,
      },
      {
        href: "/fees",
        label: "Fees & collections",
        icon: Wallet,
        capability: Capability.feeViewAny,
      },
      {
        href: "/enquiries",
        label: "Enquiries",
        icon: UserPlus,
        capability: Capability.enquiryViewAny,
      },
      {
        href: "/admissions",
        label: "Registrations",
        icon: ListChecks,
        capability: Capability.studentCreate,
      },
      {
        href: "/admissions/new",
        label: "Register a student",
        icon: UserPlus,
        capability: Capability.studentCreate,
      },
      {
        href: "/admissions/batches",
        label: "Batch planning",
        icon: CalendarDays,
        capability: Capability.batchCreate,
      },
      {
        href: "/admissions/transfer",
        label: "Transfers",
        icon: Repeat,
        capability: Capability.enrolmentUpdateAny,
      },
    ],
  },
  {
    title: "Student records",
    items: [
      {
        href: "/admin/students",
        label: "Students",
        icon: UsersRound,
        capability: Capability.studentViewAny,
      },
      {
        href: "/admin/imports",
        label: "Data import",
        icon: Workflow,
        capability: Capability.dataImport,
      },
    ],
  },
  {
    title: "Batches and courses",
    items: [
      {
        href: "/admin/batches",
        label: "Batches",
        icon: Layers,
        capability: Capability.batchViewAny,
      },
      {
        href: "/admin/courses",
        label: "Courses",
        icon: LibraryBig,
        capability: Capability.courseViewAny,
      },
      { href: "/courses", label: "Course catalogue", icon: BookOpen },
    ],
  },
  {
    title: "Results and reports",
    items: [
      {
        href: "/admin/reports",
        label: "Reports",
        icon: FileSpreadsheet,
        capability: Capability.reportViewAny,
      },
      {
        href: "/admin/completions",
        label: "Completions",
        icon: ClipboardCheck,
        capability: Capability.completionApprove,
      },
      {
        href: "/admin/certificates",
        label: "Certificates",
        icon: Award,
        capability: Capability.certificateManage,
      },
    ],
  },
  {
    title: "Calendar",
    items: [
      {
        href: "/calendar",
        label: "Calendar",
        icon: CalendarDays,
        scopedRoles: ["admin", "superadmin"],
      },
    ],
  },
  {
    title: "Teaching",
    items: [
      {
        href: "/teaching/today",
        label: "Today's class",
        icon: Sparkles,
        capability: Capability.sessionManageAny,
      },
      {
        href: "/teaching",
        label: "Class schedule",
        icon: CalendarCheck,
        capability: Capability.sessionManageAny,
      },
      {
        href: "/teaching/assignments",
        label: "Assignments",
        icon: ClipboardList,
        capability: Capability.assignmentManageAny,
      },
      {
        href: "/teaching/assessments",
        label: "Weekly tests",
        icon: PenLine,
        capability: Capability.assessmentManageAny,
      },
      {
        href: "/teaching/projects",
        label: "Projects",
        icon: FolderKanban,
        capability: Capability.projectManageAny,
      },
      {
        href: "/teaching/exams",
        label: "Exams",
        icon: ScrollText,
        capability: Capability.examManageAny,
      },
      {
        href: "/teaching/questions",
        label: "Question bank",
        icon: LibraryBig,
        capability: Capability.questionViewAny,
      },
    ],
  },
  {
    title: "Institution",
    items: [
      {
        href: "/admin/users",
        label: "User accounts",
        icon: Users,
        capability: Capability.userViewAny,
      },
      {
        href: "/admin/roles",
        label: "Roles",
        icon: ShieldCheck,
        capability: Capability.roleView,
      },
      {
        href: "/admin/policies",
        label: "Rules and policies",
        icon: ToggleLeft,
        capability: Capability.policyView,
      },
      {
        href: "/admin/forms",
        label: "Form builder",
        icon: FileText,
        capability: Capability.formManage,
      },
      {
        href: "/admin/activity-types",
        label: "Activity types",
        icon: ClipboardCheck,
        capability: Capability.activityTypeManage,
      },
      {
        href: "/admin/automation",
        label: "Automation",
        icon: Zap,
        capability: Capability.automationManage,
      },
      {
        href: "/admin/integrations",
        label: "Integrations",
        icon: Plug,
        capability: Capability.integrationManage,
      },
      {
        href: "/admin/communication",
        label: "Message templates",
        icon: Send,
        capability: Capability.templateManage,
      },
      {
        href: "/admin/branches",
        label: "Centres",
        icon: Building2,
        capability: Capability.organisationViewAny,
      },
      {
        href: "/admin/settings",
        label: "Settings",
        icon: SlidersHorizontal,
        capability: Capability.settingsManage,
      },
      {
        href: "/admin/academics",
        label: "Academic rules",
        icon: Settings2,
        capability: Capability.academicConfigure,
      },
      {
        href: "/admin/branding",
        label: "Branding",
        icon: Palette,
        capability: Capability.platformConfigure,
      },
      {
        href: "/admin/recovery",
        label: "Deleted records",
        icon: Trash2,
        capability: Capability.recordViewDeleted,
      },
    ],
  },
  {
    title: "My work",
    items: [
      { href: "/announcements", label: "Announcements", icon: Megaphone },
      { href: "/forms", label: "Form inbox", icon: ClipboardCheck },
      { href: "/notifications", label: "Notifications", icon: Bell },
      { href: "/profile", label: "My profile", icon: UserCircle2 },
    ],
  },
];

/** Superadmins see the same permitted destinations as administrators, but
 * governance is raised immediately below the overview instead of buried near
 * the foot of a day-to-day operations menu. */
export const SUPERADMIN_NAV: NavGroup[] = [
  ...ADMIN_NAV.filter((group) => !group.title),
  ...ADMIN_NAV.filter((group) => group.title === "Institution").map((group) => ({
    ...group,
    title: "Platform and governance",
  })),
  ...ADMIN_NAV.filter((group) => group.title && group.title !== "Institution"),
];

function studentItem(href: string): NavItem {
  const item = STUDENT_NAV.find((candidate) => candidate.href === href);
  if (!item) throw new Error(`No student navigation item registered for ${href}`);
  return item;
}

/** The student's links, grouped for the sidebar: learning, what is due, how
 *  they are doing, then the community and their own account. */
export const STUDENT_NAV_GROUPS: NavGroup[] = [
  {
    items: [studentItem("/dashboard"), studentItem("/my-learning")],
  },
  {
    title: "To do",
    items: [
      studentItem("/my-assignments"),
      studentItem("/my-projects"),
      studentItem("/exams"),
      studentItem("/my-activities"),
      studentItem("/forms"),
    ],
  },
  {
    title: "My progress",
    items: [
      studentItem("/my-results"),
      studentItem("/my-attendance"),
      studentItem("/my-progress"),
      studentItem("/my-fees"),
      studentItem("/my-batches"),
    ],
  },
  {
    title: "Explore and connect",
    items: [
      studentItem("/courses"),
      studentItem("/calendar"),
      studentItem("/announcements"),
      studentItem("/discussions"),
    ],
  },
  {
    title: "My account",
    items: [studentItem("/notifications"), studentItem("/profile")],
  },
];

/** Which sidebar a role gets. A configured role takes its kind's sidebar,
 *  filtered by its own capabilities (`isVisible`). A signed-out visitor or an
 *  unknown role gets the student's flat list, which is itself role-scoped. */
export function navFor(role: string | undefined): NavGroup[] {
  switch (role) {
    case "superadmin":
      return SUPERADMIN_NAV;
    case "admin":
      return ADMIN_NAV;
    case "manager":
      return MANAGER_NAV;
    case "counsellor":
      return COUNSELLOR_NAV;
    case "trainer":
      return TRAINER_NAV;
    case "student":
      return STUDENT_NAV_GROUPS;
    default:
      return [{ items: STUDENT_NAV }];
  }
}

export const STAFF_ROLES = [
  "superadmin",
  "admin",
  "manager",
  "counsellor",
  "trainer",
];

/** Whether this person should see a given entry. */
export function isVisible(
  item: NavItem,
  user: {
    role: string;
    capabilities: string[];
    custom_role?: string | null;
  } | null,
): boolean {
  if (!item.capability) {
    return !item.scopedRoles || Boolean(user && item.scopedRoles.includes(user.role));
  }
  if (user?.capabilities.includes(item.capability)) return true;
  // Assignment-scoped fallbacks are part of the built-in role contract. A
  // configured role's explicit capability list replaces that contract, so a
  // role fallback must not silently restore a permission that was removed.
  return Boolean(
    user && !user.custom_role && item.scopedRoles?.includes(user.role),
  );
}

/**
 * Where a signed-in person starts: the first entry their own navigation
 * offers them. Deriving it from the sidebar keeps the two in step — the
 * owner's ranking of the administrator's menu is also their landing page —
 * and a configured role that lost a capability never lands on a page it can
 * no longer open.
 */
export function homeFor(
  user: { role: string; capabilities: string[]; custom_role?: string | null } | null,
): string {
  if (!user) return "/login";
  if (!STAFF_ROLES.includes(user.role)) return "/dashboard";
  for (const group of navFor(user.role)) {
    const first = group.items.find((item) => isVisible(item, user));
    if (first) return first.href;
  }
  return "/profile";
}

/**
 * A `?next=` return path, accepted only when it stays on this site. Anything
 * else — another origin, a protocol-relative `//host`, a backslash trick, or
 * the sign-in page itself — falls back to `null`, so the link in an email can
 * bring somebody back to where they were going and never anywhere else.
 */
export function safeReturnPath(value: string | null | undefined): string | null {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return null;
  if (value.includes("\\") || [...value].some((ch) => ch.charCodeAt(0) < 32)) return null;
  const path = value.split(/[?#]/)[0] ?? value;
  if (path === "/login" || path.startsWith("/login/")) return null;
  return value;
}
