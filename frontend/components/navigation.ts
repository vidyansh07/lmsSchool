import type { LucideIcon } from "lucide-react";
import {
  Activity,
  Award,
  Briefcase,
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
  ListTodo,
  Megaphone,
  MessagesSquare,
  PenLine,
  Repeat,
  ScrollText,
  SlidersHorizontal,
  Sparkles,
  TrendingUp,
  UserCircle2,
  UserPlus,
  Users,
  Wallet,
  UsersRound,
  Workflow,
  Inbox,
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

/**
 * Which module colour a sidebar group wears.
 *
 * An ERP is six jobs in one coat. A counsellor working a lead, a trainer taking
 * a register and somebody chasing a payment were all looking at the same
 * orange, so nothing on screen said which part of the system they were in.
 *
 * Matched on the words in the group heading rather than by giving every group
 * an explicit colour, because the headings already say what the group is for
 * and there are twenty-four of them across six sidebars. A heading that matches
 * nothing gets no colour, which is the safe outcome: a group with no identity
 * reads as neutral rather than as the wrong area.
 *
 * The colour is never the only signal. Every item keeps its own icon and its
 * own label; this is the thing you recognise from across the room.
 */
export type ModuleAccent =
  | "academic"
  | "admissions"
  | "fees"
  | "people"
  | "placement"
  | "reports";

const ACCENT_BY_KEYWORD: [RegExp, ModuleAccent][] = [
  [/placement|employer|opening/i, "placement"],
  [/admission|enquir|counsel|lead/i, "admissions"],
  [/fee|payment|invoice|money/i, "fees"],
  [/report|analytic|data|result/i, "reports"],
  [/people|student|trainer|learner|staff|care/i, "people"],
  [/academic|teach|batch|course|class|content|calendar|planning/i, "academic"],
];

/** The accent for a group heading, or undefined when nothing matches. */
export function accentFor(title: string | undefined): ModuleAccent | undefined {
  if (!title) return undefined;
  for (const [pattern, accent] of ACCENT_BY_KEYWORD) {
    if (pattern.test(title)) return accent;
  }
  return undefined;
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
/** The placement desk. Its own group rather than another line under
 *  "Students", so the module reads as the independent thing it is — and so
 *  `accentFor` gives it the placement accent the shell already defines. */
/** The five admissions reports (`/reports`). Named "Admission reports" and
 *  not "Reports" because `/admin/reports` already carries that word and runs
 *  the export catalogue — two menu entries with one name is how somebody ends
 *  up on the wrong screen twice before learning the difference. */
const ADMISSION_REPORTS: NavItem = {
  href: "/reports",
  label: "Admission reports",
  icon: FileSpreadsheet,
  capability: Capability.feeViewAny,
};

const PLACEMENT_GROUP: NavGroup = {
  title: "Placement",
  items: [
    {
      href: "/placement",
      label: "Placement desk",
      icon: Briefcase,
      capability: Capability.placementViewAny,
    },
  ],
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
  PLACEMENT_GROUP,
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
      ADMISSION_REPORTS,
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
  PLACEMENT_GROUP,
  {
    title: "Reports",
    items: [
      {
        href: "/admin/reports",
        label: "Reports",
        icon: FileSpreadsheet,
        capability: Capability.reportViewAny,
      },
      ADMISSION_REPORTS,
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
export // Three entries used to sit here — Assignments, Weekly tests and Projects.
// The `/teaching` hub already lists all three, in the same words, and this
// sidebar carries forty-nine items for an administrator. A menu that repeats
// the page it leads to is paying for itself twice: it is longer to read, and
// the thing somebody actually cannot find is further down.
//
// Exams and the question bank stayed. They are not on that hub, so removing
// them would have left no way to reach them at all — which is the failure this
// kind of tidying usually causes.
/**
 * The administrator's sidebar, re-cut.
 *
 * It used to be eleven groups and fifty links, ordered by which table each
 * screen edits: "Trainers" and "Calendar" were groups of one, "Institution"
 * was the fourteen leftovers, and the first link in the tree -- which is also
 * where `homeFor` lands somebody -- was the audit trail. An administrator
 * opened the product and was shown a forensic log of what everybody else did
 * yesterday.
 *
 * Six groups now, and each heading finishes the sentence "I am here because I
 * need to...". A group of one link is a link. The fourteen configuration
 * screens are a destination (`/admin/configure`) rather than a seventh of the
 * menu, because nobody sets up automation and branding in the same minute.
 *
 * Nothing was removed and no capability moved: every link below carries the
 * capability it carried before, and `isVisible` still trims the tree per
 * person. The eight links other staff sidebars had and this one did not --
 * `/manage`, the three coursework screens, the work queue, discussions and
 * the enquiry form -- are back.
 */
const ADMIN_NAV: NavGroup[] = [
  {
    items: [
      {
        href: "/admin/overview",
        label: "Institution overview",
        icon: LayoutDashboard,
        capability: Capability.reportViewAny,
      },
      // Everything waiting on anybody, in full. It was reachable only from
      // the header's warnings button, which is absent when the count is
      // zero -- so the one screen that answers "what needs doing" could not
      // be found on a quiet morning.
      { href: "/needs-attention", label: "Needs attention", icon: ListChecks },
      {
        href: "/analytics",
        label: "Analytics",
        icon: TrendingUp,
        capability: Capability.reportViewAny,
      },
      CALENDAR,
    ],
  },
  {
    title: "Admissions & money",
    items: [
      {
        href: "/admissions/dashboard",
        label: "Admissions pipeline",
        icon: Workflow,
        capability: Capability.enrolmentCreate,
      },
      {
        href: "/enquiries",
        label: "Enquiries",
        icon: MessagesSquare,
        capability: Capability.enquiryViewAny,
      },
      READY_TO_ADMIT,
      {
        href: "/admissions",
        label: "Registrations",
        icon: ClipboardList,
        capability: Capability.studentCreate,
      },
      {
        href: "/admissions/new",
        label: "Register a student",
        icon: UserPlus,
        capability: Capability.studentCreate,
      },
      // The desk's own form, which asks the same questions in the order the
      // counsellor already asks them. It is not a duplicate of the wizard
      // above -- its docstring makes the case -- it was simply reachable
      // from nowhere, which is why nobody used the thing it was built for.
      {
        href: "/students/new",
        label: "New student (desk form)",
        icon: ClipboardList,
        capability: Capability.studentCreate,
      },
      {
        href: "/admissions/transfer",
        label: "Transfers",
        icon: Repeat,
        capability: Capability.enrolmentUpdateAny,
      },
      FEES_HOME,
    ],
  },
  PLACEMENT_GROUP,
  {
    title: "Teaching",
    items: [
      ...TEACHING_ITEMS,
      {
        href: "/admin/batches",
        label: "Batches",
        icon: Layers,
        capability: Capability.batchViewAny,
      },
      {
        href: "/admissions/batches",
        label: "Batch planning",
        icon: CalendarCheck,
        capability: Capability.batchCreate,
      },
      {
        href: "/admin/courses",
        label: "Courses",
        icon: BookOpen,
        capability: Capability.courseViewAny,
      },
      { href: "/courses", label: "Course catalogue", icon: LibraryBig },
      // Assignments, weekly tests and projects are deliberately absent: the
      // `/teaching` hub above already lists them in the same words, and a
      // menu that repeats the page it leads to is paying for itself twice.
      // `navigation-custom-role.test.ts` holds that line. Exams and the
      // question bank are here because the hub does not carry them.
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
      {
        href: "/dsr",
        label: "Class reports",
        icon: ClipboardCheck,
        capability: Capability.dsrViewAny,
      },
      {
        href: "/activities",
        label: "Activities",
        icon: ListTodo,
        capability: Capability.activityViewAny,
      },
      {
        href: "/manage/trainers",
        label: "Trainers",
        icon: Users,
        capability: Capability.trainerViewAny,
      },
      {
        href: "/manage/batches",
        label: "Batch review",
        icon: BookOpenCheck,
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
        icon: ListChecks,
        capability: Capability.requirementManage,
      },
      {
        href: "/admin/completions",
        label: "Completions",
        icon: GraduationCap,
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
    title: "People & records",
    items: [
      {
        href: "/admin/students",
        label: "Students",
        icon: GraduationCap,
        capability: Capability.studentViewAny,
      },
      {
        href: "/admin/users",
        label: "User accounts",
        icon: UsersRound,
        capability: Capability.userViewAny,
      },
      {
        href: "/admin/imports",
        label: "Data import",
        icon: FileSpreadsheet,
        capability: Capability.dataImport,
      },
    ],
  },
  {
    title: "Insight",
    items: [
      {
        href: "/admin/reports",
        label: "Reports & exports",
        icon: FileText,
        capability: Capability.reportViewAny,
      },
      ADMISSION_REPORTS,
      // A destination for a question asked after something has gone wrong,
      // which is why it is no longer the first thing an administrator sees.
      {
        href: "/admin/activity",
        label: "Staff activity",
        icon: Activity,
        capability: Capability.auditView,
      },
    ],
  },
  {
    title: "Configure",
    items: [
      // One line, fourteen screens. The hub itself is visible to anybody
      // holding any one of the capabilities its cards need, and each card is
      // gated separately -- so a composed role sees a shorter hub rather
      // than a dead link.
      {
        href: "/admin/configure",
        label: "Configuration",
        icon: SlidersHorizontal,
        capability: Capability.organisationViewAny,
      },
    ],
  },
  {
    title: "My work",
    items: [
      { href: "/announcements", label: "Announcements", icon: Megaphone },
      { href: "/discussions", label: "Discussions", icon: MessagesSquare },
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

/**
 * Which sidebar a person gets.
 *
 * The five named trees are curated: their grouping and order are chosen for the
 * job that role does all day, and `isVisible` then trims each one to the
 * capabilities the person actually holds.
 *
 * The fallback is the part that matters. Any other signed-in staff member — a
 * placement officer, or any role an administrator composes out of permissions —
 * used to fall through to the *student* sidebar, and so arrived at work with
 * links to "My assignments" and nothing they could use. The product supports
 * custom roles properly in the backend (`Role`, `Permission`, `ScopeGrant`) and
 * the navigation quietly did not, which made the whole feature look broken.
 *
 * So an unrecognised role now gets the widest staff tree, filtered by
 * capability. That is safe because the filter is the same one every other role
 * goes through, and because navigation has never been the thing that grants
 * access — the server decides on every request. A link nobody may follow is
 * removed by `isVisible`; a link that is missing when the permission exists is
 * the failure this fixes.
 *
 * `homeFor` reads the result of this, so fixing the sidebar fixes the landing
 * page with it: a composed role now starts on the first entry of a menu they
 * can actually use.
 */
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
      return SUPERADMIN_NAV;
  }
}

/** Base roles that are known to be staff by name. */
export const STAFF_ROLES = [
  "superadmin",
  "admin",
  "manager",
  "counsellor",
  "trainer",
];

/**
 * Whether this person works here, rather than studies here.
 *
 * Asked of their capabilities, not their role name. A placement officer or any
 * administrator-composed role holds staff capabilities and no name this file
 * knows, and judging by name alone handed them the student layout.
 *
 * A student holds only `profile.*` self-service capabilities, so the test is
 * simply: do they hold anything beyond their own record?
 */
export function isStaff(
  user: { role: string; capabilities: string[] } | null | undefined,
): boolean {
  if (!user) return false;
  if (STAFF_ROLES.includes(user.role)) return true;
  if (user.role === "student") return false;
  // A caller may hand us a user whose capabilities have not loaded yet — the
  // sign-in page does, between the credentials being accepted and the profile
  // arriving. Treating that as "no capabilities" is the safe reading, and it
  // has to not throw: this sits on the path that decides where somebody lands,
  // so an exception here is a sign-in that silently goes nowhere.
  return (user.capabilities ?? []).some(
    (capability) => !capability.startsWith("profile."),
  );
}

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
  if (user?.capabilities?.includes(item.capability)) return true;
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
  // `isStaff`, not a list of role names. A role an administrator composes out
  // of permissions has a name this file has never heard of, and testing the
  // name sent such a person to the student dashboard — the same failure
  // `navFor` had, one layer up, and invisible because the sidebar fix made
  // every *other* page work.
  if (!isStaff(user)) return "/dashboard";
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
