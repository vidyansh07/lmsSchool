/** API calls for users, students and trainers. */

import { apiFetch, apiMutate, queryString } from './api';
import type {
  ActivityDetail,
  ActivityPriority,
  AdminUser,
  FeeStatus,
  Paginated,
  StudentDuplicatesResponse,
  StudentListRow,
  StudentProfile,
  TrainerListRow,
  TrainerProfile,
  UserAuditEntry,
} from '@/types/api';

export interface ListQuery {
  page?: number;
  page_size?: number;
  search?: string;
  ordering?: string;
  [key: string]: string | number | undefined;
}

// --- Users -----------------------------------------------------------------

/**
 * Give a manager a trainer profile so they can be put on a batch. One login,
 * the profile created the first time; a second call returns the same one.
 */
export async function ensureTeachingProfile(userId: string): Promise<TrainerProfile> {
  return apiMutate<TrainerProfile>('/api/v1/trainers/teaching-profile/', {
    method: 'POST',
    body: { user_id: userId },
  });
}

export async function listUsers(query: ListQuery = {}): Promise<Paginated<AdminUser>> {
  return apiFetch<Paginated<AdminUser>>(`/api/v1/users/${queryString(query)}`);
}

export async function getUser(id: string): Promise<AdminUser> {
  return apiFetch<AdminUser>(`/api/v1/users/${id}/`);
}

export async function createUser(payload: {
  branch?: string | null;
  email: string;
  first_name: string;
  last_name?: string;
  phone?: string;
  role: string;
}): Promise<AdminUser> {
  return apiMutate<AdminUser>('/api/v1/users/', { method: 'POST', body: payload });
}

export async function updateUser(
  id: string,
  changes: Partial<
    Pick<AdminUser, 'email' | 'first_name' | 'last_name' | 'phone' | 'role' | 'custom_role'>
  >,
): Promise<AdminUser> {
  return apiMutate<AdminUser>(`/api/v1/users/${id}/`, { method: 'PATCH', body: changes });
}

/**
 * Send this person a password-reset or email-verification link.
 *
 * There is deliberately no "set their password" here. An administrator who sets
 * a password has to transmit it, which means two people know it and the record
 * says an administrator changed it rather than the owner setting one.
 */
export async function sendCredentialLink(
  id: string,
  action: 'password_reset' | 'email_verification',
): Promise<{ detail: string }> {
  return apiMutate(`/api/v1/users/${id}/credential-link/`, {
    method: 'POST',
    body: { action },
  });
}

/** What has been done to this account, most recent first. */
export async function getUserAudit(id: string): Promise<UserAuditEntry[]> {
  return apiFetch<UserAuditEntry[]>(`/api/v1/users/${id}/audit/`);
}

export async function setUserActive(
  id: string,
  isActive: boolean,
  reason = '',
): Promise<AdminUser> {
  return apiMutate<AdminUser>(`/api/v1/users/${id}/set-active/`, {
    method: 'POST',
    body: { is_active: isActive, reason },
  });
}

// --- Students --------------------------------------------------------------

export async function listStudents(query: ListQuery = {}): Promise<Paginated<StudentListRow>> {
  return apiFetch<Paginated<StudentListRow>>(`/api/v1/students/${queryString(query)}`);
}

export async function getStudent(id: string): Promise<StudentProfile> {
  return apiFetch<StudentProfile>(`/api/v1/students/${id}/`);
}

export async function getOwnStudentProfile(): Promise<StudentProfile> {
  return apiFetch<StudentProfile>('/api/v1/students/me/');
}

export async function updateOwnStudentProfile(
  changes: Partial<StudentProfile>,
): Promise<StudentProfile> {
  return apiMutate<StudentProfile>('/api/v1/students/me/', { method: 'PATCH', body: changes });
}

export async function updateStudent(
  id: string,
  changes: Partial<StudentProfile>,
): Promise<StudentProfile> {
  return apiMutate<StudentProfile>(`/api/v1/students/${id}/`, { method: 'PATCH', body: changes });
}

export async function createStudent(payload: {
  /** Required of a superadmin, ignored for everybody else (their own centre is forced). */
  branch?: string | null;
  email: string;
  first_name: string;
  last_name?: string;
  phone?: string;
  profile?: Record<string, unknown>;
  /** Rupees, minimum 1000. Omit or `null` when no fee was agreed yet. */
  fee_amount?: string | number | null;
  /**
   * Required by the server whenever the registration wizard showed a
   * duplicate match and the counsellor chose "this is a different person"
   * (ERP Phase 17, `USER_JOURNEYS.md` §4.2) — captured in the wizard's own
   * state at the duplicate-check step and only sent here, with the rest of
   * the registration, at the final "Register" submit. Omit when no
   * duplicate was ever shown.
   */
  override_reason?: string;
}): Promise<StudentProfile> {
  return apiMutate<StudentProfile>('/api/v1/students/', { method: 'POST', body: payload });
}

/**
 * `GET /api/v1/students/duplicates/` — a read, not a search: it exists only
 * to warn a counsellor mid-registration, and, like global search
 * (Phase 11), never discloses a student outside the caller's own reach.
 * `email` and `phone` are each enough alone; `name` narrows further. Empty
 * `results` on a real match just outside scope looks identical to no match
 * at all — that is the point, not a bug to work around client-side.
 */
export async function checkDuplicates(query: {
  email?: string;
  phone?: string;
  name?: string;
}): Promise<StudentDuplicatesResponse> {
  return apiFetch<StudentDuplicatesResponse>(`/api/v1/students/duplicates/${queryString(query)}`);
}

/**
 * `POST /api/v1/students/{id}/follow-ups/` — the counsellor's "Plan a
 * follow-up" action on a student's record (`USER_JOURNEYS.md` §4.3). The
 * server routes this through the same `apps.work.services.create_activity`
 * every other activity-creation path uses; the response is the same
 * `ActivityDetail` shape `POST /activities/` returns.
 */
export async function createFollowUp(
  studentId: string,
  payload: { due_at: string; priority?: ActivityPriority },
): Promise<ActivityDetail> {
  return apiMutate<ActivityDetail>(`/api/v1/students/${studentId}/follow-ups/`, {
    method: 'POST',
    body: payload,
  });
}

/** Set or clear (`null`) the fee agreed with a student. */
export async function setFeeAmount(
  id: string,
  feeAmount: string | number | null,
  note = '',
): Promise<StudentProfile> {
  return apiMutate<StudentProfile>(`/api/v1/students/${id}/fee-amount/`, {
    method: 'POST',
    body: { fee_amount: feeAmount, note },
  });
}

export async function setFeeStatus(
  id: string,
  feeStatus: FeeStatus,
  note = '',
): Promise<StudentProfile> {
  return apiMutate<StudentProfile>(`/api/v1/students/${id}/fee-status/`, {
    method: 'POST',
    body: { fee_status: feeStatus, note },
  });
}

// --- Trainers --------------------------------------------------------------

export async function listTrainers(query: ListQuery = {}): Promise<Paginated<TrainerListRow>> {
  return apiFetch<Paginated<TrainerListRow>>(`/api/v1/trainers/${queryString(query)}`);
}

export async function getTrainer(id: string): Promise<TrainerProfile> {
  return apiFetch<TrainerProfile>(`/api/v1/trainers/${id}/`);
}

export async function getOwnTrainerProfile(): Promise<TrainerProfile> {
  return apiFetch<TrainerProfile>('/api/v1/trainers/me/');
}

export async function updateOwnTrainerProfile(
  changes: Partial<TrainerProfile>,
): Promise<TrainerProfile> {
  return apiMutate<TrainerProfile>('/api/v1/trainers/me/', { method: 'PATCH', body: changes });
}

export async function updateTrainer(
  id: string,
  changes: Partial<TrainerProfile>,
): Promise<TrainerProfile> {
  return apiMutate<TrainerProfile>(`/api/v1/trainers/${id}/`, { method: 'PATCH', body: changes });
}

export async function createTrainer(payload: {
  branch?: string | null;
  email: string;
  first_name: string;
  last_name?: string;
  phone?: string;
  profile?: Record<string, unknown>;
}): Promise<TrainerProfile> {
  return apiMutate<TrainerProfile>('/api/v1/trainers/', { method: 'POST', body: payload });
}
