'use client';

import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError } from '@/lib/api';
import { QUESTION_TYPE_LABEL, formatDateTime } from '@/lib/academic-labels';
import { getAttemptReview } from '@/lib/exams';
import type { AttemptReview } from '@/types/api';

/**
 * A marked paper, question by question.
 *
 * Reachable only once the examination's results have been released — the
 * backend refuses it otherwise, and the explanations are part of what is being
 * withheld until then.
 */
function Review({ attemptId }: { attemptId: string }) {
  const [review, setReview] = useState<AttemptReview | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getAttemptReview(attemptId)
      .then((data) => {
        if (!cancelled) setReview(data);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof ApiError ? cause : null);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [attemptId]);

  if (isLoading) return <LoadingState label="Loading your paper…" rows={6} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load this paper"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }
  if (!review) return null;

  const { attempt } = review;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <span className="font-mono text-xs text-muted-foreground">{attempt.exam_code}</span>
        <h1 className="text-2xl font-semibold tracking-tight">{attempt.exam_title}</h1>
        <p className="text-sm text-muted-foreground">
          Submitted {formatDateTime(attempt.submitted_at)} · attempt {attempt.attempt_number}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle data-testid="review-score">
            {attempt.total_score} / {attempt.max_score}
          </CardTitle>
          <CardDescription>
            {attempt.percentage === null ? null : `${attempt.percentage}% · `}
            {attempt.is_passing === null
              ? 'No pass mark set'
              : attempt.is_passing
                ? 'Pass'
                : 'Below the pass mark'}
          </CardDescription>
        </CardHeader>
      </Card>

      {review.questions.map((question) => (
        <Card key={question.position} data-testid="review-question">
          <CardHeader className="gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="neutral">Question {question.position + 1}</Badge>
              {question.is_correct === null ? (
                <Badge variant="neutral">Marked by a person</Badge>
              ) : (
                <Badge variant={question.is_correct ? 'success' : 'error'}>
                  {question.is_correct ? 'Correct' : 'Incorrect'}
                </Badge>
              )}
              <span className="text-xs text-muted-foreground">
                {question.awarded ?? '—'} of {question.marks}
              </span>
            </div>
            <CardTitle className="text-base">{question.question_text}</CardTitle>
            <CardDescription>{QUESTION_TYPE_LABEL[question.question_type]}</CardDescription>
          </CardHeader>

          {question.explanation || question.marker_feedback ? (
            <CardContent className="space-y-2 text-sm">
              {question.explanation ? (
                <p className="whitespace-pre-wrap">{question.explanation}</p>
              ) : null}
              {question.marker_feedback ? (
                <p className="whitespace-pre-wrap text-muted-foreground">
                  {question.marker_feedback}
                </p>
              ) : null}
            </CardContent>
          ) : null}
        </Card>
      ))}
    </div>
  );
}

export default function AttemptReviewPage() {
  const params = useParams<{ attemptId: string }>();
  return (
    <RequireAuth>
      <Review attemptId={params.attemptId} />
    </RequireAuth>
  );
}
