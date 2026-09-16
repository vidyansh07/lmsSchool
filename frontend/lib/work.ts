/**
 * The activity engine (`/api/v1/activities/`, `/api/v1/activity-types/`,
 * ERP Phase 9). See `types/api.ts`'s "Activities / the work engine" section
 * for the two contract points resolved there (person references as `{id,
 * name}` briefs; `ActivityDetail.available_transitions`).
 *
 * Named `work.ts`, not `activity.ts` or `activities.ts`: `lib/activity.ts`
 * already owns the unrelated `/api/v1/activity/` audit-log review screen
 * (`ActivityFeedEntry`/`ActivityScorecard`), and this module's own `Activity`
 * type would collide with that file's naming if it sat alongside it.
 */

import { apiFetch, apiMutate, queryString } from "./api";
import type {
  Activity,
  ActivityCategory,
  ActivityDetail,
  ActivityPriority,
  ActivityStatus,
  ActivityType,
  Paginated,
} from "@/types/api";

// --- Activity types -----------------------------------------------------

export interface ActivityTypeListResponse {
  results: ActivityType[];
}

/** `GET /activity-types/` — reads are open to any staff member; writes need
 *  `activity_type.manage`. Cached by the server (`work:types`, 10 min). */
export async function listActivityTypes(): Promise<ActivityTypeListResponse> {
  return apiFetch<ActivityTypeListResponse>("/api/v1/activity-types/");
}

/** The writable shape of an `ActivityType`, shared by create and update —
 *  `slug` is accepted only on create (`POST`) and is immutable afterwards. */
export interface ActivityTypeInput {
  slug: string;
  name: string;
  description: string;
  category: ActivityCategory;
  allowed_creator_roles: string[];
  allowed_assignee_roles: string[];
  visible_to_student: boolean;
  default_duration_minutes: number | null;
  form: string | null;
  requires_review: boolean;
  performance_weight: string;
  risk_effect: "none" | "score_below_threshold";
  reminder_minutes_before: number | null;
  status: "active" | "disabled";
}

export async function createActivityType(
  payload: ActivityTypeInput,
): Promise<ActivityType> {
  return apiMutate<ActivityType>("/api/v1/activity-types/", {
    method: "POST",
    body: payload,
  });
}

export async function updateActivityType(
  slug: string,
  payload: Partial<Omit<ActivityTypeInput, "slug">>,
): Promise<ActivityType> {
  return apiMutate<ActivityType>(`/api/v1/activity-types/${slug}/`, {
    method: "PATCH",
    body: payload,
  });
}

// --- Activities -----------------------------------------------------------

export interface ActivityFilters {
  status?: ActivityStatus;
  type?: string;
  category?: ActivityCategory;
  student?: string;
  batch?: string;
  assigned_to?: string;
  created_by?: string;
  due_before?: string;
  due_after?: string;
  overdue?: 1;
  mine?: 1;
  ordering?: "due_at" | "-created_at" | "priority";
  page?: number;
  page_size?: number;
}

function activityQuery(filters: ActivityFilters): string {
  return queryString({ ...filters });
}

/** `GET /activities/` — `activity.view_any` (scoped), or the caller's own
 *  work as assignee/creator. */
export async function listActivities(
  filters: ActivityFilters = {},
): Promise<Paginated<Activity>> {
  return apiFetch<Paginated<Activity>>(
    `/api/v1/activities/${activityQuery(filters)}`,
  );
}

/** `GET /students/{id}/activities/` — same filters, scoped to one student
 *  (the Student 360 tab; this phase only needs the client, not that page). */
export async function listStudentActivities(
  studentId: string,
  filters: ActivityFilters = {},
): Promise<Paginated<Activity>> {
  return apiFetch<Paginated<Activity>>(
    `/api/v1/students/${studentId}/activities/${activityQuery(filters)}`,
  );
}

/** `GET /me/activities/` — sugar for `mine=1` on the caller's own work. */
export async function listMyActivities(
  filters: Omit<ActivityFilters, "mine"> = {},
): Promise<Paginated<Activity>> {
  return apiFetch<Paginated<Activity>>(
    `/api/v1/me/activities/${activityQuery(filters)}`,
  );
}

export interface CreateActivityPayload {
  student: string;
  enrollment?: string;
  activity_type: string;
  title?: string;
  assigned_to?: string;
  planned_at?: string;
  due_at?: string;
  priority?: ActivityPriority;
  student_visible?: boolean;
  /** Unique per creator for 24h — a retry with the same key returns the
   *  original 201 body instead of creating a duplicate. */
  client_key?: string;
}

export async function createActivity(
  payload: CreateActivityPayload,
): Promise<ActivityDetail> {
  return apiMutate<ActivityDetail>("/api/v1/activities/", {
    method: "POST",
    body: payload,
  });
}

/** `GET /activities/{id}/` — full detail: pinned form, history, transitions
 *  currently legal from this status. */
export async function getActivity(id: string): Promise<ActivityDetail> {
  return apiFetch<ActivityDetail>(`/api/v1/activities/${id}/`);
}

export interface UpdateActivityPayload {
  title?: string;
  planned_at?: string | null;
  due_at?: string | null;
  priority?: ActivityPriority;
  assigned_to?: string;
  /** May only move true → false (hide) — the server refuses the reverse. */
  student_visible?: boolean;
}

/** `PATCH /activities/{id}/` — editable only while DRAFT/PLANNED/ASSIGNED. */
export async function updateActivity(
  id: string,
  payload: UpdateActivityPayload,
): Promise<ActivityDetail> {
  return apiMutate<ActivityDetail>(`/api/v1/activities/${id}/`, {
    method: "PATCH",
    body: payload,
  });
}

/** `POST /activities/{id}/transition/` for `to` one of PLANNED, ASSIGNED,
 *  IN_PROGRESS, CANCELLED, REOPENED. 409s with `{details: {allowed:
 *  [...]}}` on an illegal transition — `ApiError.details` carries it. */
export async function transitionActivity(
  id: string,
  to: ActivityStatus,
  note?: string,
): Promise<ActivityDetail> {
  return apiMutate<ActivityDetail>(`/api/v1/activities/${id}/transition/`, {
    method: "POST",
    body: note ? { to, note } : { to },
  });
}

export interface CompleteActivityPayload {
  form_values: Record<string, unknown>;
  summary?: string;
  duration_minutes?: number;
  completed_at?: string;
}

/** `POST /activities/{id}/complete/` — moves to COMPLETED, or UNDER_REVIEW
 *  when the type requires review. 409 if already completed. */
export async function completeActivity(
  id: string,
  payload: CompleteActivityPayload,
): Promise<ActivityDetail> {
  return apiMutate<ActivityDetail>(`/api/v1/activities/${id}/complete/`, {
    method: "POST",
    body: payload,
  });
}

/** `POST /activities/{id}/review/` — `activity.review`, refused for the
 *  performer (the drawer hides the action for that case; the server refuses
 *  it regardless). */
export async function reviewActivity(
  id: string,
  decision: "approved" | "requires_action",
  note: string,
): Promise<ActivityDetail> {
  return apiMutate<ActivityDetail>(`/api/v1/activities/${id}/review/`, {
    method: "POST",
    body: { decision, note },
  });
}

/** `DELETE /activities/{id}/` — soft delete; `activity.delete`. Answers
 *  `200` with the (now-deleted) detail, not `204`. */
export async function deleteActivity(
  id: string,
  reason: string,
): Promise<ActivityDetail> {
  return apiMutate<ActivityDetail>(`/api/v1/activities/${id}/`, {
    method: "DELETE",
    body: { reason },
  });
}

// --- The lifecycle graph, client side ------------------------------------
//
// `apps/work/transitions.py`'s `TRANSITIONS` table, transcribed for the one
// thing a screen needs it for: which buttons a transition action bar may
// legally offer from the activity's current status. There is no HTTP
// endpoint that answers this (confirmed against `ActivityDetailSerializer`
// — no `available_transitions` field exists), so this has to be data here,
// not a value read off a response.
//
// Deliberately narrower than the Python table: this omits every edge a
// person cannot drive through `POST .../transition/` —
//   - `system`-only edges (`assigned`→`missed`, `assigned`|`in_progress`→
//     `overdue`): nobody can click a button for these.
//   - `under_review`'s two edges (→`approved`, →`requires_action`): the
//     Python table lists them for `/transition/`'s own 409 message, but the
//     product's review decision is `POST .../review/`
//     (`ActivityReviewView`/`review_activity`), which this app's Review
//     panel already covers with its own self-review check. Offering the
//     same move again as a bare "transition" button would duplicate that
//     control with none of its guardrails.
const LEGAL_TRANSITIONS: Partial<Record<ActivityStatus, ActivityStatus[]>> = {
  draft: ["planned", "cancelled"],
  planned: ["assigned", "cancelled"],
  assigned: ["in_progress", "cancelled"],
  requires_action: ["in_progress"],
  missed: ["reopened"],
  cancelled: ["reopened"],
  completed: ["reopened"],
  approved: ["reopened"],
  reopened: ["assigned"],
};

/** Every status a person may legally move `status` to via
 *  `POST /activities/{id}/transition/` right now. Empty for a status whose
 *  only way forward is `/complete/` (`in_progress`, `overdue`), that has no
 *  way forward at all (`under_review` — see above), or a status the server
 *  only ever assigns itself. */
export function legalTransitions(status: ActivityStatus): ActivityStatus[] {
  return LEGAL_TRANSITIONS[status] ?? [];
}
