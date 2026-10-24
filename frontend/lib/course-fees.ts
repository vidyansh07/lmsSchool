/**
 * What a course costs, and how that cost is normally collected.
 *
 * Two endpoints the frontend had never called. `price/` is the fee history —
 * a commercial decision announced for a date, which the course screen's
 * "Change Fees" writes and reads back. `instalments/` is the course's default
 * instalment structure: percentages of whatever a student actually has to
 * pay, copied into their fee plan the day it is made and never read back, so
 * changing the structure cannot move a due date for anybody already enrolled.
 *
 * Both are addressed by the course's id or slug, like every other course
 * route.
 */
import { apiFetch, apiMutate } from '@/lib/api';
import type { CourseFeeInstalment, CoursePrice } from '@/types/api';

export async function listCoursePrices(identifier: string): Promise<CoursePrice[]> {
  return apiFetch<CoursePrice[]>(`/api/v1/courses/${identifier}/price/`);
}

export async function recordCoursePrice(
  identifier: string,
  payload: { amount: string; effective_from?: string; note?: string },
): Promise<CoursePrice> {
  return apiMutate<CoursePrice>(`/api/v1/courses/${identifier}/price/`, {
    method: 'POST',
    body: payload,
  });
}

/** One row of the structure as the screen edits it: no id, order is the array. */
export interface CourseFeeInstalmentInput {
  label?: string;
  percent: string;
  due_after_days: number;
}

export async function listCourseInstalments(identifier: string): Promise<CourseFeeInstalment[]> {
  return apiFetch<CourseFeeInstalment[]>(`/api/v1/courses/${identifier}/instalments/`);
}

/**
 * Replace the whole structure. Replace-as-set, because the screen shows all
 * of it at once and the person editing it is answering "what is it now".
 * An empty list is a real answer: no default structure, each admission
 * decides.
 */
export async function setCourseInstalments(
  identifier: string,
  instalments: CourseFeeInstalmentInput[],
): Promise<CourseFeeInstalment[]> {
  return apiMutate<CourseFeeInstalment[]>(`/api/v1/courses/${identifier}/instalments/`, {
    method: 'PUT',
    body: { instalments },
  });
}

/**
 * Destroy a course nobody has studied under. The server refuses one with
 * batches or enrolments (409) and says to archive it instead, which is what
 * that case wants.
 */
export async function deleteCourse(identifier: string): Promise<void> {
  return apiMutate<void>(`/api/v1/courses/${identifier}/`, { method: 'DELETE' });
}
