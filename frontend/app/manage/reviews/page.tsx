'use client';

/**
 * Reviews due — the destination the manager dashboard's `reviews_due` tile
 * links to (`API_CONTRACTS.md`: "GET /dashboards/manager/ … adds … reviews_
 * due"). Neither `/manage/trainers` nor a dedicated reviews list existed
 * before this phase (`lib/manage.ts`'s module docstring), so this is the new
 * home the brief asks for: every `PerformanceReview` the caller may see
 * (`GET /performance/reviews/`), most overdue first, each row opening the
 * subject's own page — where `ReviewsPanel` (`components/manage/
 * reviews-panel.tsx`) is where the actual editing happens. This page is a
 * queue, not a second authoring surface.
 *
 * "Due" has no fixed backend definition to read here (`ReviewListView`
 * returns the whole visible set, not a `due` flag), so this reads it the
 * same way any manager would eyeball the register: a review whose `next_
 * review_at` has passed, or a `draft` with no next date set yet — flagged
 * with a badge, not filtered out by default, since a review that is *not*
 * due is still useful context once you are already looking at the list.
 */
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Select } from '@/components/ui/input';
import { ApiError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { fallback, formatDate, NO_DATA, UNKNOWN } from '@/lib/format';
import { REVIEW_STATUS_LABEL, REVIEW_STATUS_VARIANT, REVIEW_TYPE_LABEL } from '@/lib/labels';
import { listReviews } from '@/lib/performance';
import type { PerformanceReview, PerformanceSubjectType } from '@/types/api';

function isDue(review: PerformanceReview, today: string): boolean {
  if (review.next_review_at) return review.next_review_at <= today;
  return review.status === 'draft';
}

function subjectHref(review: PerformanceReview): string | null {
  if (review.subject_type === 'trainer' && review.trainer) return `/manage/trainers/${review.trainer}`;
  if (review.subject_type === 'student' && review.student) return `/students/${review.student}?tab=enrollment`;
  return null;
}

function subjectName(review: PerformanceReview): string {
  if (review.subject_type === 'trainer') return fallback(review.trainer_name, UNKNOWN);
  return fallback(review.student_name, UNKNOWN);
}

interface Filters {
  subjectType: '' | PerformanceSubjectType;
  dueOnly: boolean;
}

export function ReviewsDueWorkspace() {
  const [reviews, setReviews] = useState<PerformanceReview[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [filters, setFilters] = useState<Filters>({ subjectType: '', dueOnly: true });

  const load = useCallback(() => {
    let cancelled = false;
    listReviews()
      .then((rows) => {
        if (!cancelled) {
          setReviews(rows);
          setError(null);
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof ApiError ? cause : null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => load(), [load]);

  const today = new Date().toISOString().slice(0, 10);
  const rows = (reviews ?? [])
    .filter((review) => !filters.subjectType || review.subject_type === filters.subjectType)
    .filter((review) => !filters.dueOnly || isDue(review, today))
    .sort((a, b) => (a.next_review_at ?? '9999-99-99').localeCompare(b.next_review_at ?? '9999-99-99'));

  return (
    <div className="animate-rise-in space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Reviews due</h1>
        <p className="text-sm text-muted-foreground">
          Performance reviews needing your attention — overdue by their own next-review date, or
          still a draft with no date set.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <Select
          aria-label="Subject"
          value={filters.subjectType}
          onChange={(event) =>
            setFilters((current) => ({ ...current, subjectType: event.target.value as '' | PerformanceSubjectType }))
          }
          className="w-44"
        >
          <option value="">Trainers and students</option>
          <option value="trainer">Trainers only</option>
          <option value="student">Students only</option>
        </Select>
        <div className="flex h-10 items-center gap-2 rounded-md border border-border px-3 text-sm">
          <Checkbox
            aria-label="Due only"
            checked={filters.dueOnly}
            onCheckedChange={(checked) => setFilters((current) => ({ ...current, dueOnly: Boolean(checked) }))}
          />
          <span>Due only</span>
        </div>
      </div>

      {error ? (
        <ErrorState
          title="Could not load reviews"
          message={error.message}
          requestId={error.requestId || undefined}
          onRetry={load}
        />
      ) : reviews === null ? (
        <LoadingState label="Loading reviews…" rows={4} />
      ) : rows.length === 0 ? (
        <EmptyState
          title="Nothing due"
          description="No performance review currently needs action under these filters."
        />
      ) : (
        <ul className="stagger divide-y divide-border rounded-[var(--radius-card)] border border-border">
          {rows.map((review) => {
            const href = subjectHref(review);
            const due = isDue(review, today);
            const row = (
              <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate font-medium">{subjectName(review)}</span>
                    <Badge variant="neutral">{review.subject_type === 'trainer' ? 'Trainer' : 'Student'}</Badge>
                    <Badge variant="neutral">{REVIEW_TYPE_LABEL[review.review_type]}</Badge>
                    <Badge variant={REVIEW_STATUS_VARIANT[review.status]}>{REVIEW_STATUS_LABEL[review.status]}</Badge>
                    {due ? <Badge variant="error">Due</Badge> : null}
                  </div>
                  <p className="truncate text-sm text-muted-foreground">{fallback(review.summary, NO_DATA)}</p>
                </div>
                <p className="whitespace-nowrap text-xs text-muted-foreground">
                  {review.next_review_at
                    ? `Next review ${formatDate(review.next_review_at)}`
                    : `Recorded ${formatDate(review.created_at)}`}
                </p>
              </div>
            );
            return (
              <li
                key={review.id}
                className="animate-fade-in transition-colors hover:bg-muted/40"
                data-testid="review-due-row"
              >
                {href ? (
                  <Link href={href} className="block">
                    {row}
                  </Link>
                ) : (
                  row
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default function ManageReviewsPage() {
  return (
    <RequireAuth capability={Capability.performanceViewAny}>
      <ReviewsDueWorkspace />
    </RequireAuth>
  );
}
