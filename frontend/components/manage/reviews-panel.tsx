'use client';

/**
 * The "Reviews" section on a trainer's or a student's own detail page:
 * every `PerformanceReview` recorded against them, and — for a caller who
 * holds `review.manage_any` — the "New review"/"Edit" actions that open
 * `ReviewDialog`.
 *
 * `listReviews()` has no subject filter on the server yet (`ReviewListView
 * .get` takes no query parameters — see `lib/performance.ts`'s own
 * docstring), so this reads the caller's whole visible set and filters by
 * `trainer`/`student` id client-side, the same trade-off `lib/manage.ts`'s
 * `listFeedback` already makes for the same reason, at the same data
 * volumes.
 */
import { useCallback, useEffect, useState } from 'react';

import { ReviewDialog } from '@/components/manage/review-dialog';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ApiError } from '@/lib/api';
import { REVIEW_STATUS_LABEL, REVIEW_STATUS_VARIANT, REVIEW_TYPE_LABEL } from '@/lib/labels';
import { fallback, formatDate, NO_DATA } from '@/lib/format';
import { listReviews } from '@/lib/performance';
import type { PerformanceReview, PerformanceSubjectType } from '@/types/api';

export interface ReviewsPanelProps {
  subjectType: PerformanceSubjectType;
  subjectId: string;
  /** Whether this caller may write reviews (`review.manage_any`) — a caller
   *  without it sees the same list, read-only. */
  canManage: boolean;
}

export function ReviewsPanel({ subjectType, subjectId, canManage }: ReviewsPanelProps) {
  const [reviews, setReviews] = useState<PerformanceReview[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [dialogReview, setDialogReview] = useState<PerformanceReview | null>(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  const load = useCallback(() => {
    let cancelled = false;
    listReviews()
      .then((all) => {
        if (cancelled) return;
        const key: keyof PerformanceReview = subjectType === 'trainer' ? 'trainer' : 'student';
        setReviews(all.filter((review) => review[key] === subjectId));
        setError(null);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof ApiError ? cause : null);
      });
    return () => {
      cancelled = true;
    };
  }, [subjectType, subjectId]);

  useEffect(() => load(), [load]);

  function openNew() {
    setDialogReview(null);
    setIsDialogOpen(true);
  }

  function openEdit(review: PerformanceReview) {
    setDialogReview(review);
    setIsDialogOpen(true);
  }

  return (
    <div className="space-y-4">
      {error ? (
        <ErrorState
          title="Could not load reviews"
          message={error.message}
          requestId={error.requestId || undefined}
          onRetry={load}
        />
      ) : reviews === null ? (
        <LoadingState label="Loading reviews…" rows={2} />
      ) : reviews.length === 0 ? (
        <EmptyState title="No reviews yet" description="Nobody has recorded a performance review here." />
      ) : (
        <ul className="divide-y divide-border rounded-card border border-border">
          {reviews.map((review) => (
            <li
              key={review.id}
              className="animate-fade-in space-y-1.5 px-4 py-3 transition-colors hover:bg-muted/40"
              data-testid="performance-review-row"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">
                    {formatDate(review.period_start)} – {formatDate(review.period_end)}
                  </span>
                  <Badge variant="neutral">{REVIEW_TYPE_LABEL[review.review_type]}</Badge>
                  <Badge variant={REVIEW_STATUS_VARIANT[review.status]}>
                    {REVIEW_STATUS_LABEL[review.status]}
                  </Badge>
                </div>
                <div className="flex items-center gap-2">
                  <Badge>{review.rating} / 5</Badge>
                  {canManage ? (
                    <Button type="button" variant="ghost" size="sm" onClick={() => openEdit(review)}>
                      Edit
                    </Button>
                  ) : null}
                </div>
              </div>
              <p className="text-sm">{fallback(review.summary, NO_DATA)}</p>
              {review.next_review_at ? (
                <p className="text-xs text-muted-foreground">
                  Next review due {formatDate(review.next_review_at)}
                </p>
              ) : null}
              <p className="text-xs text-muted-foreground">
                By {fallback(review.reviewer_name, 'Unknown')} · {formatDate(review.created_at)}
              </p>
            </li>
          ))}
        </ul>
      )}

      {canManage ? (
        <Button type="button" variant="outline" size="sm" onClick={openNew}>
          New review
        </Button>
      ) : null}

      <ReviewDialog
        open={isDialogOpen}
        onOpenChange={setIsDialogOpen}
        subjectType={subjectType}
        subjectId={subjectId}
        review={dialogReview}
        onSaved={load}
      />
    </div>
  );
}
