/**
 * The administrator's activity review (`/api/v1/activity/`): the audit log
 * read as a feed of sentences, and each staff member's figures for a period.
 */

import { apiFetch, queryString } from './api';
import type { ActivityFeedEntry, ActivityScorecards, Paginated } from '@/types/api';

export interface FeedQuery {
  since?: string;
  until?: string;
  actor?: string;
  role?: string;
  kind?: string;
  branch?: string;
  search?: string;
  page?: number;
  page_size?: number;
}

export async function getActivityFeed(
  query: FeedQuery = {},
): Promise<Paginated<ActivityFeedEntry>> {
  return apiFetch<Paginated<ActivityFeedEntry>>(
    `/api/v1/activity/feed/${queryString({ ...query })}`,
  );
}

export async function getActivityScorecards(query: {
  period: 'today' | 'week' | 'month' | 'custom';
  since?: string;
  until?: string;
  branch?: string;
  role?: string;
}): Promise<ActivityScorecards> {
  return apiFetch<ActivityScorecards>(`/api/v1/activity/scorecards/${queryString({ ...query })}`);
}
