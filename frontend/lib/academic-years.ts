/**
 * Academic years (`/api/v1/academic-years/`).
 *
 * A year is a record, not a number read off a date: an institute admits for
 * next year in December, and the counsellor doing that has to be able to say
 * so. Exactly one year is current, which is what a new admission starts with
 * and what every filter defaults to.
 */

import { apiFetch } from './api';

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
