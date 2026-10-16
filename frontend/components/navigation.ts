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

/** Everybody who runs the institution rather than studying at it. */
export const STAFF_NAV: NavGroup[] = [
  {
    items: [
      {
        href: "/dashboard",
        label: "Dashboard",
        icon: LayoutDashboard,
        scopedRoles: ["trainer"],
      },
      // A counsellor's landing page is their pipeline, not an institution
      // overview they hold no capability to read.
      {
        href: "/admissions/dashboard",
        label: "Dashboard",
        icon: LayoutDashboard,
        capability: Capability.enrolmentCreate,
        scopedRoles: ["counsellor"],
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
    // The manager pages drill into the institution's day-to-day academic work
    // rather than presenting another dashboard of widgets.
    title: "Academic operations",
    items: [
      {
        href: "/activities",
        label: "Activities",
        icon: ListTodo,
        capability: Capability.activityViewAny,
        scopedRoles: ["trainer"],
      },
      {
        href: "/manage/batches",
        label: "Batch review",
        icon: Layers,
        capability: Capability.performanceViewAny,
      },
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
        href: "/dsr",
        label: "Class reports",
        icon: FileText,
        capability: Capability.dsrViewAny,
        scopedRoles: ["trainer"],
      },
      {
        // A manager's ask of the teaching staff. Trainers see it too: they
        // are the people being asked, and answer on it (D-132).
        href: "/requirements",
        label: "Trainer requirements",
        icon: Megaphone,
        capability: Capability.requirementManage,
        scopedRoles: ["trainer"],
      },
    ],
  },
  {
    // Admissions is one job done many times a day, so its screens sit together
    // and in the order somebody works through them.
    title: "Admissions",
    items: [
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
    title: "Teaching",
    items: [
      {
        href: "/teaching/today",
        label: "Today's class",
        icon: Sparkles,
        capability: Capability.sessionManageAny,
        scopedRoles: ["trainer"],
      },
      {
        href: "/teaching",
        icon: CalendarCheck,
        label: "Class schedule",
        capability: Capability.sessionManageAny,
        scopedRoles: ["trainer"],
      },
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
        icon: ClipboardCheck,
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
    ],
  },
  {
    title: "People",
    items: [
      {
        href: "/admin/users",
        label: "User accounts",
        icon: Users,
        capability: Capability.userViewAny,
      },
      {
        href: "/admin/students",
        label: "Students",
        icon: UsersRound,
        capability: Capability.studentViewAny,
      },
      {
        href: "/admin/trainers",
        label: "Trainers",
        icon: GraduationCap,
        capability: Capability.trainerViewAny,
      },
    ],
  },
  {
    title: "Courses and batches",
    items: [
      {
        href: "/admin/courses",
        label: "Course management",
        icon: PenLine,
        capability: Capability.courseViewAny,
        scopedRoles: ["trainer"],
      },
      {
        href: "/admin/batches",
        label: "Batches",
        icon: Layers,
        capability: Capability.batchViewAny,
        scopedRoles: ["trainer"],
      },
      { href: "/courses", label: "Course catalogue", icon: BookOpen },
    ],
  },
  {
    title: "Results and reports",
    items: [
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
      {
        href: "/admin/reports",
        label: "Reports",
        icon: FileSpreadsheet,
        capability: Capability.reportViewAny,
        scopedRoles: ["trainer"],
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
    title: "Institution",
    items: [
      {
        href: "/admin/academics",
        label: "Academic rules",
        icon: Settings2,
        capability: Capability.academicConfigure,
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
        href: "/admin/communication",
        label: "Message templates",
        icon: Send,
        capability: Capability.templateManage,
      },
      {
        href: "/admin/settings",
        label: "Settings",
        icon: SlidersHorizontal,
        capability: Capability.settingsManage,
      },
      {
        href: "/admin/recovery",
        label: "Deleted records",
        icon: Trash2,
        capability: Capability.recordViewDeleted,
      },
      {
        href: "/admin/branches",
        label: "Centres",
        icon: Building2,
        capability: Capability.organisationViewAny,
      },
      {
        href: "/admin/branding",
        label: "Branding",
        icon: Palette,
        capability: Capability.platformConfigure,
      },
      // Every source on the calendar scopes itself to what the caller may see,
      // so a manager gets every batch's classes and milestones and a trainer
      // only theirs. The link was trainer-only by oversight, not by design.
      {
        href: "/calendar",
        label: "Calendar",
        icon: CalendarDays,
        scopedRoles: ["trainer", "counsellor", "manager", "admin", "superadmin"],
      },
    ],
  },
  {
    title: "My work",
    items: [
      { href: "/announcements", label: "Announcements", icon: Megaphone },
      {
        href: "/discussions",
        label: "Discussions",
        icon: MessagesSquare,
        scopedRoles: ["trainer"],
      },
      // Forms sent to you to fill — anyone may receive one — and, for those
      // who send them, the ones you sent and "Fill in a form".
      { href: "/forms", label: "Form inbox", icon: ClipboardCheck },
      { href: "/notifications", label: "Notifications", icon: Bell },
      { href: "/profile", label: "My profile", icon: UserCircle2 },
    ],
  },
];

/** Roles that get the sidebar. Students get the shorter top bar. */
/**
 * The administrator's sidebar, ranked by what the owner wants seen first
 * (14 September 2026): the activity review, then the manager's work, the
 * trainers, the counsellor's work, students and fees, batches and courses,
 * outcomes, the calendar, and only then the institution's own settings.
 * The role-ranked manager, counsellor and trainer trees below reuse this
 * catalogue but put each job's daily work first.
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

/**
 * Role workspaces are deliberately different even where backend permissions
 * overlap. A manager and counsellor can cover much of the same work (D-130),
 * but their first five links should still describe different jobs. The
 * capability filter remains authoritative for what is offered inside each
 * tree, including custom roles.
 */

const STAFF_CATALOGUE = STAFF_NAV.flatMap((group) => group.items);

function staffItem(href: string): NavItem {
  const item = STAFF_CATALOGUE.find((candidate) => candidate.href === href);
  if (!item) throw new Error(`No staff navigation item registered for ${href}`);
  return item;
}

function studentItem(href: string): NavItem {
  const item = STUDENT_NAV.find((candidate) => candidate.href === href);
  if (!item) throw new Error(`No student navigation item registered for ${href}`);
  return item;
}

const MANAGER_HOME: NavItem = {
  href: "/manage",
  label: "Operations overview",
  icon: LayoutDashboard,
  capability: Capability.performanceViewAny,
};

const FEES_HOME: NavItem = {
  href: "/fees",
  label: "Fees & collections",
  icon: Wallet,
  capability: Capability.feeViewAny,
};

const TRAINER_WORK: NavItem = {
  href: "/teaching/work",
  label: "Work to review",
  icon: ListChecks,
  scopedRoles: ["trainer"],
};

export const MANAGER_NAV: NavGroup[] = [
  {
    items: [MANAGER_HOME, staffItem("/analytics")],
  },
  {
    title: "Academic operations",
    items: [
      staffItem("/activities"),
      staffItem("/manage/batches"),
      staffItem("/manage/reviews"),
      staffItem("/dsr"),
      staffItem("/requirements"),
    ],
  },
  {
    title: "People",
    items: [
      staffItem("/manage/trainers"),
      staffItem("/admin/students"),
      staffItem("/admin/users"),
    ],
  },
  {
    title: "Admissions and fees",
    items: [
      staffItem("/admissions/dashboard"),
      staffItem("/enquiries"),
      staffItem("/admissions"),
      staffItem("/admissions/new"),
      FEES_HOME,
      staffItem("/admissions/batches"),
      staffItem("/admissions/transfer"),
    ],
  },
  {
    title: "Teaching and content",
    items: [
      staffItem("/teaching/today"),
      staffItem("/teaching"),
      staffItem("/teaching/assignments"),
      staffItem("/teaching/assessments"),
      staffItem("/teaching/projects"),
      staffItem("/teaching/exams"),
      staffItem("/teaching/questions"),
      staffItem("/admin/courses"),
      staffItem("/admin/batches"),
      staffItem("/courses"),
    ],
  },
  {
    title: "Reports and tools",
    items: [
      staffItem("/admin/reports"),
      staffItem("/admin/imports"),
      staffItem("/admin/policies"),
      staffItem("/calendar"),
    ],
  },
  {
    title: "My work",
    items: [
      staffItem("/announcements"),
      staffItem("/discussions"),
      staffItem("/forms"),
      staffItem("/notifications"),
      staffItem("/profile"),
    ],
  },
];

export const COUNSELLOR_NAV: NavGroup[] = [
  {
    items: [staffItem("/admissions/dashboard"), staffItem("/enquiries"), FEES_HOME],
  },
  {
    title: "Admissions",
    items: [
      staffItem("/admissions"),
      staffItem("/admissions/new"),
      staffItem("/admissions/batches"),
      staffItem("/admissions/transfer"),
    ],
  },
  {
    title: "Student care",
    items: [
      staffItem("/activities"),
      staffItem("/admin/students"),
      staffItem("/admin/users"),
      staffItem("/calendar"),
    ],
  },
  {
    title: "Academic support",
    items: [
      staffItem("/manage/batches"),
      staffItem("/dsr"),
      staffItem("/teaching"),
      staffItem("/teaching/assignments"),
      staffItem("/teaching/assessments"),
      staffItem("/teaching/projects"),
      staffItem("/teaching/exams"),
      staffItem("/teaching/questions"),
      staffItem("/admin/courses"),
      staffItem("/admin/batches"),
      staffItem("/courses"),
      staffItem("/manage/trainers"),
    ],
  },
  {
    title: "Reports and data",
    items: [
      staffItem("/analytics"),
      staffItem("/admin/reports"),
      staffItem("/admin/imports"),
    ],
  },
  {
    title: "Communication and my work",
    items: [
      staffItem("/announcements"),
      staffItem("/discussions"),
      staffItem("/forms"),
      staffItem("/notifications"),
      staffItem("/profile"),
    ],
  },
];

export const TRAINER_NAV: NavGroup[] = [
  {
    items: [staffItem("/dashboard"), staffItem("/teaching/today"), TRAINER_WORK],
  },
  {
    title: "Teaching",
    items: [
      staffItem("/teaching"),
      staffItem("/teaching/assignments"),
      staffItem("/teaching/assessments"),
      staffItem("/teaching/projects"),
      staffItem("/teaching/exams"),
      staffItem("/teaching/questions"),
    ],
  },
  {
    title: "Learners and content",
    items: [
      staffItem("/activities"),
      staffItem("/admin/batches"),
      staffItem("/admin/courses"),
      staffItem("/courses"),
      staffItem("/dsr"),
      staffItem("/requirements"),
    ],
  },
  {
    title: "Planning and communication",
    items: [
      staffItem("/calendar"),
      staffItem("/announcements"),
      staffItem("/discussions"),
      staffItem("/forms"),
    ],
  },
  {
    title: "My account",
    items: [staffItem("/notifications"), staffItem("/profile")],
  },
];

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

/** Which role-ranked sidebar a person gets. */
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
