/**
 * The API surface for the manager's two hub screens — batches and trainers —
 * and everything they drill into.
 *
 * Four shapes here (`ManagerDashboard`, `BatchOverview`, `BatchStudentRow`,
 * `TrainerOverview`) belong to endpoints a backend workstream is building in
 * parallel to this file, to a contract fixed in advance so the two sides could
 * be built at once without either waiting on the other. Calling one of them
 * before it has landed fails exactly the way any other 404 fails — through
 * the same `ApiError` every screen already renders as a retryable error
 * state — so there is nothing here to special-case while that lands.
 *
 * Everything else calls an endpoint that already exists:
 *  - `listManageBatches` / `listManageTrainers` are thin wrappers over
 *    `lib/batches.ts` and `lib/people.ts`'s own list calls, typed to a row
 *    that *optionally* carries a few extra fields (`kind`, `attendance_percent`,
 *    `dsr_state`, …) the dense hub tables want. The base rows already satisfy
 *    that wider type — every added field is optional — so today's response
 *    works unchanged, and the moment the list serializer grows one of those
 *    fields the matching column starts rendering real data with no frontend
 *    change. Until then `lib/format.ts`'s fallbacks render an honest
 *    "No data" rather than a blank cell, which is the correct reading for a
 *    figure the list endpoint has never promised to carry.
 *  - `listBatchDsr` / `reviewDsr` drive the batch page's inline DSR approval
 *    from the daily-status-report endpoints `apps.dsr` already ships
 *    (`GET /batches/<id>/dsr/`, `POST /dsr/<id>/review/`).
 *  - `createTrainerReview` posts to the performance app's existing review
 *    endpoint (`POST /performance/reviews/`).
 *  - `getBatchPerformance` and `listFeedback` read the performance engine's
 *    own endpoints (`GET /batches/<id>/performance/`, `GET /performance/feedback/`).
 *    Nothing in the fixed contract covers "one student's full performance
 *    picture" — the contract's `/batches/<id>/students/` is a roster *list*,
 *    not a single-student read — so the student page is built on the richest
 *    real source available: the same engine output `BatchPerformanceView`
 *    already serves for a trainer's own cohort view, matched down to one
 *    enrolment. `Feedback` has no student filter on the server yet, so
 *    `listFeedback` reads the visible set and the caller filters by
 *    `student_code`; see the student page for why that is an acceptable
 *    trade at today's data volumes rather than a bug.
 *
 * Nothing here is a second copy of a shape `types/api.ts` already declares —
 * every interface below is new because the endpoint it describes is new.
 */

import { apiFetch, apiMutate, queryString } from './api';
import { listBatches } from './batches';
import type { ListQuery } from './people';
import { listTrainers } from './people';
import type { BatchListRow, BatchStatus, EnrollmentStatus, Paginated, TrainerListRow } from '@/types/api';

// --- Manager dashboard -------------------------------------------------

export type AttentionSeverity = 'low' | 'medium' | 'high';

export interface ManagerAttentionItem {
  kind: string;
  label: string;
  count: number;
  href: string;
  severity: AttentionSeverity;
}

export interface ManagerDashboard {
  batches: { total: number; active: number; behind_schedule: number; at_risk: number };
  students: { total: number; active: number; at_risk: number };
  trainers: { total: number; with_overdue_dsr: number };
  attention: ManagerAttentionItem[];
  as_of: string;
}

export async function getManagerDashboard(): Promise<ManagerDashboard> {
  return apiFetch<ManagerDashboard>('/api/v1/dashboards/manager/');
}

// --- Batches hub ---------------------------------------------------------

/**
 * A batches-hub row: every field `listBatches` already returns, plus the
 * dense-table columns the hub wants that the list endpoint does not promise
 * yet. See the module docstring for why these are optional rather than a
 * second, parallel fetch.
 */
export interface ManageBatchRow extends BatchListRow {
  kind?: string;
  delivery_mode?: string;
  attendance_percent?: number | null;
  timeline_status?: TimelineStatus | null;
  timeline_variance_percent?: number | null;
  dsr_state?: string | null;
}

export function listManageBatches(query: ListQuery = {}): Promise<Paginated<ManageBatchRow>> {
  return listBatches(query);
}

// --- Batch overview --------------------------------------------------------

export type TimelineStatus = 'ahead' | 'on_track' | 'behind' | 'not_started';

export interface BatchOverview {
  batch: {
    id: string;
    code: string;
    name: string;
    kind: string;
    status: BatchStatus;
    delivery_mode: string;
    start_date: string;
    end_date: string;
    capacity: number;
    seats_taken: number;
  };
  course: { id: string; title: string; code: string };
  trainer: { id: string; name: string; trainer_id: string } | null;
  attendance: { percentage: number | null; present: number; absent: number; total_sessions: number };
  timeline: {
    percent_complete: number | null;
    percent_expected: number | null;
    variance_percent: number | null;
    status: TimelineStatus;
    lessons_covered: number;
    course_lessons_total: number;
    next_lesson: { id: string; title: string } | null;
  };
  sessions: { total: number; completed: number; cancelled: number; upcoming: number };
  dsr: { expected: number; submitted: number; approved: number; pending_review: number; overdue: number };
  assessments: { total: number; completed: number; average_percent: number | null };
  assignments: { total: number; submitted: number; graded: number };
  projects: { total: number; submitted: number; reviewed: number };
  students: { total: number; active: number; at_risk: number };
  as_of: string;
}

export async function getBatchOverview(batchId: string): Promise<BatchOverview> {
  return apiFetch<BatchOverview>(`/api/v1/batches/${batchId}/overview/`);
}

// --- Batch roster (with performance rollups) --------------------------

export interface BatchStudentRow {
  enrollment_id: string;
  student_id: string;
  name: string;
  status: EnrollmentStatus;
  attendance_percent: number | null;
  assessment_average: number | null;
  assignments_submitted: number;
  assignments_total: number;
  projects_submitted: number;
  projects_total: number;
  progress_percent: number | null;
  risk_flags: string[];
  transferred_in: boolean;
}

export function listBatchStudents(
  batchId: string,
  query: ListQuery = {},
): Promise<Paginated<BatchStudentRow>> {
  return apiFetch<Paginated<BatchStudentRow>>(`/api/v1/batches/${batchId}/students/${queryString(query)}`);
}

// --- Trainers hub ----------------------------------------------------------

/** A trainers-hub row — see `ManageBatchRow` for why the extra fields are optional. */
export interface ManageTrainerRow extends TrainerListRow {
  active_batches?: number | null;
  at_risk_students?: number | null;
  overdue_dsr?: number | null;
}

export function listManageTrainers(query: ListQuery = {}): Promise<Paginated<ManageTrainerRow>> {
  return listTrainers(query);
}

// --- Trainer overview --------------------------------------------------

export interface TrainerReviewItem {
  id: string;
  period_start: string;
  period_end: string;
  rating: number;
  summary: string;
  reviewer: string;
  created_at: string;
}

export interface StudentFeedbackItem {
  id: string;
  body: string;
  created_at: string;
  batch_code: string;
}

export interface TrainerOverview {
  trainer: { id: string; name: string; trainer_id: string; email: string };
  batches: { total: number; active: number };
  students: { total: number; at_risk: number };
  submission: {
    attendance_rate: number | null;
    dsr_rate: number | null;
    dsr_approval_rate: number | null;
  };
  completion: { assessments: number | null; assignments: number | null; projects: number | null };
  outcomes: { student_average_score: number | null; student_attendance_percent: number | null };
  pending: {
    dsr_to_submit: number;
    assignments_to_grade: number;
    projects_to_review: number;
    overdue: number;
  };
  reviews: TrainerReviewItem[];
  student_feedback: StudentFeedbackItem[];
  as_of: string;
}

export async function getTrainerOverview(trainerId: string): Promise<TrainerOverview> {
  return apiFetch<TrainerOverview>(`/api/v1/trainers/${trainerId}/overview/`);
}

// --- Inline DSR approval -----------------------------------------------

export type DsrStatus =
  | 'draft'
  | 'submitted'
  | 'under_review'
  | 'approved'
  | 'rejected'
  | 'revision_required';

export type DsrReviewDecision = 'under_review' | 'approved' | 'rejected' | 'revision_required';

/**
 * A lean read of `DSRSerializer` — only the fields the batch page's inline
 * review queue renders. The real response carries the full report (teaching
 * notes, counts, module, …); this type does not claim otherwise, it just
 * does not need the rest.
 */
export interface ManageDsrRow {
  id: string;
  batch_code: string;
  trainer_name: string;
  trainer_code: string;
  report_date: string;
  actual_topic: string;
  status: DsrStatus;
  submitted_at: string | null;
}

export function listBatchDsr(batchId: string, query: ListQuery = {}): Promise<Paginated<ManageDsrRow>> {
  return apiFetch<Paginated<ManageDsrRow>>(`/api/v1/batches/${batchId}/dsr/${queryString(query)}`);
}

/**
 * Approve, reject, or send back one daily status report.
 *
 * `APPROVED` is a terminal status server-side — there is no transition out of
 * it, so a second call reverting an approval would always fail with a 409.
 * That is why the inline queue's "undo" is a rollback on failure (see
 * `components/manage/dsr-review-queue.tsx`), not a button offered after
 * success that the server could never honour.
 */
export function reviewDsr(dsrId: string, decision: DsrReviewDecision, comments = ''): Promise<ManageDsrRow> {
  return apiMutate<ManageDsrRow>(`/api/v1/dsr/${dsrId}/review/`, {
    method: 'POST',
    body: { decision, comments },
  });
}

// --- Writing a trainer review --------------------------------------------

export interface TrainerReviewWrite {
  trainer: string;
  period_start: string;
  period_end: string;
  rating: number;
  summary?: string;
  strengths?: string;
  concerns?: string;
  actions?: string;
}

/** A lean read of `PerformanceReviewSerializer` — only what the trainer page uses. */
export interface PerformanceReviewRecord {
  id: string;
  period_start: string;
  period_end: string;
  rating: number;
  summary: string;
  reviewer_name: string | null;
  created_at: string;
}

export function createTrainerReview(payload: TrainerReviewWrite): Promise<PerformanceReviewRecord> {
  return apiMutate<PerformanceReviewRecord>('/api/v1/performance/reviews/', {
    method: 'POST',
    body: payload,
  });
}

// --- One student's full performance picture -----------------------------

export interface StudentRiskOutcome {
  key: string;
  label: string;
  triggered: boolean;
  severity: 'none' | 'warning' | 'critical';
  detail: string;
}

/**
 * `apps.performance.engine.student_performance`'s exact return shape, for one
 * enrolment. Every numeric field is a real number or `null` by that module's
 * own contract — never `NaN`, never omitted — which is what makes reading it
 * with plain `lib/format.ts` fallbacks correct rather than merely convenient.
 */
export interface StudentPerformanceRow {
  enrollment_id: string;
  course_title: string;
  batch_code: string;
  attendance: { percent: number | null; total_sessions: number; attended: number; has_records: boolean };
  assessment: { average_percent: number | null; sitting_percent: number | null; recorded: number; total: number };
  assignments: {
    percent: number | null;
    total: number;
    submitted: number;
    graded: number;
    passed: number;
    missed: number;
  };
  projects: { percent: number | null; required: number; finished: number };
  progress: { percent: number | null; expected_percent: number | null; variance: number | null };
  overall_score: number | null;
  risk: { at_risk: boolean; outcomes: StudentRiskOutcome[]; triggered: string[]; triggered_count: number };
}

/** Every enrolment on one batch, from the performance engine — see the module docstring. */
export function getBatchPerformance(batchId: string): Promise<StudentPerformanceRow[]> {
  return apiFetch<StudentPerformanceRow[]>(`/api/v1/batches/${batchId}/performance/`);
}

/** A lean read of `FeedbackSerializer` — feedback left about a student or a trainer. */
export interface FeedbackItem {
  id: string;
  student_code: string | null;
  trainer_code: string | null;
  batch_code: string | null;
  body: string;
  author_name: string | null;
  created_at: string;
}

/**
 * Every piece of feedback the caller may see, across every student and
 * trainer. There is no server-side filter by subject yet, so the student page
 * (the one caller of this today) fetches the visible set and matches
 * `student_code` itself — workable at today's institution size, and flagged
 * as a candidate for a real `?student=` filter if that stops being true.
 */
export function listFeedback(): Promise<FeedbackItem[]> {
  return apiFetch<FeedbackItem[]>('/api/v1/performance/feedback/');
}

// --- Shared display helpers -------------------------------------------

export const TIMELINE_STATUS_LABEL: Record<TimelineStatus, string> = {
  ahead: 'Ahead of plan',
  on_track: 'On track',
  behind: 'Behind plan',
  not_started: 'Not started',
};

export const TIMELINE_STATUS_VARIANT: Record<TimelineStatus, 'neutral' | 'success' | 'warning' | 'error'> = {
  ahead: 'success',
  on_track: 'success',
  behind: 'error',
  not_started: 'neutral',
};

/**
 * The plan-vs-actual variance stated in words, so the number is never the
 * only thing on the screen that says what it means — see the batch detail
 * page's timeline section, which is the one place this reads oddly without
 * the sentence next to it.
 */
export function describeTimelineVariance(
  status: TimelineStatus,
  variancePercent: number | null,
): string {
  if (status === 'not_started') return 'This batch has not started yet.';
  if (variancePercent === null) return 'Not enough of the course has run yet to compare plan against actual.';
  const points = Math.abs(Math.round(variancePercent));
  if (status === 'ahead') return `${points} percentage point${points === 1 ? '' : 's'} ahead of the plan.`;
  if (status === 'behind') return `${points} percentage point${points === 1 ? '' : 's'} behind the plan.`;
  return 'Running on track with the plan.';
}

export const DSR_STATUS_LABEL: Record<DsrStatus, string> = {
  draft: 'Draft',
  submitted: 'Submitted',
  under_review: 'Under review',
  approved: 'Approved',
  rejected: 'Rejected',
  revision_required: 'Revision required',
};

export const DSR_STATUS_VARIANT: Record<DsrStatus, 'neutral' | 'success' | 'warning' | 'error'> = {
  draft: 'neutral',
  submitted: 'warning',
  under_review: 'warning',
  approved: 'success',
  rejected: 'error',
  revision_required: 'error',
};

/**
 * The risk engine's own labels for the flag keys it currently emits
 * (`apps/performance/risk.py`'s `RULES`), so a known flag reads exactly the
 * way the engine itself describes it. Anything else — a flag key this file
 * has not seen yet — still renders, humanised from its raw form, rather than
 * disappearing or showing a blank: the whole point of a risk flag is that it
 * is visible, so an unrecognised one is the last thing that should go quiet.
 */
const KNOWN_RISK_FLAG_LABEL: Record<string, string> = {
  attendance: 'Attendance',
  academic: 'Assessment average',
  assignments: 'Missed assignments',
  progress: 'Course progress',
};

export function describeRiskFlag(flag: string): string {
  const known = KNOWN_RISK_FLAG_LABEL[flag];
  if (known) return known;
  const spaced = flag.replace(/[_-]+/g, ' ').trim();
  if (!spaced) return 'Risk flag';
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}
