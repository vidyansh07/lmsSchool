/**
 * Academic years (`/api/v1/academic-years/`).
 *
 * A year is a record, not a number read off a date: an institute admits for
 * next year in December, and the counsellor doing that has to be able to say
 * so. Exactly one year is current, which is what a new admission starts with
 * and what every filter defaults to.
 */

import { apiFetch, apiMutate } from './api';

export interface AcademicYear {
  id: string;
  /** As people say it: "2026", or "2026-27". */
  name: string;
  starts_on: string | null;
  ends_on: string | null;
  is_current: boolean;
  /** A closed year takes no new admissions. Its records are untouched. */
  is_closed: boolean;
}

export async function listAcademicYears(): Promise<AcademicYear[]> {
  return apiFetch<AcademicYear[]>('/api/v1/academic-years/');
}

/** Adding one. `is_current` is not offered: moving it is its own act, below,
 *  and a careless create should not take the current year off another. */
export async function createAcademicYear(payload: {
  name: string;
  starts_on?: string | null;
  ends_on?: string | null;
  is_closed?: boolean;
}): Promise<AcademicYear> {
  return apiMutate<AcademicYear>('/api/v1/academic-years/', { method: 'POST', body: payload });
}

/** Changing one, including making it the current year — which the server
 *  makes exclusive in the same transaction. Setting `is_current` to false is
 *  refused: the way to move it is to set it on another year. */
export async function updateAcademicYear(
  id: string,
  payload: {
    name?: string;
    starts_on?: string | null;
    ends_on?: string | null;
    is_closed?: boolean;
    is_current?: true;
  },
): Promise<AcademicYear> {
  return apiMutate<AcademicYear>(`/api/v1/academic-years/${id}/`, {
    method: 'PATCH',
    body: payload,
  });
}
