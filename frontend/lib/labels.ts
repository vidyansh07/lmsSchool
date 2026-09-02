/** Display labels for API enumerations, kept in one place. */

import type { FeeStatus, Qualification, UserRole } from '@/types/api';

export const FEE_STATUS_LABEL: Record<FeeStatus, string> = {
  pending: 'Pending',
  partial: 'Partially paid',
  paid: 'Paid',
  waived: 'Waived',
  overdue: 'Overdue',
};

export const FEE_STATUS_VARIANT: Record<FeeStatus, 'neutral' | 'success' | 'warning' | 'error'> = {
  pending: 'neutral',
  partial: 'warning',
  paid: 'success',
  waived: 'neutral',
  overdue: 'error',
};

export const FEE_STATUS_OPTIONS: { value: FeeStatus; label: string }[] = (
  Object.keys(FEE_STATUS_LABEL) as FeeStatus[]
).map((value) => ({ value, label: FEE_STATUS_LABEL[value] }));

export const QUALIFICATION_LABEL: Record<Qualification, string> = {
  secondary: 'Secondary (10th)',
  higher_secondary: 'Higher secondary (12th)',
  diploma: 'Diploma',
  bachelors: "Bachelor's degree",
  masters: "Master's degree",
  other: 'Other',
};

export const QUALIFICATION_OPTIONS: { value: Qualification; label: string }[] = (
  Object.keys(QUALIFICATION_LABEL) as Qualification[]
).map((value) => ({ value, label: QUALIFICATION_LABEL[value] }));

export const ROLE_LABEL: Record<UserRole, string> = {
  admin: 'Administrator',
  trainer: 'Trainer',
  student: 'Student',
};

export const ROLE_OPTIONS: { value: UserRole; label: string }[] = (
  Object.keys(ROLE_LABEL) as UserRole[]
).map((value) => ({ value, label: ROLE_LABEL[value] }));
