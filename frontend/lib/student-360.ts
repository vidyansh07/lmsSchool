/**
 * The Student 360 read model (`GET /students/{id}/360/`, ERP Phase 11).
 *
 * One call for everything the header and the Overview tab need: who the
 * student is, where they sit (batch/trainer/counsellor), progress and
 * attendance, the performance/risk placeholders Phases 12/13 will fill in,
 * work counts, fee status and the two short activity feeds. Scoped the same
 * way `lib/timeline.ts` is — "can this caller see this student" is enforced
 * server-side by the same `visible_*` queryset every other student-scoped
 * endpoint uses, so this client does no authorization work of its own.
 */

import { apiFetch } from "./api";
import type { Student360Response } from "@/types/api";

export async function getStudent360(studentId: string): Promise<Student360Response> {
  return apiFetch<Student360Response>(`/api/v1/students/${encodeURIComponent(studentId)}/360/`);
}
