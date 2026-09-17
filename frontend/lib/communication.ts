/**
 * API calls for notifications, announcements, discussions, the learning
 * surface, and the Communication Center (ERP Phase 19, ADR-12,
 * `docs/erp/COMMUNICATION_CATALOG.md`, `API_CONTRACTS.md` "Communication
 * (Phase 19)").
 */

import { ApiError, apiFetch, apiMutate, queryString } from './api';
import type {
  Announcement,
  AppNotification,
  Audience,
  Bookmark,
  CommunicationChannel,
  CommunicationRecipientSpec,
  Delivery,
  DeliveryState,
  DiscussionReply,
  DiscussionThread,
  DiscussionThreadDetail,
  LearningHome,
  LessonNote,
  MessageTemplate,
  NotificationPreference,
  Paginated,
  Peer,
  TemplatePreviewResult,
  TemplateVersion,
  UpcomingItem,
} from '@/types/api';

// --- Notifications ---------------------------------------------------------

export async function listNotifications(
  query: { unread?: string; category?: string; page?: number } = {},
): Promise<Paginated<AppNotification>> {
  return apiFetch<Paginated<AppNotification>>(`/api/v1/notifications/${queryString(query)}`);
}

/** What the bell shows. Cheap enough to poll. */
export async function unreadCount(): Promise<{ unread: number }> {
  return apiFetch<{ unread: number }>('/api/v1/notifications/unread/');
}

export async function markNotificationRead(id: string): Promise<AppNotification> {
  return apiMutate<AppNotification>(`/api/v1/notifications/${id}/read/`, { method: 'POST' });
}

export async function markAllNotificationsRead(): Promise<{ unread: number }> {
  return apiMutate<{ unread: number }>('/api/v1/notifications/read-all/', { method: 'POST' });
}

export async function getNotificationPreferences(): Promise<NotificationPreference> {
  return apiFetch<NotificationPreference>('/api/v1/notifications/preferences/');
}

export async function updateNotificationPreferences(
  changes: Partial<NotificationPreference>,
): Promise<NotificationPreference> {
  return apiMutate<NotificationPreference>('/api/v1/notifications/preferences/', {
    method: 'PATCH',
    body: changes,
  });
}

// --- Announcements ---------------------------------------------------------

export async function listAnnouncements(
  query: { status?: string; batch?: string; page?: number } = {},
): Promise<Paginated<Announcement>> {
  return apiFetch<Paginated<Announcement>>(`/api/v1/announcements/${queryString(query)}`);
}

export async function createAnnouncement(payload: {
  title: string;
  body: string;
  audience: Audience;
  course?: string;
  batch?: string;
  // New audiences (ERP Phase 19): `role` addresses everyone holding a role
  // slug (`lib/labels.ts::ROLE_OPTIONS`); `branch` addresses one centre.
  role?: string;
  branch?: string;
  expires_at?: string;
  // Schedule for later instead of publishing now — `publish_at` alone puts
  // the draft in `scheduled` state; the `announcements.publish_due` beat task
  // publishes it at that moment (`API_CONTRACTS.md`).
  publish_at?: string;
  is_pinned?: boolean;
}): Promise<Announcement> {
  return apiMutate<Announcement>('/api/v1/announcements/', { method: 'POST', body: payload });
}

export async function publishAnnouncement(id: string): Promise<Announcement> {
  return apiMutate<Announcement>(`/api/v1/announcements/${id}/publish/`, { method: 'POST' });
}

export async function archiveAnnouncement(id: string): Promise<Announcement> {
  return apiMutate<Announcement>(`/api/v1/announcements/${id}/archive/`, { method: 'POST' });
}

/** Moves a draft carrying a `publish_at` into `scheduled`
 *  (`API_CONTRACTS.md`: "`POST .../schedule/` moves draft → scheduled"). */
export async function scheduleAnnouncement(
  id: string,
  publishAt: string,
): Promise<Announcement> {
  return apiMutate<Announcement>(`/api/v1/announcements/${id}/schedule/`, {
    method: 'POST',
    body: { publish_at: publishAt },
  });
}

/** From `scheduled` back to `cancelled` — never sent. */
export async function cancelAnnouncement(id: string): Promise<Announcement> {
  return apiMutate<Announcement>(`/api/v1/announcements/${id}/cancel/`, { method: 'POST' });
}

export async function announcementAudience(id: string): Promise<{ recipients: number }> {
  return apiFetch<{ recipients: number }>(`/api/v1/announcements/${id}/audience/`);
}

// --- Communication Center: templates ----------------------------------------
//
// A template's body is written by an administrator but rendered against real
// student/trainer/activity data at send time (D-051). This client never
// evaluates a body itself — every render (`previewTemplate`, `testSendTemplate`,
// the real send) is a server round trip, and the returned `html` is already
// sanitised HTML the caller renders in a sandboxed iframe (never
// `dangerouslySetInnerHTML`) — see `components/communication/template-preview.tsx`.

export async function listTemplates(
  query: { channel?: CommunicationChannel; status?: string; page?: number } = {},
): Promise<Paginated<MessageTemplate>> {
  return apiFetch<Paginated<MessageTemplate>>(`/api/v1/templates/${queryString(query)}`);
}

export interface CreateTemplatePayload {
  key: string;
  name: string;
  channel: CommunicationChannel;
  kind: string;
  language?: string;
}

export async function createTemplate(payload: CreateTemplatePayload): Promise<MessageTemplate> {
  return apiMutate<MessageTemplate>('/api/v1/templates/', { method: 'POST', body: payload });
}

export async function getTemplate(key: string): Promise<MessageTemplate> {
  return apiFetch<MessageTemplate>(`/api/v1/templates/${key}/`);
}

/** Every field is optional on the wire — `PUT` is a partial update — but the
 *  builder always sends the full set it has open, so partial-ness only
 *  matters to the type of `updateTemplateVersion`'s parameter. */
export interface TemplateVersionPayload {
  subject: string;
  body_html: string;
  body_text: string;
  /** The allowlist this version's body may reference — nothing else in the
   *  body is ever substituted (D-051). */
  variables: string[];
  provider_template_id?: string;
}

/**
 * Opens the next draft version, cloned server-side from whatever is
 * currently published (`TemplateVersionCreateView`'s own docstring: "a new
 * draft on top of whatever is currently published" — the request body is
 * ignored, `request=None` in its schema). Refused with `409` if an
 * unpublished version already exists for this template — there is never
 * more than one draft in flight at a time. Edit the returned version's
 * content with `updateTemplateVersion`.
 */
export async function createTemplateVersion(key: string): Promise<TemplateVersion> {
  return apiMutate<TemplateVersion>(`/api/v1/templates/${key}/versions/`, {
    method: 'POST',
    body: {},
  });
}

/** `PUT .../versions/{n}/` — a partial update on the one version that is not
 *  yet published (draft, or approved-but-unpublished; editing an approved
 *  one clears its approval server-side, matching `TemplateBuilder`'s own
 *  notice). The server refuses this once that version is published. */
export async function updateTemplateVersion(
  key: string,
  number: number,
  payload: Partial<TemplateVersionPayload>,
): Promise<TemplateVersion> {
  return apiMutate<TemplateVersion>(`/api/v1/templates/${key}/versions/${number}/`, {
    method: 'PUT',
    body: payload,
  });
}

/** `template.approve`; a WhatsApp-channel template's approval may come back
 *  `403 step_up_required` — the caller retries this same call once the
 *  `StepUpDialog` confirms (`components/roles/step-up-dialog.tsx`'s pattern). */
export async function approveTemplateVersion(
  key: string,
  number: number,
): Promise<TemplateVersion> {
  return apiMutate<TemplateVersion>(`/api/v1/templates/${key}/versions/${number}/approve/`, {
    method: 'POST',
    body: {},
  });
}

export async function publishTemplateVersion(
  key: string,
  number: number,
): Promise<TemplateVersion> {
  return apiMutate<TemplateVersion>(`/api/v1/templates/${key}/versions/${number}/publish/`, {
    method: 'POST',
    body: {},
  });
}

/** Renders a version against `variables` server-side: substitution over the
 *  version's own allowlist only, HTML-escaped, then sanitised — never this
 *  client evaluating anything (D-051, ADR-12). `warnings` names any variable
 *  the body referenced that is not on the allowlist. */
export async function previewTemplateVersion(
  key: string,
  number: number,
  variables: Record<string, string>,
): Promise<TemplatePreviewResult> {
  return apiMutate<TemplatePreviewResult>(`/api/v1/templates/${key}/versions/${number}/preview/`, {
    method: 'POST',
    body: { variables },
  });
}

/**
 * Sends a real message on this version's channel to the signed-in user only
 * (`COMMUNICATION_CATALOG.md`: "Test send goes to the signed-in user
 * only"), throttled server-side under the `communication` scope. Takes no
 * body — `TemplateVersionTestSendView`'s schema is `request=None`; the
 * server renders against the caller's own account data, not the Preview
 * panel's typed-in values, and returns the resulting `Delivery` row.
 */
export async function testSendTemplateVersion(key: string, number: number): Promise<Delivery> {
  return apiMutate<Delivery>(`/api/v1/templates/${key}/versions/${number}/test-send/`, {
    method: 'POST',
    body: {},
  });
}

// --- Communication Center: delivery log -------------------------------------

export interface DeliveryFilters {
  channel?: CommunicationChannel;
  state?: DeliveryState;
  recipient?: string;
  template?: string;
  since?: string;
  until?: string;
  page?: number;
  [key: string]: string | number | undefined;
}

export async function listDeliveries(filters: DeliveryFilters = {}): Promise<Paginated<Delivery>> {
  return apiFetch<Paginated<Delivery>>(`/api/v1/deliveries/${queryString(filters)}`);
}

/** `failed` rows only — the server re-checks state and refuses otherwise. */
export async function retryDelivery(id: string): Promise<Delivery> {
  return apiMutate<Delivery>(`/api/v1/deliveries/${id}/retry/`, { method: 'POST' });
}

/** `queued` rows only. */
export async function cancelDelivery(id: string): Promise<Delivery> {
  return apiMutate<Delivery>(`/api/v1/deliveries/${id}/cancel/`, { method: 'POST' });
}

// --- Communication Center: manual send ---------------------------------------

export interface SendCommunicationPayload {
  channel: CommunicationChannel;
  template: string;
  recipients: CommunicationRecipientSpec;
  variables?: Record<string, string>;
  confirm_count: number;
}

/** `services.manual_send`'s return value: `{"count": len(deliveries),
 *  "delivery_ids": [...]}`. */
export interface SendCommunicationResult {
  count: number;
  delivery_ids: string[];
}

/**
 * `POST /communication/send/` recomputes the recipient count from scratch
 * and refuses with `409` (`ConflictError({"confirm_count": [...]})`,
 * verified against `apps/communication/services.py::manual_send`) whenever
 * the caller's `confirm_count` does not match. The contract names no
 * separate endpoint for the first look the UI shows before that
 * confirmation, and the field is `IntegerField(min_value=0)` — no sentinel
 * value passes validation without being a real, meaningful guess — so this
 * asks the same endpoint honestly: `confirm_count: 0`.
 *
 * Two outcomes, both truthful:
 *  - The real count genuinely is 0 (no eligible recipient): the request
 *    succeeds, sending to nobody, and `result.count` (0) is returned as is.
 *  - The real count is anything else: the server refuses with `409` before
 *    creating a single `Delivery` row, and its message —
 *    "there are now N eligible recipient(s)" — is *the* current count,
 *    parsed here rather than guessed at or computed in the browser.
 *
 * This is the one path in the whole flow that is a compromise rather than a
 * dedicated read: the pinned contract has no `GET` for this count, so
 * "preview" is a real `POST /communication/send/` call every time, gated by
 * `communication.send` like the send itself. It never delivers anything
 * (a mismatch refuses before `create_deliveries` runs, and a genuine-zero
 * match delivers to zero people), but it does add a `communication.sent`
 * audit row for that zero-count case — a limitation flagged for the next
 * review, not a silent one.
 */
export async function previewCommunicationCount(
  payload: Omit<SendCommunicationPayload, 'confirm_count'>,
): Promise<number> {
  try {
    const result = await apiMutate<SendCommunicationResult>('/api/v1/communication/send/', {
      method: 'POST',
      body: { ...payload, confirm_count: 0 },
    });
    return result.count;
  } catch (cause) {
    if (cause instanceof ApiError && cause.status === 409) {
      const raw = cause.details?.confirm_count;
      const text = Array.isArray(raw) ? raw[0] : raw;
      const match = typeof text === 'string' ? text.match(/(\d+)/) : null;
      if (match) return Number(match[1]);
    }
    throw cause;
  }
}

/** The real send, `confirm_count` set to whatever count the caller last
 *  showed and had confirmed. A `409` here means the roster changed between
 *  that confirmation and this call — the caller's job is to show "the count
 *  changed, please review again" and re-run `previewCommunicationCount`
 *  rather than retry blindly with the same stale number. */
export async function sendCommunication(
  payload: SendCommunicationPayload,
): Promise<SendCommunicationResult> {
  return apiMutate<SendCommunicationResult>('/api/v1/communication/send/', {
    method: 'POST',
    body: payload,
  });
}

// --- Discussions -----------------------------------------------------------

export async function listThreads(
  query: { batch?: string; unanswered?: string; page?: number } = {},
): Promise<Paginated<DiscussionThread>> {
  return apiFetch<Paginated<DiscussionThread>>(`/api/v1/discussions/${queryString(query)}`);
}

export async function getThread(id: string): Promise<DiscussionThreadDetail> {
  return apiFetch<DiscussionThreadDetail>(`/api/v1/discussions/${id}/`);
}

export async function startThread(
  batchId: string,
  payload: { title: string; body: string },
): Promise<DiscussionThread> {
  return apiMutate<DiscussionThread>(`/api/v1/batches/${batchId}/threads/`, {
    method: 'POST',
    body: payload,
  });
}

export async function replyToThread(
  threadId: string,
  body: string,
): Promise<DiscussionReply> {
  return apiMutate<DiscussionReply>(`/api/v1/discussions/${threadId}/replies/`, {
    method: 'POST',
    body: { body },
  });
}

export async function moderateThread(
  threadId: string,
  changes: { pinned?: boolean; closed?: boolean },
): Promise<DiscussionThread> {
  return apiMutate<DiscussionThread>(`/api/v1/discussions/${threadId}/moderate/`, {
    method: 'POST',
    body: changes,
  });
}

export async function hideReply(replyId: string, reason: string): Promise<DiscussionReply> {
  return apiMutate<DiscussionReply>(`/api/v1/discussions/replies/${replyId}/hide/`, {
    method: 'POST',
    body: { reason },
  });
}

// --- Learning surface ------------------------------------------------------

export async function learningHome(): Promise<LearningHome[]> {
  return apiFetch<LearningHome[]>('/api/v1/learning/home/');
}

export async function upcomingWork(): Promise<UpcomingItem[]> {
  return apiFetch<UpcomingItem[]>('/api/v1/learning/upcoming/');
}

export async function listBookmarks(): Promise<Bookmark[]> {
  return apiFetch<Bookmark[]>('/api/v1/learning/bookmarks/');
}

export async function listNotes(): Promise<LessonNote[]> {
  return apiFetch<LessonNote[]>('/api/v1/learning/notes/');
}

export async function setBookmark(lessonId: string, note = ''): Promise<Bookmark> {
  return apiMutate<Bookmark>(`/api/v1/learning/lessons/${lessonId}/bookmark/`, {
    method: 'POST',
    body: { note },
  });
}

export async function removeBookmark(lessonId: string): Promise<void> {
  await apiMutate<void>(`/api/v1/learning/lessons/${lessonId}/bookmark/`, { method: 'DELETE' });
}

export async function getNote(lessonId: string): Promise<LessonNote | Record<string, never>> {
  return apiFetch<LessonNote | Record<string, never>>(
    `/api/v1/learning/lessons/${lessonId}/note/`,
  );
}

export async function saveNote(
  lessonId: string,
  body: string,
): Promise<LessonNote | Record<string, never>> {
  return apiMutate<LessonNote | Record<string, never>>(
    `/api/v1/learning/lessons/${lessonId}/note/`,
    { method: 'PUT', body: { body } },
  );
}

/** §7.7 — names and student ids only; the backend returns nothing else. */
export async function listClassmates(enrollmentId: string): Promise<Peer[]> {
  return apiFetch<Peer[]>(`/api/v1/learning/enrollments/${enrollmentId}/classmates/`);
}
