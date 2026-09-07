/**
 * The daily status report — the trainer's end-of-class account of one class —
 * plus the small amount of session-curriculum plumbing the "Today's Class"
 * workspace needs alongside it.
 *
 * Two things live here that are not, strictly, "DSR":
 *
 * 1. `recordTopic`. The planned-versus-actual lesson fields now live on
 *    `ClassSession` in `types/api.ts`, where they belong — this module briefly
 *    carried a local `SessionWithTopic` because the shared type had not caught
 *    up with the backend, and that shim is gone.
 * 2. The `localStorage` draft. It shadows both the DSR fields *and* the
 *    trainer's in-progress register marks, because from the trainer's chair
 *    both are "what I typed since I opened this class" — losing either to a
 *    closed tab is the same failure. The server has no draft concept for
 *    attendance (only the atomic register POST), so the register half of the
 *    snapshot is local-only; the DSR half is also pushed to the server draft
 *    wherever `is_editable` allows it.
 *
 * Why the write payload is narrower than the model
 * --------------------------------------------------
 * `DSRWriteSerializer` accepts `report_date`, `start_time`, `end_time` and
 * `module`, but this screen never sends them: the first three already default
 * server-side to the session's own values (`services.start_dsr`), and this
 * fast, end-of-class capture has no UI for re-pointing a report at a
 * different curriculum module. Every field below is one this screen actually
 * puts a control in front of the trainer for.
 */

import { getSession, recordSessionTopic, type SessionTopicStatus } from './academics';
import { apiFetch, apiMutate, queryString } from './api';
import { NOT_AVAILABLE } from './format';
import type { ListQuery } from './people';
import type { AttendanceStatus, ClassSession, Paginated } from '@/types/api';

/**
 * `HH:MM` from a session's `HH:MM:SS` wall-clock string, or the app's
 * fallback for anything else. `lib/format.ts`'s date formatters do not apply
 * here — a session's `start_time`/`end_time` is a plain time-of-day string,
 * not a parseable date — so this small, locked-down formatter lives here and
 * is shared by every teaching component that shows a class's time.
 */
export function formatClassTime(value: unknown): string {
  return typeof value === 'string' && value.length >= 5 ? value.slice(0, 5) : NOT_AVAILABLE;
}

// --- Session topic (planned vs. actual lesson) ------------------------------

/** Re-exported so callers need one import for everything this screen's
 *  topic control touches — see `academics.ts` for the canonical definition. */
export type TopicStatus = SessionTopicStatus;

/** `ClassSession` plus the curriculum-topic fields the session endpoints
 *  already return — see the module docstring for why this is not in
 *  `types/api.ts`. */
/** Kept as an alias so the screens that named it do not all have to change. */
export type SessionWithTopic = ClassSession;

export async function getSessionWithTopic(id: string): Promise<SessionWithTopic> {
  const session = await getSession(id);
  return session as SessionWithTopic;
}

/** Record what a class actually covered (or that nothing was). Typed more
 *  richly than `recordSessionTopic` itself — see the module docstring. */
export async function recordTopic(
  sessionId: string,
  payload: { lesson_id: string | null; status: TopicStatus },
): Promise<SessionWithTopic> {
  const session = await recordSessionTopic(sessionId, payload);
  return session as SessionWithTopic;
}

// --- Daily status report -----------------------------------------------------

/** Mirrors `apps.dsr.models.DSRStatus`. */
export type DSRStatus =
  | 'draft'
  | 'submitted'
  | 'under_review'
  | 'approved'
  | 'rejected'
  | 'revision_required';

/**
 * The read shape, matching `DSRSerializer` field for field. `id` (and
 * `created_at`/`updated_at`) are `null` on an unsaved preview — the backend's
 * `GET /sessions/<id>/dsr/` returns one when no report has been started yet,
 * shaped exactly as `POST` would create it, so the screen can render from one
 * request either way. That is the one signal this screen uses to tell "an
 * existing draft" from "nothing written yet".
 */
export interface DSR {
  id: string | null;
  session: string;
  session_date: string;
  batch: string;
  batch_code: string;
  trainer: string;
  trainer_code: string;
  trainer_name: string;
  report_date: string;
  start_time: string;
  end_time: string;
  module: string | null;
  module_title: string | null;
  planned_topic: string;
  actual_topic: string;
  student_count: number;
  present_count: number;
  absent_count: number;
  online_count: number;
  offline_count: number;
  teaching_notes: string;
  issues: string;
  student_concerns: string;
  assignment_given: boolean;
  assessment_conducted: boolean;
  status: DSRStatus;
  is_editable: boolean;
  submitted_at: string | null;
  reviewed_at: string | null;
  reviewed_by: string | null;
  reviewed_by_name: string | null;
  manager_comments: string;
  created_at: string | null;
  updated_at: string | null;
}

/** Every field this screen puts a control in front of. See the module
 *  docstring for what `DSRWriteSerializer` allows that is deliberately absent. */
export interface DSRWritePayload {
  actual_topic?: string;
  student_count?: number;
  present_count?: number;
  absent_count?: number;
  online_count?: number;
  offline_count?: number;
  teaching_notes?: string;
  issues?: string;
  student_concerns?: string;
  assignment_given?: boolean;
  assessment_conducted?: boolean;
  /** Hand straight to the reviewer in the same request — see
   *  `SessionDSRView.post` / `DSRDetailView.patch` on the backend. */
  submit?: boolean;
}

/** The writable subset of a fetched `DSR`, for seeding the draft a trainer edits. */
export function toWritePayload(dsr: DSR): DSRWritePayload {
  return {
    actual_topic: dsr.actual_topic,
    student_count: dsr.student_count,
    present_count: dsr.present_count,
    absent_count: dsr.absent_count,
    online_count: dsr.online_count,
    offline_count: dsr.offline_count,
    teaching_notes: dsr.teaching_notes,
    issues: dsr.issues,
    student_concerns: dsr.student_concerns,
    assignment_given: dsr.assignment_given,
    assessment_conducted: dsr.assessment_conducted,
  };
}

/** The report for a class: the saved draft/submission if one exists, else an
 *  unsaved preview (`id: null`) shaped exactly as `startDsr` would create it. */
export async function getSessionDsr(sessionId: string): Promise<DSR> {
  return apiFetch<DSR>(`/api/v1/sessions/${sessionId}/dsr/`);
}

/** Create the draft for a class. Pass `submit: true` to hand it to the
 *  reviewer in the same call. */
export async function startDsr(sessionId: string, payload: DSRWritePayload = {}): Promise<DSR> {
  return apiMutate<DSR>(`/api/v1/sessions/${sessionId}/dsr/`, { method: 'POST', body: payload });
}

/** Edit an existing draft (or, with `submit: true`, edit and hand it over in
 *  one call). Refused by the backend once the report has left the trainer's
 *  hands — surfaced to the caller as a normal `ApiError`. */
export async function updateDsr(id: string, changes: DSRWritePayload): Promise<DSR> {
  return apiMutate<DSR>(`/api/v1/dsr/${id}/`, { method: 'PATCH', body: changes });
}

/** Hand an already-saved draft to its reviewer with no further edits. Rarely
 *  needed directly — `updateDsr`/`startDsr` with `submit: true` covers the
 *  normal "confirm and hand over" case in one request — but kept for a
 *  trainer who autosaved, stepped away, and comes back only to submit. */
export async function submitDsr(id: string): Promise<DSR> {
  return apiMutate<DSR>(`/api/v1/dsr/${id}/submit/`, { method: 'POST' });
}

/**
 * A `DSR` from a list endpoint, where `id` is never null.
 *
 * `DSR.id` is nullable because `GET /sessions/<id>/dsr/` overloads the same
 * shape onto an unsaved preview (see `DSR`'s own docstring) — but nothing
 * `listDsr` returns is ever a preview; every row it hands back is a
 * persisted report with a real primary key. Narrowing it here means the
 * manager's review queue can key rows and build URLs from `row.id` directly,
 * rather than every call site re-deriving "but this list never has that
 * case" on its own.
 */
export type DSRListItem = DSR & { id: string };

/**
 * Every report the caller may see, across every batch — `GET /api/v1/dsr/`,
 * staff-only (`apps.dsr.access.can_read_dsrs` refuses a student or a
 * counsellor outright rather than answering with an empty page). Backs the
 * manager's review queue at `/dsr`, which is the one screen in this app that
 * needs a cross-batch view of reports rather than one class's or one batch's.
 *
 * `DSRFilterSet` recognises `batch`, `trainer`, `status`, `date_after` and
 * `date_before`; anything else in `query` (a stray `search` or `ordering`, for
 * instance) is simply not a field the filter backend looks at and is ignored
 * rather than rejected — `ListQuery`'s shape is shared across every list
 * screen in the app, not tailored per endpoint, so this is the normal way an
 * endpoint that supports a subset of it behaves. There genuinely is no
 * `ordering` parameter to send: the view declares no ordering filter backend,
 * so results always come back in the model's own newest-first order
 * (`Meta.ordering` on `DSR`), which is exactly what the queue wants by
 * default and is not something a client request can change.
 */
export function listDsr(query: ListQuery = {}): Promise<Paginated<DSRListItem>> {
  return apiFetch<Paginated<DSRListItem>>(`/api/v1/dsr/${queryString(query)}`);
}

// --- Local draft (autosave fallback) ----------------------------------------

/**
 * What survives a closed tab: the DSR fields the trainer has typed, and the
 * register marks they have keyed in, keyed together per session so reopening
 * the same class — today or a backdated catch-up — finds both.
 */
export interface DsrDraftSnapshot {
  savedAt: string;
  fields: DSRWritePayload;
  marks: Record<string, AttendanceStatus>;
  /** The topic control's current value — a lesson id, `''` (untouched, no
   *  plan to default to) or the skip sentinel. See `class-header.tsx`. */
  topicSelection: string;
}

const DRAFT_STORAGE_PREFIX = 'grras.dsr-draft.';

function draftStorageKey(sessionId: string): string {
  return `${DRAFT_STORAGE_PREFIX}${sessionId}`;
}

function isDraftSnapshot(value: unknown): value is DsrDraftSnapshot {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.savedAt === 'string' &&
    typeof candidate.fields === 'object' &&
    candidate.fields !== null &&
    typeof candidate.marks === 'object' &&
    candidate.marks !== null &&
    typeof candidate.topicSelection === 'string'
  );
}

/** Read a session's local draft, or `null` if there is none — including when
 *  storage is unreachable (a private window throws on access) or the stored
 *  value is not valid JSON shaped like a draft. Never throws. */
export function readDsrDraft(sessionId: string): DsrDraftSnapshot | null {
  try {
    const raw = window.localStorage.getItem(draftStorageKey(sessionId));
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return isDraftSnapshot(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

/** Persist a session's local draft. Silently does nothing if storage is
 *  unreachable — the in-memory form state still carries the session; there is
 *  simply no safety net left if the tab closes. */
export function writeDsrDraft(sessionId: string, snapshot: DsrDraftSnapshot): void {
  try {
    window.localStorage.setItem(draftStorageKey(sessionId), JSON.stringify(snapshot));
  } catch {
    // No persistence available. Nothing else to do.
  }
}

/** Drop a session's local draft once it has been safely submitted (or the
 *  trainer explicitly discards it). */
export function clearDsrDraft(sessionId: string): void {
  try {
    window.localStorage.removeItem(draftStorageKey(sessionId));
  } catch {
    // Nothing to clean up if storage was never reachable.
  }
}
