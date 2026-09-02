'use client';

import { useCallback, useEffect, useState } from 'react';

import { Alert, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError, fieldErrors } from '@/lib/api';
import { getPublishChecklist, setCourseStatus } from '@/lib/courses';
import { STATUS_LABEL, STATUS_VARIANT } from '@/lib/course-labels';
import type { CourseDetail, PublishChecklist, PublishStatus } from '@/types/api';

/**
 * Which transitions to offer.
 *
 * The server owns the real transition table and re-checks every request; this
 * only decides which buttons to draw. `can_publish` comes from the server too —
 * an assigned editor is offered "Submit for review" where an owner is offered
 * "Publish".
 */
function transitionsFor(course: CourseDetail): { target: PublishStatus; label: string }[] {
  const { status, can_publish: canPublish } = course;

  if (status === 'draft') {
    return canPublish
      ? [
          { target: 'published', label: 'Publish' },
          { target: 'in_review', label: 'Submit for review' },
        ]
      : [{ target: 'in_review', label: 'Submit for review' }];
  }
  if (status === 'in_review') {
    return canPublish
      ? [
          { target: 'published', label: 'Approve and publish' },
          { target: 'draft', label: 'Send back to draft' },
        ]
      : [{ target: 'draft', label: 'Withdraw from review' }];
  }
  if (status === 'published') {
    return canPublish
      ? [
          { target: 'draft', label: 'Unpublish' },
          { target: 'archived', label: 'Archive' },
        ]
      : [];
  }
  return canPublish ? [{ target: 'draft', label: 'Restore to draft' }] : [];
}

export function PublishPanel({
  course,
  onChanged,
}: {
  course: CourseDetail;
  onChanged: () => void | Promise<void>;
}) {
  const [checklist, setChecklist] = useState<PublishChecklist | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [blockers, setBlockers] = useState<string[]>([]);
  const [isBusy, setIsBusy] = useState(false);

  const loadChecklist = useCallback(() => {
    getPublishChecklist(course.id)
      .then(setChecklist)
      .catch(() => setChecklist(null));
  }, [course.id]);

  useEffect(() => {
    loadChecklist();
  }, [loadChecklist]);

  async function onTransition(target: PublishStatus) {
    setIsBusy(true);
    setErrors({});
    setBlockers([]);
    try {
      await setCourseStatus(course.id, target);
      await onChanged();
      loadChecklist();
    } catch (cause) {
      if (cause instanceof ApiError && Array.isArray(cause.details?.status)) {
        // The publish checklist comes back as a list of specific blockers.
        setBlockers(cause.details.status as string[]);
      } else {
        setErrors(fieldErrors(cause));
      }
    } finally {
      setIsBusy(false);
    }
  }

  const transitions = transitionsFor(course);

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="flex-1">Publishing</CardTitle>
          <Badge variant={STATUS_VARIANT[course.status]}>{STATUS_LABEL[course.status]}</Badge>
        </div>
        <CardDescription>
          {course.can_publish
            ? 'You can change this course’s status.'
            : 'You can edit this course and submit it for review. An owner or administrator publishes it.'}
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-3">
        {errors.__all__ || errors.status ? (
          <Alert variant="error">{errors.status ?? errors.__all__}</Alert>
        ) : null}

        {blockers.length > 0 ? (
          <Alert variant="warning" className="space-y-2">
            <AlertTitle>Not ready to publish</AlertTitle>
            <ul className="list-inside list-disc text-muted-foreground">
              {blockers.map((blocker) => (
                <li key={blocker}>{blocker}</li>
              ))}
            </ul>
          </Alert>
        ) : checklist && !checklist.ready && course.status !== 'published' ? (
          <Alert variant="info" className="space-y-2">
            <AlertTitle>Before this course can be published</AlertTitle>
            <ul className="list-inside list-disc text-muted-foreground">
              {checklist.blockers.map((blocker) => (
                <li key={blocker}>{blocker}</li>
              ))}
            </ul>
          </Alert>
        ) : null}

        {transitions.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No status changes are available to you for this course.
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {transitions.map((transition) => (
              <Button
                key={transition.target}
                size="sm"
                variant={transition.target === 'published' ? 'primary' : 'outline'}
                disabled={isBusy}
                onClick={() => void onTransition(transition.target)}
              >
                {transition.label}
              </Button>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
