/** API calls for notifications, announcements, discussions and the learning surface. */

import { apiFetch, apiMutate, queryString } from './api';
import type {
  Announcement,
  AppNotification,
  Audience,
  Bookmark,
  DiscussionReply,
  DiscussionThread,
  DiscussionThreadDetail,
  LearningHome,
  LessonNote,
  NotificationPreference,
  Paginated,
  Peer,
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
  expires_at?: string;
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

export async function announcementAudience(id: string): Promise<{ recipients: number }> {
  return apiFetch<{ recipients: number }>(`/api/v1/announcements/${id}/audience/`);
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
