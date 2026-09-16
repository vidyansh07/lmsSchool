/** Display labels for API enumerations, kept in one place. */

import {
  Award,
  CalendarCheck,
  CircleDot,
  ClipboardCheck,
  FileCheck2,
  FolderKanban,
  GraduationCap,
  ListChecks,
  type LucideIcon,
} from "lucide-react";
import type {
  ActivityCategory,
  ActivityKind,
  ActivityPriority,
  ActivityRiskEffect,
  ActivityStatus,
  ActivityTypeStatus,
  MatrixCell,
  MfaMethodName,
  PermissionCategory,
  PermissionScope,
  FeePlanStatus,
  FeeStatus,
  FormDefinitionStatus,
  FormFieldType,
  FormVersionStatus,
  InstitutionKind,
  PaymentMethod,
  PolicyCategory,
  Qualification,
  RequirementStatus,
  UserRole,
} from "@/types/api";

export const REQUIREMENT_STATUS_LABEL: Record<RequirementStatus, string> = {
  open: "Open",
  fulfilled: "Fulfilled",
  closed: "Closed",
};

export const REQUIREMENT_STATUS_VARIANT: Record<
  RequirementStatus,
  "neutral" | "success" | "warning" | "error"
> = {
  open: "warning",
  fulfilled: "success",
  closed: "neutral",
};

export const FEE_STATUS_LABEL: Record<FeeStatus, string> = {
  pending: "Pending",
  partial: "Partially paid",
  paid: "Paid",
  waived: "Waived",
  overdue: "Overdue",
};

export const FEE_STATUS_VARIANT: Record<
  FeeStatus,
  "neutral" | "success" | "warning" | "error"
> = {
  pending: "neutral",
  partial: "warning",
  paid: "success",
  waived: "neutral",
  overdue: "error",
};

export const FEE_STATUS_OPTIONS: { value: FeeStatus; label: string }[] = (
  Object.keys(FEE_STATUS_LABEL) as FeeStatus[]
).map((value) => ({ value, label: FEE_STATUS_LABEL[value] }));

export const QUALIFICATION_LABEL: Record<Qualification, string> = {
  secondary: "Secondary (10th)",
  higher_secondary: "Higher secondary (12th)",
  diploma: "Diploma",
  bachelors: "Bachelor's degree",
  masters: "Master's degree",
  other: "Other",
};

export const QUALIFICATION_OPTIONS: { value: Qualification; label: string }[] =
  (Object.keys(QUALIFICATION_LABEL) as Qualification[]).map((value) => ({
    value,
    label: QUALIFICATION_LABEL[value],
  }));

export const ROLE_LABEL: Record<UserRole, string> = {
  superadmin: "Superadmin",
  admin: "Administrator",
  manager: "Manager",
  counsellor: "Counsellor",
  trainer: "Trainer",
  student: "Student",
};

export const ROLE_OPTIONS: { value: UserRole; label: string }[] = (
  Object.keys(ROLE_LABEL) as UserRole[]
).map((value) => ({ value, label: ROLE_LABEL[value] }));

export const INSTITUTION_KIND_LABEL: Record<InstitutionKind, string> = {
  college: "College",
  employer: "Employer",
};

export const INSTITUTION_KIND_OPTIONS: {
  value: InstitutionKind;
  label: string;
}[] = (Object.keys(INSTITUTION_KIND_LABEL) as InstitutionKind[]).map(
  (value) => ({ value, label: INSTITUTION_KIND_LABEL[value] }),
);

export const PAYMENT_METHOD_LABEL: Record<PaymentMethod, string> = {
  cash: "Cash",
  upi: "UPI",
  card: "Card",
  bank_transfer: "Bank transfer",
  cheque: "Cheque",
  other: "Other",
};

export const PAYMENT_METHOD_OPTIONS: { value: PaymentMethod; label: string }[] =
  (Object.keys(PAYMENT_METHOD_LABEL) as PaymentMethod[]).map((value) => ({
    value,
    label: PAYMENT_METHOD_LABEL[value],
  }));

export const FEE_PLAN_STATUS_LABEL: Record<FeePlanStatus, string> = {
  unpaid: "Nothing paid yet",
  partial: "Partly paid",
  paid: "Paid in full",
  waived: "Waived",
};

export const FEE_PLAN_STATUS_VARIANT: Record<
  FeePlanStatus,
  "neutral" | "success" | "warning" | "error"
> = {
  unpaid: "error",
  partial: "warning",
  paid: "success",
  waived: "neutral",
};

export const ACTIVITY_KIND_LABEL: Record<ActivityKind, string> = {
  admissions: "Admissions",
  fees: "Fees",
  teaching: "Teaching",
  reviews: "Reviews",
  courses: "Courses",
  outcomes: "Outcomes",
  accounts: "Accounts",
  communication: "Communication",
  institution: "Institution",
  other: "Other",
};

export const ACTIVITY_KIND_VARIANT: Record<
  ActivityKind,
  | "blue"
  | "green"
  | "violet"
  | "amber"
  | "indigo"
  | "teal"
  | "rose"
  | "cyan"
  | "pink"
  | "neutral"
> = {
  admissions: "blue",
  fees: "green",
  teaching: "violet",
  reviews: "amber",
  courses: "indigo",
  outcomes: "teal",
  accounts: "rose",
  communication: "cyan",
  institution: "pink",
  other: "neutral",
};

export const PERMISSION_CATEGORY_LABEL: Record<PermissionCategory, string> = {
  people: "People",
  academic: "Academic",
  operations: "Operations",
  configuration: "Configuration",
  communication: "Communication",
  system: "System",
};

export const SCOPE_LABEL: Record<PermissionScope | "", string> = {
  "": "As far as the role sees",
  all: "Every centre",
  branch: "Own centre",
  assigned: "Assigned batches and courses",
  own: "Own records",
};

export const MATRIX_CELL_LABEL: Record<MatrixCell, string> = {
  explicit: "Granted",
  inherited: "Inherited",
  locked: "Locked",
  denied: "Not granted",
  system: "System",
};

// --- Policy management (ERP Phase 3, ADR-04) --------------------------------

export const POLICY_CATEGORY_LABEL: Record<PolicyCategory, string> = {
  authentication: "Authentication",
  password: "Password",
  session: "Session",
  risk: "Risk rules",
  performance: "Performance weights",
  communication: "Communication",
  export: "Export",
  deletion: "Deletion",
  approval: "Approval",
  file_upload: "File upload",
  notification: "Notification",
};

// --- Forms / form builder (ERP Phase 8) --------------------------------------

export const FORM_FIELD_TYPE_LABEL: Record<FormFieldType, string> = {
  text: "Text",
  textarea: "Long text",
  number: "Number",
  decimal: "Decimal",
  date: "Date",
  datetime: "Date & time",
  boolean: "Yes / no",
  select: "Dropdown",
  multiselect: "Multi-select",
  radio: "Radio buttons",
  checkbox: "Checkboxes",
  email: "Email",
  phone: "Phone",
  url: "URL",
  file: "File",
  image: "Image",
  richtext: "Rich text",
  relation: "Relation",
};

export const FORM_FIELD_TYPE_OPTIONS: { value: FormFieldType; label: string }[] =
  (Object.keys(FORM_FIELD_TYPE_LABEL) as FormFieldType[]).map((value) => ({
    value,
    label: FORM_FIELD_TYPE_LABEL[value],
  }));

/** Field types whose `options` is a `{value,label}` choice list. */
export const FORM_FIELD_CHOICE_TYPES: readonly FormFieldType[] = [
  "select",
  "multiselect",
  "radio",
  "checkbox",
];

export const FORM_VERSION_STATUS_LABEL: Record<FormVersionStatus, string> = {
  draft: "Draft",
  published: "Published",
  archived: "Archived",
};

export const FORM_VERSION_STATUS_VARIANT: Record<
  FormVersionStatus,
  "neutral" | "success" | "warning" | "error"
> = {
  draft: "warning",
  published: "success",
  archived: "neutral",
};

export const FORM_DEFINITION_STATUS_LABEL: Record<FormDefinitionStatus, string> = {
  active: "Active",
  archived: "Archived",
};

export const FORM_DEFINITION_STATUS_VARIANT: Record<
  FormDefinitionStatus,
  "neutral" | "success" | "warning" | "error"
> = {
  active: "success",
  archived: "neutral",
};

// --- Activities / the work engine (ERP Phase 9) ------------------------------

/** Colour-coded by what the status means for the person looking at the row:
 *  the two terminal-for-performance statuses read as done, the three that
 *  need attention as a warning, everything else as ordinary in-flight work
 *  (`ACTIVITY_CATALOG.md` "Lifecycle (§25)"). Keyed by the model's actual
 *  lowercase wire values (`apps.work.models.ActivityStatus`), not the
 *  upper-cased prose shorthand `API_CONTRACTS.md` uses for the same twelve
 *  names. */
export const ACTIVITY_STATUS_LABEL: Record<ActivityStatus, string> = {
  draft: "Draft",
  planned: "Planned",
  assigned: "Assigned",
  in_progress: "In progress",
  completed: "Completed",
  missed: "Missed",
  overdue: "Overdue",
  cancelled: "Cancelled",
  reopened: "Reopened",
  under_review: "Under review",
  approved: "Approved",
  requires_action: "Requires action",
};

export const ACTIVITY_STATUS_VARIANT: Record<
  ActivityStatus,
  "neutral" | "success" | "warning"
> = {
  draft: "neutral",
  planned: "neutral",
  assigned: "neutral",
  in_progress: "neutral",
  completed: "success",
  missed: "warning",
  overdue: "warning",
  cancelled: "neutral",
  reopened: "neutral",
  under_review: "neutral",
  approved: "success",
  requires_action: "warning",
};

export const ACTIVITY_PRIORITY_LABEL: Record<ActivityPriority, string> = {
  low: "Low",
  normal: "Normal",
  high: "High",
  urgent: "Urgent",
};

export const ACTIVITY_PRIORITY_VARIANT: Record<
  ActivityPriority,
  "neutral" | "warning" | "error"
> = {
  low: "neutral",
  normal: "neutral",
  high: "warning",
  urgent: "error",
};

export const ACTIVITY_CATEGORY_LABEL: Record<ActivityCategory, string> = {
  interview: "Interview",
  mentoring: "Mentoring",
  counselling: "Counselling",
  review: "Review",
  placement: "Placement",
  feedback: "Feedback",
  warning: "Warning",
  follow_up: "Follow-up",
  other: "Other",
};

export const ACTIVITY_CATEGORY_OPTIONS: { value: ActivityCategory; label: string }[] =
  (Object.keys(ACTIVITY_CATEGORY_LABEL) as ActivityCategory[]).map((value) => ({
    value,
    label: ACTIVITY_CATEGORY_LABEL[value],
  }));

export const ACTIVITY_TYPE_STATUS_LABEL: Record<ActivityTypeStatus, string> = {
  active: "Active",
  disabled: "Disabled",
};

export const ACTIVITY_TYPE_STATUS_VARIANT: Record<
  ActivityTypeStatus,
  "neutral" | "success" | "warning" | "error"
> = {
  active: "success",
  disabled: "neutral",
};

export const ACTIVITY_RISK_EFFECT_LABEL: Record<ActivityRiskEffect, string> = {
  none: "No effect",
  score_below_threshold: "Score below threshold",
};

/**
 * The five statuses a person can drive an activity to via
 * `POST /activities/{id}/transition/` (`apps/work/transitions.py`'s
 * `TRANSITIONS` table — every other lifecycle move is system-only, or goes
 * through `/complete/` or `/review/` instead; see `lib/work.ts`'s
 * `legalTransitions`, which computes which of these apply to a given
 * activity). Keyed by the transition's `to` value, exactly what the
 * transition body's `to` field takes.
 */
export const ACTIVITY_TRANSITION_LABEL: Partial<Record<ActivityStatus, string>> = {
  planned: "Plan",
  assigned: "Assign",
  in_progress: "Start",
  cancelled: "Cancel",
  reopened: "Reopen",
};

/** Transitions whose lifecycle rule requires a reason/note
 *  (`transitions.py`'s `Edge.requires_note`). */
export const ACTIVITY_TRANSITION_REQUIRES_NOTE: ReadonlySet<ActivityStatus> = new Set([
  "cancelled",
  "reopened",
]);

// --- MFA (ERP Phase 5, ADR-05) ------------------------------------------------

export const MFA_METHOD_LABEL: Record<MfaMethodName, string> = {
  totp: "Authenticator app",
  email: "Email code",
  recovery: "Recovery code",
};

// --- Student timeline (ERP Phase 10, ADR-09) --------------------------------

/**
 * `kind` on a `TimelineEntry` is deliberately open-ended (see ADR-09 —
 * `work/timeline.py` registers one source per app, and a later phase can
 * register another without a matching frontend release). This maps the
 * kinds known today to an icon and a label; anything else falls back to a
 * generic icon and the raw kind string title-cased, so a new source renders
 * reasonably rather than breaking or falling through an exhaustive switch.
 */
export interface TimelineKindMeta {
  icon: LucideIcon;
  label: string;
}

export const TIMELINE_KIND_META: Record<string, TimelineKindMeta> = {
  enrollment_started: { icon: GraduationCap, label: "Enrolment started" },
  attendance_day: { icon: CalendarCheck, label: "Attendance" },
  dsr_submitted: { icon: ClipboardCheck, label: "Daily report submitted" },
  assessment_result: { icon: FileCheck2, label: "Assessment result" },
  assignment_submitted: { icon: ListChecks, label: "Assignment submitted" },
  project_state_changed: { icon: FolderKanban, label: "Project update" },
  certificate_issued: { icon: Award, label: "Certificate issued" },
};

/** "some_new_kind" -> "Some New Kind" — the fallback label for a kind this
 *  file does not know about yet. */
function titleCaseKind(kind: string): string {
  return kind
    .split(/[_\s-]+/)
    .filter((word) => word.length > 0)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/** Never throws and never returns `undefined` — every `kind` string, known
 *  or not, resolves to something renderable. */
export function timelineKindMeta(kind: string): TimelineKindMeta {
  return TIMELINE_KIND_META[kind] ?? { icon: CircleDot, label: titleCaseKind(kind) || "Event" };
}
