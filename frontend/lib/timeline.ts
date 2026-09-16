/**
 * One student's composed timeline (`GET /students/{id}/timeline/`, ADR-09).
 *
 * The endpoint merges rows from every registered source app through that
 * app's own `visible_*` queryset — "can this caller see this student" is
 * already enforced server-side, so this client does no authorization work
 * of its own, only shape and query-string plumbing.
 */

import { apiFetch, queryString } from './api';
import type { TimelineResponse } from '@/types/api';

export interface TimelineQuery {
  /** Restrict to these kinds; omitted (or empty) means every kind. */
  kinds?: string[];
  since?: string;
  until?: string;
  /** The previous page's `next_cursor`, to continue past it. */
  cursor?: string;
  pageSize?: number;
}

export async function getStudentTimeline(
  studentId: string,
  query: TimelineQuery = {},
): Promise<TimelineResponse> {
  return apiFetch<TimelineResponse>(
    `/api/v1/students/${encodeURIComponent(studentId)}/timeline/${queryString({
      kinds: query.kinds && query.kinds.length > 0 ? query.kinds.join(',') : undefined,
      since: query.since,
      until: query.until,
      cursor: query.cursor,
      page_size: query.pageSize,
    })}`,
  );
}
