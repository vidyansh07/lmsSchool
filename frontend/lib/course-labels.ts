/** Display labels for course enumerations, kept in one place. */

import type {
  CourseDifficulty,
  LessonContentType,
  PublishStatus,
  CourseVisibility,
} from '@/types/api';

export const STATUS_LABEL: Record<PublishStatus, string> = {
  draft: 'Draft',
  in_review: 'In review',
  published: 'Published',
  archived: 'Archived',
};

export const STATUS_VARIANT: Record<PublishStatus, 'neutral' | 'success' | 'warning' | 'error'> = {
  draft: 'neutral',
  in_review: 'warning',
  published: 'success',
  archived: 'error',
};

export const DIFFICULTY_LABEL: Record<CourseDifficulty, string> = {
  beginner: 'Beginner',
  intermediate: 'Intermediate',
  advanced: 'Advanced',
};

export const DIFFICULTY_OPTIONS = (
  Object.keys(DIFFICULTY_LABEL) as CourseDifficulty[]
).map((value) => ({ value, label: DIFFICULTY_LABEL[value] }));

export const VISIBILITY_LABEL: Record<CourseVisibility, string> = {
  public: 'Public — listed in the catalogue',
  internal: 'Internal — signed-in users only',
  private: 'Private — assigned people only',
};

export const VISIBILITY_OPTIONS = (
  Object.keys(VISIBILITY_LABEL) as CourseVisibility[]
).map((value) => ({ value, label: VISIBILITY_LABEL[value] }));

export const CONTENT_TYPE_LABEL: Record<LessonContentType, string> = {
  text: 'Text',
  video: 'Video',
  document: 'Document',
  external_link: 'Link',
};

export const CONTENT_TYPE_OPTIONS = (
  Object.keys(CONTENT_TYPE_LABEL) as LessonContentType[]
).map((value) => ({ value, label: CONTENT_TYPE_LABEL[value] }));

/** "1h 45m" from a minute count. */
export function formatDuration(minutes: number | null | undefined): string {
  if (!minutes) return '—';
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest}m`;
  return rest === 0 ? `${hours}h` : `${hours}h ${rest}m`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return '—';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}
