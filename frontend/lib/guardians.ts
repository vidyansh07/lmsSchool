/**
 * A student's parents and guardians (`/api/v1/students/{id}/guardians/`).
 *
 * Replaced as a set rather than edited one at a time: the form shows them all
 * at once and the counsellor edits them together, so "what was sent is what
 * there is" is the only reading that matches what they saw.
 *
 * Exactly one is the first guardian — the one the institute rings when it
 * rings one rather than all, which is the choice the message settings offer.
 */

import { apiFetch, apiMutate } from './api';

export type GuardianRelation =
  | 'father'
  | 'mother'
  | 'guardian'
  | 'spouse'
  | 'sibling'
  | 'other';

export interface Guardian {
  id: string;
  name: string;
  relation: GuardianRelation;
  relation_label: string;
  mobile: string;
  email: string;
  occupation: string;
  /** "First Guardian of the student", as the message settings name it. */
  is_primary: boolean;
}

export interface GuardianInput {
  name: string;
  relation?: GuardianRelation;
  mobile?: string;
  email?: string;
  occupation?: string;
  is_primary?: boolean;
}

export const GUARDIAN_RELATION_LABEL: Record<GuardianRelation, string> = {
  father: 'Father',
  mother: 'Mother',
  guardian: 'Guardian',
  spouse: 'Spouse',
  sibling: 'Sibling',
  other: 'Other',
};

export const GUARDIAN_RELATIONS = Object.keys(GUARDIAN_RELATION_LABEL) as GuardianRelation[];

export function listGuardians(studentId: string): Promise<Guardian[]> {
  return apiFetch<Guardian[]>(`/api/v1/students/${studentId}/guardians/`);
}

/** Replaces the whole set. Needs `student.update_any`. */
export function setGuardians(
  studentId: string,
  guardians: GuardianInput[],
): Promise<Guardian[]> {
  return apiMutate<Guardian[]>(`/api/v1/students/${studentId}/guardians/`, {
    method: 'PUT',
    body: { guardians },
  });
}
