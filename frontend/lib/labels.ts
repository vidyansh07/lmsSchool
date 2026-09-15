/** Display labels for API enumerations, kept in one place. */

import type {
  ActivityKind,
  MatrixCell,
  MfaMethodName,
  PermissionCategory,
  PermissionScope,
  FeePlanStatus,
  FeeStatus,
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

// --- MFA (ERP Phase 5, ADR-05) ------------------------------------------------

export const MFA_METHOD_LABEL: Record<MfaMethodName, string> = {
  totp: "Authenticator app",
  email: "Email code",
  recovery: "Recovery code",
};
